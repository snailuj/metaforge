"""Automated filter for generated metaphor pairs.

Flags pairs that may need human review:
- Target word not in FastText vocabulary (no embeddings available)
- Duplicate targets within the new set
- Duplicate targets with the existing fixture
- Source word appears in existing fixture with same target
- Multi-word source or target
"""

import json
import sys
from pathlib import Path

FIXTURE_DIR = Path(__file__).parent.parent / "fixtures"
RAW_DIR = Path(__file__).parent.parent / "raw"


def load_fasttext_vocab(vec_path: Path, max_words: int = 200_000) -> set[str]:
    """Load vocabulary from FastText .vec file (first N words)."""
    vocab = set()
    with open(vec_path, "r", encoding="utf-8") as f:
        header = f.readline()  # skip header
        for i, line in enumerate(f):
            if i >= max_words:
                break
            word = line.split(" ", 1)[0]
            vocab.add(word.lower())
    return vocab


def run_filter(
    generated_path: Path,
    existing_path: Path,
    vec_path: Path,
) -> dict:
    """Run all filter checks and return categorised results."""
    with open(generated_path) as f:
        generated = json.load(f)
    with open(existing_path) as f:
        existing = json.load(f)

    print(f"Loading FastText vocabulary...", file=sys.stderr)
    vocab = load_fasttext_vocab(vec_path)
    print(f"  {len(vocab)} words loaded", file=sys.stderr)

    existing_targets = {p["target"].lower() for p in existing}
    existing_sources = {p["source"].lower() for p in existing}
    existing_pairs = {(p["source"].lower(), p["target"].lower()) for p in existing}

    flags: list[dict] = []
    clean: list[dict] = []

    # Track targets within generated set for duplicate detection
    seen_targets: dict[str, int] = {}

    for i, pair in enumerate(generated):
        src = pair["source"].lower()
        tgt = pair["target"].lower()
        pair_flags = []

        # Check target in FastText vocab
        if tgt not in vocab:
            pair_flags.append(f"target '{tgt}' not in FastText vocab")

        # Check source in FastText vocab
        if src not in vocab:
            pair_flags.append(f"source '{src}' not in FastText vocab")

        # Check for multi-word source or target
        if " " in pair["source"]:
            pair_flags.append(f"multi-word source: '{pair['source']}'")
        if " " in pair["target"]:
            pair_flags.append(f"multi-word target: '{pair['target']}'")

        # Duplicate target with existing fixture
        if tgt in existing_targets:
            pair_flags.append(f"target '{tgt}' already in existing fixture")

        # Duplicate pair with existing fixture
        if (src, tgt) in existing_pairs:
            pair_flags.append(f"exact pair '{src}→{tgt}' duplicates existing fixture")

        # Duplicate target within generated set
        if tgt in seen_targets:
            pair_flags.append(
                f"target '{tgt}' duplicates generated pair #{seen_targets[tgt] + 1}"
            )
        seen_targets[tgt] = i

        if pair_flags:
            flags.append({"index": i + 1, "pair": pair, "flags": pair_flags})
        else:
            clean.append(pair)

    return {
        "total": len(generated),
        "clean": len(clean),
        "flagged": len(flags),
        "flags": flags,
        "clean_pairs": clean,
    }


def main():
    generated_path = FIXTURE_DIR / "metaphor_pairs_generated.json"
    existing_path = FIXTURE_DIR / "metaphor_pairs.json"
    vec_path = RAW_DIR / "wiki-news-300d-1M.vec"

    if not vec_path.exists():
        print(f"Error: FastText vectors not found at {vec_path}", file=sys.stderr)
        sys.exit(1)

    results = run_filter(generated_path, existing_path, vec_path)

    print(f"\n{'='*60}")
    print(f"FILTER RESULTS")
    print(f"{'='*60}")
    print(f"Total pairs: {results['total']}")
    print(f"Clean: {results['clean']}")
    print(f"Flagged: {results['flagged']}")

    if results["flags"]:
        print(f"\n{'='*60}")
        print(f"FLAGGED PAIRS (need human review)")
        print(f"{'='*60}")
        for item in results["flags"]:
            p = item["pair"]
            print(f"\n  #{item['index']}: {p['source']} → {p['target']}  "
                  f"[{p['tier']}, {p['domain']}]")
            for flag in item["flags"]:
                print(f"    ⚠ {flag}")

    return results


if __name__ == "__main__":
    main()
