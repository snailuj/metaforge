"""Test BNC POS-resolved frequency import.

Fixture-based unit tests against the real SCHEMA.sql dest. The point of BNC is
the POS split (which the word-level `frequencies` table lacks), so the tests
exercise both the load and the verb-dominant-lemma query it enables.
"""
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from utils import PIPELINE_DIR
import import_bnc

SCHEMA_SQL = (PIPELINE_DIR / "SCHEMA.sql").read_text()


def _dst() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.executescript(SCHEMA_SQL)
    return conn


def _src() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.executescript(
        """
        CREATE TABLE bnc_bncs (wordid INTEGER, posid TEXT, freq INTEGER, range INTEGER, disp REAL);
        CREATE TABLE words (wordid INTEGER, word TEXT);
        INSERT INTO words VALUES (1,'take'),(2,'cat');
        INSERT INTO bnc_bncs VALUES
            (1,'n',5,1,0.1),     -- take as noun: rare
            (1,'v',732,1,0.5),   -- take as verb: dominant
            (2,'n',900,1,0.9),   -- cat as noun
            (2,'v',NULL,NULL,NULL);  -- NULL freq must be dropped
        """
    )
    return conn


def test_bnc_imported_with_pos_split():
    src, dst = _src(), _dst()
    import_bnc.import_bnc(src, dst)
    rows = dst.execute(
        "SELECT lemma, pos, freq FROM bnc_frequencies ORDER BY lemma, pos"
    ).fetchall()
    # cat/v dropped (NULL freq); the rest land with their POS-split frequency.
    assert rows == [("cat", "n", 900), ("take", "n", 5), ("take", "v", 732)]


def test_verb_dominant_lemma_query():
    """The POS-dominance filter: 'take' is verb-dominant and would be culled."""
    src, dst = _src(), _dst()
    import_bnc.import_bnc(src, dst)
    verb_dominant = dst.execute(
        """
        SELECT n.lemma FROM bnc_frequencies n JOIN bnc_frequencies v
          ON v.lemma = n.lemma AND n.pos = 'n' AND v.pos = 'v'
        WHERE v.freq > n.freq
        """
    ).fetchall()
    assert verb_dominant == [("take",)]


def test_bnc_idempotent():
    src, dst = _src(), _dst()
    import_bnc.import_bnc(src, dst)
    import_bnc.import_bnc(src, dst)
    assert dst.execute("SELECT COUNT(*) FROM bnc_frequencies").fetchone()[0] == 3
