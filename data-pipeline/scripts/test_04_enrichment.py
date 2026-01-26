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

        # Properties required (5-10 as per plan)
        props_list = json.loads(props)
        assert isinstance(props_list, list), f"{synset_id}: properties should be list"
        assert 5 <= len(props_list) <= 10, \
            f"{synset_id}: expected 5-10 properties, got {len(props_list)}"

        # Connotation should be valid value
        assert connotation in ('positive', 'neutral', 'negative', None), \
            f"{synset_id}: invalid connotation {connotation}"

        # Register should be valid value
        assert register in ('formal', 'neutral', 'informal', 'slang', None), \
            f"{synset_id}: invalid register {register}"

    conn.close()

def test_pilot_query_selects_high_frequency_words():
    """Pilot synsets should prioritize high-frequency words."""
    db_path = Path(__file__).parent.parent / "output" / "lexicon.db"
    conn = sqlite3.connect(db_path)

    # Get enriched synsets
    cursor = conn.execute("""
        SELECT e.synset_id, MAX(f.zipf) as max_zipf
        FROM enrichment e
        JOIN lemmas l ON e.synset_id = l.synset_id
        JOIN frequencies f ON l.lemma = f.lemma
        GROUP BY e.synset_id
        ORDER BY max_zipf DESC
        LIMIT 10
    """)

    results = cursor.fetchall()
    conn.close()

    # Verify we have results
    assert len(results) > 0, "No enriched synsets with frequency data found"

    # Top enriched synsets should have high Zipf scores (>= 5.0 is common)
    for synset_id, zipf in results[:5]:
        assert zipf >= 5.0, \
            f"Expected high-frequency words in pilot, but {synset_id} has Zipf {zipf}"

