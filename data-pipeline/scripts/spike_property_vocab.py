"""
Spike script to validate Two-Pass Enrichment approach (Solution 5).

Tests whether unconstrained LLM enrichment on small pilot (100 synsets)
produces diverse, curate-able property vocabulary.

Usage:
    python spike_property_vocab.py [--batch-size 20] [--pilot-size 100]

Output: property_spike.json with synsets, properties, frequency analysis
"""
import argparse
import sqlite3
import json
import os
import re
from pathlib import Path
from collections import Counter
from typing import List, Dict

try:
    from google import genai
except ImportError:
    raise ImportError("Run: pip install google-genai")

# Database is in main project root (parent of .worktrees)
SQLUNET_DB = Path(__file__).parent.parent.parent.parent.parent / "sqlunet_master.db"
OUTPUT_DIR = Path(__file__).parent.parent / "output"
OUTPUT_FILE = OUTPUT_DIR / "property_spike.json"

MODEL_NAME = "gemini-2.5-flash"  # Upgraded from Lite for better sense disambiguation

BATCH_PROMPT = """You are extracting sensory and behavioural properties for specific word senses.

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


def get_pilot_synsets(conn: sqlite3.Connection, limit: int) -> List[Dict]:
    """Get diverse pilot synsets: stratified by POS and frequency."""
    # Stratify: 40% nouns, 40% verbs, 20% adjectives (matches corpus distribution)
    queries = {
        'n': int(limit * 0.4),
        'v': int(limit * 0.4),
        'a': int(limit * 0.2)
    }

    synsets = []
    for pos, count in queries.items():
        cursor = conn.execute("""
            SELECT DISTINCT s.synsetid, s.definition, w.word
            FROM synsets s
            JOIN senses se ON se.synsetid = s.synsetid
            JOIN words w ON w.wordid = se.wordid
            WHERE s.posid = ?
            ORDER BY RANDOM()
            LIMIT ?
        """, (pos, count))
        synsets.extend([{
            "id": str(row[0]),
            "definition": row[1],
            "lemma": row[2]
        } for row in cursor.fetchall()])

    return synsets


def format_batch_items(synsets: List[Dict]) -> str:
    """Format synsets for batch prompt."""
    lines = []
    for s in synsets:
        lines.append(f"ID: {s['id']}")
        lines.append(f"Word: {s['lemma']}")
        lines.append(f"Definition: {s['definition']}")
        lines.append("")
    return "\n".join(lines)


def extract_properties_batch(client, synsets: List[Dict]) -> List[Dict]:
    """Extract properties for a batch of synsets."""
    batch_items = format_batch_items(synsets)
    prompt = BATCH_PROMPT.format(batch_items=batch_items)

    response = client.models.generate_content(
        model=MODEL_NAME,
        contents=prompt
    )

    # Build lookup for local data
    local_data = {s['id']: s for s in synsets}

    try:
        # Clean response - remove markdown code blocks if present
        text = response.text.strip()
        text = re.sub(r'^```json\s*', '', text)
        text = re.sub(r'\s*```$', '', text)
        results = json.loads(text)

        # Validate we got a list
        if not isinstance(results, list):
            raise ValueError(f"Expected list, got {type(results)}")

        # Merge LLM output (id, properties) with local data (lemma, definition)
        merged = []
        for r in results:
            rid = str(r.get('id', ''))
            if rid in local_data:
                merged.append({
                    "id": rid,
                    "lemma": local_data[rid]['lemma'],
                    "definition": local_data[rid]['definition'],
                    "properties": r.get('properties', [])
                })
            else:
                print(f"    Warning: LLM returned unknown ID {rid}")

        return merged

    except (json.JSONDecodeError, ValueError) as e:
        print(f"  Batch parse error: {e}")
        print(f"  Raw response (first 500 chars): {response.text[:500]}")
        # Return empty results for this batch
        return [{"id": s['id'], "lemma": s['lemma'], "definition": s['definition'], "properties": []}
                for s in synsets]


def run_spike(batch_size: int = 20, pilot_size: int = 100):
    """Run property vocabulary spike."""
    api_key = os.environ.get('GEMINI_API_KEY')
    if not api_key:
        raise ValueError("Set GEMINI_API_KEY environment variable")

    client = genai.Client(api_key=api_key)

    if not SQLUNET_DB.exists():
        raise FileNotFoundError(f"Database not found: {SQLUNET_DB}")

    conn = sqlite3.connect(SQLUNET_DB)

    print(f"Running property vocabulary spike...")
    print(f"  Pilot size: {pilot_size} synsets")
    print(f"  Batch size: {batch_size}")
    print(f"  Model: {MODEL_NAME}")
    print(f"  Database: {SQLUNET_DB}")

    synsets = get_pilot_synsets(conn, pilot_size)
    print(f"  Retrieved {len(synsets)} synsets")

    results = []
    all_properties = []

    # Process in batches
    num_batches = (len(synsets) + batch_size - 1) // batch_size
    for batch_idx in range(num_batches):
        start = batch_idx * batch_size
        end = min(start + batch_size, len(synsets))
        batch = synsets[start:end]

        print(f"\n  Batch {batch_idx + 1}/{num_batches} ({len(batch)} synsets)...")
        batch_results = extract_properties_batch(client, batch)

        for result in batch_results:
            results.append(result)
            props = result.get('properties', [])
            all_properties.extend(props)
            print(f"    {result.get('lemma', '?')}: {len(props)} properties")

    # Analyse property frequency
    property_freq = Counter(all_properties)

    output = {
        "synsets": results,
        "all_properties": list(set(all_properties)),
        "property_frequency": dict(property_freq.most_common(100)),
        "stats": {
            "total_synsets": len(results),
            "total_properties": len(all_properties),
            "unique_properties": len(set(all_properties)),
            "avg_properties_per_synset": round(len(all_properties) / len(results), 2) if results else 0
        },
        "config": {
            "model": MODEL_NAME,
            "batch_size": batch_size,
            "pilot_size": pilot_size
        }
    }

    OUTPUT_DIR.mkdir(exist_ok=True)
    with open(OUTPUT_FILE, 'w') as f:
        json.dump(output, f, indent=2)

    print(f"\nSpike complete!")
    print(f"  Unique properties: {output['stats']['unique_properties']}")
    print(f"  Avg properties/synset: {output['stats']['avg_properties_per_synset']}")
    print(f"  Output: {OUTPUT_FILE}")

    conn.close()


def main():
    parser = argparse.ArgumentParser(
        description="Run property vocabulary spike to validate Two-Pass Enrichment approach"
    )
    parser.add_argument(
        "--batch-size", "-b",
        type=int,
        default=20,
        help="Number of synsets per LLM call (default: 20)"
    )
    parser.add_argument(
        "--pilot-size", "-n",
        type=int,
        default=100,
        help="Total number of synsets to process (default: 100)"
    )
    args = parser.parse_args()

    run_spike(batch_size=args.batch_size, pilot_size=args.pilot_size)


if __name__ == "__main__":
    main()
