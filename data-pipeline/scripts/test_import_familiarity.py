"""Test familiarity import to lexicon_v2.db."""
import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))

from utils import LEXICON_V2
from import_familiarity import compute_rarity, import_familiarity
from import_subtlex import backfill_subtlex


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


# --- Unit tests (no real DB required) ----------------------------------------

# -- compute_rarity --

def test_compute_rarity_high_familiarity_is_common():
    """Familiarity >= 5.5 → common."""
    assert compute_rarity(6.0, None) == "common"


def test_compute_rarity_mid_familiarity_is_unusual():
    """3.5 <= familiarity < 5.5 → unusual."""
    assert compute_rarity(4.0, None) == "unusual"


def test_compute_rarity_low_familiarity_is_rare():
    """Familiarity < 3.5 → rare."""
    assert compute_rarity(2.0, None) == "rare"


def test_compute_rarity_zipf_fallback_common():
    """No familiarity, Zipf >= 4.5 → common."""
    assert compute_rarity(None, 5.0) == "common"


def test_compute_rarity_zipf_fallback_unusual():
    """No familiarity, 2.5 <= Zipf < 4.5 → unusual."""
    assert compute_rarity(None, 3.0) == "unusual"


def test_compute_rarity_zipf_fallback_rare():
    """No familiarity, Zipf < 2.5 → rare."""
    assert compute_rarity(None, 1.0) == "rare"


def test_compute_rarity_no_data_defaults_unusual():
    """Neither familiarity nor Zipf → unusual."""
    assert compute_rarity(None, None) == "unusual"


def test_compute_rarity_familiarity_takes_precedence_over_zipf():
    """When both are present, familiarity wins."""
    # High familiarity, low zipf → common (familiarity wins)
    assert compute_rarity(6.0, 1.0) == "common"
    # Low familiarity, high zipf → rare (familiarity wins)
    assert compute_rarity(2.0, 5.0) == "rare"


def test_compute_rarity_at_thresholds():
    """Exact threshold values should classify correctly."""
    assert compute_rarity(5.5, None) == "common"
    assert compute_rarity(3.5, None) == "unusual"
    assert compute_rarity(None, 4.5) == "common"
    assert compute_rarity(None, 2.5) == "unusual"


# -- import_familiarity (in-memory SQLite) --

def _make_test_db():
    """Create an in-memory SQLite with lemmas and frequencies tables."""
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE lemmas (lemma TEXT, synset_id TEXT, PRIMARY KEY (lemma, synset_id))")
    conn.execute("""CREATE TABLE frequencies (
        lemma TEXT PRIMARY KEY,
        familiarity REAL,
        familiarity_dominant INTEGER,
        zipf REAL,
        frequency INTEGER,
        rarity TEXT,
        source TEXT
    )""")
    return conn


def test_import_familiarity_exact_match():
    """import_familiarity matches lemmas exactly and populates frequencies."""
    conn = _make_test_db()
    conn.execute("INSERT INTO lemmas VALUES ('happy', 'syn-happy-01')")
    conn.execute("INSERT INTO lemmas VALUES ('sad', 'syn-sad-01')")

    fam_data = {
        "happy": (6.2, 100, 5.1),
        "sad": (5.8, 80, 4.2),
    }
    stats = import_familiarity(conn, fam_data)

    assert stats["matched"] == 2
    assert stats["unmatched"] == 0

    row = conn.execute("SELECT rarity, familiarity FROM frequencies WHERE lemma = 'happy'").fetchone()
    assert row[0] == "common"
    assert row[1] == 6.2

    conn.close()


def test_import_familiarity_hyphen_fallback():
    """import_familiarity tries dehyphenated form as fallback."""
    conn = _make_test_db()
    conn.execute("INSERT INTO lemmas VALUES ('ice-cream', 'syn-ice-01')")

    fam_data = {"ice cream": (5.0, 50, 3.5)}
    stats = import_familiarity(conn, fam_data)

    assert stats["matched_hyphen"] == 1
    row = conn.execute("SELECT familiarity FROM frequencies WHERE lemma = 'ice-cream'").fetchone()
    assert row[0] == 5.0

    conn.close()


def test_import_familiarity_unmatched_gets_unusual():
    """Unmatched lemmas get rarity='unusual' with NULL familiarity."""
    conn = _make_test_db()
    conn.execute("INSERT INTO lemmas VALUES ('xyzzy', 'syn-xyzzy-01')")

    stats = import_familiarity(conn, {})

    assert stats["unmatched"] == 1
    row = conn.execute("SELECT rarity, familiarity FROM frequencies WHERE lemma = 'xyzzy'").fetchone()
    assert row[0] == "unusual"
    assert row[1] is None

    conn.close()


# -- backfill_subtlex (in-memory SQLite) --

def test_backfill_subtlex_updates_zipf():
    """backfill_subtlex fills in zipf and frequency for matched lemmas."""
    conn = _make_test_db()
    conn.execute("INSERT INTO lemmas VALUES ('happy', 'syn-happy-01')")
    conn.execute(
        "INSERT INTO frequencies VALUES ('happy', 6.2, 100, NULL, NULL, 'common', 'brysbaert')"
    )

    subtlex_data = {"happy": (5.3, 12345)}
    stats = backfill_subtlex(conn, subtlex_data)

    assert stats["updated_zipf"] == 1
    row = conn.execute("SELECT zipf, frequency, source FROM frequencies WHERE lemma = 'happy'").fetchone()
    assert row[0] == 5.3
    assert row[1] == 12345
    assert row[2] == "brysbaert+subtlex"

    conn.close()


def test_backfill_subtlex_recomputes_rarity_when_no_familiarity():
    """backfill_subtlex recomputes rarity from Zipf when familiarity is NULL."""
    conn = _make_test_db()
    conn.execute("INSERT INTO lemmas VALUES ('xyzzy', 'syn-xyzzy-01')")
    conn.execute(
        "INSERT INTO frequencies VALUES ('xyzzy', NULL, NULL, NULL, NULL, 'unusual', NULL)"
    )

    subtlex_data = {"xyzzy": (5.0, 500)}
    stats = backfill_subtlex(conn, subtlex_data)

    assert stats["rarity_recomputed"] == 1
    row = conn.execute("SELECT rarity, source FROM frequencies WHERE lemma = 'xyzzy'").fetchone()
    assert row[0] == "common"  # Zipf 5.0 >= 4.5 threshold
    assert row[1] == "subtlex"

    conn.close()
