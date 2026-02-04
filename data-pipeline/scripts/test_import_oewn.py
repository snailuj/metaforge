"""Test OEWN import to lexicon_v2.db."""
import sqlite3
from pathlib import Path
import pytest

LEXICON_V2 = Path(__file__).parent.parent / "output" / "lexicon_v2.db"


def test_synsets_imported():
    """Verify synsets table populated."""
    conn = sqlite3.connect(LEXICON_V2)
    count = conn.execute("SELECT COUNT(*) FROM synsets").fetchone()[0]
    conn.close()
    assert count > 100000, f"Expected 100k+ synsets, got {count}"


def test_lemmas_imported():
    """Verify lemmas table populated."""
    conn = sqlite3.connect(LEXICON_V2)
    count = conn.execute("SELECT COUNT(*) FROM lemmas").fetchone()[0]
    conn.close()
    assert count > 180000, f"Expected 180k+ lemma-synset pairs, got {count}"


def test_relations_imported():
    """Verify relations table populated."""
    conn = sqlite3.connect(LEXICON_V2)
    count = conn.execute("SELECT COUNT(*) FROM relations").fetchone()[0]
    conn.close()
    assert count > 200000, f"Expected 200k+ relations, got {count}"


def test_sample_lookup():
    """Verify we can look up a known word."""
    conn = sqlite3.connect(LEXICON_V2)
    result = conn.execute("""
        SELECT s.definition
        FROM lemmas l
        JOIN synsets s ON s.synset_id = l.synset_id
        WHERE l.lemma = 'candle'
        LIMIT 1
    """).fetchone()
    conn.close()
    assert result is not None, "Should find 'candle'"
    assert 'wax' in result[0].lower() or 'light' in result[0].lower()
