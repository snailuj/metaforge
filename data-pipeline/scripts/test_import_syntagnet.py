"""Test SyntagNet import."""
import sqlite3
from pathlib import Path
import pytest

LEXICON_V2 = Path(__file__).parent.parent / "output" / "lexicon_v2.db"


def test_syntagms_imported():
    """Verify syntagms table populated."""
    conn = sqlite3.connect(LEXICON_V2)
    count = conn.execute("SELECT COUNT(*) FROM syntagms").fetchone()[0]
    conn.close()
    assert count > 80000, f"Expected 80k+ syntagms, got {count}"


def test_syntagm_structure():
    """Verify syntagms have both synset links."""
    conn = sqlite3.connect(LEXICON_V2)
    row = conn.execute("""
        SELECT synset1id, synset2id, sensekey1, sensekey2
        FROM syntagms LIMIT 1
    """).fetchone()
    conn.close()

    assert row is not None
    assert row[0] is not None, "synset1id should not be null"
    assert row[1] is not None, "synset2id should not be null"


def test_syntagm_synset_links_valid():
    """Verify syntagms link to real synsets."""
    conn = sqlite3.connect(LEXICON_V2)
    # Check a sample of syntagms have valid synset references
    orphans = conn.execute("""
        SELECT COUNT(*) FROM syntagms st
        LEFT JOIN synsets s1 ON s1.synset_id = st.synset1id
        LEFT JOIN synsets s2 ON s2.synset_id = st.synset2id
        WHERE s1.synset_id IS NULL OR s2.synset_id IS NULL
    """).fetchone()[0]
    total = conn.execute("SELECT COUNT(*) FROM syntagms").fetchone()[0]
    conn.close()

    orphan_rate = orphans / total if total > 0 else 0
    assert orphan_rate < 0.1, f"Expected <10% orphan syntagms, got {orphan_rate:.1%}"
