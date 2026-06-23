"""Test WordNet lexicographer-domain import + synsets.domainid carry.

Fixture-based unit tests against the real SCHEMA.sql dest.
"""
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from utils import PIPELINE_DIR
import import_domains
import import_oewn

SCHEMA_SQL = (PIPELINE_DIR / "SCHEMA.sql").read_text()


def _dst() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.executescript(SCHEMA_SQL)
    return conn


def _src() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.executescript(
        """
        CREATE TABLE domains (domainid INTEGER, domain TEXT, domainname TEXT, posid TEXT);
        INSERT INTO domains VALUES (3,'noun.Tops','noun.Tops','n'),(4,'noun.act','noun.act','n');
        CREATE TABLE synsets (synsetid INTEGER, posid TEXT, domainid INTEGER, definition TEXT);
        INSERT INTO synsets VALUES (100,'n',4,'a test act'),(200,'v',4,'to test');
        """
    )
    return conn


def test_domains_imported():
    src, dst = _src(), _dst()
    import_domains.import_domains(src, dst)
    rows = dst.execute(
        "SELECT domainid, domain, posid FROM domains ORDER BY domainid"
    ).fetchall()
    assert rows == [(3, "noun.Tops", "n"), (4, "noun.act", "n")]


def test_synsets_carry_domainid():
    """import_oewn must now carry the dropped domainid onto each synset."""
    src, dst = _src(), _dst()
    import_oewn.import_synsets(src, dst)
    row = dst.execute("SELECT domainid, pos FROM synsets WHERE synset_id='100'").fetchone()
    assert row == (4, "n")  # domainid carried, synset_id stringified from INT


def test_domains_idempotent():
    src, dst = _src(), _dst()
    import_domains.import_domains(src, dst)
    import_domains.import_domains(src, dst)
    assert dst.execute("SELECT COUNT(*) FROM domains").fetchone()[0] == 2
