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
