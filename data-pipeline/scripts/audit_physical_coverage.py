"""Audit physical property coverage per synset.

Reads v2 enrichment data from the DB (synset_properties.property_type)
and flags synsets below POS-dependent physical property thresholds.

Usage:
    python audit_physical_coverage.py --db PATH [-o report.json]
"""
import argparse
import json
import logging
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from utils import LEXICON_V2

log = logging.getLogger(__name__)

# Minimum physical properties per POS before flagging
POS_THRESHOLDS = {
    "n": 4,  # nouns are primary metaphor vehicles
    "v": 2,  # verbs have physical dimensions but fewer
    "a": 2,  # adjectives — sensory ones are valuable
    "r": 0,  # adverbs — no physical requirement
}


def audit_physical_coverage(conn: sqlite3.Connection) -> dict:
    """Audit physical property coverage per enriched synset.

    Returns dict with:
        total_audited: int
        total_flagged: int
        by_pos: {pos: {total, flagged, threshold}}
        flagged: [{synset_id, pos, physical_count, total_count, properties}]
    """
    rows = conn.execute("""
        SELECT s.synset_id, s.pos,
               COUNT(sp.property_id) as total_props,
               COUNT(CASE WHEN sp.property_type = 'physical' THEN 1 END) as physical_count
        FROM synsets s
        JOIN synset_properties sp ON sp.synset_id = s.synset_id
        GROUP BY s.synset_id, s.pos
    """).fetchall()

    flagged = []
    by_pos: dict[str, dict] = {}

    for synset_id, pos, total_props, physical_count in rows:
        threshold = POS_THRESHOLDS.get(pos, 0)

        if pos not in by_pos:
            by_pos[pos] = {"total": 0, "flagged": 0, "threshold": threshold}
        by_pos[pos]["total"] += 1

        if physical_count < threshold:
            prop_rows = conn.execute("""
                SELECT pv.text, sp.property_type
                FROM synset_properties sp
                JOIN property_vocabulary pv ON pv.property_id = sp.property_id
                WHERE sp.synset_id = ?
            """, (synset_id,)).fetchall()

            existing_props = [{"text": r[0], "type": r[1]} for r in prop_rows]

            flagged.append({
                "synset_id": synset_id,
                "pos": pos,
                "physical_count": physical_count,
                "total_count": total_props,
                "threshold": threshold,
                "properties": existing_props,
            })
            by_pos[pos]["flagged"] += 1

    return {
        "total_audited": len(rows),
        "total_flagged": len(flagged),
        "by_pos": by_pos,
        "flagged": flagged,
    }


def main():
    parser = argparse.ArgumentParser(
        description="Audit physical property coverage per synset.",
    )
    parser.add_argument("--db", default=str(LEXICON_V2), help="lexicon database path")
    parser.add_argument("-o", "--output", help="output JSON report path")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s: %(message)s",
    )

    conn = sqlite3.connect(args.db)
    try:
        result = audit_physical_coverage(conn)
    finally:
        conn.close()

    print(f"\n=== Physical Coverage Audit ===")
    print(f"  Audited: {result['total_audited']} synsets")
    if result['total_audited']:
        print(f"  Flagged: {result['total_flagged']} ({result['total_flagged']/result['total_audited']*100:.1f}%)")
    else:
        print(f"  Flagged: 0")
    for pos, stats in sorted(result["by_pos"].items()):
        pct = stats["flagged"] / stats["total"] * 100 if stats["total"] else 0
        print(f"  POS={pos}: {stats['flagged']}/{stats['total']} flagged ({pct:.0f}%), threshold={stats['threshold']}")

    if args.output:
        with open(args.output, "w") as f:
            json.dump(result, f, indent=2)
        print(f"\n  Report: {args.output}")


if __name__ == "__main__":
    main()
