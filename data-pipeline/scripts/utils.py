"""Shared utilities for data pipeline scripts."""
import json
import logging
import os
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import numpy.typing as npt

log = logging.getLogger(__name__)

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


@dataclass
class FastTextVectors:
    """In-memory FastText vector store.

    Stores all vectors as a single contiguous float32 matrix and a word→row-index
    map. This is ~10× more memory-efficient than the prior dict-of-Python-tuples
    representation (~11 GB → ~1.2 GB for 1M words at 300d) because Python floats
    and tuples carry per-object overhead that numpy avoids.
    """

    # shape: (N, EMBEDDING_DIM)
    matrix: npt.NDArray[np.float32]
    word_to_idx: dict[str, int]

    def __post_init__(self) -> None:
        # Defensive invariants: catch caller mistakes (wrong dtype/shape, drifted
        # row count) at construction time rather than letting them propagate as
        # silent corruption into downstream blob writes or cosine searches.
        if self.matrix.ndim != 2:
            raise ValueError(
                f"FastTextVectors.matrix must be 2D, got ndim={self.matrix.ndim}"
            )
        if self.matrix.shape[1] != EMBEDDING_DIM:
            raise ValueError(
                f"FastTextVectors.matrix shape[1] must equal EMBEDDING_DIM "
                f"({EMBEDDING_DIM}), got {self.matrix.shape[1]}"
            )
        if self.matrix.dtype != np.float32:
            raise ValueError(
                f"FastTextVectors.matrix dtype must be float32, got {self.matrix.dtype}"
            )
        if self.matrix.shape[0] != len(self.word_to_idx):
            raise ValueError(
                f"FastTextVectors row count mismatch: matrix has {self.matrix.shape[0]} "
                f"rows but word_to_idx has len={len(self.word_to_idx)}"
            )
        # Lock the matrix so a caller that accidentally mutates a returned row
        # gets a ValueError on assignment, not silent corruption of the shared
        # embedding store. np.mean / np.stack / .tobytes all copy, so existing
        # consumers are unaffected.
        self.matrix.flags.writeable = False

    def __contains__(self, word: str) -> bool:
        return word in self.word_to_idx

    def __getitem__(self, word: str) -> np.ndarray:
        # Returns the row directly (a view into the matrix). Callers must not
        # mutate it; treat as read-only.
        return self.matrix[self.word_to_idx[word]]

    def __len__(self) -> int:
        return len(self.word_to_idx)

    @property
    def dim(self) -> int:
        return int(self.matrix.shape[1])


_fasttext_cache: dict[str, FastTextVectors] = {}


def load_fasttext_vectors(vec_path: str) -> FastTextVectors:
    """Load FastText vectors from .vec file into a FastTextVectors container.

    Results are cached by path — subsequent calls return the same instance.
    Parses each row directly into a numpy float32 array, avoiding the
    per-float Python boxing overhead that previously dominated peak RSS.
    """
    if vec_path in _fasttext_cache:
        log.info("Using cached vectors for %s", vec_path)
        return _fasttext_cache[vec_path]

    log.info("Loading %s...", vec_path)

    with open(vec_path, "r", encoding="utf-8") as f:
        header = f.readline().strip().split()
        num_words, dim = int(header[0]), int(header[1])
        log.info("Header: %d words, %dd", num_words, dim)

        if dim != EMBEDDING_DIM:
            raise ValueError(
                f"FastText dimension mismatch: file has {dim}d, expected {EMBEDDING_DIM}d"
            )

        # Pre-allocate a generous matrix sized to the header. We'll trim down if
        # we drop malformed rows. Allocating up-front avoids the O(n) regrowth
        # cost of np.vstack/append and keeps a single contiguous buffer.
        matrix = np.empty((num_words, dim), dtype=np.float32)
        word_to_idx: dict[str, int] = {}
        next_idx = 0
        # Track skip reasons separately so the end-of-load warning can be
        # accurate. "Malformed" covers wrong column count and unparseable
        # floats; "duplicate" covers the first-occurrence-wins dedupe path.
        skipped_malformed = 0
        skipped_duplicate = 0

        for i, line in enumerate(f):
            parts = line.rstrip().split(" ")
            word = parts[0]
            values = parts[1:]
            if len(values) != dim:
                skipped_malformed += 1
                continue
            # First-occurrence-wins dedupe: skip later duplicates so we never
            # advance next_idx past a row we then overwrite the index for.
            # Without this, a duplicate word leaves an orphan row in the matrix
            # (matrix.shape[0] != len(word_to_idx)).
            if word in word_to_idx:
                skipped_duplicate += 1
                continue
            try:
                # float32 dtype: avoid intermediate float64 boxing — saves ~10× peak RSS during load.
                row = np.array(values, dtype=np.float32)
            except ValueError:
                skipped_malformed += 1
                continue
            matrix[next_idx] = row
            word_to_idx[word] = next_idx
            next_idx += 1

            if (i + 1) % 200000 == 0:
                log.info("Loaded %d words...", i + 1)

    if next_idx < num_words:
        # Trim unused rows so .matrix.shape[0] == len(word_to_idx).
        matrix = matrix[:next_idx].copy()

    log.info("Loaded %d vectors", len(word_to_idx))
    total_skipped = skipped_malformed + skipped_duplicate
    if total_skipped > 0:
        # Guard against degenerate `0 300` headers — percentage is undefined
        # when num_words is zero, so emit just the counts in that case.
        if num_words > 0:
            log.warning(
                "Skipped %d rows (%d malformed, %d duplicate, %.2f%% of header)",
                total_skipped, skipped_malformed, skipped_duplicate,
                total_skipped / num_words * 100,
            )
        else:
            log.warning(
                "Skipped %d rows (%d malformed, %d duplicate)",
                total_skipped, skipped_malformed, skipped_duplicate,
            )

    vectors = FastTextVectors(matrix=matrix, word_to_idx=word_to_idx)
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
