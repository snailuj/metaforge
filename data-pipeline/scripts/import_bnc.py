"""Import BNC POS-resolved word frequency from sqlunet_master.db.

bnc_bncs keys on (wordid, posid); we resolve wordid->word and store
(lemma, pos, freq). The value is the POS split: it supplies the
POS-dominance topic filter (drop noun-lemma topics that are really
verb-dominant) which the word-level `frequencies` table cannot. See the
SQLUNET data-strategy review, 2026-06-05.
"""
import sqlite3

from utils import SQLUNET_DB, LEXICON_V2


def import_bnc(src: sqlite3.Connection, dst: sqlite3.Connection):
    """Import per-(lemma, POS) BNC frequency.

    (wordid, posid) is unique in the source and resolves 1:1 to (word, posid),
    so no aggregation is needed. Rows with NULL freq are skipped (the column is
    NOT NULL in bnc_frequencies and a null frequency carries no signal).
    """
    print("Importing BNC POS-resolved frequencies...")
    cursor = src.execute(
        """
        SELECT w.word, b.posid, b.freq
        FROM bnc_bncs b
        JOIN words w ON w.wordid = b.wordid
        WHERE b.freq IS NOT NULL
        """
    )
    rows = list(cursor)
    dst.executemany(
        "INSERT OR IGNORE INTO bnc_frequencies (lemma, pos, freq) VALUES (?, ?, ?)",
        rows,
    )
    print(f"  Imported {len(rows)} (lemma, POS) frequencies")


def main():
    if not SQLUNET_DB.exists():
        raise FileNotFoundError(f"Source DB not found: {SQLUNET_DB}")
    if not LEXICON_V2.exists():
        raise FileNotFoundError(f"Target DB not found: {LEXICON_V2}")

    src = sqlite3.connect(SQLUNET_DB)
    try:
        dst = sqlite3.connect(LEXICON_V2)
        try:
            import_bnc(src, dst)
            dst.commit()
        finally:
            dst.close()
    finally:
        src.close()
    print("BNC import complete!")


if __name__ == "__main__":
    main()
