"""
Monosemy coverage analysis for the curated property vocabulary proposal.

For the top-N synsets (ranked by max lemma familiarity/zipf), measures:
  1. How many synsets have at least one monosemous lemma?
  2. Distribution of "least polysemous" lemma per synset
  3. Breakdown by POS
"""

import sqlite3
import sys
from pathlib import Path
from collections import Counter

DB_PATH = Path(__file__).parent.parent / "output" / "lexicon_v2.db"


def main():
    if not DB_PATH.exists():
        print(f"DB not found at {DB_PATH}", file=sys.stderr)
        sys.exit(1)

    conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    try:
        run_analysis(conn)
    finally:
        conn.close()


def run_analysis(conn: sqlite3.Connection):
    cur = conn.cursor()

    # Step 1: Polysemy count per lemma
    print("=== Building lemma polysemy counts ===")
    lemma_polysemy: dict[str, int] = {}
    for lemma, count in cur.execute(
        "SELECT lemma, COUNT(DISTINCT synset_id) FROM lemmas GROUP BY lemma"
    ):
        lemma_polysemy[lemma] = count

    total_lemmas = len(lemma_polysemy)
    mono_lemmas = sum(1 for c in lemma_polysemy.values() if c == 1)
    print(f"Total distinct lemmas: {total_lemmas:,}")
    print(f"Monosemous lemmas (1 synset): {mono_lemmas:,} "
          f"({100 * mono_lemmas / total_lemmas:.1f}%)")
    print()

    # Step 2: Frequency lookup (lemma -> familiarity, zipf)
    print("=== Loading frequency data ===")
    freq_data: dict[str, tuple[float, float]] = {}
    for lemma, fam, zipf in cur.execute(
        "SELECT lemma, COALESCE(familiarity, 0), COALESCE(zipf, 0) FROM frequencies"
    ):
        freq_data[lemma] = (fam, zipf)
    print(f"Frequency entries: {len(freq_data):,}")
    print()

    # Step 3: Build synset -> lemmas map and synset metadata
    print("=== Building synset data ===")
    synset_pos: dict[str, str] = {}
    for sid, pos in cur.execute("SELECT synset_id, pos FROM synsets"):
        synset_pos[sid] = pos

    synset_lemmas: dict[str, list[str]] = {}
    for sid, lemma in cur.execute("SELECT synset_id, lemma FROM lemmas"):
        synset_lemmas.setdefault(sid, []).append(lemma)

    # Step 4: Compute max familiarity per synset and rank
    synset_max_fam: dict[str, tuple[float, float]] = {}
    for sid, lemmas in synset_lemmas.items():
        max_fam = 0.0
        max_zipf = 0.0
        for lem in lemmas:
            fam, zipf = freq_data.get(lem, (0.0, 0.0))
            if fam > max_fam:
                max_fam = fam
            if zipf > max_zipf:
                max_zipf = zipf
        synset_max_fam[sid] = (max_fam, max_zipf)

    ranked_ids = sorted(
        synset_max_fam.keys(),
        key=lambda sid: synset_max_fam[sid],
        reverse=True
    )
    print(f"Total synsets with lemmas: {len(ranked_ids):,}")
    print()

    # Step 5: Analyse at each threshold
    for top_n in [5000, 10000, 20000, 35000]:
        actual_n = min(top_n, len(ranked_ids))
        subset = ranked_ids[:actual_n]

        has_mono = 0
        min_poly_dist = Counter()
        pos_stats: dict[str, dict[str, int]] = {}

        for sid in subset:
            pos = synset_pos.get(sid, "?")
            lemmas = synset_lemmas.get(sid, [])
            if not lemmas:
                continue

            poly_counts = [lemma_polysemy.get(lem, 1) for lem in lemmas]
            min_poly = min(poly_counts)
            min_poly_dist[min_poly] += 1

            if pos not in pos_stats:
                pos_stats[pos] = {"mono": 0, "total": 0}
            pos_stats[pos]["total"] += 1
            if min_poly == 1:
                has_mono += 1
                pos_stats[pos]["mono"] += 1

        print(f"=== Top {actual_n:,} synsets (by max lemma familiarity) ===")
        print(f"Synsets with >= 1 monosemous lemma: {has_mono:,} / {actual_n:,} "
              f"({100 * has_mono / actual_n:.1f}%)")
        print()

        print("  By POS:")
        for pos in sorted(pos_stats.keys()):
            s = pos_stats[pos]
            pct = 100 * s["mono"] / s["total"] if s["total"] else 0
            print(f"    {pos}: {s['mono']:,} / {s['total']:,} ({pct:.1f}%)")
        print()

        print("  Least-polysemous lemma distribution:")
        for poly in sorted(min_poly_dist.keys())[:10]:
            n = min_poly_dist[poly]
            pct = 100 * n / actual_n
            label = "monosemous" if poly == 1 else f"{poly} senses"
            print(f"    {label}: {n:,} ({pct:.1f}%)")
        over10 = sum(n for k, n in min_poly_dist.items() if k > 10)
        if over10:
            print(f"    >10 senses: {over10:,} ({100 * over10 / actual_n:.1f}%)")
        print()

        print("  Cumulative (least-polysemous lemma has at most N senses):")
        for threshold in [1, 2, 3, 5, 10]:
            cum = sum(n for k, n in min_poly_dist.items() if k <= threshold)
            print(f"    <= {threshold} senses: {cum:,} ({100 * cum / actual_n:.1f}%)")
        print()
        print("-" * 60)
        print()


if __name__ == "__main__":
    main()
