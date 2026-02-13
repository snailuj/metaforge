"""Exploration prompts and exploitation tweak generator for evolutionary prompt optimisation.

Each prompt is a radically different approach to extracting sensory/behavioural
properties from WordNet synsets. All share the controlled variable: 10-15
properties per sense, JSON output format, and {batch_items} placeholder.
"""
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "lib"))
from claude_client import prompt_text, prompt_json, ClaudeError, ParseError

# --- Exploration prompts ------------------------------------------------------

EXPLORATION_PROMPTS: dict[str, str] = {
    "persona_poet": """You are a poet cataloguing the sensory and experiential qualities of concepts.

For each word sense below, extract 10-15 properties that capture its experiential essence. Focus on:
- Sensory qualities: how it looks, sounds, feels, smells, tastes, moves
- Behavioural qualities: what it does, how it acts, how it affects
- Emotional or metaphorical associations: the feeling or experience it evokes

Think like a poet: prioritise vivid, evocative, concrete descriptors over abstract categories or definitions.

CRITICAL CONSTRAINTS:
1. Each property MUST be 1-2 words maximum. No exceptions.
2. Use terse, active forms: "flickering" not "has a flickering quality", "bitter" not "slightly bitter taste"
3. The definition specifies WHICH sense of the word to analyse. Focus ONLY on that sense.
4. Process each word sense independently using only the information provided.
5. Use present tense, active voice, minimal words.

{batch_items}

Output ONLY a valid JSON array with no markdown fences, no explanatory text, no preamble:
[{{"id": "...", "properties": [...]}}, ...]
""",

    "contrastive": """For each word sense below, extract 10-15 short, evocative properties that DISTINGUISH
this specific sense from other meanings of the same word and from similar concepts.

Focus on what makes this sense unique:
- What sensory properties does THIS sense have that other senses lack?
- What behavioural or functional qualities set it apart?
- What emotional or metaphorical associations are specific to this sense?

Go beyond simple definitions — capture the experiential essence that makes this sense distinctive.

CRITICAL CONSTRAINTS:
1. Every property MUST be 1-2 words maximum. No exceptions.
   - GOOD: "flickering", "bitter", "upward motion"
   - BAD: "has a flickering quality", "slightly bitter taste"
2. The definition specifies WHICH sense of the word to analyse. Focus ONLY on that sense.
3. Use present tense, active voice, concrete language.
4. Favour vivid, experiential descriptors over taxonomic labels.
5. Process each word sense independently using only the information provided.

{batch_items}

Output ONLY a valid JSON array with no markdown fences, no explanatory text, no preamble:
[{{"id": "...", "properties": [...]}}, ...]
""",

    "narrative": """You are an expert at extracting experiential properties from word senses. Your task is to generate vivid, evocative descriptors that capture the sensory, emotional, and behavioural essence of each concept.

For each word sense below, produce 10-15 descriptors that answer: What would you see, hear, feel, smell, taste, or emotionally experience? How does it move or behave? What does it evoke or remind you of?

CRITICAL CONSTRAINTS:

1. Every property MUST be 1-2 words maximum. Use terse, concrete descriptors:
   - GOOD: "flickering", "acrid", "smooth", "spiraling", "cold metal"
   - BAD: "has a flickering quality", "slightly bitter taste", "moves in circles"

2. Focus ONLY on the specific sense defined. The definition disambiguates which meaning to analyse. Ignore other senses of the word.

3. Prioritise experiential and sensory details. Capture how it feels, not just what category it belongs to. Favour evocative, metaphorical, and subjective descriptors over dry taxonomic labels.

4. Use present tense, active voice, minimal words. Prefer "hums" over "is humming", "jagged" over "has jagged edges".

5. Each word sense is independent. Do not rely on knowledge beyond the provided description.

{batch_items}

Output ONLY a valid JSON array with no markdown fences, no preamble, no explanation:
[{{"id": "...", "properties": [...]}}, ...]
""",

    "taxonomic": """You are a systematic sensory analyst extracting experiential and behavioural properties from word senses for computational similarity analysis.

For each word sense below, generate 10-15 short descriptors (1-2 words maximum) capturing how the sense is perceived, experienced, or behaves. Cover as many applicable dimensions as possible:

- Visual: colour, shape, size, brightness, texture, pattern
- Auditory: pitch, volume, timbre, rhythm, tone
- Tactile: temperature, weight, hardness, softness, moisture, texture
- Olfactory/Gustatory: scent, taste, flavour, pungency
- Kinetic: speed, direction, force, motion, pattern
- Temporal: duration, frequency, rhythm, regularity
- Affective: emotional tone, intensity, valence, mood
- Behavioural: actions, functions, typical interactions

CRITICAL CONSTRAINTS:

1. Every property must be 1-2 words maximum. Use terse descriptors:
   - "flickering" not "has a flickering quality"
   - "bitter" not "slightly bitter taste"
   - "upward" not "moves in an upward direction"

2. The definition specifies WHICH sense of the word to analyse. Focus ONLY on that sense. Ignore other meanings.

3. Favour vivid, concrete, experiential descriptors over abstract taxonomic labels. Evocative and metaphorical properties capture experiential essence.

4. Use present tense, active voice, minimal words. Each descriptor should stand alone.

5. Process each sense independently using only the provided definition.

{batch_items}

Output ONLY valid JSON (no markdown fences, no explanation, no preamble):
[{{"id": "...", "properties": [...]}}, ...]
""",

    "embodied": """You are extracting experiential and behavioural properties from word senses to enable computational similarity analysis. Each property must capture the sensory, emotional, or functional essence of the concept.

Task: For each word sense provided, generate 10-15 properties that describe how someone would experience this concept primarily through touch, smell, sound, weight, movement, and emotional resonance. Avoid visual-only descriptors. Focus on tactile, auditory, olfactory, kinaesthetic, and affective qualities.

Property requirements:
- Length: EVERY property must be 1-2 words maximum. This is non-negotiable.
- Format: Use present tense, active voice, minimal words
- Quality: Vivid, concrete, experiential descriptors
- GOOD: "flickering", "bitter", "rough", "metallic", "whispers", "cold", "dense", "sharp", "hollow", "pulsing"
- BAD: "has a flickering quality" (too long), "slightly bitter taste" (too long), "is cold" (unnecessary verb)

Sensory and behavioural focus:
- Tactile: texture, temperature, weight, pressure, resistance
- Auditory: sounds it makes, acoustic qualities, rhythm, pitch
- Olfactory: smells, scent associations
- Kinaesthetic: movement, motion, dynamic qualities
- Emotional/metaphorical: feelings evoked, affective associations
- Behavioural: actions, functions, typical interactions

Critical instructions:
1. Each input includes a definition specifying WHICH sense of the word to analyse. Focus EXCLUSIVELY on that sense.
2. Process each word sense independently. Do not rely on external knowledge.
3. Prioritise evocative and experiential properties over taxonomic labels.
4. Every property must be 1-2 words. No exceptions.

{batch_items}

Output ONLY a valid JSON array with no markdown fences, no explanatory text, no preamble:
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


def load_fixture_vocabulary(pairs_path: str) -> frozenset[str]:
    """Extract all unique source+target words from metaphor pairs JSON."""
    with open(pairs_path) as f:
        pairs = json.load(f)
    words = set()
    for pair in pairs:
        words.add(pair["source"])
        words.add(pair["target"])
    return frozenset(words)


def generate_tweak(
    current_prompt: str,
    per_pair: list[dict],
    mrr: float,
    model: str = "haiku",
    fixture_vocab: frozenset[str] = None,
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

    try:
        tweak = prompt_json(meta_prompt, model=model, expect=dict)
    except ParseError as e:
        raise ValueError(f"generate_tweak: {e}") from e

    if "modified_prompt" not in tweak:
        raise ValueError("Tweak response missing 'modified_prompt' key")
    if "{batch_items}" not in tweak["modified_prompt"]:
        raise ValueError("Tweaked prompt missing {batch_items} placeholder")

    # Fixture vocabulary guard: reject if new fixture words leaked in
    if fixture_vocab:
        current_words = set(current_prompt.lower().split())
        modified_words = set(tweak["modified_prompt"].lower().split())
        new_words = modified_words - current_words
        leaked = {w for w in fixture_vocab if w.lower() in new_words}
        if leaked:
            raise ValueError(
                f"Tweaked prompt contains fixture vocabulary: {leaked}"
            )

    return {
        "modified_prompt": tweak["modified_prompt"],
        "description": tweak.get("description", "no description"),
    }


# --- Second-stage prompt improver --------------------------------------------

_IMPROVER_META_PROMPT = """As a prompt engineering expert, your task is to refine the following prompt that guides an LLM in extracting sensory and behavioural properties from word senses. The goal is to obtain short, evocative descriptors suitable for computational similarity analysis between concepts.

The refined prompt must preserve the original prompt's distinctive angle or persona — if it adopts a poet's voice, a contrastive lens, or a non-visual constraint, that framing is intentional and must be retained. Your job is to sharpen clarity and structure, not to flatten the approach.

**What we mean by properties:**

"Experiential properties" are those relating to sensory modalities (e.g., visual, auditory, tactile, olfactory, gustatory) and emotional or metaphorical associations. "Behavioural properties" are actions, functions, or typical interactions associated with the word sense. The prompt should emphasise the importance of including subjective and evocative properties, going beyond simple definitions to capture the feeling or experience associated with the word sense.

**Guidelines for the refined prompt:**

1. **Output format**: The prompt must instruct the LLM to return a JSON array where each element has an "id" (matching the input) and a "properties" list of 10-15 short descriptors. No markdown fences, no explanatory text, no preamble — JSON only.

2. **Property length**: The prompt MUST explicitly instruct that every property must be 1-2 words maximum. This is a hard constraint — multi-word expressions degrade downstream analysis. The prompt should reinforce this with examples showing terse descriptors (e.g., "flickering" not "has a flickering quality", "bitter" not "slightly bitter taste").

3. **Property quality**: Descriptors should be vivid, concrete, and experiential. Sensory properties (how something looks, sounds, feels, smells, tastes, moves) and behavioural properties (how it acts, what it does, how it affects) are both valuable. Evocative and metaphorical descriptors are encouraged — they capture experiential essence better than dry taxonomic labels.

4. **Sense disambiguation**: The prompt must clearly instruct the LLM that each input includes a definition specifying WHICH sense of the word to analyse, and to focus exclusively on that sense.

5. **Independence**: Each word sense should be processed independently. The LLM must not rely on external knowledge beyond what is present in the word sense descriptions.

6. **Conciseness**: Descriptors should use present tense, active voice, and minimal words. Favour "flickering" over "has a flickering quality".

The prompt MUST contain the literal placeholder {{batch_items}} (with curly braces) — this is where word senses are inserted at runtime. Do not remove, rename, or reformat this placeholder.

Here is the prompt to refine:
---
{raw_prompt}
---

Return ONLY the refined prompt text. No explanation, no markdown fences, no preamble."""


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
    text = prompt_text(meta, model=model)

    if "{batch_items}" not in text:
        raise ValueError("Improved prompt missing {batch_items} placeholder")

    return text
