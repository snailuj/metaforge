"""Tests for metaphor_graph.py — bridge schema, hash, snap, insert, judge, view."""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))

from metaphor_graph import compute_path_hash
from metaphor_graph import apply_schema
from datetime import datetime, timezone

from metaphor_graph import insert_bridge
from metaphor_graph import snap_concept_string
from metaphor_graph import insert_bridge_with_raw_path, BridgeSnapFailure


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


def _seed_synsets(conn: sqlite3.Connection, *ids: str) -> None:
    for sid in ids:
        conn.execute("INSERT INTO synsets VALUES (?, 'n', ?)", (sid, f"defn of {sid}"))


def _ts() -> str:
    return datetime(2026, 5, 28, tzinfo=timezone.utc).isoformat()


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
