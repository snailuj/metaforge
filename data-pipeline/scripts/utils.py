"""Shared utilities for data pipeline scripts."""
from pathlib import Path

# Directory layout
SCRIPTS_DIR = Path(__file__).parent
PIPELINE_DIR = SCRIPTS_DIR.parent
OUTPUT_DIR = PIPELINE_DIR / "output"
RAW_DIR = PIPELINE_DIR / "raw"

# Outputs
LEXICON_V2 = OUTPUT_DIR / "lexicon_v2.db"

# Raw source data
SQLUNET_DB = RAW_DIR / "sqlunet_master.db"
FASTTEXT_VEC = RAW_DIR / "wiki-news-300d-1M.vec"

# Input data sources
INPUT_DIR = PIPELINE_DIR / "input"
MULTILEX_DIR = INPUT_DIR / "multilex-en"
SUBTLEX_DIR = INPUT_DIR / "subtlex-uk"

# Familiarity data
FAMILIARITY_FULL_XLSX = MULTILEX_DIR / "Full list GPT4 estimates familiarity and Multilex frequencies.xlsx"
FAMILIARITY_CLEANED_XLSX = MULTILEX_DIR / "Cleaned list GPT4 estimates familiarity and Multilex frequencies.xlsx"
MULTILEX_XLSX = MULTILEX_DIR / "Multilex English.xlsx"

# SUBTLEX-UK data
SUBTLEX_FLEMMAS_XLSX = SUBTLEX_DIR / "SUBTLEX-UK-flemmas.xlsx"
SUBTLEX_UK_XLSX = SUBTLEX_DIR / "SUBTLEX-UK.xlsx"

# Brysbaert concreteness ratings
BRYSBAERT_CONCRETENESS_TSV = RAW_DIR / "Concreteness_ratings_Brysbaert_et_al_BRM.txt"

# Familiarity thresholds (from Brysbaert 2025, tuneable)
FAMILIARITY_COMMON_THRESHOLD = 5.5   # >= 5.5 → common
FAMILIARITY_UNUSUAL_THRESHOLD = 3.5  # >= 3.5 → unusual, below → rare

# Zipf fallback thresholds (for words without familiarity data)
ZIPF_COMMON_THRESHOLD = 4.5   # >= 4.5 → common
ZIPF_UNUSUAL_THRESHOLD = 2.5  # >= 2.5 → unusual, below → rare

# Embedding configuration
EMBEDDING_DIM = 300  # FastText 300d


def normalise(text: str) -> str:
    """Normalise property text: lowercase and strip whitespace."""
    return text.lower().strip()


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

        if dim != EMBEDDING_DIM:
            raise ValueError(
                f"FastText dimension mismatch: file has {dim}d, expected {EMBEDDING_DIM}d"
            )

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
