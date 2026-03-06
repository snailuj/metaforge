"""Tests for audit_physical_coverage.py."""
import json
import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))

from audit_physical_coverage import audit_physical_coverage, POS_THRESHOLDS


def _make_test_db():
    """Create in-memory DB with synsets, synset_properties, property_vocabulary."""
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE synsets (synset_id TEXT PRIMARY KEY, pos TEXT, definition TEXT)")
    conn.execute("CREATE TABLE property_vocabulary (property_id INTEGER PRIMARY KEY, text TEXT)")
    conn.execute("""CREATE TABLE synset_properties (
        synset_id TEXT, property_id INTEGER, salience REAL DEFAULT 1.0,
        property_type TEXT, relation TEXT,
        PRIMARY KEY (synset_id, property_id)
    )""")
    return conn


def _add_synset(conn, synset_id, pos, props):
    """Helper: add a synset with properties (list of (text, type) tuples)."""
    conn.execute("INSERT INTO synsets VALUES (?, ?, 'test')", (synset_id, pos))
    for i, (text, ptype) in enumerate(props):
        pid = abs(hash(f"{synset_id}_{text}")) % 1000000
        conn.execute("INSERT OR IGNORE INTO property_vocabulary VALUES (?, ?)", (pid, text))
        conn.execute("INSERT INTO synset_properties VALUES (?, ?, 1.0, ?, NULL)",
                     (synset_id, pid, ptype))


def test_noun_with_enough_physical_not_flagged():
    """Noun with >= 4 physical properties passes audit."""
    conn = _make_test_db()
    _add_synset(conn, "syn-rock", "n", [
        ("hard", "physical"), ("heavy", "physical"),
        ("solid", "physical"), ("rough", "physical"),
        ("ancient", "social"),
    ])
    result = audit_physical_coverage(conn)
    assert len(result["flagged"]) == 0


def test_noun_with_few_physical_flagged():
    """Noun with < 4 physical properties is flagged."""
    conn = _make_test_db()
    _add_synset(conn, "syn-justice", "n", [
        ("abstract", "emotional"), ("balanced", "behaviour"),
        ("impartial", "social"), ("cold", "physical"),
    ])
    result = audit_physical_coverage(conn)
    assert len(result["flagged"]) == 1
    assert result["flagged"][0]["synset_id"] == "syn-justice"
    assert result["flagged"][0]["physical_count"] == 1


def test_verb_threshold_is_two():
    """Verb with < 2 physical properties is flagged."""
    conn = _make_test_db()
    _add_synset(conn, "syn-run", "v", [
        ("fast", "behaviour"), ("rhythmic", "behaviour"),
        ("sweaty", "physical"),
    ])
    result = audit_physical_coverage(conn)
    assert len(result["flagged"]) == 1
    assert result["flagged"][0]["physical_count"] == 1


def test_verb_with_enough_physical_not_flagged():
    """Verb with >= 2 physical properties passes."""
    conn = _make_test_db()
    _add_synset(conn, "syn-run", "v", [
        ("fast", "behaviour"), ("sweaty", "physical"), ("loud", "physical"),
    ])
    result = audit_physical_coverage(conn)
    assert len(result["flagged"]) == 0


def test_adjective_threshold_is_two():
    """Adjective with < 2 physical properties is flagged."""
    conn = _make_test_db()
    _add_synset(conn, "syn-bright", "a", [
        ("cheerful", "emotional"), ("optimistic", "emotional"),
    ])
    result = audit_physical_coverage(conn)
    assert len(result["flagged"]) == 1


def test_audit_returns_summary_stats():
    """Audit result includes total, flagged count, and per-POS breakdown."""
    conn = _make_test_db()
    _add_synset(conn, "syn-rock", "n", [
        ("hard", "physical"), ("heavy", "physical"),
        ("solid", "physical"), ("rough", "physical"),
    ])
    _add_synset(conn, "syn-justice", "n", [("fair", "social")])
    result = audit_physical_coverage(conn)
    assert result["total_audited"] == 2
    assert result["total_flagged"] == 1
    assert result["by_pos"]["n"]["flagged"] == 1


def test_synsets_without_type_annotation_flagged():
    """Synsets with NULL property_type (v1 data) are flagged — no type = 0 physical."""
    conn = _make_test_db()
    conn.execute("INSERT INTO synsets VALUES ('syn-old', 'n', 'test')")
    conn.execute("INSERT INTO property_vocabulary VALUES (1, 'hot')")
    conn.execute("INSERT INTO synset_properties VALUES ('syn-old', 1, 1.0, NULL, NULL)")
    result = audit_physical_coverage(conn)
    assert len(result["flagged"]) == 1
