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


# --- Deterministic section generators ----------------------------------------

def section_methodology(trials: list[dict]) -> str:
    """Section 2: Methodology — derived from trial data, static description."""
    explore = _exploration_trials(trials)
    baseline = _baseline_trial(trials)
    pair_count = len(baseline["per_pair"]) if baseline["per_pair"] else 0
    exploit = _exploitation_trials(trials)

    lines = [
        "## 2. Methodology",
        "",
        f"The experiment evaluated **{len(explore)} exploration prompts** against a baseline, "
        f"scoring each on **{pair_count} metaphor pairs** using Mean Reciprocal Rank (MRR).",
        "",
        "**Procedure:**",
        "",
        "1. **Exploration (Gen 0):** Each prompt was used to enrich a sample of synsets "
        "with sensory/behavioural properties. The enriched lexicon was then queried via "
        "the Metaforge API to find each metaphor pair's target in the source's nearest "
        "neighbours. MRR across all pairs gives a single score per prompt.",
        "2. **Exploitation (Gen 1+):** Prompts that outperformed the baseline (survivors) "
        "were iteratively tweaked by an LLM. Each tweak was evaluated identically; "
        "improvements were kept, regressions reverted. Early stopping after consecutive "
        "failures prevented wasted budget.",
        "",
        f"Total trials: **{len(trials)}** "
        f"({1 + len(explore)} exploration, {len(exploit)} exploitation).",
        "",
    ]
    return "\n".join(lines)


def section_exploration_results(trials: list[dict]) -> str:
    """Section 3: Exploration results table — all gen 0 trials sorted by MRR desc."""
    gen0 = [t for t in trials if t["generation"] == 0]
    gen0.sort(key=lambda t: t["mrr"], reverse=True)

    lines = [
        "## 3. Exploration Results (Gen 0)",
        "",
        "| Prompt | MRR | unique_props | hapax_rate | avg_props/synset | hit_rate | survived |",
        "|--------|-----|-------------|------------|-----------------|----------|----------|",
    ]
    for t in gen0:
        sec = t.get("secondary", {})
        survived = "Yes" if t["survived"] else "No"
        hr = _hit_rate(t)
        lines.append(
            f"| {t['prompt_name']} | {t['mrr']:.4f} "
            f"| {sec.get('unique_properties', '-')} "
            f"| {sec.get('hapax_rate', 0):.3f} "
            f"| {sec.get('avg_properties_per_synset', 0):.1f} "
            f"| {hr:.3f} "
            f"| {survived} |"
        )
    lines.append("")
    return "\n".join(lines)


def section_cross_generation_analysis(trials: list[dict]) -> str:
    """Section 5: Correlations between MRR and secondary metrics."""
    nd = _non_degenerate_trials(trials)

    lines = [
        "## 5. Cross-Generation Analysis",
        "",
    ]

    if len(nd) < 3:
        lines.append("Insufficient non-degenerate trials for correlation analysis "
                      f"(need ≥ 3, have {len(nd)}).")
        lines.append("")
        return "\n".join(lines)

    mrrs = [t["mrr"] for t in nd]
    metrics = ["unique_properties", "hapax_rate", "avg_properties_per_synset"]

    lines.append("### Correlations (MRR vs secondary metrics)")
    lines.append("")
    lines.append("| Metric | Pearson r | Description |")
    lines.append("|--------|----------|-------------|")

    for metric in metrics:
        values = [t.get("secondary", {}).get(metric, 0) for t in nd]
        r = _pearson_r(mrrs, values)
        desc = _format_correlation(r)
        lines.append(f"| {metric} | {r:.3f} | {desc} |")

    # Hit rate correlation
    hit_rates = [_hit_rate(t) for t in nd]
    r = _pearson_r(mrrs, hit_rates)
    desc = _format_correlation(r)
    lines.append(f"| hit_rate | {r:.3f} | {desc} |")

    lines.append("")

    # Hit rate comparison table
    lines.append("### Hit Rate Comparison")
    lines.append("")
    lines.append("| Trial | MRR | Hit Rate |")
    lines.append("|-------|-----|----------|")
    for t in sorted(nd, key=lambda t: t["mrr"], reverse=True):
        lines.append(f"| {t['trial_id']} | {t['mrr']:.4f} | {_hit_rate(t):.3f} |")
    lines.append("")

    return "\n".join(lines)


def section_per_pair_analysis(trials: list[dict], pairs: list[dict]) -> str:
    """Section 6: Easiest/hardest pairs, never-found, tier split."""
    nd = _non_degenerate_trials(trials)
    avg_rr = _avg_rr_by_pair(nd) if nd else _avg_rr_by_pair(trials)
    sorted_pairs = sorted(avg_rr.items(), key=lambda x: x[1])

    lines = [
        "## 6. Per-Pair Analysis",
        "",
    ]

    # Top 10 easiest
    lines.append("### Easiest Pairs (highest avg RR)")
    lines.append("")
    for pair, avg in sorted_pairs[-10:][::-1]:
        lines.append(f"- {pair}: avg RR = {avg:.3f}")
    lines.append("")

    # Top 10 hardest
    lines.append("### Hardest Pairs (lowest avg RR)")
    lines.append("")
    for pair, avg in sorted_pairs[:10]:
        lines.append(f"- {pair}: avg RR = {avg:.3f}")
    lines.append("")

    # Never found
    never_found = [pair for pair, avg in sorted_pairs if avg == 0.0]
    if never_found:
        lines.append(f"### Never Found ({len(never_found)} pairs)")
        lines.append("")
        for pair in never_found:
            lines.append(f"- {pair}")
        lines.append("")

    # Tier split
    tier_split = _tier_mrr_split(trials)
    if tier_split:
        lines.append("### Tier Comparison")
        lines.append("")
        lines.append("| Tier | Avg RR |")
        lines.append("|------|--------|")
        for tier in sorted(tier_split.keys()):
            lines.append(f"| {tier} | {tier_split[tier]:.4f} |")
        lines.append("")

    return "\n".join(lines)


def section_appendix_prompts(trials: list[dict]) -> str:
    """Section 8: Appendix A — every unique prompt text in fenced code blocks."""
    lines = [
        "## 8. Appendix A: All Prompt Texts",
        "",
    ]

    seen_texts: set[str] = set()
    for t in trials:
        text = t["prompt_text"]
        if text in seen_texts:
            lines.append(f"### {t['trial_id']} (`{t['prompt_name']}`)")
            lines.append("")
            lines.append(f"*Same as earlier {t['prompt_name']} prompt.*")
            lines.append("")
            continue
        seen_texts.add(text)
        lines.append(f"### {t['trial_id']} (`{t['prompt_name']}`)")
        lines.append("")
        lines.append("```")
        lines.append(text)
        lines.append("```")
        lines.append("")

    return "\n".join(lines)


def section_appendix_per_pair_detail(trials: list[dict]) -> str:
    """Section 9: Appendix B — per-pair detail table for the best trial."""
    best = _best_trial(trials)

    lines = [
        "## 9. Appendix B: Per-Pair Detail (Best Trial)",
        "",
        f"Best trial: **{best['trial_id']}** (MRR = {best['mrr']:.4f})",
        "",
        "| Source | Target | Tier | Rank | Reciprocal Rank |",
        "|--------|--------|------|------|-----------------|",
    ]

    sorted_pairs = sorted(
        best["per_pair"],
        key=lambda p: p.get("reciprocal_rank", 0.0),
        reverse=True,
    )
    for p in sorted_pairs:
        rank = p.get("rank") or "—"
        rr = p.get("reciprocal_rank", 0.0)
        lines.append(
            f"| {p['source']} | {p['target']} | {p.get('tier', '—')} "
            f"| {rank} | {rr:.4f} |"
        )

    lines.append("")
    return "\n".join(lines)
