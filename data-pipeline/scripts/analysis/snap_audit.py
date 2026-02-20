"""Snap quality audit report.

Measures:
  1. Snap rate per stage (exact, morphological, embedding, dropped)
  2. Property coverage per synset (how many canonical properties after snapping)
  3. Snap score distribution for embedding matches

Usage:
    python snap_audit.py --db PATH
"""
import argparse
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from utils import LEXICON_V2


def compute_snap_rates(conn: sqlite3.Connection) -> dict[str, int]:
    """Count snapped properties per method."""
    rates: dict[str, int] = {}
    for method, count in conn.execute(
        "SELECT snap_method, COUNT(*) FROM synset_properties_curated GROUP BY snap_method"
    ):
        rates[method] = count
    return rates


def compute_coverage(conn: sqlite3.Connection) -> dict[str, int]:
    """Compute per-synset property coverage after snapping."""
    synset_counts: list[int] = []
    for (count,) in conn.execute(
        "SELECT COUNT(*) FROM synset_properties_curated GROUP BY synset_id"
    ):
        synset_counts.append(count)

    return {
        "total_synsets": len(synset_counts),
        "with_3_plus": sum(1 for c in synset_counts if c >= 3),
        "with_5_plus": sum(1 for c in synset_counts if c >= 5),
        "with_8_plus": sum(1 for c in synset_counts if c >= 8),
        "avg_properties": round(sum(synset_counts) / len(synset_counts), 1) if synset_counts else 0,
    }


def compute_embedding_score_distribution(conn: sqlite3.Connection) -> dict[str, int]:
    """Distribution of cosine scores for embedding-snapped properties."""
    brackets: dict[str, int] = {
        "0.70-0.75": 0,
        "0.75-0.80": 0,
        "0.80-0.85": 0,
        "0.85-0.90": 0,
        "0.90-0.95": 0,
        "0.95-1.00": 0,
    }
    for (score,) in conn.execute(
        "SELECT snap_score FROM synset_properties_curated WHERE snap_method = 'embedding'"
    ):
        if score is None:
            continue
        if score < 0.75:
            brackets["0.70-0.75"] += 1
        elif score < 0.80:
            brackets["0.75-0.80"] += 1
        elif score < 0.85:
            brackets["0.80-0.85"] += 1
        elif score < 0.90:
            brackets["0.85-0.90"] += 1
        elif score < 0.95:
            brackets["0.90-0.95"] += 1
        else:
            brackets["0.95-1.00"] += 1
    return brackets


def print_report(conn: sqlite3.Connection):
    """Print full audit report."""
    print("=== Snap Audit Report ===\n")

    rates = compute_snap_rates(conn)
    total = sum(rates.values())
    print("Snap rates:")
    for method in ("exact", "morphological", "embedding"):
        count = rates.get(method, 0)
        pct = 100 * count / total if total else 0
        print(f"  {method}: {count:,} ({pct:.1f}%)")
    print()

    coverage = compute_coverage(conn)
    print(f"Coverage ({coverage['total_synsets']:,} synsets):")
    print(f"  >= 3 properties: {coverage['with_3_plus']:,}")
    print(f"  >= 5 properties: {coverage['with_5_plus']:,}")
    print(f"  >= 8 properties: {coverage['with_8_plus']:,}")
    print(f"  Average: {coverage['avg_properties']} properties/synset")
    print()

    dist = compute_embedding_score_distribution(conn)
    print("Embedding score distribution:")
    for bracket, count in dist.items():
        print(f"  {bracket}: {count:,}")


def main():
    parser = argparse.ArgumentParser(description="Snap quality audit report")
    parser.add_argument("--db", default=str(LEXICON_V2), help="Path to lexicon DB")
    args = parser.parse_args()

    conn = sqlite3.connect(f"file:{args.db}?mode=ro", uri=True)
    try:
        print_report(conn)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
