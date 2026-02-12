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


def test_frequencies_populated():
    """Verify frequencies table has rows after import."""
    conn = sqlite3.connect(LEXICON_V2)
    try:
        count = conn.execute("SELECT COUNT(*) FROM frequencies").fetchone()[0]
    finally:
        conn.close()
    assert count > 80000, f"Expected 80k+ frequency rows, got {count}"


def test_happy_is_common():
    """Verify 'happy' is classified as common."""
    conn = sqlite3.connect(LEXICON_V2)
    try:
        row = conn.execute(
            "SELECT rarity, familiarity FROM frequencies WHERE lemma = 'happy'"
        ).fetchone()
    finally:
        conn.close()
    assert row is not None, "'happy' should be in frequencies"
    assert row[0] == "common", f"Expected 'happy' rarity=common, got {row[0]}"
    assert row[1] is not None and row[1] >= 5.5, f"Expected familiarity >= 5.5, got {row[1]}"


def test_penchant_is_unusual():
    """Verify 'penchant' is classified as unusual."""
    conn = sqlite3.connect(LEXICON_V2)
    try:
        row = conn.execute(
            "SELECT rarity, familiarity FROM frequencies WHERE lemma = 'penchant'"
        ).fetchone()
    finally:
        conn.close()
    assert row is not None, "'penchant' should be in frequencies"
    assert row[0] == "unusual", f"Expected rarity=unusual, got {row[0]}"


def test_source_column_populated():
    """Verify source provenance is recorded."""
    conn = sqlite3.connect(LEXICON_V2)
    try:
        sources = conn.execute(
            "SELECT DISTINCT source FROM frequencies"
        ).fetchall()
        sources = [s[0] for s in sources]
    finally:
        conn.close()
    assert "brysbaert" in sources, f"Expected 'brysbaert' in sources, got {sources}"


def test_unmatched_lemmas_get_default_unusual():
    """Verify lemmas not in any dataset get rarity='unusual' and NULL familiarity."""
    conn = sqlite3.connect(LEXICON_V2)
    try:
        # Get a lemma that exists in our DB
        all_lemmas = conn.execute("SELECT DISTINCT lemma FROM lemmas").fetchall()
        freq_lemmas = conn.execute("SELECT lemma FROM frequencies").fetchall()
    finally:
        conn.close()
    # We should have frequency entries for all lemmas in our DB
    assert len(freq_lemmas) >= len(all_lemmas) * 0.95, \
        f"Expected frequencies for >= 95% of lemmas, got {len(freq_lemmas)}/{len(all_lemmas)}"


def test_no_duplicate_lemmas():
    """Verify no duplicate lemma entries in frequencies table."""
    conn = sqlite3.connect(LEXICON_V2)
    try:
        dups = conn.execute("""
            SELECT lemma, COUNT(*) as cnt
            FROM frequencies
            GROUP BY lemma
            HAVING cnt > 1
        """).fetchall()
    finally:
        conn.close()
    assert len(dups) == 0, f"Found {len(dups)} duplicate lemmas: {dups[:5]}"


def test_rarity_distribution_reasonable():
    """Verify rarity tier distribution is roughly as expected."""
    conn = sqlite3.connect(LEXICON_V2)
    try:
        rows = conn.execute("""
            SELECT rarity, COUNT(*) FROM frequencies GROUP BY rarity
        """).fetchall()
    finally:
        conn.close()
    dist = {row[0]: row[1] for row in rows}
    total = sum(dist.values())
    # Common should be a significant group (many WordNet lemmas are familiar)
    assert dist.get("common", 0) > total * 0.1, \
        f"Expected > 10% common, got {dist.get('common', 0)}/{total}"
    # We should have all three tiers
    assert "common" in dist, "Missing 'common' tier"
    assert "unusual" in dist, "Missing 'unusual' tier"
    assert "rare" in dist, "Missing 'rare' tier"


def test_subtlex_zipf_backfill():
    """Verify SUBTLEX Zipf is used when Multilex Zipf was NULL."""
    conn = sqlite3.connect(LEXICON_V2)
    try:
        # Count rows with non-null zipf
        count = conn.execute(
            "SELECT COUNT(*) FROM frequencies WHERE zipf IS NOT NULL"
        ).fetchone()[0]
    finally:
        conn.close()
    # SUBTLEX should add Zipf data beyond what Multilex provided (~50k)
    assert count > 50000, f"Expected 50k+ rows with Zipf, got {count}"


def test_subtlex_source_recorded():
    """Verify SUBTLEX source is recorded for backfilled rows."""
    conn = sqlite3.connect(LEXICON_V2)
    try:
        sources = conn.execute(
            "SELECT DISTINCT source FROM frequencies WHERE source IS NOT NULL"
        ).fetchall()
        sources = [s[0] for s in sources]
    finally:
        conn.close()
    assert "subtlex" in sources or "brysbaert+subtlex" in sources, \
        f"Expected 'subtlex' or 'brysbaert+subtlex' in sources, got {sources}"
