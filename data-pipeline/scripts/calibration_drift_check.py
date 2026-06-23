"""Calibration-drift detector: re-grade a sample of an earlier round, compute
label-flip rate. Per spec: ≥0.30 flips out of n (with n≥5) flags drift.

CLI:
  --originals <judgements.jsonl path>   first set of verdicts on the targets
  --regrades  <judgements.jsonl path>   latest re-grade verdicts
  --threshold 0.30                       flip-rate threshold for DRIFT
"""
from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path


def compute_flip_rate(originals: list[dict], regrades: list[dict]) -> dict:
    """Returns {n, flips, rate}. n = re-graded chains that exist in originals."""
    by_sig = {o["chain_signature"]: o["label"] for o in originals}
    flips = 0
    counted = 0
    for r in regrades:
        sig = r["chain_signature"]
        if sig in by_sig:
            counted += 1
            if r["label"] != by_sig[sig]:
                flips += 1
    return {"n": counted, "flips": flips,
            "rate": flips / counted if counted else 0.0}


def drift_verdict(stat: dict, threshold: float = 0.30, min_n: int = 5) -> dict:
    """Returns {status: OK|DRIFT|INSUFFICIENT, ...}."""
    if stat["n"] < min_n:
        return {"status": "INSUFFICIENT", "n": stat["n"], "min_n": min_n}
    if stat["rate"] >= threshold:
        return {"status": "DRIFT", "rate": stat["rate"], "threshold": threshold}
    return {"status": "OK", "rate": stat["rate"], "threshold": threshold}


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--originals", required=True, help="Original verdicts (jsonl)")
    p.add_argument("--regrades", required=True, help="Re-grade verdicts (jsonl)")
    p.add_argument("--threshold", type=float, default=0.30)
    args = p.parse_args()

    def load(p_str: str) -> list[dict]:
        path = Path(p_str)
        if not path.exists():
            print(f"WARNING: {path} does not exist", file=sys.stderr)
            return []
        return [json.loads(l) for l in path.read_text().splitlines() if l.strip()]

    originals = load(args.originals)
    regrades = load(args.regrades)
    stat = compute_flip_rate(originals, regrades)
    v = drift_verdict(stat, threshold=args.threshold)
    print(f"Flip-rate: {stat['flips']}/{stat['n']} = {stat['rate']:.1%}")
    print(f"Verdict: {v['status']}")
    return 0 if v["status"] != "DRIFT" else 1


if __name__ == "__main__":
    raise SystemExit(main())
