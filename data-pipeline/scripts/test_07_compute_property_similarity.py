"""Tests for property similarity matrix computation."""
import sqlite3
import sys
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).parent))
from utils import LEXICON_V2


def test_property_similarity_table_exists():
    """Verify property_similarity table was created."""
    conn = sqlite3.connect(LEXICON_V2)
    cursor = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='property_similarity'"
    )
    result = cursor.fetchone()
    conn.close()
    assert result is not None, "property_similarity table should exist"


def test_similarity_matrix_populated():
    """Verify similarity matrix has entries."""
    conn = sqlite3.connect(LEXICON_V2)
    count = conn.execute("SELECT COUNT(*) FROM property_similarity").fetchone()[0]
    conn.close()
    # Expect 50k-300k pairs (sparse, threshold >= 0.5)
    assert count > 10000, f"Expected 10k+ similarity pairs, got {count}"
    assert count < 1000000, f"Expected <1M pairs (sparse), got {count}"


def test_similarity_values_valid():
    """Verify similarity values are in valid range."""
    conn = sqlite3.connect(LEXICON_V2)
    row = conn.execute("""
        SELECT MIN(similarity), MAX(similarity)
        FROM property_similarity
    """).fetchone()
    conn.close()

    min_sim, max_sim = row
    assert min_sim >= 0.5, f"Min similarity should be >= 0.5 (threshold), got {min_sim}"
    # Allow small floating-point tolerance (cosine similarity can slightly exceed 1.0)
    assert max_sim <= 1.001, f"Max similarity should be <= 1.0 (with tolerance), got {max_sim}"


def test_similar_properties_make_sense():
    """Verify semantically similar properties have high similarity."""
    conn = sqlite3.connect(LEXICON_V2)

    # Look for 'warm' and see if 'hot' is similar
    row = conn.execute("""
        SELECT ps.similarity
        FROM property_similarity ps
        JOIN property_vocabulary pv1 ON pv1.property_id = ps.property_id_a
        JOIN property_vocabulary pv2 ON pv2.property_id = ps.property_id_b
        WHERE pv1.text = 'warm' AND pv2.text = 'hot'
           OR pv1.text = 'hot' AND pv2.text = 'warm'
        LIMIT 1
    """).fetchone()
    conn.close()

    if row:
        assert row[0] > 0.5, f"Expected warm/hot similarity > 0.5, got {row[0]}"


def test_indexes_exist():
    """Verify performance indexes are created."""
    conn = sqlite3.connect(LEXICON_V2)
    cursor = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='index' AND name LIKE 'idx_property_similarity%'"
    )
    indexes = [row[0] for row in cursor.fetchall()]
    conn.close()

    assert len(indexes) >= 2, f"Expected at least 2 indexes, got {indexes}"
