"""Tests for import_concreteness.py — Brysbaert concreteness import."""
import logging
import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))

from import_concreteness import load_concreteness, import_concreteness


def _make_test_db():
    """Create an in-memory SQLite with synsets, lemmas, and synset_concreteness tables."""
    conn = sqlite3.connect(":memory:")
    conn.execute("""CREATE TABLE synsets (
        synset_id TEXT PRIMARY KEY, pos TEXT, definition TEXT
    )""")
    conn.execute("""CREATE TABLE lemmas (
        lemma TEXT, synset_id TEXT, PRIMARY KEY (lemma, synset_id)
    )""")
    conn.execute("""CREATE TABLE synset_concreteness (
        synset_id TEXT PRIMARY KEY,
        score REAL NOT NULL,
        source TEXT NOT NULL,
        FOREIGN KEY (synset_id) REFERENCES synsets(synset_id)
    )""")
    return conn


# --- load_concreteness ---

def test_load_concreteness_parses_tsv(tmp_path):
    """load_concreteness reads tab-separated Brysbaert file."""
    tsv = tmp_path / "concreteness.txt"
    tsv.write_text(
        "Word\tBigram\tConc.M\tConc.SD\tUnknown\tTotal\tPercent_known\tSUBTLEX\tDom_Pos\n"
        "apple\t0\t4.82\t0.39\t0\t25\t100\t12345\tNoun\n"
        "justice\t0\t1.78\t1.22\t2\t25\t92\t5678\tNoun\n"
    )
    data = load_concreteness(tsv)
    assert "apple" in data
    assert abs(data["apple"] - 4.82) < 0.01
    assert "justice" in data
    assert abs(data["justice"] - 1.78) < 0.01


def test_load_concreteness_lowercases_words(tmp_path):
    """Words are lowercased for matching."""
    tsv = tmp_path / "concreteness.txt"
    tsv.write_text(
        "Word\tBigram\tConc.M\tConc.SD\tUnknown\tTotal\tPercent_known\tSUBTLEX\tDom_Pos\n"
        "Apple\t0\t4.82\t0.39\t0\t25\t100\t12345\tNoun\n"
    )
    data = load_concreteness(tsv)
    assert "apple" in data


def test_load_concreteness_logs_parse_errors(tmp_path, caplog):
    """Malformed score fields are logged at WARNING with context."""
    tsv = tmp_path / "concreteness.txt"
    tsv.write_text(
        "Word\tBigram\tConc.M\tConc.SD\tUnknown\tTotal\tPercent_known\tSUBTLEX\tDom_Pos\n"
        "apple\t0\t4.82\t0.39\t0\t25\t100\t12345\tNoun\n"
        "badword\t0\tNOTANUMBER\t0.50\t0\t25\t100\t2345\tNoun\n"
        "justice\t0\t1.78\t1.22\t2\t25\t92\t5678\tNoun\n"
    )
    with caplog.at_level(logging.WARNING, logger="import_concreteness"):
        data = load_concreteness(tsv)

    # Good rows parsed, bad row skipped
    assert "apple" in data
    assert "justice" in data
    assert "badword" not in data

    # Warning logged with context
    assert any("badword" in rec.message and "NOTANUMBER" in rec.message
               for rec in caplog.records), f"Expected parse error log, got: {caplog.text}"


def test_load_concreteness_skips_bigrams(tmp_path):
    """Bigrams (Bigram=1) are skipped — we only want single words."""
    tsv = tmp_path / "concreteness.txt"
    tsv.write_text(
        "Word\tBigram\tConc.M\tConc.SD\tUnknown\tTotal\tPercent_known\tSUBTLEX\tDom_Pos\n"
        "apple\t0\t4.82\t0.39\t0\t25\t100\t12345\tNoun\n"
        "ice cream\t1\t4.50\t0.50\t0\t25\t100\t2345\tNoun\n"
    )
    data = load_concreteness(tsv)
    assert "apple" in data
    assert "ice cream" not in data


# --- import_concreteness ---

def test_import_concreteness_single_lemma_synset():
    """Synset with one lemma gets that lemma's concreteness score."""
    conn = _make_test_db()
    conn.execute("INSERT INTO synsets VALUES ('syn-apple', 'n', 'fruit')")
    conn.execute("INSERT INTO lemmas VALUES ('apple', 'syn-apple')")

    stats = import_concreteness(conn, {"apple": 4.82})

    row = conn.execute(
        "SELECT score, source FROM synset_concreteness WHERE synset_id = 'syn-apple'"
    ).fetchone()
    assert row is not None
    assert abs(row[0] - 4.82) < 0.01
    assert row[1] == "brysbaert"
    assert stats["scored"] == 1
    conn.close()


def test_import_concreteness_multi_lemma_synset_uses_max():
    """Synset with multiple lemmas gets the max of available scores."""
    conn = _make_test_db()
    conn.execute("INSERT INTO synsets VALUES ('syn-rock', 'n', 'a stone')")
    conn.execute("INSERT INTO lemmas VALUES ('rock', 'syn-rock')")
    conn.execute("INSERT INTO lemmas VALUES ('stone', 'syn-rock')")

    # rock=4.8, stone=4.6 → max=4.8
    stats = import_concreteness(conn, {"rock": 4.8, "stone": 4.6})

    row = conn.execute(
        "SELECT score FROM synset_concreteness WHERE synset_id = 'syn-rock'"
    ).fetchone()
    assert abs(row[0] - 4.8) < 0.01
    assert stats["scored"] == 1
    conn.close()


def test_import_concreteness_partial_lemma_coverage():
    """Synset scores use only lemmas with data; ignores missing ones."""
    conn = _make_test_db()
    conn.execute("INSERT INTO synsets VALUES ('syn-rock', 'n', 'a stone')")
    conn.execute("INSERT INTO lemmas VALUES ('rock', 'syn-rock')")
    conn.execute("INSERT INTO lemmas VALUES ('boulder', 'syn-rock')")

    # Only 'rock' has a score; 'boulder' missing → score = rock's alone
    stats = import_concreteness(conn, {"rock": 4.8})

    row = conn.execute(
        "SELECT score FROM synset_concreteness WHERE synset_id = 'syn-rock'"
    ).fetchone()
    assert abs(row[0] - 4.8) < 0.01
    conn.close()


def test_import_concreteness_no_coverage_no_row():
    """Synset where no lemmas have Brysbaert data gets no row."""
    conn = _make_test_db()
    conn.execute("INSERT INTO synsets VALUES ('syn-xyzzy', 'n', 'unknown')")
    conn.execute("INSERT INTO lemmas VALUES ('xyzzy', 'syn-xyzzy')")

    stats = import_concreteness(conn, {})

    row = conn.execute(
        "SELECT * FROM synset_concreteness WHERE synset_id = 'syn-xyzzy'"
    ).fetchone()
    assert row is None
    assert stats["unscored"] == 1
    conn.close()


def test_import_concreteness_idempotent():
    """Running import twice produces same result (INSERT OR REPLACE)."""
    conn = _make_test_db()
    conn.execute("INSERT INTO synsets VALUES ('syn-apple', 'n', 'fruit')")
    conn.execute("INSERT INTO lemmas VALUES ('apple', 'syn-apple')")

    import_concreteness(conn, {"apple": 4.82})
    import_concreteness(conn, {"apple": 4.82})

    count = conn.execute("SELECT COUNT(*) FROM synset_concreteness").fetchone()[0]
    assert count == 1
    conn.close()


def test_import_concreteness_returns_stats():
    """Stats dict has scored and unscored counts."""
    conn = _make_test_db()
    conn.execute("INSERT INTO synsets VALUES ('syn-a', 'n', 'a')")
    conn.execute("INSERT INTO synsets VALUES ('syn-b', 'n', 'b')")
    conn.execute("INSERT INTO lemmas VALUES ('apple', 'syn-a')")
    conn.execute("INSERT INTO lemmas VALUES ('xyzzy', 'syn-b')")

    stats = import_concreteness(conn, {"apple": 4.82})

    assert stats["scored"] == 1
    assert stats["unscored"] == 1
    assert stats["total_synsets"] == 2
    conn.close()
