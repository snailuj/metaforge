"""Tests for predict_concreteness.py — FastText concreteness regression."""
import sqlite3
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).parent))

from predict_concreteness import build_synset_embeddings, build_training_data


def _make_test_db():
    """In-memory DB with synsets, lemmas, and synset_concreteness."""
    conn = sqlite3.connect(":memory:")
    conn.executescript("""
        CREATE TABLE synsets (
            synset_id TEXT PRIMARY KEY, pos TEXT, definition TEXT
        );
        CREATE TABLE lemmas (
            lemma TEXT, synset_id TEXT, PRIMARY KEY (lemma, synset_id)
        );
        CREATE TABLE synset_concreteness (
            synset_id TEXT PRIMARY KEY,
            score REAL NOT NULL,
            source TEXT NOT NULL
        );

        INSERT INTO synsets VALUES ('100', 'n', 'a fruit');
        INSERT INTO synsets VALUES ('200', 'n', 'fairness');
        INSERT INTO synsets VALUES ('300', 'v', 'to move');

        INSERT INTO lemmas VALUES ('apple', '100');
        INSERT INTO lemmas VALUES ('fruit', '100');
        INSERT INTO lemmas VALUES ('justice', '200');
        INSERT INTO lemmas VALUES ('run', '300');
        INSERT INTO lemmas VALUES ('sprint', '300');
    """)
    conn.commit()
    return conn


def _make_vectors():
    """Fake FastText vectors — 4d for testing."""
    return {
        "apple":   (1.0, 0.0, 0.0, 0.0),
        "fruit":   (0.9, 0.1, 0.0, 0.0),
        "justice": (0.0, 0.0, 1.0, 0.0),
        "run":     (0.0, 1.0, 0.0, 0.0),
        "sprint":  (0.0, 0.8, 0.2, 0.0),
    }


def test_build_synset_embeddings_mean():
    conn = _make_test_db()
    vectors = _make_vectors()
    embeddings = build_synset_embeddings(conn, vectors)

    # synset 100 has apple + fruit → mean
    assert "100" in embeddings
    expected = np.array([(1.0 + 0.9) / 2, (0.0 + 0.1) / 2, 0.0, 0.0])
    np.testing.assert_allclose(embeddings["100"], expected, atol=1e-6)

    # synset 300 has run + sprint → mean
    assert "300" in embeddings
    expected = np.array([0.0, (1.0 + 0.8) / 2, (0.0 + 0.2) / 2, 0.0])
    np.testing.assert_allclose(embeddings["300"], expected, atol=1e-6)


def test_build_synset_embeddings_skips_oov():
    conn = _make_test_db()
    vectors = {"apple": (1.0, 0.0, 0.0, 0.0)}  # only apple, no fruit/justice/run/sprint
    embeddings = build_synset_embeddings(conn, vectors)

    assert "100" in embeddings  # apple covers synset 100
    assert "200" not in embeddings  # justice is OOV
    assert "300" not in embeddings  # run+sprint OOV


def test_build_training_data():
    conn = _make_test_db()
    # Add Brysbaert scores
    conn.executemany(
        "INSERT INTO synset_concreteness VALUES (?, ?, ?)",
        [("100", 4.82, "brysbaert"), ("200", 1.78, "brysbaert")],
    )
    conn.commit()

    vectors = _make_vectors()
    embeddings = build_synset_embeddings(conn, vectors)
    X, y, synset_ids = build_training_data(conn, embeddings)

    assert X.shape[0] == 2  # 2 scored synsets with embeddings
    assert X.shape[1] == 4  # 4d test vectors
    assert len(y) == 2
    assert len(synset_ids) == 2
    # Verify scores match
    idx_100 = synset_ids.index("100")
    assert y[idx_100] == pytest.approx(4.82)
    idx_200 = synset_ids.index("200")
    assert y[idx_200] == pytest.approx(1.78)


def test_build_training_data_skips_unembedded():
    conn = _make_test_db()
    conn.executemany(
        "INSERT INTO synset_concreteness VALUES (?, ?, ?)",
        [("100", 4.82, "brysbaert"), ("200", 1.78, "brysbaert")],
    )
    conn.commit()

    # Only apple in vectors — synset 200 (justice) has no embedding
    vectors = {"apple": (1.0, 0.0, 0.0, 0.0)}
    embeddings = build_synset_embeddings(conn, vectors)
    X, y, synset_ids = build_training_data(conn, embeddings)

    assert X.shape[0] == 1  # only synset 100
    assert "100" in synset_ids
    assert "200" not in synset_ids


def test_build_training_data_ignores_regression_source():
    """Only use Brysbaert ground truth, not previously predicted values."""
    conn = _make_test_db()
    conn.executemany(
        "INSERT INTO synset_concreteness VALUES (?, ?, ?)",
        [
            ("100", 4.82, "brysbaert"),
            ("200", 2.50, "fasttext_regression"),  # predicted — skip
        ],
    )
    conn.commit()

    vectors = _make_vectors()
    embeddings = build_synset_embeddings(conn, vectors)
    X, y, synset_ids = build_training_data(conn, embeddings)

    assert X.shape[0] == 1  # only brysbaert source
    assert "100" in synset_ids
    assert "200" not in synset_ids
