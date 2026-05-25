"""Karpathy loop eval harness — the truth-signal entry point.

This script is **immutable per loop iteration** — iteration subagents
MUST NOT modify it. Use the operator-escalation hatch
(``OUTCOME=escalate_harness_flaw``) if you genuinely cannot work
around a harness flaw. Anything else fails the commit gate.

What it does:

1. Loads the two cohorts the loop scores against:
   - Phase 2 spike cohort (200 topics, ~1700 (topic, vehicle) pairs)
   - M01 Lakoff cohort (~30 Lakoff classes, 170 pairs)
2. Scores both cohorts through the current cascade
   (``evaluate_cascade.evaluate_cascade_pair``) with production config.
3. Computes the loop's truth metrics via the immutable
   ``evaluate_loop_metric`` module:
   - Phase 2: bootstrap median ratio (10 resamples, 80% topic-level)
   - Lakoff:  deterministic end-to-end ratio
4. In ``--mode baseline``, writes the structured result to a JSON file.
5. In ``--mode compare``, reads a baseline JSON and emits a structured
   PASS/FAIL verdict against the configured commit gate
   (Phase 2 median must improve; Lakoff must not relative-degrade
   beyond tolerance).

Usage::

    # Capture baseline before the iteration agent runs
    python data-pipeline/scripts/evaluate_loop_harness.py \\
        --mode baseline \\
        --output data-pipeline/output/loop_baseline.json

    # Score current code and compare to baseline (the iteration's
    # commit/revert decision reads this output)
    python data-pipeline/scripts/evaluate_loop_harness.py \\
        --mode compare \\
        --baseline data-pipeline/output/loop_baseline.json \\
        --output data-pipeline/output/loop_current.json
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "lib"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import argparse
import json
import logging
import sqlite3
from contextlib import closing
from dataclasses import asdict
from datetime import datetime

from evaluate_aptness import lookup_primary_synset
from evaluate_cascade import CascadeConfig, evaluate_cascade_pair
from evaluate_loop_metric import (
    bootstrap_e2e_ratio,
    compare_metrics,
    end_to_end_ratio,
)

log = logging.getLogger(__name__)


# Default cohort paths — overridable via CLI but the production loop
# always uses these. Captured as constants so the loop driver's prompt
# can refer to them unambiguously.
DEFAULT_PHASE2_APT = Path("data-pipeline/output/metaphor_spike_apt_phase2_20260525T004154.jsonl")
DEFAULT_PHASE2_INAPT = Path("data-pipeline/output/metaphor_spike_inapt_phase2_20260525T004154.jsonl")
DEFAULT_LAKOFF_APT = Path("data-pipeline/fixtures/lakoff_apt.jsonl")
DEFAULT_LAKOFF_INAPT = Path("data-pipeline/fixtures/lakoff_inapt.jsonl")
DEFAULT_DB = Path("data-pipeline/output/lexicon_v2.db")


# Production cascade config (same as M03 ratification, see
# docs/memory/m03_cascade_winner_config.md).
PRODUCTION_CASCADE_CONFIG = CascadeConfig(
    concreteness_threshold=1.0,
    ortony_scoring="jaccard_salience",
    alpha=1.0,
    composition="additive",
    # 2026-05-25 post-loop-1: switched gate_mode hard -> soft to recover
    # OOD coverage. See data-pipeline/output/loop1_eyeball_report.md for
    # the motivating finding (30% of random OOD topics gate-killed under
    # hard mode). gate_alpha=2.0 is the starting point — loop-2 tunes it.
    gate_mode="soft",
    gate_alpha=2.0,
)


# ---------------------------------------------------------------------------
# Cohort loaders — flatten the per-cohort file shapes to the common row
# dict shape that evaluate_loop_metric expects.
# ---------------------------------------------------------------------------


def _load_phase2_pairs(apt_path: Path, inapt_path: Path) -> list[dict]:
    """Flatten the Phase 2 spike JSONL into (topic, vehicle, cohort) rows.

    Apt JSONL: each line is one topic-response with a "metaphors" array.
    Inapt JSONL: each line is one topic-response with an "inapt_metaphors"
    array. We unpack to one row per vehicle, dropping any malformed
    entries with a warning.
    """
    rows: list[dict] = []
    for path, cohort, vehicles_key in (
        (apt_path, "apt", "metaphors"),
        (inapt_path, "inapt", "inapt_metaphors"),
    ):
        if not path.exists():
            raise FileNotFoundError(f"cohort file missing: {path}")
        with path.open(encoding="utf-8") as fh:
            for line_no, raw in enumerate(fh, start=1):
                line = raw.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError as e:
                    log.warning("skip malformed json %s:%d (%s)", path, line_no, e)
                    continue
                if not isinstance(obj, dict):
                    continue
                topic = obj.get("topic")
                if not isinstance(topic, str):
                    continue
                vehicles = obj.get(vehicles_key, [])
                if not isinstance(vehicles, list):
                    continue
                for entry in vehicles:
                    if not isinstance(entry, dict):
                        continue
                    vehicle = entry.get("vehicle")
                    if not isinstance(vehicle, str) or not vehicle:
                        continue
                    row = {"topic": topic, "vehicle": vehicle, "cohort": cohort}
                    # Preserve inapt_reason_type so per-reason analysis
                    # downstream (not used by the commit gate but
                    # consumed by report-rendering tools).
                    reason = entry.get("inapt_reason_type")
                    if isinstance(reason, str):
                        row["inapt_reason_type"] = reason
                    rows.append(row)
    return rows


def _load_lakoff_pairs(apt_path: Path, inapt_path: Path) -> list[dict]:
    """Lakoff fixtures are already one (topic, vehicle) per line.

    The shape is::

        apt:    {"topic": "anger", "vehicle": "fire", "lakoff_class": "..."}
        inapt:  {"topic": "anger", "vehicle": "umbrella", "label": "inapt"}
    """
    rows: list[dict] = []
    for path, cohort in ((apt_path, "apt"), (inapt_path, "inapt")):
        if not path.exists():
            raise FileNotFoundError(f"cohort file missing: {path}")
        with path.open(encoding="utf-8") as fh:
            for line_no, raw in enumerate(fh, start=1):
                line = raw.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError as e:
                    log.warning("skip malformed lakoff %s:%d (%s)", path, line_no, e)
                    continue
                if not isinstance(obj, dict):
                    continue
                topic = obj.get("topic")
                vehicle = obj.get("vehicle")
                if not isinstance(topic, str) or not isinstance(vehicle, str):
                    continue
                rows.append({"topic": topic, "vehicle": vehicle, "cohort": cohort})
    return rows


# ---------------------------------------------------------------------------
# Cascade scoring
# ---------------------------------------------------------------------------


def _score_pairs(
    conn: sqlite3.Connection,
    pairs: list[dict],
    config: CascadeConfig,
) -> list[dict]:
    """Score every (topic, vehicle) pair through the cascade.

    Returns rows in the evaluate_loop_metric shape — each pair gets
    a ``status`` (cascade_status) and ``score`` (final_score). Missing
    lemmas land as ``status=unresolved`` so the denominator still
    counts them.
    """
    out: list[dict] = []
    # Cache topic-side lookups per (topic, cohort) — same topic appears
    # many times within a cohort.
    sid_cache: dict[str, str | None] = {}

    def _resolve(word: str) -> str | None:
        if word not in sid_cache:
            sid_cache[word] = lookup_primary_synset(conn, word)
        return sid_cache[word]

    for p in pairs:
        topic = p["topic"]
        vehicle = p["vehicle"]
        sid_t = _resolve(topic)
        sid_v = _resolve(vehicle)
        row = {**p}
        if sid_t is None or sid_v is None:
            row["status"] = "unresolved"
            row["score"] = None
            out.append(row)
            continue
        try:
            cr = evaluate_cascade_pair(conn, sid_t, sid_v, config)
        except Exception as e:
            log.warning("cascade scoring failed (%s, %s): %s", topic, vehicle, e)
            row["status"] = "unresolved"
            row["score"] = None
            out.append(row)
            continue
        row["status"] = cr.status
        row["score"] = cr.final_score
        out.append(row)
    return out


# ---------------------------------------------------------------------------
# Top-level eval
# ---------------------------------------------------------------------------


def evaluate_loop(
    db_path: Path,
    phase2_apt: Path,
    phase2_inapt: Path,
    lakoff_apt: Path,
    lakoff_inapt: Path,
    config: CascadeConfig = PRODUCTION_CASCADE_CONFIG,
    bootstrap_n: int = 10,
    bootstrap_seed: int = 20260525,
) -> dict:
    """Score both cohorts and compute the loop's truth metrics."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    if not db_path.exists():
        raise FileNotFoundError(f"db missing: {db_path}")

    phase2_pairs = _load_phase2_pairs(phase2_apt, phase2_inapt)
    lakoff_pairs = _load_lakoff_pairs(lakoff_apt, lakoff_inapt)
    log.info(
        "loaded %d Phase 2 pairs, %d Lakoff pairs",
        len(phase2_pairs), len(lakoff_pairs),
    )

    with closing(sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)) as conn:
        phase2_scored = _score_pairs(conn, phase2_pairs, config)
        lakoff_scored = _score_pairs(conn, lakoff_pairs, config)

    # Phase 2: bootstrap (the loop's primary commit-gate signal).
    bootstrap = bootstrap_e2e_ratio(
        phase2_scored, n_resamples=bootstrap_n, seed=bootstrap_seed,
    )
    # Also emit a single full-cohort e2e for diagnostics.
    phase2_e2e = end_to_end_ratio(phase2_scored)

    # Lakoff: deterministic single-shot ratio (cohort too small for bootstrap).
    lakoff_e2e = end_to_end_ratio(lakoff_scored)

    return {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "config": {
            "concreteness_threshold": config.concreteness_threshold,
            "ortony_scoring": config.ortony_scoring,
            "alpha": config.alpha,
            "composition": config.composition,
            "d_cap": config.d_cap,
            "bootstrap_n": bootstrap_n,
            "bootstrap_seed": bootstrap_seed,
        },
        "phase2": {
            "median_ratio": bootstrap.median_ratio,
            "p10_ratio": bootstrap.p10_ratio,
            "p90_ratio": bootstrap.p90_ratio,
            "per_resample_ratio": bootstrap.per_resample_ratio,
            "full_cohort_ratio": phase2_e2e.ratio,
            "apt_promote_rate": phase2_e2e.apt_promote_rate,
            "inapt_promote_rate": phase2_e2e.inapt_promote_rate,
            "threshold": phase2_e2e.threshold,
            "n_apt": phase2_e2e.n_apt_total,
            "n_inapt": phase2_e2e.n_inapt_total,
        },
        "lakoff": {
            "ratio": lakoff_e2e.ratio,
            "apt_promote_rate": lakoff_e2e.apt_promote_rate,
            "inapt_promote_rate": lakoff_e2e.inapt_promote_rate,
            "threshold": lakoff_e2e.threshold,
            "n_apt": lakoff_e2e.n_apt_total,
            "n_inapt": lakoff_e2e.n_inapt_total,
        },
    }


# ---------------------------------------------------------------------------
# Modes + CLI
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("--mode", choices=("baseline", "compare"), required=True)
    ap.add_argument("--db", type=Path, default=DEFAULT_DB)
    ap.add_argument("--phase2-apt", type=Path, default=DEFAULT_PHASE2_APT)
    ap.add_argument("--phase2-inapt", type=Path, default=DEFAULT_PHASE2_INAPT)
    ap.add_argument("--lakoff-apt", type=Path, default=DEFAULT_LAKOFF_APT)
    ap.add_argument("--lakoff-inapt", type=Path, default=DEFAULT_LAKOFF_INAPT)
    ap.add_argument("--bootstrap-n", type=int, default=10)
    ap.add_argument("--bootstrap-seed", type=int, default=20260525)
    ap.add_argument(
        "--baseline", type=Path,
        help="Required for --mode compare. Path to baseline JSON to compare against.",
    )
    ap.add_argument(
        "--output", type=Path,
        help="Write the structured result here. Required for --mode baseline; "
             "optional for --mode compare.",
    )
    ap.add_argument(
        "--lakoff-degrade-tolerance", type=float, default=0.05,
        help="Relative tolerance for Lakoff ratio degradation (default: 5%%).",
    )
    args = ap.parse_args(argv)

    result = evaluate_loop(
        db_path=args.db,
        phase2_apt=args.phase2_apt,
        phase2_inapt=args.phase2_inapt,
        lakoff_apt=args.lakoff_apt,
        lakoff_inapt=args.lakoff_inapt,
        bootstrap_n=args.bootstrap_n,
        bootstrap_seed=args.bootstrap_seed,
    )

    if args.mode == "baseline":
        if not args.output:
            raise SystemExit("--mode baseline requires --output")
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8",
        )
        print(f"Baseline written to {args.output}")
        _print_summary("baseline", result)
        return 0

    # compare mode
    if not args.baseline:
        raise SystemExit("--mode compare requires --baseline")
    if not args.baseline.exists():
        raise SystemExit(f"baseline file missing: {args.baseline}")
    baseline = json.loads(args.baseline.read_text(encoding="utf-8"))

    verdict = compare_metrics(
        baseline=baseline, current=result,
        lakoff_degrade_tolerance=args.lakoff_degrade_tolerance,
    )
    out = {
        "baseline_path": str(args.baseline),
        "baseline": baseline,
        "current": result,
        "verdict": asdict(verdict),
    }
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8",
        )
        log.info("wrote compare result to %s", args.output)

    _print_summary("baseline", baseline)
    _print_summary("current", result)
    print("\n=== Commit Gate Verdict ===")
    for r in verdict.reasons:
        print(f"  {r}")
    print(f"\nRESULT: {'PASS' if verdict.passed else 'FAIL'}")
    return 0 if verdict.passed else 1


def _print_summary(label: str, r: dict) -> None:
    p2 = r["phase2"]
    lak = r["lakoff"]
    print(f"\n=== {label} ===")
    print(
        f"  Phase 2: median={p2['median_ratio']:.4f}  "
        f"p10={p2['p10_ratio']:.4f}  p90={p2['p90_ratio']:.4f}  "
        f"full={p2['full_cohort_ratio']:.4f}  "
        f"(n_apt={p2['n_apt']}, n_inapt={p2['n_inapt']})"
    )
    print(
        f"  Lakoff:  ratio={lak['ratio']:.4f}  "
        f"(n_apt={lak['n_apt']}, n_inapt={lak['n_inapt']})"
    )


if __name__ == "__main__":
    raise SystemExit(main())
