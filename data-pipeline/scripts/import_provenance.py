"""Import seed-data provenance (sources + meta) from sqlunet_master.db.

Copies the upstream-dataset manifest (WordNet/OEWN/VerbNet/BNC/SyntagNet
versions + licence references) and the build metadata into seed_sources /
seed_meta. The lexicon previously carried no provenance table; this is the
licence-audit anchor (see the SQLUNET data-strategy review, 2026-06-05).
"""
import sqlite3

from utils import SQLUNET_DB, LEXICON_V2


def import_sources(src: sqlite3.Connection, dst: sqlite3.Connection):
    """Import the upstream-dataset provenance manifest."""
    print("Importing seed sources...")
    cursor = src.execute(
        "SELECT idsource, name, version, wnversion, url, provider, reference FROM sources"
    )
    rows = list(cursor)
    dst.executemany(
        """INSERT OR IGNORE INTO seed_sources
           (idsource, name, version, wnversion, url, provider, reference)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        rows,
    )
    print(f"  Imported {len(rows)} sources")


def import_meta(src: sqlite3.Connection, dst: sqlite3.Connection):
    """Import the build metadata row (created / dbsize / build provenance)."""
    print("Importing build meta...")
    cursor = src.execute("SELECT created, dbsize, build FROM meta")
    rows = list(cursor)
    dst.executemany(
        "INSERT OR IGNORE INTO seed_meta (created, dbsize, build) VALUES (?, ?, ?)",
        rows,
    )
    print(f"  Imported {len(rows)} meta row(s)")


def main():
    if not SQLUNET_DB.exists():
        raise FileNotFoundError(f"Source DB not found: {SQLUNET_DB}")
    if not LEXICON_V2.exists():
        raise FileNotFoundError(f"Target DB not found: {LEXICON_V2}")

    src = sqlite3.connect(SQLUNET_DB)
    try:
        dst = sqlite3.connect(LEXICON_V2)
        try:
            import_sources(src, dst)
            import_meta(src, dst)
            dst.commit()
        finally:
            dst.close()
    finally:
        src.close()
    print("Provenance import complete!")


if __name__ == "__main__":
    main()
