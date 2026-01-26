# data-pipeline/scripts/test_01_import_wordnet.py
import pytest
import sqlite3
from pathlib import Path

def test_lexicon_db_has_synsets():
    """Lexicon DB should contain synsets with definitions."""
    db_path = Path(__file__).parent.parent / "output" / "lexicon.db"
    assert db_path.exists(), "lexicon.db not found - run 01_import_wordnet.py first"

    conn = sqlite3.connect(db_path)
    cursor = conn.execute("SELECT COUNT(*) FROM synsets")
    count = cursor.fetchone()[0]
    conn.close()

    assert count > 100000, f"Expected >100k synsets, got {count}"

def test_synset_has_required_fields():
    """Each synset should have id, pos, and definition."""
    db_path = Path(__file__).parent.parent / "output" / "lexicon.db"
    conn = sqlite3.connect(db_path)
    cursor = conn.execute(
        "SELECT synset_id, pos, definition FROM synsets LIMIT 1"
    )
    row = cursor.fetchone()
    conn.close()

    assert row is not None
    synset_id, pos, definition = row
    assert synset_id is not None
    assert pos in ('n', 'v', 'a', 'r', 's')
    assert len(definition) > 0
