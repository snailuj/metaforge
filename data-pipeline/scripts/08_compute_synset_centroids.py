#!/usr/bin/env python3
"""
Compute synset centroids from property embeddings.

For each enriched synset, averages its property embeddings into a single
300d centroid vector. Stored in synset_centroids table for fast Go-side
cosine distance computation (eliminates N+1 query problem).

Usage:
    python 08_compute_synset_centroids.py
"""
import sqlite3
import struct
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
from utils import LEXICON_V2, EMBEDDING_DIM


def create_centroids_table(conn: sqlite3.Connection) -> None:
    """Create synset_centroids table."""
    conn.executescript("""
        DROP TABLE IF EXISTS synset_centroids;

        CREATE TABLE synset_centroids (
            synset_id TEXT PRIMARY KEY,
            centroid BLOB NOT NULL,
            property_count INTEGER NOT NULL
        );
    """)
    conn.commit()
    print("Created synset_centroids table")


def compute_and_store_centroids(conn: sqlite3.Connection) -> int:
    """Compute centroid for each enriched synset and store in DB.

    Returns the number of centroids computed.
    """
    # Get all enriched synsets and their property embeddings
    cursor = conn.execute("""
        SELECT sp.synset_id, pv.embedding
        FROM synset_properties sp
        JOIN property_vocabulary pv ON pv.property_id = sp.property_id
        WHERE pv.embedding IS NOT NULL
        ORDER BY sp.synset_id
    """)

    current_synset = None
    embeddings = []
    rows_to_insert = []

    for synset_id, blob in cursor:
        if synset_id != current_synset:
            # Store previous synset's centroid
            if current_synset is not None and len(embeddings) > 0:
                centroid = _compute_centroid(embeddings)
                centroid_blob = struct.pack(f'{EMBEDDING_DIM}f', *centroid)
                rows_to_insert.append((current_synset, centroid_blob, len(embeddings)))

            current_synset = synset_id
            embeddings = []

        vec = np.array(struct.unpack(f'{EMBEDDING_DIM}f', blob), dtype=np.float32)
        embeddings.append(vec)

    # Don't forget the last synset
    if current_synset is not None and len(embeddings) > 0:
        centroid = _compute_centroid(embeddings)
        centroid_blob = struct.pack(f'{EMBEDDING_DIM}f', *centroid)
        rows_to_insert.append((current_synset, centroid_blob, len(embeddings)))

    # Batch insert
    conn.executemany(
        "INSERT INTO synset_centroids (synset_id, centroid, property_count) VALUES (?, ?, ?)",
        rows_to_insert
    )
    conn.commit()

    return len(rows_to_insert)


def _compute_centroid(embeddings: list[np.ndarray]) -> np.ndarray:
    """Average a list of embedding vectors into a single centroid."""
    stacked = np.stack(embeddings)
    return stacked.mean(axis=0)


def main():
    if not LEXICON_V2.exists():
        print(f"Error: Database not found: {LEXICON_V2}")
        sys.exit(1)

    print(f"Computing synset centroids in {LEXICON_V2}...")
    conn = sqlite3.connect(LEXICON_V2)

    create_centroids_table(conn)
    count = compute_and_store_centroids(conn)

    # Show stats
    if count > 0:
        row = conn.execute("""
            SELECT MIN(property_count), MAX(property_count), AVG(property_count)
            FROM synset_centroids
        """).fetchone()
        print(f"\nComputed {count} synset centroids")
        print(f"  Properties per synset: min={row[0]}, max={row[1]}, avg={row[2]:.1f}")
    else:
        print("\nNo centroids computed (no enriched synsets with embeddings)")

    conn.close()
    print("Centroid computation complete!")


if __name__ == "__main__":
    main()
