"""Import Brysbaert et al. (2014) concreteness ratings into synset_concreteness.

Reads the tab-separated concreteness ratings file, matches lemmas against our
lexicon, computes max concreteness per synset, and populates the
synset_concreteness table.

Usage:
    python import_concreteness.py
"""
import logging
import sqlite3
from pathlib import Path

log = logging.getLogger(__name__)

from utils import LEXICON_V2, BRYSBAERT_CONCRETENESS_TSV


def load_concreteness(tsv_path: Path) -> dict[str, float]:
    """Load concreteness ratings from the Brysbaert TSV.

    Returns dict mapping lowercase word -> concreteness mean (1.0-5.0).
    Skips bigrams (Bigram column = 1).
    """
    print(f"Loading concreteness data from {tsv_path.name}...")
    data: dict[str, float] = {}

    with open(tsv_path, "r", encoding="utf-8") as f:
        header = f.readline().strip().split("\t")
        for col in ("Word", "Conc.M", "Bigram"):
            if col not in header:
                raise ValueError(
                    f"Required column {col!r} not found in {tsv_path.name}. "
                    f"Available columns: {header}"
                )
        word_idx = header.index("Word")
        conc_m_idx = header.index("Conc.M")
        bigram_idx = header.index("Bigram")

        for line in f:
            fields = line.strip().split("\t")
            if len(fields) <= max(word_idx, conc_m_idx, bigram_idx):
                continue

            # Skip bigrams
            if fields[bigram_idx].strip() == "1":
                continue

            word = fields[word_idx].strip().lower()
            if not word:
                continue

            try:
                score = float(fields[conc_m_idx])
            except (ValueError, IndexError) as exc:
                log.warning("skipping row: word=%r raw_score=%r error=%s",
                            word, fields[conc_m_idx] if len(fields) > conc_m_idx else "<missing>",
                            exc)
                continue

            if word not in data:  # keep first occurrence
                data[word] = score

    print(f"  Loaded {len(data)} single-word entries")
    return data


def import_concreteness(
    conn: sqlite3.Connection,
    concreteness_data: dict[str, float],
) -> dict[str, int]:
    """Import concreteness ratings into synset_concreteness table.

    For each synset, collects all its lemmas, looks up each in
    concreteness_data, and stores the max score. Synsets with zero
    matching lemmas get no row.

    Returns stats dict with counts.
    """
    # Get all synset → lemmas mappings
    cursor = conn.execute("SELECT synset_id, lemma FROM lemmas")
    synset_lemmas: dict[str, list[str]] = {}
    for synset_id, lemma in cursor:
        synset_lemmas.setdefault(synset_id, []).append(lemma)

    print(f"  {len(synset_lemmas)} synsets in lexicon")

    # Clear existing data
    conn.execute("DELETE FROM synset_concreteness")

    rows = []
    stats = {"scored": 0, "unscored": 0, "total_synsets": len(synset_lemmas)}

    for synset_id, lemmas in synset_lemmas.items():
        scores = []
        for lemma in lemmas:
            if lemma in concreteness_data:
                scores.append(concreteness_data[lemma])

        if scores:
            max_score = max(scores)
            rows.append((synset_id, max_score, "brysbaert"))
            stats["scored"] += 1
        else:
            stats["unscored"] += 1

    conn.executemany(
        "INSERT OR REPLACE INTO synset_concreteness (synset_id, score, source) VALUES (?, ?, ?)",
        rows,
    )
    conn.commit()

    return stats


def main():
    if not BRYSBAERT_CONCRETENESS_TSV.exists():
        raise FileNotFoundError(
            f"Concreteness data not found: {BRYSBAERT_CONCRETENESS_TSV}"
        )
    if not LEXICON_V2.exists():
        raise FileNotFoundError(f"Lexicon DB not found: {LEXICON_V2}")

    concreteness_data = load_concreteness(BRYSBAERT_CONCRETENESS_TSV)

    conn = sqlite3.connect(LEXICON_V2)
    try:
        # Ensure table exists
        conn.execute("""CREATE TABLE IF NOT EXISTS synset_concreteness (
            synset_id TEXT PRIMARY KEY,
            score REAL NOT NULL,
            source TEXT NOT NULL,
            FOREIGN KEY (synset_id) REFERENCES synsets(synset_id)
        )""")
        stats = import_concreteness(conn, concreteness_data)
    finally:
        conn.close()

    coverage = stats["scored"] / stats["total_synsets"] * 100 if stats["total_synsets"] else 0
    print(f"\nImport complete:")
    print(f"  Scored:     {stats['scored']} ({coverage:.1f}%)")
    print(f"  Unscored:   {stats['unscored']}")
    print(f"  Total:      {stats['total_synsets']}")


if __name__ == "__main__":
    main()
