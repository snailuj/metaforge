# data-pipeline/scripts/01_import_wordnet.py
"""
Import Open English WordNet SQLite into our lexicon database.
Extracts synsets, lemmas, and relationships.
"""
import sqlite3
import gzip
from pathlib import Path
from tqdm import tqdm

RAW_DIR = Path(__file__).parent.parent / "raw"
OUTPUT_DIR = Path(__file__).parent.parent / "output"

def create_schema(conn: sqlite3.Connection):
    """Create lexicon database schema."""
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS synsets (
            synset_id TEXT PRIMARY KEY,
            pos TEXT NOT NULL,
            definition TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS lemmas (
            lemma TEXT NOT NULL,
            synset_id TEXT NOT NULL,
            FOREIGN KEY (synset_id) REFERENCES synsets(synset_id),
            PRIMARY KEY (lemma, synset_id)
        );

        CREATE TABLE IF NOT EXISTS relations (
            source_synset TEXT NOT NULL,
            target_synset TEXT NOT NULL,
            relation_type TEXT NOT NULL,
            FOREIGN KEY (source_synset) REFERENCES synsets(synset_id),
            FOREIGN KEY (target_synset) REFERENCES synsets(synset_id)
        );

        CREATE INDEX IF NOT EXISTS idx_lemmas_lemma ON lemmas(lemma);
        CREATE INDEX IF NOT EXISTS idx_relations_source ON relations(source_synset);
        CREATE INDEX IF NOT EXISTS idx_relations_type ON relations(relation_type);
    """)

def import_wordnet():
    """Import WordNet data into lexicon.db."""
    OUTPUT_DIR.mkdir(exist_ok=True)

    # Source WordNet DB - using oewn-2024.db as mentioned in the user's context
    wn_db_path = RAW_DIR / "oewn-2024.db"
    if not wn_db_path.exists():
        # Try the original filename if oewn-2024.db doesn't exist
        gz_path = RAW_DIR / "english-wordnet-2020.db.gz"
        if gz_path.exists():
            print(f"Decompressing {gz_path}...")
            with gzip.open(gz_path, 'rb') as f_in:
                with open(wn_db_path, 'wb') as f_out:
                    f_out.write(f_in.read())
        else:
            raise FileNotFoundError(f"WordNet DB not found at {wn_db_path} or {gz_path}")

    # Connect to source and destination
    src_conn = sqlite3.connect(wn_db_path)
    dst_conn = sqlite3.connect(OUTPUT_DIR / "lexicon.db")

    create_schema(dst_conn)

    # Import synsets with definitions
    print("Importing synsets...")
    cursor = src_conn.execute("""
        SELECT s.id, s.pos, d.definition 
        FROM synsets s
        LEFT JOIN definitions d ON s.rowid = d.synset_rowid
        WHERE d.definition IS NOT NULL
    """)
    synsets = cursor.fetchall()

    dst_conn.executemany(
        "INSERT OR REPLACE INTO synsets (synset_id, pos, definition) VALUES (?, ?, ?)",
        tqdm(synsets, desc="Synsets")
    )

    # Import lemmas (words) - need to join forms -> entries -> senses -> synsets
    print("Importing lemmas...")
    cursor = src_conn.execute("""
        SELECT DISTINCT f.form, s.id as synset_id
        FROM forms f
        JOIN entries e ON f.entry_rowid = e.rowid
        JOIN senses sn ON e.rowid = sn.entry_rowid
        JOIN synsets s ON sn.synset_rowid = s.rowid
        WHERE f.rank = 0  -- preferred lemma form
    """)
    lemmas = cursor.fetchall()

    dst_conn.executemany(
        "INSERT OR REPLACE INTO lemmas (lemma, synset_id) VALUES (?, ?)",
        tqdm(lemmas, desc="Lemmas")
    )

    # Import relations (synonymy, antonymy, hypernymy, etc.)
    print("Importing relations...")
    cursor = src_conn.execute("""
        SELECT s1.id as source_synset, s2.id as target_synset, rt.type as relation_type
        FROM synset_relations sr
        JOIN synsets s1 ON sr.source_rowid = s1.rowid
        JOIN synsets s2 ON sr.target_rowid = s2.rowid
        JOIN relation_types rt ON sr.type_rowid = rt.rowid
    """)
    relations = cursor.fetchall()

    dst_conn.executemany(
        "INSERT INTO relations (source_synset, target_synset, relation_type) VALUES (?, ?, ?)",
        tqdm(relations, desc="Relations")
    )

    dst_conn.commit()

    # Report stats
    synset_count = dst_conn.execute("SELECT COUNT(*) FROM synsets").fetchone()[0]
    lemma_count = dst_conn.execute("SELECT COUNT(*) FROM lemmas").fetchone()[0]
    relation_count = dst_conn.execute("SELECT COUNT(*) FROM relations").fetchone()[0]

    print(f"\nImported:")
    print(f"  {synset_count:,} synsets")
    print(f"  {lemma_count:,} lemmas")
    print(f"  {relation_count:,} relations")

    src_conn.close()
    dst_conn.close()

if __name__ == "__main__":
    import_wordnet()