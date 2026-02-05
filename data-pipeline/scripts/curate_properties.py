"""Curate property vocabulary: normalise, add FastText embeddings, flag OOV."""
import json
import sqlite3
import struct
from typing import Optional
import re

from utils import PILOT_FILE, LEXICON_V2, FASTTEXT_VEC, EMBEDDING_DIM, normalise


def load_fasttext_vectors(vec_path: Path) -> dict[str, tuple[float, ...]]:
    """Load FastText vectors from .vec file into memory.

    Returns dict mapping word -> tuple of floats.
    """
    vectors = {}
    print(f"  Loading {vec_path}...")

    with open(vec_path, "r", encoding="utf-8") as f:
        # First line is "num_words dimension"
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
                continue  # Skip malformed lines

            if (i + 1) % 200000 == 0:
                print(f"    Loaded {i + 1} words...")

    print(f"  Loaded {len(vectors)} vectors")
    return vectors


def get_embedding(word: str, vectors: dict[str, tuple[float, ...]]) -> Optional[bytes]:
    """Get embedding bytes for a word, or None if OOV."""
    if word not in vectors:
        return None
    return struct.pack(f"{EMBEDDING_DIM}f", *vectors[word])


def get_compound_embedding(
    text: str, vectors: dict[str, tuple[float, ...]]
) -> Optional[bytes]:
    """Get averaged embedding for compound/hyphenated words."""
    # Split on hyphen, space, or slash
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

    # Average the embeddings
    avg = tuple(
        sum(e[i] for e in embeddings) / len(embeddings) for i in range(EMBEDDING_DIM)
    )
    return struct.pack(f"{EMBEDDING_DIM}f", *avg)


def main():
    if not PILOT_FILE.exists():
        raise FileNotFoundError(f"Pilot file not found: {PILOT_FILE}")
    if not FASTTEXT_VEC.exists():
        raise FileNotFoundError(f"FastText vectors not found: {FASTTEXT_VEC}")

    print("Loading pilot data...")
    with open(PILOT_FILE) as f:
        pilot = json.load(f)

    print("Loading FastText vectors...")
    vectors = load_fasttext_vectors(FASTTEXT_VEC)
    print(f"  {len(vectors)} words in FastText vocabulary")

    # Collect all unique properties
    all_props = set()
    for synset in pilot["synsets"]:
        for prop in synset.get("properties", []):
            all_props.add(normalise(prop))

    print(f"  {len(all_props)} unique properties to process")

    # Process each property
    conn = sqlite3.connect(LEXICON_V2)

    oov_count = 0
    emb_count = 0
    oov_list = []

    for prop in sorted(all_props):
        # Try direct lookup first
        emb = get_embedding(prop, vectors)

        # Try compound if direct fails (handles hyphens, spaces, slashes)
        if emb is None and re.search(r"[-\s/]", prop):
            emb = get_compound_embedding(prop, vectors)

        is_oov = 1 if emb is None else 0
        if is_oov:
            oov_count += 1
            oov_list.append(prop)
        else:
            emb_count += 1

        conn.execute(
            """
            INSERT OR REPLACE INTO property_vocabulary (text, embedding, is_oov, source)
            VALUES (?, ?, ?, 'pilot')
        """,
            (prop, emb, is_oov),
        )

    conn.commit()
    conn.close()

    print(f"\nCuration complete!")
    print(f"  Properties with embeddings: {emb_count}")
    print(f"  OOV properties: {oov_count}")
    print(f"  Coverage: {emb_count / len(all_props):.1%}")

    if oov_list:
        print(f"\nOOV properties ({len(oov_list)}):")
        for prop in sorted(oov_list):
            print(f"  - {prop}")


if __name__ == "__main__":
    main()
