"""Consolidated downstream enrichment pipeline.

Takes enrichment JSON (from enrich_properties.py) and populates the lexicon DB:
  1. Curate properties — normalise, add FastText embeddings, flag OOV
  2. Populate synset_properties junction table
  3. Compute property IDF weights
  4. Compute pairwise property similarity matrix
  5. Compute synset centroids

Each function takes a sqlite3.Connection and is independently importable.
The run_pipeline() orchestrator calls them in sequence.

Usage as CLI:
    python enrich_pipeline.py --db PATH --enrichment FILE --fasttext PATH
"""
import argparse
import json
import math
import re
import sqlite3
import struct
import sys
from pathlib import Path
from typing import Optional

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
from utils import EMBEDDING_DIM, FASTTEXT_VEC, normalise

MAX_PROPERTIES_PER_SYNSET = 15
SIMILARITY_CHUNK_SIZE = 2048


# =============================================================================
# 1. Curate properties (from curate_properties.py)
# =============================================================================

def load_fasttext_vectors(vec_path: str) -> dict[str, tuple[float, ...]]:
    """Load FastText vectors from .vec file into memory."""
    vectors = {}
    print(f"  Loading {vec_path}...")

    with open(vec_path, "r", encoding="utf-8") as f:
        header = f.readline().strip().split()
        num_words, dim = int(header[0]), int(header[1])
        print(f"  Header: {num_words} words, {dim}d")

        for i, line in enumerate(f):
            parts = line.rstrip().split(" ")
            word = parts[0]
            try:
                vec = tuple(float(x) for x in parts[1:])
                if len(vec) == dim:
                    vectors[word] = vec
            except ValueError:
                continue

            if (i + 1) % 200000 == 0:
                print(f"    Loaded {i + 1} words...")

    print(f"  Loaded {len(vectors)} vectors")
    return vectors


def _get_embedding(
    word: str, vectors: dict[str, tuple[float, ...]]
) -> Optional[bytes]:
    """Get embedding bytes for a word, or None if OOV."""
    if word not in vectors:
        return None
    return struct.pack(f"{EMBEDDING_DIM}f", *vectors[word])


def _get_compound_embedding(
    text: str, vectors: dict[str, tuple[float, ...]]
) -> Optional[bytes]:
    """Get averaged embedding for compound/hyphenated words."""
    parts = re.split(r"[-\s/]", text)
    parts = [p.strip() for p in parts if p.strip()]

    if not parts:
        return None

    embeddings = []
    for part in parts:
        if part in vectors:
            embeddings.append(vectors[part])

    if not embeddings:
        return None

    avg = tuple(
        sum(e[i] for e in embeddings) / len(embeddings) for i in range(EMBEDDING_DIM)
    )
    return struct.pack(f"{EMBEDDING_DIM}f", *avg)


def curate_properties(
    conn: sqlite3.Connection,
    enrichment_data: dict,
    vectors: dict[str, tuple[float, ...]],
) -> int:
    """Normalise properties, add FastText embeddings, flag OOV.

    Returns the number of properties inserted.
    """
    all_props = set()
    for synset in enrichment_data.get("synsets", []):
        for prop in synset.get("properties", [])[:MAX_PROPERTIES_PER_SYNSET]:
            all_props.add(normalise(prop))

    count = 0
    for prop in sorted(all_props):
        emb = _get_embedding(prop, vectors)
        if emb is None and re.search(r"[-\s/]", prop):
            emb = _get_compound_embedding(prop, vectors)

        is_oov = 1 if emb is None else 0

        conn.execute(
            """INSERT OR REPLACE INTO property_vocabulary (text, embedding, is_oov, source)
               VALUES (?, ?, ?, 'pilot')""",
            (prop, emb, is_oov),
        )
        count += 1

    conn.commit()
    print(f"  Curated {count} properties")
    return count


# =============================================================================
# 2. Populate synset_properties (from populate_synset_properties.py)
# =============================================================================

def populate_synset_properties(
    conn: sqlite3.Connection,
    enrichment_data: dict,
    model_used: str,
) -> int:
    """Create enrichment entries and synset-property links.

    Returns the number of synset-property links created.
    """
    prop_ids = {}
    for row in conn.execute("SELECT property_id, text FROM property_vocabulary"):
        prop_ids[row[1]] = row[0]

    links = 0
    for synset in enrichment_data.get("synsets", []):
        synset_id = synset["id"]

        conn.execute(
            "INSERT OR IGNORE INTO enrichment (synset_id, model_used) VALUES (?, ?)",
            (synset_id, model_used),
        )

        for prop in synset.get("properties", [])[:MAX_PROPERTIES_PER_SYNSET]:
            prop_norm = normalise(prop)
            if prop_norm in prop_ids:
                conn.execute(
                    "INSERT OR IGNORE INTO synset_properties (synset_id, property_id) VALUES (?, ?)",
                    (synset_id, prop_ids[prop_norm]),
                )
                links += 1

    conn.commit()
    print(f"  Created {links} synset-property links")
    return links


# =============================================================================
# 3. Compute property IDF (from 06_compute_property_idf.py)
# =============================================================================

def _ensure_idf_column(conn: sqlite3.Connection) -> None:
    """Add IDF column to property_vocabulary if it doesn't exist."""
    cursor = conn.execute("PRAGMA table_info(property_vocabulary)")
    columns = [row[1] for row in cursor.fetchall()]
    if "idf" not in columns:
        conn.execute("ALTER TABLE property_vocabulary ADD COLUMN idf REAL")
        conn.commit()


def compute_idf(conn: sqlite3.Connection) -> None:
    """Compute IDF = log(N / df) for all properties."""
    _ensure_idf_column(conn)

    total_synsets = conn.execute(
        "SELECT COUNT(DISTINCT synset_id) FROM synset_properties"
    ).fetchone()[0]

    if total_synsets == 0:
        print("  Warning: no synset_properties entries — skipping IDF")
        return

    cursor = conn.execute("""
        SELECT pv.property_id, COUNT(sp.synset_id) as doc_freq
        FROM property_vocabulary pv
        LEFT JOIN synset_properties sp ON sp.property_id = pv.property_id
        GROUP BY pv.property_id
    """)

    updates = []
    for property_id, doc_freq in cursor:
        idf = math.log(total_synsets / doc_freq) if doc_freq > 0 else math.log(total_synsets)
        updates.append((idf, property_id))

    conn.executemany(
        "UPDATE property_vocabulary SET idf = ? WHERE property_id = ?", updates
    )
    conn.commit()
    print(f"  Computed IDF for {len(updates)} properties (N={total_synsets})")


# =============================================================================
# 4. Compute property similarity (from 07_compute_property_similarity.py)
# =============================================================================

def compute_property_similarity(
    conn: sqlite3.Connection,
    threshold: float = 0.5,
    chunk_size: Optional[int] = None,
) -> int:
    """Compute pairwise cosine similarity and store pairs above threshold.

    Uses block-wise processing to avoid allocating a full n×n matrix.
    Peak memory: O(n × 300) for embeddings + O(chunk_size²) per sub-matrix.

    Returns the number of unique pairs stored.
    """
    if chunk_size is None:
        chunk_size = SIMILARITY_CHUNK_SIZE

    # Drop and recreate table (without indexes — bulk insert first)
    conn.executescript("""
        DROP TABLE IF EXISTS property_similarity;
        CREATE TABLE property_similarity (
            property_id_a INTEGER NOT NULL,
            property_id_b INTEGER NOT NULL,
            similarity REAL NOT NULL,
            PRIMARY KEY (property_id_a, property_id_b)
        );
    """)

    cursor = conn.execute(
        "SELECT property_id, embedding FROM property_vocabulary WHERE embedding IS NOT NULL"
    )
    property_ids = []
    embeddings = []
    for prop_id, blob in cursor:
        vec = struct.unpack(f"{EMBEDDING_DIM}f", blob)
        property_ids.append(prop_id)
        embeddings.append(vec)

    n = len(property_ids)
    if n < 2:
        print("  <2 properties with embeddings — skipping similarity")
        return 0

    matrix = np.array(embeddings, dtype=np.float32)
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    norms[norms == 0] = 1
    normalised = matrix / norms

    unique_count = 0
    for ci in range(0, n, chunk_size):
        ci_end = min(ci + chunk_size, n)
        for cj in range(ci, n, chunk_size):
            cj_end = min(cj + chunk_size, n)

            sub_sim = np.dot(normalised[ci:ci_end], normalised[cj:cj_end].T)
            pairs = []

            if ci == cj:
                # Diagonal chunk — upper triangle only (i < j)
                for li in range(ci_end - ci):
                    for lj in range(li + 1, cj_end - cj):
                        s = float(sub_sim[li, lj])
                        if s >= threshold:
                            pairs.append((property_ids[ci + li], property_ids[cj + lj], s))
                            pairs.append((property_ids[cj + lj], property_ids[ci + li], s))
            else:
                # Off-diagonal chunk — all pairs (ci < cj guaranteed)
                for li in range(ci_end - ci):
                    for lj in range(cj_end - cj):
                        s = float(sub_sim[li, lj])
                        if s >= threshold:
                            pairs.append((property_ids[ci + li], property_ids[cj + lj], s))
                            pairs.append((property_ids[cj + lj], property_ids[ci + li], s))

            if pairs:
                conn.executemany(
                    "INSERT INTO property_similarity (property_id_a, property_id_b, similarity) VALUES (?, ?, ?)",
                    pairs,
                )
                unique_count += len(pairs) // 2

    # Create indexes after bulk insert
    conn.executescript("""
        CREATE INDEX IF NOT EXISTS idx_property_similarity_a ON property_similarity(property_id_a);
        CREATE INDEX IF NOT EXISTS idx_property_similarity_b ON property_similarity(property_id_b);
        CREATE INDEX IF NOT EXISTS idx_property_similarity_score ON property_similarity(similarity);
    """)
    conn.commit()
    print(f"  Stored {unique_count} unique similar property pairs (threshold={threshold})")
    return unique_count


# =============================================================================
# 5. Compute synset centroids (from 08_compute_synset_centroids.py)
# =============================================================================

def compute_synset_centroids(conn: sqlite3.Connection) -> int:
    """Compute per-synset centroid (mean of property embeddings).

    Returns the number of centroids computed.
    """
    conn.executescript("""
        DROP TABLE IF EXISTS synset_centroids;
        CREATE TABLE synset_centroids (
            synset_id TEXT PRIMARY KEY,
            centroid BLOB NOT NULL,
            property_count INTEGER NOT NULL
        );
    """)

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
            if current_synset is not None and embeddings:
                centroid = np.stack(embeddings).mean(axis=0)
                centroid_blob = struct.pack(f"{EMBEDDING_DIM}f", *centroid)
                rows_to_insert.append((current_synset, centroid_blob, len(embeddings)))
            current_synset = synset_id
            embeddings = []

        vec = np.array(struct.unpack(f"{EMBEDDING_DIM}f", blob), dtype=np.float32)
        embeddings.append(vec)

    # Last synset
    if current_synset is not None and embeddings:
        centroid = np.stack(embeddings).mean(axis=0)
        centroid_blob = struct.pack(f"{EMBEDDING_DIM}f", *centroid)
        rows_to_insert.append((current_synset, centroid_blob, len(embeddings)))

    conn.executemany(
        "INSERT INTO synset_centroids (synset_id, centroid, property_count) VALUES (?, ?, ?)",
        rows_to_insert,
    )
    conn.commit()
    print(f"  Computed {len(rows_to_insert)} synset centroids")
    return len(rows_to_insert)


# =============================================================================
# Orchestrator
# =============================================================================

def run_pipeline(
    db_path: str,
    enrichment_file: str,
    fasttext_vec: str,
    threshold: float = 0.5,
) -> dict:
    """Run the full downstream enrichment pipeline.

    Returns a stats dict.
    """
    print(f"=== Enrichment Pipeline ===")
    print(f"  DB: {db_path}")
    print(f"  Enrichment: {enrichment_file}")

    with open(enrichment_file) as f:
        data = json.load(f)

    model_used = data.get("config", {}).get("model", "unknown")

    vectors = load_fasttext_vectors(fasttext_vec)

    conn = sqlite3.connect(db_path)
    try:
        props = curate_properties(conn, data, vectors)
        links = populate_synset_properties(conn, data, model_used)
        compute_idf(conn)
        sim_pairs = compute_property_similarity(conn, threshold=threshold)
        centroids = compute_synset_centroids(conn)
    finally:
        conn.close()

    stats = {
        "properties_curated": props,
        "synset_links": links,
        "similarity_pairs": sim_pairs,
        "centroids": centroids,
    }
    print(f"=== Pipeline complete: {stats} ===")
    return stats


def main():
    parser = argparse.ArgumentParser(description="Run downstream enrichment pipeline")
    parser.add_argument("--db", required=True, help="Path to lexicon DB")
    parser.add_argument("--enrichment", required=True, help="Enrichment JSON file")
    parser.add_argument(
        "--fasttext",
        default=str(FASTTEXT_VEC),
        help="Path to FastText .vec file",
    )
    parser.add_argument(
        "--threshold", type=float, default=0.5, help="Similarity threshold"
    )
    args = parser.parse_args()

    run_pipeline(args.db, args.enrichment, args.fasttext, args.threshold)


if __name__ == "__main__":
    main()
