"""Metaphor Enrichment Spike — Phase 1a runner.

5 anchor topics × 2 models × 2 prompts = 20 LLM calls.
Hand-curated topic glosses; no LLM gloss generation (Phase 2 work).

Usage:
    python data-pipeline/scripts/metaphor_spike_1a.py \\
        --db data-pipeline/output/lexicon_v2.db \\
        --output-dir data-pipeline/output

Outputs (written to --output-dir; <TS> = YYYYMMDDTHHMMSS run timestamp):
    metaphor_spike_apt_haiku_phase1a_<TS>.jsonl
    metaphor_spike_apt_sonnet_phase1a_<TS>.jsonl
    metaphor_spike_inapt_haiku_phase1a_<TS>.jsonl
    metaphor_spike_inapt_sonnet_phase1a_<TS>.jsonl
    metaphor_spike_scores_phase1a_<TS>.jsonl
    metaphor_spike_scoring_phase1a_<TS>.md
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "lib"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import json
import logging
import sqlite3
import argparse
from datetime import datetime
from dataclasses import dataclass, field
from typing import Optional

from evaluate_cascade import evaluate_cascade_pair, CascadeConfig
from evaluate_aptness import lookup_primary_synset
from claude_client import prompt_json, ClaudeError

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Anchor topics — hand-curated for Phase 1a.
# Covers: Lakoff classic (anger), concrete metaphor-rich (heart),
# compound noun (deadline), emotion (anxiety), emotion/grief (grief).
# Gloss kept tight — one clause — matching the spike doc's "word + tight
# Claude-summarised gloss" input shape without building a gloss generator.
# ---------------------------------------------------------------------------
TOPICS: list[dict[str, str]] = [
    {
        "word": "anger",
        "gloss": "a strong feeling of displeasure or hostility",
    },
    {
        "word": "heart",
        "gloss": "the hollow muscular organ that pumps blood through the body",
    },
    {
        "word": "deadline",
        "gloss": "a point in time by which something must be completed",
    },
    {
        "word": "anxiety",
        "gloss": "a feeling of worry and unease about uncertain outcomes",
    },
    {
        "word": "grief",
        "gloss": "deep sorrow caused by loss or bereavement",
    },
]

# ---------------------------------------------------------------------------
# Model aliases — full model IDs as required by claude -p --model flag.
# ---------------------------------------------------------------------------
MODEL_HAIKU = "claude-haiku-4-5-20251001"
MODEL_SONNET = "claude-sonnet-4-6"

MODELS = [MODEL_HAIKU, MODEL_SONNET]

# ---------------------------------------------------------------------------
# Prompt templates (verbatim from spike doc — do not paraphrase).
# ---------------------------------------------------------------------------

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

EXAMPLE
Input: anger (a strong feeling of displeasure)
Output: {{"topic":"anger","metaphors":[
  {{"vehicle":"fire","shared_features":[
    {{"dimension":"sensorimotor","concept":"heat"}},
    {{"dimension":"behaviour","concept":"spreading"}},
    {{"dimension":"behaviour","concept":"consumption"}},
    {{"dimension":"effect","concept":"destruction"}},
    {{"dimension":"emotional","concept":"intensity"}}],"confidence":0.95}},
  {{"vehicle":"storm","shared_features":[
    {{"dimension":"behaviour","concept":"buildup"}},
    {{"dimension":"behaviour","concept":"release"}},
    {{"dimension":"sensorimotor","concept":"turbulence"}},
    {{"dimension":"effect","concept":"damage"}}],"confidence":0.85}},
  {{"vehicle":"volcano","shared_features":[
    {{"dimension":"behaviour","concept":"pressure"}},
    {{"dimension":"behaviour","concept":"eruption"}},
    {{"dimension":"sensorimotor","concept":"heat"}},
    {{"dimension":"emotional","concept":"release"}}],"confidence":0.85}},
  {{"vehicle":"beast","shared_features":[
    {{"dimension":"behaviour","concept":"taming"}},
    {{"dimension":"functional","concept":"agency"}},
    {{"dimension":"social","concept":"fear"}}],"confidence":0.7}}]}}

EXAMPLE
Input: time (an indefinite period as a continuum)
Output: {{"topic":"time","metaphors":[
  {{"vehicle":"money","shared_features":[
    {{"dimension":"functional","concept":"spending"}},
    {{"dimension":"functional","concept":"saving"}},
    {{"dimension":"social","concept":"budgeting"}},
    {{"dimension":"behaviour","concept":"tracking"}}],"confidence":0.95}},
  {{"vehicle":"river","shared_features":[
    {{"dimension":"behaviour","concept":"flowing"}},
    {{"dimension":"sensorimotor","concept":"motion"}},
    {{"dimension":"effect","concept":"erosion"}}],"confidence":0.9}},
  {{"vehicle":"thief","shared_features":[
    {{"dimension":"behaviour","concept":"taking"}},
    {{"dimension":"effect","concept":"loss"}},
    {{"dimension":"emotional","concept":"grief"}}],"confidence":0.75}}]}}

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
- single_dimension: shares only one of {{sensorimotor, behaviour,
  functional, effect, emotional, social}}. Insufficient resonance.
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

EXAMPLE
Input: anger (a strong feeling of displeasure)
Output: {{"topic":"anger","inapt_metaphors":[
  {{"vehicle":"calendar","inapt_reason_type":"single_dimension","explanation":"shares only the functional dimension of time-tracking; no sensorimotor, emotional, or behavioural resonance"}},
  {{"vehicle":"fury","inapt_reason_type":"same_domain","explanation":"near-synonym in the emotion domain; not a cross-domain mapping at all"}},
  {{"vehicle":"emotion","inapt_reason_type":"synonym_or_hypernym","explanation":"anger is a kind-of emotion; a taxonomic parent, not a metaphor"}}]}}

EXAMPLE
Input: time (an indefinite period as a continuum)
Output: {{"topic":"time","inapt_metaphors":[
  {{"vehicle":"clock","inapt_reason_type":"single_dimension","explanation":"shares only the functional dimension of measurement; clock is an instrument of time, not a structurally-different domain mapping onto it"}},
  {{"vehicle":"duration","inapt_reason_type":"same_domain","explanation":"near-synonym; same conceptual domain, no cross-domain leap"}},
  {{"vehicle":"eternity","inapt_reason_type":"wrong_concreteness","explanation":"more abstract than time itself; vehicle should be more concrete than topic"}}]}}

Input: {topic} ({gloss})
Output:\
"""


def build_apt_prompt(topic: str, gloss: str) -> str:
    """Render the apt prompt template for a single topic."""
    return _APT_TEMPLATE.format(topic=topic, gloss=gloss)


def build_inapt_prompt(topic: str, gloss: str) -> str:
    """Render the inapt prompt template for a single topic."""
    return _INAPT_TEMPLATE.format(topic=topic, gloss=gloss)


_VALID_DIMENSIONS = frozenset({
    "sensorimotor", "behaviour", "functional", "effect", "emotional", "social",
})

_VALID_INAPT_REASON_TYPES = frozenset({
    "single_dimension", "same_domain", "wrong_concreteness",
    "dead_metaphor", "synonym_or_hypernym",
})


@dataclass
class AptValidation:
    """Validation result for one apt LLM response object."""
    schema_ok: bool
    n_vehicles: int
    n_concepts: int
    n_single_word_concepts: int
    concept_violations: list[str]  # multi-word concept strings
    schema_errors: list[str]       # structural problems


@dataclass
class InaptValidation:
    """Validation result for one inapt LLM response object."""
    schema_ok: bool
    n_vehicles: int
    schema_errors: list[str]


def validate_apt_response(raw: dict) -> AptValidation:
    """Validate one apt LLM response against the spike doc schema.

    Checks:
    - top-level "metaphors" key present and a list
    - each metaphor has "vehicle" (str), "shared_features" (list), "confidence" (float)
    - each shared_feature has "dimension" (valid enum) and "concept" (str)
    - concept single-word compliance (no spaces)
    """
    errors: list[str] = []
    concept_violations: list[str] = []
    n_vehicles = 0
    n_concepts = 0
    n_single_word = 0

    metaphors = raw.get("metaphors")
    if not isinstance(metaphors, list):
        errors.append("missing or non-list 'metaphors' key")
        return AptValidation(
            schema_ok=False,
            n_vehicles=0,
            n_concepts=0,
            n_single_word_concepts=0,
            concept_violations=[],
            schema_errors=errors,
        )

    for i, m in enumerate(metaphors):
        if not isinstance(m, dict):
            errors.append(f"metaphor[{i}] is not a dict (got {type(m).__name__})")
            continue
        if not isinstance(m.get("vehicle"), str):
            errors.append(f"metaphor[{i}] missing 'vehicle'")
        if not isinstance(m.get("confidence"), (int, float)):
            errors.append(f"metaphor[{i}] missing numeric 'confidence'")

        features = m.get("shared_features")
        if not isinstance(features, list):
            errors.append(f"metaphor[{i}] missing 'shared_features' list")
            continue

        n_vehicles += 1
        for j, sf in enumerate(features):
            if not isinstance(sf, dict):
                errors.append(
                    f"metaphor[{i}].shared_features[{j}] is not a dict "
                    f"(got {type(sf).__name__})"
                )
                continue
            dim = sf.get("dimension", "")
            concept = sf.get("concept", "")
            if dim not in _VALID_DIMENSIONS:
                errors.append(
                    f"metaphor[{i}].shared_features[{j}] invalid dimension {dim!r}"
                )
            if not isinstance(concept, str):
                errors.append(
                    f"metaphor[{i}].shared_features[{j}] concept is not a string"
                )
                n_concepts += 1
                concept_violations.append(repr(concept))
                continue
            n_concepts += 1
            if " " not in concept.strip():
                n_single_word += 1
            else:
                concept_violations.append(concept)

    return AptValidation(
        schema_ok=len(errors) == 0,
        n_vehicles=n_vehicles,
        n_concepts=n_concepts,
        n_single_word_concepts=n_single_word,
        concept_violations=concept_violations,
        schema_errors=errors,
    )


def validate_inapt_response(raw: dict) -> InaptValidation:
    """Validate one inapt LLM response against the spike doc schema."""
    errors: list[str] = []
    n_vehicles = 0

    inapt_metaphors = raw.get("inapt_metaphors")
    if not isinstance(inapt_metaphors, list):
        errors.append("missing or non-list 'inapt_metaphors' key")
        return InaptValidation(schema_ok=False, n_vehicles=0, schema_errors=errors)

    for i, m in enumerate(inapt_metaphors):
        if not isinstance(m, dict):
            errors.append(
                f"inapt_metaphors[{i}] is not a dict (got {type(m).__name__})"
            )
            continue
        if not isinstance(m.get("vehicle"), str):
            errors.append(f"inapt_metaphors[{i}] missing 'vehicle'")
        reason = m.get("inapt_reason_type", "")
        if reason not in _VALID_INAPT_REASON_TYPES:
            errors.append(
                f"inapt_metaphors[{i}] invalid inapt_reason_type {reason!r}"
            )
        if not isinstance(m.get("explanation"), str):
            errors.append(f"inapt_metaphors[{i}] missing 'explanation'")
        n_vehicles += 1

    return InaptValidation(
        schema_ok=len(errors) == 0,
        n_vehicles=n_vehicles,
        schema_errors=errors,
    )


@dataclass
class ConceptSnapResult:
    n_concepts: int
    n_snapped: int
    snap_rate: float      # 0.0 when n_concepts == 0
    unsnapped: list[str]  # concepts that had no lemmas row


def check_concept_snap_rate(
    conn: sqlite3.Connection, concepts: list[str]
) -> ConceptSnapResult:
    """Check how many concept words resolve against the lemmas table.

    Each concept is looked up case-insensitively. Duplicates are
    counted once per unique string (same concept appearing in multiple
    shared_features entries for different vehicles is deduplicated so
    one bad word doesn't dominate the rate unfairly).
    """
    if not concepts:
        return ConceptSnapResult(
            n_concepts=0, n_snapped=0, snap_rate=0.0, unsnapped=[]
        )

    unique = list(dict.fromkeys(
        c.strip().lower()
        for c in concepts
        if isinstance(c, str) and c.strip()
    ))
    snapped: list[str] = []
    unsnapped: list[str] = []

    for word in unique:
        row = conn.execute(
            "SELECT 1 FROM lemmas WHERE lemma = ? LIMIT 1", (word,)
        ).fetchone()
        if row:
            snapped.append(word)
        else:
            unsnapped.append(word)

    n = len(unique)
    return ConceptSnapResult(
        n_concepts=n,
        n_snapped=len(snapped),
        snap_rate=len(snapped) / n if n else 0.0,
        unsnapped=unsnapped,
    )


# Production-blessed cascade config from M03 — gate=1.0, alpha=1.0, additive.
# Documented in docs/memory/m03_cascade_winner_config.md.
PRODUCTION_CASCADE_CONFIG = CascadeConfig(
    concreteness_threshold=1.0,
    ortony_scoring="jaccard_salience",
    alpha=1.0,
    composition="additive",
)


@dataclass
class ScoredVehicle:
    """Cascade score result for one (topic, vehicle) pair from an apt response."""
    topic: str
    vehicle: str
    synset_topic: Optional[str]
    synset_vehicle: Optional[str]
    cascade_status: str   # CascadeStatus literal
    final_score: Optional[float]
    gate_passed: bool


def write_jsonl_line(path: Path, obj: dict) -> None:
    """Append one JSON object as a newline to path.

    Creates parent directories if absent. If `obj` is not
    JSON-serialisable the line is skipped with a WARNING — the
    spike runner must not abort on a single bad payload.
    Thread-safety: this runner is single-threaded; no locking needed.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        line = json.dumps(obj, ensure_ascii=False)
    except (TypeError, ValueError) as e:
        log.warning("write_jsonl_line: skipping non-serialisable payload (%s)", e)
        return
    try:
        with path.open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")
    except OSError as e:
        log.warning("write_jsonl_line: write failed for %s: %s", path, e)


def score_apt_vehicles(
    conn: sqlite3.Connection,
    apt_response: dict,
    config: CascadeConfig,
) -> list[ScoredVehicle]:
    """Score each vehicle in an apt response through the cascade.

    Returns one ScoredVehicle per metaphor entry in the response.
    Vehicles that cannot be resolved to a synset_id receive status
    "unresolved" — they are returned (not dropped) so the caller can
    track attrition.
    """
    topic_word = apt_response.get("topic", "")
    metaphors = apt_response.get("metaphors", [])

    sid_topic = lookup_primary_synset(conn, topic_word)
    results: list[ScoredVehicle] = []

    for m in metaphors:
        if not isinstance(m, dict):
            continue
        vehicle_word = m.get("vehicle", "")
        if not isinstance(vehicle_word, str):
            vehicle_word = ""
        sid_vehicle = lookup_primary_synset(conn, vehicle_word)

        if sid_topic is None or sid_vehicle is None:
            results.append(
                ScoredVehicle(
                    topic=topic_word,
                    vehicle=vehicle_word,
                    synset_topic=sid_topic,
                    synset_vehicle=sid_vehicle,
                    cascade_status="unresolved",
                    final_score=None,
                    gate_passed=False,
                )
            )
            continue

        try:
            cr = evaluate_cascade_pair(conn, sid_topic, sid_vehicle, config)
        except Exception as e:
            log.warning(
                "cascade scoring failed topic=%r vehicle=%r: %s",
                topic_word, vehicle_word, e,
            )
            results.append(
                ScoredVehicle(
                    topic=topic_word,
                    vehicle=vehicle_word,
                    synset_topic=sid_topic,
                    synset_vehicle=sid_vehicle,
                    cascade_status="unresolved",
                    final_score=None,
                    gate_passed=False,
                )
            )
            continue

        results.append(
            ScoredVehicle(
                topic=topic_word,
                vehicle=vehicle_word,
                synset_topic=sid_topic,
                synset_vehicle=sid_vehicle,
                cascade_status=cr.status,
                final_score=cr.final_score,
                gate_passed=cr.gate_passed,
            )
        )

    return results


@dataclass
class GateMetrics:
    """Phase 1a gate-check metrics for one (model, prompt_type) combination."""
    model: str
    prompt_type: str   # "apt" or "inapt"
    n_calls: int
    parse_ok_rate: float
    schema_ok_rate: float
    single_word_rate: float   # apt only; 0.0 for inapt
    snap_rate: float          # apt only; 0.0 for inapt


def compute_gate_metrics(
    validations: list[AptValidation],
    snap: ConceptSnapResult,
    model: str = "",
    prompt_type: str = "apt",
) -> GateMetrics:
    """Aggregate validation results into gate-check metrics.

    parse_ok_rate: fraction of calls that produced a parseable object
    (parse failures are represented by AptValidation with schema_ok=False
    and schema_errors containing 'parse_failure').
    schema_ok_rate: fraction of parseable responses with valid schema.
    single_word_rate: fraction of all concept strings that are single words.
    snap_rate: taken directly from ConceptSnapResult.snap_rate.
    """
    n = len(validations)
    if n == 0:
        return GateMetrics(
            model=model,
            prompt_type=prompt_type,
            n_calls=0,
            parse_ok_rate=0.0,
            schema_ok_rate=0.0,
            single_word_rate=0.0,
            snap_rate=0.0,
        )

    # Parse failures are injected as validations with a specific schema_error
    n_parse_ok = sum(
        1 for v in validations
        if not any("parse_failure" in e for e in v.schema_errors)
    )
    n_schema_ok = sum(1 for v in validations if v.schema_ok)

    total_concepts = sum(v.n_concepts for v in validations)
    total_single_word = sum(v.n_single_word_concepts for v in validations)
    single_word_rate = (
        round(total_single_word / total_concepts, 6) if total_concepts else 0.0
    )

    return GateMetrics(
        model=model,
        prompt_type=prompt_type,
        n_calls=n,
        parse_ok_rate=round(n_parse_ok / n, 6),
        schema_ok_rate=round(n_schema_ok / n, 6),
        single_word_rate=single_word_rate,
        snap_rate=round(snap.snap_rate, 6),
    )


def write_report(
    path: Path,
    apt_metrics: list[GateMetrics],
    inapt_metrics: list[GateMetrics],
    scored_vehicles: list[ScoredVehicle],
    concept_violations: list[str],
    unsnapped_concepts: list[str],
) -> None:
    """Write the gate-check Markdown report.

    This file is the human-eyeball scratchpad. It contains:
    - Gate-check metric tables (one row per model/prompt_type)
    - Cascade score summary (mean scored, gate_dropped, unresolved counts)
    - Concept violation list (multi-word concepts)
    - Unsnapped concept list (concepts absent from lemmas table)
    - Manual eyeball section (pre-populated header, blank body for operator)
    """
    lines: list[str] = [
        "# Metaphor Spike Phase 1a — Gate-Check Report",
        "",
        f"Generated by `metaphor_spike_1a.py`. Topics: {len(TOPICS)} · "
        f"Models: {len(MODELS)} · Prompt types: 2 · Total calls: "
        f"{len(TOPICS) * len(MODELS) * 2}",
        "",
        "## Phase 1a Gate-Check Metrics",
        "",
        "### Apt Prompt",
        "",
        "| Model | Calls | Parse OK | Schema OK | Single-word % | Snap rate |",
        "|-------|-------|----------|-----------|---------------|-----------|",
    ]
    for m in apt_metrics:
        lines.append(
            f"| {m.model} | {m.n_calls} | {m.parse_ok_rate:.0%} | "
            f"{m.schema_ok_rate:.0%} | {m.single_word_rate:.0%} | "
            f"{m.snap_rate:.0%} |"
        )

    lines += [
        "",
        "### Inapt Prompt",
        "",
        "| Model | Calls | Parse OK | Schema OK |",
        "|-------|-------|----------|-----------|",
    ]
    for m in inapt_metrics:
        lines.append(
            f"| {m.model} | {m.n_calls} | {m.parse_ok_rate:.0%} | "
            f"{m.schema_ok_rate:.0%} |"
        )

    # Cascade scores
    status_counts: dict[str, int] = {}
    scores: list[float] = []
    for sv in scored_vehicles:
        status_counts[sv.cascade_status] = (
            status_counts.get(sv.cascade_status, 0) + 1
        )
        if sv.final_score is not None:
            scores.append(sv.final_score)

    mean_score = sum(scores) / len(scores) if scores else 0.0
    lines += [
        "",
        "## Cascade Score Summary (apt vehicles only)",
        "",
        f"- Scored pairs: {status_counts.get('scored', 0)}",
        f"- Gate dropped: {status_counts.get('gate_dropped', 0)}",
        f"- Unresolved (lemma miss): {status_counts.get('unresolved', 0)}",
        f"- Missing concreteness: {status_counts.get('missing_concreteness', 0)}",
        f"- No properties: {status_counts.get('no_properties', 0)}",
        f"- Mean cascade score (scored only): {mean_score:.4f}",
        "",
    ]

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
        "| Topic | Haiku apt quality | Sonnet apt quality | Notes |",
        "|-------|------------------|--------------------|-------|",
    ]
    for t in TOPICS:
        lines.append(f"| {t['word']} | | | |")

    lines += [
        "",
        "### Gate Decision",
        "",
        "- [ ] JSON parseability ≥80% per model: **PASS / FAIL**",
        "- [ ] Schema compliance ≥80% per model: **PASS / FAIL**",
        "- [ ] Single-word concept compliance ≥90% per model: **PASS / FAIL**",
        "- [ ] Concept snap-rate ≥80% per model: **PASS / FAIL**",
        "- [ ] Manual eyeball quality acceptable on Sonnet: **PASS / FAIL**",
        "",
        "**Overall Phase 1a verdict:** PASS / FAIL",
        "",
    ]

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")
    log.info("wrote report to %s", path)


def run_spike(db_path: Path, output_dir: Path) -> None:
    """Run the Phase 1a spike: 20 LLM calls + cascade scoring + report.

    Every run produces a fresh set of timestamp-keyed output files
    (YYYYMMDDTHHMMSS computed at run start). Old runs are never
    overwritten — operator commits each run's outputs to git for a
    permanent record.
    """
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    if not db_path.exists():
        raise FileNotFoundError(f"DB not found: {db_path}")

    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)

    # Timestamp suffix for this run — used in every output filename.
    # Matches the existing enrichment naming convention
    # (enrichment_<tag>_<model>_v<ver>_<YYYYMMDD>.json) but with
    # second-level precision so same-day re-runs don't collide.
    run_ts = datetime.now().strftime("%Y%m%dT%H%M%S")
    log.info("run_timestamp=%s", run_ts)

    output_dir.mkdir(parents=True, exist_ok=True)

    # Output file paths — one JSONL per (model, prompt_type) combination,
    # all stamped with the run timestamp.
    def _path(stem: str) -> Path:
        return output_dir / f"metaphor_spike_{stem}_phase1a_{run_ts}.jsonl"

    output_paths: dict[tuple[str, str], Path] = {
        (MODEL_HAIKU, "apt"):    _path("apt_haiku"),
        (MODEL_SONNET, "apt"):   _path("apt_sonnet"),
        (MODEL_HAIKU, "inapt"):  _path("inapt_haiku"),
        (MODEL_SONNET, "inapt"): _path("inapt_sonnet"),
    }
    scores_path = _path("scores")
    report_path = output_dir / f"metaphor_spike_scoring_phase1a_{run_ts}.md"

    # No truncation needed — every run gets fresh timestamp-stamped files.
    # Guard against accidental same-second collisions (extremely rare):
    for p in list(output_paths.values()) + [scores_path, report_path]:
        if p.exists():
            raise FileExistsError(
                f"Output file already exists: {p} — same-second re-run detected. "
                f"Wait one second and re-invoke."
            )

    # Accumulate per-(model, prompt_type) validation results for metrics
    apt_validations: dict[str, list[AptValidation]] = {m: [] for m in MODELS}
    inapt_validations: dict[str, list[InaptValidation]] = {m: [] for m in MODELS}
    all_scored_vehicles: list[ScoredVehicle] = []
    all_concept_violations: list[str] = []
    all_unsnapped: list[str] = []

    total_apt_concepts: dict[str, list[str]] = {m: [] for m in MODELS}

    for topic in TOPICS:
        word = topic["word"]
        gloss = topic["gloss"]
        log.info("topic: %s", word)

        for model in MODELS:
            # --- Apt call ---------------------------------------------------
            apt_prompt = build_apt_prompt(word, gloss)
            log.info("  model=%s  prompt=apt", model)
            try:
                raw_apt = prompt_json(apt_prompt, model=model, expect=dict)
                # Attach gloss locally for human inspection (not echoed by LLM)
                raw_apt["_gloss"] = gloss
                write_jsonl_line(output_paths[(model, "apt")], raw_apt)
                v_apt = validate_apt_response(raw_apt)
            except ClaudeError as e:
                log.warning("apt call failed model=%s topic=%s: %s", model, word, e)
                raw_apt = {"topic": word, "metaphors": [], "_error": str(e)}
                write_jsonl_line(output_paths[(model, "apt")], raw_apt)
                v_apt = AptValidation(
                    schema_ok=False,
                    n_vehicles=0,
                    n_concepts=0,
                    n_single_word_concepts=0,
                    concept_violations=[],
                    schema_errors=[f"parse_failure: {e}"],
                )

            apt_validations[model].append(v_apt)
            all_concept_violations.extend(v_apt.concept_violations)
            total_apt_concepts[model].extend(
                sf["concept"]
                for m_entry in raw_apt.get("metaphors", [])
                if isinstance(m_entry, dict)
                for sf in m_entry.get("shared_features", [])
                if isinstance(sf, dict) and isinstance(sf.get("concept"), str)
            )

            # Score apt vehicles through the cascade
            if v_apt.schema_ok:
                scored = score_apt_vehicles(conn, raw_apt, PRODUCTION_CASCADE_CONFIG)
                all_scored_vehicles.extend(scored)
                for sv in scored:
                    write_jsonl_line(scores_path, {
                        "topic": sv.topic,
                        "vehicle": sv.vehicle,
                        "model": model,
                        "synset_topic": sv.synset_topic,
                        "synset_vehicle": sv.synset_vehicle,
                        "cascade_status": sv.cascade_status,
                        "final_score": sv.final_score,
                        "gate_passed": sv.gate_passed,
                    })

            # --- Inapt call -------------------------------------------------
            inapt_prompt = build_inapt_prompt(word, gloss)
            log.info("  model=%s  prompt=inapt", model)
            try:
                raw_inapt = prompt_json(inapt_prompt, model=model, expect=dict)
                raw_inapt["_gloss"] = gloss
                write_jsonl_line(output_paths[(model, "inapt")], raw_inapt)
                v_inapt = validate_inapt_response(raw_inapt)
            except ClaudeError as e:
                log.warning("inapt call failed model=%s topic=%s: %s", model, word, e)
                raw_inapt = {"topic": word, "inapt_metaphors": [], "_error": str(e)}
                write_jsonl_line(output_paths[(model, "inapt")], raw_inapt)
                v_inapt = InaptValidation(
                    schema_ok=False,
                    n_vehicles=0,
                    schema_errors=[f"parse_failure: {e}"],
                )
            inapt_validations[model].append(v_inapt)

    # --- Aggregate metrics per model ----------------------------------------
    apt_metrics: list[GateMetrics] = []
    inapt_metrics: list[GateMetrics] = []

    for model in MODELS:
        snap = check_concept_snap_rate(conn, total_apt_concepts[model])
        all_unsnapped.extend(snap.unsnapped)

        apt_metrics.append(
            compute_gate_metrics(
                apt_validations[model], snap, model=model, prompt_type="apt"
            )
        )
        inapt_snap = ConceptSnapResult(
            n_concepts=0, n_snapped=0, snap_rate=0.0, unsnapped=[]
        )
        inapt_metrics.append(
            compute_gate_metrics(
                # InaptValidation → coerce to AptValidation shape for the
                # shared aggregator. Only parse_ok_rate and schema_ok_rate
                # are meaningful for inapt.
                [
                    AptValidation(
                        schema_ok=v.schema_ok,
                        n_vehicles=v.n_vehicles,
                        n_concepts=0,
                        n_single_word_concepts=0,
                        concept_violations=[],
                        schema_errors=v.schema_errors,
                    )
                    for v in inapt_validations[model]
                ],
                inapt_snap,
                model=model,
                prompt_type="inapt",
            )
        )

    conn.close()

    write_report(
        report_path,
        apt_metrics,
        inapt_metrics,
        all_scored_vehicles,
        all_concept_violations,
        all_unsnapped,
    )

    # Print gate-check summary to stdout for operator review
    print("\n=== Phase 1a Gate-Check Summary ===")
    for m in apt_metrics:
        print(
            f"  {m.model}  apt  "
            f"parse={m.parse_ok_rate:.0%}  schema={m.schema_ok_rate:.0%}  "
            f"single-word={m.single_word_rate:.0%}  snap={m.snap_rate:.0%}"
        )
    for m in inapt_metrics:
        print(
            f"  {m.model}  inapt  "
            f"parse={m.parse_ok_rate:.0%}  schema={m.schema_ok_rate:.0%}"
        )
    print(f"\nReport: {report_path}")
    print(f"Scores: {scores_path}")


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
    import sys as _sys
    _sys.exit(main())
