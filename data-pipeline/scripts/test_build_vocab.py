"""Tests for build_vocab.py — curated property vocabulary builder."""
import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))


def make_test_db(tmp_path):
    """Create a minimal lexicon DB with synsets, lemmas, frequencies."""
    db_path = tmp_path / "test_lexicon.db"
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
        CREATE TABLE frequencies (
            lemma TEXT PRIMARY KEY,
            familiarity REAL,
            zipf REAL,
            frequency INTEGER,
            rarity TEXT NOT NULL DEFAULT 'unusual',
            source TEXT
        );

        -- 3 synsets with varying polysemy
        INSERT INTO synsets VALUES ('s1', 'n', 'a warm thing');
        INSERT INTO synsets VALUES ('s2', 'a', 'having warmth');
        INSERT INTO synsets VALUES ('s3', 'n', 'a cold thing');

        -- Lemma polysemy: "warm" appears in s1 + s2 (polysemy=2), "toasty" only in s1 (mono)
        INSERT INTO lemmas VALUES ('warm', 's1');
        INSERT INTO lemmas VALUES ('toasty', 's1');
        INSERT INTO lemmas VALUES ('warm', 's2');
        INSERT INTO lemmas VALUES ('tepid', 's2');
        INSERT INTO lemmas VALUES ('cold', 's3');
        INSERT INTO lemmas VALUES ('frigid', 's3');

        -- Familiarity: s1 most familiar (warm=6.0), s3 second (cold=5.5), s2 least (tepid=3.0)
        -- Note: "warm" appears in both s1 and s2 — s2's max fam would be 6.0 without this fix.
        -- We set warm's fam to 5.2 so s1 max=5.2 (via warm), s2 max=5.2 (via warm), s3 max=5.5.
        -- Actually: we want s1 > s3 > s2, so give toasty high fam to boost s1.
        INSERT INTO frequencies VALUES ('warm', 5.0, 5.0, 1000, 'common', 'test');
        INSERT INTO frequencies VALUES ('toasty', 6.0, 3.0, 100, 'unusual', 'test');
        INSERT INTO frequencies VALUES ('tepid', 3.0, 2.0, 50, 'rare', 'test');
        INSERT INTO frequencies VALUES ('cold', 5.5, 4.5, 800, 'common', 'test');
        INSERT INTO frequencies VALUES ('frigid', 3.5, 2.5, 60, 'unusual', 'test');
    """)
    conn.commit()
    conn.close()
    return db_path


def test_build_vocab_picks_least_polysemous(tmp_path):
    """Each synset gets its least-polysemous lemma as canonical entry."""
    from build_vocab import build_vocabulary

    db_path = make_test_db(tmp_path)
    conn = sqlite3.connect(str(db_path))
    try:
        entries = build_vocabulary(conn, top_n=10)
    finally:
        conn.close()

    # s1 should pick "toasty" (polysemy=1) over "warm" (polysemy=2)
    s1_entry = next(e for e in entries if e["synset_id"] == "s1")
    assert s1_entry["lemma"] == "toasty"

    # s2 should pick "tepid" (polysemy=1) over "warm" (polysemy=2)
    s2_entry = next(e for e in entries if e["synset_id"] == "s2")
    assert s2_entry["lemma"] == "tepid"


def test_build_vocab_deduplicates_surface_forms(tmp_path):
    """If two synsets pick the same lemma, second one falls back."""
    db_path = tmp_path / "dedup.db"
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
        CREATE TABLE frequencies (
            lemma TEXT PRIMARY KEY,
            familiarity REAL,
            zipf REAL,
            frequency INTEGER,
            rarity TEXT NOT NULL DEFAULT 'unusual',
            source TEXT
        );

        -- Both synsets only have "bright" as their sole lemma
        INSERT INTO synsets VALUES ('s1', 'a', 'luminous');
        INSERT INTO synsets VALUES ('s2', 'a', 'intelligent');
        INSERT INTO lemmas VALUES ('bright', 's1');
        INSERT INTO lemmas VALUES ('bright', 's2');
        INSERT INTO lemmas VALUES ('brilliant', 's2');
        INSERT INTO frequencies VALUES ('bright', 6.0, 5.0, 500, 'common', 'test');
        INSERT INTO frequencies VALUES ('brilliant', 5.0, 4.0, 300, 'common', 'test');
    """)
    conn.commit()

    from build_vocab import build_vocabulary

    try:
        entries = build_vocabulary(conn, top_n=10)
    finally:
        conn.close()

    lemmas = [e["lemma"] for e in entries]
    # "bright" claimed by one synset, "brilliant" used as fallback for the other
    assert "bright" in lemmas
    assert "brilliant" in lemmas
    # No duplicates
    assert len(lemmas) == len(set(lemmas))


def test_build_vocab_ranks_by_familiarity(tmp_path):
    """Synsets are ranked by max lemma familiarity descending."""
    from build_vocab import build_vocabulary

    db_path = make_test_db(tmp_path)
    conn = sqlite3.connect(str(db_path))
    try:
        entries = build_vocabulary(conn, top_n=2)
    finally:
        conn.close()

    # Only top-2 by familiarity: s1 (warm=6.0) and s3 (cold=5.5)
    ids = [e["synset_id"] for e in entries]
    assert len(ids) == 2
    assert "s1" in ids
    assert "s3" in ids


def test_build_vocab_stores_to_table(tmp_path):
    """build_and_store creates the property_vocab_curated table."""
    from build_vocab import build_and_store

    db_path = make_test_db(tmp_path)
    conn = sqlite3.connect(str(db_path))
    try:
        count = build_and_store(conn, top_n=10)
    finally:
        conn.close()

    assert count == 3

    conn = sqlite3.connect(str(db_path))
    try:
        rows = conn.execute(
            "SELECT synset_id, lemma, pos, polysemy FROM property_vocab_curated ORDER BY vocab_id"
        ).fetchall()
    finally:
        conn.close()

    assert len(rows) == 3
    # Check schema columns exist
    assert all(len(r) == 4 for r in rows)
