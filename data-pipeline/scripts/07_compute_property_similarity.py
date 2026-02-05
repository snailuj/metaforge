#!/usr/bin/env python3
"""
Compute pairwise property similarity matrix using FastText embeddings.

Stores pairs where cosine_similarity >= 0.5 in property_similarity table.
Uses vectorised NumPy operations for efficiency.

Usage:
    python 07_compute_property_similarity.py [--threshold 0.5]
"""
import argparse
import sqlite3
import struct
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
from utils import LEXICON_V2, EMBEDDING_DIM


def create_similarity_table(conn: sqlite3.Connection) -> None:
    """Create property_similarity table and indexes."""
    conn.executescript("""
        DROP TABLE IF EXISTS property_similarity;

        CREATE TABLE property_similarity (
            property_id_a INTEGER NOT NULL,
            property_id_b INTEGER NOT NULL,
            similarity REAL NOT NULL,
            PRIMARY KEY (property_id_a, property_id_b),
            FOREIGN KEY (property_id_a) REFERENCES property_vocabulary(property_id),
            FOREIGN KEY (property_id_b) REFERENCES property_vocabulary(property_id)
        );

        CREATE INDEX idx_property_similarity_a ON property_similarity(property_id_a);
        CREATE INDEX idx_property_similarity_b ON property_similarity(property_id_b);
        CREATE INDEX idx_property_similarity_score ON property_similarity(similarity);
    """)
    conn.commit()
    print("Created property_similarity table with indexes")


def load_embeddings(conn: sqlite3.Connection) -> tuple[list[int], np.ndarray]:
    """Load all property embeddings into a NumPy matrix."""
    cursor = conn.execute("""
        SELECT property_id, embedding
        FROM property_vocabulary
        WHERE embedding IS NOT NULL
    """)

    property_ids = []
    embeddings = []

    for prop_id, blob in cursor:
        vec = struct.unpack(f'{EMBEDDING_DIM}f', blob)
        property_ids.append(prop_id)
        embeddings.append(vec)

    print(f"Loaded {len(property_ids)} property embeddings")
    return property_ids, np.array(embeddings, dtype=np.float32)


def compute_similarity_matrix(embeddings: np.ndarray) -> np.ndarray:
    """Compute cosine similarity matrix using vectorised operations."""
    # Normalise vectors
    norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
    norms[norms == 0] = 1  # Avoid division by zero
    normalised = embeddings / norms

    # Compute similarity matrix (dot product of normalised vectors)
    similarity = np.dot(normalised, normalised.T)

    return similarity


def store_similarities(conn: sqlite3.Connection, property_ids: list[int],
                       similarity: np.ndarray, threshold: float) -> int:
    """Store similarity pairs above threshold."""
    n = len(property_ids)
    pairs = []

    # Only store upper triangle (i < j) to avoid duplicates
    for i in range(n):
        for j in range(i + 1, n):
            sim = float(similarity[i, j])
            if sim >= threshold:
                pairs.append((property_ids[i], property_ids[j], sim))
                # Also store reverse for easier querying
                pairs.append((property_ids[j], property_ids[i], sim))

    # Batch insert
    conn.executemany(
        "INSERT INTO property_similarity (property_id_a, property_id_b, similarity) VALUES (?, ?, ?)",
        pairs
    )
    conn.commit()

    return len(pairs) // 2  # Return unique pairs count


def main():
    parser = argparse.ArgumentParser(description="Compute property similarity matrix")
    parser.add_argument("--threshold", type=float, default=0.5,
                        help="Minimum similarity to store (default: 0.5)")
    args = parser.parse_args()

    if not LEXICON_V2.exists():
        print(f"Error: Database not found: {LEXICON_V2}")
        sys.exit(1)

    print(f"Computing property similarity matrix (threshold={args.threshold})...")
    conn = sqlite3.connect(LEXICON_V2)

    # Create table
    create_similarity_table(conn)

    # Load embeddings
    property_ids, embeddings = load_embeddings(conn)

    # Compute similarity
    print("Computing pairwise cosine similarities...")
    similarity = compute_similarity_matrix(embeddings)

    # Store results
    print(f"Storing pairs with similarity >= {args.threshold}...")
    pair_count = store_similarities(conn, property_ids, similarity, args.threshold)

    conn.close()

    print(f"\nSimilarity computation complete!")
    print(f"  Stored {pair_count} unique similar property pairs")
    print(f"  Table: property_similarity")


if __name__ == "__main__":
    main()
