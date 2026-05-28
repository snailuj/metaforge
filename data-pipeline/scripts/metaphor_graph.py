"""Metaphor graph schema, path hashing, snap, insert, judgment, view helpers.

Implements the bridge-centric metaphor graph layer specified in
docs/superpowers/specs/2026-05-28-metaphor-graph-schema-design.md.

Public surface:
    compute_path_hash(step_synset_ids)        -> str        # idempotency hash
    apply_schema(conn)                        -> None       # creates tables + view
    snap_concept_string(conn, text)           -> str | None # exact + morphological
    insert_bridge(conn, ...)                  -> int        # returns bridge_id
    record_judgment(conn, ...)                -> int        # returns judgment_id
"""
from __future__ import annotations

import hashlib
import sqlite3
import logging

log = logging.getLogger(__name__)

import nltk
from nltk.stem import WordNetLemmatizer

# NLTK lemmatiser is thread-safe and cheap to instantiate but we cache the
# instance to avoid repeated attribute lookups in tight loops.
_LEMMATISER: WordNetLemmatizer | None = None


def _get_lemmatiser() -> WordNetLemmatizer:
    global _LEMMATISER
    if _LEMMATISER is None:
        try:
            nltk.data.find("corpora/wordnet")
        except LookupError:
            log.info("snap_concept_string: WordNet corpus missing — downloading")
            try:
                nltk.download("wordnet", quiet=True)
            except Exception as e:
                log.error("snap_concept_string: WordNet download failed: %s", e)
                raise
        _LEMMATISER = WordNetLemmatizer()
    return _LEMMATISER


METAPHOR_GRAPH_DDL = """
CREATE TABLE IF NOT EXISTS metaphor_bridges (
    bridge_id          INTEGER PRIMARY KEY AUTOINCREMENT,
    topic_synset_id    TEXT NOT NULL REFERENCES synsets(synset_id),
    vehicle_synset_id  TEXT NOT NULL REFERENCES synsets(synset_id),
    proposer           TEXT NOT NULL,
    proposed_at        TEXT NOT NULL,
    path_hash          TEXT NOT NULL,
    rationale          TEXT,
    cosine_distance    REAL,
    ortony_score       REAL,
    cascade_score      REAL,
    signed_delta       REAL,
    UNIQUE (topic_synset_id, vehicle_synset_id, proposer, path_hash)
);

CREATE INDEX IF NOT EXISTS idx_metaphor_bridges_topic
    ON metaphor_bridges(topic_synset_id);
CREATE INDEX IF NOT EXISTS idx_metaphor_bridges_vehicle
    ON metaphor_bridges(vehicle_synset_id);
CREATE INDEX IF NOT EXISTS idx_metaphor_bridges_proposer
    ON metaphor_bridges(proposer);

CREATE TABLE IF NOT EXISTS metaphor_bridge_steps (
    bridge_id          INTEGER NOT NULL REFERENCES metaphor_bridges(bridge_id) ON DELETE CASCADE,
    step_index         INTEGER NOT NULL,
    via_synset_id      TEXT NOT NULL REFERENCES synsets(synset_id),
    PRIMARY KEY (bridge_id, step_index)
);

CREATE INDEX IF NOT EXISTS idx_metaphor_bridge_steps_via
    ON metaphor_bridge_steps(via_synset_id);

CREATE TABLE IF NOT EXISTS metaphor_judgments (
    judgment_id        INTEGER PRIMARY KEY AUTOINCREMENT,
    bridge_id          INTEGER NOT NULL REFERENCES metaphor_bridges(bridge_id) ON DELETE CASCADE,
    label              TEXT NOT NULL CHECK (label IN
                         ('live','dead_synonym','dead_lakoff','irrelevant','edge_case')),
    judged_by          TEXT NOT NULL,
    judged_at          TEXT NOT NULL,
    confidence         REAL,
    notes              TEXT,
    UNIQUE (bridge_id, judged_by)
);

CREATE INDEX IF NOT EXISTS idx_metaphor_judgments_label
    ON metaphor_judgments(label);
CREATE INDEX IF NOT EXISTS idx_metaphor_judgments_judged_by
    ON metaphor_judgments(judged_by);
"""


def apply_schema(conn: sqlite3.Connection) -> None:
    """Apply metaphor-graph tables + indexes. Idempotent.

    The graph_edges VIEW is added by a separate function (apply_graph_view)
    because the view depends on tables that may or may not exist in test
    fixtures (synset_metonyms, property_antonyms, etc.). Production DBs
    have all sources; tests opt in.
    """
    conn.executescript(METAPHOR_GRAPH_DDL)
    conn.commit()


def compute_path_hash(step_synset_ids: list[str]) -> str:
    """Order-preserving sha256 over the bridge's intermediate node IDs.

    Used as the idempotency key alongside (topic, vehicle, proposer): re-running
    a proposer with the same bridge does not create a duplicate row.

    Raises ValueError if the path is empty — every bridge must have at least
    one intermediate, per the spec.
    """
    if not step_synset_ids:
        raise ValueError("path_hash: empty path — every bridge needs >=1 intermediate")
    joined = "|".join(step_synset_ids)
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()


def insert_bridge(
    conn: sqlite3.Connection,
    *,
    topic_synset_id: str,
    vehicle_synset_id: str,
    proposer: str,
    proposed_at: str,
    path: list[str],
    rationale: str | None = None,
    cosine_distance: float | None = None,
    ortony_score: float | None = None,
    cascade_score: float | None = None,
    signed_delta: float | None = None,
) -> int:
    """Insert a metaphor bridge with its ordered intermediate steps. Idempotent.

    `path` must be a non-empty list of pre-snapped synset_ids — the
    intermediate nodes between topic and vehicle. Endpoints are NOT in the
    path.

    Returns the bridge_id (existing if a duplicate of (topic, vehicle,
    proposer, path_hash) is already stored; newly created otherwise).

    The whole operation runs inside a single transaction — if any step
    insert fails the bridge row is rolled back too.
    """
    path_hash = compute_path_hash(path)

    # Check for existing row first (idempotency). This is a read; do it before
    # opening the write transaction so we don't churn on common no-ops.
    existing = conn.execute(
        "SELECT bridge_id FROM metaphor_bridges "
        "WHERE topic_synset_id = ? AND vehicle_synset_id = ? "
        "AND proposer = ? AND path_hash = ?",
        (topic_synset_id, vehicle_synset_id, proposer, path_hash),
    ).fetchone()
    if existing is not None:
        return existing[0]

    with conn:  # atomic: commit on success, rollback on exception
        cur = conn.execute(
            "INSERT INTO metaphor_bridges "
            "(topic_synset_id, vehicle_synset_id, proposer, proposed_at, path_hash, "
            " rationale, cosine_distance, ortony_score, cascade_score, signed_delta) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                topic_synset_id, vehicle_synset_id, proposer, proposed_at, path_hash,
                rationale, cosine_distance, ortony_score, cascade_score, signed_delta,
            ),
        )
        bridge_id = cur.lastrowid
        conn.executemany(
            "INSERT INTO metaphor_bridge_steps (bridge_id, step_index, via_synset_id) "
            "VALUES (?, ?, ?)",
            [(bridge_id, i, via) for i, via in enumerate(path)],
        )
    return bridge_id


def snap_concept_string(conn: sqlite3.Connection, text: str) -> str | None:
    """Map a raw LLM-emitted concept string to a curated synset_id.

    Mirrors the first two stages of the snap_properties.py cascade:
        1. Exact match on property_vocab_curated.lemma (case-insensitive).
        2. Morphological normalisation via NLTK WordNet lemmatiser, then exact.

    Returns the synset_id of the matched curated vocab entry, or None if no
    match. Embedding-based fallback is deliberately NOT implemented here —
    callers that need it can call the batch snapper directly. This single-
    string helper is for proposer pipelines where exact+morphological
    coverage suffices.
    """
    if not text or not text.strip():
        return None
    normalised = text.strip().lower()

    # Stage 1: exact
    # TODO(perf): LOWER(lemma) bypasses idx_vocab_lemma. Acceptable at single-proposer
    # call frequency; revisit with an expression index if bridge proposal scales up.
    row = conn.execute(
        "SELECT synset_id FROM property_vocab_curated WHERE LOWER(lemma) = ? LIMIT 1",
        (normalised,),
    ).fetchone()
    if row is not None:
        return row[0]

    # Stage 2: morphological — try a/v/n/r lemmatisation, matching snap_properties.py order
    lemmatiser = _get_lemmatiser()
    for pos in ("a", "v", "n", "r"):
        candidate = lemmatiser.lemmatize(normalised, pos=pos)
        if candidate == normalised:
            continue
        row = conn.execute(
            "SELECT synset_id FROM property_vocab_curated WHERE LOWER(lemma) = ? LIMIT 1",
            (candidate,),
        ).fetchone()
        if row is not None:
            return row[0]

    log.debug("snap_concept_string miss: text=%r normalised=%r", text, normalised)
    return None


class BridgeSnapFailure(ValueError):
    """Raised when one or more raw concept strings on a proposed bridge fail
    to snap to a curated synset. The bridge is not inserted."""


def insert_bridge_with_raw_path(
    conn: sqlite3.Connection,
    *,
    topic_synset_id: str,
    vehicle_synset_id: str,
    proposer: str,
    proposed_at: str,
    raw_path: list[str],
    rationale: str | None = None,
    cosine_distance: float | None = None,
    ortony_score: float | None = None,
    cascade_score: float | None = None,
    signed_delta: float | None = None,
) -> int:
    """Snap each raw concept string in raw_path to a curated synset, then
    insert the bridge via insert_bridge().

    All-or-nothing: if ANY string fails to snap, BridgeSnapFailure is raised
    and no row is inserted. Snap is done before the write transaction so the
    failure does not leave a partial bridge.
    """
    snapped: list[str] = []
    failures: list[str] = []
    for raw in raw_path:
        s = snap_concept_string(conn, raw)
        if s is None:
            failures.append(raw)
        else:
            snapped.append(s)
    if failures:
        raise BridgeSnapFailure(
            f"could not snap concept string(s) to curated vocab: {failures!r}"
        )
    return insert_bridge(
        conn,
        topic_synset_id=topic_synset_id,
        vehicle_synset_id=vehicle_synset_id,
        proposer=proposer,
        proposed_at=proposed_at,
        path=snapped,
        rationale=rationale,
        cosine_distance=cosine_distance,
        ortony_score=ortony_score,
        cascade_score=cascade_score,
        signed_delta=signed_delta,
    )
