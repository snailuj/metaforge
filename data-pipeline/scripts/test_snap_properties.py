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


def test_snap_all_stages_integration(tmp_path):
    """All four stages (exact / morphological / embedding / drop) in a single run
    produce a coherent result. Regression bar for the streaming two-pass refactor:
    Stages 1-2 must drain the synset-property cursor without loading embedding blobs,
    and Stage 3 must fetch embeddings only for the residue.
    """
    from snap_properties import snap_properties

    db_path = tmp_path / "all_stages.db"
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

        -- Vocab: warm, flicker, bright, distant
        INSERT INTO property_vocab_curated VALUES (1, 'vs1', 'warm',     'a', 1);
        INSERT INTO property_vocab_curated VALUES (2, 'vs2', 'flicker',  'v', 1);
        INSERT INTO property_vocab_curated VALUES (3, 'vs3', 'bright',   'a', 1);
        INSERT INTO property_vocab_curated VALUES (4, 'vs4', 'distant',  'a', 1);
        INSERT INTO vocab_clusters VALUES (1, 1, 1, 1);
        INSERT INTO vocab_clusters VALUES (2, 2, 1, 1);
        INSERT INTO vocab_clusters VALUES (3, 3, 1, 1);
        INSERT INTO vocab_clusters VALUES (4, 4, 1, 1);
    """)

    # Vocab embeddings (stage 3 needs these — only for bright/distant)
    conn.execute("INSERT INTO property_vocabulary VALUES (3, 'bright', ?, 0, 'pilot')",
                 (_make_embedding(1.0),))
    conn.execute("INSERT INTO property_vocabulary VALUES (4, 'distant', ?, 0, 'pilot')",
                 (_make_embedding(-1.0),))

    # Extracted properties: exact, morph, embedding-near-bright, dropped (no embedding)
    conn.execute("INSERT INTO property_vocabulary VALUES (10, 'warm', NULL, 0, 'pilot')")
    conn.execute("INSERT INTO property_vocabulary VALUES (11, 'flickering', NULL, 0, 'pilot')")
    conn.execute("INSERT INTO property_vocabulary VALUES (12, 'radiant', ?, 0, 'pilot')",
                 (_make_embedding(1.001),))   # near 'bright'
    conn.execute("INSERT INTO property_vocabulary VALUES (13, 'xyzqwerty', NULL, 0, 'pilot')")  # dropped

    # Two synsets exercise each property
    conn.execute("INSERT INTO synset_properties VALUES ('s_a', 10, 0.9, NULL, NULL)")  # exact
    conn.execute("INSERT INTO synset_properties VALUES ('s_a', 11, 0.8, NULL, NULL)")  # morph
    conn.execute("INSERT INTO synset_properties VALUES ('s_a', 12, 0.7, NULL, NULL)")  # embedding
    conn.execute("INSERT INTO synset_properties VALUES ('s_a', 13, 0.6, NULL, NULL)")  # dropped
    conn.execute("INSERT INTO synset_properties VALUES ('s_b', 12, 0.5, NULL, NULL)")  # embedding (shared pid)
    conn.commit()

    try:
        result = snap_properties(conn, embedding_threshold=0.7)
    finally:
        conn.close()

    # Stats: 1 exact, 1 morph, 2 embedding, 1 dropped
    assert result["exact"] == 1
    assert result["morphological"] == 1
    assert result["embedding"] == 2
    assert result["dropped"] == 1

    conn = sqlite3.connect(str(db_path))
    try:
        rows = conn.execute(
            "SELECT synset_id, vocab_id, snap_method, salience_sum "
            "FROM synset_properties_curated ORDER BY synset_id, vocab_id"
        ).fetchall()
    finally:
        conn.close()

    by_key = {(sid, vid): (method, sal) for sid, vid, method, sal in rows}
    assert by_key[("s_a", 1)][0] == "exact"
    assert abs(by_key[("s_a", 1)][1] - 0.9) < 0.01
    assert by_key[("s_a", 2)][0] == "morphological"
    assert abs(by_key[("s_a", 2)][1] - 0.8) < 0.01
    assert by_key[("s_a", 3)][0] == "embedding"
    assert abs(by_key[("s_a", 3)][1] - 0.7) < 0.01
    assert by_key[("s_b", 3)][0] == "embedding"
    assert abs(by_key[("s_b", 3)][1] - 0.5) < 0.01
    # vocab_id 4 (distant) and the dropped 'xyzqwerty' must not appear
    assert ("s_a", 4) not in by_key
    assert ("s_b", 4) not in by_key


def test_snap_skips_jsonl_write_for_in_memory_db(tmp_path, caplog, monkeypatch):
    """For an in-memory connection, PRAGMA database_list returns an empty path —
    we must NOT silently write snap_dropped.jsonl into the caller's cwd. Log a
    WARNING and skip the write.
    """
    import logging
    import os

    from snap_properties import snap_properties

    # Run from inside tmp_path so any unintended cwd-write is detectable.
    monkeypatch.chdir(tmp_path)

    conn = sqlite3.connect(":memory:")
    conn.executescript("""
        CREATE TABLE property_vocab_curated (
            vocab_id INTEGER PRIMARY KEY,
            synset_id TEXT NOT NULL,
            lemma TEXT NOT NULL,
            pos TEXT NOT NULL,
            polysemy INTEGER NOT NULL,
            UNIQUE(synset_id)
        );
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
        INSERT INTO property_vocab_curated VALUES (1, 'vs1', 'warm', 'a', 1);
        INSERT INTO vocab_clusters VALUES (1, 1, 1, 1);
        -- 'unmatchable' -> drops at no_embedding stage.
        INSERT INTO property_vocabulary VALUES (10, 'unmatchable', NULL, 0, 'pilot');
        INSERT INTO synset_properties VALUES ('abc', 10, 1.0, NULL, NULL);
    """)
    conn.commit()

    with caplog.at_level(logging.WARNING, logger="snap_properties"):
        try:
            snap_properties(conn, embedding_threshold=0.7)
        finally:
            conn.close()

    # No .jsonl file in cwd or anywhere we can see.
    cwd_files = os.listdir(tmp_path)
    assert "snap_dropped.jsonl" not in cwd_files, (
        f"in-memory DB must not write JSONL; cwd contains: {cwd_files}"
    )

    warning_messages = [
        r.message for r in caplog.records if r.levelno == logging.WARNING
    ]
    assert any(
        "in-memory" in m and "snap_dropped" in m for m in warning_messages
    ), f"expected WARNING about in-memory skip; got: {warning_messages}"


def test_snap_streams_dropped_props_to_jsonl(tmp_path):
    """Dropped properties stream to snap_dropped.jsonl (one record per line),
    not buffered in memory and dumped as a single JSON document. This caps
    memory at V2 scale where the dropped list could otherwise reach ~50MB.
    """
    import json as _json

    from snap_properties import snap_properties

    db_path, conn = make_snap_db(tmp_path)  # 'xyzqwerty' will be dropped
    try:
        snap_properties(conn, embedding_threshold=0.7)
    finally:
        conn.close()

    jsonl_path = tmp_path / "snap_dropped.jsonl"
    assert jsonl_path.exists(), (
        f"expected {jsonl_path} (one JSON object per line); not found. "
        f"tmp_path contents: {list(tmp_path.iterdir())}"
    )
    # Old buffered .json file must NOT be created.
    json_path = tmp_path / "snap_dropped.json"
    assert not json_path.exists(), (
        "snap_dropped.json (single-document) must not be created — "
        "the streaming JSONL replaces it"
    )

    with open(jsonl_path) as f:
        lines = [line for line in f if line.strip()]

    assert len(lines) >= 1
    for line in lines:
        record = _json.loads(line)  # each line is a complete JSON object
        assert "reason" in record
        assert "synset_id" in record
        assert "text" in record


def test_snap_logs_warning_with_per_reason_breakdown_on_drops(tmp_path, caplog):
    """When properties are dropped, log a WARNING with per-reason breakdown
    (zero_norm / no_embedding / below_threshold) so operators can distinguish
    'vocab embeddings broken' from 'OOV'.
    """
    import logging

    from snap_properties import snap_properties

    db_path, conn = make_snap_db(tmp_path)  # 'xyzqwerty' will be dropped (no_embedding)

    with caplog.at_level(logging.WARNING, logger="snap_properties"):
        try:
            snap_properties(conn, embedding_threshold=0.7)
        finally:
            conn.close()

    warning_messages = [
        r.message for r in caplog.records if r.levelno == logging.WARNING
    ]
    assert any(
        "dropped" in m.lower() and "no_embedding" in m for m in warning_messages
    ), (
        "expected WARNING with per-reason 'no_embedding' breakdown; "
        f"got: {warning_messages}"
    )


def test_snap_vocab_by_lemma_lowest_vocab_id_wins_on_collision(tmp_path):
    """When two property_vocab_curated rows share a lemma (e.g. POS variants),
    snap deterministically picks the lowest vocab_id. Without ORDER BY, SQLite
    returns rows in unspecified order and last-write-wins picks whichever the
    engine returned last — unstable across rebuilds.
    """
    from snap_properties import snap_properties

    db_path = tmp_path / "tiebreak_test.db"
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

        -- Two vocab rows share lemma 'fast' (POS variants).
        -- Insert in reverse vocab_id order so an unordered SELECT might return
        -- vid=7 last. The fix is to ORDER BY vocab_id ASC so vid=3 wins.
        INSERT INTO property_vocab_curated VALUES (7, 'vs7', 'fast', 'v', 1);
        INSERT INTO property_vocab_curated VALUES (3, 'vs3', 'fast', 'a', 1);
        INSERT INTO vocab_clusters VALUES (3, 3, 1, 1);
        INSERT INTO vocab_clusters VALUES (7, 7, 1, 1);

        INSERT INTO property_vocabulary VALUES (10, 'fast', NULL, 0, 'pilot');
        INSERT INTO synset_properties VALUES ('abc', 10, 1.0, NULL, NULL);
    """)
    conn.commit()

    try:
        snap_properties(conn, embedding_threshold=0.7)
    finally:
        conn.close()

    conn = sqlite3.connect(str(db_path))
    try:
        rows = conn.execute(
            "SELECT vocab_id FROM synset_properties_curated WHERE synset_id='abc'"
        ).fetchall()
    finally:
        conn.close()

    assert len(rows) == 1
    assert rows[0][0] == 3, (
        f"expected lowest vocab_id (3) on lemma collision, got {rows[0][0]} — "
        "tie-breaker is unstable"
    )


def test_snap_stats_count_per_link_not_per_unique_key(tmp_path):
    """stats counts must be per-link, not per-unique-(sid, cluster_id) key.

    When two distinct properties snap to the SAME (sid, cluster_id) via different
    methods, both should be counted in their respective stage buckets — otherwise
    the summary line ('Snapped N property links') under-reports against the input
    cursor and the per-stage counts disagree with stats['dropped'] (which is
    already per-link).
    """
    from snap_properties import snap_properties

    db_path = tmp_path / "perlink_test.db"
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

        -- 'flicker' (vid=1) and 'sparkle' (vid=2) share cluster_id=1.
        INSERT INTO property_vocab_curated VALUES (1, 'vs1', 'flicker', 'v', 1);
        INSERT INTO property_vocab_curated VALUES (2, 'vs2', 'sparkle', 'v', 1);
        INSERT INTO vocab_clusters VALUES (1, 1, 1, 0);
        INSERT INTO vocab_clusters VALUES (2, 1, 0, 0);

        -- 'sparkle' (exact) and 'flickering' (morph) both land on (abc, 1).
        INSERT INTO property_vocabulary VALUES (10, 'flickering', NULL, 0, 'pilot');
        INSERT INTO property_vocabulary VALUES (11, 'sparkle',    NULL, 0, 'pilot');

        -- One additional truly-dropped property.
        INSERT INTO property_vocabulary VALUES (12, 'xyzqwerty',  NULL, 0, 'pilot');

        INSERT INTO synset_properties VALUES ('abc', 10, 1.0, NULL, NULL);
        INSERT INTO synset_properties VALUES ('abc', 11, 1.0, NULL, NULL);
        INSERT INTO synset_properties VALUES ('abc', 12, 1.0, NULL, NULL);
    """)
    conn.commit()

    try:
        result = snap_properties(conn, embedding_threshold=0.7)
    finally:
        conn.close()

    # Three input links: 1 exact (sparkle), 1 morph (flickering->flicker), 1 dropped.
    total = result["exact"] + result["morphological"] + result["embedding"] + result["dropped"]
    assert total == 3, (
        f"expected per-link count to sum to 3 input links; got {total}: {result}"
    )
    assert result["exact"] == 1
    assert result["morphological"] == 1
    assert result["dropped"] == 1


def test_snap_accumulator_upgrades_method_when_higher_quality_match_arrives_later(tmp_path):
    """When a morphological match populates a (sid, cluster_id) key first, then an
    exact match for the same key arrives, the accumulator must upgrade snap_method
    to 'exact' (higher quality wins) AND accumulate salience from both contributions.

    Quality order: exact > morphological > embedding.
    """
    from snap_properties import snap_properties

    db_path = tmp_path / "upgrade_test.db"
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

        -- 'flicker' (vid=1) and 'sparkle' (vid=2) share cluster_id=1.
        -- Property 'flickering' will hit Stage 2 (morph) and snap to flicker.
        -- Property 'sparkle' will hit Stage 1 (exact) and snap to sparkle.
        -- Both end up keyed on (sid='abc', cluster_id=1), and Pass 1 walks
        -- synset_properties in property_id order, so the morph match for
        -- 'flickering' (pid=10) is inserted FIRST, then the exact match for
        -- 'sparkle' (pid=11) hits the same accumulator key second.
        INSERT INTO property_vocab_curated VALUES (1, 'vs1', 'flicker', 'v', 1);
        INSERT INTO property_vocab_curated VALUES (2, 'vs2', 'sparkle', 'v', 1);
        INSERT INTO vocab_clusters VALUES (1, 1, 1, 0);
        INSERT INTO vocab_clusters VALUES (2, 1, 0, 0);

        INSERT INTO property_vocabulary VALUES (10, 'flickering', NULL, 0, 'pilot');
        INSERT INTO property_vocabulary VALUES (11, 'sparkle',    NULL, 0, 'pilot');

        INSERT INTO synset_properties VALUES ('abc', 10, 0.4, NULL, NULL);
        INSERT INTO synset_properties VALUES ('abc', 11, 0.6, NULL, NULL);
    """)
    conn.commit()

    try:
        snap_properties(conn, embedding_threshold=0.7)
    finally:
        conn.close()

    conn = sqlite3.connect(str(db_path))
    try:
        rows = conn.execute(
            "SELECT synset_id, cluster_id, snap_method, salience_sum "
            "FROM synset_properties_curated"
        ).fetchall()
    finally:
        conn.close()

    # Single row (deduped on cluster_id), method upgraded to 'exact', salience accumulated.
    assert len(rows) == 1
    assert rows[0][0] == "abc"
    assert rows[0][1] == 1  # cluster_id
    assert rows[0][2] == "exact", (
        f"expected upgraded snap_method='exact', got {rows[0][2]!r} — "
        "the accumulator silently kept the first-inserted morphological method"
    )
    assert abs(rows[0][3] - 1.0) < 0.01  # 0.4 + 0.6


def test_main_basicConfig_surfaces_log_info(tmp_path):
    """`python snap_properties.py --db ...` must surface the log.info summary
    line. Without basicConfig in main(), the root logger swallows it.
    """
    import subprocess
    import sys

    db_path, conn = make_snap_db(tmp_path)
    conn.close()

    script_path = Path(__file__).parent / "snap_properties.py"
    result = subprocess.run(
        [sys.executable, str(script_path), "--db", str(db_path), "--threshold", "0.7"],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )

    # Combined stdout + stderr (basicConfig writes to stderr by default).
    combined = result.stdout + result.stderr
    assert result.returncode == 0, f"snap CLI exited {result.returncode}: {combined}"
    assert "Snapped" in combined, (
        f"expected 'Snapped' summary line via log.info; got:\nstdout={result.stdout!r}\n"
        f"stderr={result.stderr!r}"
    )


def test_snap_continues_when_dropped_jsonl_write_fails(tmp_path, caplog, monkeypatch):
    """If opening (or writing) snap_dropped.jsonl raises OSError (e.g. PermissionError
    or ENOSPC), snap must not crash — drops are diagnostic-only. Log a WARNING,
    set the JSONL stream to None, and continue. Canonical writes to
    synset_properties_curated must still complete.
    """
    import logging

    from snap_properties import snap_properties

    db_path, conn = make_snap_db(tmp_path)  # 'xyzqwerty' triggers a drop

    real_open = open

    def boom_open(path, mode="r", *a, **kw):
        if str(path).endswith("snap_dropped.jsonl") and "w" in mode:
            raise PermissionError("simulated read-only filesystem")
        return real_open(path, mode, *a, **kw)

    monkeypatch.setattr("builtins.open", boom_open)

    with caplog.at_level(logging.WARNING, logger="snap_properties"):
        try:
            result = snap_properties(conn, embedding_threshold=0.7)
        finally:
            conn.close()

    # snap_dropped.jsonl must NOT exist on disk (open was blocked).
    assert not (tmp_path / "snap_dropped.jsonl").exists()

    # WARNING naming the path + diagnostic-only reassurance.
    warning_messages = [
        r.message for r in caplog.records if r.levelno == logging.WARNING
    ]
    assert any(
        "snap_dropped" in m and "diagnostic" in m.lower() for m in warning_messages
    ), f"expected WARNING about diagnostic-only drop write failure; got: {warning_messages}"

    # Canonical writes still succeeded — exact + luminous matches present.
    conn = sqlite3.connect(str(db_path))
    try:
        rows = conn.execute(
            "SELECT vocab_id, snap_method FROM synset_properties_curated"
        ).fetchall()
    finally:
        conn.close()
    assert len(rows) >= 2, (
        f"canonical synset_properties_curated rows must still be committed; got {rows}"
    )


def test_snap_re_raises_operational_error_when_not_missing_table(tmp_path):
    """OperationalError sub-cases other than 'no such table' (locked DB, disk-IO,
    missing-column, readonly) must propagate — the WARNING about vocab_clusters
    is misleading for those cases. Only the 'no such table' message degrades
    gracefully.
    """
    from snap_properties import snap_properties

    db_path, conn = make_snap_db(tmp_path)

    # Wrap conn so the SELECT against vocab_clusters raises a non-missing-table
    # OperationalError (simulate locked DB or schema drift).
    class FailingConn:
        def __init__(self, real):
            self._real = real

        def __getattr__(self, name):
            return getattr(self._real, name)

        def execute(self, sql, *args, **kw):
            if "vocab_clusters" in sql and sql.lstrip().upper().startswith("SELECT"):
                raise sqlite3.OperationalError("database is locked")
            return self._real.execute(sql, *args, **kw)

    proxy = FailingConn(conn)
    try:
        with pytest.raises(sqlite3.OperationalError, match="locked"):
            snap_properties(proxy, embedding_threshold=0.7)
    finally:
        conn.close()


def test_snap_logs_warning_when_vocab_clusters_table_missing(tmp_path, caplog):
    """Missing vocab_clusters table is recoverable — log WARNING, do not silently swallow."""
    import logging

    from snap_properties import snap_properties

    db_path = tmp_path / "no_clusters.db"
    conn = sqlite3.connect(str(db_path))
    # Same fixture as make_snap_db but WITHOUT the vocab_clusters table — exercise the
    # degraded path where snapping falls back to vocab_id-only dedup.
    conn.executescript("""
        CREATE TABLE property_vocab_curated (
            vocab_id INTEGER PRIMARY KEY,
            synset_id TEXT NOT NULL,
            lemma TEXT NOT NULL,
            pos TEXT NOT NULL,
            polysemy INTEGER NOT NULL,
            UNIQUE(synset_id)
        );
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
        INSERT INTO property_vocab_curated VALUES (1, 'vs1', 'warm', 'a', 1);
        INSERT INTO property_vocabulary VALUES (10, 'warm', NULL, 0, 'pilot');
        INSERT INTO synset_properties VALUES ('abc', 10, 1.0, NULL, NULL);
    """)
    conn.commit()

    with caplog.at_level(logging.WARNING, logger="snap_properties"):
        try:
            snap_properties(conn, embedding_threshold=0.7)
        finally:
            conn.close()

    assert any(
        "vocab_clusters" in record.message and record.levelno == logging.WARNING
        for record in caplog.records
    ), f"Expected WARNING about vocab_clusters; got: {[r.message for r in caplog.records]}"


def test_snap_dropped_jsonl_handle_closed_on_mid_function_exception(tmp_path, monkeypatch):
    """If Pass 2 raises after _record_drop has lazily opened the JSONL stream, the
    finally clause must close the file handle so it does not leak. The on-disk
    JSONL must be well-formed up to the failure point (each line a complete JSON
    object).
    """
    import json as _json

    from snap_properties import snap_properties

    db_path, conn = make_snap_db(tmp_path)  # 'xyzqwerty' triggers a drop in Stage 3

    # Capture the file handle the closure opens so we can introspect after the raise.
    opened_handles: list = []
    real_open = open

    def tracking_open(path, mode="r", *a, **kw):
        fh = real_open(path, mode, *a, **kw)
        if str(path).endswith("snap_dropped.jsonl"):
            opened_handles.append(fh)
        return fh

    monkeypatch.setattr("builtins.open", tracking_open)

    # Wrap conn so we can fail the bulk INSERT after drops have streamed.
    # sqlite3.Connection attributes are read-only, so use a proxy object.
    class FailingConn:
        def __init__(self, real):
            self._real = real

        def __getattr__(self, name):
            return getattr(self._real, name)

        def executemany(self, sql, params):
            if "synset_properties_curated" in sql:
                raise sqlite3.OperationalError("simulated mid-run failure")
            return self._real.executemany(sql, params)

    proxy = FailingConn(conn)
    try:
        with pytest.raises(sqlite3.OperationalError):
            snap_properties(proxy, embedding_threshold=0.7)
    finally:
        conn.close()

    # The drops fixture only triggers no_embedding (Stage 3 fallback) — confirm a
    # handle was opened, then closed by the finally clause.
    assert opened_handles, "expected JSONL handle to be opened on at least one drop"
    fh = opened_handles[0]
    assert fh.closed, "dropped_fh must be closed by finally clause after exception"

    # Lines on disk must be well-formed JSON (no torn writes).
    jsonl_path = tmp_path / "snap_dropped.jsonl"
    if jsonl_path.exists():
        with real_open(jsonl_path) as f:
            for line in f:
                if line.strip():
                    _json.loads(line)


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
