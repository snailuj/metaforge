"""Build antonym pairs table from WordNet attribute relations.

WordNet attribute relations (relation_type '60') link adjective synsets to
shared attribute nouns. Adjectives sharing an attribute noun are typically
antonyms (hot/cold, light/dark, strong/weak).

Usage:
    python build_antonyms.py --db PATH
"""
import argparse
import sqlite3
import sys
from itertools import combinations
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from utils import LEXICON_V2


def build_antonym_table(conn: sqlite3.Connection) -> int:
    """Build property_antonyms from attribute relations.

    Finds adjective synsets that share an attribute noun (via relation_type '60'),
    filters to those present in property_vocab_curated, and stores bidirectional
    antonym pairs.

    Returns the number of unique antonym pairs found.
    """
    conn.executescript("""
        DROP TABLE IF EXISTS property_antonyms;
        CREATE TABLE property_antonyms (
            vocab_id_a  INTEGER NOT NULL,
            vocab_id_b  INTEGER NOT NULL,
            PRIMARY KEY (vocab_id_a, vocab_id_b)
        );
    """)

    # Find all attribute nouns and their linked adjective synsets
    # relation_type '60' = attribute relation (adjective -> attribute noun)
    attr_groups: dict[str, list[str]] = {}
    for adj_synset, attr_noun in conn.execute("""
        SELECT source_synset, target_synset
        FROM relations
        WHERE relation_type = '60'
    """):
        attr_groups.setdefault(attr_noun, []).append(adj_synset)

    # Load vocabulary synset -> vocab_id mapping
    vocab_map: dict[str, int] = {}
    for vid, sid in conn.execute(
        "SELECT vocab_id, synset_id FROM property_vocab_curated"
    ):
        vocab_map[sid] = vid

    # Generate antonym pairs: all combinations of adjectives sharing an attribute
    unique_pairs: set[tuple[int, int]] = set()
    for attr_noun, adj_synsets in attr_groups.items():
        # Filter to synsets in vocabulary
        vocab_ids = [vocab_map[s] for s in adj_synsets if s in vocab_map]
        if len(vocab_ids) < 2:
            continue

        for a, b in combinations(vocab_ids, 2):
            pair = (min(a, b), max(a, b))
            unique_pairs.add(pair)

    # Insert bidirectionally
    inserts = []
    for a, b in unique_pairs:
        inserts.append((a, b))
        inserts.append((b, a))

    conn.executemany(
        "INSERT OR IGNORE INTO property_antonyms (vocab_id_a, vocab_id_b) VALUES (?, ?)",
        inserts,
    )
    conn.commit()

    print(f"  Found {len(unique_pairs)} unique antonym pairs ({len(inserts)} bidirectional rows)")
    return len(unique_pairs)


def build_cluster_antonym_table(conn: sqlite3.Connection) -> int:
    """Lift property_antonyms from vocab_id pairs to cluster_id pairs.

    Reads property_antonyms + vocab_clusters.
    Writes cluster_antonyms table with deduplicated bidirectional pairs.

    Returns the number of unique cluster antonym pairs found.
    """
    conn.executescript("""
        DROP TABLE IF EXISTS cluster_antonyms;
        CREATE TABLE cluster_antonyms (
            cluster_id_a INTEGER NOT NULL,
            cluster_id_b INTEGER NOT NULL,
            PRIMARY KEY (cluster_id_a, cluster_id_b)
        );
    """)

    # Load cluster lookup
    cluster_lookup: dict[int, int] = {}
    for vid, cid in conn.execute("SELECT vocab_id, cluster_id FROM vocab_clusters"):
        cluster_lookup[vid] = cid

    # Map vocab antonym pairs to cluster pairs
    unique_pairs: set[tuple[int, int]] = set()
    for vid_a, vid_b in conn.execute(
        "SELECT vocab_id_a, vocab_id_b FROM property_antonyms"
    ):
        cid_a = cluster_lookup.get(vid_a, vid_a)
        cid_b = cluster_lookup.get(vid_b, vid_b)
        if cid_a == cid_b:
            continue  # skip self-antonym at cluster level
        pair = (min(cid_a, cid_b), max(cid_a, cid_b))
        unique_pairs.add(pair)

    # Insert bidirectionally
    inserts = []
    for a, b in unique_pairs:
        inserts.append((a, b))
        inserts.append((b, a))

    conn.executemany(
        "INSERT OR IGNORE INTO cluster_antonyms (cluster_id_a, cluster_id_b) VALUES (?, ?)",
        inserts,
    )
    conn.commit()

    print(f"  Found {len(unique_pairs)} unique cluster antonym pairs ({len(inserts)} bidirectional rows)")
    return len(unique_pairs)


def main():
    parser = argparse.ArgumentParser(description="Build antonym pairs from attribute relations")
    parser.add_argument("--db", default=str(LEXICON_V2), help="Path to lexicon DB")
    args = parser.parse_args()

    conn = sqlite3.connect(args.db)
    try:
        build_antonym_table(conn)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
