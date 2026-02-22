"""Snap free-form extracted properties to curated vocabulary entries.

Three-stage cascade:
  1. Exact match — property text matches vocabulary lemma verbatim
  2. Morphological normalisation — stem/lemmatise then exact match
  3. Embedding top-1 — cosine similarity above threshold (numpy-vectorised)
  4. Drop — no match found

Usage:
    python snap_properties.py --db PATH [--threshold 0.7]
"""
import argparse
import sqlite3
import struct
import sys
from pathlib import Path

import nltk
import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
from utils import LEXICON_V2, EMBEDDING_DIM

# Ensure WordNet lemmatiser data is available
try:
    nltk.data.find("corpora/wordnet")
except LookupError:
    nltk.download("wordnet", quiet=True)

from nltk.stem import WordNetLemmatizer

_lemmatiser = WordNetLemmatizer()


def _lemmatise(word: str) -> list[str]:
    """Return morphological variants of a word."""
    variants = set()
    for pos in ("a", "v", "n", "r"):
        variants.add(_lemmatiser.lemmatize(word, pos=pos))
    # Also try stripping common suffixes
    if word.endswith("ing") and len(word) > 5:
        variants.add(word[:-3])       # "flickering" -> "flicker"
        variants.add(word[:-3] + "e") # "absorbing" -> "absorbe" (may not be a word)
    if word.endswith("ed") and len(word) > 4:
        variants.add(word[:-2])       # "abridged" -> "abridg"
        variants.add(word[:-1])       # "abridged" -> "abbridge" (may not be a word)
        variants.add(word[:-2] + "e") # "abridged" -> "abridge"
    variants.discard(word)  # Don't re-try exact match
    return list(variants)


def _build_vocab_matrix(
    conn: sqlite3.Connection,
    vocab_by_lemma: dict[str, int],
) -> tuple[np.ndarray, list[int]]:
    """Build normalised numpy matrix of vocab embeddings.

    Single query joins property_vocab_curated with property_vocabulary
    to get embeddings for vocab entries.

    Returns (matrix, vocab_ids) where matrix is (n, EMBEDDING_DIM)
    and vocab_ids[i] corresponds to matrix[i].
    """
    rows = conn.execute("""
        SELECT pvc.vocab_id, pv.embedding
        FROM property_vocab_curated pvc
        JOIN property_vocabulary pv ON LOWER(pv.text) = LOWER(pvc.lemma)
        WHERE pv.embedding IS NOT NULL
    """).fetchall()

    if not rows:
        return np.empty((0, EMBEDDING_DIM), dtype=np.float32), []

    vocab_ids = []
    vectors = []
    for vid, blob in rows:
        vec = struct.unpack(f"{EMBEDDING_DIM}f", blob)
        vectors.append(vec)
        vocab_ids.append(vid)

    matrix = np.array(vectors, dtype=np.float32)
    # L2-normalise for cosine similarity via dot product
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    norms[norms == 0] = 1
    matrix /= norms

    return matrix, vocab_ids


def snap_properties(
    conn: sqlite3.Connection,
    embedding_threshold: float = 0.7,
) -> dict[str, int]:
    """Snap free-form properties to curated vocabulary.

    Reads from synset_properties + property_vocabulary + property_vocab_curated.
    Writes to synset_properties_curated.

    Stage 3 (embedding) uses numpy-vectorised cosine similarity:
    O(P_unmatched) matrix-vector multiplications instead of O(P × V) Python loops.

    Returns stats dict with counts per snap stage.
    """
    # Create output table
    conn.executescript("""
        DROP TABLE IF EXISTS synset_properties_curated;
        CREATE TABLE synset_properties_curated (
            synset_id    TEXT NOT NULL,
            vocab_id     INTEGER NOT NULL,
            cluster_id   INTEGER NOT NULL,
            snap_method  TEXT NOT NULL,
            snap_score   REAL,
            salience_sum REAL NOT NULL DEFAULT 1.0,
            PRIMARY KEY (synset_id, cluster_id)
        );
    """)

    # Load vocabulary: lemma -> vocab_id
    vocab_by_lemma: dict[str, int] = {}
    for vid, lemma in conn.execute(
        "SELECT vocab_id, lemma FROM property_vocab_curated"
    ):
        vocab_by_lemma[lemma.lower()] = vid

    # Load cluster lookup: vocab_id -> cluster_id
    cluster_lookup: dict[int, int] = {}
    try:
        for vid, cid in conn.execute("SELECT vocab_id, cluster_id FROM vocab_clusters"):
            cluster_lookup[vid] = cid
    except Exception:
        pass  # Table may not exist yet — all cluster_ids default to vocab_id
    print(f"    Cluster lookup loaded: {len(cluster_lookup)} entries", flush=True)

    # Build normalised vocab embedding matrix for Stage 3
    vocab_matrix, vocab_ids = _build_vocab_matrix(conn, vocab_by_lemma)
    has_vocab_embeddings = len(vocab_ids) > 0
    print(f"    Vocab embeddings loaded: {len(vocab_ids)} entries", flush=True)

    # Load synset-property links with property text, embedding, and salience
    synset_props: list[tuple[str, str, bytes | None, float]] = []
    for sid, text, emb, salience in conn.execute("""
        SELECT sp.synset_id, pv.text, pv.embedding, sp.salience
        FROM synset_properties sp
        JOIN property_vocabulary pv ON pv.property_id = sp.property_id
    """):
        synset_props.append((sid, text, emb, salience))

    total_links = len(synset_props)
    print(f"    Property links to snap: {total_links}", flush=True)

    stats = {"exact": 0, "morphological": 0, "embedding": 0, "dropped": 0}
    # accumulated: key=(synset_id, cluster_id) -> (vocab_id, snap_method, snap_score, salience_sum)
    accumulated: dict[tuple[str, int], tuple[int, str, float | None, float]] = {}

    # Collect unmatched properties for batched embedding lookup
    # (index in synset_props, synset_id, embedding_bytes, salience)
    embedding_candidates: list[tuple[int, str, bytes, float]] = []

    for i, (sid, prop_text, prop_emb, salience) in enumerate(synset_props):
        if (i + 1) % 20000 == 0:
            print(f"    Stages 1-2: {i + 1}/{total_links} "
                  f"(exact={stats['exact']}, morph={stats['morphological']})",
                  flush=True)

        prop_lower = prop_text.lower().strip()

        # Stage 1: Exact match
        if prop_lower in vocab_by_lemma:
            vid = vocab_by_lemma[prop_lower]
            cid = cluster_lookup.get(vid, vid)
            key = (sid, cid)
            if key in accumulated:
                existing = accumulated[key]
                accumulated[key] = (existing[0], existing[1], existing[2], existing[3] + salience)
            else:
                accumulated[key] = (vid, "exact", None, salience)
                stats["exact"] += 1
            continue

        # Stage 2: Morphological normalisation
        matched = False
        for variant in _lemmatise(prop_lower):
            if variant in vocab_by_lemma:
                vid = vocab_by_lemma[variant]
                cid = cluster_lookup.get(vid, vid)
                key = (sid, cid)
                if key in accumulated:
                    existing = accumulated[key]
                    accumulated[key] = (existing[0], existing[1], existing[2], existing[3] + salience)
                else:
                    accumulated[key] = (vid, "morphological", None, salience)
                    stats["morphological"] += 1
                matched = True
                break
        if matched:
            continue

        # Collect for Stage 3 batch processing
        if prop_emb and has_vocab_embeddings:
            embedding_candidates.append((i, sid, prop_emb, salience))
        else:
            stats["dropped"] += 1

    # Stage 3: Batch embedding similarity via numpy
    # Each candidate gets a single matrix-vector dot product: O(V × 300)
    print(f"    Stage 3: {len(embedding_candidates)} candidates for embedding match",
          flush=True)

    for j, (idx, sid, prop_emb, salience) in enumerate(embedding_candidates):
        if (j + 1) % 2000 == 0:
            print(f"    Stage 3: {j + 1}/{len(embedding_candidates)} "
                  f"(matched={stats['embedding']})", flush=True)

        # Unpack and normalise the query vector
        vec = np.array(
            struct.unpack(f"{EMBEDDING_DIM}f", prop_emb),
            dtype=np.float32,
        )
        norm = np.linalg.norm(vec)
        if norm == 0:
            stats["dropped"] += 1
            continue
        vec /= norm

        # Cosine similarities via single matrix-vector multiply
        scores = vocab_matrix @ vec  # shape: (n_vocab,)
        best_idx = int(np.argmax(scores))
        best_score = float(scores[best_idx])

        if best_score >= embedding_threshold:
            best_vid = vocab_ids[best_idx]
            best_cid = cluster_lookup.get(best_vid, best_vid)
            key = (sid, best_cid)
            if key in accumulated:
                existing = accumulated[key]
                accumulated[key] = (existing[0], existing[1], existing[2], existing[3] + salience)
            else:
                accumulated[key] = (best_vid, "embedding", best_score, salience)
                stats["embedding"] += 1
        else:
            stats["dropped"] += 1

    inserts = [
        (sid, vid, cid, method, score, sal_sum)
        for (sid, cid), (vid, method, score, sal_sum) in accumulated.items()
    ]
    conn.executemany(
        "INSERT INTO synset_properties_curated "
        "(synset_id, vocab_id, cluster_id, snap_method, snap_score, salience_sum) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        inserts,
    )

    # Create indexes after bulk insert
    conn.executescript("""
        CREATE INDEX IF NOT EXISTS idx_spc_synset ON synset_properties_curated(synset_id);
        CREATE INDEX IF NOT EXISTS idx_spc_vocab ON synset_properties_curated(vocab_id);
        CREATE INDEX IF NOT EXISTS idx_spc_cluster ON synset_properties_curated(cluster_id);
    """)
    conn.commit()

    total = sum(stats.values())
    print(f"  Snapped {total} property links:")
    print(f"    exact: {stats['exact']}, morphological: {stats['morphological']}, "
          f"embedding: {stats['embedding']}, dropped: {stats['dropped']}")
    return stats


def main():
    parser = argparse.ArgumentParser(description="Snap properties to curated vocabulary")
    parser.add_argument("--db", default=str(LEXICON_V2), help="Path to lexicon DB")
    parser.add_argument("--threshold", type=float, default=0.7, help="Embedding similarity threshold")
    args = parser.parse_args()

    conn = sqlite3.connect(args.db)
    try:
        snap_properties(conn, embedding_threshold=args.threshold)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
