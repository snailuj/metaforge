"""Import SyntagNet collocation pairs."""
import sqlite3
from pathlib import Path

# Database is in main project root (parent of .worktrees)
SQLUNET_DB = Path(__file__).parent.parent.parent.parent.parent / "sqlunet_master.db"
LEXICON_V2 = Path(__file__).parent.parent / "output" / "lexicon_v2.db"


def import_syntagms(src: sqlite3.Connection, dst: sqlite3.Connection):
    """Import SyntagNet collocation pairs."""
    print("Importing SyntagNet syntagms...")
    # Filter to only include syntagms where both synsets exist
    cursor = src.execute("""
        SELECT syntagmid, synset1id, synset2id, sensekey1, sensekey2, word1id, word2id
        FROM sn_syntagms
        WHERE synset1id IS NOT NULL AND synset2id IS NOT NULL
    """)

    rows = [(row[0], str(row[1]), str(row[2]), row[3], row[4], row[5], row[6])
            for row in cursor]

    dst.executemany("""
        INSERT OR IGNORE INTO syntagms
        (syntagm_id, synset1id, synset2id, sensekey1, sensekey2, word1id, word2id)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, rows)
    print(f"  Imported {len(rows)} syntagms")


def main():
    if not SQLUNET_DB.exists():
        raise FileNotFoundError(f"Source DB not found: {SQLUNET_DB}")
    if not LEXICON_V2.exists():
        raise FileNotFoundError(f"Target DB not found: {LEXICON_V2}")

    src = sqlite3.connect(SQLUNET_DB)
    dst = sqlite3.connect(LEXICON_V2)

    import_syntagms(src, dst)

    dst.commit()
    src.close()
    dst.close()
    print("SyntagNet import complete!")


if __name__ == "__main__":
    main()
