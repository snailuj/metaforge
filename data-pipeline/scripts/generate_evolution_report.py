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
import math
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


# --- Filtering helpers -------------------------------------------------------

def _baseline_trial(trials: list[dict]) -> dict:
    """Return the trial with trial_id 'baseline'."""
    return next(t for t in trials if t["trial_id"] == "baseline")


def _exploration_trials(trials: list[dict]) -> list[dict]:
    """Return generation 0 trials excluding baseline."""
    return [t for t in trials if t["generation"] == 0 and t["trial_id"] != "baseline"]


def _exploitation_trials(trials: list[dict]) -> list[dict]:
    """Return trials with generation > 0."""
    return [t for t in trials if t["generation"] > 0]


def _non_degenerate_trials(trials: list[dict]) -> list[dict]:
    """Return trials with MRR > 0."""
    return [t for t in trials if t["mrr"] > 0]


def _best_trial(trials: list[dict]) -> dict:
    """Return the trial with the highest MRR."""
    return max(trials, key=lambda t: t["mrr"])


def _lineages(trials: list[dict]) -> dict[str, list[dict]]:
    """Group trials by prompt_name, each sorted by generation ascending."""
    groups: dict[str, list[dict]] = {}
    for t in trials:
        groups.setdefault(t["prompt_name"], []).append(t)
    for name in groups:
        groups[name].sort(key=lambda t: t["generation"])
    return groups


# --- Metric helpers ----------------------------------------------------------

def _pearson_r(xs: list[float], ys: list[float]) -> float:
    """Compute Pearson correlation coefficient. Returns 0.0 if < 3 points."""
    n = len(xs)
    if n < 3:
        return 0.0
    mean_x = sum(xs) / n
    mean_y = sum(ys) / n
    cov = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))
    std_x = math.sqrt(sum((x - mean_x) ** 2 for x in xs))
    std_y = math.sqrt(sum((y - mean_y) ** 2 for y in ys))
    if std_x == 0 or std_y == 0:
        return 0.0
    return cov / (std_x * std_y)


def _avg_rr_by_pair(trials: list[dict]) -> dict[str, float]:
    """Compute mean reciprocal rank per source→target pair across all trials."""
    accum: dict[str, list[float]] = {}
    for t in trials:
        for p in t["per_pair"]:
            key = f"{p['source']} → {p['target']}"
            accum.setdefault(key, []).append(p.get("reciprocal_rank", 0.0))
    return {k: sum(v) / len(v) for k, v in accum.items()}


def _tier_mrr_split(trials: list[dict]) -> dict[str, float]:
    """Average MRR per tier across non-degenerate trials.

    Groups each trial's per_pair by tier, computes per-tier mean RR
    within each trial, then averages across non-degenerate trials.
    """
    nd = _non_degenerate_trials(trials)
    if not nd:
        return {}
    tier_sums: dict[str, list[float]] = {}
    for t in nd:
        tier_rrs: dict[str, list[float]] = {}
        for p in t["per_pair"]:
            tier = p.get("tier", "unknown")
            tier_rrs.setdefault(tier, []).append(p.get("reciprocal_rank", 0.0))
        for tier, rrs in tier_rrs.items():
            tier_sums.setdefault(tier, []).append(sum(rrs) / len(rrs))
    return {tier: sum(v) / len(v) for tier, v in tier_sums.items()}


def _hit_rate(trial: dict) -> float:
    """Fraction of pairs with reciprocal_rank > 0 in a single trial."""
    pairs = trial["per_pair"]
    if not pairs:
        return 0.0
    hits = sum(1 for p in pairs if p.get("reciprocal_rank", 0.0) > 0)
    return hits / len(pairs)


# --- Formatting helpers ------------------------------------------------------

def _format_pct(value: float) -> str:
    """Format a fractional value as a percentage string with sign prefix."""
    pct = value * 100
    if pct >= 0:
        return f"+{pct:.1f}%"
    return f"{pct:.1f}%"


def _format_correlation(r: float) -> str:
    """Describe a Pearson r value in plain English."""
    abs_r = abs(r)
    if abs_r >= 0.7:
        strength = "strong"
    elif abs_r >= 0.4:
        strength = "moderate"
    else:
        strength = "weak"
    if r >= 0:
        return f"{strength} positive"
    return f"{strength} negative"
