"""Bad_path-rate convergence diagnostic with Wilson 95% CI.

Per spec: point comparisons at n=20 are statistically meaningless; use CI overlap.
Status: DOWN (proceed) / FLAT (intervention needed) / CEILING (8-round hard stop)
      / INSUFFICIENT (need more rounds) / MIXED (some movement but ambiguous).
"""
from __future__ import annotations
import argparse
import json
import math
from pathlib import Path

def wilson_ci(k: int, n: int, alpha: float = 0.05) -> tuple[float, float]:
    """95% Wilson CI for a binomial proportion. Returns (lower, upper)."""
    if n == 0:
        return (0.0, 0.0)
    z = 1.959963984540054  # scipy.stats.norm.ppf(1 - 0.025); avoids scipy dep
    z2 = z * z
    p = k / n
    centre = (p + z2 / (2 * n)) / (1 + z2 / n)
    margin = (z * math.sqrt((p * (1 - p) + z2 / (4 * n)) / n)) / (1 + z2 / n)
    lo = max(0.0, centre - margin)
    hi = min(1.0, centre + margin)
    return (lo, hi)

def ci_overlap(ci1: tuple[float, float], ci2: tuple[float, float]) -> bool:
    return not (ci1[1] < ci2[0] or ci2[1] < ci1[0])

def convergence_verdict(rounds: list[dict], ceiling: int = 8) -> dict:
    """rounds: [{round, bad_path, total}, ...] sorted by round ascending."""
    if len(rounds) >= ceiling:
        return {"status": "CEILING", "rounds": len(rounds),
                "message": f"hit {ceiling}-round ceiling; escalate intervention"}
    if len(rounds) < 2:
        return {"status": "INSUFFICIENT", "rounds": len(rounds)}

    # Look at last 2: do their CIs separate downward?
    last = rounds[-1]; prev = rounds[-2]
    ci_last = wilson_ci(last["bad_path"], last["total"])
    ci_prev = wilson_ci(prev["bad_path"], prev["total"])
    if not ci_overlap(ci_last, ci_prev) and ci_last[1] < ci_prev[0]:
        return {"status": "DOWN", "rounds": len(rounds),
                "ci_last": ci_last, "ci_prev": ci_prev}

    # Look across last 3 for flatness
    if len(rounds) >= 3:
        last3 = rounds[-3:]
        cis = [wilson_ci(r["bad_path"], r["total"]) for r in last3]
        all_overlap = all(ci_overlap(cis[i], cis[j])
                          for i in range(3) for j in range(3) if i != j)
        if all_overlap:
            return {"status": "FLAT", "rounds": len(rounds), "cis": cis}

    return {"status": "MIXED", "rounds": len(rounds)}

def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--judgements", default="data-pipeline/grading/judgements_provisional.jsonl")
    args = p.parse_args()
    path = Path(args.judgements)
    lines = path.read_text().splitlines() if path.exists() else []
    judgements = [json.loads(l) for l in lines if l.strip()]

    # Aggregate: latest-per-signature, then count bad_path per round
    latest_by_sig: dict[str, dict] = {}
    for j in judgements:
        sig = j["chain_signature"]
        if sig not in latest_by_sig or j["ts"] > latest_by_sig[sig]["ts"]:
            latest_by_sig[sig] = j

    per_round: dict[int, dict] = {}
    for j in latest_by_sig.values():
        r = j["round"]
        per_round.setdefault(r, {"round": r, "bad_path": 0, "total": 0})
        per_round[r]["total"] += 1
        if j["label"] == "bad_path":
            per_round[r]["bad_path"] += 1

    rounds = sorted(per_round.values(), key=lambda x: x["round"])
    for r in rounds:
        lo, hi = wilson_ci(r["bad_path"], r["total"])
        rate = r["bad_path"] / max(1, r["total"])
        print(f"Round {r['round']}: bad_path {r['bad_path']}/{r['total']} = "
              f"{rate:.0%}  CI95: ({lo:.2f}, {hi:.2f})")
    v = convergence_verdict(rounds)
    print(f"\nVerdict: {v['status']}")
    if "message" in v:
        print(f"  {v['message']}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
