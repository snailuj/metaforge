"""Import SyntagNet collocation pairs."""
import sqlite3

from utils import SQLUNET_DB, LEXICON_V2


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


def count_orphan_syntagms(conn: sqlite3.Connection) -> tuple[int, int, float]:
    """Count syntagms with unlinked synsets.

    Returns (orphan_count, total_count, orphan_rate).
    """
    orphans = conn.execute("""
        SELECT COUNT(*) FROM syntagms st
        LEFT JOIN synsets s1 ON s1.synset_id = st.synset1id
        LEFT JOIN synsets s2 ON s2.synset_id = st.synset2id
        WHERE s1.synset_id IS NULL OR s2.synset_id IS NULL
    """).fetchone()[0]
    total = conn.execute("SELECT COUNT(*) FROM syntagms").fetchone()[0]
    rate = orphans / total if total > 0 else 0
    return orphans, total, rate


def main():
    if not SQLUNET_DB.exists():
        raise FileNotFoundError(f"Source DB not found: {SQLUNET_DB}")
    if not LEXICON_V2.exists():
        raise FileNotFoundError(f"Target DB not found: {LEXICON_V2}")

    src = sqlite3.connect(SQLUNET_DB)
    dst = sqlite3.connect(LEXICON_V2)

    import_syntagms(src, dst)

    dst.commit()

    # Count and log orphan syntagms
    orphans, total, rate = count_orphan_syntagms(dst)
    print(f"\nOrphan syntagm analysis:")
    print(f"  Total syntagms: {total}")
    print(f"  Orphans (unlinked synsets): {orphans}")
    print(f"  Orphan rate: {rate:.2%}")

    src.close()
    dst.close()
    print("\nSyntagNet import complete!")


if __name__ == "__main__":
    main()
