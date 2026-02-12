"""Shared utilities for data pipeline scripts."""
from pathlib import Path

# Directory layout
SCRIPTS_DIR = Path(__file__).parent
PIPELINE_DIR = SCRIPTS_DIR.parent
OUTPUT_DIR = PIPELINE_DIR / "output"
RAW_DIR = PIPELINE_DIR / "raw"

# Outputs
LEXICON_V2 = OUTPUT_DIR / "lexicon_v2.db"
PILOT_FILE = OUTPUT_DIR / "property_pilot_2k.json"

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
