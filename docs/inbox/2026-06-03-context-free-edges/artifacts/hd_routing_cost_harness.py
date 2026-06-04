"""H-D tiered-model-routing cost + quality harness.

Measures the spend-vs-quality frontier for context-free metaphor-edge
generation at scale, on the EXISTING ≤20-synset cohort. Two parts:

  PART 1 (cost) — re-characterise per-call cost cold-vs-warm for haiku /
    sonnet so the 100k extrapolation rests on measured CLI rates, not the
    theoretical $0.07 cold floor. Parses total_cost_usd + the cache_*
    token fields out of the CLI JSON so the cold/warm split is observed,
    not assumed.

  PART 2 (quality) — run THREE routes on the SAME ≤20-topic cohort and
    grade each route's bridges with an LLM-judge calibrated to Julian's
    11 human labels. The routes:
      R1  baseline    : Haiku-propose -> Sonnet-refine   (current 2-call)
      R2  haiku-only  : Haiku-propose-AND-chain          (1-call, Sonnet
                        gold few-shots baked into the template, no Sonnet
                        at request time — the "Sonnet-as-prompt-engineer"
                        pattern from the 2026-05-25 spike)
      R3  banded      : R2 for all, ESCALATE to Sonnet only on an
                        uncertainty band (Haiku self-reported confidence
                        below tau, OR vehicle in same FastText domain as
                        topic -> likely-dead risk).

The harness EMITS the cohort prompts and a cost log; the ORCHESTRATOR
runs the claude calls (this script makes NONE) and tracks spend. Pass
--dry-run to print the call plan + projected spend without any API use.

Quality bar (status.md A1): a bridge is good iff the LLM-judge labels it
`live` (genuine non-clichéd cross-domain) AND linkage-good. The decision
metric is APT(LIVE) RATE per route and its delta vs baseline, reported
with a Wilson 95% CI (n is tiny — never extrapolate past the CI).

No numbers are fabricated here: every rate is computed from grades the
orchestrator collects; every cost from total_cost_usd in the CLI JSON.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "lib"))
sys.path.insert(0, str(ROOT / "data-pipeline" / "scripts"))

# Cohort = the 20 graded topics (so grades exist to anchor the judge).
COHORT_TOPICS_JSON = Path(__file__).with_name("cohort_topics.json")
HAIKU_APT_JSONL = (
    ROOT / "data-pipeline" / "output"
    / "metaphor_spike_apt_phase2_20260525T004154.jsonl"
)
HUMAN_LABELS = ROOT / "data-pipeline" / "grading" / "judgements_provisional.jsonl"
COST_LOG = Path(__file__).with_name("hd_cost_log.jsonl")
GRADE_LOG = Path(__file__).with_name("hd_grade_log.jsonl")


# --------------------------------------------------------------------------
# COST MODEL (pure — no API). Measured anchors come from real Metaforge runs.
# --------------------------------------------------------------------------
# Token prices per MTok (USD), Anthropic list:
PRICE = {
    "haiku":  {"in": 1.00, "out": 5.00, "cw": 1.25, "cr": 0.10},
    "sonnet": {"in": 3.00, "out": 15.00, "cw": 3.75, "cr": 0.30},
    "opus":   {"in": 15.00, "out": 75.00, "cw": 18.75, "cr": 1.50},
}
CLI_SYS_TOKENS = 57_279        # measured cache-creation per cold call (G6)
# Content sizes measured from real data:
#   sonnet chain output ~790 tok (n=20 grading chains), prompt ~700 tok
#   haiku propose output ~700 tok, prompt ~700 tok
CONTENT = {
    "haiku":  {"in": 700, "out": 700},
    "sonnet": {"in": 700, "out": 790},
    "opus":   {"in": 700, "out": 790},
}


def per_call_cost(model: str, cold: bool) -> float:
    p, c = PRICE[model], CONTENT[model]
    sys_cost = CLI_SYS_TOKENS * (p["cw"] if cold else p["cr"]) / 1e6
    return sys_cost + c["in"] * p["in"] / 1e6 + c["out"] * p["out"] / 1e6


def project_100k(haiku_call: float, sonnet_call: float) -> dict:
    """Project total USD at 100k topics for each route, given measured
    per-call rates (pass the rates Part 1 measures)."""
    N = 100_000
    out = {
        "baseline_2call": N * (haiku_call + sonnet_call),
        "haiku_only_1call": N * haiku_call,
    }
    for esc in (0.05, 0.10, 0.20, 0.30):
        out[f"banded_{int(esc*100)}pct_sonnet"] = N * haiku_call + N * esc * sonnet_call
    return out


# --------------------------------------------------------------------------
# ESCALATION BAND (pure) — decides which topics R3 sends to Sonnet.
# --------------------------------------------------------------------------
def needs_escalation(
    haiku_confidence: float,
    topic_vehicle_cosine: float | None,
    *,
    tau_conf: float = 0.80,
    tau_same_domain: float = 0.55,
) -> bool:
    """Escalate when Haiku is unsure OR when topic and vehicle sit in the
    SAME FastText neighbourhood (high cosine => same-domain => dead-metaphor
    risk, the exact failure Sonnet uniquely caught: `pump` for heart).

    Both signals are context-free and computed from existing substrate
    (synset_centroids cosine; Haiku's self-reported per-vehicle confidence).
    """
    if haiku_confidence < tau_conf:
        return True
    if topic_vehicle_cosine is not None and topic_vehicle_cosine >= tau_same_domain:
        return True
    return False


# --------------------------------------------------------------------------
# WILSON 95% CI (pure) — for the tiny-n apt-rate decision metric.
# --------------------------------------------------------------------------
def wilson_ci(k: int, n: int, z: float = 1.96) -> tuple[float, float, float]:
    if n == 0:
        return (0.0, 0.0, 1.0)
    p = k / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = (z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))) / denom
    return (p, max(0.0, centre - half), min(1.0, centre + half))


# --------------------------------------------------------------------------
# JUDGE PROMPT (text only — orchestrator sends it). Calibration-first.
# --------------------------------------------------------------------------
def build_judge_prompt(topic: str, vehicle: str, chain: list[str]) -> str:
    chain_str = " -> ".join(chain)
    return f"""You grade metaphor BRIDGES for a creative-writing thesaurus.
The bar is LIVE / literary cross-domain metaphor — NOT dead, conventional,
synonym, co-hyponym, or definitional paraphrase.

Grade this bridge on two axes:
  metaphor: live | dead | irrelevant
    - live   = genuine, non-clichéd cross-domain mapping (anger->volcano)
    - dead   = conventional/lexicalised (heart->pump), synonym, same-domain
    - irrelevant = no apt mapping
  linkage: good | bad
    - good = EACH adjacent hop is apt shown in isolation (context-free-hop)
    - bad  = some hop only works given the others, or is a non-sequitur

Topic:   {topic}
Vehicle: {vehicle}
Path:    {chain_str}

Respond with STRICT JSON, nothing else:
{{"metaphor": "live|dead|irrelevant", "linkage": "good|bad", "why": "<=12 words"}}"""


# --------------------------------------------------------------------------
# COST-LOG PARSER (pure) — extracts the observed cold/warm split.
# --------------------------------------------------------------------------
def parse_cli_cost(cli_json: dict) -> dict:
    """Pull cost + cache fields from a `claude -p --output-format json`
    result event. `cache_creation_input_tokens` > 0 => this call was COLD
    (paid the 57k cache-write); cache_read_input_tokens > 0 => WARM."""
    usage = cli_json.get("usage", {}) if isinstance(cli_json, dict) else {}
    cw = usage.get("cache_creation_input_tokens", 0)
    cr = usage.get("cache_read_input_tokens", 0)
    return {
        "total_cost_usd": cli_json.get("total_cost_usd"),
        "cache_creation_input_tokens": cw,
        "cache_read_input_tokens": cr,
        "cold": cw > cr,
    }


def summarise_cost_log(path: Path) -> dict:
    """After the orchestrator runs the cohort, summarise observed rates:
    measured $/call per model, observed warm-fraction, and the resulting
    100k projection from project_100k()."""
    rows = [json.loads(l) for l in path.open() if l.strip()] if path.exists() else []
    by_model: dict[str, list] = {}
    for r in rows:
        by_model.setdefault(r["model"], []).append(r)
    out = {}
    for model, rs in by_model.items():
        costs = [r["total_cost_usd"] for r in rs if r.get("total_cost_usd") is not None]
        cold = sum(1 for r in rs if r.get("cold"))
        out[model] = {
            "n": len(rs),
            "mean_cost_usd": (sum(costs) / len(costs)) if costs else None,
            "warm_fraction": 1 - cold / len(rs) if rs else None,
        }
    if "haiku" in out and "sonnet" in out and out["haiku"]["mean_cost_usd"] and out["sonnet"]["mean_cost_usd"]:
        out["projection_100k"] = project_100k(
            out["haiku"]["mean_cost_usd"], out["sonnet"]["mean_cost_usd"]
        )
    return out


# --------------------------------------------------------------------------
# CALL-PLAN EMITTER — what the orchestrator should run (no API here).
# --------------------------------------------------------------------------
def emit_call_plan() -> dict:
    """Return the route-by-route call plan for the cohort, plus the
    theoretical cold/warm per-call costs (sanity anchor)."""
    topics = json.loads(COHORT_TOPICS_JSON.read_text()) if COHORT_TOPICS_JSON.exists() else []
    n = len(topics) if isinstance(topics, list) else len(topics.get("topics", []))
    plan = {
        "cohort_n": n,
        "routes": {
            "R1_baseline":   {"calls_per_topic": "1 haiku + 1 sonnet", "total_calls": 2 * n},
            "R2_haiku_only": {"calls_per_topic": "1 haiku", "total_calls": n},
            "R3_banded":     {"calls_per_topic": "1 haiku + (esc) sonnet", "total_calls": "n .. 2n"},
        },
        "per_call_cost_anchor": {
            "haiku_cold": round(per_call_cost("haiku", True), 4),
            "haiku_warm": round(per_call_cost("haiku", False), 4),
            "sonnet_cold": round(per_call_cost("sonnet", True), 4),
            "sonnet_warm": round(per_call_cost("sonnet", False), 4),
            "opus_warm": round(per_call_cost("opus", False), 4),
        },
        "measured_anchor": {
            "phase2_haiku_per_call_usd": 0.005,   # 200 topics, 400 calls, ~$2 (PIPELINE.md L173)
            "note": "warm-batch operating point; cold floor is a non-binding worst case",
        },
    }
    return plan


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true",
                    help="print call plan + projected spend; make NO API calls")
    ap.add_argument("--summarise-cost", action="store_true",
                    help="summarise hd_cost_log.jsonl after orchestrator run")
    args = ap.parse_args()

    if args.summarise_cost:
        print(json.dumps(summarise_cost_log(COST_LOG), indent=2))
        return 0

    # Default + --dry-run both just emit the plan; this script never calls API.
    plan = emit_call_plan()
    # Theoretical 100k projection at measured warm rate (haiku $0.005, sonnet ~$0.0147):
    proj = project_100k(0.005, 0.0147)
    print(json.dumps({"call_plan": plan, "projection_100k_warm": {k: round(v) for k, v in proj.items()}}, indent=2))
    print("\n# This script makes NO API calls. Orchestrator runs the routes,"
          " appends per-call {model,total_cost_usd,cold} to hd_cost_log.jsonl,"
          " and {route,topic,vehicle,metaphor,linkage} to hd_grade_log.jsonl,"
          " then re-runs with --summarise-cost.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
