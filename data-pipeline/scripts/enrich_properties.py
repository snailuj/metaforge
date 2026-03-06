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

BATCH_PROMPT_V2 = """You are extracting sensory and behavioural properties for specific word senses, with salience weights and metadata.

CRITICAL: The definition tells you WHICH sense of the word to analyse. Many words have multiple meanings — focus ONLY on the sense described in the definition.

For each word sense, provide:

1. **usage_example**: A natural sentence using the word in this specific sense.

2. **properties**: 10-15 properties, each as a JSON object:
   - "text": exactly ONE word (no hyphens, no compounds, no spaces)
     GOOD: flickering, frigid, shrill, dense, molten, conical, pungent
     BAD: cold metal (two words), high-pitched (hyphenated), lava-formed (compound)
     If you need "cold metal", choose ONE word: frigid, metallic, or icy
   - "salience": 0.0-1.0 — how immediately/strongly this property comes to mind for this concept
     - 0.9-1.0: Defining, inescapable (fire → hot, ice → cold)
     - 0.6-0.8: Strong association (fire → dangerous, ice → slippery)
     - 0.3-0.5: Secondary/contextual (fire → ancient, ice → seasonal)
   - "type": one of "physical", "behaviour", "effect", "functional", "emotional", "social"
   - "relation": short phrase linking word to property (e.g. "fire emits heat")

   Property types:
   - physical: texture, weight, temperature, luminosity, sound, colour, shape, size, material, smell, taste
   - behaviour: speed, rhythm, intensity, duration, pattern of movement
   - effect: what it causes, its consequences, its aftermath
   - functional: what it does, enables, or is used for
   - emotional: feelings it evokes or is associated with
   - social: cultural, relational, or status associations

   IMPORTANT: At least 4 of your properties must have type "physical". Most concrete nouns
   have at least 4 physical qualities. If the concept genuinely has fewer, include as many
   as truly apply.

3. **lemma_metadata**: For EACH listed lemma, provide:
   - "lemma": the word form
   - "register": "formal", "neutral", "informal", or "slang"
   - "connotation": "positive", "neutral", or "negative"

Examples:

Word: candle
Lemmas: candle, taper
Definition: stick of wax with a wick; gives light when burning

{{"id": "oewn-candle-n", "usage_example": "She lit a candle and watched the flame flicker in the draught.", "properties": [{{"text": "warm", "salience": 0.9, "type": "physical", "relation": "candle emits warmth"}}, {{"text": "flickering", "salience": 0.85, "type": "behaviour", "relation": "flame flickers"}}, {{"text": "ephemeral", "salience": 0.7, "type": "effect", "relation": "candle burns away"}}, {{"text": "luminous", "salience": 0.8, "type": "physical", "relation": "candle gives light"}}, {{"text": "waxy", "salience": 0.75, "type": "physical", "relation": "made of wax"}}, {{"text": "fragile", "salience": 0.6, "type": "physical", "relation": "wick is delicate"}}, {{"text": "aromatic", "salience": 0.5, "type": "effect", "relation": "scented candles smell"}}, {{"text": "ceremonial", "salience": 0.4, "type": "social", "relation": "used in rituals"}}, {{"text": "intimate", "salience": 0.65, "type": "emotional", "relation": "evokes closeness"}}, {{"text": "ancient", "salience": 0.3, "type": "social", "relation": "pre-electric lighting"}}], "lemma_metadata": [{{"lemma": "candle", "register": "neutral", "connotation": "positive"}}, {{"lemma": "taper", "register": "formal", "connotation": "neutral"}}]}}

Word: volcano
Lemmas: volcano
Definition: a mountain formed by volcanic material

{{"id": "oewn-volcano-n", "usage_example": "The volcano erupted, sending a plume of ash into the sky.", "properties": [{{"text": "hot", "salience": 0.95, "type": "physical", "relation": "volcano radiates extreme heat"}}, {{"text": "conical", "salience": 0.8, "type": "physical", "relation": "volcano has cone shape"}}, {{"text": "towering", "salience": 0.85, "type": "physical", "relation": "volcano is very tall"}}, {{"text": "molten", "salience": 0.9, "type": "physical", "relation": "contains molten lava"}}, {{"text": "ashy", "salience": 0.7, "type": "physical", "relation": "produces ash"}}, {{"text": "eruptive", "salience": 0.85, "type": "behaviour", "relation": "volcano erupts violently"}}, {{"text": "destructive", "salience": 0.75, "type": "effect", "relation": "eruptions destroy surroundings"}}, {{"text": "dormant", "salience": 0.5, "type": "behaviour", "relation": "may be inactive for years"}}, {{"text": "rumbling", "salience": 0.65, "type": "physical", "relation": "produces low sounds"}}, {{"text": "ancient", "salience": 0.4, "type": "social", "relation": "geological timescale"}}], "lemma_metadata": [{{"lemma": "volcano", "register": "neutral", "connotation": "negative"}}]}}
(NOT: magmatic, pyroclastic, geological — these are taxonomic labels, not experiential properties)

Now extract properties for each of these word senses:

{batch_items}

Output ONLY a valid JSON array (no markdown, no explanation):
[{{"id": "...", "usage_example": "...", "properties": [...], "lemma_metadata": [...]}}, ...]
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


def format_batch_items_v2(synsets: List[Dict]) -> str:
    """Format synsets for the v2 batch prompt, including all lemmas."""
    lines = []
    for s in synsets:
        lines.append(f"ID: {s['id']}")
        lines.append(f"Word: {s['lemma']}")
        all_lemmas = s.get("all_lemmas", [s["lemma"]])
        lines.append(f"Lemmas: {', '.join(all_lemmas)}")
        lines.append(f"Definition: {s['definition']}")
        lines.append("")
    return "\n".join(lines)


def extract_batch(
    synsets: List[Dict],
    model: str = "haiku",
    prompt_template: str = None,
    formatter=None,
    verbose: bool = False,
) -> List[Dict]:
    """Extract properties for a batch of synsets via Claude CLI.

    Returns merged results with local data (lemma, definition, pos).
    Retries up to 5 times on failure via claude_client.

    Args:
        formatter: callable to format synsets for the prompt.
            Defaults to format_batch_items (v1).
    """
    template = prompt_template or BATCH_PROMPT
    if "{batch_items}" not in template:
        raise ValueError("prompt_template must contain {batch_items} placeholder")
    fmt = formatter or format_batch_items
    batch_items = fmt(synsets)
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
                "usage_example": r.get('usage_example', ''),
                "lemma_metadata": r.get('lemma_metadata', []),
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


def get_frequency_ranked_synsets(
    conn: sqlite3.Connection,
    limit: int,
    required_ids: list | None = None,
) -> List[Dict]:
    """Get synsets ranked by max lemma familiarity, excluding already-enriched.

    If required_ids is provided, those synsets are included first, then
    remaining slots are filled with frequency-ranked synsets up to limit.

    For each synset, picks the most familiar lemma (for the enrichment prompt).
    Synsets already present in the enrichment table are excluded (padding only).
    """
    synsets = []
    seen_ids = set()

    # Phase 1: fetch required synsets by ID (unconditional — not excluded by enrichment)
    if required_ids:
        placeholders = ",".join("?" for _ in required_ids)
        cursor = conn.execute(f"""
            WITH ranked_lemmas AS (
                SELECT
                    s.synset_id,
                    s.definition,
                    s.pos,
                    l.lemma,
                    ROW_NUMBER() OVER (
                        PARTITION BY s.synset_id
                        ORDER BY COALESCE(f.familiarity, 0) DESC, l.lemma
                    ) AS rn
                FROM synsets s
                JOIN lemmas l ON l.synset_id = s.synset_id
                LEFT JOIN frequencies f ON f.lemma = l.lemma
                WHERE s.synset_id IN ({placeholders})
            )
            SELECT synset_id, definition, lemma, pos
            FROM ranked_lemmas
            WHERE rn = 1
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

    # Phase 2: pad remaining slots with frequency-ranked synsets
    remaining = limit - len(synsets)
    if remaining > 0:
        # Check if enrichment table exists (fresh DBs may not have it)
        has_enrichment = conn.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='enrichment'"
        ).fetchone()[0] > 0

        exclude_clause = (
            "AND s.synset_id NOT IN (SELECT synset_id FROM enrichment)"
            if has_enrichment else ""
        )

        # Also exclude already-selected required IDs
        if seen_ids:
            seen_placeholders = ",".join("?" for _ in seen_ids)
            seen_clause = f"AND s.synset_id NOT IN ({seen_placeholders})"
            seen_params = list(seen_ids)
        else:
            seen_clause = ""
            seen_params = []

        cursor = conn.execute(f"""
            WITH ranked_lemmas AS (
                SELECT
                    s.synset_id,
                    s.definition,
                    s.pos,
                    l.lemma,
                    COALESCE(f.familiarity, 0) AS fam,
                    ROW_NUMBER() OVER (
                        PARTITION BY s.synset_id
                        ORDER BY COALESCE(f.familiarity, 0) DESC, l.lemma
                    ) AS rn,
                    MAX(COALESCE(f.familiarity, 0)) OVER (
                        PARTITION BY s.synset_id
                    ) AS max_fam
                FROM synsets s
                JOIN lemmas l ON l.synset_id = s.synset_id
                LEFT JOIN frequencies f ON f.lemma = l.lemma
                WHERE 1=1 {exclude_clause} {seen_clause}
            )
            SELECT synset_id, definition, lemma, pos
            FROM ranked_lemmas
            WHERE rn = 1
            ORDER BY max_fam DESC
            LIMIT ?
        """, (*seen_params, remaining))

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

    # Attach all lemmas per synset (for v2 prompt)
    synset_ids = [s["id"] for s in synsets]
    if synset_ids:
        placeholders = ",".join("?" * len(synset_ids))
        lemma_rows = conn.execute(
            f"SELECT synset_id, lemma FROM lemmas WHERE synset_id IN ({placeholders})",
            synset_ids,
        ).fetchall()
        lemma_map: dict[str, list[str]] = {}
        for sid, lemma in lemma_rows:
            lemma_map.setdefault(sid, []).append(lemma)
        for s in synsets:
            s["all_lemmas"] = lemma_map.get(s["id"], [s["lemma"]])

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
    strategy: str = "random",
    schema_version: str = "v1",
) -> EnrichmentResult:
    """Run property enrichment on synsets using claude CLI.

    Queries synset data from the lexicon DB (lexicon_v2 schema).
    Returns an EnrichmentResult dataclass.

    Args:
        schema_version: "v1" for plain property strings, "v2" for structured
            property objects with salience, type, relation, and lemma metadata.
    """
    if db_path is None:
        db_path = str(LEXICON_V2)

    db = Path(db_path)
    if not db.exists():
        raise FileNotFoundError(f"Database not found: {db_path}")

    conn = sqlite3.connect(db_path)
    try:
        if output_file is None:
            raise ValueError("output_file is required")

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

        # Select prompt template and formatter based on schema version
        if schema_version == "v2":
            template = BATCH_PROMPT_V2
            formatter = format_batch_items_v2
        else:
            template = prompt_template or BATCH_PROMPT
            formatter = format_batch_items

        print(f"Running property enrichment...")
        print(f"  Size: {size} synsets")
        print(f"  Batch size: {batch_size}")
        print(f"  Model: {model}")
        print(f"  Strategy: {strategy}")
        print(f"  Schema version: {schema_version}")
        print(f"  Database: {db_path}")

        if strategy == "frequency":
            synsets = get_frequency_ranked_synsets(conn, size, required_ids=required_ids)
        else:
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
                    batch, model=model, prompt_template=template,
                    formatter=formatter, verbose=verbose,
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

        # Extract text key for stats (v2 properties are dicts, v1 are strings)
        property_texts = [
            p["text"] if isinstance(p, dict) else p
            for p in all_properties
        ]
        property_freq = Counter(property_texts)

        output = {
            "synsets": results,
            "all_properties": list(set(property_texts)),
            "property_frequency": dict(property_freq.most_common(100)),
            "stats": {
                "total_synsets": len(results),
                "total_properties": len(property_texts),
                "unique_properties": len(set(property_texts)),
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
                "schema_version": schema_version,
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
        "--output", "-o", type=str, required=True,
        help="Output file path (e.g. enrichment_8000_sonnet_20260220.json)",
    )
    parser.add_argument(
        "--synset-ids", type=str, default=None,
        help="JSON file with array of synset IDs to enrich (optional)",
    )
    parser.add_argument(
        "--strategy", type=str, default="random",
        choices=["random", "frequency"],
        help="Synset selection strategy: 'random' (POS-stratified) or 'frequency' (by familiarity, excludes already-enriched)",
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true",
        help="Enable DEBUG logging for raw LLM request/response",
    )
    parser.add_argument(
        "--schema-version", type=str, default="v1",
        choices=["v1", "v2"],
        help="Enrichment schema version: v1 (plain strings) or v2 (structured with salience/type/relation/lemma_metadata)",
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
        strategy=args.strategy,
        schema_version=args.schema_version,
    )


if __name__ == "__main__":
    main()
