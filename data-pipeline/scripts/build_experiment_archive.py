"""Build SQLite archive of all enrichment experiment data.

Creates a self-contained database with:
- Benchmark synsets
- All variant results (A, B, C)
- Prompt texts
- Computed metrics per synset

Usage:
    python build_experiment_archive.py
"""
import json
import sqlite3
from pathlib import Path

from utils import OUTPUT_DIR

ARCHIVE_PATH = OUTPUT_DIR / "enrichment_experiment.db"

# Prompt texts — stored verbatim for reproducibility
PROMPT_TEXTS = {
    "A": "Original prompt, 5-10 properties. Categories: Physical, Behavioural, Perceptual, Functional. Examples show 7 props each.",
    "B": "Dual-dimension prompt, 10-15 properties. Explicit SENSORY + STRUCTURAL/FUNCTIONAL split. Examples show 12 props each.",
    "C": "Original prompt (identical to A), 10-15 properties. Same categories, same examples as A. Only count instruction changed.",
}


def create_schema(conn: sqlite3.Connection):
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS variants (
            variant_id TEXT PRIMARY KEY,
            description TEXT NOT NULL,
            prompt_type TEXT NOT NULL,     -- 'original' or 'dual-dimension'
            property_range TEXT NOT NULL,  -- '5-10' or '10-15'
            model TEXT NOT NULL,
            total_synsets INTEGER,
            total_properties INTEGER,
            unique_properties INTEGER,
            avg_per_synset REAL,
            failed_batches INTEGER
        );

        CREATE TABLE IF NOT EXISTS benchmark_synsets (
            synset_id TEXT PRIMARY KEY,
            lemma TEXT NOT NULL,
            definition TEXT NOT NULL,
            pos TEXT NOT NULL,
            all_lemmas TEXT,
            lemma_count INTEGER
        );

        CREATE TABLE IF NOT EXISTS synset_results (
            variant_id TEXT NOT NULL,
            synset_id TEXT NOT NULL,
            lemma TEXT NOT NULL,
            definition TEXT NOT NULL,
            pos TEXT,
            property_count INTEGER NOT NULL,
            properties_json TEXT NOT NULL,  -- JSON array of property strings
            PRIMARY KEY (variant_id, synset_id),
            FOREIGN KEY (variant_id) REFERENCES variants(variant_id)
        );

        CREATE TABLE IF NOT EXISTS properties (
            variant_id TEXT NOT NULL,
            synset_id TEXT NOT NULL,
            property TEXT NOT NULL,
            FOREIGN KEY (variant_id) REFERENCES variants(variant_id)
        );

        CREATE INDEX IF NOT EXISTS idx_props_variant ON properties(variant_id);
        CREATE INDEX IF NOT EXISTS idx_props_property ON properties(property);
        CREATE INDEX IF NOT EXISTS idx_props_synset ON properties(variant_id, synset_id);

        CREATE TABLE IF NOT EXISTS prompt_texts (
            variant_id TEXT PRIMARY KEY,
            full_prompt TEXT NOT NULL
        );
    """)


def load_variant_data(conn: sqlite3.Connection, variant_id: str,
                      data: dict, prompt_type: str, prop_range: str):
    """Load a variant's results into the archive."""
    stats = data.get('stats', {})
    config = data.get('config', {})

    conn.execute("""
        INSERT OR REPLACE INTO variants
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        variant_id,
        PROMPT_TEXTS[variant_id],
        prompt_type,
        prop_range,
        config.get('model', 'gemini-2.5-flash'),
        stats.get('total_synsets', 0),
        stats.get('total_properties', 0),
        stats.get('unique_properties', 0),
        stats.get('avg_properties_per_synset', 0),
        stats.get('failed_batches', 0),
    ))

    for synset in data.get('synsets', []):
        props = synset.get('properties', [])
        conn.execute("""
            INSERT OR REPLACE INTO synset_results
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            variant_id,
            synset['id'],
            synset['lemma'],
            synset['definition'],
            synset.get('pos', ''),
            len(props),
            json.dumps(props),
        ))

        for prop in props:
            conn.execute("""
                INSERT INTO properties VALUES (?, ?, ?)
            """, (variant_id, synset['id'], prop))


def load_benchmark(conn: sqlite3.Connection, benchmark: dict):
    """Load benchmark synset metadata."""
    for s in benchmark.get('synsets', []):
        conn.execute("""
            INSERT OR REPLACE INTO benchmark_synsets
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            s['id'],
            s['lemma'],
            s['definition'],
            s['pos'],
            json.dumps(s.get('all_lemmas', [])),
            s.get('lemma_count', 0),
        ))


def main():
    if ARCHIVE_PATH.exists():
        ARCHIVE_PATH.unlink()

    conn = sqlite3.connect(ARCHIVE_PATH)
    create_schema(conn)

    # Load benchmark
    with open(OUTPUT_DIR / "benchmark_500.json") as f:
        benchmark = json.load(f)
    load_benchmark(conn, benchmark)
    print(f"Loaded {len(benchmark['synsets'])} benchmark synsets")

    # Load each variant
    variants = {
        'A': ('original', '5-10'),
        'B': ('dual-dimension', '10-15'),
        'C': ('original', '10-15'),
    }

    # Store full prompt texts from enrich_ab.py
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "enrich_ab",
        Path(__file__).parent / "enrich_ab.py"
    )
    mod = importlib.util.module_from_spec(spec)
    # We only need the PROMPTS dict — avoid running main()
    import types
    # Manually extract prompt constants by reading the file
    enrich_path = Path(__file__).parent / "enrich_ab.py"
    enrich_source = enrich_path.read_text()

    for variant_id, (prompt_type, prop_range) in variants.items():
        variant_file = OUTPUT_DIR / f"ab_variant_{variant_id}.json"
        if not variant_file.exists():
            print(f"Skipping variant {variant_id}: file not found")
            continue

        with open(variant_file) as f:
            data = json.load(f)

        load_variant_data(conn, variant_id, data, prompt_type, prop_range)
        print(f"Loaded variant {variant_id}: {data['stats']['total_synsets']} synsets, "
              f"{data['stats']['unique_properties']} unique properties")

    # Store prompt texts (extract from enrich_ab.py source)
    import re
    for variant_id in ['A', 'B', 'C']:
        pattern = rf'PROMPT_{variant_id}\s*=\s*"""(.*?)"""'
        match = re.search(pattern, enrich_source, re.DOTALL)
        if match:
            conn.execute(
                "INSERT OR REPLACE INTO prompt_texts VALUES (?, ?)",
                (variant_id, match.group(1))
            )

    conn.commit()

    # Print summary
    print(f"\nArchive created: {ARCHIVE_PATH}")
    print(f"  Size: {ARCHIVE_PATH.stat().st_size / 1024:.0f} KB")

    # Quick verification
    for row in conn.execute("SELECT variant_id, total_synsets, unique_properties, avg_per_synset FROM variants"):
        print(f"  {row[0]}: {row[1]} synsets, {row[2]} unique props, avg {row[3]:.2f}")

    total_props = conn.execute("SELECT COUNT(*) FROM properties").fetchone()[0]
    print(f"  Total property rows: {total_props}")

    conn.close()


if __name__ == "__main__":
    main()
