"""Test synset_properties junction table."""
import sqlite3
from pathlib import Path

import pytest

LEXICON_V2 = Path(__file__).parent.parent / "output" / "lexicon_v2.db"


def test_junction_populated():
    """Verify synset_properties has entries."""
    conn = sqlite3.connect(LEXICON_V2)
    count = conn.execute("SELECT COUNT(*) FROM synset_properties").fetchone()[0]
    conn.close()
    assert count > 10000, f"Expected 10k+ synset-property links, got {count}"


def test_properties_queryable():
    """Verify we can query properties for a synset."""
    conn = sqlite3.connect(LEXICON_V2)
    row = conn.execute("""
        SELECT sp.synset_id, pv.text, pv.embedding IS NOT NULL as has_emb
        FROM synset_properties sp
        JOIN property_vocabulary pv ON pv.property_id = sp.property_id
        LIMIT 1
    """).fetchone()
    conn.close()

    assert row is not None, "Should have at least one synset-property link"


def test_synsets_have_multiple_properties():
    """Verify synsets have multiple properties (not just 1:1)."""
    conn = sqlite3.connect(LEXICON_V2)
    row = conn.execute("""
        SELECT synset_id, COUNT(*) as prop_count
        FROM synset_properties
        GROUP BY synset_id
        HAVING prop_count >= 3
        LIMIT 1
    """).fetchone()
    conn.close()

    assert row is not None, "Should have synsets with 3+ properties"


def test_properties_linked_to_multiple_synsets():
    """Verify properties are reused across synsets."""
    conn = sqlite3.connect(LEXICON_V2)
    row = conn.execute("""
        SELECT property_id, COUNT(*) as synset_count
        FROM synset_properties
        GROUP BY property_id
        HAVING synset_count >= 2
        LIMIT 1
    """).fetchone()
    conn.close()

    assert row is not None, "Should have properties linked to 2+ synsets"
