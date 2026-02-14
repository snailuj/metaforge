"""Tests for snap_properties.py — property-to-vocabulary snapping."""
import sqlite3
import struct
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))

EMBEDDING_DIM = 300


def _make_embedding(seed: float) -> bytes:
    """Create a deterministic 300d embedding for testing."""
    vec = [seed + i * 0.001 for i in range(EMBEDDING_DIM)]
    return struct.pack(f"{EMBEDDING_DIM}f", *vec)


def make_snap_db(tmp_path):
    """Create DB with vocabulary + property_vocabulary + synset_properties."""
    db_path = tmp_path / "snap_test.db"
    conn = sqlite3.connect(str(db_path))
    conn.executescript("""
        CREATE TABLE property_vocab_curated (
            vocab_id INTEGER PRIMARY KEY,
            synset_id TEXT NOT NULL,
            lemma TEXT NOT NULL,
            pos TEXT NOT NULL,
            polysemy INTEGER NOT NULL,
            UNIQUE(synset_id)
        );
        CREATE INDEX idx_vocab_lemma ON property_vocab_curated(lemma);

        CREATE TABLE property_vocabulary (
            property_id INTEGER PRIMARY KEY,
            text TEXT NOT NULL UNIQUE,
            embedding BLOB,
            is_oov INTEGER NOT NULL DEFAULT 0,
            source TEXT NOT NULL DEFAULT 'pilot'
        );

        CREATE TABLE synset_properties (
            synset_id TEXT NOT NULL,
            property_id INTEGER NOT NULL,
            PRIMARY KEY (synset_id, property_id)
        );

        -- Vocabulary entries
        INSERT INTO property_vocab_curated VALUES (1, 'vs1', 'warm', 'a', 1);
        INSERT INTO property_vocab_curated VALUES (2, 'vs2', 'cold', 'a', 1);
        INSERT INTO property_vocab_curated VALUES (3, 'vs3', 'luminous', 'a', 1);

        -- Existing properties from enrichment (free-form)
        INSERT INTO property_vocabulary VALUES (10, 'warm', NULL, 0, 'pilot');
        INSERT INTO property_vocabulary VALUES (11, 'chilly', NULL, 0, 'pilot');
        INSERT INTO property_vocabulary VALUES (12, 'luminous', NULL, 0, 'pilot');
        INSERT INTO property_vocabulary VALUES (13, 'xyzqwerty', NULL, 0, 'pilot');

        -- Synset 'abc' has properties: warm, chilly, luminous, xyzqwerty
        INSERT INTO synset_properties VALUES ('abc', 10);
        INSERT INTO synset_properties VALUES ('abc', 11);
        INSERT INTO synset_properties VALUES ('abc', 12);
        INSERT INTO synset_properties VALUES ('abc', 13);
    """)
    conn.commit()
    return db_path, conn


def test_snap_exact_match(tmp_path):
    """Properties matching a vocabulary lemma exactly snap via 'exact'."""
    from snap_properties import snap_properties

    db_path, conn = make_snap_db(tmp_path)
    try:
        result = snap_properties(conn, embedding_threshold=0.7)
    finally:
        conn.close()

    conn = sqlite3.connect(str(db_path))
    try:
        rows = conn.execute(
            "SELECT synset_id, vocab_id, snap_method FROM synset_properties_curated "
            "WHERE snap_method = 'exact'"
        ).fetchall()
    finally:
        conn.close()

    # "warm" and "luminous" match exactly
    assert len(rows) == 2
    vocab_ids = {r[1] for r in rows}
    assert 1 in vocab_ids  # warm
    assert 3 in vocab_ids  # luminous


def test_snap_drops_unmatched(tmp_path):
    """Properties with no match at any stage are dropped."""
    from snap_properties import snap_properties

    db_path, conn = make_snap_db(tmp_path)
    try:
        result = snap_properties(conn, embedding_threshold=0.7)
    finally:
        conn.close()

    # xyzqwerty should not appear — no exact, no morph, no embedding match
    conn = sqlite3.connect(str(db_path))
    try:
        rows = conn.execute(
            "SELECT * FROM synset_properties_curated WHERE vocab_id NOT IN (1, 2, 3)"
        ).fetchall()
    finally:
        conn.close()

    assert len(rows) == 0


def test_snap_result_stats(tmp_path):
    """snap_properties returns a stats dict with counts per stage."""
    from snap_properties import snap_properties

    _, conn = make_snap_db(tmp_path)
    try:
        result = snap_properties(conn, embedding_threshold=0.7)
    finally:
        conn.close()

    assert "exact" in result
    assert "dropped" in result
    assert result["exact"] >= 2  # warm + luminous


def test_snap_creates_table(tmp_path):
    """synset_properties_curated table is created with correct schema."""
    from snap_properties import snap_properties

    db_path, conn = make_snap_db(tmp_path)
    try:
        snap_properties(conn, embedding_threshold=0.7)
    finally:
        conn.close()

    conn = sqlite3.connect(str(db_path))
    try:
        cursor = conn.execute("PRAGMA table_info(synset_properties_curated)")
        columns = {row[1] for row in cursor.fetchall()}
    finally:
        conn.close()

    assert "synset_id" in columns
    assert "vocab_id" in columns
    assert "snap_method" in columns
    assert "snap_score" in columns


def test_snap_morphological_participle(tmp_path):
    """Participle 'flickering' snaps to vocabulary entry 'flicker' via morphological stage."""
    db_path = tmp_path / "morph_test.db"
    conn = sqlite3.connect(str(db_path))
    conn.executescript("""
        CREATE TABLE property_vocab_curated (
            vocab_id INTEGER PRIMARY KEY,
            synset_id TEXT NOT NULL,
            lemma TEXT NOT NULL,
            pos TEXT NOT NULL,
            polysemy INTEGER NOT NULL,
            UNIQUE(synset_id)
        );
        CREATE INDEX idx_vocab_lemma ON property_vocab_curated(lemma);

        CREATE TABLE property_vocabulary (
            property_id INTEGER PRIMARY KEY,
            text TEXT NOT NULL UNIQUE,
            embedding BLOB,
            is_oov INTEGER NOT NULL DEFAULT 0,
            source TEXT NOT NULL DEFAULT 'pilot'
        );

        CREATE TABLE synset_properties (
            synset_id TEXT NOT NULL,
            property_id INTEGER NOT NULL,
            PRIMARY KEY (synset_id, property_id)
        );

        -- Vocabulary has "flicker"
        INSERT INTO property_vocab_curated VALUES (1, 'vs1', 'flicker', 'v', 1);

        -- Extracted property is "flickering" (VBG form)
        INSERT INTO property_vocabulary VALUES (10, 'flickering', NULL, 0, 'pilot');
        INSERT INTO synset_properties VALUES ('abc', 10);
    """)
    conn.commit()

    from snap_properties import snap_properties

    try:
        result = snap_properties(conn, embedding_threshold=0.7)
    finally:
        conn.close()

    assert result["morphological"] >= 1

    conn = sqlite3.connect(str(db_path))
    try:
        rows = conn.execute(
            "SELECT vocab_id, snap_method FROM synset_properties_curated"
        ).fetchall()
    finally:
        conn.close()

    assert any(r[0] == 1 and r[1] == "morphological" for r in rows)
