"""Shared utilities for data pipeline scripts."""
import json
import os
import subprocess
import tempfile
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

        skipped = 0
        for i, line in enumerate(f):
            parts = line.rstrip().split(" ")
            word = parts[0]
            try:
                vec = tuple(float(x) for x in parts[1:])
                if len(vec) == dim:
                    vectors[word] = vec
                else:
                    skipped += 1
            except ValueError:
                skipped += 1
                continue

            if (i + 1) % 200000 == 0:
                print(f"    Loaded {i + 1} words...")

    print(f"  Loaded {len(vectors)} vectors")
    if skipped > 0:
        print(f"  WARNING: skipped {skipped} malformed lines ({skipped / num_words * 100:.2f}%)")
    _fasttext_cache[vec_path] = vectors
    return vectors


# --- Checkpoint I/O -----------------------------------------------------------

def load_checkpoint(checkpoint_path: Path) -> dict:
    """Load checkpoint state from disk, or return empty state.

    Handles both unified format (synsets key) and legacy format (results key).
    Always returns with 'synsets' key for caller consistency.
    """
    if checkpoint_path.exists():
        try:
            with open(checkpoint_path) as f:
                data = json.load(f)
        except json.JSONDecodeError as e:
            print(f"  WARNING: corrupt checkpoint at {checkpoint_path}: {e}")
            print(f"  Starting from empty state. Corrupt file preserved as {checkpoint_path}.corrupt")
            checkpoint_path.rename(checkpoint_path.with_suffix(".json.corrupt"))
            return {"completed_ids": [], "synsets": []}
        # Backward compat: remap legacy 'results' key to 'synsets'
        if "results" in data and "synsets" not in data:
            data["synsets"] = data.pop("results")
        return data
    return {"completed_ids": [], "synsets": []}


def save_checkpoint(checkpoint_path: Path, state: dict):
    """Save checkpoint state to disk atomically.

    Writes to a temporary file then renames to prevent truncation on crash.
    """
    fd, tmp_path = tempfile.mkstemp(
        dir=checkpoint_path.parent, suffix=".tmp"
    )
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(state, f)
        Path(tmp_path).rename(checkpoint_path)
    except Exception:
        Path(tmp_path).unlink(missing_ok=True)
        raise


# --- Git metadata -------------------------------------------------------------

def get_git_commit() -> str:
    """Return short git commit hash, or 'unknown' on failure."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, timeout=5,
        )
        return result.stdout.strip() if result.returncode == 0 else "unknown"
    except (subprocess.SubprocessError, OSError):
        return "unknown"
