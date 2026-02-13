"""Unit tests for import_subtlex.py — SUBTLEX-UK frequency import."""
import sqlite3
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parent))

from import_subtlex import load_subtlex_flemmas, backfill_subtlex


# --- Helpers -----------------------------------------------------------------

def _make_test_db():
    """Create an in-memory SQLite with lemmas and frequencies tables."""
    conn = sqlite3.connect(":memory:")
    conn.execute(
        "CREATE TABLE lemmas (lemma TEXT, synset_id TEXT, PRIMARY KEY (lemma, synset_id))"
    )
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


def _mock_workbook(rows):
    """Build a mock openpyxl workbook with given rows (including header)."""
    wb = MagicMock()
    ws = MagicMock()
    wb.active = ws

    # Header row — iter_rows(min_row=1, max_row=1) returns a single row of cells
    header_cells = [MagicMock(value=h) for h in rows[0]]
    ws.iter_rows.side_effect = lambda **kwargs: (
        iter([header_cells]) if kwargs.get("max_row") == 1
        else iter(rows[1:])
    )

    return wb


# --- load_subtlex_flemmas (mocked workbook) ----------------------------------

@patch("import_subtlex.openpyxl.load_workbook")
def test_load_subtlex_flemmas_basic(mock_load_wb, tmp_path):
    """load_subtlex_flemmas returns dict of flemma -> (Zipf, freq)."""
    wb = _mock_workbook([
        ("flemma", "Zipf", "lemmafreqs_combined", "extra"),
        ("happy", 5.3, 12345, "x"),
        ("sad", 4.1, 678, "y"),
    ])
    mock_load_wb.return_value = wb

    data = load_subtlex_flemmas(tmp_path / "fake.xlsx")

    assert len(data) == 2
    assert data["happy"] == (5.3, 12345)
    assert data["sad"] == (4.1, 678)


@patch("import_subtlex.openpyxl.load_workbook")
def test_load_subtlex_flemmas_skips_none_flemma(mock_load_wb, tmp_path):
    """Rows with None flemma are skipped."""
    wb = _mock_workbook([
        ("flemma", "Zipf", "lemmafreqs_combined"),
        (None, 5.0, 100),
        ("valid", 3.0, 200),
    ])
    mock_load_wb.return_value = wb

    data = load_subtlex_flemmas(tmp_path / "fake.xlsx")

    assert len(data) == 1
    assert "valid" in data


@patch("import_subtlex.openpyxl.load_workbook")
def test_load_subtlex_flemmas_deduplicates(mock_load_wb, tmp_path):
    """Only first occurrence of a flemma is kept."""
    wb = _mock_workbook([
        ("flemma", "Zipf", "lemmafreqs_combined"),
        ("word", 5.0, 100),
        ("word", 3.0, 50),
    ])
    mock_load_wb.return_value = wb

    data = load_subtlex_flemmas(tmp_path / "fake.xlsx")

    assert len(data) == 1
    assert data["word"] == (5.0, 100)


@patch("import_subtlex.openpyxl.load_workbook")
def test_load_subtlex_flemmas_skips_null_zipf(mock_load_wb, tmp_path):
    """Rows with None Zipf are skipped."""
    wb = _mock_workbook([
        ("flemma", "Zipf", "lemmafreqs_combined"),
        ("nozip", None, 100),
        ("haszip", 4.0, 200),
    ])
    mock_load_wb.return_value = wb

    data = load_subtlex_flemmas(tmp_path / "fake.xlsx")

    assert len(data) == 1
    assert "haszip" in data


@patch("import_subtlex.openpyxl.load_workbook")
def test_load_subtlex_flemmas_lowercases(mock_load_wb, tmp_path):
    """Flemma keys are lowercased."""
    wb = _mock_workbook([
        ("flemma", "Zipf", "lemmafreqs_combined"),
        ("Happy", 5.3, 12345),
    ])
    mock_load_wb.return_value = wb

    data = load_subtlex_flemmas(tmp_path / "fake.xlsx")

    assert "happy" in data


# --- backfill_subtlex (in-memory SQLite) -------------------------------------

def test_backfill_subtlex_updates_brysbaert_source():
    """Rows with source='brysbaert' become 'brysbaert+subtlex'."""
    conn = _make_test_db()
    conn.execute(
        "INSERT INTO frequencies VALUES ('happy', 6.2, 100, NULL, NULL, 'common', 'brysbaert')"
    )

    stats = backfill_subtlex(conn, {"happy": (5.3, 12345)})

    assert stats["updated_zipf"] == 1
    row = conn.execute("SELECT source FROM frequencies WHERE lemma = 'happy'").fetchone()
    assert row[0] == "brysbaert+subtlex"
    conn.close()


def test_backfill_subtlex_null_source_becomes_subtlex():
    """Rows with source=NULL become 'subtlex'."""
    conn = _make_test_db()
    conn.execute(
        "INSERT INTO frequencies VALUES ('xyzzy', NULL, NULL, NULL, NULL, 'unusual', NULL)"
    )

    stats = backfill_subtlex(conn, {"xyzzy": (5.0, 500)})

    row = conn.execute("SELECT source FROM frequencies WHERE lemma = 'xyzzy'").fetchone()
    assert row[0] == "subtlex"
    conn.close()


def test_backfill_subtlex_recomputes_rarity_common():
    """Rarity is recomputed to 'common' when familiarity is NULL and Zipf >= 4.5."""
    conn = _make_test_db()
    conn.execute(
        "INSERT INTO frequencies VALUES ('word', NULL, NULL, NULL, NULL, 'unusual', NULL)"
    )

    backfill_subtlex(conn, {"word": (5.0, 500)})

    row = conn.execute("SELECT rarity FROM frequencies WHERE lemma = 'word'").fetchone()
    assert row[0] == "common"
    conn.close()


def test_backfill_subtlex_recomputes_rarity_rare():
    """Rarity is recomputed to 'rare' when familiarity is NULL and Zipf < 2.5."""
    conn = _make_test_db()
    conn.execute(
        "INSERT INTO frequencies VALUES ('obscure', NULL, NULL, NULL, NULL, 'unusual', NULL)"
    )

    backfill_subtlex(conn, {"obscure": (1.5, 5)})

    row = conn.execute("SELECT rarity FROM frequencies WHERE lemma = 'obscure'").fetchone()
    assert row[0] == "rare"
    conn.close()


def test_backfill_subtlex_preserves_rarity_when_familiarity_exists():
    """Rarity is NOT recomputed when familiarity is present."""
    conn = _make_test_db()
    conn.execute(
        "INSERT INTO frequencies VALUES ('happy', 6.2, 100, NULL, NULL, 'common', 'brysbaert')"
    )

    stats = backfill_subtlex(conn, {"happy": (2.0, 50)})

    assert stats["rarity_recomputed"] == 0
    row = conn.execute("SELECT rarity FROM frequencies WHERE lemma = 'happy'").fetchone()
    assert row[0] == "common"  # unchanged despite low Zipf
    conn.close()


def test_backfill_subtlex_no_match():
    """Unmatched lemmas are counted but not modified."""
    conn = _make_test_db()
    conn.execute(
        "INSERT INTO frequencies VALUES ('lonely', 4.0, 50, NULL, NULL, 'unusual', 'brysbaert')"
    )

    stats = backfill_subtlex(conn, {"other": (5.0, 100)})

    assert stats["no_match"] == 1
    assert stats["updated_zipf"] == 0
    conn.close()
