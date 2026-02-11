"""Curate a reusable benchmark set of synsets for prompt A/B testing.

Selects synsets from the high-reachability population (3+ lemmas),
stratified by POS, with a fixed random seed for reproducibility.

Usage:
    python curate_benchmark.py [--size 500] [--seed 42]

Output: data-pipeline/output/benchmark_<size>.json
"""
import argparse
import json
import sqlite3
from pathlib import Path

from utils import SQLUNET_DB, OUTPUT_DIR


# POS stratification weights (slightly flattened vs corpus to ensure
# meaningful representation of smaller POS categories)
POS_WEIGHTS = {
    'n': 0.50,   # nouns
    'v': 0.25,   # verbs
    'a': 0.10,   # adjectives (head)
    's': 0.10,   # adjectives (satellite)
    'r': 0.05,   # adverbs
}


def select_benchmark(conn: sqlite3.Connection, size: int, seed: int) -> list[dict]:
    """Select stratified benchmark synsets from 3+ lemma population."""
    synsets = []

    for pos, weight in POS_WEIGHTS.items():
        count = max(1, int(size * weight))

        # Use deterministic random via seed — SQLite's RANDOM() isn't seedable,
        # so we pull all candidates and slice in Python.
        cursor = conn.execute("""
            SELECT s.synsetid, s.definition, s.posid,
                   GROUP_CONCAT(DISTINCT w.word) as lemmas,
                   COUNT(DISTINCT w.word) as lemma_count
            FROM synsets s
            JOIN senses se ON se.synsetid = s.synsetid
            JOIN words w ON w.wordid = se.wordid
            WHERE s.posid = ?
            GROUP BY s.synsetid
            HAVING COUNT(DISTINCT w.word) >= 3
            ORDER BY s.synsetid
        """, (pos,))

        candidates = cursor.fetchall()

        # Deterministic shuffle
        import random
        rng = random.Random(seed)
        rng.shuffle(candidates)

        for row in candidates[:count]:
            lemmas = row[3].split(',')
            synsets.append({
                "id": str(row[0]),
                "definition": row[1],
                "pos": row[2],
                "lemma": lemmas[0],          # primary lemma for prompt
                "all_lemmas": lemmas,
                "lemma_count": row[4],
            })

    # Final shuffle so batches aren't POS-grouped
    rng.shuffle(synsets)

    return synsets


def main():
    parser = argparse.ArgumentParser(description="Curate benchmark synset set")
    parser.add_argument("--size", "-n", type=int, default=500,
                        help="Benchmark size (default: 500)")
    parser.add_argument("--seed", "-s", type=int, default=42,
                        help="Random seed for reproducibility (default: 42)")
    args = parser.parse_args()

    if not SQLUNET_DB.exists():
        raise FileNotFoundError(f"Database not found: {SQLUNET_DB}")

    conn = sqlite3.connect(SQLUNET_DB)
    synsets = select_benchmark(conn, args.size, args.seed)
    conn.close()

    # POS summary
    from collections import Counter
    pos_counts = Counter(s['pos'] for s in synsets)

    output = {
        "synsets": synsets,
        "meta": {
            "size": len(synsets),
            "seed": args.seed,
            "min_lemma_count": 3,
            "pos_distribution": dict(pos_counts),
            "source_db": str(SQLUNET_DB),
        }
    }

    output_file = OUTPUT_DIR / f"benchmark_{len(synsets)}.json"
    output_file.parent.mkdir(exist_ok=True)
    with open(output_file, 'w') as f:
        json.dump(output, f, indent=2)

    print(f"Benchmark curated: {len(synsets)} synsets")
    print(f"  POS distribution: {dict(pos_counts)}")
    print(f"  Avg lemma count: {sum(s['lemma_count'] for s in synsets) / len(synsets):.1f}")
    print(f"  Output: {output_file}")


if __name__ == "__main__":
    main()
