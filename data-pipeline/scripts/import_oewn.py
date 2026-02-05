"""Import OEWN core data from sqlunet_master.db to lexicon_v2.db."""
import sqlite3

from utils import SQLUNET_DB, LEXICON_V2


def import_synsets(src: sqlite3.Connection, dst: sqlite3.Connection):
    """Import synsets table."""
    print("Importing synsets...")
    cursor = src.execute("""
        SELECT synsetid, posid, definition
        FROM synsets
    """)

    rows = [(str(row[0]), row[1], row[2]) for row in cursor]
    dst.executemany(
        "INSERT OR IGNORE INTO synsets (synset_id, pos, definition) VALUES (?, ?, ?)",
        rows
    )
    print(f"  Imported {len(rows)} synsets")


def import_lemmas(src: sqlite3.Connection, dst: sqlite3.Connection):
    """Import lemma-synset mappings."""
    print("Importing lemmas...")
    cursor = src.execute("""
        SELECT DISTINCT w.word, se.synsetid
        FROM words w
        JOIN senses se ON se.wordid = w.wordid
    """)

    rows = [(row[0], str(row[1])) for row in cursor]
    dst.executemany(
        "INSERT OR IGNORE INTO lemmas (lemma, synset_id) VALUES (?, ?)",
        rows
    )
    print(f"  Imported {len(rows)} lemma-synset pairs")


def import_relations(src: sqlite3.Connection, dst: sqlite3.Connection):
    """Import semantic relations."""
    print("Importing relations...")
    cursor = src.execute("""
        SELECT synset1id, synset2id, relationid
        FROM semrelations
    """)

    rows = [(str(row[0]), str(row[1]), str(row[2])) for row in cursor]
    dst.executemany(
        "INSERT OR IGNORE INTO relations (source_synset, target_synset, relation_type) VALUES (?, ?, ?)",
        rows
    )
    print(f"  Imported {len(rows)} relations")


def main():
    if not SQLUNET_DB.exists():
        raise FileNotFoundError(f"Source DB not found: {SQLUNET_DB}")
    if not LEXICON_V2.exists():
        raise FileNotFoundError(f"Target DB not found: {LEXICON_V2}")

    src = sqlite3.connect(SQLUNET_DB)
    dst = sqlite3.connect(LEXICON_V2)

    import_synsets(src, dst)
    import_lemmas(src, dst)
    import_relations(src, dst)

    dst.commit()
    src.close()
    dst.close()
    print("OEWN import complete!")


if __name__ == "__main__":
    main()
