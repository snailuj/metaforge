"""Snap free-form extracted properties to curated vocabulary entries.

Three-stage cascade:
  1. Exact match — property text matches vocabulary lemma verbatim
  2. Morphological normalisation — stem/lemmatise then exact match
  3. Embedding top-K — cosine similarity above threshold
  4. Drop — no match found

Usage:
    python snap_properties.py --db PATH [--threshold 0.7]
"""
import argparse
import math
import sqlite3
import struct
import sys
from pathlib import Path

import nltk

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


def _cosine_similarity(a: bytes, b: bytes) -> float:
    """Compute cosine similarity between two embedding blobs."""
    va = struct.unpack(f"{EMBEDDING_DIM}f", a)
    vb = struct.unpack(f"{EMBEDDING_DIM}f", b)
    dot = sum(x * y for x, y in zip(va, vb))
    norm_a = math.sqrt(sum(x * x for x in va))
    norm_b = math.sqrt(sum(x * x for x in vb))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def snap_properties(
    conn: sqlite3.Connection,
    embedding_threshold: float = 0.7,
) -> dict[str, int]:
    """Snap free-form properties to curated vocabulary.

    Reads from synset_properties + property_vocabulary + property_vocab_curated.
    Writes to synset_properties_curated.

    Returns stats dict with counts per snap stage.
    """
    # Create output table
    conn.executescript("""
        DROP TABLE IF EXISTS synset_properties_curated;
        CREATE TABLE synset_properties_curated (
            synset_id   TEXT NOT NULL,
            vocab_id    INTEGER NOT NULL,
            snap_method TEXT NOT NULL,
            snap_score  REAL,
            PRIMARY KEY (synset_id, vocab_id)
        );
    """)

    # Load vocabulary: lemma -> vocab_id
    vocab_by_lemma: dict[str, int] = {}
    vocab_embeddings: dict[int, bytes] = {}
    for vid, lemma in conn.execute(
        "SELECT vocab_id, lemma FROM property_vocab_curated"
    ):
        vocab_by_lemma[lemma.lower()] = vid

    # Load vocabulary embeddings (from property_vocabulary, matched by text)
    for vid, lemma in conn.execute(
        "SELECT vocab_id, lemma FROM property_vocab_curated"
    ):
        row = conn.execute(
            "SELECT embedding FROM property_vocabulary WHERE text = ? AND embedding IS NOT NULL",
            (lemma.lower(),)
        ).fetchone()
        if row and row[0]:
            vocab_embeddings[vid] = row[0]

    # Load synset-property links with property text and embedding
    synset_props: list[tuple[str, str, bytes | None]] = []
    for sid, text, emb in conn.execute("""
        SELECT sp.synset_id, pv.text, pv.embedding
        FROM synset_properties sp
        JOIN property_vocabulary pv ON pv.property_id = sp.property_id
    """):
        synset_props.append((sid, text, emb))

    stats = {"exact": 0, "morphological": 0, "embedding": 0, "dropped": 0}
    inserts: list[tuple[str, int, str, float | None]] = []
    seen: set[tuple[str, int]] = set()

    for sid, prop_text, prop_emb in synset_props:
        prop_lower = prop_text.lower().strip()

        # Stage 1: Exact match
        if prop_lower in vocab_by_lemma:
            vid = vocab_by_lemma[prop_lower]
            key = (sid, vid)
            if key not in seen:
                inserts.append((sid, vid, "exact", None))
                seen.add(key)
                stats["exact"] += 1
            continue

        # Stage 2: Morphological normalisation
        matched = False
        for variant in _lemmatise(prop_lower):
            if variant in vocab_by_lemma:
                vid = vocab_by_lemma[variant]
                key = (sid, vid)
                if key not in seen:
                    inserts.append((sid, vid, "morphological", None))
                    seen.add(key)
                    stats["morphological"] += 1
                matched = True
                break
        if matched:
            continue

        # Stage 3: Embedding similarity
        if prop_emb and vocab_embeddings:
            best_vid = None
            best_score = 0.0
            for vid, v_emb in vocab_embeddings.items():
                score = _cosine_similarity(prop_emb, v_emb)
                if score > best_score:
                    best_score = score
                    best_vid = vid
            if best_vid is not None and best_score >= embedding_threshold:
                key = (sid, best_vid)
                if key not in seen:
                    inserts.append((sid, best_vid, "embedding", best_score))
                    seen.add(key)
                    stats["embedding"] += 1
                continue

        # Stage 4: Drop
        stats["dropped"] += 1

    conn.executemany(
        "INSERT INTO synset_properties_curated (synset_id, vocab_id, snap_method, snap_score) "
        "VALUES (?, ?, ?, ?)",
        inserts,
    )

    # Create indexes after bulk insert
    conn.executescript("""
        CREATE INDEX IF NOT EXISTS idx_spc_synset ON synset_properties_curated(synset_id);
        CREATE INDEX IF NOT EXISTS idx_spc_vocab ON synset_properties_curated(vocab_id);
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
