"""Tests for property IDF computation."""
import sqlite3
import sys
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).parent))
from utils import LEXICON_V2


def test_idf_column_exists():
    """Verify IDF column was added to property_vocabulary."""
    conn = sqlite3.connect(LEXICON_V2)
    cursor = conn.execute("PRAGMA table_info(property_vocabulary)")
    columns = [row[1] for row in cursor.fetchall()]
    conn.close()
    assert "idf" in columns, "property_vocabulary should have 'idf' column"


def test_idf_values_populated():
    """Verify IDF values are populated for properties with synset links."""
    conn = sqlite3.connect(LEXICON_V2)

    # Count properties that have synset links
    linked_count = conn.execute("""
        SELECT COUNT(DISTINCT pv.property_id)
        FROM property_vocabulary pv
        JOIN synset_properties sp ON sp.property_id = pv.property_id
    """).fetchone()[0]

    # Count properties with IDF values
    idf_count = conn.execute("""
        SELECT COUNT(*) FROM property_vocabulary WHERE idf IS NOT NULL
    """).fetchone()[0]

    conn.close()

    # All linked properties should have IDF
    assert idf_count >= linked_count, \
        f"Expected {linked_count}+ properties with IDF, got {idf_count}"


def test_idf_values_reasonable():
    """Verify IDF values are within expected range."""
    conn = sqlite3.connect(LEXICON_V2)

    # Get min and max IDF
    row = conn.execute("""
        SELECT MIN(idf), MAX(idf), AVG(idf)
        FROM property_vocabulary
        WHERE idf IS NOT NULL
    """).fetchone()

    conn.close()

    min_idf, max_idf, avg_idf = row

    # IDF = log(N/df), with N ~= 1967 enriched synsets
    # min IDF: when df = N (property in all synsets) -> log(1) = 0
    # max IDF: when df = 1 (property in one synset) -> log(1967) ~= 7.58
    assert min_idf >= 0, f"IDF should be non-negative, got min={min_idf}"
    assert max_idf <= 10, f"IDF should be < 10, got max={max_idf}"
    assert 2 < avg_idf < 8, f"Average IDF should be 2-8, got {avg_idf}"


def test_idf_high_for_rare_properties():
    """Verify rare properties have high IDF."""
    conn = sqlite3.connect(LEXICON_V2)

    # Find a property that appears in few synsets
    row = conn.execute("""
        SELECT pv.text, pv.idf, COUNT(sp.synset_id) as doc_freq
        FROM property_vocabulary pv
        JOIN synset_properties sp ON sp.property_id = pv.property_id
        GROUP BY pv.property_id
        ORDER BY doc_freq ASC
        LIMIT 1
    """).fetchone()

    conn.close()

    if row:
        text, idf, doc_freq = row
        # Rare property (low doc_freq) should have high IDF
        if doc_freq <= 5:
            assert idf > 5, f"Rare property '{text}' (df={doc_freq}) should have high IDF, got {idf}"


def test_idf_low_for_common_properties():
    """Verify common properties have low IDF."""
    conn = sqlite3.connect(LEXICON_V2)

    # Find a property that appears in many synsets
    row = conn.execute("""
        SELECT pv.text, pv.idf, COUNT(sp.synset_id) as doc_freq
        FROM property_vocabulary pv
        JOIN synset_properties sp ON sp.property_id = pv.property_id
        GROUP BY pv.property_id
        ORDER BY doc_freq DESC
        LIMIT 1
    """).fetchone()

    conn.close()

    if row:
        text, idf, doc_freq = row
        # Common property (high doc_freq) should have low IDF
        if doc_freq >= 50:
            assert idf < 4, f"Common property '{text}' (df={doc_freq}) should have low IDF, got {idf}"
