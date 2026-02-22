"""Tests for build_antonyms.py — antonym pair detection via attribute relations."""
import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))


def make_antonym_db(tmp_path):
    """Create DB with relations (type 60) + vocabulary for antonym detection."""
    db_path = tmp_path / "antonym_test.db"
    conn = sqlite3.connect(str(db_path))
    conn.executescript("""
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
        CREATE TABLE relations (
            source_synset TEXT NOT NULL,
            target_synset TEXT NOT NULL,
            relation_type TEXT NOT NULL
        );
        CREATE TABLE property_vocab_curated (
            vocab_id INTEGER PRIMARY KEY,
            synset_id TEXT NOT NULL,
            lemma TEXT NOT NULL,
            pos TEXT NOT NULL,
            polysemy INTEGER NOT NULL,
            UNIQUE(synset_id)
        );

        -- Attribute noun "temperature" (synset t1)
        INSERT INTO synsets VALUES ('t1', 'n', 'degree of hotness');

        -- Adjective synsets linked to attribute noun via relation_type 60
        INSERT INTO synsets VALUES ('a1', 'a', 'having high temperature');
        INSERT INTO synsets VALUES ('a2', 'a', 'having low temperature');
        INSERT INTO lemmas VALUES ('hot', 'a1');
        INSERT INTO lemmas VALUES ('cold', 'a2');

        -- Attribute relations: a1 -> t1 (hot -> temperature), a2 -> t1 (cold -> temperature)
        INSERT INTO relations VALUES ('a1', 't1', '60');
        INSERT INTO relations VALUES ('a2', 't1', '60');

        -- Both are in the curated vocabulary
        INSERT INTO property_vocab_curated VALUES (1, 'a1', 'hot', 'a', 1);
        INSERT INTO property_vocab_curated VALUES (2, 'a2', 'cold', 'a', 1);

        -- A third adjective NOT in vocabulary (should be excluded)
        INSERT INTO synsets VALUES ('a3', 'a', 'warm-ish');
        INSERT INTO lemmas VALUES ('lukewarm', 'a3');
        INSERT INTO relations VALUES ('a3', 't1', '60');
    """)
    conn.commit()
    return db_path, conn


def test_build_antonyms_finds_pairs(tmp_path):
    """Adjectives sharing an attribute noun are detected as antonym pairs."""
    from build_antonyms import build_antonym_table

    db_path, conn = make_antonym_db(tmp_path)
    try:
        count = build_antonym_table(conn)
    finally:
        conn.close()

    # hot <-> cold (both in vocabulary, share attribute t1)
    conn = sqlite3.connect(str(db_path))
    try:
        rows = conn.execute(
            "SELECT vocab_id_a, vocab_id_b FROM property_antonyms ORDER BY vocab_id_a, vocab_id_b"
        ).fetchall()
    finally:
        conn.close()

    # Bidirectional: (1,2) and (2,1)
    assert (1, 2) in rows
    assert (2, 1) in rows
    assert count == 1  # 1 unique pair


def test_build_antonyms_excludes_non_vocabulary(tmp_path):
    """Synsets not in property_vocab_curated are excluded from antonym pairs."""
    from build_antonyms import build_antonym_table

    db_path, conn = make_antonym_db(tmp_path)
    try:
        build_antonym_table(conn)
    finally:
        conn.close()

    conn = sqlite3.connect(str(db_path))
    try:
        rows = conn.execute("SELECT * FROM property_antonyms").fetchall()
    finally:
        conn.close()

    # Only hot <-> cold, not lukewarm (a3 not in vocabulary)
    assert len(rows) == 2  # bidirectional


def test_build_antonyms_creates_table(tmp_path):
    """property_antonyms table is created with correct schema."""
    from build_antonyms import build_antonym_table

    db_path, conn = make_antonym_db(tmp_path)
    try:
        build_antonym_table(conn)
    finally:
        conn.close()

    conn = sqlite3.connect(str(db_path))
    try:
        cursor = conn.execute("PRAGMA table_info(property_antonyms)")
        columns = {row[1] for row in cursor.fetchall()}
    finally:
        conn.close()

    assert "vocab_id_a" in columns
    assert "vocab_id_b" in columns


# --- Cluster antonym tests ---

def make_cluster_antonym_db(tmp_path):
    """Create DB with property_antonyms + vocab_clusters for cluster antonym lifting."""
    db_path = tmp_path / "cluster_ant_test.db"
    conn = sqlite3.connect(str(db_path))
    conn.executescript("""
        CREATE TABLE property_antonyms (
            vocab_id_a INTEGER NOT NULL,
            vocab_id_b INTEGER NOT NULL,
            PRIMARY KEY (vocab_id_a, vocab_id_b)
        );
        CREATE TABLE vocab_clusters (
            vocab_id         INTEGER PRIMARY KEY,
            cluster_id       INTEGER NOT NULL,
            is_representative INTEGER NOT NULL DEFAULT 0,
            is_singleton     INTEGER NOT NULL DEFAULT 0
        );

        -- vocab 1 ("hot") in cluster 1, vocab 5 ("warm") also in cluster 1
        -- vocab 2 ("cold") in cluster 2, vocab 6 ("chilly") also in cluster 2
        INSERT INTO vocab_clusters VALUES (1, 1, 1, 0);
        INSERT INTO vocab_clusters VALUES (5, 1, 0, 0);
        INSERT INTO vocab_clusters VALUES (2, 2, 1, 0);
        INSERT INTO vocab_clusters VALUES (6, 2, 0, 0);
        INSERT INTO vocab_clusters VALUES (3, 3, 1, 1);  -- singleton "bright"

        -- Antonym pairs at vocab level: hot<->cold, warm<->chilly
        INSERT INTO property_antonyms VALUES (1, 2);
        INSERT INTO property_antonyms VALUES (2, 1);
        INSERT INTO property_antonyms VALUES (5, 6);
        INSERT INTO property_antonyms VALUES (6, 5);
    """)
    conn.commit()
    return db_path, conn


def test_cluster_antonyms_lifts_to_clusters(tmp_path):
    """Vocab-level antonym pairs are lifted to cluster-level pairs."""
    from build_antonyms import build_cluster_antonym_table

    db_path, conn = make_cluster_antonym_db(tmp_path)
    try:
        count = build_cluster_antonym_table(conn)
    finally:
        conn.close()

    conn = sqlite3.connect(str(db_path))
    try:
        rows = conn.execute(
            "SELECT cluster_id_a, cluster_id_b FROM cluster_antonyms "
            "ORDER BY cluster_id_a, cluster_id_b"
        ).fetchall()
    finally:
        conn.close()

    # hot(cluster 1) <-> cold(cluster 2) — deduplicated from both vocab pairs
    assert (1, 2) in rows
    assert (2, 1) in rows
    assert len(rows) == 2  # bidirectional, but deduplicated
    assert count == 1  # 1 unique pair


def test_cluster_antonyms_creates_table(tmp_path):
    """cluster_antonyms table has correct schema."""
    from build_antonyms import build_cluster_antonym_table

    db_path, conn = make_cluster_antonym_db(tmp_path)
    try:
        build_cluster_antonym_table(conn)
    finally:
        conn.close()

    conn = sqlite3.connect(str(db_path))
    try:
        cursor = conn.execute("PRAGMA table_info(cluster_antonyms)")
        columns = {row[1] for row in cursor.fetchall()}
    finally:
        conn.close()

    assert "cluster_id_a" in columns
    assert "cluster_id_b" in columns


def test_cluster_antonyms_empty_when_no_antonyms(tmp_path):
    """No crash when property_antonyms is empty."""
    from build_antonyms import build_cluster_antonym_table

    db_path = tmp_path / "empty_test.db"
    conn = sqlite3.connect(str(db_path))
    conn.executescript("""
        CREATE TABLE property_antonyms (
            vocab_id_a INTEGER NOT NULL,
            vocab_id_b INTEGER NOT NULL,
            PRIMARY KEY (vocab_id_a, vocab_id_b)
        );
        CREATE TABLE vocab_clusters (
            vocab_id         INTEGER PRIMARY KEY,
            cluster_id       INTEGER NOT NULL,
            is_representative INTEGER NOT NULL DEFAULT 0,
            is_singleton     INTEGER NOT NULL DEFAULT 0
        );
    """)
    conn.commit()

    try:
        count = build_cluster_antonym_table(conn)
    finally:
        conn.close()

    assert count == 0
