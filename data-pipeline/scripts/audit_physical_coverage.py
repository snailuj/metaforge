"""Audit enrichment data for physical property coverage.

Reads enrichment JSON (or live checkpoint) and flags synsets with
insufficient physical properties based on POS-dependent thresholds.

Usage:
    python audit_physical_coverage.py --input checkpoint_enrich.json --output flagged.json
    python audit_physical_coverage.py --input enrichment_8000.json --exclude gap_fill.json -o flagged.json
"""

import argparse
import json
import sys
import time
from pathlib import Path


POS_THRESHOLDS = {
    "n": 4,
    "v": 2,
    "a": 2,
    "s": 2,  # satellite adjective — same threshold as adjective
}

DEFAULT_THRESHOLD = 2  # fallback for unknown POS (adverbs, etc.)


def audit_physical_coverage(
    data: dict,
    exclude_ids: set[str] | None = None,
) -> dict:
    """Audit enrichment data for physical property coverage.

    Args:
        data: Enrichment/checkpoint JSON ({"synsets": [...]}).
              Also accepts legacy checkpoint format ({"results": [...]}).
        exclude_ids: Synset IDs to skip (already gap-filled).

    Returns:
        Dict with flagged_ids, total_synsets, flagged_count, pos_breakdown.
    """
    # Unified format uses 'synsets'; legacy checkpoint fallback to 'results'
    synsets = data.get("synsets") or data.get("results") or []
    exclude = exclude_ids or set()

    flagged_ids = []
    pos_breakdown = {}

    for synset in synsets:
        sid = synset["id"]
        if sid in exclude:
            continue

        pos = synset.get("pos", "n")
        threshold = POS_THRESHOLDS.get(pos, DEFAULT_THRESHOLD)

        physical_count = sum(
            1 for p in synset.get("properties", [])
            if isinstance(p, dict) and p.get("type") == "physical"
        )

        # Track POS stats
        if pos not in pos_breakdown:
            pos_breakdown[pos] = {"total": 0, "flagged": 0, "avg_physical": 0, "physical_sum": 0}
        pos_breakdown[pos]["total"] += 1
        pos_breakdown[pos]["physical_sum"] += physical_count

        if physical_count < threshold:
            flagged_ids.append(sid)
            pos_breakdown[pos]["flagged"] += 1

    # Compute averages
    for stats in pos_breakdown.values():
        if stats["total"] > 0:
            stats["avg_physical"] = round(stats["physical_sum"] / stats["total"], 2)
        del stats["physical_sum"]

    total = len([s for s in synsets if s["id"] not in exclude])

    return {
        "flagged_ids": flagged_ids,
        "total_synsets": total,
        "flagged_count": len(flagged_ids),
        "flagged_pct": round(len(flagged_ids) / total * 100, 1) if total else 0,
        "pos_breakdown": pos_breakdown,
    }


def load_json_with_retry(path: Path, retries: int = 1) -> dict:
    """Load JSON, retrying once on decode error (concurrent write tolerance)."""
    for attempt in range(retries + 1):
        try:
            with open(path) as f:
                return json.load(f)
        except json.JSONDecodeError:
            if attempt < retries:
                print(f"  JSON decode error, retrying in 1s...", file=sys.stderr)
                time.sleep(1)
            else:
                raise


def main():
    parser = argparse.ArgumentParser(
        description="Audit enrichment data for physical property coverage"
    )
    parser.add_argument(
        "--input", "-i", type=str, required=True,
        help="Enrichment JSON or checkpoint file to audit",
    )
    parser.add_argument(
        "--output", "-o", type=str, required=True,
        help="Output JSON with flagged synset IDs",
    )
    parser.add_argument(
        "--exclude", "-x", type=str, default=None,
        help="JSON file with synset IDs to exclude (already gap-filled)",
    )
    args = parser.parse_args()

    data = load_json_with_retry(Path(args.input))

    exclude_ids = set()
    if args.exclude:
        exclude_data = json.loads(Path(args.exclude).read_text())
        # Accept either a plain list or an enrichment-format dict
        if isinstance(exclude_data, list):
            exclude_ids = set(str(i) for i in exclude_data)
        elif isinstance(exclude_data, dict) and "synsets" in exclude_data:
            exclude_ids = {s["id"] for s in exclude_data["synsets"]}

    result = audit_physical_coverage(data, exclude_ids=exclude_ids)

    # Write output
    Path(args.output).write_text(json.dumps(result, indent=2))

    # Print summary to stdout
    print(f"\n=== Physical Coverage Audit ===")
    print(f"Total synsets: {result['total_synsets']}")
    print(f"Flagged: {result['flagged_count']} ({result['flagged_pct']}%)")
    print(f"\nBreakdown by POS:")
    for pos, stats in sorted(result["pos_breakdown"].items()):
        print(f"  {pos}: {stats['flagged']}/{stats['total']} flagged "
              f"(avg {stats['avg_physical']} physical)")


if __name__ == "__main__":
    main()
