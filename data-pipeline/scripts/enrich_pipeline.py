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

import nltk
import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
from utils import EMBEDDING_DIM, FASTTEXT_VEC, normalise
from build_vocab import build_and_store
from cluster_vocab import cluster_vocab
from snap_properties import snap_properties
from build_antonyms import build_antonym_table, build_cluster_antonym_table

# Lazy-download NLTK tagger data on first import
try:
    nltk.data.find("taggers/averaged_perceptron_tagger_eng")
except LookupError:
    nltk.download("averaged_perceptron_tagger_eng", quiet=True)

MAX_PROPERTIES_PER_SYNSET = 15
SIMILARITY_CHUNK_SIZE = 2048


def _ensure_v2_schema(conn: sqlite3.Connection) -> None:
    """Apply v2 schema migrations: add salience columns, create lemma_metadata."""
    # Add columns to synset_properties if missing
    cols = {r[1] for r in conn.execute("PRAGMA table_info(synset_properties)").fetchall()}
    if "salience" not in cols:
        conn.execute("ALTER TABLE synset_properties ADD COLUMN salience REAL NOT NULL DEFAULT 1.0")
    if "property_type" not in cols:
        conn.execute("ALTER TABLE synset_properties ADD COLUMN property_type TEXT")
    if "relation" not in cols:
        conn.execute("ALTER TABLE synset_properties ADD COLUMN relation TEXT")

    # Create lemma_metadata table if missing
    conn.execute("""
        CREATE TABLE IF NOT EXISTS lemma_metadata (
            lemma       TEXT NOT NULL,
            synset_id   TEXT NOT NULL,
            register    TEXT CHECK (register IN ('formal', 'neutral', 'informal', 'slang')),
            connotation TEXT CHECK (connotation IN ('positive', 'neutral', 'negative')),
            PRIMARY KEY (lemma, synset_id)
        )
    """)
    conn.commit()


# =============================================================================
# MWE filter — strip adjectives/adverbs from multi-word properties
# =============================================================================

_STRIP_PREFIXES = ("JJ", "RB")


def filter_mwe(text: str) -> str | None:
    """Filter multi-word expressions by stripping adjectives/adverbs.

    Single tokens pass through unchanged. For multi-word inputs, POS-tag
    and remove JJ*/RB* words. Keep only if exactly 1 word remains.
    """
    tokens = text.split()
    if len(tokens) <= 1:
        return text
    tagged = nltk.pos_tag(tokens)
    kept = [word for word, tag in tagged if not tag.startswith(_STRIP_PREFIXES)]
    if len(kept) == 1:
        return kept[0]
    return None


# =============================================================================
# 1. Curate properties (from curate_properties.py)
# =============================================================================

_fasttext_cache: dict[str, dict[str, tuple[float, ...]]] = {}


def load_fasttext_vectors(vec_path: str) -> dict[str, tuple[float, ...]]:
    """Load FastText vectors from .vec file into memory.

    Results are cached by path — subsequent calls return the same dict.
    """
    if vec_path in _fasttext_cache:
        print(f"  Using cached vectors for {vec_path}")
        return _fasttext_cache[vec_path]

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
    _fasttext_cache[vec_path] = vectors
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
            filtered = filter_mwe(normalise(prop))
            if filtered is not None:
                all_props.add(filtered)

    count = 0
    for prop in sorted(all_props):
        emb = _get_embedding(prop, vectors)
        if emb is None and re.search(r"[-\s/]", prop):
            emb = _get_compound_embedding(prop, vectors)

        is_oov = 1 if emb is None else 0

        conn.execute(
            """INSERT OR IGNORE INTO property_vocabulary (text, embedding, is_oov, source)
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
            prop_filtered = filter_mwe(normalise(prop))
            if prop_filtered is None:
                continue
            if prop_filtered in prop_ids:
                conn.execute(
                    "INSERT OR IGNORE INTO synset_properties (synset_id, property_id) VALUES (?, ?)",
                    (synset_id, prop_ids[prop_filtered]),
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

    # O(n²) pairwise similarity — n properties, chunked to limit memory
    num_chunks = (n + chunk_size - 1) // chunk_size
    total_chunk_pairs = num_chunks * (num_chunks + 1) // 2  # upper triangle of chunk grid
    print(f"  Computing pairwise similarity: {n} properties, "
          f"{num_chunks} chunks, {total_chunk_pairs} chunk pairs", flush=True)

    matrix = np.array(embeddings, dtype=np.float32)
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    norms[norms == 0] = 1
    normalised = matrix / norms

    unique_count = 0
    chunk_pairs_done = 0
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

            chunk_pairs_done += 1
            if chunk_pairs_done % 5 == 0 or chunk_pairs_done == total_chunk_pairs:
                print(f"    Chunk {chunk_pairs_done}/{total_chunk_pairs} "
                      f"({chunk_pairs_done * 100 // total_chunk_pairs}%), "
                      f"pairs so far: {unique_count}", flush=True)

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
# 6. Store lemma embeddings
# =============================================================================

def store_lemma_embeddings(
    conn: sqlite3.Connection,
    vectors: dict[str, tuple[float, ...]],
) -> int:
    """Store FastText embeddings for all known lemmas.

    Creates the lemma_embeddings table and populates it with packed 300d
    vectors for every lemma in the lemmas table that exists in the vectors
    dict.  OOV lemmas are excluded.

    Returns the number of embeddings stored.
    """
    conn.execute("""
        CREATE TABLE IF NOT EXISTS lemma_embeddings (
            lemma TEXT PRIMARY KEY,
            embedding BLOB NOT NULL
        )
    """)

    lemmas = conn.execute("SELECT DISTINCT lemma FROM lemmas").fetchall()

    count = 0
    for (lemma,) in lemmas:
        if lemma in vectors:
            blob = struct.pack(f"{EMBEDDING_DIM}f", *vectors[lemma])
            conn.execute(
                "INSERT OR REPLACE INTO lemma_embeddings (lemma, embedding) VALUES (?, ?)",
                (lemma, blob),
            )
            count += 1

    conn.commit()
    print(f"  Stored {count} lemma embeddings")
    return count


# =============================================================================
# Orchestrator
# =============================================================================

def run_pipeline(
    db_path: str,
    enrichment_files: list[str],
    fasttext_vec: str,
    threshold: float = 0.5,
) -> dict:
    """Run the full downstream enrichment pipeline.

    Accepts one or more enrichment JSON files. FastText vectors are loaded
    once and reused across all files.

    Returns a stats dict.
    """
    print(f"=== Enrichment Pipeline ===")
    print(f"  DB: {db_path}")
    print(f"  Enrichment files: {len(enrichment_files)}")
    for f in enrichment_files:
        print(f"    {f}")

    vectors = load_fasttext_vectors(fasttext_vec)

    total_props = 0
    total_links = 0
    lemma_emb_count = 0

    conn = sqlite3.connect(db_path)
    try:
        # Process each enrichment file (curate + populate)
        for enrichment_file in enrichment_files:
            print(f"\n  --- Processing: {enrichment_file} ---")
            with open(enrichment_file) as f:
                data = json.load(f)

            model_used = data.get("config", {}).get("model", "unknown")

            total_props += curate_properties(conn, data, vectors)
            lemma_emb_count = store_lemma_embeddings(conn, vectors)
            total_links += populate_synset_properties(conn, data, model_used)

        # Downstream steps run once on the combined data
        print("\n  --- Running downstream steps ---")
        compute_idf(conn)
        sim_pairs = compute_property_similarity(conn, threshold=threshold)
        centroids = compute_synset_centroids(conn)

        # --- Curated vocabulary pipeline ---
        print("  Building curated vocabulary...")
        vocab_entries = build_and_store(conn)
        print("  Clustering vocabulary...")
        cluster_stats = cluster_vocab(conn)
        print("  Snapping properties to curated vocabulary...")
        snap_stats = snap_properties(conn)
        print("  Building antonym pairs...")
        antonym_pairs = build_antonym_table(conn)
        print("  Building cluster antonym pairs...")
        cluster_antonym_pairs = build_cluster_antonym_table(conn)
    finally:
        conn.close()

    stats = {
        "properties_curated": total_props,
        "lemma_embeddings": lemma_emb_count,
        "synset_links": total_links,
        "similarity_pairs": sim_pairs,
        "centroids": centroids,
        "vocab_entries": vocab_entries,
        "vocab_clusters": cluster_stats.get("num_clusters", 0),
        "vocab_singletons": cluster_stats.get("singletons", 0),
        "snapped_properties": sum(snap_stats.values()) - snap_stats.get("dropped", 0),
        "antonym_pairs": antonym_pairs,
        "cluster_antonym_pairs": cluster_antonym_pairs,
    }
    print(f"=== Pipeline complete: {stats} ===")
    return stats


def main():
    parser = argparse.ArgumentParser(description="Run downstream enrichment pipeline")
    parser.add_argument("--db", required=True, help="Path to lexicon DB")
    parser.add_argument(
        "--enrichment", required=True, nargs="+",
        help="One or more enrichment JSON files",
    )
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
