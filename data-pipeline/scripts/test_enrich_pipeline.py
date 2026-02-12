"""Tests for enrich_pipeline.py — consolidated downstream enrichment pipeline.

All tests use in-memory SQLite — no real DB or FastText vectors needed.
"""
import json
import math
import sqlite3
import struct
import sys
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).parent))

from enrich_pipeline import (
    MAX_PROPERTIES_PER_SYNSET,
    SIMILARITY_CHUNK_SIZE,
    curate_properties,
    populate_synset_properties,
    compute_idf,
    compute_property_similarity,
    compute_synset_centroids,
    run_pipeline,
)
from utils import EMBEDDING_DIM


# --- Helpers ------------------------------------------------------------------

SCHEMA_SQL = """
CREATE TABLE synsets (
    synset_id TEXT PRIMARY KEY,
    pos TEXT NOT NULL,
    definition TEXT NOT NULL
);

CREATE TABLE lemmas (
    lemma TEXT NOT NULL,
    synset_id TEXT NOT NULL,
    PRIMARY KEY (lemma, synset_id)
);

CREATE TABLE property_vocabulary (
    property_id INTEGER PRIMARY KEY,
    text TEXT NOT NULL UNIQUE,
    embedding BLOB,
    is_oov INTEGER NOT NULL DEFAULT 0,
    source TEXT NOT NULL DEFAULT 'pilot',
    idf REAL
);

CREATE TABLE enrichment (
    synset_id TEXT PRIMARY KEY,
    model_used TEXT,
    extracted_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE synset_properties (
    synset_id TEXT NOT NULL,
    property_id INTEGER NOT NULL,
    PRIMARY KEY (synset_id, property_id)
);

CREATE TABLE property_similarity (
    property_id_a INTEGER NOT NULL,
    property_id_b INTEGER NOT NULL,
    similarity REAL NOT NULL,
    PRIMARY KEY (property_id_a, property_id_b)
);

CREATE TABLE synset_centroids (
    synset_id TEXT PRIMARY KEY,
    centroid BLOB NOT NULL,
    property_count INTEGER NOT NULL
);
"""


def _make_vec(*values) -> tuple:
    """Create a 300d vector with given initial values, rest zeros."""
    full = list(values) + [0.0] * (EMBEDDING_DIM - len(values))
    return tuple(full)


def _make_blob(*values) -> bytes:
    """Create a 300d embedding blob with given initial values, rest zeros."""
    vec = _make_vec(*values)
    return struct.pack(f"{EMBEDDING_DIM}f", *vec)


def _make_db() -> sqlite3.Connection:
    """Create an in-memory DB with the minimal schema for testing."""
    conn = sqlite3.connect(":memory:")
    conn.executescript(SCHEMA_SQL)
    return conn


def _make_enrichment_data():
    """Create minimal enrichment JSON structure."""
    return {
        "synsets": [
            {
                "id": "syn001",
                "lemma": "candle",
                "definition": "stick of wax with a wick",
                "pos": "n",
                "properties": ["warm", "flickering", "luminous"],
            },
            {
                "id": "syn002",
                "lemma": "storm",
                "definition": "violent weather condition",
                "pos": "n",
                "properties": ["loud", "violent", "dark-grey"],
            },
        ],
        "config": {"model": "test-model"},
    }


def _make_vectors():
    """Create fake FastText vectors dict."""
    return {
        "warm": _make_vec(1.0, 0.0, 0.0),
        "flickering": _make_vec(0.8, 0.2, 0.0),
        "luminous": _make_vec(0.9, 0.1, 0.0),
        "loud": _make_vec(0.0, 1.0, 0.0),
        "violent": _make_vec(0.0, 0.8, 0.2),
        # "dark-grey" is NOT in vocab — compound word
        "dark": _make_vec(0.0, 0.0, 1.0),
        "grey": _make_vec(0.1, 0.0, 0.9),
    }


# --- 1. curate_properties inserts with embeddings ----------------------------

def test_curate_properties_inserts():
    conn = _make_db()
    data = _make_enrichment_data()
    vectors = _make_vectors()

    count = curate_properties(conn, data, vectors)

    rows = conn.execute("SELECT text, embedding, is_oov FROM property_vocabulary").fetchall()
    texts = {r[0] for r in rows}

    assert "warm" in texts
    assert "flickering" in texts
    assert "luminous" in texts
    assert "loud" in texts
    assert "violent" in texts
    assert count == len(texts)

    # Verify embeddings are present for in-vocab words
    warm_row = conn.execute(
        "SELECT embedding, is_oov FROM property_vocabulary WHERE text = 'warm'"
    ).fetchone()
    assert warm_row[0] is not None
    assert warm_row[1] == 0


# --- 2. curate_properties OOV flagged ----------------------------------------

def test_curate_properties_oov_flagged():
    conn = _make_db()
    # Use a property not in vectors
    data = {
        "synsets": [
            {"id": "s1", "properties": ["xyznonexistent"]},
        ],
    }
    vectors = _make_vectors()

    curate_properties(conn, data, vectors)

    row = conn.execute(
        "SELECT is_oov, embedding FROM property_vocabulary WHERE text = 'xyznonexistent'"
    ).fetchone()
    assert row[0] == 1  # is_oov
    assert row[1] is None  # no embedding


# --- 3. curate_properties compound embedding ---------------------------------

def test_curate_properties_compound_embedding():
    conn = _make_db()
    data = {
        "synsets": [
            {"id": "s1", "properties": ["dark-grey"]},
        ],
    }
    vectors = _make_vectors()

    curate_properties(conn, data, vectors)

    row = conn.execute(
        "SELECT embedding, is_oov FROM property_vocabulary WHERE text = 'dark-grey'"
    ).fetchone()
    # Should have an averaged embedding from "dark" and "grey"
    assert row[0] is not None
    assert row[1] == 0

    # Verify the averaging: dark=(0,0,1) grey=(0.1,0,0.9) → avg=(0.05,0,0.95)
    values = struct.unpack(f"{EMBEDDING_DIM}f", row[0])
    assert abs(values[0] - 0.05) < 0.01
    assert abs(values[2] - 0.95) < 0.01


# --- 4. populate_synset_properties -------------------------------------------

def test_populate_synset_properties():
    conn = _make_db()
    data = _make_enrichment_data()
    vectors = _make_vectors()

    curate_properties(conn, data, vectors)
    count = populate_synset_properties(conn, data, "test-model")

    # Check junction table entries
    rows = conn.execute("SELECT synset_id, property_id FROM synset_properties").fetchall()
    assert len(rows) > 0
    assert count == len(rows)

    # Check enrichment entries
    enrichment = conn.execute("SELECT synset_id, model_used FROM enrichment").fetchall()
    assert len(enrichment) == 2
    models = {r[1] for r in enrichment}
    assert "test-model" in models

    # Check syn001 has its 3 properties
    syn001_props = conn.execute(
        "SELECT COUNT(*) FROM synset_properties WHERE synset_id = 'syn001'"
    ).fetchone()[0]
    assert syn001_props == 3


# --- 5. compute_idf values ---------------------------------------------------

def test_compute_idf_values():
    conn = _make_db()
    data = _make_enrichment_data()
    vectors = _make_vectors()

    curate_properties(conn, data, vectors)
    populate_synset_properties(conn, data, "test-model")
    compute_idf(conn)

    # N = 2 synsets. "warm" appears in 1 synset → IDF = log(2/1) ≈ 0.693
    row = conn.execute(
        "SELECT idf FROM property_vocabulary WHERE text = 'warm'"
    ).fetchone()
    assert row is not None
    assert abs(row[0] - math.log(2 / 1)) < 0.01

    # If a property appears in both synsets it doesn't here, but let's check
    # "violent" appears in 1 synset → IDF = log(2/1)
    row = conn.execute(
        "SELECT idf FROM property_vocabulary WHERE text = 'violent'"
    ).fetchone()
    assert abs(row[0] - math.log(2 / 1)) < 0.01


# --- 6. compute_property_similarity ------------------------------------------

def test_compute_property_similarity():
    conn = _make_db()
    data = _make_enrichment_data()
    vectors = _make_vectors()

    curate_properties(conn, data, vectors)

    # warm=(1,0,0) and flickering=(0.8,0.2,0) should be quite similar
    threshold = 0.5
    count = compute_property_similarity(conn, threshold=threshold)

    rows = conn.execute(
        "SELECT property_id_a, property_id_b, similarity FROM property_similarity"
    ).fetchall()

    # All stored pairs should be above threshold
    for _, _, sim in rows:
        assert sim >= threshold

    # warm and flickering should be stored
    warm_id = conn.execute(
        "SELECT property_id FROM property_vocabulary WHERE text = 'warm'"
    ).fetchone()[0]
    flicker_id = conn.execute(
        "SELECT property_id FROM property_vocabulary WHERE text = 'flickering'"
    ).fetchone()[0]

    pair = conn.execute(
        "SELECT similarity FROM property_similarity WHERE property_id_a = ? AND property_id_b = ?",
        (warm_id, flicker_id),
    ).fetchone()
    assert pair is not None
    assert pair[0] > 0.5


# --- 7. compute_synset_centroids ---------------------------------------------

def test_compute_synset_centroids():
    conn = _make_db()
    data = _make_enrichment_data()
    vectors = _make_vectors()

    curate_properties(conn, data, vectors)
    populate_synset_properties(conn, data, "test-model")
    count = compute_synset_centroids(conn)

    assert count == 2  # two synsets

    row = conn.execute(
        "SELECT centroid, property_count FROM synset_centroids WHERE synset_id = 'syn001'"
    ).fetchone()
    assert row is not None
    assert row[1] == 3  # warm, flickering, luminous

    # Verify centroid is the mean of warm, flickering, luminous embeddings
    centroid_vals = struct.unpack(f"{EMBEDDING_DIM}f", row[0])
    # warm=(1,0,0), flickering=(0.8,0.2,0), luminous=(0.9,0.1,0)
    expected_0 = (1.0 + 0.8 + 0.9) / 3  # 0.9
    expected_1 = (0.0 + 0.2 + 0.1) / 3  # 0.1
    assert abs(centroid_vals[0] - expected_0) < 0.01
    assert abs(centroid_vals[1] - expected_1) < 0.01


# --- 8. run_pipeline end-to-end ----------------------------------------------

def test_run_pipeline_end_to_end(tmp_path):
    """Mock FastText loading, verify full pipeline produces correct tables."""
    # Write enrichment JSON
    data = _make_enrichment_data()
    enrichment_file = tmp_path / "enrichment.json"
    enrichment_file.write_text(json.dumps(data))

    # Create DB with schema
    db_path = tmp_path / "test.db"
    conn = sqlite3.connect(str(db_path))
    conn.executescript(SCHEMA_SQL)
    conn.close()

    vectors = _make_vectors()

    with patch("enrich_pipeline.load_fasttext_vectors", return_value=vectors):
        stats = run_pipeline(str(db_path), str(enrichment_file), "dummy.vec")

    assert stats["properties_curated"] > 0
    assert stats["synset_links"] > 0
    assert stats["centroids"] == 2

    # Verify tables populated
    conn = sqlite3.connect(str(db_path))
    prop_count = conn.execute("SELECT COUNT(*) FROM property_vocabulary").fetchone()[0]
    sp_count = conn.execute("SELECT COUNT(*) FROM synset_properties").fetchone()[0]
    centroid_count = conn.execute("SELECT COUNT(*) FROM synset_centroids").fetchone()[0]
    conn.close()

    assert prop_count > 0
    assert sp_count > 0
    assert centroid_count == 2


# --- 9. curate_properties caps per synset ------------------------------------

def test_curate_properties_caps_per_synset():
    """Only MAX_PROPERTIES_PER_SYNSET properties per synset enter vocabulary."""
    conn = _make_db()
    # Generate 20 unique properties — all single words so they get embeddings
    props_20 = [f"prop{i}" for i in range(20)]
    data = {
        "synsets": [
            {"id": "s1", "properties": props_20},
        ],
    }
    # All 20 words in vectors so none are filtered by OOV
    vectors = {p: _make_vec(float(i)) for i, p in enumerate(props_20)}

    count = curate_properties(conn, data, vectors)

    assert count == MAX_PROPERTIES_PER_SYNSET


# --- 10. populate_synset_properties caps per synset --------------------------

def test_populate_synset_properties_caps_per_synset():
    """Junction table has at most MAX_PROPERTIES_PER_SYNSET rows per synset."""
    conn = _make_db()
    props_20 = [f"prop{i}" for i in range(20)]
    data = {
        "synsets": [
            {"id": "s1", "properties": props_20},
        ],
    }
    vectors = {p: _make_vec(float(i)) for i, p in enumerate(props_20)}

    curate_properties(conn, data, vectors)
    links = populate_synset_properties(conn, data, "test-model")

    row_count = conn.execute(
        "SELECT COUNT(*) FROM synset_properties WHERE synset_id = 's1'"
    ).fetchone()[0]

    assert links == MAX_PROPERTIES_PER_SYNSET
    assert row_count == MAX_PROPERTIES_PER_SYNSET


# --- 11. chunked similarity matches naive -----------------------------------

def _get_sim_pairs(conn):
    """Return set of ((id_a, id_b), similarity) from property_similarity."""
    rows = conn.execute(
        "SELECT property_id_a, property_id_b, similarity FROM property_similarity"
    ).fetchall()
    return {(a, b): round(s, 6) for a, b, s in rows}


def test_similarity_chunked_matches_naive():
    """Chunked computation (chunk_size=2) produces identical pairs to naive."""
    # Set up 5 properties with known embeddings
    conn = _make_db()
    props = ["alpha", "beta", "gamma", "delta", "epsilon"]
    vecs = {
        "alpha": _make_vec(1.0, 0.0, 0.0),
        "beta": _make_vec(0.9, 0.1, 0.0),
        "gamma": _make_vec(0.0, 1.0, 0.0),
        "delta": _make_vec(0.0, 0.9, 0.1),
        "epsilon": _make_vec(0.0, 0.0, 1.0),
    }
    data = {"synsets": [{"id": "s1", "properties": props}]}

    curate_properties(conn, data, vecs)

    # Run with default (large) chunk_size — effectively naive
    naive_count = compute_property_similarity(conn, threshold=0.5)
    naive_pairs = _get_sim_pairs(conn)

    # Run again with chunk_size=2 — forces multiple chunks
    chunked_count = compute_property_similarity(conn, threshold=0.5, chunk_size=2)
    chunked_pairs = _get_sim_pairs(conn)

    assert naive_count == chunked_count
    assert naive_pairs == chunked_pairs


# --- 12. similarity with chunk_size=1 (edge case) ---------------------------

def test_similarity_chunk_size_one():
    """chunk_size=1 is the extreme edge case — still produces correct pairs."""
    conn = _make_db()
    props = ["hot", "warm", "cold"]
    vecs = {
        "hot": _make_vec(1.0, 0.0, 0.0),
        "warm": _make_vec(0.9, 0.1, 0.0),
        "cold": _make_vec(-1.0, 0.0, 0.0),
    }
    data = {"synsets": [{"id": "s1", "properties": props}]}

    curate_properties(conn, data, vecs)

    # Run with chunk_size=1
    count = compute_property_similarity(conn, threshold=0.5, chunk_size=1)
    pairs = _get_sim_pairs(conn)

    # hot and warm should be similar (cosine > 0.5)
    hot_id = conn.execute(
        "SELECT property_id FROM property_vocabulary WHERE text = 'hot'"
    ).fetchone()[0]
    warm_id = conn.execute(
        "SELECT property_id FROM property_vocabulary WHERE text = 'warm'"
    ).fetchone()[0]

    assert (hot_id, warm_id) in pairs
    assert (warm_id, hot_id) in pairs
    assert pairs[(hot_id, warm_id)] > 0.5

    # cold should not be similar to hot or warm (cosine < 0.5)
    cold_id = conn.execute(
        "SELECT property_id FROM property_vocabulary WHERE text = 'cold'"
    ).fetchone()[0]
    assert (hot_id, cold_id) not in pairs
    assert (warm_id, cold_id) not in pairs

    assert count > 0
