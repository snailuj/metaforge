"""Test seed-data provenance import (sources + meta) from sqlunet_master.db.

Fixture-based unit tests: a minimal in-memory SQLUNET source + a dest built
from the real SCHEMA.sql, so the test exercises the canonical DDL and catches
script/schema drift. Post-rebuild row-count checks live in the validation step.
"""
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from utils import PIPELINE_DIR
import import_provenance

SCHEMA_SQL = (PIPELINE_DIR / "SCHEMA.sql").read_text()


def _dst() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.executescript(SCHEMA_SQL)
    return conn


def _src() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.executescript(
        """
        CREATE TABLE sources (idsource INTEGER, name TEXT, version TEXT,
                              wnversion TEXT, url TEXT, provider TEXT, reference TEXT);
        CREATE TABLE meta (created INTEGER, dbsize INTEGER, build TEXT);
        INSERT INTO sources VALUES
            (1,'WordNet','3.1','3.1',NULL,NULL,NULL),
            (40,'BNC','2001','any',NULL,NULL,NULL);
        INSERT INTO meta VALUES ('2026-01-04 07:51:17', 595996672,
            'BRANCH: 3_oewn_with_collocations');
        """
    )
    return conn


def test_sources_imported():
    src, dst = _src(), _dst()
    import_provenance.import_sources(src, dst)
    rows = dst.execute(
        "SELECT idsource, name, version, wnversion FROM seed_sources ORDER BY idsource"
    ).fetchall()
    assert rows == [(1, "WordNet", "3.1", "3.1"), (40, "BNC", "2001", "any")]


def test_meta_imported():
    src, dst = _src(), _dst()
    import_provenance.import_meta(src, dst)
    row = dst.execute("SELECT created, dbsize, build FROM seed_meta").fetchone()
    assert row[1] == 595996672
    assert "oewn" in row[2].lower()


def test_idempotent_reimport():
    """Re-running the import must not duplicate rows (idempotency standard)."""
    src, dst = _src(), _dst()
    import_provenance.import_sources(src, dst)
    import_provenance.import_sources(src, dst)
    count = dst.execute("SELECT COUNT(*) FROM seed_sources").fetchone()[0]
    assert count == 2
