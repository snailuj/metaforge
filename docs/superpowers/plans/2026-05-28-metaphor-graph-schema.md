# Metaphor Graph Schema Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Land the metaphor-graph SQLite schema (`metaphor_bridges`, `metaphor_bridge_steps`, `metaphor_judgments`) plus a unified `graph_edges` VIEW and a Python helper module, so the eyeballer instrument and the eventual graph-completion model have a stable storage surface.

**Architecture:** A single Python module `metaphor_graph.py` owns: schema DDL constants, schema application, path-hash computation, a single-string concept snapper (exact + morphological stages of the existing snap cascade), an idempotent bridge inserter, and a judgment recorder. SCHEMA.sql is updated in lockstep so fresh DB rebuilds include the new tables. A `graph_edges` VIEW unions existing relation tables (`synset_properties_curated`, `synset_metonyms` via `syntagms`, `property_antonyms` via `property_vocab_curated`) with judged-live bridges. No changes to the existing enrichment pipeline.

**Tech Stack:** Python 3.11, SQLite (via stdlib `sqlite3`), pytest, NLTK for morphological lemmatisation (already a dep).

**Spec:** `docs/superpowers/specs/2026-05-28-metaphor-graph-schema-design.md`

---

## File Map

**Create:**
- `data-pipeline/scripts/metaphor_graph.py` — single module with DDL, hash, snap, insert, record_judgment, view-helper.
- `data-pipeline/scripts/test_metaphor_graph.py` — pytest suite for all of the above.

**Modify:**
- `data-pipeline/SCHEMA.sql` — append new tables, indexes, and view at end of file.

**Read-only references during impl:**
- `data-pipeline/scripts/snap_properties.py` — for the exact + morphological match logic patterns to mirror in the single-string snapper.
- `data-pipeline/scripts/test_snap_properties.py` — for in-memory DB fixture patterns.
- `data-pipeline/scripts/test_evaluate_cascade.py` — for executescript-based fixture style.

---

## Working directory and environment

All commands assume CWD `/home/agent/projects/metaforge`. Python tests run via the project venv:

```bash
source data-pipeline/.venv/bin/activate
# or, if missing:
python3 -m venv data-pipeline/.venv
data-pipeline/.venv/bin/pip install -r data-pipeline/requirements.txt
```

Run the full project pytest suite after each commit to catch regressions:

```bash
data-pipeline/.venv/bin/python -m pytest data-pipeline/scripts/ -q
```

Single test (used per-task):

```bash
data-pipeline/.venv/bin/python -m pytest data-pipeline/scripts/test_metaphor_graph.py::TEST_NAME -v
```

---

## Task 1: Path-hash helper (pure function)

**Files:**
- Create: `data-pipeline/scripts/metaphor_graph.py`
- Create: `data-pipeline/scripts/test_metaphor_graph.py`

- [ ] **Step 1: Write the failing tests**

Add to `data-pipeline/scripts/test_metaphor_graph.py`:

```python
"""Tests for metaphor_graph.py — bridge schema, hash, snap, insert, judge, view."""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))

from metaphor_graph import compute_path_hash


class TestComputePathHash:
    def test_empty_path_raises(self):
        """Empty paths are not legal — every bridge has at least one intermediate."""
        with pytest.raises(ValueError, match="empty"):
            compute_path_hash([])

    def test_single_step_is_deterministic(self):
        h1 = compute_path_hash(["heat-n-1"])
        h2 = compute_path_hash(["heat-n-1"])
        assert h1 == h2
        assert len(h1) == 64  # sha256 hex

    def test_different_steps_differ(self):
        assert compute_path_hash(["heat-n-1"]) != compute_path_hash(["destruction-n-1"])

    def test_order_matters(self):
        """A→B→C and A→C→B are different traversals → different hashes."""
        forward = compute_path_hash(["heat-n-1", "spreading-n-1"])
        reverse = compute_path_hash(["spreading-n-1", "heat-n-1"])
        assert forward != reverse

    def test_delimiter_safety(self):
        """Synset IDs never contain '|' in this DB (numeric strings), but the
        hash must not collide if hypothetical IDs share a prefix."""
        # ["a", "bc"] vs ["ab", "c"] — same concat without delimiter, different with
        assert compute_path_hash(["a", "bc"]) != compute_path_hash(["ab", "c"])
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
data-pipeline/.venv/bin/python -m pytest data-pipeline/scripts/test_metaphor_graph.py::TestComputePathHash -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'metaphor_graph'`.

- [ ] **Step 3: Write minimal implementation**

Create `data-pipeline/scripts/metaphor_graph.py`:

```python
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
from typing import Iterable


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
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
data-pipeline/.venv/bin/python -m pytest data-pipeline/scripts/test_metaphor_graph.py::TestComputePathHash -v
```

Expected: 5/5 PASS.

- [ ] **Step 5: Commit**

```bash
git add data-pipeline/scripts/metaphor_graph.py data-pipeline/scripts/test_metaphor_graph.py
git commit -m "feat(metaphor-graph): compute_path_hash helper for bridge idempotency

Order-preserving sha256 over intermediate synset IDs. Used as the third
component of the (topic, vehicle, proposer, path_hash) UNIQUE key on
metaphor_bridges. Empty paths rejected — every bridge must articulate
at least one intermediate node."
```

---

## Task 2: Schema DDL constants + `apply_schema()`

**Files:**
- Modify: `data-pipeline/scripts/metaphor_graph.py`
- Modify: `data-pipeline/scripts/test_metaphor_graph.py`

- [ ] **Step 1: Write the failing tests**

Append to `test_metaphor_graph.py`:

```python
from metaphor_graph import apply_schema


def _conn() -> sqlite3.Connection:
    """Fresh in-memory DB with FK enforcement on. Tests build the synsets
    table directly because they need control over fixture rows."""
    conn = sqlite3.connect(":memory:")
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript("""
        CREATE TABLE synsets (
            synset_id TEXT PRIMARY KEY,
            pos TEXT NOT NULL CHECK (pos IN ('n','v','a','r','s')),
            definition TEXT NOT NULL
        );
    """)
    return conn


class TestApplySchema:
    def test_creates_metaphor_bridges_table(self):
        conn = _conn()
        apply_schema(conn)
        cur = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='metaphor_bridges'")
        assert cur.fetchone() is not None

    def test_creates_metaphor_bridge_steps_table(self):
        conn = _conn()
        apply_schema(conn)
        cur = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='metaphor_bridge_steps'")
        assert cur.fetchone() is not None

    def test_creates_metaphor_judgments_table(self):
        conn = _conn()
        apply_schema(conn)
        cur = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='metaphor_judgments'")
        assert cur.fetchone() is not None

    def test_creates_indexes(self):
        conn = _conn()
        apply_schema(conn)
        names = {row[0] for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND name LIKE 'idx_metaphor%'"
        )}
        assert names == {
            "idx_metaphor_bridges_topic",
            "idx_metaphor_bridges_vehicle",
            "idx_metaphor_bridges_proposer",
            "idx_metaphor_bridge_steps_via",
            "idx_metaphor_judgments_label",
            "idx_metaphor_judgments_judged_by",
        }

    def test_idempotent(self):
        """Re-applying must not error — uses IF NOT EXISTS guards."""
        conn = _conn()
        apply_schema(conn)
        apply_schema(conn)  # second call must not raise
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
data-pipeline/.venv/bin/python -m pytest data-pipeline/scripts/test_metaphor_graph.py::TestApplySchema -v
```

Expected: FAIL with `ImportError: cannot import name 'apply_schema' from 'metaphor_graph'`.

- [ ] **Step 3: Write minimal implementation**

Append to `metaphor_graph.py` (before any function definitions, at module top after the imports):

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
data-pipeline/.venv/bin/python -m pytest data-pipeline/scripts/test_metaphor_graph.py::TestApplySchema -v
```

Expected: 5/5 PASS.

- [ ] **Step 5: Commit**

```bash
git add data-pipeline/scripts/metaphor_graph.py data-pipeline/scripts/test_metaphor_graph.py
git commit -m "feat(metaphor-graph): schema DDL + apply_schema() idempotent installer

Three new tables: metaphor_bridges (topic, vehicle, proposer, path_hash,
cached cascade features), metaphor_bridge_steps (ordered intermediates),
metaphor_judgments (label per bridge per judge). All FKs into synsets.
Idempotent via IF NOT EXISTS guards."
```

---

## Task 3: FK referential integrity test

**Files:**
- Modify: `data-pipeline/scripts/test_metaphor_graph.py`

- [ ] **Step 1: Write the failing test**

Append to `test_metaphor_graph.py`:

```python
class TestForeignKeyEnforcement:
    def test_bridge_rejects_unknown_topic_synset(self):
        conn = _conn()
        apply_schema(conn)
        conn.execute("INSERT INTO synsets VALUES ('fire-n-1', 'n', 'a fire')")
        with pytest.raises(sqlite3.IntegrityError, match="FOREIGN KEY"):
            conn.execute(
                "INSERT INTO metaphor_bridges "
                "(topic_synset_id, vehicle_synset_id, proposer, proposed_at, path_hash) "
                "VALUES (?, ?, ?, ?, ?)",
                ("nonexistent-synset", "fire-n-1", "cascade_v1", "2026-05-28", "deadbeef"),
            )

    def test_bridge_step_rejects_unknown_bridge(self):
        conn = _conn()
        apply_schema(conn)
        conn.execute("INSERT INTO synsets VALUES ('heat-n-1', 'n', 'heat')")
        with pytest.raises(sqlite3.IntegrityError, match="FOREIGN KEY"):
            conn.execute(
                "INSERT INTO metaphor_bridge_steps (bridge_id, step_index, via_synset_id) "
                "VALUES (?, ?, ?)",
                (9999, 0, "heat-n-1"),
            )

    def test_judgment_rejects_unknown_bridge(self):
        conn = _conn()
        apply_schema(conn)
        with pytest.raises(sqlite3.IntegrityError, match="FOREIGN KEY"):
            conn.execute(
                "INSERT INTO metaphor_judgments "
                "(bridge_id, label, judged_by, judged_at) VALUES (?, ?, ?, ?)",
                (9999, "live", "julian", "2026-05-28"),
            )

    def test_judgment_rejects_unknown_label(self):
        conn = _conn()
        apply_schema(conn)
        conn.execute("INSERT INTO synsets VALUES ('anger-n-1', 'n', 'anger')")
        conn.execute("INSERT INTO synsets VALUES ('fire-n-1', 'n', 'a fire')")
        conn.execute("INSERT INTO synsets VALUES ('heat-n-1', 'n', 'heat')")
        conn.execute(
            "INSERT INTO metaphor_bridges "
            "(topic_synset_id, vehicle_synset_id, proposer, proposed_at, path_hash) "
            "VALUES (?, ?, ?, ?, ?)",
            ("anger-n-1", "fire-n-1", "cascade_v1", "2026-05-28", "deadbeef"),
        )
        bid = conn.execute("SELECT bridge_id FROM metaphor_bridges").fetchone()[0]
        with pytest.raises(sqlite3.IntegrityError, match="CHECK"):
            conn.execute(
                "INSERT INTO metaphor_judgments "
                "(bridge_id, label, judged_by, judged_at) VALUES (?, ?, ?, ?)",
                (bid, "maybe-live-ish", "julian", "2026-05-28"),
            )
```

- [ ] **Step 2: Run tests to verify they pass immediately**

```bash
data-pipeline/.venv/bin/python -m pytest data-pipeline/scripts/test_metaphor_graph.py::TestForeignKeyEnforcement -v
```

Expected: 4/4 PASS — the constraints are already in the DDL from Task 2; this task pins them with explicit tests so a future migration cannot silently drop them.

- [ ] **Step 3: Commit**

```bash
git add data-pipeline/scripts/test_metaphor_graph.py
git commit -m "test(metaphor-graph): pin FK + label CHECK constraints on metaphor tables

Explicit tests so a future schema migration cannot silently drop the
referential integrity or label enum constraints. Verifies bridges reject
unknown synsets, bridge_steps reject unknown bridges, judgments reject
unknown bridges, and judgments reject unknown labels."
```

---

## Task 4: `insert_bridge()` with pre-snapped synset_ids + idempotency

**Files:**
- Modify: `data-pipeline/scripts/metaphor_graph.py`
- Modify: `data-pipeline/scripts/test_metaphor_graph.py`

- [ ] **Step 1: Write the failing tests**

Append to `test_metaphor_graph.py`:

```python
from datetime import datetime, timezone

from metaphor_graph import insert_bridge


def _seed_synsets(conn: sqlite3.Connection, *ids: str) -> None:
    for sid in ids:
        conn.execute("INSERT INTO synsets VALUES (?, 'n', ?)", (sid, f"defn of {sid}"))


def _ts() -> str:
    return datetime(2026, 5, 28, tzinfo=timezone.utc).isoformat()


class TestInsertBridge:
    def test_inserts_bridge_and_steps_atomically(self):
        conn = _conn()
        apply_schema(conn)
        _seed_synsets(conn, "anger-n-1", "fire-n-1", "heat-n-1")

        bid = insert_bridge(
            conn,
            topic_synset_id="anger-n-1",
            vehicle_synset_id="fire-n-1",
            proposer="cascade_v1",
            proposed_at=_ts(),
            path=["heat-n-1"],
        )

        row = conn.execute(
            "SELECT topic_synset_id, vehicle_synset_id, proposer, path_hash "
            "FROM metaphor_bridges WHERE bridge_id = ?",
            (bid,),
        ).fetchone()
        assert row == ("anger-n-1", "fire-n-1", "cascade_v1", compute_path_hash(["heat-n-1"]))

        steps = conn.execute(
            "SELECT step_index, via_synset_id FROM metaphor_bridge_steps "
            "WHERE bridge_id = ? ORDER BY step_index",
            (bid,),
        ).fetchall()
        assert steps == [(0, "heat-n-1")]

    def test_multi_hop_path_preserves_order(self):
        conn = _conn()
        apply_schema(conn)
        _seed_synsets(conn, "anger-n-1", "rumour-n-1", "heat-n-1", "spreading-n-1")

        bid = insert_bridge(
            conn,
            topic_synset_id="anger-n-1",
            vehicle_synset_id="rumour-n-1",
            proposer="haiku_v1",
            proposed_at=_ts(),
            path=["heat-n-1", "spreading-n-1"],
            rationale="both spread heat-like through social space",
        )

        steps = conn.execute(
            "SELECT step_index, via_synset_id FROM metaphor_bridge_steps "
            "WHERE bridge_id = ? ORDER BY step_index",
            (bid,),
        ).fetchall()
        assert steps == [(0, "heat-n-1"), (1, "spreading-n-1")]

        rationale = conn.execute(
            "SELECT rationale FROM metaphor_bridges WHERE bridge_id = ?",
            (bid,),
        ).fetchone()[0]
        assert rationale == "both spread heat-like through social space"

    def test_idempotent_returns_existing_bridge_id(self):
        conn = _conn()
        apply_schema(conn)
        _seed_synsets(conn, "anger-n-1", "fire-n-1", "heat-n-1")
        kwargs = dict(
            topic_synset_id="anger-n-1",
            vehicle_synset_id="fire-n-1",
            proposer="cascade_v1",
            proposed_at=_ts(),
            path=["heat-n-1"],
        )
        first = insert_bridge(conn, **kwargs)
        second = insert_bridge(conn, **kwargs)
        assert first == second
        assert conn.execute("SELECT COUNT(*) FROM metaphor_bridges").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM metaphor_bridge_steps").fetchone()[0] == 1

    def test_same_path_different_proposers_are_separate_bridges(self):
        conn = _conn()
        apply_schema(conn)
        _seed_synsets(conn, "anger-n-1", "fire-n-1", "heat-n-1")
        a = insert_bridge(
            conn,
            topic_synset_id="anger-n-1",
            vehicle_synset_id="fire-n-1",
            proposer="cascade_v1",
            proposed_at=_ts(),
            path=["heat-n-1"],
        )
        b = insert_bridge(
            conn,
            topic_synset_id="anger-n-1",
            vehicle_synset_id="fire-n-1",
            proposer="haiku_v1",
            proposed_at=_ts(),
            path=["heat-n-1"],
        )
        assert a != b
        assert conn.execute("SELECT COUNT(*) FROM metaphor_bridges").fetchone()[0] == 2

    def test_cached_features_stored(self):
        conn = _conn()
        apply_schema(conn)
        _seed_synsets(conn, "anger-n-1", "fire-n-1", "heat-n-1")
        bid = insert_bridge(
            conn,
            topic_synset_id="anger-n-1",
            vehicle_synset_id="fire-n-1",
            proposer="cascade_v1",
            proposed_at=_ts(),
            path=["heat-n-1"],
            cosine_distance=0.27,
            ortony_score=0.45,
            cascade_score=0.18,
            signed_delta=1.3,
        )
        row = conn.execute(
            "SELECT cosine_distance, ortony_score, cascade_score, signed_delta "
            "FROM metaphor_bridges WHERE bridge_id = ?",
            (bid,),
        ).fetchone()
        assert row == (0.27, 0.45, 0.18, 1.3)

    def test_rejects_empty_path(self):
        conn = _conn()
        apply_schema(conn)
        _seed_synsets(conn, "anger-n-1", "fire-n-1")
        with pytest.raises(ValueError, match="empty"):
            insert_bridge(
                conn,
                topic_synset_id="anger-n-1",
                vehicle_synset_id="fire-n-1",
                proposer="cascade_v1",
                proposed_at=_ts(),
                path=[],
            )
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
data-pipeline/.venv/bin/python -m pytest data-pipeline/scripts/test_metaphor_graph.py::TestInsertBridge -v
```

Expected: FAIL with `ImportError: cannot import name 'insert_bridge'`.

- [ ] **Step 3: Write minimal implementation**

Append to `metaphor_graph.py`:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
data-pipeline/.venv/bin/python -m pytest data-pipeline/scripts/test_metaphor_graph.py::TestInsertBridge -v
```

Expected: 6/6 PASS.

- [ ] **Step 5: Commit**

```bash
git add data-pipeline/scripts/metaphor_graph.py data-pipeline/scripts/test_metaphor_graph.py
git commit -m "feat(metaphor-graph): insert_bridge() idempotent inserter for pre-snapped paths

Inserts (bridge, ordered steps) atomically within a transaction. Returns
existing bridge_id if (topic, vehicle, proposer, path_hash) already
present. Cached cascade features (cosine, ortony, cascade_score,
signed_delta) and LLM rationale are optional columns on the bridge row."
```

---

## Task 5: Single-string concept snapper (exact + morphological)

**Files:**
- Modify: `data-pipeline/scripts/metaphor_graph.py`
- Modify: `data-pipeline/scripts/test_metaphor_graph.py`

- [ ] **Step 1: Write the failing tests**

Append to `test_metaphor_graph.py`:

```python
from metaphor_graph import snap_concept_string


def _seed_curated(conn: sqlite3.Connection, rows: list[tuple[int, str, str, str, int]]) -> None:
    """rows: (vocab_id, synset_id, lemma, pos, polysemy)."""
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS property_vocab_curated (
            vocab_id    INTEGER PRIMARY KEY,
            synset_id   TEXT NOT NULL,
            lemma       TEXT NOT NULL,
            pos         TEXT NOT NULL,
            polysemy    INTEGER NOT NULL,
            UNIQUE(synset_id)
        );
        CREATE INDEX IF NOT EXISTS idx_vocab_lemma ON property_vocab_curated(lemma);
    """)
    conn.executemany(
        "INSERT INTO property_vocab_curated (vocab_id, synset_id, lemma, pos, polysemy) VALUES (?, ?, ?, ?, ?)",
        rows,
    )


class TestSnapConceptString:
    def test_exact_match(self):
        conn = _conn()
        apply_schema(conn)
        _seed_synsets(conn, "heat-n-1", "fire-n-1")
        _seed_curated(conn, [
            (1, "heat-n-1", "heat", "n", 1),
            (2, "fire-n-1", "fire", "n", 1),
        ])
        assert snap_concept_string(conn, "heat") == "heat-n-1"

    def test_exact_match_case_insensitive(self):
        conn = _conn()
        apply_schema(conn)
        _seed_synsets(conn, "heat-n-1")
        _seed_curated(conn, [(1, "heat-n-1", "heat", "n", 1)])
        assert snap_concept_string(conn, "HEAT") == "heat-n-1"
        assert snap_concept_string(conn, "Heat") == "heat-n-1"

    def test_morphological_match(self):
        conn = _conn()
        apply_schema(conn)
        _seed_synsets(conn, "burn-v-1")
        _seed_curated(conn, [(1, "burn-v-1", "burn", "v", 1)])
        # "burning" lemmatises to "burn" via NLTK
        assert snap_concept_string(conn, "burning") == "burn-v-1"

    def test_miss_returns_none(self):
        conn = _conn()
        apply_schema(conn)
        _seed_synsets(conn, "heat-n-1")
        _seed_curated(conn, [(1, "heat-n-1", "heat", "n", 1)])
        assert snap_concept_string(conn, "qwertyfloof") is None

    def test_empty_string_returns_none(self):
        conn = _conn()
        apply_schema(conn)
        _seed_curated(conn, [])
        assert snap_concept_string(conn, "") is None
        assert snap_concept_string(conn, "   ") is None
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
data-pipeline/.venv/bin/python -m pytest data-pipeline/scripts/test_metaphor_graph.py::TestSnapConceptString -v
```

Expected: FAIL with `ImportError: cannot import name 'snap_concept_string'`.

- [ ] **Step 3: Write minimal implementation**

Append to `metaphor_graph.py`:

```python
import nltk
from nltk.stem import WordNetLemmatizer

# NLTK lemmatiser is thread-safe and cheap to instantiate but we cache the
# instance to avoid repeated attribute lookups in tight loops.
_LEMMATISER: WordNetLemmatizer | None = None


def _get_lemmatiser() -> WordNetLemmatizer:
    global _LEMMATISER
    if _LEMMATISER is None:
        # ensure wordnet is downloaded — silent no-op if already present
        try:
            nltk.data.find("corpora/wordnet")
        except LookupError:
            nltk.download("wordnet", quiet=True)
        _LEMMATISER = WordNetLemmatizer()
    return _LEMMATISER


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
    row = conn.execute(
        "SELECT synset_id FROM property_vocab_curated WHERE LOWER(lemma) = ? LIMIT 1",
        (normalised,),
    ).fetchone()
    if row is not None:
        return row[0]

    # Stage 2: morphological — try noun then verb lemmatisation
    lemmatiser = _get_lemmatiser()
    for pos in ("n", "v", "a", "r"):
        candidate = lemmatiser.lemmatize(normalised, pos=pos)
        if candidate == normalised:
            continue
        row = conn.execute(
            "SELECT synset_id FROM property_vocab_curated WHERE LOWER(lemma) = ? LIMIT 1",
            (candidate,),
        ).fetchone()
        if row is not None:
            return row[0]

    return None
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
data-pipeline/.venv/bin/python -m pytest data-pipeline/scripts/test_metaphor_graph.py::TestSnapConceptString -v
```

Expected: 5/5 PASS.

- [ ] **Step 5: Commit**

```bash
git add data-pipeline/scripts/metaphor_graph.py data-pipeline/scripts/test_metaphor_graph.py
git commit -m "feat(metaphor-graph): snap_concept_string() exact+morphological single-string snapper

Two-stage snap (exact lemma match, then NLTK lemmatisation) for mapping
LLM-emitted concept strings to curated synset_ids. Embedding fallback
deferred — callers needing it run the batch snap_properties.py pipeline."
```

---

## Task 6: `insert_bridge()` accepts raw concept strings (calls snap)

**Files:**
- Modify: `data-pipeline/scripts/metaphor_graph.py`
- Modify: `data-pipeline/scripts/test_metaphor_graph.py`

- [ ] **Step 1: Write the failing tests**

Append to `test_metaphor_graph.py`:

```python
from metaphor_graph import insert_bridge_with_raw_path, BridgeSnapFailure


class TestInsertBridgeWithRawPath:
    def test_snaps_raw_concept_strings(self):
        conn = _conn()
        apply_schema(conn)
        _seed_synsets(conn, "anger-n-1", "fire-n-1", "heat-n-1")
        _seed_curated(conn, [(1, "heat-n-1", "heat", "n", 1)])

        bid = insert_bridge_with_raw_path(
            conn,
            topic_synset_id="anger-n-1",
            vehicle_synset_id="fire-n-1",
            proposer="haiku_v1",
            proposed_at=_ts(),
            raw_path=["heat"],  # raw concept string, not synset_id
            rationale="both consume",
        )

        step = conn.execute(
            "SELECT via_synset_id FROM metaphor_bridge_steps WHERE bridge_id = ?",
            (bid,),
        ).fetchone()
        assert step == ("heat-n-1",)

    def test_raises_on_snap_failure(self):
        conn = _conn()
        apply_schema(conn)
        _seed_synsets(conn, "anger-n-1", "fire-n-1")
        _seed_curated(conn, [(1, "heat-n-1", "heat", "n", 1)])
        conn.execute("INSERT INTO synsets VALUES ('heat-n-1', 'n', 'heat')")

        with pytest.raises(BridgeSnapFailure, match="qwertyfloof"):
            insert_bridge_with_raw_path(
                conn,
                topic_synset_id="anger-n-1",
                vehicle_synset_id="fire-n-1",
                proposer="haiku_v1",
                proposed_at=_ts(),
                raw_path=["qwertyfloof"],
            )
        # nothing committed
        assert conn.execute("SELECT COUNT(*) FROM metaphor_bridges").fetchone()[0] == 0

    def test_partial_snap_failure_still_rejects_whole_bridge(self):
        conn = _conn()
        apply_schema(conn)
        _seed_synsets(conn, "anger-n-1", "rumour-n-1", "heat-n-1")
        _seed_curated(conn, [(1, "heat-n-1", "heat", "n", 1)])
        with pytest.raises(BridgeSnapFailure, match="spreading"):
            insert_bridge_with_raw_path(
                conn,
                topic_synset_id="anger-n-1",
                vehicle_synset_id="rumour-n-1",
                proposer="haiku_v1",
                proposed_at=_ts(),
                raw_path=["heat", "spreading"],  # second one will fail to snap
            )
        assert conn.execute("SELECT COUNT(*) FROM metaphor_bridges").fetchone()[0] == 0
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
data-pipeline/.venv/bin/python -m pytest data-pipeline/scripts/test_metaphor_graph.py::TestInsertBridgeWithRawPath -v
```

Expected: FAIL with `ImportError: cannot import name 'insert_bridge_with_raw_path'`.

- [ ] **Step 3: Write minimal implementation**

Append to `metaphor_graph.py`:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
data-pipeline/.venv/bin/python -m pytest data-pipeline/scripts/test_metaphor_graph.py::TestInsertBridgeWithRawPath -v
```

Expected: 3/3 PASS.

- [ ] **Step 5: Commit**

```bash
git add data-pipeline/scripts/metaphor_graph.py data-pipeline/scripts/test_metaphor_graph.py
git commit -m "feat(metaphor-graph): insert_bridge_with_raw_path() snaps then inserts atomically

LLM proposers emit one-word concept strings; this helper runs them
through the exact+morphological snapper before insertion. All-or-
nothing — any single snap failure raises BridgeSnapFailure and no
row is written."
```

---

## Task 7: `record_judgment()` helper

**Files:**
- Modify: `data-pipeline/scripts/metaphor_graph.py`
- Modify: `data-pipeline/scripts/test_metaphor_graph.py`

- [ ] **Step 1: Write the failing tests**

Append to `test_metaphor_graph.py`:

```python
from metaphor_graph import record_judgment


class TestRecordJudgment:
    def test_inserts_judgment(self):
        conn = _conn()
        apply_schema(conn)
        _seed_synsets(conn, "anger-n-1", "fire-n-1", "heat-n-1")
        bid = insert_bridge(
            conn,
            topic_synset_id="anger-n-1",
            vehicle_synset_id="fire-n-1",
            proposer="cascade_v1",
            proposed_at=_ts(),
            path=["heat-n-1"],
        )

        jid = record_judgment(
            conn,
            bridge_id=bid,
            label="live",
            judged_by="julian",
            judged_at=_ts(),
            confidence=0.95,
            notes="canonical fire-anger",
        )

        row = conn.execute(
            "SELECT bridge_id, label, judged_by, confidence, notes "
            "FROM metaphor_judgments WHERE judgment_id = ?",
            (jid,),
        ).fetchone()
        assert row == (bid, "live", "julian", 0.95, "canonical fire-anger")

    def test_unique_constraint_one_per_bridge_per_judge(self):
        conn = _conn()
        apply_schema(conn)
        _seed_synsets(conn, "anger-n-1", "fire-n-1", "heat-n-1")
        bid = insert_bridge(
            conn,
            topic_synset_id="anger-n-1",
            vehicle_synset_id="fire-n-1",
            proposer="cascade_v1",
            proposed_at=_ts(),
            path=["heat-n-1"],
        )
        record_judgment(
            conn, bridge_id=bid, label="live", judged_by="julian", judged_at=_ts(),
        )
        with pytest.raises(sqlite3.IntegrityError, match="UNIQUE"):
            record_judgment(
                conn, bridge_id=bid, label="dead_lakoff", judged_by="julian", judged_at=_ts(),
            )

    def test_different_judges_same_bridge_both_allowed(self):
        conn = _conn()
        apply_schema(conn)
        _seed_synsets(conn, "anger-n-1", "fire-n-1", "heat-n-1")
        bid = insert_bridge(
            conn,
            topic_synset_id="anger-n-1",
            vehicle_synset_id="fire-n-1",
            proposer="cascade_v1",
            proposed_at=_ts(),
            path=["heat-n-1"],
        )
        j1 = record_judgment(
            conn, bridge_id=bid, label="live", judged_by="julian", judged_at=_ts(),
        )
        j2 = record_judgment(
            conn, bridge_id=bid, label="live", judged_by="llm_judge_v1", judged_at=_ts(),
        )
        assert j1 != j2
        assert conn.execute("SELECT COUNT(*) FROM metaphor_judgments").fetchone()[0] == 2
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
data-pipeline/.venv/bin/python -m pytest data-pipeline/scripts/test_metaphor_graph.py::TestRecordJudgment -v
```

Expected: FAIL with `ImportError: cannot import name 'record_judgment'`.

- [ ] **Step 3: Write minimal implementation**

Append to `metaphor_graph.py`:

```python
def record_judgment(
    conn: sqlite3.Connection,
    *,
    bridge_id: int,
    label: str,
    judged_by: str,
    judged_at: str,
    confidence: float | None = None,
    notes: str | None = None,
) -> int:
    """Insert a judgment on a bridge by a named judge.

    Raises sqlite3.IntegrityError if (bridge_id, judged_by) already has a
    judgment — by spec, one verdict per judge per bridge. If a judge wants
    to change their mind, that's an UPDATE on the existing row, not a new
    insert (caller responsibility — this helper is insert-only).

    Returns the new judgment_id.
    """
    with conn:
        cur = conn.execute(
            "INSERT INTO metaphor_judgments "
            "(bridge_id, label, judged_by, judged_at, confidence, notes) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (bridge_id, label, judged_by, judged_at, confidence, notes),
        )
    return cur.lastrowid
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
data-pipeline/.venv/bin/python -m pytest data-pipeline/scripts/test_metaphor_graph.py::TestRecordJudgment -v
```

Expected: 3/3 PASS.

- [ ] **Step 5: Commit**

```bash
git add data-pipeline/scripts/metaphor_graph.py data-pipeline/scripts/test_metaphor_graph.py
git commit -m "feat(metaphor-graph): record_judgment() inserts one verdict per bridge per judge

UNIQUE(bridge_id, judged_by) enforces the one-verdict-per-judge rule.
Insert-only; mind-changes are caller-driven UPDATEs."
```

---

## Task 8: `graph_edges` VIEW + `apply_graph_view()`

**Files:**
- Modify: `data-pipeline/scripts/metaphor_graph.py`
- Modify: `data-pipeline/scripts/test_metaphor_graph.py`

- [ ] **Step 1: Write the failing tests**

Append to `test_metaphor_graph.py`:

```python
from metaphor_graph import apply_graph_view


def _conn_with_full_sources() -> sqlite3.Connection:
    """In-memory DB with all the upstream tables the VIEW unions over."""
    conn = _conn()
    apply_schema(conn)
    conn.executescript("""
        CREATE TABLE property_vocab_curated (
            vocab_id    INTEGER PRIMARY KEY,
            synset_id   TEXT NOT NULL,
            lemma       TEXT NOT NULL,
            pos         TEXT NOT NULL,
            polysemy    INTEGER NOT NULL,
            UNIQUE(synset_id)
        );
        CREATE TABLE synset_properties_curated (
            synset_id    TEXT NOT NULL,
            vocab_id     INTEGER NOT NULL,
            cluster_id   INTEGER NOT NULL,
            snap_method  TEXT NOT NULL,
            snap_score   REAL,
            salience_sum REAL NOT NULL DEFAULT 1.0,
            PRIMARY KEY (synset_id, cluster_id)
        );
        CREATE TABLE syntagms (
            syntagm_id INTEGER PRIMARY KEY,
            synset1id  TEXT NOT NULL,
            synset2id  TEXT NOT NULL,
            sensekey1  TEXT NOT NULL DEFAULT '',
            sensekey2  TEXT NOT NULL DEFAULT '',
            word1id    INTEGER NOT NULL DEFAULT 0,
            word2id    INTEGER NOT NULL DEFAULT 0
        );
        CREATE TABLE synset_metonyms (
            synset_id            TEXT NOT NULL,
            metonym_syntagm_id   INTEGER NOT NULL,
            metonym_rank         INTEGER NOT NULL,
            PRIMARY KEY (synset_id, metonym_syntagm_id)
        );
        CREATE TABLE property_antonyms (
            vocab_id_a  INTEGER NOT NULL,
            vocab_id_b  INTEGER NOT NULL,
            PRIMARY KEY (vocab_id_a, vocab_id_b)
        );
    """)
    return conn


class TestGraphEdgesView:
    def test_view_exists_after_apply(self):
        conn = _conn_with_full_sources()
        apply_graph_view(conn)
        cur = conn.execute("SELECT name FROM sqlite_master WHERE type='view' AND name='graph_edges'")
        assert cur.fetchone() is not None

    def test_emits_has_property_edges(self):
        conn = _conn_with_full_sources()
        apply_graph_view(conn)
        _seed_synsets(conn, "fire-n-1", "heat-n-1")
        conn.execute("INSERT INTO property_vocab_curated VALUES (10, 'heat-n-1', 'heat', 'n', 1)")
        conn.execute(
            "INSERT INTO synset_properties_curated "
            "(synset_id, vocab_id, cluster_id, snap_method, snap_score, salience_sum) "
            "VALUES ('fire-n-1', 10, 100, 'exact', NULL, 0.8)"
        )
        rows = conn.execute(
            "SELECT src_synset_id, dst_synset_id, relation, weight FROM graph_edges"
        ).fetchall()
        assert ("fire-n-1", "heat-n-1", "has_property", 0.8) in rows

    def test_emits_metonym_edges(self):
        conn = _conn_with_full_sources()
        apply_graph_view(conn)
        _seed_synsets(conn, "crown-n-1", "king-n-1")
        conn.execute(
            "INSERT INTO syntagms (syntagm_id, synset1id, synset2id) VALUES (1, 'crown-n-1', 'king-n-1')"
        )
        conn.execute(
            "INSERT INTO synset_metonyms VALUES ('crown-n-1', 1, 1)"
        )
        rows = conn.execute(
            "SELECT src_synset_id, dst_synset_id, relation FROM graph_edges WHERE relation='metonym_of'"
        ).fetchall()
        assert ("crown-n-1", "king-n-1", "metonym_of") in rows

    def test_emits_antonym_edges_via_curated_vocab(self):
        conn = _conn_with_full_sources()
        apply_graph_view(conn)
        _seed_synsets(conn, "hot-a-1", "cold-a-1")
        conn.execute("INSERT INTO property_vocab_curated VALUES (1, 'hot-a-1', 'hot', 'a', 1)")
        conn.execute("INSERT INTO property_vocab_curated VALUES (2, 'cold-a-1', 'cold', 'a', 1)")
        conn.execute("INSERT INTO property_antonyms VALUES (1, 2)")
        rows = conn.execute(
            "SELECT src_synset_id, dst_synset_id, relation FROM graph_edges WHERE relation='antonym_of'"
        ).fetchall()
        assert ("hot-a-1", "cold-a-1", "antonym_of") in rows

    def test_emits_metaphor_link_for_judged_live_bridge(self):
        conn = _conn_with_full_sources()
        apply_graph_view(conn)
        _seed_synsets(conn, "anger-n-1", "fire-n-1", "heat-n-1")
        bid = insert_bridge(
            conn,
            topic_synset_id="anger-n-1",
            vehicle_synset_id="fire-n-1",
            proposer="cascade_v1",
            proposed_at=_ts(),
            path=["heat-n-1"],
        )
        record_judgment(
            conn, bridge_id=bid, label="live", judged_by="julian", judged_at=_ts(), confidence=0.9,
        )
        rows = conn.execute(
            "SELECT src_synset_id, dst_synset_id, relation, weight, bridge_id "
            "FROM graph_edges WHERE relation='metaphor_link'"
        ).fetchall()
        assert rows == [("anger-n-1", "fire-n-1", "metaphor_link", 0.9, bid)]

    def test_excludes_unjudged_bridge(self):
        conn = _conn_with_full_sources()
        apply_graph_view(conn)
        _seed_synsets(conn, "anger-n-1", "fire-n-1", "heat-n-1")
        insert_bridge(
            conn,
            topic_synset_id="anger-n-1",
            vehicle_synset_id="fire-n-1",
            proposer="cascade_v1",
            proposed_at=_ts(),
            path=["heat-n-1"],
        )
        rows = conn.execute(
            "SELECT * FROM graph_edges WHERE relation='metaphor_link'"
        ).fetchall()
        assert rows == []

    def test_excludes_judged_dead_bridge(self):
        conn = _conn_with_full_sources()
        apply_graph_view(conn)
        _seed_synsets(conn, "anger-n-1", "fire-n-1", "heat-n-1")
        bid = insert_bridge(
            conn,
            topic_synset_id="anger-n-1",
            vehicle_synset_id="fire-n-1",
            proposer="cascade_v1",
            proposed_at=_ts(),
            path=["heat-n-1"],
        )
        record_judgment(
            conn, bridge_id=bid, label="dead_lakoff", judged_by="julian", judged_at=_ts(),
        )
        rows = conn.execute(
            "SELECT * FROM graph_edges WHERE relation='metaphor_link'"
        ).fetchall()
        assert rows == []

    def test_idempotent_apply(self):
        conn = _conn_with_full_sources()
        apply_graph_view(conn)
        apply_graph_view(conn)  # second call must not raise
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
data-pipeline/.venv/bin/python -m pytest data-pipeline/scripts/test_metaphor_graph.py::TestGraphEdgesView -v
```

Expected: FAIL with `ImportError: cannot import name 'apply_graph_view'`.

- [ ] **Step 3: Write minimal implementation**

Append to `metaphor_graph.py`:

```python
GRAPH_EDGES_VIEW_DDL = """
DROP VIEW IF EXISTS graph_edges;

CREATE VIEW graph_edges AS
SELECT
    spc.synset_id     AS src_synset_id,
    pvc.synset_id     AS dst_synset_id,
    'has_property'    AS relation,
    spc.salience_sum  AS weight,
    NULL              AS bridge_id
FROM synset_properties_curated spc
JOIN property_vocab_curated pvc ON pvc.vocab_id = spc.vocab_id

UNION ALL

SELECT
    sm.synset_id                                                            AS src_synset_id,
    CASE WHEN s.synset1id = sm.synset_id THEN s.synset2id ELSE s.synset1id END AS dst_synset_id,
    'metonym_of'                                                            AS relation,
    NULL                                                                    AS weight,
    NULL                                                                    AS bridge_id
FROM synset_metonyms sm
JOIN syntagms s ON s.syntagm_id = sm.metonym_syntagm_id

UNION ALL

SELECT
    pa.synset_id   AS src_synset_id,
    pb.synset_id   AS dst_synset_id,
    'antonym_of'   AS relation,
    NULL           AS weight,
    NULL           AS bridge_id
FROM property_antonyms pant
JOIN property_vocab_curated pa ON pa.vocab_id = pant.vocab_id_a
JOIN property_vocab_curated pb ON pb.vocab_id = pant.vocab_id_b

UNION ALL

SELECT
    mb.topic_synset_id   AS src_synset_id,
    mb.vehicle_synset_id AS dst_synset_id,
    'metaphor_link'      AS relation,
    mj.confidence        AS weight,
    mb.bridge_id         AS bridge_id
FROM metaphor_bridges mb
JOIN metaphor_judgments mj ON mj.bridge_id = mb.bridge_id
WHERE mj.label = 'live';
"""


def apply_graph_view(conn: sqlite3.Connection) -> None:
    """Create (or replace) the graph_edges VIEW. Depends on:
      - synset_properties_curated, property_vocab_curated  (has_property)
      - synset_metonyms, syntagms                          (metonym_of)
      - property_antonyms, property_vocab_curated          (antonym_of)
      - metaphor_bridges, metaphor_judgments               (metaphor_link)

    Idempotent: DROPs and re-creates the view each call.
    """
    conn.executescript(GRAPH_EDGES_VIEW_DDL)
    conn.commit()
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
data-pipeline/.venv/bin/python -m pytest data-pipeline/scripts/test_metaphor_graph.py::TestGraphEdgesView -v
```

Expected: 8/8 PASS.

- [ ] **Step 5: Run the whole project test suite to catch regressions**

```bash
data-pipeline/.venv/bin/python -m pytest data-pipeline/scripts/ -q
```

Expected: all tests pass (605+ tests; the new file adds ~30).

- [ ] **Step 6: Commit**

```bash
git add data-pipeline/scripts/metaphor_graph.py data-pipeline/scripts/test_metaphor_graph.py
git commit -m "feat(metaphor-graph): graph_edges VIEW unifies property+metonym+antonym+metaphor

UNION ALL across synset_properties_curated, synset_metonyms (via
syntagms), property_antonyms (via property_vocab_curated), and judged-
live metaphor_bridges. Live judgments only — dead/irrelevant labels and
unjudged proposals stay in the underlying tables for ML training but do
not show up as graph structure. Apply is idempotent (DROP IF EXISTS +
CREATE)."
```

---

## Task 9: Sync new DDL into SCHEMA.sql

**Files:**
- Modify: `data-pipeline/SCHEMA.sql`

- [ ] **Step 1: Append new tables + indexes + view to SCHEMA.sql**

Append at the end of `data-pipeline/SCHEMA.sql`:

```sql
-- ============================================================
-- Metaphor graph (2026-05-28)
-- ============================================================
-- Bridge-centric layer: a proposal is (topic, vehicle, path) where the
-- path is an ordered list of intermediate synsets. Cascade and LLM
-- proposers share one pool. Judgments attach per (bridge, judge).
-- Spec: docs/superpowers/specs/2026-05-28-metaphor-graph-schema-design.md

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

-- Unified graph view: existing relation tables + judged-live metaphor links
DROP VIEW IF EXISTS graph_edges;
CREATE VIEW graph_edges AS
SELECT
    spc.synset_id     AS src_synset_id,
    pvc.synset_id     AS dst_synset_id,
    'has_property'    AS relation,
    spc.salience_sum  AS weight,
    NULL              AS bridge_id
FROM synset_properties_curated spc
JOIN property_vocab_curated pvc ON pvc.vocab_id = spc.vocab_id
UNION ALL
SELECT
    sm.synset_id                                                            AS src_synset_id,
    CASE WHEN s.synset1id = sm.synset_id THEN s.synset2id ELSE s.synset1id END AS dst_synset_id,
    'metonym_of'                                                            AS relation,
    NULL                                                                    AS weight,
    NULL                                                                    AS bridge_id
FROM synset_metonyms sm
JOIN syntagms s ON s.syntagm_id = sm.metonym_syntagm_id
UNION ALL
SELECT
    pa.synset_id   AS src_synset_id,
    pb.synset_id   AS dst_synset_id,
    'antonym_of'   AS relation,
    NULL           AS weight,
    NULL           AS bridge_id
FROM property_antonyms pant
JOIN property_vocab_curated pa ON pa.vocab_id = pant.vocab_id_a
JOIN property_vocab_curated pb ON pb.vocab_id = pant.vocab_id_b
UNION ALL
SELECT
    mb.topic_synset_id   AS src_synset_id,
    mb.vehicle_synset_id AS dst_synset_id,
    'metaphor_link'      AS relation,
    mj.confidence        AS weight,
    mb.bridge_id         AS bridge_id
FROM metaphor_bridges mb
JOIN metaphor_judgments mj ON mj.bridge_id = mb.bridge_id
WHERE mj.label = 'live';
```

- [ ] **Step 2: Verify SCHEMA.sql is still valid SQL by applying to a fresh in-memory DB**

```bash
data-pipeline/.venv/bin/python -c "
import sqlite3
from pathlib import Path
ddl = Path('data-pipeline/SCHEMA.sql').read_text()
conn = sqlite3.connect(':memory:')
conn.executescript(ddl)
tables = [r[0] for r in conn.execute(\"SELECT name FROM sqlite_master WHERE type='table' ORDER BY name\")]
views = [r[0] for r in conn.execute(\"SELECT name FROM sqlite_master WHERE type='view' ORDER BY name\")]
assert 'metaphor_bridges' in tables, tables
assert 'metaphor_bridge_steps' in tables, tables
assert 'metaphor_judgments' in tables, tables
assert 'graph_edges' in views, views
print('SCHEMA.sql applies cleanly; new tables + view present.')
"
```

Expected: prints `SCHEMA.sql applies cleanly; new tables + view present.`

- [ ] **Step 3: Run full project test suite once more**

```bash
data-pipeline/.venv/bin/python -m pytest data-pipeline/scripts/ -q
```

Expected: all tests pass.

- [ ] **Step 4: Commit**

```bash
git add data-pipeline/SCHEMA.sql
git commit -m "schema(metaphor-graph): add metaphor_bridges + steps + judgments + graph_edges view

Keeps SCHEMA.sql in sync with the DDL emitted by metaphor_graph.py
apply_schema() / apply_graph_view(). Fresh DB rebuilds (restore_db.sh +
import_raw.sh) will now include the metaphor-graph layer."
```

---

## Self-Review (already performed)

**Spec coverage:**

| Spec requirement | Task | Status |
|---|---|---|
| metaphor_bridges table | Task 2 | ✓ |
| metaphor_bridge_steps table | Task 2 | ✓ |
| metaphor_judgments table | Task 2 | ✓ |
| FK referential integrity | Task 3 | ✓ |
| path_hash idempotency mechanism | Task 1 | ✓ |
| Pre-snapped insert path | Task 4 | ✓ |
| Raw-string insert path | Task 6 | ✓ |
| Single-string concept snapper | Task 5 | ✓ |
| Judgment recorder | Task 7 | ✓ |
| graph_edges VIEW (has_property/metonym/antonym/metaphor_link) | Task 8 | ✓ |
| Live-only filter on metaphor_link | Task 8 | ✓ |
| SCHEMA.sql parity | Task 9 | ✓ |
| Multi-judge UNIQUE constraint | Task 7 | ✓ |
| Idempotent re-apply | Task 2, 8 | ✓ |
| Eyeballer integration | OUT OF SCOPE — separate plan |
| Cascade modification to emit bridges | OUT OF SCOPE — separate plan |
| Completion algorithm | OUT OF SCOPE per spec |
| Embedding-fallback snap stage | DEFERRED — exact+morphological for v1 (Task 5 docs this) |
| Antonym source migration | NOT NEEDED — view JOINs through property_antonyms |

**Placeholder scan:** None. Every step has concrete code, exact file paths, exact commands, and exact expected outputs. No "TBD" / "implement later" / "handle edge cases" / "similar to" patterns.

**Type consistency:** Function signatures verified across tasks:
- `compute_path_hash(list[str]) -> str` — Task 1, used Task 4, 6
- `apply_schema(conn) -> None` — Task 2, used Task 3, 4, 5, 6, 7, 8
- `snap_concept_string(conn, text) -> str | None` — Task 5, used Task 6
- `insert_bridge(conn, *, topic_synset_id, vehicle_synset_id, proposer, proposed_at, path, rationale=None, ...)` — Task 4, used Task 8
- `insert_bridge_with_raw_path(conn, *, ..., raw_path, ...)` — Task 6
- `record_judgment(conn, *, bridge_id, label, judged_by, judged_at, confidence=None, notes=None) -> int` — Task 7, used Task 8
- `apply_graph_view(conn) -> None` — Task 8

All callers use the keyword-only arguments declared by the callees. No drift.

---

## Plan complete

Saved to `docs/superpowers/plans/2026-05-28-metaphor-graph-schema.md`.

**Execution options:**

1. **Subagent-Driven (recommended)** — I dispatch a fresh subagent per task, two-stage review (spec compliance, then code quality) between tasks. Continuous execution; you can interject corrections at any point.
2. **Inline Execution** — I execute tasks in this session using executing-plans, with checkpoints for you to review.

Which approach?
