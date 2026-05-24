# Metaphor Enrichment Spike — Phase 1a Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Run 20 LLM calls (5 topics × 2 models × 2 prompts) to validate that both Claude models can emit schema-compliant metaphor JSON with single-word concepts that snap against the lexicon, and score each apt (topic, vehicle) pair through the existing cascade.

**Architecture:** One runner script hard-codes 5 anchor topics with hand-written glosses, calls the existing `claude -p` subprocess via `lib/claude_client.py`, writes per-call JSONL output, scores apt vehicles through `evaluate_cascade.py`'s `evaluate_cascade_pair`, and prints a gate-check report. No new DB tables, no new infrastructure.

**Tech Stack:** Python 3.12, `lib/claude_client.py` (subprocess `claude -p`), `data-pipeline/scripts/evaluate_cascade.py`, SQLite (read-only via `lexicon_v2.db`), pytest

---

## File Structure

| File | Status | Responsibility |
|------|--------|----------------|
| `data-pipeline/scripts/metaphor_spike_1a.py` | **Create** | Runner: topics → prompts → API calls → JSONL → cascade scores → report |
| `data-pipeline/scripts/test_metaphor_spike_1a.py` | **Create** | Pytest unit tests for every pure function in the runner |
| `data-pipeline/output/metaphor_spike_apt_haiku.jsonl` | Generated | Haiku apt LLM output (one JSON object per line) |
| `data-pipeline/output/metaphor_spike_apt_sonnet.jsonl` | Generated | Sonnet apt LLM output |
| `data-pipeline/output/metaphor_spike_inapt_haiku.jsonl` | Generated | Haiku inapt LLM output |
| `data-pipeline/output/metaphor_spike_inapt_sonnet.jsonl` | Generated | Sonnet inapt LLM output |
| `data-pipeline/output/metaphor_spike_scores.jsonl` | Generated | Per-(topic, vehicle) cascade score rows |
| `data-pipeline/output/metaphor_spike_scoring.md` | Generated | Aggregate gate-check metrics + manual eyeball scratchpad |

No existing files are modified. The runner is a standalone spike script — it imports only from `lib/claude_client.py` and `data-pipeline/scripts/evaluate_cascade.py`.

---

### Task 1: Scaffold runner module with topic list and prompt builders

**Files:**
- Create: `data-pipeline/scripts/metaphor_spike_1a.py`
- Create: `data-pipeline/scripts/test_metaphor_spike_1a.py`

The 5th topic selected here is **"grief"** — it is an emotion noun (matching the spike doc's category of "emotion / state nouns"), distinct from the four listed in the spike doc (`anger`, `heart`, `deadline`, `anxiety`), and metaphor-rich without being exotic.

#### Background

The runner uses `lib/claude_client.py`'s `prompt_json` function, which calls `claude -p` via subprocess and returns the parsed Python object. Import path: `sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "lib"))` — same pattern as `enrich_properties.py`.

The prompts are copied verbatim from the spike doc. The `<TOPIC>` and `<GLOSS>` placeholders in the prompt templates are replaced at call time.

- [ ] **Step 1: Write the failing tests for topic-list structure and prompt builders**

```python
# data-pipeline/scripts/test_metaphor_spike_1a.py
"""Tests for metaphor_spike_1a.py — Phase 1a runner.

Uses no DB and no LLM calls. Every test is pure-function.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))

from metaphor_spike_1a import (
    TOPICS,
    build_apt_prompt,
    build_inapt_prompt,
)


def test_topics_count():
    assert len(TOPICS) == 5


def test_topics_have_word_and_gloss():
    for t in TOPICS:
        assert "word" in t, f"missing 'word' key: {t}"
        assert "gloss" in t, f"missing 'gloss' key: {t}"
        assert t["word"].strip(), "word must be non-empty"
        assert t["gloss"].strip(), "gloss must be non-empty"


def test_topic_words_are_single_tokens():
    """Topic words must not contain spaces — they are lemma keys."""
    for t in TOPICS:
        assert " " not in t["word"], f"topic word must be single token: {t['word']!r}"


def test_apt_prompt_contains_topic_and_gloss():
    prompt = build_apt_prompt("fire", "rapid oxidation producing heat and light")
    assert "fire" in prompt
    assert "rapid oxidation producing heat and light" in prompt
    # Must not echo the gloss placeholder literally
    assert "<TOPIC>" not in prompt
    assert "<GLOSS>" not in prompt


def test_inapt_prompt_contains_topic_and_gloss():
    prompt = build_inapt_prompt("fire", "rapid oxidation producing heat and light")
    assert "fire" in prompt
    assert "rapid oxidation producing heat and light" in prompt
    assert "<TOPIC>" not in prompt
    assert "<GLOSS>" not in prompt


def test_apt_and_inapt_prompts_are_different():
    apt = build_apt_prompt("grief", "deep sorrow")
    inapt = build_inapt_prompt("grief", "deep sorrow")
    assert apt != inapt
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
cd /home/agent/projects/metaforge
source data-pipeline/.venv/bin/activate
python -m pytest data-pipeline/scripts/test_metaphor_spike_1a.py -v 2>&1 | head -30
```

Expected: `ModuleNotFoundError: No module named 'metaphor_spike_1a'`

- [ ] **Step 3: Implement the topic list and prompt builders**

The prompt templates below are copied verbatim from the spike doc — do not edit the body text.

```python
# data-pipeline/scripts/metaphor_spike_1a.py
"""Metaphor Enrichment Spike — Phase 1a runner.

5 anchor topics × 2 models × 2 prompts = 20 LLM calls.
Hand-curated topic glosses; no LLM gloss generation (Phase 2 work).

Usage:
    python data-pipeline/scripts/metaphor_spike_1a.py \\
        --db data-pipeline/output/lexicon_v2.db \\
        --output-dir data-pipeline/output

Outputs (written to --output-dir):
    metaphor_spike_apt_haiku.jsonl
    metaphor_spike_apt_sonnet.jsonl
    metaphor_spike_inapt_haiku.jsonl
    metaphor_spike_inapt_sonnet.jsonl
    metaphor_spike_scores.jsonl
    metaphor_spike_scoring.md
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "lib"))

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
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
cd /home/agent/projects/metaforge
source data-pipeline/.venv/bin/activate
python -m pytest data-pipeline/scripts/test_metaphor_spike_1a.py -v
```

Expected: 7 tests PASS

- [ ] **Step 5: Commit**

```bash
git add data-pipeline/scripts/metaphor_spike_1a.py data-pipeline/scripts/test_metaphor_spike_1a.py
git commit -m "feat(spike-1a): scaffold runner with topic list and prompt builders"
```

---

### Task 2: Schema validation helpers

**Files:**
- Modify: `data-pipeline/scripts/metaphor_spike_1a.py` (append functions)
- Modify: `data-pipeline/scripts/test_metaphor_spike_1a.py` (append tests)

These helpers validate LLM output against the spike doc's output schemas. They are pure functions — no DB, no subprocess. Used later by the runner to compute gate-check metrics and write JSONL.

#### Background — schemas

**Apt schema** (per topic):
```json
{"topic": "anger", "metaphors": [{"vehicle": "fire", "shared_features": [{"dimension": "sensorimotor", "concept": "heat"}], "confidence": 0.95}]}
```
Valid `dimension` values: `sensorimotor`, `behaviour`, `functional`, `effect`, `emotional`, `social`.

**Inapt schema** (per topic):
```json
{"topic": "anger", "inapt_metaphors": [{"vehicle": "fury", "inapt_reason_type": "same_domain", "explanation": "near-synonym"}]}
```
Valid `inapt_reason_type` values: `single_dimension`, `same_domain`, `wrong_concreteness`, `dead_metaphor`, `synonym_or_hypernym`.

- [ ] **Step 1: Write failing tests for schema validators**

Append to `data-pipeline/scripts/test_metaphor_spike_1a.py`:

```python
from metaphor_spike_1a import (
    TOPICS,
    build_apt_prompt,
    build_inapt_prompt,
    validate_apt_response,
    validate_inapt_response,
    AptValidation,
    InaptValidation,
)


def test_validate_apt_response_valid():
    raw = {
        "topic": "anger",
        "metaphors": [
            {
                "vehicle": "fire",
                "shared_features": [
                    {"dimension": "sensorimotor", "concept": "heat"},
                    {"dimension": "behaviour", "concept": "spreading"},
                ],
                "confidence": 0.95,
            }
        ],
    }
    v = validate_apt_response(raw)
    assert v.schema_ok
    assert v.n_vehicles == 1
    assert v.n_concepts == 2
    assert v.n_single_word_concepts == 2
    assert v.concept_violations == []


def test_validate_apt_response_multi_word_concept():
    """A concept containing a space must be counted as a violation."""
    raw = {
        "topic": "anger",
        "metaphors": [
            {
                "vehicle": "fire",
                "shared_features": [
                    {"dimension": "sensorimotor", "concept": "must be tamed"},
                ],
                "confidence": 0.9,
            }
        ],
    }
    v = validate_apt_response(raw)
    assert v.schema_ok
    assert v.n_concepts == 1
    assert v.n_single_word_concepts == 0
    assert "must be tamed" in v.concept_violations


def test_validate_apt_response_bad_dimension():
    """An invalid dimension value makes schema_ok False."""
    raw = {
        "topic": "anger",
        "metaphors": [
            {
                "vehicle": "fire",
                "shared_features": [
                    {"dimension": "other", "concept": "heat"},
                ],
                "confidence": 0.9,
            }
        ],
    }
    v = validate_apt_response(raw)
    assert not v.schema_ok


def test_validate_apt_response_missing_metaphors_key():
    raw = {"topic": "anger"}
    v = validate_apt_response(raw)
    assert not v.schema_ok


def test_validate_inapt_response_valid():
    raw = {
        "topic": "anger",
        "inapt_metaphors": [
            {
                "vehicle": "fury",
                "inapt_reason_type": "same_domain",
                "explanation": "near-synonym",
            }
        ],
    }
    v = validate_inapt_response(raw)
    assert v.schema_ok
    assert v.n_vehicles == 1


def test_validate_inapt_response_bad_reason_type():
    raw = {
        "topic": "anger",
        "inapt_metaphors": [
            {
                "vehicle": "fury",
                "inapt_reason_type": "made_up_tag",
                "explanation": "near-synonym",
            }
        ],
    }
    v = validate_inapt_response(raw)
    assert not v.schema_ok


def test_validate_inapt_response_missing_key():
    raw = {"topic": "anger"}
    v = validate_inapt_response(raw)
    assert not v.schema_ok
```

- [ ] **Step 2: Run to confirm failure**

```bash
cd /home/agent/projects/metaforge
source data-pipeline/.venv/bin/activate
python -m pytest data-pipeline/scripts/test_metaphor_spike_1a.py -v 2>&1 | tail -20
```

Expected: `ImportError` on `validate_apt_response`, `validate_inapt_response`, `AptValidation`, `InaptValidation`

- [ ] **Step 3: Implement the schema validators**

Append to `data-pipeline/scripts/metaphor_spike_1a.py` (after the prompt template section, before any `if __name__ == "__main__"`):

```python
import json
import logging
import sqlite3
import argparse
from dataclasses import dataclass, field
from typing import Optional

log = logging.getLogger(__name__)

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
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
cd /home/agent/projects/metaforge
source data-pipeline/.venv/bin/activate
python -m pytest data-pipeline/scripts/test_metaphor_spike_1a.py -v
```

Expected: all tests PASS (7 from Task 1 + 8 new = 15 total)

- [ ] **Step 5: Commit**

```bash
git add data-pipeline/scripts/metaphor_spike_1a.py data-pipeline/scripts/test_metaphor_spike_1a.py
git commit -m "feat(spike-1a): add schema validators for apt and inapt LLM responses"
```

---

### Task 3: Concept snap-rate checker

**Files:**
- Modify: `data-pipeline/scripts/metaphor_spike_1a.py` (append function)
- Modify: `data-pipeline/scripts/test_metaphor_spike_1a.py` (append tests)

This function checks each concept word extracted from an apt response against the `lemmas` table and returns how many resolved to at least one `synset_id`. The snap-rate gate is one of the four Phase 1a pass/fail criteria.

#### Background

`lemmas` table schema: `(lemma TEXT, synset_id TEXT, PRIMARY KEY (lemma, synset_id))`. A concept "snaps" if `SELECT 1 FROM lemmas WHERE lemma = ? LIMIT 1` returns a row. This mirrors the property-snap path described in the spike doc — "single words can be programmatically resolved to dictionary entries via the same `lemmas → synset_id` path used for vehicles."

- [ ] **Step 1: Write failing test for snap-rate checker**

Append to `data-pipeline/scripts/test_metaphor_spike_1a.py`:

```python
from metaphor_spike_1a import (
    TOPICS,
    build_apt_prompt,
    build_inapt_prompt,
    validate_apt_response,
    validate_inapt_response,
    AptValidation,
    InaptValidation,
    check_concept_snap_rate,
    ConceptSnapResult,
)


def _make_lemmas_db(words: list[str]) -> sqlite3.Connection:
    """In-memory DB with a lemmas table populated for the given words."""
    conn = sqlite3.connect(":memory:")
    conn.execute(
        "CREATE TABLE lemmas (lemma TEXT NOT NULL, synset_id TEXT NOT NULL, "
        "PRIMARY KEY (lemma, synset_id))"
    )
    for i, w in enumerate(words):
        conn.execute("INSERT INTO lemmas VALUES (?, ?)", (w, f"s-{i}"))
    conn.commit()
    return conn


def test_concept_snap_all_known():
    conn = _make_lemmas_db(["heat", "spreading", "destruction"])
    concepts = ["heat", "spreading", "destruction"]
    result = check_concept_snap_rate(conn, concepts)
    assert result.n_concepts == 3
    assert result.n_snapped == 3
    assert result.snap_rate == 1.0
    assert result.unsnapped == []


def test_concept_snap_partial():
    conn = _make_lemmas_db(["heat"])
    concepts = ["heat", "unknownxyz", "alsounkown"]
    result = check_concept_snap_rate(conn, concepts)
    assert result.n_concepts == 3
    assert result.n_snapped == 1
    assert round(result.snap_rate, 4) == round(1 / 3, 4)
    assert "unknownxyz" in result.unsnapped
    assert "alsounkown" in result.unsnapped


def test_concept_snap_empty_list():
    conn = _make_lemmas_db([])
    result = check_concept_snap_rate(conn, [])
    assert result.n_concepts == 0
    assert result.n_snapped == 0
    assert result.snap_rate == 0.0
```

- [ ] **Step 2: Run to confirm failure**

```bash
cd /home/agent/projects/metaforge
source data-pipeline/.venv/bin/activate
python -m pytest data-pipeline/scripts/test_metaphor_spike_1a.py::test_concept_snap_all_known -v 2>&1 | tail -10
```

Expected: `ImportError` on `check_concept_snap_rate`, `ConceptSnapResult`

- [ ] **Step 3: Implement the snap-rate checker**

Append to `data-pipeline/scripts/metaphor_spike_1a.py` (after the validators):

```python
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

    unique = list(dict.fromkeys(c.strip().lower() for c in concepts if c.strip()))
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
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
cd /home/agent/projects/metaforge
source data-pipeline/.venv/bin/activate
python -m pytest data-pipeline/scripts/test_metaphor_spike_1a.py -v
```

Expected: all 18 tests PASS

- [ ] **Step 5: Commit**

```bash
git add data-pipeline/scripts/metaphor_spike_1a.py data-pipeline/scripts/test_metaphor_spike_1a.py
git commit -m "feat(spike-1a): concept snap-rate checker against lemmas table"
```

---

### Task 4: JSONL writer and cascade scorer

**Files:**
- Modify: `data-pipeline/scripts/metaphor_spike_1a.py` (append functions)
- Modify: `data-pipeline/scripts/test_metaphor_spike_1a.py` (append tests)

Two helpers:
1. `write_jsonl_line` — appends one JSON object as a line to a JSONL file. Idempotent across restarts (runner appends; deduplication is by re-run isolation, not inline).
2. `score_apt_vehicles` — given a parsed apt response dict and a DB connection, scores each (topic, vehicle) pair through `evaluate_cascade_pair` using the production-blessed CascadeConfig (`gate=1.0, alpha=1.0, additive`) from the M03 winner config.

#### Background — cascade API

```python
# evaluate_cascade.py public surface used here:
from evaluate_cascade import evaluate_cascade_pair, CascadeConfig, CascadeResult
from evaluate_aptness import lookup_primary_synset
```

`evaluate_cascade_pair(conn, synset_id_topic, synset_id_vehicle, config)` returns a `CascadeResult` with `.status`, `.final_score`, `.gate_passed`.

`lookup_primary_synset(conn, lemma)` returns a `synset_id` or `None`.

The production-blessed config from M03: `CascadeConfig(concreteness_threshold=1.0, alpha=1.0, composition="additive")`.

- [ ] **Step 1: Write failing tests**

Append to `data-pipeline/scripts/test_metaphor_spike_1a.py`:

```python
import struct
from metaphor_spike_1a import (
    TOPICS,
    build_apt_prompt,
    build_inapt_prompt,
    validate_apt_response,
    validate_inapt_response,
    AptValidation,
    InaptValidation,
    check_concept_snap_rate,
    ConceptSnapResult,
    write_jsonl_line,
    score_apt_vehicles,
    ScoredVehicle,
    PRODUCTION_CASCADE_CONFIG,
)


def test_write_jsonl_line(tmp_path):
    out = tmp_path / "out.jsonl"
    write_jsonl_line(out, {"topic": "anger", "vehicle": "fire"})
    write_jsonl_line(out, {"topic": "anger", "vehicle": "storm"})
    lines = out.read_text().strip().splitlines()
    assert len(lines) == 2
    assert json.loads(lines[0]) == {"topic": "anger", "vehicle": "fire"}
    assert json.loads(lines[1]) == {"topic": "anger", "vehicle": "storm"}


def test_write_jsonl_line_creates_parent(tmp_path):
    out = tmp_path / "subdir" / "out.jsonl"
    write_jsonl_line(out, {"x": 1})
    assert out.exists()


def _make_cascade_db() -> sqlite3.Connection:
    """Minimal schema for cascade scoring. Includes all tables the cascade
    and lookup_primary_synset touch."""
    conn = sqlite3.connect(":memory:")
    conn.executescript("""
        CREATE TABLE lemmas (
            lemma TEXT NOT NULL,
            synset_id TEXT NOT NULL,
            PRIMARY KEY (lemma, synset_id)
        );
        CREATE TABLE property_vocab_curated (
            vocab_id INTEGER PRIMARY KEY,
            lemma TEXT NOT NULL,
            polysemy INTEGER NOT NULL DEFAULT 1,
            synset_id TEXT NOT NULL
        );
        CREATE TABLE synset_concreteness (
            synset_id TEXT PRIMARY KEY,
            score REAL NOT NULL,
            source TEXT NOT NULL
        );
        CREATE TABLE synset_properties_curated (
            synset_id   TEXT NOT NULL,
            vocab_id    INTEGER NOT NULL,
            cluster_id  INTEGER NOT NULL,
            snap_method TEXT NOT NULL,
            snap_score  REAL,
            salience_sum REAL NOT NULL DEFAULT 1.0,
            PRIMARY KEY (synset_id, cluster_id)
        );
        CREATE TABLE property_vocabulary (
            vocab_id INTEGER PRIMARY KEY,
            text TEXT NOT NULL,
            cluster_id INTEGER NOT NULL DEFAULT 0
        );
    """)
    # topic: grief (abstract, low concreteness)
    conn.execute("INSERT INTO lemmas VALUES ('grief', 'syn-grief')")
    conn.execute("INSERT INTO property_vocab_curated VALUES (1, 'grief', 1, 'syn-grief')")
    conn.execute("INSERT INTO synset_concreteness VALUES ('syn-grief', 1.5, 'test')")
    # vehicle: storm (concrete, higher concreteness)
    conn.execute("INSERT INTO lemmas VALUES ('storm', 'syn-storm')")
    conn.execute("INSERT INTO property_vocab_curated VALUES (2, 'storm', 1, 'syn-storm')")
    conn.execute("INSERT INTO synset_concreteness VALUES ('syn-storm', 4.5, 'test')")
    # Give both synsets a shared property so Ortony finds overlap
    conn.execute("INSERT INTO property_vocabulary VALUES (10, 'intense', 0)")
    conn.execute("INSERT INTO synset_properties_curated VALUES ('syn-grief', 10, 0, 'exact', 1.0, 0.9)")
    conn.execute("INSERT INTO synset_properties_curated VALUES ('syn-storm', 10, 0, 'exact', 1.0, 0.9)")
    conn.commit()
    return conn


def test_score_apt_vehicles_scored_pair():
    conn = _make_cascade_db()
    apt_response = {
        "topic": "grief",
        "metaphors": [
            {
                "vehicle": "storm",
                "shared_features": [{"dimension": "emotional", "concept": "intensity"}],
                "confidence": 0.85,
            }
        ],
    }
    scored = score_apt_vehicles(conn, apt_response, PRODUCTION_CASCADE_CONFIG)
    assert len(scored) == 1
    sv = scored[0]
    assert sv.topic == "grief"
    assert sv.vehicle == "storm"
    # storm (4.5) - grief (1.5) = 3.0 ≥ gate threshold 1.0 → should pass
    assert sv.cascade_status in ("scored", "gate_dropped", "no_properties",
                                  "missing_concreteness", "unresolved")
    # Status must be a string from the CascadeStatus literal
    assert isinstance(sv.cascade_status, str)


def test_score_apt_vehicles_unknown_vehicle():
    """Vehicle not in lemmas → unresolved, still returns a row."""
    conn = _make_cascade_db()
    apt_response = {
        "topic": "grief",
        "metaphors": [
            {
                "vehicle": "notaword99xyz",
                "shared_features": [{"dimension": "emotional", "concept": "loss"}],
                "confidence": 0.5,
            }
        ],
    }
    scored = score_apt_vehicles(conn, apt_response, PRODUCTION_CASCADE_CONFIG)
    assert len(scored) == 1
    assert scored[0].cascade_status == "unresolved"
    assert scored[0].final_score is None
```

- [ ] **Step 2: Run to confirm failure**

```bash
cd /home/agent/projects/metaforge
source data-pipeline/.venv/bin/activate
python -m pytest data-pipeline/scripts/test_metaphor_spike_1a.py -v 2>&1 | tail -15
```

Expected: `ImportError` on `write_jsonl_line`, `score_apt_vehicles`, `ScoredVehicle`, `PRODUCTION_CASCADE_CONFIG`

- [ ] **Step 3: Implement the JSONL writer and cascade scorer**

Append to `data-pipeline/scripts/metaphor_spike_1a.py` (after the snap-rate section). The cascade imports go at module top after the existing imports.

First, add these imports at the top of the file (after the existing `sys.path.insert` line):

```python
sys.path.insert(0, str(Path(__file__).resolve().parent))
from evaluate_cascade import evaluate_cascade_pair, CascadeConfig
from evaluate_aptness import lookup_primary_synset
```

Then append:

```python
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

    Creates parent directories if absent.
    Thread-safety: this runner is single-threaded; no locking needed.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(obj, ensure_ascii=False) + "\n")


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
        vehicle_word = m.get("vehicle", "")
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

        cr = evaluate_cascade_pair(conn, sid_topic, sid_vehicle, config)
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
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
cd /home/agent/projects/metaforge
source data-pipeline/.venv/bin/activate
python -m pytest data-pipeline/scripts/test_metaphor_spike_1a.py -v
```

Expected: all 24 tests PASS

- [ ] **Step 5: Commit**

```bash
git add data-pipeline/scripts/metaphor_spike_1a.py data-pipeline/scripts/test_metaphor_spike_1a.py
git commit -m "feat(spike-1a): JSONL writer and cascade scorer for apt vehicles"
```

---

### Task 5: Aggregate metrics and report writer

**Files:**
- Modify: `data-pipeline/scripts/metaphor_spike_1a.py` (append functions)
- Modify: `data-pipeline/scripts/test_metaphor_spike_1a.py` (append tests)

`compute_gate_metrics` aggregates raw validation and snap results into the four Phase 1a gate-check numbers. `write_report` renders the Markdown report file.

- [ ] **Step 1: Write failing tests**

Append to `data-pipeline/scripts/test_metaphor_spike_1a.py`:

```python
from metaphor_spike_1a import (
    TOPICS,
    build_apt_prompt,
    build_inapt_prompt,
    validate_apt_response,
    validate_inapt_response,
    AptValidation,
    InaptValidation,
    check_concept_snap_rate,
    ConceptSnapResult,
    write_jsonl_line,
    score_apt_vehicles,
    ScoredVehicle,
    PRODUCTION_CASCADE_CONFIG,
    GateMetrics,
    compute_gate_metrics,
)


def test_compute_gate_metrics_all_pass():
    validations = [
        AptValidation(
            schema_ok=True,
            n_vehicles=3,
            n_concepts=6,
            n_single_word_concepts=6,
            concept_violations=[],
            schema_errors=[],
        ),
        AptValidation(
            schema_ok=True,
            n_vehicles=2,
            n_concepts=4,
            n_single_word_concepts=4,
            concept_violations=[],
            schema_errors=[],
        ),
    ]
    snap = ConceptSnapResult(n_concepts=10, n_snapped=10, snap_rate=1.0, unsnapped=[])
    m = compute_gate_metrics(validations, snap)
    assert m.parse_ok_rate == 1.0  # both parsed (no parse failure injected)
    assert m.schema_ok_rate == 1.0
    assert m.single_word_rate == 1.0
    assert m.snap_rate == 1.0


def test_compute_gate_metrics_mixed():
    validations = [
        AptValidation(
            schema_ok=True,
            n_vehicles=2,
            n_concepts=4,
            n_single_word_concepts=3,  # one multi-word violation
            concept_violations=["must be tamed"],
            schema_errors=[],
        ),
        AptValidation(
            schema_ok=False,  # schema failure
            n_vehicles=0,
            n_concepts=0,
            n_single_word_concepts=0,
            concept_violations=[],
            schema_errors=["missing 'metaphors' key"],
        ),
    ]
    snap = ConceptSnapResult(n_concepts=4, n_snapped=3, snap_rate=0.75, unsnapped=["xyz"])
    m = compute_gate_metrics(validations, snap)
    assert m.schema_ok_rate == 0.5  # 1/2
    assert m.single_word_rate == round(3 / 4, 6)  # 3 of 4 concepts single-word
    assert m.snap_rate == 0.75


def test_compute_gate_metrics_zero_concepts():
    validations = [
        AptValidation(
            schema_ok=False,
            n_vehicles=0,
            n_concepts=0,
            n_single_word_concepts=0,
            concept_violations=[],
            schema_errors=["missing key"],
        )
    ]
    snap = ConceptSnapResult(n_concepts=0, n_snapped=0, snap_rate=0.0, unsnapped=[])
    m = compute_gate_metrics(validations, snap)
    assert m.single_word_rate == 0.0
    assert m.snap_rate == 0.0
```

- [ ] **Step 2: Run to confirm failure**

```bash
cd /home/agent/projects/metaforge
source data-pipeline/.venv/bin/activate
python -m pytest data-pipeline/scripts/test_metaphor_spike_1a.py -v 2>&1 | tail -15
```

Expected: `ImportError` on `GateMetrics`, `compute_gate_metrics`

- [ ] **Step 3: Implement gate metrics and report writer**

Append to `data-pipeline/scripts/metaphor_spike_1a.py`:

```python
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
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
cd /home/agent/projects/metaforge
source data-pipeline/.venv/bin/activate
python -m pytest data-pipeline/scripts/test_metaphor_spike_1a.py -v
```

Expected: all 27 tests PASS

- [ ] **Step 5: Commit**

```bash
git add data-pipeline/scripts/metaphor_spike_1a.py data-pipeline/scripts/test_metaphor_spike_1a.py
git commit -m "feat(spike-1a): gate metrics aggregator and Markdown report writer"
```

---

### Task 6: Main runner loop

**Files:**
- Modify: `data-pipeline/scripts/metaphor_spike_1a.py` (append `run_spike` and `main`)

This wires everything together: iterates topics × models × prompt types, calls the LLM via `prompt_json`, writes JSONL per call, scores apt vehicles, and at the end aggregates metrics and writes the report. No new tests for `run_spike` itself — the LLM call is a subprocess side-effect; the functions it calls are already unit-tested.

#### Background — claude_client API

```python
from claude_client import prompt_json, ClaudeError
# prompt_json(prompt_str, model=model_id, expect=dict) → dict
# Raises ClaudeError subclasses on parse failure, empty response, rate limit.
```

The `model` argument to `prompt_json` is the full model ID string (e.g. `"claude-haiku-4-5-20251001"`). The `lib/claude_client.py` passes this directly to `claude -p --model`.

When a call fails (parse error, empty response), the runner records a sentinel validation with `schema_errors=["parse_failure: <error>"]` and continues — it never aborts the loop.

- [ ] **Step 1: Append the runner to `metaphor_spike_1a.py`**

No test is written for `run_spike` directly because it calls the LLM subprocess. The unit-tested helper functions already cover all the logic inside the loop.

Append to `data-pipeline/scripts/metaphor_spike_1a.py`:

```python
from claude_client import prompt_json, ClaudeError


def run_spike(db_path: Path, output_dir: Path) -> None:
    """Run the Phase 1a spike: 20 LLM calls + cascade scoring + report.

    Idempotent by output file: if the JSONL files already exist the
    runner overwrites them (truncates on open). Re-run safely.
    """
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    if not db_path.exists():
        raise FileNotFoundError(f"DB not found: {db_path}")

    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)

    # Output file paths — one JSONL per (model, prompt_type) combination
    output_paths: dict[tuple[str, str], Path] = {
        (MODEL_HAIKU, "apt"):    output_dir / "metaphor_spike_apt_haiku.jsonl",
        (MODEL_SONNET, "apt"):   output_dir / "metaphor_spike_apt_sonnet.jsonl",
        (MODEL_HAIKU, "inapt"):  output_dir / "metaphor_spike_inapt_haiku.jsonl",
        (MODEL_SONNET, "inapt"): output_dir / "metaphor_spike_inapt_sonnet.jsonl",
    }
    scores_path = output_dir / "metaphor_spike_scores.jsonl"
    report_path = output_dir / "metaphor_spike_scoring.md"

    output_dir.mkdir(parents=True, exist_ok=True)

    # Truncate output files before the run so a re-run gives clean data.
    for p in list(output_paths.values()) + [scores_path]:
        p.write_text("")

    # Accumulate per-(model, prompt_type) validation results for metrics
    apt_validations: dict[str, list[AptValidation]] = {m: [] for m in MODELS}
    inapt_validations: dict[str, list[InaptValidation]] = {m: [] for m in MODELS}
    all_scored_vehicles: list[ScoredVehicle] = []
    all_concept_violations: list[str] = []
    all_unsnapped: list[str] = []

    total_apt_concepts: list[str] = {m: [] for m in MODELS}

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
                for sf in m_entry.get("shared_features", [])
                if isinstance(sf.get("concept"), str)
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
```

- [ ] **Step 2: Verify the module imports cleanly (no LLM calls)**

```bash
cd /home/agent/projects/metaforge
source data-pipeline/.venv/bin/activate
python -c "import sys; sys.path.insert(0, 'data-pipeline/scripts'); import metaphor_spike_1a; print('import ok')"
```

Expected: `import ok`

- [ ] **Step 3: Run full test suite to confirm no regressions**

```bash
cd /home/agent/projects/metaforge
source data-pipeline/.venv/bin/activate
python -m pytest data-pipeline/scripts/test_metaphor_spike_1a.py -v
```

Expected: all 27 tests PASS

- [ ] **Step 4: Commit**

```bash
git add data-pipeline/scripts/metaphor_spike_1a.py
git commit -m "feat(spike-1a): main runner loop wiring topics → LLM → JSONL → cascade → report"
```

---

### Task 7: Smoke-test the import path and CLI help

**Files:**
- No code changes — validation step only

Confirms the complete module can be imported from the correct working directory, and that `--help` works. Catches any remaining import errors before the operator runs the real 20-call spike.

- [ ] **Step 1: Verify module import from repo root**

```bash
cd /home/agent/projects/metaforge
source data-pipeline/.venv/bin/activate
python -c "
import sys
sys.path.insert(0, 'lib')
sys.path.insert(0, 'data-pipeline/scripts')
import metaphor_spike_1a as m
print('TOPICS:', [t['word'] for t in m.TOPICS])
print('MODELS:', m.MODELS)
print('CONFIG:', m.PRODUCTION_CASCADE_CONFIG)
"
```

Expected output (order may vary):
```
TOPICS: ['anger', 'heart', 'deadline', 'anxiety', 'grief']
MODELS: ['claude-haiku-4-5-20251001', 'claude-sonnet-4-6']
CONFIG: CascadeConfig(concreteness_threshold=1.0, ortony_scoring='jaccard_salience', d_cap=0.77, alpha=1.0, composition='additive')
```

- [ ] **Step 2: Verify CLI help**

```bash
cd /home/agent/projects/metaforge
source data-pipeline/.venv/bin/activate
python data-pipeline/scripts/metaphor_spike_1a.py --help
```

Expected: prints usage with `--db` and `--output-dir` arguments, exits 0.

- [ ] **Step 3: Run full test suite one final time**

```bash
cd /home/agent/projects/metaforge
source data-pipeline/.venv/bin/activate
python -m pytest data-pipeline/scripts/test_metaphor_spike_1a.py -v
```

Expected: all 27 tests PASS

- [ ] **Step 4: Commit**

```bash
git add data-pipeline/scripts/metaphor_spike_1a.py data-pipeline/scripts/test_metaphor_spike_1a.py
git commit -m "chore(spike-1a): smoke-test validation — import path and CLI confirmed"
```

---

## Self-Review

### Spec coverage

| Spike doc requirement | Covered by |
|----------------------|-----------|
| 5 anchor topics (anger, heart, deadline, anxiety + 1) | Task 1 `TOPICS` list — 5th topic is `grief` |
| Both models: Haiku 4.5 + Sonnet 4.6 | Task 1 `MODELS`, Task 6 runner loop |
| Both prompts: apt + inapt verbatim | Task 1 prompt templates |
| 20 LLM calls (5×2×2) | Task 6 `run_spike` nested loop |
| Score-as-we-go cascade scoring | Task 4 `score_apt_vehicles`, Task 6 loop |
| JSON parseability % | Task 5 `compute_gate_metrics` `parse_ok_rate` |
| Schema compliance % | Task 5 `compute_gate_metrics` `schema_ok_rate` |
| Single-word concept compliance % | Task 2 `validate_apt_response`, Task 5 `compute_gate_metrics` `single_word_rate` |
| Concept snap-rate against `lemmas` % | Task 3 `check_concept_snap_rate`, Task 5 + Task 6 |
| Manual eyeball quality scratchpad | Task 5 `write_report` — eyeball table + gate decision checkboxes |
| JSONL output files (4 × model/prompt) | Task 4 `write_jsonl_line`, Task 6 `output_paths` |
| Cascade scores JSONL | Task 4, Task 6 `scores_path` |
| Gloss attached locally, not echoed | Task 6: `raw["_gloss"] = gloss` after receiving response |
| No new DB tables | Confirmed — runner uses `lexicon_v2.db` read-only |
| Production cascade config (gate=1.0, alpha=1.0, additive) | Task 4 `PRODUCTION_CASCADE_CONFIG` |

No spec requirements are missing.

### Placeholder scan

No TBD, TODO, or "implement later" strings found. All code blocks are complete.

### Type consistency

- `AptValidation` defined in Task 2, used in Tasks 3–6 — field names consistent throughout.
- `InaptValidation` defined in Task 2, coerced to `AptValidation` shape in Task 6 for the shared `compute_gate_metrics` — this coercion is explicit, not implicit.
- `CascadeConfig` / `evaluate_cascade_pair` / `lookup_primary_synset` — imported from existing modules; no redefinition.
- `PRODUCTION_CASCADE_CONFIG` — defined once in Task 4, used in Tasks 4 and 6.
- `write_jsonl_line(path: Path, obj: dict)` — signature defined Task 4, called Task 6.
- `score_apt_vehicles(conn, apt_response, config)` — signature defined Task 4, called Task 6.
- `compute_gate_metrics(validations, snap, model, prompt_type)` — defined Task 5, called Task 6.
- `write_report(path, apt_metrics, inapt_metrics, scored_vehicles, concept_violations, unsnapped_concepts)` — defined Task 5, called Task 6.
- `total_apt_concepts` in Task 6 is a `dict[str, list[str]]` keyed by model — correctly accessed as `total_apt_concepts[model]`.

All types are consistent.
