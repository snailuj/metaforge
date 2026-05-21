"""Compute synset centroids from property embeddings.

For each enriched synset, average its property embeddings into a single
300-d centroid vector and store in `synset_centroids` for fast Go-side
cosine distance queries (eliminates the N+1 query problem in
`GetForgeMatches`). The Python-side cascade evaluator (M03) also reads
centroids from this table for its domain-distance re-rank stage.

This module restores the pipeline step that was inadvertently dropped
in commit 3948dedf ("Refactor: pipeline split + MRR evaluation
framework"). The Python-side cascade evaluator (M03) reads centroids
from this table for its domain-distance re-rank stage; the planned Go
API forge integration (M03-S05) will read them too. Without this step
in the pipeline, the table only gets populated by an out-of-band manual
run that any clean rebuild then forgets.

`run_pipeline()` in `enrich_pipeline.py` calls `build_synset_centroids`
after the snap/antonym steps so every fresh rebuild has up-to-date
centroids.

Idempotency: uses INSERT OR REPLACE so a re-run cleanly updates any
stale rows. The table itself is created with `CREATE TABLE IF NOT
EXISTS` rather than `DROP TABLE; CREATE TABLE` so a mid-rebuild
interrupt doesn't lose previously-built centroids.
"""
from __future__ import annotations

import logging
import sqlite3
import struct
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
from utils import EMBEDDING_DIM, LEXICON_V2

log = logging.getLogger(__name__)


_CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS synset_centroids (
    synset_id      TEXT PRIMARY KEY,
    centroid       BLOB NOT NULL,
    property_count INTEGER NOT NULL
);
"""


def ensure_table(conn: sqlite3.Connection) -> None:
    """Create synset_centroids if it doesn't exist. Idempotent."""
    conn.execute(_CREATE_TABLE_SQL)
    conn.commit()


def build_synset_centroids(conn: sqlite3.Connection) -> int:
    """Compute + store a centroid per enriched synset. Returns row count.

    Reads property embeddings from ``property_vocabulary.embedding`` joined
    via ``synset_properties.property_id``. Synsets whose properties have
    no embeddings (entirely-OOV property set) get no centroid — silently
    skipped, since the cascade evaluator handles missing-centroid pairs
    fail-open.

    Idempotent: uses INSERT OR REPLACE so a re-run updates rows in place.
    After the insert, centroids for synsets that no longer appear in
    ``synset_properties`` are pruned so stale rows from a prior rebuild
    cannot silently feed into the cascade.

    Note on table asymmetry: this builder reads property embeddings from
    ``property_vocabulary`` joined via ``synset_properties`` (pre-snap, raw
    properties). The Ortony stage of the cascade reads cluster ids from
    ``synset_properties_curated`` (post-snap, cluster-canonicalised). A synset
    can in principle have one signal but not the other (e.g. raw properties
    with all-NULL embeddings → no centroid but curated cluster ids present →
    Ortony works). The cascade evaluator handles missing centroids fail-open
    in this case.
    """
    ensure_table(conn)

    cursor = conn.execute(
        """
        SELECT sp.synset_id, pv.embedding
        FROM synset_properties sp
        JOIN property_vocabulary pv ON pv.property_id = sp.property_id
        WHERE pv.embedding IS NOT NULL
        ORDER BY sp.synset_id
        """
    )

    current_synset: str | None = None
    embeddings: list[np.ndarray] = []
    rows_to_insert: list[tuple[str, bytes, int]] = []
    synsets_seen: set[str] = set()
    synsets_with_all_malformed: list[str] = []

    def _flush() -> None:
        nonlocal current_synset, embeddings
        if current_synset is not None:
            if embeddings:
                centroid = np.mean(np.stack(embeddings), axis=0).astype(np.float32)
                blob = struct.pack(f"{EMBEDDING_DIM}f", *centroid)
                rows_to_insert.append((current_synset, blob, len(embeddings)))
            else:
                # synset had properties but every embedding was malformed or NULL
                synsets_with_all_malformed.append(current_synset)
        embeddings = []

    for synset_id, blob in cursor:
        if synset_id != current_synset:
            _flush()
            current_synset = synset_id
        if synset_id is not None:
            synsets_seen.add(synset_id)
        # Length-divisibility guard BEFORE np.frombuffer: a BLOB whose byte length
        # is not a multiple of 4 crashes inside numpy with a ValueError rather
        # than surfacing as a per-row WARNING. Mirror of the sibling guards in
        # evaluate_cascade._centroid (684319f4) and m03_diagnostics._centroid
        # (736032fd) — the round-2 superpowers reviewer flagged this builder as
        # the missed third sibling.
        if len(blob) % 4 != 0:
            log.warning(
                "skipping property embedding for %s: malformed BLOB length %d (not multiple of 4)",
                synset_id, len(blob),
            )
            continue
        vec = np.frombuffer(blob, dtype=np.float32)
        if vec.shape != (EMBEDDING_DIM,):
            log.warning(
                "skipping malformed property embedding on synset %s "
                "(expected %d float32, got %d bytes)",
                synset_id, EMBEDDING_DIM, len(blob),
            )
            continue
        embeddings.append(vec)
    _flush()

    log.info(
        "centroid build: %d synsets seen, %d to insert, %d skipped (all-malformed embeddings)",
        len(synsets_seen), len(rows_to_insert), len(synsets_with_all_malformed),
    )
    if synsets_with_all_malformed:
        log.warning(
            "%d synsets had no usable embeddings (sample: %s)",
            len(synsets_with_all_malformed),
            synsets_with_all_malformed[:5],
        )

    if not rows_to_insert:
        log.info("no centroids to insert — no enriched synsets with embeddings")
        return 0

    conn.executemany(
        "INSERT OR REPLACE INTO synset_centroids "
        "(synset_id, centroid, property_count) VALUES (?, ?, ?)",
        rows_to_insert,
    )
    conn.commit()

    # Prune centroids for synsets that no longer have any properties (stale from
    # prior rebuild). Without this, a synset whose properties get deleted between
    # rebuilds keeps its stale centroid and the cascade silently uses it.
    deleted = conn.execute(
        """
        DELETE FROM synset_centroids
        WHERE synset_id NOT IN (
            SELECT DISTINCT synset_id FROM synset_properties
        )
        """
    ).rowcount
    conn.commit()
    if deleted > 0:
        log.info("pruned %d stale centroids (no longer in synset_properties)", deleted)

    log.info("stored %d synset centroids", len(rows_to_insert))
    return len(rows_to_insert)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    if not LEXICON_V2.exists():
        log.error("Database not found: %s", LEXICON_V2)
        sys.exit(1)
    log.info("Computing synset centroids in %s...", LEXICON_V2)
    conn = sqlite3.connect(LEXICON_V2)
    try:
        count = build_synset_centroids(conn)
        if count > 0:
            row = conn.execute(
                "SELECT MIN(property_count), MAX(property_count), "
                "AVG(property_count) FROM synset_centroids"
            ).fetchone()
            log.info(
                "stored %d centroids — properties per synset: min=%d max=%d avg=%.1f",
                count, row[0], row[1], row[2],
            )
    finally:
        conn.close()


if __name__ == "__main__":
    main()
