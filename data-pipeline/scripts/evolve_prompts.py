"""Evolutionary prompt optimisation orchestrator.

Explores radically different prompts, then exploits survivors with targeted tweaks,
all scored by MRR against curated metaphor pairs.

Usage:
    python evolve_prompts.py --model haiku --size 700 --port 9091
    python evolve_prompts.py --phase explore   # exploration only
    python evolve_prompts.py --phase exploit   # exploitation only (reads explore log)
    python evolve_prompts.py --dry-run         # budget estimate
"""
import argparse
import json
import sys
import time
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).parent))

from enrich_properties import BATCH_PROMPT, UsageExhaustedError
from evaluate_mrr import evaluate
from prompt_templates import EXPLORATION_PROMPTS, generate_tweak, improve_prompt
from utils import OUTPUT_DIR


# --- Data structures ---------------------------------------------------------

@dataclass
class TrialResult:
    """Record of a single prompt evaluation trial."""
    trial_id: str
    prompt_name: str
    prompt_text: str
    mrr: float
    per_pair: list[dict]
    secondary: dict
    parent_id: Optional[str]
    generation: int
    mutation: Optional[str]
    survived: bool
    timestamp: str
    enrichment_coverage: float = 1.0
    valid: bool = True


# --- Helpers -----------------------------------------------------------------

def _save_log(trials: list[TrialResult], path: Path) -> None:
    """Save trial log to JSON (crash-safe: write after each trial)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump([asdict(t) for t in trials], f, indent=2)


def _ping_usage(model: str = "haiku") -> bool:
    """Check if LLM usage has renewed by sending a trivial prompt.

    Returns True if the API responds without a rate-limit error.
    """
    import subprocess
    try:
        proc = subprocess.run(
            ["claude", "-p", "--output-format", "json", "--model", model,
             "--max-turns", "1", "--no-session-persistence"],
            input="Reply with just the word 'ok'.",
            capture_output=True, text=True, timeout=30,
        )
        if proc.returncode != 0:
            return False
        events = json.loads(proc.stdout)
        result_event = next(
            (e for e in reversed(events) if e.get("type") == "result"), None
        )
        if result_event and result_event.get("is_error"):
            error_text = result_event.get("result", "").lower()
            if any(ind in error_text for ind in ("rate limit", "usage limit", "quota", "overloaded", "429")):
                return False
        return True
    except Exception:
        return False


def _wait_for_usage_renewal(model: str = "haiku", poll_interval: float = 300.0) -> None:
    """Poll until usage renews (default: every 5 minutes)."""
    print("  Usage exhausted. Waiting for renewal...")
    while not _ping_usage(model):
        print(f"    Still exhausted. Sleeping {poll_interval}s...")
        time.sleep(poll_interval)
    print("  Usage renewed. Resuming.")


def _evaluate_with_backoff(
    prompt_template: str,
    model: str,
    enrich_size: int,
    port: int,
    verbose: bool = False,
    **kwargs,
) -> dict:
    """Run evaluate() with usage-exhaustion backoff."""
    while True:
        try:
            return evaluate(
                enrichment_file=None,
                enrich_size=enrich_size,
                enrich_model=model,
                port=port,
                prompt_template=prompt_template,
                verbose=verbose,
                **kwargs,
            )
        except UsageExhaustedError:
            _wait_for_usage_renewal(model)


def _now() -> str:
    """ISO 8601 timestamp."""
    return datetime.now(timezone.utc).isoformat()


# --- Exploration -------------------------------------------------------------

def run_exploration(
    prompts: dict[str, str],
    baseline_prompt: str,
    model: str = "haiku",
    enrich_size: int = 700,
    port: int = 9091,
    output_dir: Path = None,
    verbose: bool = False,
) -> list[TrialResult]:
    """Evaluate baseline + exploration prompts, identify survivors.

    Survivors = prompts with MRR > baseline MRR.
    Saves log incrementally after each trial.
    """
    if output_dir is None:
        output_dir = OUTPUT_DIR / "evolution"
    output_dir = Path(output_dir)
    log_path = output_dir / "exploration_log.json"

    trials: list[TrialResult] = []

    # Baseline
    print("=== Exploration: evaluating baseline ===")
    result = _evaluate_with_backoff(
        prompt_template=baseline_prompt,
        model=model,
        enrich_size=enrich_size,
        port=port,
        verbose=verbose,
    )
    baseline_trial = TrialResult(
        trial_id="baseline",
        prompt_name="baseline",
        prompt_text=baseline_prompt,
        mrr=result["mrr"],
        per_pair=result["per_pair"],
        secondary=result["secondary"],
        parent_id=None,
        generation=0,
        mutation=None,
        survived=True,
        timestamp=_now(),
    )
    trials.append(baseline_trial)
    _save_log(trials, log_path)
    baseline_mrr = result["mrr"]
    print(f"  Baseline MRR = {baseline_mrr:.4f}")

    # Exploration prompts
    for name, prompt in prompts.items():
        print(f"\n=== Exploration: evaluating {name} ===")
        result = _evaluate_with_backoff(
            prompt_template=prompt,
            model=model,
            enrich_size=enrich_size,
            port=port,
            verbose=verbose,
        )
        trial_valid = result.get("valid", True)
        if trial_valid:
            survived = result["mrr"] > baseline_mrr
        else:
            survived = False
        coverage = result.get("enrichment_coverage", 1.0)
        trial = TrialResult(
            trial_id=f"explore-{name}",
            prompt_name=name,
            prompt_text=prompt,
            mrr=result["mrr"],
            per_pair=result["per_pair"],
            secondary=result["secondary"],
            parent_id=None,
            generation=0,
            mutation=None,
            survived=survived,
            timestamp=_now(),
            enrichment_coverage=coverage,
            valid=trial_valid,
        )
        trials.append(trial)
        _save_log(trials, log_path)
        if not trial_valid:
            status = "INVALID (infra failure)"
        elif survived:
            status = "SURVIVED"
        else:
            status = "eliminated"
        print(f"  {name}: MRR = {result['mrr']:.4f} ({status})")

    survivors = [t for t in trials if t.survived and t.trial_id != "baseline"]
    print(f"\n=== Exploration complete: {len(survivors)} survivors out of {len(prompts)} ===")

    return trials


# --- Exploitation ------------------------------------------------------------

def run_exploitation(
    survivor_name: str,
    survivor_prompt: str,
    survivor_mrr: float,
    per_pair: list[dict],
    max_tweaks: int = 7,
    consecutive_failure_limit: int = 3,
    model: str = "haiku",
    enrich_size: int = 700,
    port: int = 9091,
    output_dir: Path = None,
    verbose: bool = False,
    exploit_model: str = "haiku",
    improver_model: str = "sonnet",
) -> list[TrialResult]:
    """Exploit a surviving prompt with incremental tweaks.

    Generates targeted modifications using an LLM, keeps improvements,
    reverts regressions. Stops after max_tweaks or K consecutive failures.
    """
    if output_dir is None:
        output_dir = OUTPUT_DIR / "evolution"
    output_dir = Path(output_dir)
    log_path = output_dir / f"exploitation_{survivor_name}_log.json"

    trials: list[TrialResult] = []
    current_prompt = survivor_prompt
    current_mrr = survivor_mrr
    current_per_pair = per_pair
    parent_id = f"explore-{survivor_name}"
    consecutive_failures = 0

    for tweak_num in range(1, max_tweaks + 1):
        gen = tweak_num
        print(f"\n=== Exploit {survivor_name} g{gen}: generating tweak ===")

        try:
            tweak = generate_tweak(
                current_prompt=current_prompt,
                per_pair=current_per_pair,
                mrr=current_mrr,
                model=exploit_model,
            )
            # Second stage: improve the raw tweak with a stronger model
            improved = improve_prompt(tweak["modified_prompt"], model=improver_model)
            tweak["modified_prompt"] = improved
        except (ValueError, RuntimeError) as e:
            print(f"  Tweak generation failed: {e}")
            consecutive_failures += 1
            if consecutive_failures >= consecutive_failure_limit:
                print(f"  Early stop: {consecutive_failure_limit} consecutive failures")
                break
            continue

        print(f"  Tweak: {tweak['description']}")

        result = _evaluate_with_backoff(
            prompt_template=tweak["modified_prompt"],
            model=model,
            enrich_size=enrich_size,
            port=port,
            verbose=verbose,
        )

        trial_valid = result.get("valid", True)
        coverage = result.get("enrichment_coverage", 1.0)
        improved = trial_valid and result["mrr"] > current_mrr
        trial_id = f"exploit-{survivor_name}-g{gen}"
        trial = TrialResult(
            trial_id=trial_id,
            prompt_name=survivor_name,
            prompt_text=tweak["modified_prompt"],
            mrr=result["mrr"],
            per_pair=result["per_pair"],
            secondary=result["secondary"],
            parent_id=parent_id,
            generation=gen,
            mutation=tweak["description"],
            survived=improved,
            timestamp=_now(),
            enrichment_coverage=coverage,
            valid=trial_valid,
        )
        trials.append(trial)
        _save_log(trials, log_path)

        if not trial_valid:
            print(f"  MRR {result['mrr']:.4f} — INVALID (infra failure, not counted)")
            # Infra failures don't count toward consecutive failure limit
        elif improved:
            print(f"  MRR {current_mrr:.4f} → {result['mrr']:.4f} — KEPT")
            current_prompt = tweak["modified_prompt"]
            current_mrr = result["mrr"]
            current_per_pair = result["per_pair"]
            parent_id = trial_id
            consecutive_failures = 0
        else:
            print(f"  MRR {current_mrr:.4f} → {result['mrr']:.4f} — reverted")
            consecutive_failures += 1
            if consecutive_failures >= consecutive_failure_limit:
                print(f"  Early stop: {consecutive_failure_limit} consecutive failures")
                break

    print(f"\n=== Exploitation of {survivor_name} complete: "
          f"best MRR = {current_mrr:.4f} ===")

    return trials


# --- Full experiment ---------------------------------------------------------

def run_experiment(
    model: str = "haiku",
    enrich_size: int = 700,
    port: int = 9091,
    output_dir: Path = None,
    max_tweaks: int = 7,
    consecutive_failure_limit: int = 3,
    phase: str = "both",
    verbose: bool = False,
    exploit_model: str = "haiku",
    improver_model: str = "sonnet",
) -> list[TrialResult]:
    """Run full evolutionary prompt experiment: exploration → exploitation.

    phase: "both", "explore", or "exploit" (exploit reads explore log).
    """
    if output_dir is None:
        output_dir = OUTPUT_DIR / "evolution"
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    all_trials: list[TrialResult] = []

    # Exploration
    if phase in ("both", "explore"):
        explore_trials = run_exploration(
            prompts=EXPLORATION_PROMPTS,
            baseline_prompt=BATCH_PROMPT,
            model=model,
            enrich_size=enrich_size,
            port=port,
            output_dir=output_dir,
            verbose=verbose,
        )
        all_trials.extend(explore_trials)
    elif phase == "exploit":
        # Load exploration results from log
        log_path = output_dir / "exploration_log.json"
        if not log_path.exists():
            raise FileNotFoundError(
                f"Exploration log not found: {log_path}. Run --phase explore first."
            )
        with open(log_path) as f:
            explore_data = json.load(f)
        explore_trials = [TrialResult(**d) for d in explore_data]
        all_trials.extend(explore_trials)

    # Exploitation
    if phase in ("both", "exploit"):
        survivors = [t for t in all_trials if t.survived and t.trial_id != "baseline"]
        for survivor in survivors:
            exploit_trials = run_exploitation(
                survivor_name=survivor.prompt_name,
                survivor_prompt=survivor.prompt_text,
                survivor_mrr=survivor.mrr,
                per_pair=survivor.per_pair,
                max_tweaks=max_tweaks,
                consecutive_failure_limit=consecutive_failure_limit,
                model=model,
                enrich_size=enrich_size,
                port=port,
                output_dir=output_dir,
                verbose=verbose,
                exploit_model=exploit_model,
                improver_model=improver_model,
            )
            all_trials.extend(exploit_trials)

    # Save complete log
    _save_log(all_trials, output_dir / "experiment_log.json")

    return all_trials


# --- Budget estimate ---------------------------------------------------------

def dry_run_estimate(
    num_prompts: int = 5,
    max_tweaks: int = 7,
    cost_per_run: float = 1.50,
) -> dict:
    """Estimate budget for the experiment without running anything."""
    exploration_runs = 1 + num_prompts  # baseline + prompts
    exploration_cost = exploration_runs * cost_per_run

    # Worst case: all prompts survive
    max_exploitation_runs = max_tweaks * num_prompts
    max_exploitation_cost = max_exploitation_runs * cost_per_run

    max_total = exploration_cost + max_exploitation_cost

    return {
        "exploration_runs": exploration_runs,
        "exploration_cost": exploration_cost,
        "max_exploitation_runs": max_exploitation_runs,
        "max_exploitation_cost": max_exploitation_cost,
        "max_total_runs": exploration_runs + max_exploitation_runs,
        "max_total_cost": max_total,
    }


# --- Report generation -------------------------------------------------------

def generate_report(trials: list[TrialResult]) -> str:
    """Generate a markdown report from experiment trials."""
    lines = ["# Evolutionary Prompt Optimisation Report", ""]

    if not trials:
        lines.append("No trials recorded.")
        return "\n".join(lines)

    # Summary table
    lines.append("## Summary")
    lines.append("")
    lines.append("| Trial | Prompt | MRR | Generation | Survived | Mutation |")
    lines.append("|-------|--------|-----|-----------|----------|----------|")
    for t in trials:
        survived = "Yes" if t.survived else "No"
        mutation = t.mutation or "-"
        lines.append(
            f"| {t.trial_id} | {t.prompt_name} | {t.mrr:.4f} | {t.generation} "
            f"| {survived} | {mutation} |"
        )
    lines.append("")

    # Per-lineage timeline
    lineages: dict[str, list[TrialResult]] = {}
    for t in trials:
        lineages.setdefault(t.prompt_name, []).append(t)

    lines.append("## Per-Lineage Timeline")
    lines.append("")
    for name, lineage in lineages.items():
        sorted_lineage = sorted(lineage, key=lambda t: t.generation)
        lines.append(f"### {name}")
        lines.append("")
        for t in sorted_lineage:
            marker = "+" if t.survived else "-"
            mutation_note = f" ({t.mutation})" if t.mutation else ""
            lines.append(f"- [{marker}] g{t.generation}: MRR={t.mrr:.4f}{mutation_note}")
        lines.append("")

    # Per-pair analysis
    lines.append("## Per-Pair Analysis")
    lines.append("")

    # Collect all unique pairs across trials
    pair_results: dict[str, list[tuple[str, float]]] = {}
    for t in trials:
        for p in t.per_pair:
            key = f"{p['source']} → {p['target']}"
            pair_results.setdefault(key, []).append((t.trial_id, p.get("reciprocal_rank", 0.0)))

    if pair_results:
        # Find hardest and easiest pairs
        avg_rr = {k: sum(rr for _, rr in v) / len(v) for k, v in pair_results.items()}
        sorted_pairs = sorted(avg_rr.items(), key=lambda x: x[1])

        lines.append("### Hardest Pairs (lowest average reciprocal rank)")
        lines.append("")
        for pair, avg in sorted_pairs[:10]:
            lines.append(f"- {pair}: avg RR = {avg:.3f}")
        lines.append("")

        lines.append("### Easiest Pairs (highest average reciprocal rank)")
        lines.append("")
        for pair, avg in sorted_pairs[-10:]:
            lines.append(f"- {pair}: avg RR = {avg:.3f}")
        lines.append("")

    # Recommendations
    lines.append("## Recommendations")
    lines.append("")

    best = max(trials, key=lambda t: t.mrr)
    lines.append(f"- **Best prompt**: {best.trial_id} (MRR = {best.mrr:.4f})")

    survivors = [t for t in trials if t.survived and t.trial_id != "baseline"]
    if survivors:
        lines.append(f"- **Survivors**: {', '.join(t.trial_id for t in survivors)}")
    else:
        lines.append("- No prompts outperformed the baseline.")

    lines.append("")
    return "\n".join(lines)


# --- CLI ---------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Evolutionary prompt optimisation for Metaforge enrichment"
    )
    parser.add_argument(
        "--model", "-m", type=str, default="haiku",
        help="Claude model (default: haiku)",
    )
    parser.add_argument(
        "--size", "-s", type=int, default=700,
        help="Enrichment size per trial (default: 700)",
    )
    parser.add_argument(
        "--port", "-p", type=int, default=9091,
        help="API server port (default: 9091)",
    )
    parser.add_argument(
        "--output-dir", "-o", type=str, default=None,
        help="Output directory (default: output/evolution/)",
    )
    parser.add_argument(
        "--max-tweaks", type=int, default=7,
        help="Max exploitation tweaks per survivor (default: 7)",
    )
    parser.add_argument(
        "--phase", choices=["both", "explore", "exploit"], default="both",
        help="Run phase: both, explore only, or exploit only (default: both)",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Print budget estimate without running",
    )
    parser.add_argument(
        "--exploit-model", type=str, default="haiku",
        help="Model for tweak generation in exploitation (default: haiku)",
    )
    parser.add_argument(
        "--improver-model", type=str, default="sonnet",
        help="Model for prompt improvement stage (default: sonnet)",
    )
    parser.add_argument(
        "--verbose", action="store_true",
        help="Enable DEBUG logging for raw LLM request/response",
    )
    args = parser.parse_args()

    if args.dry_run:
        estimate = dry_run_estimate(
            num_prompts=len(EXPLORATION_PROMPTS),
            max_tweaks=args.max_tweaks,
        )
        print("=== Dry Run: Budget Estimate ===")
        print(f"  Exploration: {estimate['exploration_runs']} runs "
              f"(~${estimate['exploration_cost']:.0f})")
        print(f"  Exploitation (worst case): {estimate['max_exploitation_runs']} runs "
              f"(~${estimate['max_exploitation_cost']:.0f})")
        print(f"  Total (worst case): {estimate['max_total_runs']} runs "
              f"(~${estimate['max_total_cost']:.0f})")
        print("\nNote: Early stopping typically reduces exploitation cost by 30-50%.")
        return

    if args.verbose:
        import logging
        logging.basicConfig(level=logging.DEBUG, format="%(levelname)s: %(message)s")

    output_dir = Path(args.output_dir) if args.output_dir else None

    all_trials = run_experiment(
        model=args.model,
        enrich_size=args.size,
        port=args.port,
        output_dir=output_dir,
        max_tweaks=args.max_tweaks,
        phase=args.phase,
        verbose=args.verbose,
        exploit_model=args.exploit_model,
        improver_model=args.improver_model,
    )

    print(f"\n=== Experiment complete: {len(all_trials)} total trials ===")


if __name__ == "__main__":
    main()
