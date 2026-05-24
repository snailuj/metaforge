"""Metaphor Enrichment Spike — Phase 1b runner.

20 anchor topics × Haiku-only × 2 prompts = 40 LLM calls.

Architecture: **Sonnet-as-prompt-engineer**. Sonnet has already been
run once (via ``generate_spike_1b_gold_examples.py``) on three example
topics outside the test set; the resulting gold few-shot examples are
loaded from ``spike_1b_gold_examples.json`` and baked into the apt /
inapt templates. Haiku is then used for the bulk of the work. This
costs ~$0.41 against Phase 1a's dual-model ~$1.12 (~63% cheaper).

Phase 1b gates against Phase 2 cohort scale-up on:
- JSON parseability / schema compliance / single-word / snap rate
  (same as Phase 1a, single-model thresholds)
- Cascade discrimination on the 20-topic cohort:
    * separation_score = mean(apt cascade score) - mean(inapt)
    * aptness_rate     = % apt scores > median(apt ∪ inapt)
    * per-inapt_reason_type breakdown: which failure modes the
      cascade catches vs misses (the M05 calibration evidence)

Usage::

    python data-pipeline/scripts/metaphor_spike_1b.py \\
        --db data-pipeline/output/lexicon_v2.db \\
        --output-dir data-pipeline/output

Outputs (written to --output-dir; <TS> = YYYYMMDDTHHMMSS run timestamp)::

    metaphor_spike_apt_phase1b_<TS>.jsonl
    metaphor_spike_inapt_phase1b_<TS>.jsonl
    metaphor_spike_scores_phase1b_<TS>.jsonl
    metaphor_spike_scoring_phase1b_<TS>.md
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "lib"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import argparse
import json
import logging
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from claude_client import prompt_json, ClaudeError
from evaluate_aptness import (
    aggregate_metrics,
    classify_aptness,
    lookup_primary_synset,
    _percentile,
)
from evaluate_cascade import CascadeConfig, evaluate_cascade_pair
from metaphor_spike_1a import (
    AptValidation,
    ConceptSnapResult,
    GateMetrics,
    InaptValidation,
    MODEL_HAIKU,
    PRODUCTION_CASCADE_CONFIG,
    ScoredVehicle,
    check_concept_snap_rate,
    compute_gate_metrics,
    validate_apt_response,
    validate_inapt_response,
    write_jsonl_line,
)

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Anchor topics — 20-topic Phase 1b set from the spike doc.
# 5 Lakoff abstractions, 5 concrete metaphor-rich, 5 compound/rare,
# 5 emotion/state. Glosses are hand-curated tight clauses (no LLM
# gloss generation — that's Phase 2 work).
# ---------------------------------------------------------------------------
TOPICS: list[dict[str, str]] = [
    # Canonical Lakoff abstractions
    {"word": "anger",     "gloss": "a strong feeling of displeasure or hostility"},
    {"word": "time",      "gloss": "an indefinite period of past, present, and future as a continuum"},
    {"word": "ideas",     "gloss": "thoughts or concepts formed in the mind"},
    {"word": "life",      "gloss": "the existence of a living being from birth to death"},
    {"word": "argument",  "gloss": "an exchange of opposing views or reasons"},
    # Concrete but metaphor-rich nouns
    {"word": "heart",     "gloss": "the hollow muscular organ that pumps blood through the body"},
    {"word": "light",     "gloss": "electromagnetic radiation perceived by the eye"},
    {"word": "road",      "gloss": "a paved way for vehicles connecting places"},
    {"word": "anchor",    "gloss": "a heavy device dropped to hold a vessel in place"},
    {"word": "mirror",    "gloss": "a polished surface that reflects an image"},
    # Compound / rare nouns
    {"word": "deadline",  "gloss": "a point in time by which something must be completed"},
    {"word": "recursion", "gloss": "a process that refers to or repeats itself"},
    {"word": "ambush",    "gloss": "a surprise attack from a concealed position"},
    {"word": "threshold", "gloss": "a doorway, or a point at which a change occurs"},
    {"word": "gridlock",  "gloss": "a traffic standstill in which vehicles cannot move"},
    # Emotion / state nouns
    {"word": "anxiety",   "gloss": "a feeling of worry and unease about uncertain outcomes"},
    {"word": "hope",      "gloss": "an expectation of a desired outcome"},
    {"word": "grief",     "gloss": "deep sorrow caused by loss or bereavement"},
    {"word": "courage",   "gloss": "the ability to face fear, pain, or risk"},
    {"word": "doubt",     "gloss": "uncertainty about the truth of something"},
]


# ---------------------------------------------------------------------------
# Gold-example loading and template construction.
# ---------------------------------------------------------------------------

_GOLD_EXAMPLES_PATH = Path(__file__).resolve().parent / "spike_1b_gold_examples.json"


def _format_apt_example(topic_obj: dict) -> str:
    """Render one apt gold example as a compact `Input:` / `Output:` block.

    JSON braces in the example body are LEFT literal — they appear as
    the substituted value of {examples} in a single .format() call,
    which does not recursively interpret the substituted text.
    """
    word = topic_obj["word"]
    gloss = topic_obj["gloss"]
    apt = topic_obj["apt"]
    body = json.dumps(apt, ensure_ascii=False)
    return f"EXAMPLE\nInput: {word} ({gloss})\nOutput: {body}"


def _format_inapt_example(topic_obj: dict) -> str:
    """Render one inapt gold example — same single-pass approach as apt."""
    word = topic_obj["word"]
    gloss = topic_obj["gloss"]
    inapt = topic_obj["inapt"]
    body = json.dumps(inapt, ensure_ascii=False)
    return f"EXAMPLE\nInput: {word} ({gloss})\nOutput: {body}"


def _load_gold_examples(path: Path = _GOLD_EXAMPLES_PATH) -> list[dict]:
    """Load the Sonnet-generated gold examples from disk."""
    if not path.exists():
        raise FileNotFoundError(
            f"Gold examples file missing: {path}. Run "
            f"generate_spike_1b_gold_examples.py first."
        )
    data = json.loads(path.read_text(encoding="utf-8"))
    topics = data.get("topics", [])
    if not topics:
        raise ValueError(f"Gold examples file has no topics: {path}")
    return topics


_GOLD_TOPICS = _load_gold_examples()


_APT_TEMPLATE = """\
You generate metaphor mappings for a thesaurus. For each topic word,
return 3-7 concrete vehicles that map onto it via cross-domain
structural similarity.

QUALITY CRITERIA (every entry must satisfy):
1. CONCRETE vehicle. Physically perceivable. Vehicle must be more
   concrete than topic.
2. CROSS-DOMAIN. Vehicle from a clearly different conceptual domain.
   anger→fire (emotion→physical) GOOD.
   anger→rage (emotion→emotion, synonym) BAD.
3. MULTI-DIMENSIONAL. Metaphor should resonate across 2+ of these:
   sensorimotor, behaviour, functional, effect, emotional, social.
   Single-dimension matches are weak.
4. NOT a synonym, hypernym, hyponym, meronym, or paraphrase.
5. Living metaphor preferred. Lakoff classics (life→journey) are
   fine if structurally rich; avoid dead metaphors literalised by
   usage (e.g. "leg of a table").

Each shared_feature pairs a dimension with a specific concept that
both topic and vehicle exhibit.

CONCEPT FORMAT (CRITICAL): Each "concept" value MUST be a SINGLE
common English word (noun, gerund, or adjective). NOT a phrase. NOT
a list. NOT a comma-separated string. NOT a sentence fragment.
These concepts are programmatically resolved to dictionary entries
downstream, so they MUST exist as standalone words.

GOOD: heat, spreading, destruction, intensity, taming, eruption
BAD:  "must be tamed", "spent saved wasted", "clears air after",
      "pressure builds invisibly then erupts"

If a single word cannot capture what you mean, split it into
multiple shared_feature entries.

If fewer than 3 strong metaphors exist, return only the strong ones.

OUTPUT (JSON only, no markdown, no preamble). DO NOT echo the input gloss in the output — runner attaches it locally:
{{"topic":"<word>","metaphors":[{{"vehicle":"<word>","shared_features":[{{"dimension":"<dim>","concept":"<concept>"}}],"confidence":<0.0-1.0>}}]}}

{examples}

Input: {topic} ({gloss})
Output:\
"""


_INAPT_TEMPLATE = """\
You generate plausible-but-INAPT metaphor mappings for a thesaurus
evaluation cohort. For each topic, return 2-3 vehicles that have
SURFACE resemblance to good metaphors but actually fail under
structural scrutiny.

The goal is to test whether a structural-similarity algorithm can
DISCRIMINATE apt cross-domain metaphors from plausible-looking
cross-domain noise. Therefore:

- DO NOT return obvious antonyms or random unrelated words. They
  test triviality, not discrimination.
- DO return vehicles that share a single surface feature, are
  paraphrastic, or sit in the same conceptual domain.
- Each vehicle must look "metaphor-eligible" at first glance —
  the inaptness should require analysis to detect.

FAILURE MODES (closed vocabulary — pick exactly one per vehicle):
- single_dimension: shares only one of {{{{sensorimotor, behaviour,
  functional, effect, emotional, social}}}}. Insufficient resonance.
- same_domain: actually a paraphrase / synonym / near-synonym in
  the same conceptual domain. anger→fury, time→duration.
- wrong_concreteness: vehicle is at the same abstraction level as
  topic, or more abstract. anger→fury, time→eternity.
- dead_metaphor: a once-living metaphor now literalised by usage
  ("leg of a table"). The mapping no longer feels figurative.
- synonym_or_hypernym: vehicle is a kind-of / part-of /
  contained-in the topic. anger→emotion, fire→combustion.

OUTPUT (JSON only, no markdown, no preamble). DO NOT echo the input gloss in the output — runner attaches it locally:
{{"topic":"<word>","inapt_metaphors":[{{"vehicle":"<word>","inapt_reason_type":"<tag>","explanation":"<text>"}}]}}

{examples}

Input: {topic} ({gloss})
Output:\
"""


_APT_EXAMPLES_BLOCK = "\n\n".join(_format_apt_example(t) for t in _GOLD_TOPICS)
_INAPT_EXAMPLES_BLOCK = "\n\n".join(_format_inapt_example(t) for t in _GOLD_TOPICS)


def build_apt_prompt(topic: str, gloss: str) -> str:
    """Render the apt prompt template (gold examples baked in) for a topic.

    Single .format() call substitutes ``examples``, ``topic`` and
    ``gloss`` together. Brace literals in the template ({{...}}) and
    in the example JSON (already escaped by _escape_braces) survive as
    single braces in the rendered output.
    """
    return _APT_TEMPLATE.format(
        examples=_APT_EXAMPLES_BLOCK, topic=topic, gloss=gloss
    )


def build_inapt_prompt(topic: str, gloss: str) -> str:
    """Render the inapt prompt template (gold examples baked in) for a topic."""
    return _INAPT_TEMPLATE.format(
        examples=_INAPT_EXAMPLES_BLOCK, topic=topic, gloss=gloss
    )


# ---------------------------------------------------------------------------
# Inapt vehicle scoring — Phase 1b adds this so we can compute
# discrimination metrics (apt cohort vs inapt cohort).
# ---------------------------------------------------------------------------


@dataclass
class ScoredInaptVehicle(ScoredVehicle):
    """Cascade score for one (topic, inapt_vehicle) pair.

    Inherits topic/vehicle/synset/status/score/gate_passed from
    ScoredVehicle and adds the inapt_reason_type tag so we can compute
    per-failure-mode discrimination later.
    """
    inapt_reason_type: str = ""


def score_inapt_vehicles(
    conn: sqlite3.Connection,
    inapt_response: dict,
    config: CascadeConfig,
) -> list[ScoredInaptVehicle]:
    """Score each inapt vehicle through the cascade.

    Mirrors score_apt_vehicles from Phase 1a but reads
    ``inapt_metaphors`` and preserves ``inapt_reason_type`` on each
    result row so downstream aggregation can break out per failure mode.
    """
    topic_word = inapt_response.get("topic", "")
    inapt_metaphors = inapt_response.get("inapt_metaphors", [])

    sid_topic = lookup_primary_synset(conn, topic_word)
    results: list[ScoredInaptVehicle] = []

    for m in inapt_metaphors:
        if not isinstance(m, dict):
            continue
        vehicle_word = m.get("vehicle", "")
        if not isinstance(vehicle_word, str):
            vehicle_word = ""
        reason = m.get("inapt_reason_type", "")
        if not isinstance(reason, str):
            reason = ""
        sid_vehicle = lookup_primary_synset(conn, vehicle_word)

        if sid_topic is None or sid_vehicle is None:
            results.append(
                ScoredInaptVehicle(
                    topic=topic_word,
                    vehicle=vehicle_word,
                    synset_topic=sid_topic,
                    synset_vehicle=sid_vehicle,
                    cascade_status="unresolved",
                    final_score=None,
                    gate_passed=False,
                    inapt_reason_type=reason,
                )
            )
            continue

        try:
            cr = evaluate_cascade_pair(conn, sid_topic, sid_vehicle, config)
        except Exception as e:
            log.warning(
                "inapt cascade scoring failed topic=%r vehicle=%r: %s",
                topic_word, vehicle_word, e,
            )
            results.append(
                ScoredInaptVehicle(
                    topic=topic_word,
                    vehicle=vehicle_word,
                    synset_topic=sid_topic,
                    synset_vehicle=sid_vehicle,
                    cascade_status="unresolved",
                    final_score=None,
                    gate_passed=False,
                    inapt_reason_type=reason,
                )
            )
            continue

        results.append(
            ScoredInaptVehicle(
                topic=topic_word,
                vehicle=vehicle_word,
                synset_topic=sid_topic,
                synset_vehicle=sid_vehicle,
                cascade_status=cr.status,
                final_score=cr.final_score,
                gate_passed=cr.gate_passed,
                inapt_reason_type=reason,
            )
        )

    return results


# ---------------------------------------------------------------------------
# Phase 1b discrimination metrics.
# ---------------------------------------------------------------------------


@dataclass
class DiscriminationMetrics:
    """Aggregate cascade-discrimination metrics for the cohort."""
    n_apt_scored: int
    n_inapt_scored: int
    mean_apt_score: float
    mean_inapt_score: float
    separation_score: float
    median_threshold: float
    aptness_rate: float          # fraction of apt scores > median(apt∪inapt)
    false_positive_rate: float   # fraction of inapt scores > same threshold
    per_reason_breakdown: dict[str, dict]  # reason_type -> {n, mean, gate_pass_rate}


def compute_discrimination(
    apt_scored: list[ScoredVehicle],
    inapt_scored: list[ScoredInaptVehicle],
) -> DiscriminationMetrics:
    """Compute Phase 1b discrimination metrics.

    Only pairs with cascade_status == "scored" contribute to the mean /
    separation. Gate-dropped, unresolved, and no-properties rows are
    counted via the per-reason breakdown's ``n`` but excluded from
    ``mean`` so cohort attrition does not deflate the signal.

    Threshold: median of the combined apt+inapt scored distribution.
    Picked because the Phase 1b cohort is too small for a fitted
    threshold to be meaningful, and median splits the empirical
    distribution evenly so aptness_rate and FP rate are directly
    interpretable as 'fraction above the typical score'.
    """
    apt_scores = [
        sv.final_score for sv in apt_scored
        if sv.cascade_status == "scored" and sv.final_score is not None
    ]
    inapt_scores = [
        sv.final_score for sv in inapt_scored
        if sv.cascade_status == "scored" and sv.final_score is not None
    ]

    agg = aggregate_metrics(apt_scores, inapt_scores)
    threshold = _percentile(apt_scores + inapt_scores, 50.0)
    classify = classify_aptness(apt_scores, inapt_scores, threshold)

    per_reason: dict[str, dict] = {}
    for sv in inapt_scored:
        bucket = per_reason.setdefault(
            sv.inapt_reason_type or "unspecified",
            {"n_total": 0, "n_scored": 0, "scores": [], "n_gate_pass": 0},
        )
        bucket["n_total"] += 1
        if sv.cascade_status == "scored" and sv.final_score is not None:
            bucket["n_scored"] += 1
            bucket["scores"].append(sv.final_score)
        if sv.gate_passed:
            bucket["n_gate_pass"] += 1

    breakdown: dict[str, dict] = {}
    for reason, b in per_reason.items():
        mean = sum(b["scores"]) / len(b["scores"]) if b["scores"] else 0.0
        # Discriminated = fraction of this reason's vehicles whose
        # cascade score sits at-or-below the median threshold. Higher
        # is better for the cascade.
        n = len(b["scores"])
        discriminated = (
            sum(1 for s in b["scores"] if s <= threshold) / n if n else 0.0
        )
        breakdown[reason] = {
            "n_total": b["n_total"],
            "n_scored": b["n_scored"],
            "mean_score": round(mean, 6),
            "discriminated_rate": round(discriminated, 6),
            "gate_pass_rate": round(b["n_gate_pass"] / b["n_total"], 6) if b["n_total"] else 0.0,
        }

    return DiscriminationMetrics(
        n_apt_scored=len(apt_scores),
        n_inapt_scored=len(inapt_scores),
        mean_apt_score=agg["mean_apt_score"],
        mean_inapt_score=agg["mean_inapt_score"],
        separation_score=agg["separation_score"],
        median_threshold=round(threshold, 6),
        aptness_rate=round(classify["aptness_rate"], 6),
        false_positive_rate=round(classify["false_positive_rate"], 6),
        per_reason_breakdown=breakdown,
    )


# ---------------------------------------------------------------------------
# Report writer — Phase 1b mirrors Phase 1a's gate-check tables and adds
# discrimination sections.
# ---------------------------------------------------------------------------


def write_report(
    path: Path,
    apt_metrics: GateMetrics,
    inapt_metrics: GateMetrics,
    apt_scored: list[ScoredVehicle],
    inapt_scored: list[ScoredInaptVehicle],
    concept_violations: list[str],
    unsnapped_concepts: list[str],
    discrimination: DiscriminationMetrics,
) -> None:
    """Write the Phase 1b gate-check + discrimination report."""
    lines: list[str] = [
        "# Metaphor Spike Phase 1b — Gate-Check + Discrimination Report",
        "",
        f"Generated by `metaphor_spike_1b.py`. Topics: {len(TOPICS)} · "
        f"Model: {MODEL_HAIKU} · Prompt types: 2 · Total calls: "
        f"{len(TOPICS) * 2}",
        "",
        "Architecture: Sonnet-as-prompt-engineer. Sonnet generated 3 gold "
        "few-shot examples (love, knowledge, fear) outside the test set; "
        "Haiku then drafts all 40 spike responses using those baked-in "
        "examples.",
        "",
        "## Phase 1b Gate-Check Metrics",
        "",
        "### Apt Prompt",
        "",
        "| Model | Calls | Parse OK | Schema OK | Single-word % | Snap rate |",
        "|-------|-------|----------|-----------|---------------|-----------|",
        f"| {apt_metrics.model} | {apt_metrics.n_calls} | "
        f"{apt_metrics.parse_ok_rate:.0%} | {apt_metrics.schema_ok_rate:.0%} | "
        f"{apt_metrics.single_word_rate:.0%} | {apt_metrics.snap_rate:.0%} |",
        "",
        "### Inapt Prompt",
        "",
        "| Model | Calls | Parse OK | Schema OK |",
        "|-------|-------|----------|-----------|",
        f"| {inapt_metrics.model} | {inapt_metrics.n_calls} | "
        f"{inapt_metrics.parse_ok_rate:.0%} | {inapt_metrics.schema_ok_rate:.0%} |",
        "",
    ]

    # Cascade status counts
    def _status_counts(rows):
        c: dict[str, int] = {}
        for r in rows:
            c[r.cascade_status] = c.get(r.cascade_status, 0) + 1
        return c

    apt_counts = _status_counts(apt_scored)
    inapt_counts = _status_counts(inapt_scored)

    lines += [
        "## Cascade Score Summary",
        "",
        "| Cohort | Scored | Gate dropped | Unresolved | Missing concreteness | No properties |",
        "|--------|--------|--------------|------------|----------------------|---------------|",
        f"| apt   | {apt_counts.get('scored', 0)} | {apt_counts.get('gate_dropped', 0)} | "
        f"{apt_counts.get('unresolved', 0)} | {apt_counts.get('missing_concreteness', 0)} | "
        f"{apt_counts.get('no_properties', 0)} |",
        f"| inapt | {inapt_counts.get('scored', 0)} | {inapt_counts.get('gate_dropped', 0)} | "
        f"{inapt_counts.get('unresolved', 0)} | {inapt_counts.get('missing_concreteness', 0)} | "
        f"{inapt_counts.get('no_properties', 0)} |",
        "",
        "## Discrimination Metrics",
        "",
        f"- Mean apt score (scored only): **{discrimination.mean_apt_score:.4f}** "
        f"(n={discrimination.n_apt_scored})",
        f"- Mean inapt score (scored only): **{discrimination.mean_inapt_score:.4f}** "
        f"(n={discrimination.n_inapt_scored})",
        f"- **Separation score = {discrimination.separation_score:+.4f}** "
        f"(apt_mean − inapt_mean; positive = cascade ranks apt above inapt)",
        f"- Median threshold (apt ∪ inapt): {discrimination.median_threshold:.4f}",
        f"- **Aptness rate = {discrimination.aptness_rate:.0%}** "
        f"(fraction of apt scores above median)",
        f"- False positive rate = {discrimination.false_positive_rate:.0%} "
        f"(fraction of inapt scores above median)",
        "",
        "### Per-`inapt_reason_type` Discrimination",
        "",
        "How often the cascade ranks each inapt failure mode at-or-below "
        "the apt∪inapt median (higher discriminated_rate = cascade catches "
        "this failure mode better).",
        "",
        "| Reason | n_total | n_scored | Mean score | Discriminated rate | Gate-pass rate |",
        "|--------|---------|----------|------------|--------------------|----------------|",
    ]
    for reason, b in sorted(discrimination.per_reason_breakdown.items()):
        lines.append(
            f"| {reason} | {b['n_total']} | {b['n_scored']} | "
            f"{b['mean_score']:.4f} | {b['discriminated_rate']:.0%} | "
            f"{b['gate_pass_rate']:.0%} |"
        )
    lines.append("")

    if concept_violations:
        lines += [
            "## Multi-word Concept Violations",
            "",
            "These `concept` values contain spaces — they failed the single-word constraint.",
            "",
        ]
        for cv in sorted(set(concept_violations)):
            lines.append(f"- `{cv}`")
        lines.append("")

    if unsnapped_concepts:
        lines += [
            "## Unsnapped Concepts",
            "",
            "These concept words had no entry in the `lemmas` table.",
            "",
        ]
        for uc in sorted(set(unsnapped_concepts)):
            lines.append(f"- `{uc}`")
        lines.append("")

    lines += [
        "## Manual Eyeball Quality Pass",
        "",
        "Operator: fill in after reviewing JSONL output files.",
        "",
        "| Topic | Haiku apt quality | Notes |",
        "|-------|------------------|-------|",
    ]
    for t in TOPICS:
        lines.append(f"| {t['word']} | | |")

    lines += [
        "",
        "### Gate Decision (Phase 1b → Phase 2)",
        "",
        "- [ ] JSON parseability ≥80%: **PASS / FAIL**",
        "- [ ] Schema compliance ≥80%: **PASS / FAIL**",
        "- [ ] Single-word concept compliance ≥90%: **PASS / FAIL**",
        "- [ ] Concept snap-rate ≥80%: **PASS / FAIL**",
        "- [ ] Separation score > 0 (cascade ranks apt above inapt): **PASS / FAIL**",
        "- [ ] Manual eyeball quality acceptable: **PASS / FAIL**",
        "",
        "**Overall Phase 1b verdict:** PASS / FAIL",
        "",
    ]

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")
    log.info("wrote report to %s", path)


# ---------------------------------------------------------------------------
# Spike orchestration.
# ---------------------------------------------------------------------------


def run_spike(db_path: Path, output_dir: Path) -> None:
    """Run the Phase 1b spike: 40 Haiku calls + cascade scoring + report."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    if not db_path.exists():
        raise FileNotFoundError(f"DB not found: {db_path}")

    with closing(sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)) as conn:
        run_ts = datetime.now().strftime("%Y%m%dT%H%M%S")
        log.info("run_timestamp=%s", run_ts)

        output_dir.mkdir(parents=True, exist_ok=True)

        def _path(stem: str, ext: str = "jsonl") -> Path:
            return output_dir / f"metaphor_spike_{stem}_phase1b_{run_ts}.{ext}"

        apt_path = _path("apt")
        inapt_path = _path("inapt")
        scores_path = _path("scores")
        report_path = _path("scoring", ext="md")

        for p in (apt_path, inapt_path, scores_path, report_path):
            if p.exists():
                raise FileExistsError(
                    f"Output file already exists: {p} — same-second re-run detected. "
                    f"Wait one second and re-invoke."
                )

        apt_validations: list[AptValidation] = []
        inapt_validations: list[InaptValidation] = []
        apt_scored_all: list[ScoredVehicle] = []
        inapt_scored_all: list[ScoredInaptVehicle] = []
        concept_violations: list[str] = []
        apt_concepts: list[str] = []

        for topic in TOPICS:
            word = topic["word"]
            gloss = topic["gloss"]
            log.info("topic: %s", word)

            # --- Apt call -----------------------------------------------------
            apt_prompt = build_apt_prompt(word, gloss)
            try:
                raw_apt = prompt_json(apt_prompt, model=MODEL_HAIKU, expect=dict)
                raw_apt["_gloss"] = gloss
                write_jsonl_line(apt_path, raw_apt)
                v_apt = validate_apt_response(raw_apt)
            except ClaudeError as e:
                log.warning("apt call failed topic=%s: %s", word, e)
                raw_apt = {"topic": word, "metaphors": [], "_error": str(e)}
                write_jsonl_line(apt_path, raw_apt)
                v_apt = AptValidation(
                    schema_ok=False,
                    n_vehicles=0,
                    n_concepts=0,
                    n_single_word_concepts=0,
                    concept_violations=[],
                    schema_errors=[f"parse_failure: {e}"],
                )

            apt_validations.append(v_apt)
            concept_violations.extend(v_apt.concept_violations)
            apt_concepts.extend(
                sf["concept"]
                for m_entry in raw_apt.get("metaphors", [])
                if isinstance(m_entry, dict)
                for sf in m_entry.get("shared_features", [])
                if isinstance(sf, dict) and isinstance(sf.get("concept"), str)
            )

            if v_apt.schema_ok:
                apt_scored = _score_apt_local(conn, raw_apt, PRODUCTION_CASCADE_CONFIG)
                apt_scored_all.extend(apt_scored)
                for sv in apt_scored:
                    write_jsonl_line(scores_path, {
                        "cohort": "apt",
                        "topic": sv.topic,
                        "vehicle": sv.vehicle,
                        "synset_topic": sv.synset_topic,
                        "synset_vehicle": sv.synset_vehicle,
                        "cascade_status": sv.cascade_status,
                        "final_score": sv.final_score,
                        "gate_passed": sv.gate_passed,
                    })

            # --- Inapt call ---------------------------------------------------
            inapt_prompt = build_inapt_prompt(word, gloss)
            try:
                raw_inapt = prompt_json(inapt_prompt, model=MODEL_HAIKU, expect=dict)
                raw_inapt["_gloss"] = gloss
                write_jsonl_line(inapt_path, raw_inapt)
                v_inapt = validate_inapt_response(raw_inapt)
            except ClaudeError as e:
                log.warning("inapt call failed topic=%s: %s", word, e)
                raw_inapt = {"topic": word, "inapt_metaphors": [], "_error": str(e)}
                write_jsonl_line(inapt_path, raw_inapt)
                v_inapt = InaptValidation(
                    schema_ok=False,
                    n_vehicles=0,
                    schema_errors=[f"parse_failure: {e}"],
                )
            inapt_validations.append(v_inapt)

            if v_inapt.schema_ok:
                inapt_scored = score_inapt_vehicles(conn, raw_inapt, PRODUCTION_CASCADE_CONFIG)
                inapt_scored_all.extend(inapt_scored)
                for sv in inapt_scored:
                    write_jsonl_line(scores_path, {
                        "cohort": "inapt",
                        "topic": sv.topic,
                        "vehicle": sv.vehicle,
                        "inapt_reason_type": sv.inapt_reason_type,
                        "synset_topic": sv.synset_topic,
                        "synset_vehicle": sv.synset_vehicle,
                        "cascade_status": sv.cascade_status,
                        "final_score": sv.final_score,
                        "gate_passed": sv.gate_passed,
                    })

        snap = check_concept_snap_rate(conn, apt_concepts)
        apt_metrics = compute_gate_metrics(
            apt_validations, snap, model=MODEL_HAIKU, prompt_type="apt"
        )
        # Coerce InaptValidation rows into the AptValidation shape the
        # aggregator expects — only parse_ok and schema_ok rates apply.
        inapt_metrics = compute_gate_metrics(
            [
                AptValidation(
                    schema_ok=v.schema_ok,
                    n_vehicles=v.n_vehicles,
                    n_concepts=0,
                    n_single_word_concepts=0,
                    concept_violations=[],
                    schema_errors=v.schema_errors,
                )
                for v in inapt_validations
            ],
            ConceptSnapResult(n_concepts=0, n_snapped=0, snap_rate=0.0, unsnapped=[]),
            model=MODEL_HAIKU,
            prompt_type="inapt",
        )

        discrimination = compute_discrimination(apt_scored_all, inapt_scored_all)

    # write_report runs after the DB connection is released.
    write_report(
        report_path,
        apt_metrics,
        inapt_metrics,
        apt_scored_all,
        inapt_scored_all,
        concept_violations,
        snap.unsnapped,
        discrimination,
    )

    print("\n=== Phase 1b Gate-Check Summary ===")
    print(
        f"  apt    parse={apt_metrics.parse_ok_rate:.0%}  "
        f"schema={apt_metrics.schema_ok_rate:.0%}  "
        f"single-word={apt_metrics.single_word_rate:.0%}  "
        f"snap={apt_metrics.snap_rate:.0%}"
    )
    print(
        f"  inapt  parse={inapt_metrics.parse_ok_rate:.0%}  "
        f"schema={inapt_metrics.schema_ok_rate:.0%}"
    )
    print(
        f"  separation={discrimination.separation_score:+.4f}  "
        f"aptness_rate={discrimination.aptness_rate:.0%}  "
        f"fp_rate={discrimination.false_positive_rate:.0%}"
    )
    print(f"\nReport: {report_path}")
    print(f"Scores: {scores_path}")


def _score_apt_local(
    conn: sqlite3.Connection,
    apt_response: dict,
    config: CascadeConfig,
) -> list[ScoredVehicle]:
    """Score apt vehicles — wrapped here so Phase 1b owns its own retry/log
    policy without depending on Phase 1a's function staying stable.

    Logic mirrors Phase 1a's score_apt_vehicles exactly.
    """
    topic_word = apt_response.get("topic", "")
    metaphors = apt_response.get("metaphors", [])
    sid_topic = lookup_primary_synset(conn, topic_word)
    out: list[ScoredVehicle] = []
    for m in metaphors:
        if not isinstance(m, dict):
            continue
        vehicle_word = m.get("vehicle", "")
        if not isinstance(vehicle_word, str):
            vehicle_word = ""
        sid_vehicle = lookup_primary_synset(conn, vehicle_word)
        if sid_topic is None or sid_vehicle is None:
            out.append(ScoredVehicle(
                topic=topic_word, vehicle=vehicle_word,
                synset_topic=sid_topic, synset_vehicle=sid_vehicle,
                cascade_status="unresolved", final_score=None, gate_passed=False,
            ))
            continue
        try:
            cr = evaluate_cascade_pair(conn, sid_topic, sid_vehicle, config)
        except Exception as e:
            log.warning("apt cascade scoring failed topic=%r vehicle=%r: %s",
                        topic_word, vehicle_word, e)
            out.append(ScoredVehicle(
                topic=topic_word, vehicle=vehicle_word,
                synset_topic=sid_topic, synset_vehicle=sid_vehicle,
                cascade_status="unresolved", final_score=None, gate_passed=False,
            ))
            continue
        out.append(ScoredVehicle(
            topic=topic_word, vehicle=vehicle_word,
            synset_topic=sid_topic, synset_vehicle=sid_vehicle,
            cascade_status=cr.status, final_score=cr.final_score,
            gate_passed=cr.gate_passed,
        ))
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument(
        "--db", type=Path,
        default=Path(__file__).resolve().parent.parent / "output" / "lexicon_v2.db",
        help="Path to lexicon_v2.db (default: data-pipeline/output/lexicon_v2.db)",
    )
    ap.add_argument(
        "--output-dir", type=Path,
        default=Path(__file__).resolve().parent.parent / "output",
        help="Directory for JSONL and report output (default: data-pipeline/output)",
    )
    args = ap.parse_args(argv)
    run_spike(args.db, args.output_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
