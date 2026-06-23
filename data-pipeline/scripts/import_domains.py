"""Import WordNet lexicographer-file domains from sqlunet_master.db.

The 45-row domains lookup is the target of synsets.domainid (carried by
import_oewn). A coarse semantic-type signal for M05/Bridge/thesaurus — NOT a
cascade aptness feature (see the SQLUNET data-strategy review, 2026-06-05).
"""
import sqlite3

from utils import SQLUNET_DB, LEXICON_V2


def import_domains(src: sqlite3.Connection, dst: sqlite3.Connection):
    """Import the 45 lexicographer-file domain definitions."""
    print("Importing WordNet domains...")
    cursor = src.execute("SELECT domainid, domain, domainname, posid FROM domains")
    rows = list(cursor)
    dst.executemany(
        "INSERT OR IGNORE INTO domains (domainid, domain, domainname, posid) VALUES (?, ?, ?, ?)",
        rows,
    )
    print(f"  Imported {len(rows)} domains")


def main():
    if not SQLUNET_DB.exists():
        raise FileNotFoundError(f"Source DB not found: {SQLUNET_DB}")
    if not LEXICON_V2.exists():
        raise FileNotFoundError(f"Target DB not found: {LEXICON_V2}")

    src = sqlite3.connect(SQLUNET_DB)
    try:
        dst = sqlite3.connect(LEXICON_V2)
        try:
            import_domains(src, dst)
            dst.commit()
        finally:
            dst.close()
    finally:
        src.close()
    print("Domains import complete!")


if __name__ == "__main__":
    main()
