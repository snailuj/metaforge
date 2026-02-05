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

# Embedding configuration
EMBEDDING_DIM = 300  # FastText 300d


def normalise(text: str) -> str:
    """Normalise property text: lowercase and strip whitespace."""
    return text.lower().strip()
