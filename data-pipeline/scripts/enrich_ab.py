"""A/B/C enrichment runner for prompt experiments.

Runs a prompt variant against a pre-curated benchmark set with:
- Tenacity retry on API failures
- Checkpointing for resume on crash
- Configurable property range and prompt

Variants:
    A = Original prompt, 5-10 properties
    B = Dual-dimension prompt, 10-15 properties
    C = Original prompt, 10-15 properties (isolates count effect)

Usage:
    python enrich_ab.py --variant A --synsets-file output/benchmark_500.json
    python enrich_ab.py --variant B --synsets-file output/benchmark_500.json
    python enrich_ab.py --variant C --synsets-file output/benchmark_500.json
    python enrich_ab.py --variant A --synsets-file output/benchmark_500.json --resume
"""
import argparse
import json
import os
import re
import time
from pathlib import Path
from collections import Counter
from typing import List, Dict

try:
    from google import genai
except ImportError:
    raise ImportError("Run: pip install google-genai")

from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from utils import OUTPUT_DIR

MODEL_NAME = "gemini-2.5-flash"

# --- Prompt variants --------------------------------------------------------

PROMPT_A = """You are extracting sensory and behavioural properties for specific word senses.

CRITICAL: The definition tells you WHICH sense of the word to analyse. Many words have multiple meanings — focus ONLY on the sense described in the definition.

Extract 5-10 properties per word that describe:
- Physical qualities (texture, weight, temperature, luminosity, sound)
- Behavioural qualities (speed, rhythm, intensity, duration)
- Perceptual qualities (how it's experienced by senses)
- Functional qualities (what it does, how it moves, what it enables)

Properties must be SHORT (1-2 words). Be creative — capture the experiential essence, not just dictionary categories.

Examples showing sense disambiguation:

Word: run
Definition: deal in illegally, such as arms or liquor
Properties: ["furtive", "risky", "profitable", "shadowy", "underground", "covert", "transactional"]
(NOT: fast, athletic, sweaty — those are the locomotion sense)

Word: chain
Definition: a series of things depending on each other as if linked together
Properties: ["sequential", "dependent", "cascading", "fragile", "interconnected", "cumulative"]
(NOT: heavy, metallic, cold — those are the physical chain sense)

Word: fleece
Definition: shear the wool from
Properties: ["cutting", "harvesting", "seasonal", "rhythmic", "skilled", "yielding", "stripping"]
(NOT: woolly, soft, warm — those describe the material, not the shearing action)

Word: candle
Definition: stick of wax with a wick; gives light when burning
Properties: ["warm", "flickering", "luminous", "fragile", "waxy", "ephemeral", "aromatic"]

Word: whisper
Definition: speak softly; in a low voice
Properties: ["quiet", "intimate", "secretive", "breathy", "gentle", "transient", "hushed"]

Now extract properties for each of these word senses:

{batch_items}

Output ONLY a valid JSON array (no markdown, no explanation):
[{{"id": "...", "properties": [...]}}, ...]
"""

PROMPT_B = """You are extracting rich, multi-dimensional properties for specific word senses.

CRITICAL: The definition tells you WHICH sense of the word to analyse. Many words have multiple meanings — focus ONLY on the sense described in the definition.

Extract 10-15 properties per word. You MUST cover BOTH dimensions:

SENSORY — how it's experienced by the senses:
- Physical qualities (texture, weight, temperature, luminosity, sound, smell)
- Perceptual qualities (what it looks/sounds/feels like)

STRUCTURAL/FUNCTIONAL — how it works and relates:
- Functional qualities (what it does, how it moves, what it enables)
- Relational qualities (how it connects, depends on, or affects other things)
- Behavioural qualities (speed, rhythm, intensity, duration, pattern)

Aim for roughly half sensory, half structural/functional. Properties must be SHORT (1-2 words). Be creative — capture the experiential AND mechanical essence.

Examples showing sense disambiguation and dual coverage:

Word: run
Definition: deal in illegally, such as arms or liquor
Properties: ["furtive", "shadowy", "hushed", "risky", "profitable", "underground", "covert", "transactional", "networked", "volatile", "adrenaline-charged", "clandestine"]
(NOT: fast, athletic, sweaty — those are the locomotion sense)

Word: chain
Definition: a series of things depending on each other as if linked together
Properties: ["sequential", "dependent", "cascading", "fragile", "interconnected", "cumulative", "linear", "tensioned", "propagating", "vulnerable", "ordered", "binding"]
(NOT: heavy, metallic, cold — those are the physical chain sense)

Word: candle
Definition: stick of wax with a wick; gives light when burning
Properties: ["warm", "flickering", "luminous", "fragile", "waxy", "ephemeral", "aromatic", "melting", "radiant", "consuming", "diminishing", "solitary", "atmospheric"]

Word: whisper
Definition: speak softly; in a low voice
Properties: ["quiet", "intimate", "secretive", "breathy", "gentle", "transient", "hushed", "conspiratorial", "directional", "private", "deliberate", "fleeting"]

Now extract properties for each of these word senses:

{batch_items}

Output ONLY a valid JSON array (no markdown, no explanation):
[{{"id": "...", "properties": [...]}}, ...]
"""

# Variant C: IDENTICAL to A except "5-10" → "10-15". Isolates the count effect.
# Every other word, example, and instruction is byte-for-byte the same as A.
PROMPT_C = """You are extracting sensory and behavioural properties for specific word senses.

CRITICAL: The definition tells you WHICH sense of the word to analyse. Many words have multiple meanings — focus ONLY on the sense described in the definition.

Extract 10-15 properties per word that describe:
- Physical qualities (texture, weight, temperature, luminosity, sound)
- Behavioural qualities (speed, rhythm, intensity, duration)
- Perceptual qualities (how it's experienced by senses)
- Functional qualities (what it does, how it moves, what it enables)

Properties must be SHORT (1-2 words). Be creative — capture the experiential essence, not just dictionary categories.

Examples showing sense disambiguation:

Word: run
Definition: deal in illegally, such as arms or liquor
Properties: ["furtive", "risky", "profitable", "shadowy", "underground", "covert", "transactional"]
(NOT: fast, athletic, sweaty — those are the locomotion sense)

Word: chain
Definition: a series of things depending on each other as if linked together
Properties: ["sequential", "dependent", "cascading", "fragile", "interconnected", "cumulative"]
(NOT: heavy, metallic, cold — those are the physical chain sense)

Word: fleece
Definition: shear the wool from
Properties: ["cutting", "harvesting", "seasonal", "rhythmic", "skilled", "yielding", "stripping"]
(NOT: woolly, soft, warm — those describe the material, not the shearing action)

Word: candle
Definition: stick of wax with a wick; gives light when burning
Properties: ["warm", "flickering", "luminous", "fragile", "waxy", "ephemeral", "aromatic"]

Word: whisper
Definition: speak softly; in a low voice
Properties: ["quiet", "intimate", "secretive", "breathy", "gentle", "transient", "hushed"]

Now extract properties for each of these word senses:

{batch_items}

Output ONLY a valid JSON array (no markdown, no explanation):
[{{"id": "...", "properties": [...]}}, ...]
"""

PROMPTS = {"A": PROMPT_A, "B": PROMPT_B, "C": PROMPT_C}


# --- Helpers ----------------------------------------------------------------

def format_batch_items(synsets: List[Dict]) -> str:
    lines = []
    for s in synsets:
        lines.append(f"ID: {s['id']}")
        lines.append(f"Word: {s['lemma']}")
        lines.append(f"Definition: {s['definition']}")
        lines.append("")
    return "\n".join(lines)


def load_checkpoint(checkpoint_path: Path) -> dict:
    if checkpoint_path.exists():
        with open(checkpoint_path) as f:
            return json.load(f)
    return {"completed_ids": [], "results": []}


def save_checkpoint(checkpoint_path: Path, state: dict):
    with open(checkpoint_path, 'w') as f:
        json.dump(state, f)


def make_extract_fn(client):
    """Create a retrying extraction function bound to a client."""

    @retry(
        stop=stop_after_attempt(5),
        wait=wait_exponential(multiplier=2, min=4, max=120),
        retry=retry_if_exception_type((Exception,)),
        before_sleep=lambda retry_state: print(
            f"    Retry {retry_state.attempt_number}/5 after error: "
            f"{retry_state.outcome.exception()}"
        ),
    )
    def extract_batch(synsets: List[Dict], prompt_template: str) -> List[Dict]:
        batch_items = format_batch_items(synsets)
        prompt = prompt_template.format(batch_items=batch_items)

        response = client.models.generate_content(
            model=MODEL_NAME,
            contents=prompt
        )

        local_data = {s['id']: s for s in synsets}

        text = response.text.strip()
        text = re.sub(r'^```json\s*', '', text)
        text = re.sub(r'\s*```$', '', text)
        results = json.loads(text)

        if not isinstance(results, list):
            raise ValueError(f"Expected list, got {type(results)}")

        merged = []
        for r in results:
            rid = str(r.get('id', ''))
            if rid in local_data:
                merged.append({
                    "id": rid,
                    "lemma": local_data[rid]['lemma'],
                    "definition": local_data[rid]['definition'],
                    "pos": local_data[rid].get('pos', ''),
                    "properties": r.get('properties', [])
                })
            else:
                print(f"    Warning: LLM returned unknown ID {rid}")

        return merged

    return extract_batch


# --- Main -------------------------------------------------------------------

def run_enrichment(variant: str, synsets_file: Path, batch_size: int = 20,
                   resume: bool = False):
    api_key = os.environ.get('GEMINI_API_KEY')
    if not api_key:
        raise ValueError("Set GEMINI_API_KEY environment variable")

    client = genai.Client(api_key=api_key)
    prompt_template = PROMPTS[variant]

    # Load benchmark synsets
    with open(synsets_file) as f:
        benchmark = json.load(f)
    all_synsets = benchmark["synsets"]

    # Checkpoint setup
    checkpoint_path = OUTPUT_DIR / f"checkpoint_{variant}.json"
    if resume:
        state = load_checkpoint(checkpoint_path)
        completed_ids = set(state["completed_ids"])
        results = state["results"]
        print(f"Resuming from checkpoint: {len(completed_ids)} synsets already done")
    else:
        completed_ids = set()
        results = []
        # Clean any stale checkpoint
        if checkpoint_path.exists():
            checkpoint_path.unlink()

    # Filter out already-completed synsets
    remaining = [s for s in all_synsets if s['id'] not in completed_ids]

    print(f"Enrichment variant {variant}")
    print(f"  Model: {MODEL_NAME}")
    variant_labels = {
        'A': 'original prompt, 5-10 props',
        'B': 'dual-dimension prompt, 10-15 props',
        'C': 'original prompt, 10-15 props',
    }
    print(f"  Prompt: {variant_labels.get(variant, variant)}")
    print(f"  Synsets: {len(remaining)} remaining of {len(all_synsets)} total")
    print(f"  Batch size: {batch_size}")

    extract_batch = make_extract_fn(client)
    all_properties = []
    failed_batches = 0

    num_batches = (len(remaining) + batch_size - 1) // batch_size
    for batch_idx in range(num_batches):
        start = batch_idx * batch_size
        end = min(start + batch_size, len(remaining))
        batch = remaining[start:end]

        print(f"\n  Batch {batch_idx + 1}/{num_batches} ({len(batch)} synsets)...")

        try:
            batch_results = extract_batch(batch, prompt_template)

            for result in batch_results:
                results.append(result)
                completed_ids.add(result['id'])
                props = result.get('properties', [])
                all_properties.extend(props)
                print(f"    {result.get('lemma', '?')}: {len(props)} properties")

            # Checkpoint after every batch
            save_checkpoint(checkpoint_path, {
                "completed_ids": list(completed_ids),
                "results": results,
            })

        except Exception as e:
            print(f"  BATCH FAILED after retries: {e}")
            failed_batches += 1
            # Save progress and continue
            save_checkpoint(checkpoint_path, {
                "completed_ids": list(completed_ids),
                "results": results,
            })

        # Gentle rate limiting — 1s between batches
        time.sleep(1)

    # Recompute all_properties from full results (in case of resume)
    all_properties = []
    for r in results:
        all_properties.extend(r.get('properties', []))

    property_freq = Counter(all_properties)

    output = {
        "synsets": results,
        "all_properties": list(set(all_properties)),
        "property_frequency": dict(property_freq.most_common(100)),
        "stats": {
            "total_synsets": len(results),
            "total_properties": len(all_properties),
            "unique_properties": len(set(all_properties)),
            "avg_properties_per_synset": round(
                len(all_properties) / len(results), 2
            ) if results else 0,
            "failed_batches": failed_batches,
        },
        "config": {
            "model": MODEL_NAME,
            "variant": variant,
            "prompt": variant_labels.get(variant, variant),
            "batch_size": batch_size,
            "benchmark_size": len(all_synsets),
            "benchmark_meta": benchmark.get("meta", {}),
        }
    }

    output_file = OUTPUT_DIR / f"ab_variant_{variant}.json"
    with open(output_file, 'w') as f:
        json.dump(output, f, indent=2)

    # Clean up checkpoint on success
    if failed_batches == 0 and checkpoint_path.exists():
        checkpoint_path.unlink()

    print(f"\nVariant {variant} complete!")
    print(f"  Synsets enriched: {output['stats']['total_synsets']}")
    print(f"  Unique properties: {output['stats']['unique_properties']}")
    print(f"  Avg properties/synset: {output['stats']['avg_properties_per_synset']}")
    print(f"  Failed batches: {failed_batches}")
    print(f"  Output: {output_file}")


def main():
    parser = argparse.ArgumentParser(description="A/B enrichment runner")
    parser.add_argument("--variant", "-v", required=True, choices=["A", "B", "C"],
                        help="Prompt variant: A (original 5-10), B (dual-dim 10-15), C (original 10-15)")
    parser.add_argument("--synsets-file", "-f", required=True, type=str,
                        help="Path to benchmark synsets JSON file")
    parser.add_argument("--batch-size", "-b", type=int, default=20,
                        help="Synsets per API call (default: 20)")
    parser.add_argument("--resume", "-r", action="store_true",
                        help="Resume from checkpoint")
    args = parser.parse_args()

    run_enrichment(
        variant=args.variant,
        synsets_file=Path(args.synsets_file),
        batch_size=args.batch_size,
        resume=args.resume,
    )


if __name__ == "__main__":
    main()
