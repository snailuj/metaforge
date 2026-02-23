"""Consolidated downstream enrichment pipeline.

Takes enrichment JSON (from enrich_properties.py) and populates the lexicon DB:
  1. Curate properties — normalise, add FastText embeddings, flag OOV
  2. Populate synset_properties junction table
  3. Build curated vocabulary, cluster, snap, and generate antonyms

Each function takes a sqlite3.Connection and is independently importable.
The run_pipeline() orchestrator calls them in sequence.

Usage as CLI:
    python enrich_pipeline.py --db PATH --enrichment FILE --fasttext PATH
"""
import argparse
import json
import re
import sqlite3
import struct
import sys
from pathlib import Path
from typing import Optional

import nltk

sys.path.insert(0, str(Path(__file__).parent))
from utils import EMBEDDING_DIM, FASTTEXT_VEC, normalise
from build_vocab import build_and_store
from cluster_vocab import cluster_vocab
from snap_properties import snap_properties
from build_antonyms import build_antonym_table, build_cluster_antonym_table

# Lazy-download NLTK tagger data on first import
try:
    nltk.data.find("taggers/averaged_perceptron_tagger_eng")
except LookupError:
    nltk.download("averaged_perceptron_tagger_eng", quiet=True)

MAX_PROPERTIES_PER_SYNSET = 15


def _ensure_v2_schema(conn: sqlite3.Connection) -> None:
    """Apply v2 schema migrations: add salience columns, create lemma_metadata."""
    # Add columns to synset_properties if missing
    cols = {r[1] for r in conn.execute("PRAGMA table_info(synset_properties)").fetchall()}
    if "salience" not in cols:
        conn.execute("ALTER TABLE synset_properties ADD COLUMN salience REAL NOT NULL DEFAULT 1.0")
    if "property_type" not in cols:
        conn.execute("ALTER TABLE synset_properties ADD COLUMN property_type TEXT")
    if "relation" not in cols:
        conn.execute("ALTER TABLE synset_properties ADD COLUMN relation TEXT")

    # Create lemma_metadata table if missing
    conn.execute("""
        CREATE TABLE IF NOT EXISTS lemma_metadata (
            lemma       TEXT NOT NULL,
            synset_id   TEXT NOT NULL,
            register    TEXT CHECK (register IN ('formal', 'neutral', 'informal', 'slang')),
            connotation TEXT CHECK (connotation IN ('positive', 'neutral', 'negative')),
            PRIMARY KEY (lemma, synset_id)
        )
    """)
    conn.commit()


# =============================================================================
# MWE filter — strip adjectives/adverbs from multi-word properties
# =============================================================================

_STRIP_PREFIXES = ("JJ", "RB")


def filter_mwe(text: str) -> str | None:
    """Filter multi-word expressions by stripping adjectives/adverbs.

    Single tokens pass through unchanged. For multi-word inputs, POS-tag
    and remove JJ*/RB* words. Keep only if exactly 1 word remains.
    """
    tokens = text.split()
    if len(tokens) <= 1:
        return text
    tagged = nltk.pos_tag(tokens)
    kept = [word for word, tag in tagged if not tag.startswith(_STRIP_PREFIXES)]
    if len(kept) == 1:
        return kept[0]
    return None


# =============================================================================
# 1. Curate properties (from curate_properties.py)
# =============================================================================

_fasttext_cache: dict[str, dict[str, tuple[float, ...]]] = {}


def load_fasttext_vectors(vec_path: str) -> dict[str, tuple[float, ...]]:
    """Load FastText vectors from .vec file into memory.

    Results are cached by path — subsequent calls return the same dict.
    """
    if vec_path in _fasttext_cache:
        print(f"  Using cached vectors for {vec_path}")
        return _fasttext_cache[vec_path]

    vectors = {}
    print(f"  Loading {vec_path}...")

    with open(vec_path, "r", encoding="utf-8") as f:
        header = f.readline().strip().split()
        num_words, dim = int(header[0]), int(header[1])
        print(f"  Header: {num_words} words, {dim}d")

        for i, line in enumerate(f):
            parts = line.rstrip().split(" ")
            word = parts[0]
            try:
                vec = tuple(float(x) for x in parts[1:])
                if len(vec) == dim:
                    vectors[word] = vec
            except ValueError:
                continue

            if (i + 1) % 200000 == 0:
                print(f"    Loaded {i + 1} words...")

    print(f"  Loaded {len(vectors)} vectors")
    _fasttext_cache[vec_path] = vectors
    return vectors


def _get_embedding(
    word: str, vectors: dict[str, tuple[float, ...]]
) -> Optional[bytes]:
    """Get embedding bytes for a word, or None if OOV."""
    if word not in vectors:
        return None
    return struct.pack(f"{EMBEDDING_DIM}f", *vectors[word])


def _get_compound_embedding(
    text: str, vectors: dict[str, tuple[float, ...]]
) -> Optional[bytes]:
    """Get averaged embedding for compound/hyphenated words."""
    parts = re.split(r"[-\s/]", text)
    parts = [p.strip() for p in parts if p.strip()]

    if not parts:
        return None

    embeddings = []
    for part in parts:
        if part in vectors:
            embeddings.append(vectors[part])

    if not embeddings:
        return None

    avg = tuple(
        sum(e[i] for e in embeddings) / len(embeddings) for i in range(EMBEDDING_DIM)
    )
    return struct.pack(f"{EMBEDDING_DIM}f", *avg)


def _extract_property_text(prop) -> str | None:
    """Extract property text from v1 string or v2 structured object."""
    if isinstance(prop, dict):
        return prop.get("text")
    return prop


def curate_properties(
    conn: sqlite3.Connection,
    enrichment_data: dict,
    vectors: dict[str, tuple[float, ...]],
) -> int:
    """Normalise properties, add FastText embeddings, flag OOV.

    Handles both v1 (plain string) and v2 (structured object with .text) formats.

    Returns the number of properties inserted.
    """
    all_props = set()
    for synset in enrichment_data.get("synsets", []):
        for prop in synset.get("properties", [])[:MAX_PROPERTIES_PER_SYNSET]:
            raw_text = _extract_property_text(prop)
            if raw_text is None:
                continue
            filtered = filter_mwe(normalise(raw_text))
            if filtered is not None:
                all_props.add(filtered)

    count = 0
    for prop in sorted(all_props):
        emb = _get_embedding(prop, vectors)
        if emb is None and re.search(r"[-\s/]", prop):
            emb = _get_compound_embedding(prop, vectors)

        is_oov = 1 if emb is None else 0

        conn.execute(
            """INSERT OR IGNORE INTO property_vocabulary (text, embedding, is_oov, source)
               VALUES (?, ?, ?, 'pilot')""",
            (prop, emb, is_oov),
        )
        count += 1

    conn.commit()
    print(f"  Curated {count} properties")
    return count


# =============================================================================
# 2. Populate synset_properties (from populate_synset_properties.py)
# =============================================================================

def populate_synset_properties(
    conn: sqlite3.Connection,
    enrichment_data: dict,
    model_used: str,
) -> int:
    """Create enrichment entries and synset-property links.

    Handles both v1 (plain string) and v2 (structured object) property formats.
    For v2 objects, stores salience, property_type, and relation alongside
    the synset-property link. Also stores usage_example in the enrichment table.

    Returns the number of synset-property links created.
    """
    prop_ids = {}
    for row in conn.execute("SELECT property_id, text FROM property_vocabulary"):
        prop_ids[row[1]] = row[0]

    links = 0
    for synset in enrichment_data.get("synsets", []):
        synset_id = synset["id"]
        usage_example = synset.get("usage_example")

        conn.execute(
            """INSERT OR IGNORE INTO enrichment
               (synset_id, model_used, usage_example)
               VALUES (?, ?, ?)""",
            (synset_id, model_used, usage_example),
        )

        for prop in synset.get("properties", [])[:MAX_PROPERTIES_PER_SYNSET]:
            raw_text = _extract_property_text(prop)
            if raw_text is None:
                continue
            prop_filtered = filter_mwe(normalise(raw_text))
            if prop_filtered is None:
                continue
            if prop_filtered in prop_ids:
                salience = 1.0
                property_type = None
                relation = None
                if isinstance(prop, dict):
                    salience = prop.get("salience", 1.0)
                    property_type = prop.get("type")
                    relation = prop.get("relation")

                conn.execute(
                    """INSERT OR IGNORE INTO synset_properties
                       (synset_id, property_id, salience, property_type, relation)
                       VALUES (?, ?, ?, ?, ?)""",
                    (synset_id, prop_ids[prop_filtered], salience, property_type, relation),
                )
                links += 1

    conn.commit()
    print(f"  Created {links} synset-property links")
    return links


# =============================================================================
# 2b. Populate lemma metadata (register, connotation)
# =============================================================================

def populate_lemma_metadata(
    conn: sqlite3.Connection,
    enrichment_data: dict,
) -> int:
    """Store per-lemma register and connotation from v2 enrichment data.

    Returns the number of metadata entries inserted.
    """
    count = 0
    for synset in enrichment_data.get("synsets", []):
        synset_id = synset["id"]
        for meta in synset.get("lemma_metadata", []):
            conn.execute(
                """INSERT OR IGNORE INTO lemma_metadata
                   (lemma, synset_id, register, connotation)
                   VALUES (?, ?, ?, ?)""",
                (meta["lemma"], synset_id, meta.get("register"), meta.get("connotation")),
            )
            count += 1
    conn.commit()
    print(f"  Stored {count} lemma metadata entries")
    return count


# =============================================================================
# 3. Store lemma embeddings
# =============================================================================

def store_lemma_embeddings(
    conn: sqlite3.Connection,
    vectors: dict[str, tuple[float, ...]],
) -> int:
    """Store FastText embeddings for all known lemmas.

    Creates the lemma_embeddings table and populates it with packed 300d
    vectors for every lemma in the lemmas table that exists in the vectors
    dict.  OOV lemmas are excluded.

    Returns the number of embeddings stored.
    """
    conn.execute("""
        CREATE TABLE IF NOT EXISTS lemma_embeddings (
            lemma TEXT PRIMARY KEY,
            embedding BLOB NOT NULL
        )
    """)

    lemmas = conn.execute("SELECT DISTINCT lemma FROM lemmas").fetchall()

    count = 0
    for (lemma,) in lemmas:
        if lemma in vectors:
            blob = struct.pack(f"{EMBEDDING_DIM}f", *vectors[lemma])
            conn.execute(
                "INSERT OR REPLACE INTO lemma_embeddings (lemma, embedding) VALUES (?, ?)",
                (lemma, blob),
            )
            count += 1

    conn.commit()
    print(f"  Stored {count} lemma embeddings")
    return count


# =============================================================================
# Orchestrator
# =============================================================================

def run_pipeline(
    db_path: str,
    enrichment_files: list[str],
    fasttext_vec: str,
) -> dict:
    """Run the full downstream enrichment pipeline.

    Accepts one or more enrichment JSON files. FastText vectors are loaded
    once and reused across all files.

    Returns a stats dict.
    """
    print(f"=== Enrichment Pipeline ===")
    print(f"  DB: {db_path}")
    print(f"  Enrichment files: {len(enrichment_files)}")
    for f in enrichment_files:
        print(f"    {f}")

    vectors = load_fasttext_vectors(fasttext_vec)

    total_props = 0
    total_links = 0
    total_lemma_metadata = 0
    lemma_emb_count = 0

    conn = sqlite3.connect(db_path)
    try:
        _ensure_v2_schema(conn)

        # Process each enrichment file (curate + populate)
        for enrichment_file in enrichment_files:
            print(f"\n  --- Processing: {enrichment_file} ---")
            with open(enrichment_file) as f:
                data = json.load(f)

            model_used = data.get("config", {}).get("model", "unknown")

            total_props += curate_properties(conn, data, vectors)
            lemma_emb_count = store_lemma_embeddings(conn, vectors)
            total_links += populate_synset_properties(conn, data, model_used)
            total_lemma_metadata += populate_lemma_metadata(conn, data)

        # --- Curated vocabulary pipeline ---
        print("\n  --- Running downstream steps ---")
        print("  Building curated vocabulary...")
        vocab_entries = build_and_store(conn)
        print("  Clustering vocabulary...")
        cluster_stats = cluster_vocab(conn)
        print("  Snapping properties to curated vocabulary...")
        snap_stats = snap_properties(conn)
        print("  Building antonym pairs...")
        antonym_pairs = build_antonym_table(conn)
        print("  Building cluster antonym pairs...")
        cluster_antonym_pairs = build_cluster_antonym_table(conn)
    finally:
        conn.close()

    stats = {
        "properties_curated": total_props,
        "lemma_embeddings": lemma_emb_count,
        "synset_links": total_links,
        "lemma_metadata": total_lemma_metadata,
        "vocab_entries": vocab_entries,
        "vocab_clusters": cluster_stats.get("num_clusters", 0),
        "vocab_singletons": cluster_stats.get("singletons", 0),
        "snapped_properties": sum(snap_stats.values()) - snap_stats.get("dropped", 0),
        "antonym_pairs": antonym_pairs,
        "cluster_antonym_pairs": cluster_antonym_pairs,
    }
    print(f"=== Pipeline complete: {stats} ===")
    return stats


def main():
    parser = argparse.ArgumentParser(description="Run downstream enrichment pipeline")
    parser.add_argument("--db", required=True, help="Path to lexicon DB")
    parser.add_argument(
        "--enrichment", required=True, nargs="+",
        help="One or more enrichment JSON files",
    )
    parser.add_argument(
        "--fasttext",
        default=str(FASTTEXT_VEC),
        help="Path to FastText .vec file",
    )
    args = parser.parse_args()

    run_pipeline(args.db, args.enrichment, args.fasttext)


if __name__ == "__main__":
    main()
