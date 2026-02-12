"""Tests for property similarity matrix computation."""
import importlib
import sqlite3
import struct
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).parent))
from utils import LEXICON_V2, EMBEDDING_DIM

# Import module with numeric prefix
sim_module = importlib.import_module("07_compute_property_similarity")


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


# Unit tests for compute_similarity_matrix and store_similarities functions


def test_compute_similarity_matrix_identical_vectors():
    """Verify identical vectors have similarity 1.0."""
    embeddings = np.array([[1.0, 0.0, 0.0], [1.0, 0.0, 0.0]], dtype=np.float32)
    similarity = sim_module.compute_similarity_matrix(embeddings)

    # Both vectors identical -> similarity should be 1.0
    assert similarity[0, 1] == pytest.approx(1.0, abs=1e-6)
    assert similarity[1, 0] == pytest.approx(1.0, abs=1e-6)


def test_compute_similarity_matrix_orthogonal_vectors():
    """Verify orthogonal vectors have similarity 0.0."""
    embeddings = np.array([[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]], dtype=np.float32)
    similarity = sim_module.compute_similarity_matrix(embeddings)

    # Orthogonal vectors -> similarity should be 0.0
    assert similarity[0, 1] == pytest.approx(0.0, abs=1e-6)
    assert similarity[1, 0] == pytest.approx(0.0, abs=1e-6)


def test_compute_similarity_matrix_zero_vector():
    """Verify zero vector doesn't cause division by zero."""
    embeddings = np.array([[0.0, 0.0, 0.0], [1.0, 0.0, 0.0]], dtype=np.float32)
    similarity = sim_module.compute_similarity_matrix(embeddings)

    # Should not raise, zero vector gets normalised to zero
    assert not np.isnan(similarity).any()
    assert not np.isinf(similarity).any()


def test_store_similarities_symmetric_pairs():
    """Verify store_similarities writes both (a,b) and (b,a) pairs."""
    # Create in-memory DB with property_vocabulary table
    conn = sqlite3.connect(":memory:")
    conn.executescript("""
        CREATE TABLE property_vocabulary (
            property_id INTEGER PRIMARY KEY,
            text TEXT NOT NULL
        );
        INSERT INTO property_vocabulary (property_id, text) VALUES (1, 'test1'), (2, 'test2');
    """)

    # Create similarity table
    sim_module.create_similarity_table(conn)

    # Create a simple similarity matrix: two properties with high similarity
    property_ids = [1, 2]
    similarity = np.array([[1.0, 0.8], [0.8, 1.0]], dtype=np.float32)

    # Store with threshold 0.5
    unique_count = sim_module.store_similarities(conn, property_ids, similarity, threshold=0.5)

    # Verify unique count (should be 1 unique pair)
    assert unique_count == 1, f"Expected 1 unique pair, got {unique_count}"

    # Verify both (1,2) and (2,1) are stored
    rows = conn.execute(
        "SELECT property_id_a, property_id_b, similarity FROM property_similarity ORDER BY property_id_a, property_id_b"
    ).fetchall()
    conn.close()

    assert len(rows) == 2, f"Expected 2 rows (symmetric), got {len(rows)}"
    assert rows[0] == (1, 2, pytest.approx(0.8, abs=1e-6))
    assert rows[1] == (2, 1, pytest.approx(0.8, abs=1e-6))
