"""Inject external MRR results into the exploration log.

One-off utility for seeding results from manual evaluations (e.g. a crashed v4 run
that completed persona_poet but not the rest) into the exploration log so that
resume can pick up from where it left off.

Usage:
    python seed_exploration.py --mrr-file output/mrr_persona_poet_v4.json \
        --prompt-name persona_poet \
        --exploration-log output/evolution/exploration_log.json
"""
import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from prompt_templates import EXPLORATION_PROMPTS


def build_trial_result(
    prompt_name: str,
    prompt_text: str,
    mrr_results: dict,
    baseline_mrr: float,
) -> dict:
    """Create a TrialResult-compatible dict from external MRR results."""
    mrr = mrr_results["mrr"]
    return {
        "trial_id": f"explore-{prompt_name}",
        "prompt_name": prompt_name,
        "prompt_text": prompt_text,
        "mrr": mrr,
        "per_pair": mrr_results.get("per_pair", []),
        "secondary": mrr_results.get("secondary", {}),
        "parent_id": None,
        "generation": 0,
        "mutation": None,
        "survived": mrr > baseline_mrr,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "enrichment_coverage": 1.0,
        "valid": True,
        "mrr_shared": None,
        "parent_mrr_shared": None,
        "shared_delta": None,
        "eval_subset": None,
        "shared_with_parent": None,
        "rotation_seed": None,
        "pool_version": None,
        "elo_rating": None,
    }


def seed_exploration_log(
    mrr_file: str,
    prompt_name: str,
    exploration_log: str,
) -> None:
    """Load MRR results and append to exploration log.

    Raises ValueError if prompt_name already exists in the log.
    """
    log_path = Path(exploration_log)

    # Load existing log or start fresh
    if log_path.exists():
        with open(log_path) as f:
            log = json.load(f)
    else:
        log = []

    # Check for duplicates
    existing_names = {entry["prompt_name"] for entry in log}
    if prompt_name in existing_names:
        raise ValueError(f"Prompt '{prompt_name}' already in log")

    # Determine baseline MRR from log
    baseline_entry = next((e for e in log if e["trial_id"] == "baseline"), None)
    baseline_mrr = baseline_entry["mrr"] if baseline_entry else 0.0

    # Load MRR results
    with open(mrr_file) as f:
        mrr_results = json.load(f)

    # Get prompt text from exploration prompts
    prompt_text = EXPLORATION_PROMPTS.get(prompt_name, "")

    # Build and append
    trial = build_trial_result(prompt_name, prompt_text, mrr_results, baseline_mrr)
    log.append(trial)

    # Save
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with open(log_path, "w") as f:
        json.dump(log, f, indent=2)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Seed external MRR results into exploration log"
    )
    parser.add_argument("--mrr-file", required=True, help="Path to MRR results JSON")
    parser.add_argument("--prompt-name", required=True, help="Prompt name (must be in EXPLORATION_PROMPTS)")
    parser.add_argument(
        "--exploration-log",
        default=str(Path(__file__).parent.parent / "output" / "evolution" / "exploration_log.json"),
        help="Path to exploration log JSON",
    )
    args = parser.parse_args()

    seed_exploration_log(args.mrr_file, args.prompt_name, args.exploration_log)
    print(f"Seeded '{args.prompt_name}' into {args.exploration_log}")


if __name__ == "__main__":
    main()
