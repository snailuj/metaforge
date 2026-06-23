"""Import SemCor sense attributes (sensekey + tagcount) from sqlunet_master.db.

The original import read `senses` only to manufacture (lemma, synset) pairs and
discarded the sense-level signal. This restores it for every sense:
  sensekey  the stable cross-resource sense id (unique, non-null across all senses)
  tagcount  the SemCor empirical usage count — the deterministic dominant-sense
            prior that unblocks topic disambiguation. NULL where SemCor never
            tagged the sense (~81%); LLM disambiguation remains the fallback.
See the SQLUNET data-strategy review, 2026-06-05.
"""
import sqlite3

from utils import SQLUNET_DB, LEXICON_V2


def import_sense_attributes(src: sqlite3.Connection, dst: sqlite3.Connection):
    """Import one row per sense: (sensekey, lemma, synset_id, sensenum, tagcount).

    synsetid is stringified to match the lexicon's TEXT synset_id spine. Senses
    without a sensekey are skipped (sensekey is the primary key; in the real
    source all 185k senses carry a unique non-null sensekey, but the guard keeps
    the importer robust to a malformed source).
    """
    print("Importing SemCor sense attributes...")
    cursor = src.execute(
        """
        SELECT se.sensekey, w.word, se.synsetid, se.sensenum, se.tagcount
        FROM senses se
        JOIN words w ON w.wordid = se.wordid
        WHERE se.sensekey IS NOT NULL
        """
    )
    rows = [(row[0], row[1], str(row[2]), row[3], row[4]) for row in cursor]
    dst.executemany(
        """INSERT OR IGNORE INTO sense_attributes
           (sensekey, lemma, synset_id, sensenum, tagcount)
           VALUES (?, ?, ?, ?, ?)""",
        rows,
    )
    tagged = sum(1 for r in rows if r[4] is not None and r[4] > 0)
    print(f"  Imported {len(rows)} sense attributes ({tagged} SemCor-tagged)")


def main():
    if not SQLUNET_DB.exists():
        raise FileNotFoundError(f"Source DB not found: {SQLUNET_DB}")
    if not LEXICON_V2.exists():
        raise FileNotFoundError(f"Target DB not found: {LEXICON_V2}")

    src = sqlite3.connect(SQLUNET_DB)
    try:
        dst = sqlite3.connect(LEXICON_V2)
        try:
            import_sense_attributes(src, dst)
            dst.commit()
        finally:
            dst.close()
    finally:
        src.close()
    print("SemCor import complete!")


if __name__ == "__main__":
    main()
