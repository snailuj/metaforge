"""Shared utilities for data pipeline scripts."""
from pathlib import Path

# Database paths
SCRIPTS_DIR = Path(__file__).parent
OUTPUT_DIR = SCRIPTS_DIR.parent / "output"
LEXICON_V2 = OUTPUT_DIR / "lexicon_v2.db"
PILOT_FILE = OUTPUT_DIR / "property_pilot_2k.json"

# External data (in main project, not worktree)
PROJECT_ROOT = SCRIPTS_DIR.parent.parent.parent.parent
SQLUNET_DB = PROJECT_ROOT / "sqlunet_master.db"
FASTTEXT_VEC = PROJECT_ROOT / "sprint-zero" / "data-pipeline" / "output" / "wiki-news-300d-1M.vec"

# Embedding configuration
EMBEDDING_DIM = 300  # FastText 300d


def normalise(text: str) -> str:
    """Normalise property text: lowercase and strip whitespace."""
    return text.lower().strip()
