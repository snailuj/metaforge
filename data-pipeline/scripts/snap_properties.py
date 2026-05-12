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

    def __post_init__(self) -> None:
        # Invariant: snap_score is None iff snap_method != "embedding".
        # exact and morphological matches have no cosine score; embedding
        # matches always do. Reject illegal states early.
        if (self.snap_method == "embedding") != (self.snap_score is not None):
            raise ValueError(
                "AccumulatedMatch invariant: snap_score must be set iff "
                f"snap_method == 'embedding' (got method={self.snap_method!r}, "
                f"score={self.snap_score!r})"
            )

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
    # ORDER BY pvc.vocab_id ASC so np.argmax resolves ties on lemma collision
    # deterministically (lowest vocab_id wins). Without ORDER BY, SQL row order
    # is unspecified and snap output drifts across rebuilds when two pvc rows
    # share a lemma but differ in POS or polysemy.
    rows = conn.execute("""
        SELECT pvc.vocab_id, pv.embedding
        FROM property_vocab_curated pvc
        JOIN property_vocabulary pv ON LOWER(pv.text) = LOWER(pvc.lemma)
        WHERE pv.embedding IS NOT NULL
        ORDER BY pvc.vocab_id
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
    # Create output table.
    # CHECK constraints must mirror SCHEMA.sql verbatim — without them the
    # canonical writer strips the constraints on every snap run, leaving them
    # only enforced on a fresh SCHEMA.sql import.
    conn.executescript("""
        DROP TABLE IF EXISTS synset_properties_curated;
        CREATE TABLE synset_properties_curated (
            synset_id    TEXT NOT NULL,
            vocab_id     INTEGER NOT NULL,
            cluster_id   INTEGER NOT NULL,
            snap_method  TEXT NOT NULL CHECK (snap_method IN ('exact', 'morphological', 'embedding')),
            snap_score   REAL,
            salience_sum REAL NOT NULL DEFAULT 1.0 CHECK (salience_sum >= 0.0),
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
    # "no such table" on first-run schemas. Other OperationalError variants
    # (lock contention, disk-IO, readonly, missing-column, schema drift) re-raise
    # so callers can react and we don't pin a misleading WARNING on them.
    cluster_lookup: dict[int, int] = {}
    try:
        for vid, cid in conn.execute("SELECT vocab_id, cluster_id FROM vocab_clusters"):
            cluster_lookup[vid] = cid
    except sqlite3.OperationalError as exc:
        if "no such table" not in str(exc).lower():
            raise
        log.warning(
            "vocab_clusters table not loaded (%s); dedup will degrade to vocab_id-only",
            exc,
        )
    log.info("Cluster lookup loaded: %d entries", len(cluster_lookup))

    # Build normalised vocab embedding matrix for Stage 3
    vocab_matrix, vocab_ids = _build_vocab_matrix(conn)
    has_vocab_embeddings = len(vocab_ids) > 0
    log.info("Vocab embeddings loaded: %d entries", len(vocab_ids))

    stats: dict[str, int] = {"exact": 0, "morphological": 0, "embedding": 0, "dropped": 0}
    accumulated: dict[tuple[str, int], AccumulatedMatch] = {}
    # Per-reason drop counts (so we can log a breakdown without buffering records).
    drop_counts: dict[str, int] = {}

    # Resolve DB path up front so we can open the dropped-records JSONL stream.
    # PRAGMA returns an empty string for ':memory:' connections — guard so we
    # don't silently dump a JSONL into the caller's cwd.
    db_path_str = conn.execute("PRAGMA database_list").fetchone()[2]
    if db_path_str:
        dropped_path: Path | None = Path(db_path_str).parent / "snap_dropped.jsonl"
    else:
        dropped_path = None
        log.warning("skipping snap_dropped.jsonl: in-memory DB has no on-disk path")

    # Lazy open: only create the file if at least one drop occurs. The handle is
    # opened on first drop inside _record_drop and closed by the finally clause
    # below — this guarantees no leak even if Pass 2, executemany, executescript,
    # or commit raises mid-stage.
    dropped_fh = None

    def _record_drop(record: dict) -> None:
        """Stream one drop record to JSONL and bump per-reason counter.

        Streaming caps memory at V2 scale (~50MB if buffered as a list). Each
        record is one self-contained line, so jq/grep work without loading the
        whole file.

        Drops are diagnostic-only — if open() or write() fails (PermissionError,
        ENOSPC, etc.) OR json.dumps() fails (TypeError/ValueError on a
        non-serialisable value such as numpy.float32, Path, Decimal) we log a
        WARNING, disable further JSONL writes, and let the canonical snap stage
        continue. Mirrors the in-memory-DB guard.
        """
        nonlocal dropped_fh, dropped_path
        stats["dropped"] += 1
        drop_counts[record["reason"]] = drop_counts.get(record["reason"], 0) + 1
        if dropped_path is None:
            return
        try:
            if dropped_fh is None:
                dropped_fh = open(dropped_path, "w")
            dropped_fh.write(json.dumps(record) + "\n")
        except (OSError, TypeError, ValueError) as exc:
            log.warning(
                "skipping snap_dropped.jsonl write to %s (%s: %s); "
                "drops are diagnostic-only, snap stage continues",
                dropped_path,
                type(exc).__name__,
                exc,
            )
            if dropped_fh is not None:
                try:
                    dropped_fh.close()
                except OSError as close_exc:
                    # Symmetric to the outer dropped_fh close-guard in the
                    # finally block: a close failure here must not be
                    # silently swallowed or we lose the only trace that
                    # recovery itself was lossy. Diagnostic stream is
                    # already being torn down, so just log and continue.
                    log.warning(
                        "snap_dropped.jsonl close failed during "
                        "write-error recovery (%s: %s); diagnostic "
                        "stream disabled",
                        type(close_exc).__name__,
                        close_exc,
                    )
            dropped_fh = None
            dropped_path = None

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

        On upgrade the new match's vocab_id replaces the existing one — the
        cluster_id key is shared but vocab_id can differ (e.g. an exact match
        on 'sparkle' arriving after a morphological match on 'flicker' both
        landing in cluster 1; the persisted row reports the higher-quality
        match's vocab_id, not the lower).
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

    try:
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
                log.info(
                    "Stages 1-2: %d (exact=%d, morph=%d)",
                    seen, stats["exact"], stats["morphological"],
                )

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
        log.info("Property links to snap: %d", total_links)
        log.info("Stage 3: %d candidates for embedding match", len(unmatched))

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
                    log.info(
                        "Stage 3: %d/%d (matched=%d)",
                        j + 1, len(unmatched), stats["embedding"],
                    )

                if pid in zero_norm_pids:
                    _record_drop({"text": prop_text, "synset_id": sid,
                                  "salience": salience, "reason": "zero_norm"})
                    continue

                vec = emb_cache.get(pid)
                if vec is None:
                    _record_drop({"text": prop_text, "synset_id": sid,
                                  "salience": salience, "reason": "no_embedding"})
                    continue

                # Cosine similarities via single matrix-vector multiply.
                # Clamp to [-1.0, 1.0] before persistence — float32 drift in
                # the normalisation + matmul path can produce values just above
                # 1.0 (e.g. 1.00000011920929 observed in the live DB) which
                # blocks a future snap_score CHECK constraint.
                scores = vocab_matrix @ vec  # shape: (n_vocab,)
                best_idx = int(np.argmax(scores))
                best_score = float(np.clip(scores[best_idx], -1.0, 1.0))

                if best_score >= embedding_threshold:
                    best_vid = vocab_ids[best_idx]
                    best_cid = cluster_lookup.get(best_vid, best_vid)
                    _merge((sid, best_cid), best_vid, "embedding", best_score, salience)
                    stats["embedding"] += 1
                else:
                    _record_drop({"text": prop_text, "synset_id": sid,
                                  "salience": salience, "reason": "below_threshold",
                                  "best_score": best_score})
        else:
            # No vocab embeddings (or no residue) — every unmatched entry is dropped
            for sid, pid, prop_text, salience in unmatched:
                _record_drop({"text": prop_text, "synset_id": sid,
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
        log.info(
            "Snapped %d property links: exact=%d, morphological=%d, embedding=%d, dropped=%d",
            total,
            stats["exact"],
            stats["morphological"],
            stats["embedding"],
            stats["dropped"],
        )
    finally:
        if dropped_fh is not None:
            try:
                dropped_fh.close()
            except OSError as exc:
                log.warning(
                    "failed to close snap_dropped.jsonl handle: %s",
                    exc,
                )

    if drop_counts:
        # Per-reason breakdown so operators can distinguish 'vocab embeddings broken'
        # (zero_norm) from 'OOV property text' (no_embedding) from 'noise above floor'
        # (below_threshold). Mirrors cluster_vocab.py's log.error pattern.
        breakdown = ", ".join(
            f"{reason}={count}" for reason, count in sorted(drop_counts.items())
        )
        log.warning(
            "Snap dropped %d property links: %s",
            sum(drop_counts.values()),
            breakdown,
        )
        if dropped_path is not None:
            log.info("Dropped properties written to %s", dropped_path)

    return stats


def main():
    parser = argparse.ArgumentParser(description="Snap properties to curated vocabulary")
    parser.add_argument("--db", default=str(LEXICON_V2), help="Path to lexicon DB")
    parser.add_argument("--threshold", type=float, default=0.7, help="Embedding similarity threshold")
    args = parser.parse_args()

    # Configure logging so the standalone CLI surfaces log.info summary +
    # log.warning per-reason breakdown lines. Mirrors run_sweep.py and
    # preprocess_munch.py.
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    conn = sqlite3.connect(args.db)
    try:
        snap_properties(conn, embedding_threshold=args.threshold)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
