"""Build curated property vocabulary from WordNet synsets.

Selects the least-polysemous lemma per synset, deduplicates surface forms,
and stores canonical entries in property_vocab_curated.

Usage:
    python build_vocab.py --db PATH [--top-n 35000]
"""
import argparse
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from utils import LEXICON_V2


def build_vocabulary(
    conn: sqlite3.Connection,
    top_n: int = 35000,
) -> list[dict]:
    """Build curated vocabulary entries from the lexicon.

    For each of the top-N synsets (ranked by max lemma familiarity):
    1. Compute polysemy count for each lemma
    2. Pick the least-polysemous lemma
    3. Greedy-deduplicate: if lemma already claimed, try the next option

    Returns list of dicts with keys: synset_id, lemma, pos, polysemy.
    """
    # Step 1: Polysemy count per lemma
    lemma_polysemy: dict[str, int] = {}
    for lemma, count in conn.execute(
        "SELECT lemma, COUNT(DISTINCT synset_id) FROM lemmas GROUP BY lemma"
    ):
        lemma_polysemy[lemma] = count

    # Step 2: Frequency data for ranking
    freq_data: dict[str, float] = {}
    for lemma, fam in conn.execute(
        "SELECT lemma, COALESCE(familiarity, 0) FROM frequencies"
    ):
        freq_data[lemma] = fam

    # Step 3: Synset metadata + lemma lists
    synset_pos: dict[str, str] = {}
    for sid, pos in conn.execute("SELECT synset_id, pos FROM synsets"):
        synset_pos[sid] = pos

    synset_lemmas: dict[str, list[str]] = {}
    for sid, lemma in conn.execute("SELECT synset_id, lemma FROM lemmas"):
        synset_lemmas.setdefault(sid, []).append(lemma)

    # Step 4: Rank synsets by max lemma familiarity
    synset_max_fam: dict[str, float] = {}
    for sid, lemmas in synset_lemmas.items():
        synset_max_fam[sid] = max(freq_data.get(lem, 0.0) for lem in lemmas)

    ranked = sorted(synset_max_fam.keys(), key=lambda s: synset_max_fam[s], reverse=True)
    subset = ranked[:top_n]

    # Step 5: Pick least-polysemous lemma with greedy dedup
    claimed: set[str] = set()
    entries: list[dict] = []

    for sid in subset:
        lemmas = synset_lemmas.get(sid, [])
        if not lemmas:
            continue

        # Sort by polysemy (ascending), then length (ascending), then alpha
        candidates = sorted(
            lemmas,
            key=lambda lem: (lemma_polysemy.get(lem, 1), len(lem), lem),
        )

        chosen = None
        chosen_poly = None
        for lem in candidates:
            if lem not in claimed:
                chosen = lem
                chosen_poly = lemma_polysemy.get(lem, 1)
                break

        if chosen is None:
            # All lemmas already claimed — use the least-polysemous anyway
            # and flag as shared (first candidate)
            chosen = candidates[0]
            chosen_poly = lemma_polysemy.get(chosen, 1)

        claimed.add(chosen)
        entries.append({
            "synset_id": sid,
            "lemma": chosen,
            "pos": synset_pos.get(sid, "?"),
            "polysemy": chosen_poly,
        })

    return entries


def build_and_store(
    conn: sqlite3.Connection,
    top_n: int = 35000,
) -> int:
    """Build vocabulary and store in property_vocab_curated table.

    Returns the number of entries stored.
    """
    entries = build_vocabulary(conn, top_n=top_n)

    conn.executescript("""
        DROP TABLE IF EXISTS property_vocab_curated;
        CREATE TABLE property_vocab_curated (
            vocab_id    INTEGER PRIMARY KEY,
            synset_id   TEXT NOT NULL,
            lemma       TEXT NOT NULL,
            pos         TEXT NOT NULL,
            polysemy    INTEGER NOT NULL,
            UNIQUE(synset_id)
        );
        CREATE INDEX idx_vocab_lemma ON property_vocab_curated(lemma);
    """)

    conn.executemany(
        "INSERT INTO property_vocab_curated (synset_id, lemma, pos, polysemy) VALUES (?, ?, ?, ?)",
        [(e["synset_id"], e["lemma"], e["pos"], e["polysemy"]) for e in entries],
    )
    conn.commit()

    print(f"  Stored {len(entries)} vocabulary entries")
    return len(entries)


def main():
    parser = argparse.ArgumentParser(description="Build curated property vocabulary")
    parser.add_argument("--db", default=str(LEXICON_V2), help="Path to lexicon DB")
    parser.add_argument("--top-n", type=int, default=35000, help="Top-N synsets by familiarity")
    args = parser.parse_args()

    conn = sqlite3.connect(args.db)
    try:
        count = build_and_store(conn, top_n=args.top_n)
        print(f"Done — {count} entries in property_vocab_curated")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
