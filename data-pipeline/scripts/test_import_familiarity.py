"""Test familiarity import to lexicon_v2.db."""
import sqlite3
import pytest

from utils import LEXICON_V2


def test_frequencies_schema_has_familiarity_column():
    """Verify frequencies table has the new familiarity columns."""
    conn = sqlite3.connect(LEXICON_V2)
    try:
        cursor = conn.execute("PRAGMA table_info(frequencies)")
        columns = {row[1]: row[2] for row in cursor.fetchall()}
    finally:
        conn.close()

    assert "familiarity" in columns, "Missing familiarity column"
    assert "familiarity_dominant" in columns, "Missing familiarity_dominant column"
    assert "source" in columns, "Missing source column"
    assert columns["familiarity"] == "REAL"
    assert columns["familiarity_dominant"] == "INTEGER"
