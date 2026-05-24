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

import json
import logging
import sqlite3
import argparse
from datetime import datetime
from dataclasses import dataclass, field
from typing import Optional

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
            dim = sf.get("dimension", "")
            concept = sf.get("concept", "")
            if dim not in _VALID_DIMENSIONS:
                errors.append(
                    f"metaphor[{i}].shared_features[{j}] invalid dimension {dim!r}"
                )
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
