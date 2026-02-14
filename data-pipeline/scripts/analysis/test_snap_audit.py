"""Tests for snap_audit.py — snap quality report."""
import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))


def make_audit_db(tmp_path):
    """Create a DB with synset_properties_curated for audit testing."""
    db_path = tmp_path / "audit_test.db"
    conn = sqlite3.connect(str(db_path))
    conn.executescript("""
        CREATE TABLE synset_properties_curated (
            synset_id TEXT NOT NULL,
            vocab_id INTEGER NOT NULL,
            snap_method TEXT NOT NULL,
            snap_score REAL,
            PRIMARY KEY (synset_id, vocab_id)
        );

        -- Synset s1: 3 properties (2 exact, 1 embedding)
        INSERT INTO synset_properties_curated VALUES ('s1', 1, 'exact', NULL);
        INSERT INTO synset_properties_curated VALUES ('s1', 2, 'exact', NULL);
        INSERT INTO synset_properties_curated VALUES ('s1', 3, 'embedding', 0.82);

        -- Synset s2: 1 property (morphological)
        INSERT INTO synset_properties_curated VALUES ('s2', 4, 'morphological', NULL);
    """)
    conn.commit()
    return db_path, conn


def test_snap_rate_report(tmp_path):
    """Report returns correct counts per snap method."""
    from snap_audit import compute_snap_rates

    _, conn = make_audit_db(tmp_path)
    try:
        rates = compute_snap_rates(conn)
    finally:
        conn.close()

    assert rates["exact"] == 2
    assert rates["morphological"] == 1
    assert rates["embedding"] == 1


def test_coverage_report(tmp_path):
    """Report returns per-synset property counts."""
    from snap_audit import compute_coverage

    _, conn = make_audit_db(tmp_path)
    try:
        coverage = compute_coverage(conn)
    finally:
        conn.close()

    assert coverage["total_synsets"] == 2
    assert coverage["with_3_plus"] == 1   # s1 has 3
    assert coverage["with_5_plus"] == 0
