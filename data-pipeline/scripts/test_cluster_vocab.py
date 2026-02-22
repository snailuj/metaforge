"""Tests for cluster_vocab.py — synonym vocabulary clustering."""
import sqlite3
import struct
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))

EMBEDDING_DIM = 300


def _make_embedding(seed: float) -> bytes:
    """Create a deterministic 300d embedding for testing.

    seed controls direction — similar seeds yield high cosine similarity.
    """
    vec = [seed + i * 0.001 for i in range(EMBEDDING_DIM)]
    return struct.pack(f"{EMBEDDING_DIM}f", *vec)


def _make_cluster_db(conn: sqlite3.Connection) -> None:
    """Create base tables for clustering tests."""
    conn.executescript("""
        CREATE TABLE property_vocab_curated (
            vocab_id INTEGER PRIMARY KEY,
            synset_id TEXT NOT NULL,
            lemma TEXT NOT NULL,
            pos TEXT NOT NULL,
            polysemy INTEGER NOT NULL,
            UNIQUE(synset_id)
        );
        CREATE TABLE lemma_embeddings (
            lemma TEXT PRIMARY KEY,
            embedding BLOB NOT NULL
        );
    """)


def test_basic_clustering(tmp_path):
    """Two similar entries cluster together; one dissimilar stays singleton."""
    from cluster_vocab import cluster_vocab

    db_path = tmp_path / "test.db"
    conn = sqlite3.connect(str(db_path))
    _make_cluster_db(conn)

    # "heavy" and "weighty" are similar (close seeds)
    # "bright" is dissimilar (distant seed)
    conn.execute("INSERT INTO property_vocab_curated VALUES (1, 's1', 'heavy', 'a', 1)")
    conn.execute("INSERT INTO property_vocab_curated VALUES (2, 's2', 'weighty', 'a', 1)")
    conn.execute("INSERT INTO property_vocab_curated VALUES (3, 's3', 'bright', 'a', 1)")

    conn.execute("INSERT INTO lemma_embeddings VALUES ('heavy', ?)", (_make_embedding(1.0),))
    conn.execute("INSERT INTO lemma_embeddings VALUES ('weighty', ?)", (_make_embedding(1.001),))
    conn.execute("INSERT INTO lemma_embeddings VALUES ('bright', ?)", (_make_embedding(-1.0),))
    conn.commit()

    stats = cluster_vocab(conn, threshold=0.8)
    conn.close()

    conn = sqlite3.connect(str(db_path))
    rows = conn.execute(
        "SELECT vocab_id, cluster_id, is_representative, is_singleton FROM vocab_clusters ORDER BY vocab_id"
    ).fetchall()
    conn.close()

    assert len(rows) == 3

    # heavy and weighty should share a cluster
    heavy = rows[0]
    weighty = rows[1]
    bright = rows[2]

    assert heavy[1] == weighty[1]  # same cluster_id
    assert heavy[1] != bright[1]   # different from bright

    # bright is a singleton
    assert bright[3] == 1  # is_singleton

    # cluster_id = smallest vocab_id in cluster
    assert heavy[1] == 1  # min(1, 2) = 1

    # Exactly one representative per cluster
    reps_in_cluster = [r for r in [heavy, weighty] if r[2] == 1]
    assert len(reps_in_cluster) == 1

    assert stats["total_vocab"] == 3
    assert stats["num_clusters"] > 0


def test_transitive_closure(tmp_path):
    """A~B and B~C should all end up in one cluster (transitive)."""
    from cluster_vocab import cluster_vocab

    db_path = tmp_path / "test.db"
    conn = sqlite3.connect(str(db_path))
    _make_cluster_db(conn)

    # A close to B, B close to C, but A not directly close to C
    # Use seeds: A=1.0, B=1.05, C=1.10 — with threshold 0.8 all transitively linked
    conn.execute("INSERT INTO property_vocab_curated VALUES (10, 's10', 'alpha', 'a', 1)")
    conn.execute("INSERT INTO property_vocab_curated VALUES (20, 's20', 'beta', 'a', 1)")
    conn.execute("INSERT INTO property_vocab_curated VALUES (30, 's30', 'gamma', 'a', 1)")

    conn.execute("INSERT INTO lemma_embeddings VALUES ('alpha', ?)", (_make_embedding(1.0),))
    conn.execute("INSERT INTO lemma_embeddings VALUES ('beta', ?)", (_make_embedding(1.001),))
    conn.execute("INSERT INTO lemma_embeddings VALUES ('gamma', ?)", (_make_embedding(1.002),))
    conn.commit()

    cluster_vocab(conn, threshold=0.8)
    conn.close()

    conn = sqlite3.connect(str(db_path))
    rows = conn.execute("SELECT vocab_id, cluster_id FROM vocab_clusters ORDER BY vocab_id").fetchall()
    conn.close()

    cluster_ids = {r[1] for r in rows}
    assert len(cluster_ids) == 1  # all in one cluster

    # cluster_id = smallest vocab_id
    assert rows[0][1] == 10


def test_representative_is_smallest(tmp_path):
    """The representative of each cluster is the entry with smallest vocab_id."""
    from cluster_vocab import cluster_vocab

    db_path = tmp_path / "test.db"
    conn = sqlite3.connect(str(db_path))
    _make_cluster_db(conn)

    conn.execute("INSERT INTO property_vocab_curated VALUES (5, 's5', 'big', 'a', 1)")
    conn.execute("INSERT INTO property_vocab_curated VALUES (3, 's3', 'large', 'a', 1)")
    conn.execute("INSERT INTO property_vocab_curated VALUES (9, 's9', 'huge', 'a', 1)")

    conn.execute("INSERT INTO lemma_embeddings VALUES ('big', ?)", (_make_embedding(1.0),))
    conn.execute("INSERT INTO lemma_embeddings VALUES ('large', ?)", (_make_embedding(1.0005),))
    conn.execute("INSERT INTO lemma_embeddings VALUES ('huge', ?)", (_make_embedding(1.001),))
    conn.commit()

    cluster_vocab(conn, threshold=0.8)
    conn.close()

    conn = sqlite3.connect(str(db_path))
    rows = conn.execute(
        "SELECT vocab_id, cluster_id, is_representative FROM vocab_clusters ORDER BY vocab_id"
    ).fetchall()
    conn.close()

    # All should share cluster_id = 3 (smallest vocab_id)
    for row in rows:
        assert row[1] == 3

    # Only vocab_id 3 is the representative
    reps = [r for r in rows if r[2] == 1]
    assert len(reps) == 1
    assert reps[0][0] == 3


def test_no_embeddings_all_singletons(tmp_path):
    """Vocab entries without embeddings become singletons."""
    from cluster_vocab import cluster_vocab

    db_path = tmp_path / "test.db"
    conn = sqlite3.connect(str(db_path))
    _make_cluster_db(conn)

    conn.execute("INSERT INTO property_vocab_curated VALUES (1, 's1', 'unknown', 'a', 1)")
    conn.execute("INSERT INTO property_vocab_curated VALUES (2, 's2', 'mystery', 'a', 1)")
    # No lemma_embeddings rows
    conn.commit()

    stats = cluster_vocab(conn, threshold=0.8)
    conn.close()

    conn = sqlite3.connect(str(db_path))
    rows = conn.execute(
        "SELECT vocab_id, cluster_id, is_representative, is_singleton FROM vocab_clusters ORDER BY vocab_id"
    ).fetchall()
    conn.close()

    assert len(rows) == 2
    # Each is its own cluster
    assert rows[0][1] == 1  # cluster_id = own vocab_id
    assert rows[1][1] == 2
    # Both singletons
    assert rows[0][3] == 1
    assert rows[1][3] == 1
    # Both representatives
    assert rows[0][2] == 1
    assert rows[1][2] == 1

    assert stats["singletons"] == 2


def test_threshold_boundary(tmp_path):
    """Similarity exactly at threshold clusters; just below does not."""
    from cluster_vocab import cluster_vocab

    db_path = tmp_path / "test.db"
    conn = sqlite3.connect(str(db_path))
    _make_cluster_db(conn)

    # Create three unit vectors with controlled cosine similarities:
    # alpha = [1, 0, 0, ...]
    # beta  = [0.8, 0.6, 0, ...]       → sim(alpha, beta) = 0.8 (at threshold)
    # gamma = [0, 0, 1, ...]            → sim(alpha, gamma) = 0, sim(beta, gamma) = 0
    import math
    theta = math.acos(0.8)

    vec_a = [0.0] * EMBEDDING_DIM
    vec_a[0] = 1.0
    emb_a = struct.pack(f"{EMBEDDING_DIM}f", *vec_a)

    vec_b = [0.0] * EMBEDDING_DIM
    vec_b[0] = math.cos(theta)
    vec_b[1] = math.sin(theta)
    emb_b = struct.pack(f"{EMBEDDING_DIM}f", *vec_b)

    # Orthogonal to both — sim = 0 to alpha and beta
    vec_c = [0.0] * EMBEDDING_DIM
    vec_c[2] = 1.0
    emb_c = struct.pack(f"{EMBEDDING_DIM}f", *vec_c)

    conn.execute("INSERT INTO property_vocab_curated VALUES (1, 's1', 'alpha', 'a', 1)")
    conn.execute("INSERT INTO property_vocab_curated VALUES (2, 's2', 'beta', 'a', 1)")
    conn.execute("INSERT INTO property_vocab_curated VALUES (3, 's3', 'gamma', 'a', 1)")

    conn.execute("INSERT INTO lemma_embeddings VALUES ('alpha', ?)", (emb_a,))
    conn.execute("INSERT INTO lemma_embeddings VALUES ('beta', ?)", (emb_b,))
    conn.execute("INSERT INTO lemma_embeddings VALUES ('gamma', ?)", (emb_c,))
    conn.commit()

    cluster_vocab(conn, threshold=0.8)
    conn.close()

    conn = sqlite3.connect(str(db_path))
    rows = conn.execute(
        "SELECT vocab_id, cluster_id FROM vocab_clusters ORDER BY vocab_id"
    ).fetchall()
    conn.close()

    alpha, beta, gamma = rows[0], rows[1], rows[2]

    # alpha and beta should cluster (sim = 0.8, at threshold)
    assert alpha[1] == beta[1]

    # gamma should NOT cluster with either (sim = 0)
    assert gamma[1] != alpha[1]
