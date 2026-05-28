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

    def test_antonym_bidirectional_fan_out_preserved(self):
        """property_antonyms stores both (a,b) and (b,a); the view passes both
        through. Consumers must DISTINCT if they want undirected edges."""
        conn = _conn_with_full_sources()
        apply_graph_view(conn)
        _seed_synsets(conn, "hot-a-1", "cold-a-1")
        conn.execute("INSERT INTO property_vocab_curated VALUES (1, 'hot-a-1', 'hot', 'a', 1)")
        conn.execute("INSERT INTO property_vocab_curated VALUES (2, 'cold-a-1', 'cold', 'a', 1)")
        conn.execute("INSERT INTO property_antonyms VALUES (1, 2)")
        conn.execute("INSERT INTO property_antonyms VALUES (2, 1)")
        rows = conn.execute(
            "SELECT src_synset_id, dst_synset_id FROM graph_edges WHERE relation='antonym_of'"
        ).fetchall()
        assert ("hot-a-1", "cold-a-1") in rows
        assert ("cold-a-1", "hot-a-1") in rows

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


class TestSchemaSqlParity:
    """Pin the Python METAPHOR_GRAPH_DDL constant to the canonical SCHEMA.sql.

    Both must produce structurally identical tables, indexes, and views. A
    column added or dropped in one but not the other would silently diverge
    test fixtures from fresh DB rebuilds via import_raw.sh / restore_db.sh.
    """

    def _apply_schema_sql(self) -> sqlite3.Connection:
        """Apply the full SCHEMA.sql to a fresh in-memory DB."""
        schema_sql = Path(
            "/home/agent/projects/metaforge/data-pipeline/SCHEMA.sql"
        ).read_text()
        conn = sqlite3.connect(":memory:")
        conn.executescript(schema_sql)
        return conn

    def _apply_python_ddl(self) -> sqlite3.Connection:
        """Apply METAPHOR_GRAPH_DDL + GRAPH_EDGES_VIEW_DDL on top of the
        minimal upstream tables the view depends on."""
        conn = _conn_with_full_sources()
        apply_graph_view(conn)
        return conn

    def _describe(self, conn: sqlite3.Connection, name: str) -> str:
        """Canonical CREATE statement from sqlite_master."""
        row = conn.execute(
            "SELECT sql FROM sqlite_master WHERE name = ?",
            (name,),
        ).fetchone()
        return row[0] if row else ""

    def test_metaphor_bridges_ddl_matches(self):
        sql_conn = self._apply_schema_sql()
        py_conn = self._apply_python_ddl()
        # Normalise whitespace so cosmetic formatting differences don't fail
        # the test; structural content must match.
        sql_def = " ".join(self._describe(sql_conn, "metaphor_bridges").split())
        py_def = " ".join(self._describe(py_conn, "metaphor_bridges").split())
        assert sql_def == py_def, f"SCHEMA.sql vs Python DDL diverged on metaphor_bridges:\nSQL: {sql_def}\nPY:  {py_def}"

    def test_metaphor_bridge_steps_ddl_matches(self):
        sql_conn = self._apply_schema_sql()
        py_conn = self._apply_python_ddl()
        sql_def = " ".join(self._describe(sql_conn, "metaphor_bridge_steps").split())
        py_def = " ".join(self._describe(py_conn, "metaphor_bridge_steps").split())
        assert sql_def == py_def

    def test_metaphor_judgments_ddl_matches(self):
        sql_conn = self._apply_schema_sql()
        py_conn = self._apply_python_ddl()
        sql_def = " ".join(self._describe(sql_conn, "metaphor_judgments").split())
        py_def = " ".join(self._describe(py_conn, "metaphor_judgments").split())
        assert sql_def == py_def

    def test_graph_edges_view_ddl_matches(self):
        sql_conn = self._apply_schema_sql()
        py_conn = self._apply_python_ddl()
        sql_def = " ".join(self._describe(sql_conn, "graph_edges").split())
        py_def = " ".join(self._describe(py_conn, "graph_edges").split())
        assert sql_def == py_def
