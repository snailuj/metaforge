"""Test SemCor sense-attribute import (sensekey + tagcount for every sense).

Fixture-based unit tests against the real SCHEMA.sql dest. Covers the three
behaviours that matter: tagged senses carry their dominant-sense tagcount, the
untagged tail is still captured (sensekey present, tagcount NULL), and the
dominant-sense lookup the disambiguator relies on resolves correctly.
"""
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from utils import PIPELINE_DIR
import import_semcor

SCHEMA_SQL = (PIPELINE_DIR / "SCHEMA.sql").read_text()


def _dst() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.executescript(SCHEMA_SQL)
    return conn


def _src() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.executescript(
        """
        CREATE TABLE senses (senseid INTEGER, sensekey TEXT, synsetid INTEGER,
            luid INTEGER, wordid INTEGER, casedwordid INTEGER, lexid INTEGER,
            sensenum INTEGER, tagcount INTEGER);
        CREATE TABLE words (wordid INTEGER, word TEXT);
        INSERT INTO words VALUES (10,'fire');
        INSERT INTO senses VALUES
          (1,'fire%1:11:00::',71587,1,10,NULL,11,1,43),   -- burning event: dominant
          (2,'fire%2:33:01::',21119,1,10,NULL,33,1,30),   -- firing weapon
          (3,'fire%1:22:00::',94543,1,10,NULL,22,3,NULL), -- untagged tail (NULL tagcount)
          (4,NULL,            55555,1,10,NULL,99,9,NULL); -- no sensekey: must be skipped
        """
    )
    return conn


def test_tagged_sense_imported():
    src, dst = _src(), _dst()
    import_semcor.import_sense_attributes(src, dst)
    row = dst.execute(
        "SELECT lemma, synset_id, sensenum, tagcount FROM sense_attributes WHERE sensekey='fire%1:11:00::'"
    ).fetchone()
    assert row == ("fire", "71587", 1, 43)  # synset_id stringified from INT


def test_untagged_tail_captured():
    """Untagged senses are still stored (for the sensekey), tagcount NULL."""
    src, dst = _src(), _dst()
    import_semcor.import_sense_attributes(src, dst)
    row = dst.execute(
        "SELECT synset_id, tagcount FROM sense_attributes WHERE sensekey='fire%1:22:00::'"
    ).fetchone()
    assert row == ("94543", None)


def test_null_sensekey_skipped():
    """A sense without a sensekey cannot be keyed and must be dropped."""
    src, dst = _src(), _dst()
    import_semcor.import_sense_attributes(src, dst)
    count = dst.execute("SELECT COUNT(*) FROM sense_attributes").fetchone()[0]
    assert count == 3  # the 4th row (NULL sensekey) skipped


def test_dominant_sense_by_tagcount():
    """The disambiguator's core query: highest-tagcount synset for a lemma."""
    src, dst = _src(), _dst()
    import_semcor.import_sense_attributes(src, dst)
    winner = dst.execute(
        "SELECT synset_id FROM sense_attributes WHERE lemma='fire' ORDER BY tagcount DESC LIMIT 1"
    ).fetchone()
    assert winner == ("71587",)  # NULLs sort last under DESC; 43 wins


def test_semcor_idempotent():
    src, dst = _src(), _dst()
    import_semcor.import_sense_attributes(src, dst)
    import_semcor.import_sense_attributes(src, dst)
    assert dst.execute("SELECT COUNT(*) FROM sense_attributes").fetchone()[0] == 3
