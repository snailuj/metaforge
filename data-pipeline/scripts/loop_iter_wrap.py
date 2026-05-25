"""Karpathy loop iteration wrapper — orchestrator pre/post hooks.

Automates the mechanical parts of the loop driver around each
iteration:

- **pre mode:** snapshot lexicon_v2.db, record loop HEAD SHA + DB
  md5 + baseline JSON copy, chmod a-w on the immutable file set
  (filesystem-level write protection for cohort fixtures, harness
  module, baseline JSON, canonical DB). Emit a JSON object the
  orchestrator threads into the post invocation.
- **post mode:** check DB hash for unauthorised mutation, run the
  full Python + Go test suites (only when the iteration committed
  cleanly — saves a ~3-4 min test run on revert outcomes), restore
  / hard-reset / force-revert as needed, refresh baseline JSON on a
  clean commit, leave immutable files unlocked for the orchestrator
  between iterations (next pre hook re-locks). Emit a final outcome
  JSON.

Test running is the orchestrator's responsibility per the v2
iteration contract: iteration agents only run the eval harness for
their commit-or-revert decision; the wrapper runs the full project
test suites between iterations as the safety net for regressions
the cohort metric can't catch (snap_properties.py drift, Go API
breakage, etc.). This frees the iteration's 15-min implementation
budget from test-orchestration overhead.

The light code review (looking for cohort-data hardcoding) is the
orchestrator's own subagent dispatch and lives outside this script —
this script handles only the deterministic mechanical checks.

Usage::

    # Before spawning an iteration:
    python data-pipeline/scripts/loop_iter_wrap.py --mode pre \\
        --iter-id 7

    # After the iteration agent reports back:
    python data-pipeline/scripts/loop_iter_wrap.py --mode post \\
        --pre-sha <from pre> \\
        --pre-db-hash <from pre> \\
        --snapshot-path <from pre> \\
        --outcome <iteration's reported outcome string>

Both modes emit a single JSON object to stdout. The orchestrator
captures and threads them.

Run this script FROM the worktree where the loop is checked out
(`.worktrees/loop/` in the default project layout). It uses
`git rev-parse --show-toplevel` to anchor all paths; running it
from the canonical main checkout would lock the wrong files.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import stat
import subprocess
from pathlib import Path
from typing import Optional


def _repo_root() -> Path:
    """Resolve the worktree root via git. Must be invoked from inside
    the worktree being protected."""
    out = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        capture_output=True, text=True, check=True,
    )
    return Path(out.stdout.strip())


# Iteration-reported outcomes (what the iteration agent may say).
_ITERATION_OUTCOMES = {
    "committed",
    "reverted_tests_failed",
    "reverted_harness_crash",
    "reverted_metric_fail",
    "timed_out",
    "escalate_harness_flaw",
    "escalate_db_change",
}

# Final outcomes the orchestrator surfaces — superset including the
# orchestrator-only downgrades.
_FINAL_OUTCOMES = _ITERATION_OUTCOMES | {
    "reverted_db_mutation",
    "reverted_data_hack",
}


def _immutable_paths(root: Path) -> list[Path]:
    """Files chmod a-w during iteration. Operators / orchestrator
    write-unlock them between iterations to refresh baseline.

    Includes the wrapper script itself so iterations can't disable
    their own safeguards by editing this file.
    """
    return [
        # Harness module — the immutable truth-signal code.
        root / "data-pipeline" / "scripts" / "evaluate_loop_metric.py",
        root / "data-pipeline" / "scripts" / "evaluate_loop_harness.py",
        root / "data-pipeline" / "scripts" / "test_evaluate_loop_metric.py",
        root / "data-pipeline" / "scripts" / "test_evaluate_loop_harness.py",
        # The wrapper itself — iterations can't unlock anything by
        # patching the script.
        root / "data-pipeline" / "scripts" / "loop_iter_wrap.py",
        # Baseline JSON — orchestrator-only writes (refresh after
        # clean commit). Iteration would be rewriting the baseline
        # they're being measured against.
        root / "data-pipeline" / "output" / "loop_baseline.json",
        # Cohort fixtures — the data discrimination is measured on.
        # These exist as actual files in the worktree (committed).
        root / "data-pipeline" / "fixtures" / "lakoff_apt.jsonl",
        root / "data-pipeline" / "fixtures" / "lakoff_inapt.jsonl",
        # Canonical DB — symlinked from the worktree to the main
        # repo's data-pipeline/output/lexicon_v2.db. chmod follows
        # the symlink and locks the canonical file.
        root / "data-pipeline" / "output" / "lexicon_v2.db",
        # Phase 2 cohort outputs — committed in the loop branch
        # (and in main); locking prevents iterations from rewriting
        # the cohort data they're being measured on.
        root / "data-pipeline" / "output" / "metaphor_spike_apt_phase2_20260525T004154.jsonl",
        root / "data-pipeline" / "output" / "metaphor_spike_inapt_phase2_20260525T004154.jsonl",
    ]


def _chmod_lock(paths: list[Path]) -> list[dict]:
    """Remove write bits from every existing path. Returns list of
    {path, prior_mode, new_mode} for diagnostics."""
    out = []
    for p in paths:
        if not p.exists():
            continue
        # Resolve symlinks so chmod hits the real file (lexicon_v2.db
        # symlink → canonical).
        real = p.resolve()
        prior = real.stat().st_mode
        # Strip user / group / other write bits.
        new = prior & ~(stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH)
        os.chmod(real, new)
        out.append({
            "path": str(p),
            "real_path": str(real),
            "prior_mode": oct(prior),
            "new_mode": oct(new),
        })
    return out


def _chmod_unlock(paths: list[Path]) -> list[dict]:
    """Restore u+w (user write) on every existing path. Mirrors
    _chmod_lock but only adds the user-write bit (keeps group/other
    consistent with the umask)."""
    out = []
    for p in paths:
        if not p.exists():
            continue
        real = p.resolve()
        prior = real.stat().st_mode
        new = prior | stat.S_IWUSR
        os.chmod(real, new)
        out.append({
            "path": str(p),
            "real_path": str(real),
            "prior_mode": oct(prior),
            "new_mode": oct(new),
        })
    return out


def _md5(path: Path) -> str:
    """Streaming md5 — lexicon_v2.db is 400MB so don't read into memory."""
    h = hashlib.md5()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _git(args: list[str], cwd: Path) -> str:
    out = subprocess.run(
        ["git", *args], cwd=cwd, capture_output=True, text=True, check=True,
    )
    return out.stdout.strip()


def cmd_pre(iter_id: int, snapshot_dir: Path) -> dict:
    """Capture pre-state and apply OS-level write protection.

    1. Verify we're on the loop branch with a clean tree.
    2. Hash the canonical DB.
    3. Copy DB + baseline JSON to the snapshot location.
    4. Record the current HEAD SHA.
    5. chmod a-w on the immutable file set — iterations cannot
       physically write to them through any mechanism (snap reruns,
       direct sqlite3 connections, ALTER TABLE, redirected output, ...
       all fail with EACCES at the filesystem layer).
    """
    root = _repo_root()
    db = root / "data-pipeline" / "output" / "lexicon_v2.db"
    baseline = root / "data-pipeline" / "output" / "loop_baseline.json"

    branch = _git(["rev-parse", "--abbrev-ref", "HEAD"], root)
    if branch != "loop":
        raise SystemExit(
            f"loop_iter_wrap: not on loop branch (current: {branch}). "
            "Refusing to snapshot — operator must check out loop first."
        )
    dirty = _git(["status", "--porcelain"], root)
    # Filter out untracked symlinks — those are infrastructure we
    # created during worktree setup (.venv → canonical, DB symlink,
    # vectors symlink). They're never going to be committed and
    # shouldn't block the snapshot.
    significant = []
    for line in dirty.splitlines():
        if not line.strip():
            continue
        status, _, path = line.partition(" ")
        path = path.strip()
        full = root / path
        if line.startswith("??") and full.is_symlink():
            continue
        significant.append(line)
    if significant:
        raise SystemExit(
            "loop_iter_wrap: working tree has significant uncommitted "
            "changes. Refusing to snapshot.\n" + "\n".join(significant)
        )
    if not db.exists():
        raise SystemExit(f"loop_iter_wrap: DB missing: {db}")
    if not baseline.exists():
        raise SystemExit(f"loop_iter_wrap: baseline missing: {baseline}")

    snapshot_dir.mkdir(parents=True, exist_ok=True)
    snapshot_path = snapshot_dir / f"lexicon_v2.db.loop-iter{iter_id}-pre"
    baseline_snapshot = snapshot_dir / f"loop_baseline.json.loop-iter{iter_id}-pre"

    shutil.copy2(db, snapshot_path)
    shutil.copy2(baseline, baseline_snapshot)

    pre_db_hash = _md5(db)
    pre_sha = _git(["rev-parse", "HEAD"], root)

    locked = _chmod_lock(_immutable_paths(root))

    return {
        "iter_id": iter_id,
        "root": str(root),
        "pre_sha": pre_sha,
        "pre_db_hash": pre_db_hash,
        "snapshot_path": str(snapshot_path),
        "baseline_snapshot_path": str(baseline_snapshot),
        "locked_files": locked,
    }


def _run_python_tests(root: Path, venv_python: Path) -> tuple[bool, str]:
    """Run the Python test suite. Returns (passed, stdout+stderr tail)."""
    out = subprocess.run(
        [str(venv_python), "-m", "pytest", "data-pipeline/", "-q", "--tb=short"],
        cwd=root, capture_output=True, text=True,
        timeout=300,  # 5 min cap; current full suite is ~70s
    )
    passed = out.returncode == 0
    # Capture tail for diagnostics — full output would bloat the orchestrator
    # log; the operator can re-run pytest manually if they want full detail.
    combined = (out.stdout + out.stderr)[-4000:]
    return passed, combined


def _run_go_tests(root: Path) -> tuple[bool, str]:
    """Run the Go test suite. Returns (passed, stdout+stderr tail).

    The previously-deadlocking TestCascadeUnion_ClassicalPairsSurface_
    AsCandidates is now ~110s for all 4 subcases; the full suite
    fits well inside the 5-min cap.
    """
    # Handler suite alone takes ~200s when ClassicalPairs is included
    # (the four anchor subcases at TopK=10000 burn ~110s combined).
    # Plus 40s for thesaurus + 20s for db. Total ~280s baseline,
    # leaving headroom for variation gives the 540s go-test cap.
    out = subprocess.run(
        ["/usr/local/go/bin/go", "test", "-timeout", "540s", "./..."],
        cwd=root / "api", capture_output=True, text=True,
        timeout=720,
    )
    passed = out.returncode == 0
    combined = (out.stdout + out.stderr)[-4000:]
    return passed, combined


def cmd_post(
    pre_sha: str,
    pre_db_hash: str,
    snapshot_path: Path,
    baseline_snapshot_path: Optional[Path],
    outcome: str,
) -> dict:
    """Check post-state, apply mechanical gates, restore write perms.

    Order:
    1. Unlock immutables (so the orchestrator can act on them — restore
       DB, hard-reset branch, refresh baseline).
    2. DB hash gate: if hash changed, restore from snapshot, hard-reset
       branch if iteration committed, force OUTCOME=reverted_db_mutation.
    3. Test gate (only when iteration committed cleanly + DB unchanged):
       run Python + Go test suites. If either fails, hard-reset branch
       and force OUTCOME=reverted_tests_failed. Tests are skipped on
       revert / timeout / escalate outcomes since the branch will be
       reset to pre_sha anyway.
    4. Revert / timeout / escalate outcomes: ensure branch didn't
       advance — hard-reset if it did.
    5. Clean commit outcome: refresh baseline JSON by re-running the
       harness in --mode baseline.

    Immutable files are LEFT UNLOCKED on exit — the next iteration's
    pre call will lock them again. This avoids the orchestrator being
    unable to refresh baseline mid-loop.
    """
    if outcome not in _ITERATION_OUTCOMES and outcome not in _FINAL_OUTCOMES:
        raise SystemExit(
            f"loop_iter_wrap: unknown outcome {outcome!r}. "
            f"Allowed: {sorted(_FINAL_OUTCOMES)}"
        )

    root = _repo_root()
    db = root / "data-pipeline" / "output" / "lexicon_v2.db"
    baseline = root / "data-pipeline" / "output" / "loop_baseline.json"
    venv_python = root / ".venv" / "bin" / "python"
    harness = root / "data-pipeline" / "scripts" / "evaluate_loop_harness.py"

    branch = _git(["rev-parse", "--abbrev-ref", "HEAD"], root)
    if branch != "loop":
        raise SystemExit(
            f"loop_iter_wrap: not on loop branch (current: {branch})."
        )

    # Step 1 — unlock so we can act.
    _chmod_unlock(_immutable_paths(root))

    current_sha = _git(["rev-parse", "HEAD"], root)
    iteration_advanced = current_sha != pre_sha

    db_hash_changed = _md5(db) != pre_db_hash
    db_restored = False
    branch_reset = False
    baseline_refreshed = False
    final_outcome = outcome

    # Step 2 — DB mutation gate.
    if db_hash_changed:
        shutil.copy2(snapshot_path, db)
        db_restored = True
        if iteration_advanced:
            _git(["reset", "--hard", pre_sha], root)
            branch_reset = True
            iteration_advanced = False
        final_outcome = "reverted_db_mutation"

    # Step 3 — Test gate. Run pytest + go test only when the iteration
    # COMMITTED cleanly so far. On revert/timeout/escalate outcomes
    # the branch will be reset back to pre_sha (which had tests
    # passing already), so re-running them would be ~5 min of waste.
    tests_passed: Optional[bool] = None
    python_tail = None
    go_tail = None
    if (
        final_outcome == "committed"
        and iteration_advanced
        and not db_hash_changed
    ):
        venv_python = root / ".venv" / "bin" / "python"
        if not venv_python.exists():
            raise SystemExit(
                f"loop_iter_wrap: venv python missing at {venv_python}."
            )
        py_ok, python_tail = _run_python_tests(root, venv_python)
        go_ok, go_tail = _run_go_tests(root)
        tests_passed = py_ok and go_ok
        if not tests_passed:
            _git(["reset", "--hard", pre_sha], root)
            branch_reset = True
            iteration_advanced = False
            final_outcome = "reverted_tests_failed"

    # Step 4 — revert / timeout / escalate outcomes must leave branch
    # at pre_sha. Defensive guard against an iteration that committed
    # despite reporting one of these outcomes.
    revert_outcomes = (
        "reverted_tests_failed", "reverted_harness_crash",
        "reverted_metric_fail", "reverted_db_mutation",
        "reverted_data_hack",
        "timed_out", "escalate_harness_flaw", "escalate_db_change",
    )
    if final_outcome in revert_outcomes and iteration_advanced:
        _git(["reset", "--hard", pre_sha], root)
        branch_reset = True
        iteration_advanced = False

    # Step 5 — clean commit refresh.
    baseline_refresh_error = None
    if final_outcome == "committed" and iteration_advanced and not db_hash_changed:
        if not venv_python.exists():
            raise SystemExit(
                f"loop_iter_wrap: venv python missing at {venv_python}."
            )
        out = subprocess.run(
            [
                str(venv_python), str(harness),
                "--mode", "baseline",
                "--output", str(baseline),
            ],
            cwd=root, capture_output=True, text=True,
        )
        if out.returncode != 0:
            baseline_refresh_error = out.stderr
        else:
            baseline_refreshed = True

    return {
        "root": str(root),
        "iter_id_pre_sha": pre_sha,
        "final_outcome": final_outcome,
        "db_restored": db_restored,
        "branch_reset": branch_reset,
        "tests_ran": tests_passed is not None,
        "tests_passed": tests_passed,
        "baseline_refreshed": baseline_refreshed,
        "baseline_refresh_error": baseline_refresh_error,
        # Stderr/stdout tails surface only when the gate fires —
        # otherwise None to keep the orchestrator log compact.
        "python_test_tail": python_tail if tests_passed is False else None,
        "go_test_tail": go_tail if tests_passed is False else None,
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("--mode", choices=("pre", "post"), required=True)
    ap.add_argument("--snapshot-dir", type=Path, default=Path("/tmp"))
    ap.add_argument("--iter-id", type=int, default=0)
    ap.add_argument("--pre-sha", type=str)
    ap.add_argument("--pre-db-hash", type=str)
    ap.add_argument("--snapshot-path", type=Path)
    ap.add_argument("--baseline-snapshot-path", type=Path)
    ap.add_argument("--outcome", type=str)
    args = ap.parse_args(argv)

    if args.mode == "pre":
        result = cmd_pre(args.iter_id, args.snapshot_dir)
    else:
        for required in ("pre_sha", "pre_db_hash", "snapshot_path", "outcome"):
            if getattr(args, required) is None:
                raise SystemExit(f"--mode post requires --{required.replace('_','-')}")
        result = cmd_post(
            pre_sha=args.pre_sha,
            pre_db_hash=args.pre_db_hash,
            snapshot_path=args.snapshot_path,
            baseline_snapshot_path=args.baseline_snapshot_path,
            outcome=args.outcome,
        )

    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
