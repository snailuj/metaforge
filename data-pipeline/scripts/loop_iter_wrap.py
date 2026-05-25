"""Karpathy loop iteration wrapper — orchestrator pre/post hooks.

Automates the mechanical parts of the loop driver around each
iteration:

- **pre mode:** snapshot lexicon_v2.db, record loop HEAD SHA + DB
  md5 + baseline JSON copy. Emit a JSON object the orchestrator
  threads into the post invocation.
- **post mode:** check DB hash for unauthorised mutation, restore
  from snapshot if changed, hard-reset loop branch if the iteration
  also committed, refresh baseline JSON on a clean commit. Emit a
  final outcome JSON.

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
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Optional


# These paths are anchored at the repo root so the wrapper can be
# invoked from anywhere. The repo root is computed via git rev-parse.
def _repo_root() -> Path:
    out = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        capture_output=True, text=True, check=True,
    )
    return Path(out.stdout.strip())


# Outcome categories the iteration agent may report. Order matters:
# the lookup table below maps each to a status code.
_ITERATION_OUTCOMES = {
    "committed",
    "reverted_tests_failed",
    "reverted_harness_crash",
    "reverted_metric_fail",
    "timed_out",
    "escalate_harness_flaw",
    "escalate_db_change",
}

# Final outcomes the orchestrator surfaces (a superset of the
# iteration-reported ones).
_FINAL_OUTCOMES = _ITERATION_OUTCOMES | {
    "reverted_db_mutation",
    "reverted_data_hack",
}


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


def _git_safe(args: list[str], cwd: Path) -> tuple[int, str, str]:
    """Non-raising git invocation. Returns (returncode, stdout, stderr)."""
    out = subprocess.run(
        ["git", *args], cwd=cwd, capture_output=True, text=True,
    )
    return out.returncode, out.stdout.strip(), out.stderr.strip()


def cmd_pre(iter_id: int, snapshot_dir: Path) -> dict:
    """Capture pre-state.

    1. Verify we're on the loop branch with a clean tree (uncommitted
       changes would mean a prior iteration didn't clean up).
    2. Hash the canonical DB.
    3. Copy the DB to the snapshot location.
    4. Copy the baseline JSON to a parallel snapshot.
    5. Record the current HEAD SHA.
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
    if dirty:
        raise SystemExit(
            f"loop_iter_wrap: working tree is not clean. "
            f"Refusing to snapshot.\n{dirty}"
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

    return {
        "iter_id": iter_id,
        "pre_sha": pre_sha,
        "pre_db_hash": pre_db_hash,
        "snapshot_path": str(snapshot_path),
        "baseline_snapshot_path": str(baseline_snapshot),
    }


def cmd_post(
    pre_sha: str,
    pre_db_hash: str,
    snapshot_path: Path,
    baseline_snapshot_path: Optional[Path],
    outcome: str,
) -> dict:
    """Check post-state and apply mechanical gates.

    Gate order (each gate either passes through or downgrades the
    outcome):

    1. DB hash gate. If the canonical DB hash changed: restore from
       snapshot. If the iteration also committed (loop HEAD != pre_sha),
       hard-reset loop. Force outcome = reverted_db_mutation.
    2. (Light code review gate is orchestrator-driven, NOT this
       script's job. The orchestrator runs that BEFORE invoking us
       and either keeps OUTCOME=committed or downgrades to
       reverted_data_hack. We honour the outcome it tells us.)
    3. If final outcome is reverted_*, hard-reset loop branch to
       pre_sha if it advanced.
    4. If final outcome is committed AND DB unchanged AND no other
       gate fired: refresh baseline JSON so the next iteration
       compares against the new HEAD.
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

    current_sha = _git(["rev-parse", "HEAD"], root)
    iteration_advanced = current_sha != pre_sha

    db_hash_changed = _md5(db) != pre_db_hash
    db_restored = False
    branch_reset = False
    baseline_refreshed = False
    final_outcome = outcome

    # Gate 1: DB mutation.
    if db_hash_changed:
        shutil.copy2(snapshot_path, db)
        db_restored = True
        if iteration_advanced:
            _git(["reset", "--hard", pre_sha], root)
            branch_reset = True
            iteration_advanced = False  # no longer advanced
        final_outcome = "reverted_db_mutation"

    # Gate 3: revert outcomes — make sure branch is at pre_sha.
    if final_outcome.startswith("reverted_") and iteration_advanced:
        _git(["reset", "--hard", pre_sha], root)
        branch_reset = True
        iteration_advanced = False

    # Gate 3b: timed_out / escalate_* outcomes — same, ensure branch
    # didn't advance. The iteration shouldn't have committed in these
    # cases but check defensively.
    if final_outcome in ("timed_out", "escalate_harness_flaw", "escalate_db_change") and iteration_advanced:
        _git(["reset", "--hard", pre_sha], root)
        branch_reset = True
        iteration_advanced = False

    # Gate 4: refresh baseline on a clean commit.
    if final_outcome == "committed" and iteration_advanced and not db_hash_changed:
        if not venv_python.exists():
            raise SystemExit(
                f"loop_iter_wrap: venv python missing at {venv_python}. "
                "Run `python3 -m venv .venv && pip install -r ...` at repo root."
            )
        out = subprocess.run(
            [
                str(venv_python), str(harness),
                "--mode", "baseline",
                "--output", str(baseline),
            ],
            cwd=root,
            capture_output=True, text=True,
        )
        if out.returncode != 0:
            # Baseline refresh failed — committed change is still in
            # place but the next iteration's baseline is stale. Flag
            # but don't override outcome — the operator decides whether
            # to revert.
            return {
                "iter_id_pre_sha": pre_sha,
                "final_outcome": final_outcome,
                "db_restored": db_restored,
                "branch_reset": branch_reset,
                "baseline_refreshed": False,
                "baseline_refresh_error": out.stderr,
            }
        baseline_refreshed = True

    return {
        "iter_id_pre_sha": pre_sha,
        "final_outcome": final_outcome,
        "db_restored": db_restored,
        "branch_reset": branch_reset,
        "baseline_refreshed": baseline_refreshed,
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
