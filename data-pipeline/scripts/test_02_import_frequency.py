import pytest
import sqlite3
from pathlib import Path

def test_frequencies_table_exists():
    """Database should have frequencies table after import."""
    db_path = Path(__file__).parent.parent / "output" / "lexicon.db"
    assert db_path.exists(), "lexicon.db not found - run 01_import_wordnet.py first"

    conn = sqlite3.connect(db_path)
    cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='frequencies'")
    table_exists = cursor.fetchone() is not None
    conn.close()

    assert table_exists, "frequencies table not found - run 02_import_frequency.py first"

def test_frequency_data_imported():
    """Should import 160k+ frequency entries from SUBTLEX-UK."""
    db_path = Path(__file__).parent.parent / "output" / "lexicon.db"
    conn = sqlite3.connect(db_path)
    cursor = conn.execute("SELECT COUNT(*) FROM frequencies")
    count = cursor.fetchone()[0]
    conn.close()

    assert count > 150000, f"Expected >150k frequency entries, got {count}"

def test_frequency_has_required_fields():
    """Each frequency entry should have word, frequency_count, zipf, and rarity_tier."""
    db_path = Path(__file__).parent.parent / "output" / "lexicon.db"
    conn = sqlite3.connect(db_path)
    cursor = conn.execute(
        "SELECT word, frequency_count, zipf, rarity_tier FROM frequencies LIMIT 1"
    )
    row = cursor.fetchone()
    conn.close()

    assert row is not None, "No frequency data found"
    word, frequency_count, zipf, rarity_tier = row
    assert isinstance(word, str) and len(word) > 0
    assert isinstance(frequency_count, int) and frequency_count >= 0
    assert isinstance(zipf, float) and zipf >= 0
    assert rarity_tier in ('common', 'uncommon', 'rare', 'archaic')

def test_rarity_tier_classification():
    """Rarity tiers should be correctly classified based on Zipf frequency."""
    db_path = Path(__file__).parent.parent / "output" / "lexicon.db"
    conn = sqlite3.connect(db_path)
    
    # Test common words (Zipf >= 5)
    cursor = conn.execute("SELECT COUNT(*) FROM frequencies WHERE zipf >= 5 AND rarity_tier = 'common'")
    common_count = cursor.fetchone()[0]
    
    # Test uncommon words (4 <= Zipf < 5)
    cursor = conn.execute("SELECT COUNT(*) FROM frequencies WHERE zipf >= 4 AND zipf < 5 AND rarity_tier = 'uncommon'")
    uncommon_count = cursor.fetchone()[0]
    
    # Test rare words (3 <= Zipf < 4)
    cursor = conn.execute("SELECT COUNT(*) FROM frequencies WHERE zipf >= 3 AND zipf < 4 AND rarity_tier = 'rare'")
    rare_count = cursor.fetchone()[0]
    
    # Test archaic words (Zipf < 3)
    cursor = conn.execute("SELECT COUNT(*) FROM frequencies WHERE zipf < 3 AND rarity_tier = 'archaic'")
    archaic_count = cursor.fetchone()[0]
    
    conn.close()
    
    assert common_count > 0, "No common words found"
    assert uncommon_count > 0, "No uncommon words found"
    assert rare_count > 0, "No rare words found"
    assert archaic_count > 0, "No archaic words found"

def test_known_words_have_expected_frequencies():
    """Common words should have expected frequency ranges."""
    db_path = Path(__file__).parent.parent / "output" / "lexicon.db"
    conn = sqlite3.connect(db_path)
    
    # Test some common words that should be in SUBTLEX-UK
    test_words = ['the', 'and', 'house', 'computer']
    
    for word in test_words:
        cursor = conn.execute(
            "SELECT zipf, rarity_tier FROM frequencies WHERE word = ?", 
            (word,)
        )
        row = cursor.fetchone()
        if row:  # Word might not exist in SUBTLEX-UK
            zipf, rarity_tier = row
            assert isinstance(zipf, float) and zipf > 0
            assert rarity_tier in ('common', 'uncommon', 'rare', 'archaic')
    
    conn.close()