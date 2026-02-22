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
            salience REAL NOT NULL DEFAULT 1.0,
            property_type TEXT,
            relation TEXT,
            PRIMARY KEY (synset_id, property_id)
        );

        CREATE TABLE vocab_clusters (
            vocab_id         INTEGER PRIMARY KEY,
            cluster_id       INTEGER NOT NULL,
            is_representative INTEGER NOT NULL DEFAULT 0,
            is_singleton     INTEGER NOT NULL DEFAULT 0
        );
        CREATE INDEX idx_vc_cluster ON vocab_clusters(cluster_id);

        -- Vocabulary entries
        INSERT INTO property_vocab_curated VALUES (1, 'vs1', 'warm', 'a', 1);
        INSERT INTO property_vocab_curated VALUES (2, 'vs2', 'cold', 'a', 1);
        INSERT INTO property_vocab_curated VALUES (3, 'vs3', 'luminous', 'a', 1);

        -- Clusters: warm(1) is singleton, cold(2) is singleton, luminous(3) is singleton
        INSERT INTO vocab_clusters VALUES (1, 1, 1, 1);
        INSERT INTO vocab_clusters VALUES (2, 2, 1, 1);
        INSERT INTO vocab_clusters VALUES (3, 3, 1, 1);

        -- Existing properties from enrichment (free-form)
        INSERT INTO property_vocabulary VALUES (10, 'warm', NULL, 0, 'pilot');
        INSERT INTO property_vocabulary VALUES (11, 'chilly', NULL, 0, 'pilot');
        INSERT INTO property_vocabulary VALUES (12, 'luminous', NULL, 0, 'pilot');
        INSERT INTO property_vocabulary VALUES (13, 'xyzqwerty', NULL, 0, 'pilot');

        -- Synset 'abc' has properties: warm, chilly, luminous, xyzqwerty
        INSERT INTO synset_properties VALUES ('abc', 10, 1.0, NULL, NULL);
        INSERT INTO synset_properties VALUES ('abc', 11, 1.0, NULL, NULL);
        INSERT INTO synset_properties VALUES ('abc', 12, 1.0, NULL, NULL);
        INSERT INTO synset_properties VALUES ('abc', 13, 1.0, NULL, NULL);
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
    assert "cluster_id" in columns
    assert "snap_method" in columns
    assert "snap_score" in columns


def test_snap_cluster_id_populated(tmp_path):
    """Each snapped row has the correct cluster_id from vocab_clusters."""
    from snap_properties import snap_properties

    db_path, conn = make_snap_db(tmp_path)
    try:
        snap_properties(conn, embedding_threshold=0.7)
    finally:
        conn.close()

    conn = sqlite3.connect(str(db_path))
    try:
        rows = conn.execute(
            "SELECT synset_id, vocab_id, cluster_id FROM synset_properties_curated"
        ).fetchall()
    finally:
        conn.close()

    # Each row's cluster_id should match its vocab_id (all singletons in this fixture)
    for sid, vid, cid in rows:
        assert cid == vid, f"cluster_id {cid} != vocab_id {vid} for synset {sid}"


def test_snap_cluster_dedup(tmp_path):
    """Two vocab entries in the same cluster snapped to the same synset produce one row."""
    from snap_properties import snap_properties

    db_path = tmp_path / "dedup_test.db"
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
            salience REAL NOT NULL DEFAULT 1.0,
            property_type TEXT,
            relation TEXT,
            PRIMARY KEY (synset_id, property_id)
        );

        CREATE TABLE vocab_clusters (
            vocab_id         INTEGER PRIMARY KEY,
            cluster_id       INTEGER NOT NULL,
            is_representative INTEGER NOT NULL DEFAULT 0,
            is_singleton     INTEGER NOT NULL DEFAULT 0
        );
        CREATE INDEX idx_vc_cluster ON vocab_clusters(cluster_id);

        -- "heavy" (id=1) and "weighty" (id=2) are in the same cluster (cluster_id=1)
        INSERT INTO property_vocab_curated VALUES (1, 'vs1', 'heavy', 'a', 1);
        INSERT INTO property_vocab_curated VALUES (2, 'vs2', 'weighty', 'a', 1);
        INSERT INTO vocab_clusters VALUES (1, 1, 1, 0);
        INSERT INTO vocab_clusters VALUES (2, 1, 0, 0);

        -- Synset 'abc' has both "heavy" and "weighty" as properties
        INSERT INTO property_vocabulary VALUES (10, 'heavy', NULL, 0, 'pilot');
        INSERT INTO property_vocabulary VALUES (11, 'weighty', NULL, 0, 'pilot');
        INSERT INTO synset_properties VALUES ('abc', 10, 1.0, NULL, NULL);
        INSERT INTO synset_properties VALUES ('abc', 11, 1.0, NULL, NULL);
    """)
    conn.commit()

    try:
        snap_properties(conn, embedding_threshold=0.7)
    finally:
        conn.close()

    conn = sqlite3.connect(str(db_path))
    try:
        rows = conn.execute(
            "SELECT synset_id, vocab_id, cluster_id FROM synset_properties_curated"
        ).fetchall()
    finally:
        conn.close()

    # Only one row: deduplication on (synset_id, cluster_id)
    assert len(rows) == 1
    assert rows[0][0] == "abc"
    assert rows[0][2] == 1  # cluster_id


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
            salience REAL NOT NULL DEFAULT 1.0,
            property_type TEXT,
            relation TEXT,
            PRIMARY KEY (synset_id, property_id)
        );

        CREATE TABLE vocab_clusters (
            vocab_id         INTEGER PRIMARY KEY,
            cluster_id       INTEGER NOT NULL,
            is_representative INTEGER NOT NULL DEFAULT 0,
            is_singleton     INTEGER NOT NULL DEFAULT 0
        );

        -- Vocabulary has "flicker"
        INSERT INTO property_vocab_curated VALUES (1, 'vs1', 'flicker', 'v', 1);
        INSERT INTO vocab_clusters VALUES (1, 1, 1, 1);

        -- Extracted property is "flickering" (VBG form)
        INSERT INTO property_vocabulary VALUES (10, 'flickering', NULL, 0, 'pilot');
        INSERT INTO synset_properties VALUES ('abc', 10, 1.0, NULL, NULL);
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


def test_snap_embedding_match(tmp_path):
    """Properties with similar embeddings snap via 'embedding' stage."""
    from snap_properties import snap_properties

    db_path = tmp_path / "emb_test.db"
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
            salience REAL NOT NULL DEFAULT 1.0,
            property_type TEXT,
            relation TEXT,
            PRIMARY KEY (synset_id, property_id)
        );

        CREATE TABLE vocab_clusters (
            vocab_id         INTEGER PRIMARY KEY,
            cluster_id       INTEGER NOT NULL,
            is_representative INTEGER NOT NULL DEFAULT 0,
            is_singleton     INTEGER NOT NULL DEFAULT 0
        );

        -- Vocabulary has "bright" with an embedding
        INSERT INTO property_vocab_curated VALUES (1, 'vs1', 'bright', 'a', 1);
        INSERT INTO property_vocab_curated VALUES (2, 'vs2', 'distant', 'a', 1);
        INSERT INTO vocab_clusters VALUES (1, 1, 1, 1);
        INSERT INTO vocab_clusters VALUES (2, 2, 1, 1);
    """)

    # "bright" vocab embedding
    bright_emb = _make_embedding(1.0)
    conn.execute(
        "INSERT INTO property_vocabulary VALUES (1, 'bright', ?, 0, 'pilot')",
        (bright_emb,),
    )
    # "distant" vocab embedding — very different seed
    distant_emb = _make_embedding(-1.0)
    conn.execute(
        "INSERT INTO property_vocabulary VALUES (2, 'distant', ?, 0, 'pilot')",
        (distant_emb,),
    )

    # Extracted property "radiant" with embedding very close to "bright"
    radiant_emb = _make_embedding(1.001)  # very close to bright's 1.0
    conn.execute(
        "INSERT INTO property_vocabulary VALUES (10, 'radiant', ?, 0, 'pilot')",
        (radiant_emb,),
    )
    conn.execute("INSERT INTO synset_properties VALUES ('abc', 10, 1.0, NULL, NULL)")
    conn.commit()

    try:
        result = snap_properties(conn, embedding_threshold=0.7)
    finally:
        conn.close()

    assert result["embedding"] >= 1

    conn = sqlite3.connect(str(db_path))
    try:
        rows = conn.execute(
            "SELECT vocab_id, snap_method, snap_score FROM synset_properties_curated"
        ).fetchall()
    finally:
        conn.close()

    assert len(rows) == 1
    assert rows[0][0] == 1  # matched to "bright", not "distant"
    assert rows[0][1] == "embedding"
    assert rows[0][2] is not None and rows[0][2] > 0.99  # very high similarity


def test_snap_accumulates_salience_for_same_cluster(tmp_path):
    """Two properties snapping to the same cluster accumulate their saliences."""
    from snap_properties import snap_properties

    db_path = tmp_path / "sal_test.db"
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
            salience REAL NOT NULL DEFAULT 1.0,
            property_type TEXT,
            relation TEXT,
            PRIMARY KEY (synset_id, property_id)
        );

        CREATE TABLE vocab_clusters (
            vocab_id         INTEGER PRIMARY KEY,
            cluster_id       INTEGER NOT NULL,
            is_representative INTEGER NOT NULL DEFAULT 0,
            is_singleton     INTEGER NOT NULL DEFAULT 0
        );
        CREATE INDEX idx_vc_cluster ON vocab_clusters(cluster_id);

        -- "heavy" (id=1) and "weighty" (id=2) are in the same cluster (cluster_id=1)
        INSERT INTO property_vocab_curated VALUES (1, 'vs1', 'heavy', 'a', 1);
        INSERT INTO property_vocab_curated VALUES (2, 'vs2', 'weighty', 'a', 1);
        INSERT INTO vocab_clusters VALUES (1, 1, 1, 0);
        INSERT INTO vocab_clusters VALUES (2, 1, 0, 0);

        -- Synset 'abc' has "heavy" (salience 0.9) and "weighty" (salience 0.8)
        INSERT INTO property_vocabulary VALUES (10, 'heavy', NULL, 0, 'pilot');
        INSERT INTO property_vocabulary VALUES (11, 'weighty', NULL, 0, 'pilot');
        INSERT INTO synset_properties VALUES ('abc', 10, 0.9, NULL, NULL);
        INSERT INTO synset_properties VALUES ('abc', 11, 0.8, NULL, NULL);
    """)
    conn.commit()

    try:
        snap_properties(conn, embedding_threshold=0.7)
    finally:
        conn.close()

    conn = sqlite3.connect(str(db_path))
    try:
        rows = conn.execute(
            "SELECT synset_id, cluster_id, salience_sum FROM synset_properties_curated"
        ).fetchall()
    finally:
        conn.close()

    # Only one row (dedup on cluster_id), salience_sum = 0.9 + 0.8 = 1.7
    assert len(rows) == 1
    assert rows[0][0] == "abc"
    assert rows[0][1] == 1  # cluster_id
    assert abs(rows[0][2] - 1.7) < 0.01


def test_snap_salience_sum_default_for_single_match(tmp_path):
    """A single property snapping to a cluster has salience_sum = its own salience."""
    from snap_properties import snap_properties

    db_path = tmp_path / "sal_single_test.db"
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
            salience REAL NOT NULL DEFAULT 1.0,
            property_type TEXT,
            relation TEXT,
            PRIMARY KEY (synset_id, property_id)
        );

        CREATE TABLE vocab_clusters (
            vocab_id         INTEGER PRIMARY KEY,
            cluster_id       INTEGER NOT NULL,
            is_representative INTEGER NOT NULL DEFAULT 0,
            is_singleton     INTEGER NOT NULL DEFAULT 0
        );
        CREATE INDEX idx_vc_cluster ON vocab_clusters(cluster_id);

        -- "warm" is a singleton cluster
        INSERT INTO property_vocab_curated VALUES (1, 'vs1', 'warm', 'a', 1);
        INSERT INTO vocab_clusters VALUES (1, 1, 1, 1);

        -- Synset 'abc' has "warm" with salience 0.85
        INSERT INTO property_vocabulary VALUES (10, 'warm', NULL, 0, 'pilot');
        INSERT INTO synset_properties VALUES ('abc', 10, 0.85, NULL, NULL);
    """)
    conn.commit()

    try:
        snap_properties(conn, embedding_threshold=0.7)
    finally:
        conn.close()

    conn = sqlite3.connect(str(db_path))
    try:
        rows = conn.execute(
            "SELECT synset_id, salience_sum FROM synset_properties_curated"
        ).fetchall()
    finally:
        conn.close()

    assert len(rows) == 1
    assert abs(rows[0][1] - 0.85) < 0.01


def test_snap_creates_salience_sum_column(tmp_path):
    """synset_properties_curated table includes salience_sum column."""
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

    assert "salience_sum" in columns
