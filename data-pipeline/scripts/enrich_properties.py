"""Production enrichment script using claude -p CLI.

Extracts sensory/behavioural properties from WordNet synsets via Claude.
Uses the winning Variant C prompt (original prompt, 10-15 properties).

Usage:
    python enrich_properties.py [--size 2000] [--batch-size 20] [--model haiku]
                                [--delay 1.0] [--resume] [--output FILE]
                                [--synset-ids FILE]
"""
import argparse
import json
import logging
import sqlite3
import sys
import time
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Dict, Optional

log = logging.getLogger(__name__)

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "lib"))
from claude_client import prompt_json, RateLimitError

from utils import LEXICON_V2, OUTPUT_DIR


# --- Errors ------------------------------------------------------------------

# Backward-compatible alias for callers that catch UsageExhaustedError
UsageExhaustedError = RateLimitError


@dataclass
class EnrichmentResult:
    """Result of a run_enrichment() invocation, including coverage stats."""
    output_file: str
    requested: int
    succeeded: int
    failed: int
    failed_ids: list[str] = field(default_factory=list)

    @property
    def coverage(self) -> float:
        return self.succeeded / self.requested if self.requested else 1.0


# --- Prompt (Variant C: original prompt, 10-15 properties) -------------------

BATCH_PROMPT = """You are extracting sensory and behavioural properties for specific word senses.

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


# --- Helpers ------------------------------------------------------------------

def format_batch_items(synsets: List[Dict]) -> str:
    """Format synsets for the batch prompt."""
    lines = []
    for s in synsets:
        lines.append(f"ID: {s['id']}")
        lines.append(f"Word: {s['lemma']}")
        lines.append(f"Definition: {s['definition']}")
        lines.append("")
    return "\n".join(lines)


def extract_batch(
    synsets: List[Dict],
    model: str = "haiku",
    prompt_template: str = None,
    verbose: bool = False,
) -> List[Dict]:
    """Extract properties for a batch of synsets via Claude CLI.

    Returns merged results with local data (lemma, definition, pos).
    Retries up to 5 times on failure via claude_client.
    """
    template = prompt_template or BATCH_PROMPT
    if "{batch_items}" not in template:
        raise ValueError("prompt_template must contain {batch_items} placeholder")
    batch_items = format_batch_items(synsets)
    prompt = template.format(batch_items=batch_items)

    results = prompt_json(prompt, model=model, expect=list, verbose=verbose)

    local_data = {s['id']: s for s in synsets}
    merged = []
    for r in results:
        rid = str(r.get('id', ''))
        if rid in local_data:
            merged.append({
                "id": rid,
                "lemma": local_data[rid]['lemma'],
                "definition": local_data[rid]['definition'],
                "pos": local_data[rid].get('pos', ''),
                "properties": r.get('properties', []),
            })
        else:
            log.warning("LLM returned unknown ID %s", rid)
    return merged


# --- Checkpoint ---------------------------------------------------------------

def load_checkpoint(checkpoint_path: Path) -> dict:
    """Load checkpoint state from disk, or return empty state."""
    if checkpoint_path.exists():
        with open(checkpoint_path) as f:
            return json.load(f)
    return {"completed_ids": [], "results": []}


def save_checkpoint(checkpoint_path: Path, state: dict):
    """Save checkpoint state to disk."""
    with open(checkpoint_path, 'w') as f:
        json.dump(state, f)


# --- Synset selection ---------------------------------------------------------

def get_pilot_synsets(
    conn: sqlite3.Connection,
    limit: int,
    required_ids: Optional[List[str]] = None,
) -> List[Dict]:
    """Get diverse synsets: stratified by POS and frequency.

    Queries lexicon_v2 schema (synsets + lemmas tables).
    If required_ids is provided, those synsets are included first, then
    remaining slots are filled randomly to reach the limit.
    """
    synsets = []
    seen_ids = set()

    # Phase 1: fetch required synsets by ID
    if required_ids:
        placeholders = ",".join("?" for _ in required_ids)
        cursor = conn.execute(f"""
            SELECT DISTINCT s.synset_id, s.definition, l.lemma, s.pos
            FROM synsets s
            JOIN lemmas l ON l.synset_id = s.synset_id
            WHERE s.synset_id IN ({placeholders})
        """, required_ids)
        for row in cursor.fetchall():
            sid = str(row[0])
            if sid not in seen_ids:
                synsets.append({
                    "id": sid,
                    "definition": row[1],
                    "lemma": row[2],
                    "pos": row[3],
                })
                seen_ids.add(sid)

    # Phase 2: fill remaining slots with random stratified selection
    remaining = limit - len(synsets)
    if remaining > 0:
        queries = {
            'n': int(remaining * 0.4),
            'v': int(remaining * 0.4),
            'a': int(remaining * 0.2),
        }

        for pos, count in queries.items():
            if seen_ids:
                exclude_placeholders = ",".join("?" for _ in seen_ids)
                cursor = conn.execute(f"""
                    SELECT DISTINCT s.synset_id, s.definition, l.lemma
                    FROM synsets s
                    JOIN lemmas l ON l.synset_id = s.synset_id
                    WHERE s.pos = ?
                      AND s.synset_id NOT IN ({exclude_placeholders})
                    ORDER BY RANDOM()
                    LIMIT ?
                """, (pos, *seen_ids, count))
            else:
                cursor = conn.execute("""
                    SELECT DISTINCT s.synset_id, s.definition, l.lemma
                    FROM synsets s
                    JOIN lemmas l ON l.synset_id = s.synset_id
                    WHERE s.pos = ?
                    ORDER BY RANDOM()
                    LIMIT ?
                """, (pos, count))
            for row in cursor.fetchall():
                sid = str(row[0])
                if sid not in seen_ids:
                    synsets.append({
                        "id": sid,
                        "definition": row[1],
                        "lemma": row[2],
                        "pos": pos,
                    })
                    seen_ids.add(sid)

    return synsets


# --- Main loop ----------------------------------------------------------------

def run_enrichment(
    size: int = 2000,
    batch_size: int = 20,
    model: str = "haiku",
    delay: float = 1.0,
    resume: bool = False,
    output_file: Path = None,
    synset_ids_file: Path = None,
    required_synset_ids: set[str] = None,
    prompt_template: str = None,
    verbose: bool = False,
    db_path: str = None,
) -> EnrichmentResult:
    """Run property enrichment on synsets using claude CLI.

    Queries synset data from the lexicon DB (lexicon_v2 schema).
    Returns an EnrichmentResult dataclass.
    """
    if db_path is None:
        db_path = str(LEXICON_V2)

    db = Path(db_path)
    if not db.exists():
        raise FileNotFoundError(f"Database not found: {db_path}")

    conn = sqlite3.connect(db_path)
    try:
        if output_file is None:
            output_file = OUTPUT_DIR / f"property_pilot_{size}.json"

        checkpoint_path = OUTPUT_DIR / "checkpoint_enrich.json"

        # Load required synset IDs — from set, file, or neither
        required_ids = None
        if required_synset_ids is not None:
            required_ids = list(required_synset_ids)
            print(f"  Required synset IDs: {len(required_ids)} (passed directly)")
        elif synset_ids_file is not None:
            with open(synset_ids_file) as f:
                required_ids = json.load(f)
            print(f"  Required synset IDs: {len(required_ids)} from {synset_ids_file}")

        print(f"Running property enrichment...")
        print(f"  Size: {size} synsets")
        print(f"  Batch size: {batch_size}")
        print(f"  Model: {model}")
        print(f"  Database: {db_path}")

        synsets = get_pilot_synsets(conn, size, required_ids=required_ids)
        print(f"  Retrieved {len(synsets)} synsets")

        # Checkpoint handling
        if resume:
            state = load_checkpoint(checkpoint_path)
            completed_ids = set(state["completed_ids"])
            results = state["results"]
            print(f"  Resuming from checkpoint: {len(completed_ids)} already done")
        else:
            completed_ids = set()
            results = []
            if checkpoint_path.exists():
                checkpoint_path.unlink()

        remaining = [s for s in synsets if s['id'] not in completed_ids]

        all_properties = []
        failed_batches = 0
        failed_synset_ids: list[str] = []

        num_batches = (len(remaining) + batch_size - 1) // batch_size
        for batch_idx in range(num_batches):
            start = batch_idx * batch_size
            end = min(start + batch_size, len(remaining))
            batch = remaining[start:end]

            print(f"\n  Batch {batch_idx + 1}/{num_batches} ({len(batch)} synsets)...")

            try:
                batch_results = extract_batch(
                    batch, model=model, prompt_template=prompt_template,
                    verbose=verbose,
                )

                for result in batch_results:
                    results.append(result)
                    completed_ids.add(result['id'])
                    props = result.get('properties', [])
                    all_properties.extend(props)
                    print(f"    {result.get('lemma', '?')}: {len(props)} properties")

                save_checkpoint(checkpoint_path, {
                    "completed_ids": list(completed_ids),
                    "results": results,
                })

            except Exception as e:
                print(f"  BATCH FAILED after retries: {e}")
                failed_batches += 1
                failed_synset_ids.extend(s['id'] for s in batch)
                save_checkpoint(checkpoint_path, {
                    "completed_ids": list(completed_ids),
                    "results": results,
                })

            if delay > 0:
                time.sleep(delay)

        # Recompute all_properties from full results (covers resume case)
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
                "failed_synset_ids": failed_synset_ids,
            },
            "config": {
                "model": model,
                "batch_size": batch_size,
                "size": size,
            },
        }

        output_file.parent.mkdir(exist_ok=True)
        with open(output_file, 'w') as f:
            json.dump(output, f, indent=2)

        # Clean up checkpoint on full success
        if failed_batches == 0 and checkpoint_path.exists():
            checkpoint_path.unlink()

        print(f"\nEnrichment complete!")
        print(f"  Synsets enriched: {output['stats']['total_synsets']}")
        print(f"  Unique properties: {output['stats']['unique_properties']}")
        print(f"  Avg properties/synset: {output['stats']['avg_properties_per_synset']}")
        print(f"  Failed batches: {failed_batches}")
        print(f"  Output: {output_file}")

    finally:
        conn.close()

    return EnrichmentResult(
        output_file=str(output_file),
        requested=len(synsets),
        succeeded=len(results),
        failed=len(failed_synset_ids),
        failed_ids=failed_synset_ids,
    )


def main():
    parser = argparse.ArgumentParser(
        description="Extract sensory/behavioural properties from synsets via Claude CLI"
    )
    parser.add_argument(
        "--size", "-n", type=int, default=2000,
        help="Total synsets to enrich (default: 2000)",
    )
    parser.add_argument(
        "--batch-size", "-b", type=int, default=20,
        help="Synsets per claude invocation (default: 20)",
    )
    parser.add_argument(
        "--model", "-m", type=str, default="haiku",
        help="Claude model alias (default: haiku)",
    )
    parser.add_argument(
        "--delay", type=float, default=1.0,
        help="Seconds between batches (default: 1.0)",
    )
    parser.add_argument(
        "--resume", "-r", action="store_true",
        help="Resume from checkpoint",
    )
    parser.add_argument(
        "--output", "-o", type=str, default=None,
        help="Output file path (default: property_pilot_<size>.json)",
    )
    parser.add_argument(
        "--synset-ids", type=str, default=None,
        help="JSON file with array of synset IDs to enrich (optional)",
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true",
        help="Enable DEBUG logging for raw LLM request/response",
    )
    args = parser.parse_args()

    if args.verbose:
        logging.basicConfig(level=logging.DEBUG, format="%(levelname)s: %(message)s")

    output_file = Path(args.output) if args.output else None
    synset_ids_file = Path(args.synset_ids) if args.synset_ids else None
    run_enrichment(
        size=args.size,
        batch_size=args.batch_size,
        model=args.model,
        delay=args.delay,
        resume=args.resume,
        output_file=output_file,
        synset_ids_file=synset_ids_file,
        verbose=args.verbose,
    )


if __name__ == "__main__":
    main()
