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
import re
from pathlib import Path

from enrich_properties import invoke_claude
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
    """Return trials with MRR > 0 and valid=True (excludes infra failures)."""
    return [t for t in trials if t["mrr"] > 0 and t.get("valid", True)]


def _infrastructure_failed_trials(trials: list[dict]) -> list[dict]:
    """Return trials where valid=False (infrastructure/API failures)."""
    return [t for t in trials if not t.get("valid", True)]


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


# --- LLM prose helpers -------------------------------------------------------

def _build_briefing(trials: list[dict], pairs: list[dict]) -> dict:
    """Compute all metrics into a structured dict for LLM consumption."""
    baseline = _baseline_trial(trials)
    best = _best_trial(trials)
    nd = _non_degenerate_trials(trials)
    explore = _exploration_trials(trials)
    exploit = _exploitation_trials(trials)
    survivors = [t for t in explore if t["survived"]]

    improvement = (best["mrr"] - baseline["mrr"]) / baseline["mrr"] if baseline["mrr"] > 0 else 0.0

    # Correlations
    correlations = {}
    if len(nd) >= 3:
        mrrs = [t["mrr"] for t in nd]
        for metric in ["unique_properties", "hapax_rate", "avg_properties_per_synset"]:
            values = [t.get("secondary", {}).get(metric, 0) for t in nd]
            r = _pearson_r(mrrs, values)
            correlations[metric] = {"r": round(r, 3), "description": _format_correlation(r)}
        hit_rates = [_hit_rate(t) for t in nd]
        r = _pearson_r(mrrs, hit_rates)
        correlations["hit_rate"] = {"r": round(r, 3), "description": _format_correlation(r)}

    # Lineage summaries
    lineage_data = {}
    for name, lineage in _lineages(trials).items():
        if name == "baseline":
            continue
        lineage_data[name] = [
            {
                "trial_id": t["trial_id"],
                "generation": t["generation"],
                "mrr": t["mrr"],
                "survived": t["survived"],
                "mutation": t.get("mutation"),
            }
            for t in lineage
        ]

    # Degenerate trials (MRR=0, but valid — bad prompt, not infra failure)
    degenerate = [t["trial_id"] for t in trials
                  if t["mrr"] == 0.0 and t.get("valid", True)]

    # Infrastructure failures (valid=False)
    infra_failed = [t["trial_id"] for t in trials if not t.get("valid", True)]

    return {
        "best_trial_id": best["trial_id"],
        "best_mrr": best["mrr"],
        "baseline_mrr": baseline["mrr"],
        "improvement_pct": _format_pct(improvement),
        "improvement_raw": round(improvement, 4),
        "survivor_count": len(survivors),
        "total_trials": len(trials),
        "exploration_count": len(explore),
        "exploitation_count": len(exploit),
        "pair_count": len(baseline.get("per_pair", [])),
        "correlations": correlations,
        "tier_split": _tier_mrr_split(trials),
        "lineages": lineage_data,
        "degenerate_trials": degenerate,
        "infra_failed_trials": infra_failed,
    }


def _executive_summary_prompt(briefing: dict) -> str:
    """Build the meta-prompt for executive summary LLM generation."""
    return (
        "You are writing a concise executive summary paragraph for a prompt "
        "optimisation experiment report. Here are the key metrics:\n\n"
        f"- Total trials: {briefing['total_trials']}\n"
        f"- Best trial: {briefing['best_trial_id']} (MRR = {briefing['best_mrr']})\n"
        f"- Baseline MRR: {briefing['baseline_mrr']}\n"
        f"- Improvement: {briefing['improvement_pct']}\n"
        f"- Survivors: {briefing['survivor_count']} out of {briefing['exploration_count']}\n"
        f"- Degenerate trials (MRR=0): {len(briefing['degenerate_trials'])}\n\n"
        "Write a single analytical paragraph summarising the experiment outcomes. "
        "Be concise, factual, and highlight the most important findings. "
        "Do not use markdown headers. Output only the paragraph text."
    )


def _exploitation_narrative_prompt(briefing: dict) -> str:
    """Build the meta-prompt for exploitation lineage narratives."""
    return (
        "You are writing brief analytical narratives for each lineage in a prompt "
        "optimisation experiment. Here is the lineage data:\n\n"
        f"{json.dumps(briefing['lineages'], indent=2)}\n\n"
        "For each lineage, write 2-3 sentences explaining what mutations were tried "
        "and why they succeeded or failed. Format as markdown with ### headers for "
        "each lineage name. Be concise and analytical."
    )


def _discussion_prompt(briefing: dict) -> str:
    """Build the meta-prompt for the discussion section."""
    return (
        "You are writing the Discussion section of a prompt optimisation experiment report. "
        "Here is a comprehensive data briefing:\n\n"
        f"```json\n{json.dumps(briefing, indent=2)}\n```\n\n"
        "Write an analytical discussion covering:\n"
        "1. What prompt characteristics correlated with higher MRR\n"
        "2. Why certain exploitation tweaks succeeded or failed\n"
        "3. Tier performance patterns (strong vs medium metaphor pairs)\n"
        "4. Failure modes and degenerate trials\n"
        "5. Recommendations for the next iteration\n\n"
        "Use markdown subheadings (###). Be concise, data-driven, and analytical. "
        "Reference specific numbers from the briefing."
    )


def _llm_prose(briefing: dict, section_prompt: str, model: str = "haiku") -> str:
    """Invoke Claude CLI and extract the result text."""
    proc = invoke_claude(section_prompt, model=model)

    events = json.loads(proc.stdout)
    result_event = next(
        (e for e in reversed(events) if e.get("type") == "result"), None
    )
    if result_event is None:
        return "*[LLM returned no result]*"
    if result_event.get("is_error"):
        return f"*[LLM error: {result_event.get('result', 'unknown')}]*"

    text = result_event["result"].strip()
    # Strip markdown fences if present
    text = re.sub(r'^```(?:markdown)?\s*', '', text)
    text = re.sub(r'\s*```$', '', text)
    # Strip LLM preamble (e.g. "I'll write..." or "Here is...")
    text = re.sub(
        r"^(?:I'll|I will|Here is|Here's|Let me|Sure)[^\n]*\n+",
        '', text, count=1,
    )
    return text


# --- LLM-authored section generators ----------------------------------------

def section_executive_summary(
    trials: list[dict], model: str = "haiku", no_llm: bool = False,
    pairs: list[dict] | None = None,
) -> str:
    """Section 1: Executive Summary — LLM-authored or placeholder."""
    lines = ["## 1. Executive Summary", ""]

    if no_llm:
        best = _best_trial(trials)
        baseline = _baseline_trial(trials)
        improvement = (
            (best["mrr"] - baseline["mrr"]) / baseline["mrr"]
            if baseline["mrr"] > 0 else 0.0
        )
        lines.append(
            f"*[LLM prose skipped]* Best trial: {best['trial_id']} "
            f"(MRR = {best['mrr']:.4f}, {_format_pct(improvement)} over baseline)."
        )
    else:
        briefing = _build_briefing(trials, pairs or [])
        prompt = _executive_summary_prompt(briefing)
        prose = _llm_prose(briefing, prompt, model=model)
        lines.append(prose)

    lines.append("")
    return "\n".join(lines)


def section_exploitation_results(
    trials: list[dict], model: str = "haiku", no_llm: bool = False,
    pairs: list[dict] | None = None,
) -> str:
    """Section 4: Exploitation results — tables + LLM narrative per lineage."""
    exploit = _exploitation_trials(trials)
    all_lineages = _lineages(trials)

    lines = ["## 4. Exploitation Results (Gen 1+)", ""]

    if not exploit:
        lines.append("No exploitation trials were run.")
        lines.append("")
        return "\n".join(lines)

    # Per-lineage tables
    for name, lineage in all_lineages.items():
        if name == "baseline":
            continue
        exploit_in_lineage = [t for t in lineage if t["generation"] > 0]
        if not exploit_in_lineage:
            continue

        gen0 = next((t for t in lineage if t["generation"] == 0), None)
        lines.append(f"### {name}")
        lines.append("")
        lines.append("| Gen | Parent MRR | MRR | Delta | Mutation | Kept? |")
        lines.append("|-----|-----------|-----|-------|----------|-------|")

        parent_mrr = gen0["mrr"] if gen0 else 0.0
        for t in exploit_in_lineage:
            delta = t["mrr"] - parent_mrr
            kept = "Yes" if t["survived"] else "No"
            mutation = t.get("mutation", "-") or "-"
            # Truncate long mutations for table
            if len(mutation) > 80:
                mutation = mutation[:77] + "..."
            lines.append(
                f"| {t['generation']} | {parent_mrr:.4f} | {t['mrr']:.4f} "
                f"| {delta:+.4f} | {mutation} | {kept} |"
            )
            if t["survived"]:
                parent_mrr = t["mrr"]

        lines.append("")

    # LLM narrative
    if not no_llm:
        briefing = _build_briefing(trials, pairs or [])
        prompt = _exploitation_narrative_prompt(briefing)
        prose = _llm_prose(briefing, prompt, model=model)
        lines.append(prose)
        lines.append("")
    else:
        lines.append("*[LLM lineage narratives skipped]*")
        lines.append("")

    return "\n".join(lines)


def section_discussion(
    trials: list[dict], pairs: list[dict],
    model: str = "haiku", no_llm: bool = False,
) -> str:
    """Section 7: Discussion — LLM-authored or placeholder."""
    lines = ["## 7. Discussion", ""]

    if no_llm:
        lines.append("*[LLM discussion skipped]*")
    else:
        briefing = _build_briefing(trials, pairs)
        prompt = _discussion_prompt(briefing)
        prose = _llm_prose(briefing, prompt, model=model)
        lines.append(prose)

    lines.append("")
    return "\n".join(lines)


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

    infra_failures = [t for t in gen0 if not t.get("valid", True)]

    lines = [
        "## 3. Exploration Results (Gen 0)",
        "",
        "| Prompt | MRR | unique_props | hapax_rate | avg_props/synset | hit_rate | survived |",
        "|--------|-----|-------------|------------|-----------------|----------|----------|",
    ]
    for t in gen0:
        sec = t.get("secondary", {})
        if not t.get("valid", True):
            survived = "Infra fail"
        elif t["survived"]:
            survived = "Yes"
        else:
            survived = "No"
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

    if infra_failures:
        names = ", ".join(t["prompt_name"] for t in infra_failures)
        lines.append(
            f"**Note:** {len(infra_failures)} trial(s) had infrastructure failures "
            f"({names}) — results are unreliable and excluded from elimination decisions."
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


# --- Report composition -----------------------------------------------------

def generate_report(
    trials: list[dict],
    pairs: list[dict],
    model: str = "haiku",
    no_llm: bool = False,
) -> str:
    """Compose all sections into a complete markdown report."""
    sections = [
        "# Evolutionary Prompt Optimisation — Experiment Report",
        "",
        section_executive_summary(trials, model=model, no_llm=no_llm, pairs=pairs),
        section_methodology(trials),
        section_exploration_results(trials),
        section_exploitation_results(trials, model=model, no_llm=no_llm, pairs=pairs),
        section_cross_generation_analysis(trials),
        section_per_pair_analysis(trials, pairs),
        section_discussion(trials, pairs, model=model, no_llm=no_llm),
        section_appendix_prompts(trials),
        section_appendix_per_pair_detail(trials),
    ]
    return "\n".join(sections)


# --- CLI ---------------------------------------------------------------------

def main():
    """CLI entry point for report generation."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Generate comprehensive evolution experiment report"
    )
    parser.add_argument(
        "--experiment-log", type=str, default=str(DEFAULT_EXPERIMENT_LOG),
        help=f"Path to experiment_log.json (default: {DEFAULT_EXPERIMENT_LOG})",
    )
    parser.add_argument(
        "--pairs", type=str, default=str(DEFAULT_PAIRS_FILE),
        help=f"Path to metaphor_pairs.json (default: {DEFAULT_PAIRS_FILE})",
    )
    parser.add_argument(
        "--output", "-o", type=str, default=str(DEFAULT_OUTPUT),
        help=f"Output report path (default: {DEFAULT_OUTPUT})",
    )
    parser.add_argument(
        "--model", "-m", type=str, default="haiku",
        help="Claude model for LLM prose (default: haiku)",
    )
    parser.add_argument(
        "--no-llm", action="store_true",
        help="Skip LLM prose sections (for CI/testing)",
    )
    args = parser.parse_args()

    trials = load_experiment_log(Path(args.experiment_log))
    pairs = load_metaphor_pairs(Path(args.pairs))

    report = generate_report(trials, pairs, model=args.model, no_llm=args.no_llm)

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        f.write(report)

    print(f"Report written to {output_path} ({len(report)} chars)")


if __name__ == "__main__":
    main()
