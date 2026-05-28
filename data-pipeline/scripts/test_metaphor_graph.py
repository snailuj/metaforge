"""Tests for metaphor_graph.py — bridge schema, hash, snap, insert, judge, view."""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))

from metaphor_graph import compute_path_hash
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
