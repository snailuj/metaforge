"""Tests for synset centroid computation."""
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
centroid_module = importlib.import_module("08_compute_synset_centroids")


def test_synset_centroids_table_exists():
    """Verify synset_centroids table was created."""
    conn = sqlite3.connect(LEXICON_V2)
    cursor = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='synset_centroids'"
    )
    result = cursor.fetchone()
    conn.close()
    assert result is not None, "synset_centroids table should exist"


def test_synset_centroids_populated():
    """Verify centroids computed for enriched synsets."""
    conn = sqlite3.connect(LEXICON_V2)

    # Count enriched synsets (those with properties)
    enriched_count = conn.execute(
        "SELECT COUNT(DISTINCT synset_id) FROM synset_properties"
    ).fetchone()[0]

    # Count centroids
    centroid_count = conn.execute(
        "SELECT COUNT(*) FROM synset_centroids"
    ).fetchone()[0]

    conn.close()

    # Every enriched synset with embeddings should have a centroid
    assert centroid_count > 0, "Expected at least some centroids"
    # Allow some gap for synsets whose properties are all OOV
    assert centroid_count >= enriched_count * 0.9, \
        f"Expected ~{enriched_count} centroids, got {centroid_count}"


def test_centroid_dimensions_correct():
    """Verify each centroid is 300 float32 values (1200 bytes)."""
    conn = sqlite3.connect(LEXICON_V2)
    row = conn.execute(
        "SELECT centroid FROM synset_centroids LIMIT 1"
    ).fetchone()
    conn.close()

    assert row is not None, "Expected at least one centroid"
    blob = row[0]
    expected_size = EMBEDDING_DIM * 4  # 300 * 4 bytes = 1200
    assert len(blob) == expected_size, \
        f"Expected {expected_size} bytes, got {len(blob)}"

    # Verify it decodes to valid floats
    values = struct.unpack(f'{EMBEDDING_DIM}f', blob)
    assert len(values) == EMBEDDING_DIM


def test_property_count_populated():
    """Verify property_count is set correctly."""
    conn = sqlite3.connect(LEXICON_V2)

    # Pick a synset and verify property_count matches actual count
    row = conn.execute("""
        SELECT sc.synset_id, sc.property_count,
               (SELECT COUNT(*) FROM synset_properties sp
                JOIN property_vocabulary pv ON pv.property_id = sp.property_id
                WHERE sp.synset_id = sc.synset_id
                AND pv.embedding IS NOT NULL) as actual_count
        FROM synset_centroids sc
        LIMIT 1
    """).fetchone()

    conn.close()

    assert row is not None, "Expected at least one centroid"
    synset_id, stored_count, actual_count = row
    assert stored_count == actual_count, \
        f"Synset {synset_id}: property_count={stored_count}, actual={actual_count}"


def test_centroid_index_exists():
    """Verify primary key index on synset_id."""
    conn = sqlite3.connect(LEXICON_V2)

    # synset_id is PRIMARY KEY so it's automatically indexed
    # Check the table schema
    cursor = conn.execute("PRAGMA table_info(synset_centroids)")
    columns = {row[1]: row[5] for row in cursor.fetchall()}  # name: pk
    conn.close()

    assert "synset_id" in columns, "synset_centroids should have synset_id column"
    assert columns["synset_id"] > 0, "synset_id should be primary key"


# Unit tests for _compute_centroid function


def test_compute_centroid_averages_vectors():
    """Verify _compute_centroid averages vectors correctly."""
    embeddings = [
        np.array([1.0, 0.0, 0.0], dtype=np.float32),
        np.array([0.0, 1.0, 0.0], dtype=np.float32),
    ]
    centroid = centroid_module._compute_centroid(embeddings)

    expected = np.array([0.5, 0.5, 0.0], dtype=np.float32)
    np.testing.assert_array_almost_equal(centroid, expected, decimal=6)


def test_compute_centroid_single_vector():
    """Verify _compute_centroid with single vector returns itself."""
    embeddings = [np.array([1.0, 2.0, 3.0], dtype=np.float32)]
    centroid = centroid_module._compute_centroid(embeddings)

    expected = np.array([1.0, 2.0, 3.0], dtype=np.float32)
    np.testing.assert_array_almost_equal(centroid, expected, decimal=6)
