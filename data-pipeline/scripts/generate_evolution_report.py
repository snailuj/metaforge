"""Comprehensive report generator for evolutionary prompt optimisation experiments.

Reads experiment_log.json and metaphor_pairs.json, computes metrics,
optionally shells out to Claude CLI for analytical prose sections,
and produces a markdown report.

Usage:
    python generate_evolution_report.py
    python generate_evolution_report.py --no-llm          # skip LLM prose
    python generate_evolution_report.py --experiment-log path/to/log.json
"""
import json
from pathlib import Path

from utils import OUTPUT_DIR, PIPELINE_DIR


# --- Default paths -----------------------------------------------------------

DEFAULT_EXPERIMENT_LOG = OUTPUT_DIR / "evolution" / "experiment_log.json"
DEFAULT_PAIRS_FILE = PIPELINE_DIR / "fixtures" / "metaphor_pairs.json"
DEFAULT_OUTPUT = OUTPUT_DIR / "evolution" / "evolution_report.md"


# --- Data loading ------------------------------------------------------------

def load_experiment_log(path: Path) -> list[dict]:
    """Load experiment log from JSON file. Raises FileNotFoundError if missing."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Experiment log not found: {path}")
    with open(path) as f:
        return json.load(f)


def load_metaphor_pairs(path: Path) -> list[dict]:
    """Load metaphor pairs fixture from JSON file."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Metaphor pairs not found: {path}")
    with open(path) as f:
        return json.load(f)
