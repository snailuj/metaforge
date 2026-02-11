#!/usr/bin/env python3
"""
Compute IDF (Inverse Document Frequency) weights for property vocabulary.

IDF downweights properties that appear in many synsets (e.g., "sudden" in 100 synsets)
and upweights distinctive properties (e.g., "incandescent" in 3 synsets).

Formula: IDF = log(N / df)
- N = total enriched synsets
- df = document frequency (synsets containing this property)

Usage:
    python 06_compute_property_idf.py
"""
import math
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from utils import LEXICON_V2


def add_idf_column(conn: sqlite3.Connection) -> bool:
    """Add IDF column to property_vocabulary if it doesn't exist."""
    cursor = conn.execute("PRAGMA table_info(property_vocabulary)")
    columns = [row[1] for row in cursor.fetchall()]

    if "idf" not in columns:
        print("Adding 'idf' column to property_vocabulary...")
        conn.execute("ALTER TABLE property_vocabulary ADD COLUMN idf REAL")
        conn.commit()
        return True
    return False


def compute_idf(conn: sqlite3.Connection) -> None:
    """Compute and store IDF values for all properties."""
    # Get total number of enriched synsets (N)
    total_synsets = conn.execute(
        "SELECT COUNT(DISTINCT synset_id) FROM synset_properties"
    ).fetchone()[0]

    if total_synsets == 0:
        print("Warning: No synset_properties entries found")
        return

    print(f"Total enriched synsets (N): {total_synsets}")

    # Get document frequency for each property
    cursor = conn.execute("""
        SELECT pv.property_id, pv.text, COUNT(sp.synset_id) as doc_freq
        FROM property_vocabulary pv
        LEFT JOIN synset_properties sp ON sp.property_id = pv.property_id
        GROUP BY pv.property_id
    """)

    updates = []
    for property_id, text, doc_freq in cursor:
        if doc_freq > 0:
            # IDF = log(N / df)
            idf = math.log(total_synsets / doc_freq)
        else:
            # Property not linked to any synset - use max IDF
            idf = math.log(total_synsets)

        updates.append((idf, property_id))

    # Batch update
    conn.executemany(
        "UPDATE property_vocabulary SET idf = ? WHERE property_id = ?",
        updates
    )
    conn.commit()

    print(f"Computed IDF for {len(updates)} properties")

    # Show distribution
    stats = conn.execute("""
        SELECT
            MIN(idf) as min_idf,
            MAX(idf) as max_idf,
            AVG(idf) as avg_idf,
            COUNT(*) as count
        FROM property_vocabulary
        WHERE idf IS NOT NULL
    """).fetchone()

    print(f"  Min IDF: {stats[0]:.2f}")
    print(f"  Max IDF: {stats[1]:.2f}")
    print(f"  Avg IDF: {stats[2]:.2f}")

    # Show examples of high and low IDF properties
    print("\nHigh IDF (distinctive) properties:")
    for row in conn.execute("""
        SELECT pv.text, pv.idf, COUNT(sp.synset_id) as df
        FROM property_vocabulary pv
        LEFT JOIN synset_properties sp ON sp.property_id = pv.property_id
        WHERE pv.idf IS NOT NULL
        GROUP BY pv.property_id
        ORDER BY pv.idf DESC
        LIMIT 5
    """):
        print(f"  {row[0]}: IDF={row[1]:.2f} (df={row[2]})")

    print("\nLow IDF (common) properties:")
    for row in conn.execute("""
        SELECT pv.text, pv.idf, COUNT(sp.synset_id) as df
        FROM property_vocabulary pv
        LEFT JOIN synset_properties sp ON sp.property_id = pv.property_id
        WHERE pv.idf IS NOT NULL
        GROUP BY pv.property_id
        ORDER BY pv.idf ASC
        LIMIT 5
    """):
        print(f"  {row[0]}: IDF={row[1]:.2f} (df={row[2]})")


def main():
    if not LEXICON_V2.exists():
        print(f"Error: Database not found: {LEXICON_V2}")
        sys.exit(1)

    print(f"Computing IDF weights in {LEXICON_V2}...")
    conn = sqlite3.connect(LEXICON_V2)
    try:
        add_idf_column(conn)
        compute_idf(conn)
    finally:
        conn.close()
    print("\nIDF computation complete!")


if __name__ == "__main__":
    main()
