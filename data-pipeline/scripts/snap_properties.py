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
import json
import logging
import sqlite3
import struct
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import nltk
import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
from utils import LEXICON_V2, EMBEDDING_DIM

log = logging.getLogger(__name__)

# Snap method names. Quality order (high -> low): exact > morphological > embedding.
# The accumulator keeps whichever method has the highest rank when multiple
# properties resolve to the same (synset_id, cluster_id).
SnapMethod = Literal["exact", "morphological", "embedding"]
_METHOD_RANK: dict[SnapMethod, int] = {"exact": 3, "morphological": 2, "embedding": 1}


@dataclass(frozen=True)
class AccumulatedMatch:
    """A match accumulated against a (synset_id, cluster_id) key.

    Frozen — every state transition produces a new instance. Field order is no
    longer load-bearing (previous code used positional 4-tuples and silently
    discarded higher-quality methods that arrived after a lower-quality match).
    """

    vocab_id: int
    snap_method: SnapMethod
    snap_score: float | None
    salience_sum: float

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

    # Load vocabulary: lemma -> vocab_id.
    # ORDER BY vocab_id DESC so the dict-assignment loop ends with the LOWEST
    # vocab_id as the final write per lemma. Lowest vocab_id wins on lemma
    # collision — matches cluster_vocab.py's `min(members)` convention and keeps
    # snap output stable across rebuilds.
    vocab_by_lemma: dict[str, int] = {}
    for vid, lemma in conn.execute(
        "SELECT vocab_id, lemma FROM property_vocab_curated ORDER BY vocab_id DESC"
    ):
        vocab_by_lemma[lemma.lower()] = vid

    # Load cluster lookup: vocab_id -> cluster_id.
    # Narrow the except to OperationalError — the only recoverable failure mode is
    # "no such table" on first-run schemas. Any other exception (corruption, lock
    # contention, schema drift) must propagate so callers can react.
    cluster_lookup: dict[int, int] = {}
    try:
        for vid, cid in conn.execute("SELECT vocab_id, cluster_id FROM vocab_clusters"):
            cluster_lookup[vid] = cid
    except sqlite3.OperationalError as exc:
        log.warning(
            "vocab_clusters table not loaded (%s); dedup will degrade to vocab_id-only",
            exc,
        )
    print(f"    Cluster lookup loaded: {len(cluster_lookup)} entries", flush=True)

    # Build normalised vocab embedding matrix for Stage 3
    vocab_matrix, vocab_ids = _build_vocab_matrix(conn)
    has_vocab_embeddings = len(vocab_ids) > 0
    print(f"    Vocab embeddings loaded: {len(vocab_ids)} entries", flush=True)

    stats: dict[str, int] = {"exact": 0, "morphological": 0, "embedding": 0, "dropped": 0}
    accumulated: dict[tuple[str, int], AccumulatedMatch] = {}
    # Track dropped properties for diagnostics
    dropped_props: list[dict] = []

    def _merge(
        key: tuple[str, int],
        vocab_id: int,
        method: SnapMethod,
        score: float | None,
        salience: float,
    ) -> None:
        """Insert or upgrade the accumulator entry for `key`.

        Upgrade policy: keep the higher-rank snap_method (exact > morphological >
        embedding). On collision, salience always accumulates; on tie or lower
        rank we keep the existing method/score (deterministic).
        """
        existing = accumulated.get(key)
        if existing is None:
            accumulated[key] = AccumulatedMatch(vocab_id, method, score, salience)
            return
        if _METHOD_RANK[method] > _METHOD_RANK[existing.snap_method]:
            accumulated[key] = AccumulatedMatch(
                vocab_id,
                method,
                score,
                existing.salience_sum + salience,
            )
        else:
            accumulated[key] = AccumulatedMatch(
                existing.vocab_id,
                existing.snap_method,
                existing.snap_score,
                existing.salience_sum + salience,
            )

    # Pass 1 (Stages 1-2): stream synset-property cursor WITHOUT loading embedding blobs.
    # The blob column is ~1.2 KB per row; the full join is ~245k rows ≈ 294 MB if
    # materialised. By projecting only (synset_id, property_id, text, salience) we
    # keep peak memory in the low MBs and only carry the unmatched residue forward.
    # Unmatched entries: (synset_id, property_id, text, salience)
    unmatched: list[tuple[str, int, str, float]] = []
    seen = 0
    pass1_cursor = conn.execute("""
        SELECT sp.synset_id, sp.property_id, pv.text, sp.salience
        FROM synset_properties sp
        JOIN property_vocabulary pv ON pv.property_id = sp.property_id
    """)
    for sid, pid, prop_text, salience in pass1_cursor:
        seen += 1
        if seen % 20000 == 0:
            print(f"    Stages 1-2: {seen} "
                  f"(exact={stats['exact']}, morph={stats['morphological']})",
                  flush=True)

        prop_lower = prop_text.lower().strip()

        # Stage 1: Exact match
        if prop_lower in vocab_by_lemma:
            vid = vocab_by_lemma[prop_lower]
            cid = cluster_lookup.get(vid, vid)
            _merge((sid, cid), vid, "exact", None, salience)
            stats["exact"] += 1
            continue

        # Stage 2: Morphological normalisation
        matched = False
        for variant in _lemmatise(prop_lower):
            if variant in vocab_by_lemma:
                vid = vocab_by_lemma[variant]
                cid = cluster_lookup.get(vid, vid)
                _merge((sid, cid), vid, "morphological", None, salience)
                stats["morphological"] += 1
                matched = True
                break
        if matched:
            continue

        # Defer to Pass 2 — stage 3 will fetch embeddings for residual property_ids only
        unmatched.append((sid, pid, prop_text, salience))

    total_links = seen
    print(f"    Property links to snap: {total_links}", flush=True)
    print(f"    Stage 3: {len(unmatched)} candidates for embedding match", flush=True)

    # Pass 2 (Stage 3): cosine-similarity match for unmatched entries.
    # Embeddings are fetched ONCE per unique property_id via a temp-table join,
    # so blob memory scales with the unmatched residue, not with the full corpus.
    if unmatched and has_vocab_embeddings:
        unique_pids = {pid for _, pid, _, _ in unmatched}
        emb_cache: dict[int, np.ndarray] = {}
        zero_norm_pids: set[int] = set()

        conn.execute(
            "CREATE TEMP TABLE _snap_unmatched_pids (property_id INTEGER PRIMARY KEY)"
        )
        try:
            conn.executemany(
                "INSERT INTO _snap_unmatched_pids VALUES (?)",
                [(pid,) for pid in unique_pids],
            )
            for pid, emb_blob in conn.execute("""
                SELECT pv.property_id, pv.embedding
                FROM property_vocabulary pv
                JOIN _snap_unmatched_pids u ON u.property_id = pv.property_id
                WHERE pv.embedding IS NOT NULL
            """):
                vec = np.array(
                    struct.unpack(f"{EMBEDDING_DIM}f", emb_blob),
                    dtype=np.float32,
                )
                norm = np.linalg.norm(vec)
                if norm == 0:
                    zero_norm_pids.add(pid)
                else:
                    emb_cache[pid] = vec / norm
        finally:
            conn.execute("DROP TABLE IF EXISTS _snap_unmatched_pids")

        for j, (sid, pid, prop_text, salience) in enumerate(unmatched):
            if (j + 1) % 2000 == 0:
                print(f"    Stage 3: {j + 1}/{len(unmatched)} "
                      f"(matched={stats['embedding']})", flush=True)

            if pid in zero_norm_pids:
                stats["dropped"] += 1
                dropped_props.append({"text": prop_text, "synset_id": sid,
                                      "salience": salience, "reason": "zero_norm"})
                continue

            vec = emb_cache.get(pid)
            if vec is None:
                stats["dropped"] += 1
                dropped_props.append({"text": prop_text, "synset_id": sid,
                                      "salience": salience, "reason": "no_embedding"})
                continue

            # Cosine similarities via single matrix-vector multiply
            scores = vocab_matrix @ vec  # shape: (n_vocab,)
            best_idx = int(np.argmax(scores))
            best_score = float(scores[best_idx])

            if best_score >= embedding_threshold:
                best_vid = vocab_ids[best_idx]
                best_cid = cluster_lookup.get(best_vid, best_vid)
                _merge((sid, best_cid), best_vid, "embedding", best_score, salience)
                stats["embedding"] += 1
            else:
                stats["dropped"] += 1
                dropped_props.append({"text": prop_text, "synset_id": sid,
                                      "salience": salience, "reason": "below_threshold",
                                      "best_score": best_score})
    else:
        # No vocab embeddings (or no residue) — every unmatched entry is dropped
        for sid, pid, prop_text, salience in unmatched:
            stats["dropped"] += 1
            dropped_props.append({"text": prop_text, "synset_id": sid,
                                  "salience": salience, "reason": "no_embedding"})

    inserts = [
        (sid, m.vocab_id, cid, m.snap_method, m.snap_score, m.salience_sum)
        for (sid, cid), m in accumulated.items()
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

    if dropped_props:
        db_path = conn.execute("PRAGMA database_list").fetchone()[2]
        dropped_path = Path(db_path).parent / "snap_dropped.json"
        with open(dropped_path, "w") as f:
            json.dump(dropped_props, f, indent=2)
        print(f"    Dropped properties written to {dropped_path}")

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
