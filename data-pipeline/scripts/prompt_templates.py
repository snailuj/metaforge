"""Exploration prompts and exploitation tweak generator for evolutionary prompt optimisation.

Each prompt is a radically different approach to extracting sensory/behavioural
properties from WordNet synsets. All share the controlled variable: 10-15
properties per sense, JSON output format, and {batch_items} placeholder.
"""
import json
import re

from enrich_properties import invoke_claude

# --- Exploration prompts ------------------------------------------------------

EXPLORATION_PROMPTS: dict[str, str] = {
    "persona_poet": """You are a poet cataloguing the sensory qualities of every concept you encounter.
For each word sense below, write 10-15 short (1-2 word) properties that capture its
experiential essence — how it feels, sounds, looks, moves, or affects the body.

Think like a poet: prioritise vivid, evocative, sensory language over abstract categories.

CRITICAL: The definition tells you WHICH sense of the word to analyse. Focus ONLY on that sense.

{batch_items}

Output ONLY a valid JSON array (no markdown, no explanation):
[{{"id": "...", "properties": [...]}}, ...]
""",

    "contrastive": """For each word sense below, list 10-15 short (1-2 word) properties that DISTINGUISH
this specific sense from other meanings of the same word and from similar concepts.

Focus on what makes this sense unique:
- What properties does THIS sense have that other senses lack?
- What sensory or behavioural qualities set it apart?

CRITICAL: The definition tells you WHICH sense of the word to analyse. Focus ONLY on that sense.

{batch_items}

Output ONLY a valid JSON array (no markdown, no explanation):
[{{"id": "...", "properties": [...]}}, ...]
""",

    "narrative": """Imagine encountering each concept below in real life. Describe your experience
using 10-15 single words or short (1-2 word) phrases.

What would you see, hear, feel, smell, or taste? How would it move? What would
it remind you of? Capture the lived, embodied experience.

CRITICAL: The definition tells you WHICH sense of the word to analyse. Focus ONLY on that sense.

{batch_items}

Output ONLY a valid JSON array (no markdown, no explanation):
[{{"id": "...", "properties": [...]}}, ...]
""",

    "taxonomic": """Systematically classify each word sense below along every perceptible dimension.
For each sense, provide 10-15 short (1-2 word) properties covering as many of
these dimensions as apply:

- Visual (colour, shape, size, luminosity, texture)
- Auditory (pitch, volume, timbre, rhythm)
- Tactile (temperature, weight, hardness, moisture)
- Olfactory/Gustatory (scent, taste, pungency)
- Kinetic (speed, direction, force, pattern)
- Temporal (duration, frequency, regularity)
- Affective (emotional tone, intensity, valence)

CRITICAL: The definition tells you WHICH sense of the word to analyse. Focus ONLY on that sense.

{batch_items}

Output ONLY a valid JSON array (no markdown, no explanation):
[{{"id": "...", "properties": [...]}}, ...]
""",

    "embodied": """Describe each word sense below to someone who experiences the world primarily
through touch, smell, and sound (not sight). Use 10-15 short (1-2 word) properties
that convey how each concept feels physically, sounds, smells, weighs, or moves.

Avoid visual-only properties. Prioritise tactile, auditory, olfactory, and
kinaesthetic qualities.

CRITICAL: The definition tells you WHICH sense of the word to analyse. Focus ONLY on that sense.

{batch_items}

Output ONLY a valid JSON array (no markdown, no explanation):
[{{"id": "...", "properties": [...]}}, ...]
""",
}


# --- Exploitation tweak generator --------------------------------------------

_TWEAK_META_PROMPT = """You are an expert prompt engineer optimising a prompt that extracts sensory/behavioural properties from word senses.

The current prompt achieves MRR = {mrr:.4f}.

Performance summary:
- {hit_count}/{total_count} pairs found in suggestions
- {strong_count} with reciprocal rank > 0.5
- {weak_count} not found at all
- Strong-tier hit rate: {strong_rate:.0%}
- Medium-tier hit rate: {medium_rate:.0%}

The current prompt is:
---
{current_prompt}
---

Propose ONE specific, targeted modification to the prompt that could improve results on the weak pairs without hurting the strong pairs. The modification should be a concrete change (add/remove/rephrase a specific section).

IMPORTANT: The modified prompt MUST contain the literal text {{batch_items}} (with curly braces) as a placeholder — this is where word senses get inserted at runtime.

Return ONLY a JSON object (no markdown, no explanation):
{{"modified_prompt": "...", "description": "one-line summary of what you changed and why"}}
"""


def generate_tweak(
    current_prompt: str,
    per_pair: list[dict],
    mrr: float,
    model: str = "haiku",
) -> dict:
    """Generate a targeted prompt tweak using an LLM.

    Returns dict with 'modified_prompt' and 'description' keys.
    Raises ValueError if the LLM response is unparseable or invalid.
    """
    total_count = len(per_pair)
    hit_count = sum(1 for p in per_pair if p.get("reciprocal_rank", 0) > 0)
    strong_count = sum(1 for p in per_pair if p.get("reciprocal_rank", 0) > 0.5)
    weak_count = sum(1 for p in per_pair if p.get("reciprocal_rank", 0) == 0)

    # Tier-level hit rates
    strong_tier = [p for p in per_pair if p.get("tier") == "strong"]
    medium_tier = [p for p in per_pair if p.get("tier") == "medium"]
    strong_rate = (
        sum(1 for p in strong_tier if p.get("reciprocal_rank", 0) > 0) / len(strong_tier)
        if strong_tier else 0.0
    )
    medium_rate = (
        sum(1 for p in medium_tier if p.get("reciprocal_rank", 0) > 0) / len(medium_tier)
        if medium_tier else 0.0
    )

    meta_prompt = _TWEAK_META_PROMPT.format(
        mrr=mrr,
        hit_count=hit_count,
        total_count=total_count,
        strong_count=strong_count,
        weak_count=weak_count,
        strong_rate=strong_rate,
        medium_rate=medium_rate,
        current_prompt=current_prompt,
    )

    proc = invoke_claude(meta_prompt, model=model)

    # Parse the LLM response
    events = json.loads(proc.stdout)
    result_event = next(
        (e for e in reversed(events) if e.get("type") == "result"), None
    )
    if result_event is None or result_event.get("is_error"):
        raise ValueError("Failed to generate tweak: no valid result from LLM")

    text = result_event["result"].strip()
    text = re.sub(r'^```json\s*', '', text)
    text = re.sub(r'\s*```$', '', text)

    try:
        tweak = json.loads(text)
    except json.JSONDecodeError as e:
        raise ValueError(f"Failed to parse tweak response as JSON: {e}") from e

    if "modified_prompt" not in tweak:
        raise ValueError("Tweak response missing 'modified_prompt' key")
    if "{batch_items}" not in tweak["modified_prompt"]:
        raise ValueError("Tweaked prompt missing {batch_items} placeholder")

    return {
        "modified_prompt": tweak["modified_prompt"],
        "description": tweak.get("description", "no description"),
    }


# --- Second-stage prompt improver --------------------------------------------

_IMPROVER_META_PROMPT = """You are a prompt engineering expert. Your task is to improve the quality of the following prompt that extracts sensory/behavioural properties from word senses.

Apply prompt engineering best practices:
- Ensure clear, unambiguous instructions
- Structure for optimal LLM comprehension
- Remove redundancy or contradictions
- Improve instruction ordering and flow
- Do NOT add example words or specific domain content
- Do NOT add concrete word examples (like "candle", "whisper", etc.)

CRITICAL: The improved prompt MUST contain the literal text {{batch_items}} (with curly braces) as a placeholder — this is where word senses get inserted at runtime. Do not remove or alter this placeholder.

Here is the prompt to improve:
---
{raw_prompt}
---

Return ONLY the improved prompt text. No explanation, no markdown fences, no preamble."""


def improve_prompt(
    raw_prompt: str,
    model: str = "sonnet",
) -> str:
    """Apply prompt engineering best practices to a raw exploitation tweak.

    Sends the prompt through a stronger model with instructions to improve
    clarity and structure without adding domain-specific content.
    Preserves the {batch_items} placeholder.

    Returns the improved prompt text.
    Raises ValueError if the improved prompt lacks {batch_items}.
    """
    meta = _IMPROVER_META_PROMPT.format(raw_prompt=raw_prompt)
    proc = invoke_claude(meta, model=model)

    events = json.loads(proc.stdout)
    result_event = next(
        (e for e in reversed(events) if e.get("type") == "result"), None
    )
    if result_event is None or result_event.get("is_error"):
        raise ValueError("Failed to improve prompt: no valid result from LLM")

    text = result_event["result"].strip()
    # Strip markdown fences if present
    text = re.sub(r'^```(?:markdown)?\s*', '', text)
    text = re.sub(r'\s*```$', '', text)

    if "{batch_items}" not in text:
        raise ValueError("Improved prompt missing {batch_items} placeholder")

    return text
