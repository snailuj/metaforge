# data-pipeline/scripts/test_04_enrichment.py
import pytest
import sqlite3
import json
from pathlib import Path

def test_enrichment_table_exists():
    """Enrichment table should exist in lexicon.db."""
    db_path = Path(__file__).parent.parent / "output" / "lexicon.db"
    conn = sqlite3.connect(db_path)
    cursor = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='enrichment'"
    )
    result = cursor.fetchone()
    conn.close()
    assert result is not None, "enrichment table not found"

def test_pilot_synsets_have_enrichment():
    """Pilot synsets should have extracted enrichment data."""
    db_path = Path(__file__).parent.parent / "output" / "lexicon.db"
    conn = sqlite3.connect(db_path)
    cursor = conn.execute("SELECT COUNT(*) FROM enrichment")
    count = cursor.fetchone()[0]
    conn.close()

    # Pilot is 1000 synsets
    assert count >= 500, f"Expected >=500 enrichment entries, got {count}"

def test_enrichment_has_all_fields():
    """Enrichment should include properties, metonyms, connotation, register, example."""
    db_path = Path(__file__).parent.parent / "output" / "lexicon.db"
    conn = sqlite3.connect(db_path)
    cursor = conn.execute("""
        SELECT synset_id, properties, metonyms, connotation, register, usage_example
        FROM enrichment LIMIT 10
    """)

    for row in cursor:
        synset_id, props, metonyms, connotation, register, example = row

        # Properties required
        props_list = json.loads(props)
        assert isinstance(props_list, list), f"{synset_id}: properties should be list"
        assert len(props_list) >= 3, f"{synset_id}: expected 3+ properties"

        # Connotation should be valid value
        assert connotation in ('positive', 'neutral', 'negative', None), \
            f"{synset_id}: invalid connotation {connotation}"

        # Register should be valid value
        assert register in ('formal', 'neutral', 'informal', 'slang', None), \
            f"{synset_id}: invalid register {register}"

    conn.close()
