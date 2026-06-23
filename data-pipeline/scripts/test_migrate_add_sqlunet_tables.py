"""Test the additive SQLUNET migration on an EXISTING (pre-migration) DB.

Builds a minimal lexicon that predates the new tables (synsets WITHOUT domainid,
plus a sentinel enrichment row), runs the migration against a fixture source,
and asserts the new tables populate, domainid backfills, the pre-existing data
is preserved, and re-running is idempotent.
"""
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import migrate_add_sqlunet_tables as mig


def _existing_dst() -> sqlite3.Connection:
    """A lexicon as it looked BEFORE this migration: synsets has no domainid,
    and there is enrichment data that must survive untouched."""
    conn = sqlite3.connect(":memory:")
    conn.executescript(
        """
        CREATE TABLE synsets (synset_id TEXT PRIMARY KEY, pos TEXT NOT NULL, definition TEXT NOT NULL);
        CREATE TABLE enrichment (synset_id TEXT PRIMARY KEY, connotation TEXT);
        INSERT INTO synsets VALUES ('71587','n','the event of something burning'),
                                   ('21119','v','start firing a weapon');
        INSERT INTO enrichment VALUES ('71587','neutral');
        """
    )
    return conn


def _src() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.executescript(
        """
        CREATE TABLE domains (domainid INTEGER, domain TEXT, domainname TEXT, posid TEXT);
        INSERT INTO domains VALUES (26,'noun.event','noun.event','n'),(33,'verb.competition','verb.competition','v');
        CREATE TABLE synsets (synsetid INTEGER, posid TEXT, domainid INTEGER, definition TEXT);
        INSERT INTO synsets VALUES (71587,'n',26,'burning'),(21119,'v',33,'firing');
        CREATE TABLE words (wordid INTEGER, word TEXT);
        INSERT INTO words VALUES (10,'fire');
        CREATE TABLE senses (senseid INTEGER, sensekey TEXT, synsetid INTEGER, luid INTEGER,
            wordid INTEGER, casedwordid INTEGER, lexid INTEGER, sensenum INTEGER, tagcount INTEGER);
        INSERT INTO senses VALUES (1,'fire%1:11:00::',71587,1,10,NULL,11,1,43),
                                  (2,'fire%2:33:01::',21119,1,10,NULL,33,1,30);
        CREATE TABLE bnc_bncs (wordid INTEGER, posid TEXT, freq INTEGER, range INTEGER, disp REAL);
        INSERT INTO bnc_bncs VALUES (10,'n',500,1,0.5);
        CREATE TABLE sources (idsource INTEGER, name TEXT, version TEXT, wnversion TEXT, url TEXT, provider TEXT, reference TEXT);
        INSERT INTO sources VALUES (1,'WordNet','3.1','3.1',NULL,NULL,NULL);
        CREATE TABLE meta (created INTEGER, dbsize INTEGER, build TEXT);
        INSERT INTO meta VALUES ('2026-01-04', 1, 'b');
        """
    )
    return conn


def test_migration_adds_tables_and_backfills_domainid():
    src, dst = _src(), _existing_dst()
    mig.migrate(src, dst)
    dst.commit()
    assert dst.execute("SELECT COUNT(*) FROM sense_attributes").fetchone()[0] == 2
    assert dst.execute("SELECT COUNT(*) FROM domains").fetchone()[0] == 2
    assert dst.execute("SELECT COUNT(*) FROM bnc_frequencies").fetchone()[0] == 1
    assert dst.execute("SELECT COUNT(*) FROM seed_sources").fetchone()[0] == 1
    # domainid backfilled onto the pre-existing synsets
    assert dst.execute("SELECT domainid FROM synsets WHERE synset_id='71587'").fetchone()[0] == 26


def test_migration_preserves_existing_enrichment():
    src, dst = _src(), _existing_dst()
    mig.migrate(src, dst)
    dst.commit()
    assert dst.execute("SELECT connotation FROM enrichment WHERE synset_id='71587'").fetchone()[0] == "neutral"


def test_migration_idempotent():
    src, dst = _src(), _existing_dst()
    mig.migrate(src, dst)
    mig.migrate(src, dst)  # second run must not duplicate or error
    dst.commit()
    assert dst.execute("SELECT COUNT(*) FROM sense_attributes").fetchone()[0] == 2
    assert dst.execute("SELECT COUNT(*) FROM synsets WHERE domainid IS NOT NULL").fetchone()[0] == 2
