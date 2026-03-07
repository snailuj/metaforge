"""Gap-fill physical properties for flagged synsets.

Targeted second-pass enrichment: calls the LLM with a physical-only prompt
for synsets that have insufficient physical properties (as identified by
audit_physical_coverage.py).

Output is enrichment-format JSON compatible with enrich.sh --from-json.

Usage:
    python gap_fill_physical.py --synset-ids flagged.json --db lexicon_v2.db \
      --model sonnet --output gap_fill_physical.json
"""

import argparse
import json
import logging
import sqlite3
import sys
import time
from collections import Counter
from pathlib import Path
from typing import List, Dict

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "lib"))
from claude_client import prompt_json, RateLimitError

OUTPUT_DIR = Path(__file__).parent.parent / "output"

GAP_FILL_PROMPT = """You are extracting PHYSICAL and SENSORY properties for specific word senses.

For each word sense below, provide 4-6 properties that describe its physical, tangible, or sensory qualities.

RULES:
- Each property must be a SINGLE WORD (no hyphens, no compounds, no phrases)
- Focus ONLY on physical/sensory properties: texture, weight, temperature, shape, colour, sound, smell, taste, luminosity, size
- The definition tells you WHICH sense — focus only on that sense
- Every property gets salience 0.0-1.0 and a short relation phrase

Output format per word:
{{"id": "...", "properties": [{{"text": "word", "salience": 0.8, "type": "physical", "relation": "short phrase"}}]}}

Example:

Word: anvil
Definition: a heavy block of iron or steel on which hot metals are hammered into shape
Properties: heavy, metallic, dense, dark, resonant, rigid

{batch_items}

Output ONLY a valid JSON array (no markdown, no explanation):
[{{"id": "...", "properties": [...]}}, ...]
"""


def format_gap_fill_batch(synsets: List[Dict]) -> str:
    """Format synsets for the gap-fill prompt."""
    lines = []
    for s in synsets:
        lines.append(f"ID: {s['id']}")
        lines.append(f"Word: {s['lemma']}")
        lines.append(f"Definition: {s['definition']}")
        lines.append("")
    return "\n".join(lines)


def load_synsets_from_db(db_path: str, synset_ids: list[str]) -> List[Dict]:
    """Look up synset details from the DB for gap-fill."""
    conn = sqlite3.connect(db_path)
    try:
        placeholders = ",".join("?" for _ in synset_ids)
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
        """, synset_ids)
        return [
            {"id": str(row[0]), "definition": row[1], "lemma": row[2], "pos": row[3]}
            for row in cursor.fetchall()
        ]
    finally:
        conn.close()


def build_output(results: List[Dict], model: str, batch_size: int) -> dict:
    """Build enrichment-format output JSON."""
    all_properties = []
    for r in results:
        all_properties.extend(r.get("properties", []))

    property_texts = [
        p["text"] if isinstance(p, dict) else p
        for p in all_properties
    ]
    property_freq = Counter(property_texts)

    return {
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
        },
        "config": {
            "model": model,
            "batch_size": batch_size,
            "purpose": "gap_fill_physical",
        },
    }


def load_checkpoint(checkpoint_path: Path) -> dict:
    """Load checkpoint state, or return empty state.

    Handles both unified format (synsets key) and legacy format (results key).
    Always returns with 'synsets' key for caller consistency.
    """
    if checkpoint_path.exists():
        with open(checkpoint_path) as f:
            data = json.load(f)
        # Backward compat: remap legacy 'results' key to 'synsets'
        if "results" in data and "synsets" not in data:
            data["synsets"] = data.pop("results")
        return data
    return {"completed_ids": [], "synsets": []}


def save_checkpoint(checkpoint_path: Path, state: dict):
    """Save checkpoint state to disk."""
    with open(checkpoint_path, "w") as f:
        json.dump(state, f, indent=2)


def run_gap_fill(
    synsets: List[Dict],
    model: str = "sonnet",
    batch_size: int = 20,
    delay: float = 1.0,
    output_file: Path = None,
    resume: bool = False,
    verbose: bool = False,
) -> dict:
    """Run physical gap-fill enrichment on synsets."""
    checkpoint_path = OUTPUT_DIR / "checkpoint_gap_fill.json"

    if resume:
        state = load_checkpoint(checkpoint_path)
        completed_ids = set(state["completed_ids"])
        results = state["synsets"]
        print(f"  Resuming from checkpoint: {len(completed_ids)} already done")
    else:
        completed_ids = set()
        results = []
        if checkpoint_path.exists():
            checkpoint_path.unlink()

    remaining = [s for s in synsets if s["id"] not in completed_ids]
    failed_batches = 0

    num_batches = (len(remaining) + batch_size - 1) // batch_size
    print(f"Gap-fill: {len(remaining)} synsets in {num_batches} batches")

    for batch_idx in range(num_batches):
        start = batch_idx * batch_size
        end = min(start + batch_size, len(remaining))
        batch = remaining[start:end]

        print(f"\n  Batch {batch_idx + 1}/{num_batches} ({len(batch)} synsets)...")

        try:
            batch_items = format_gap_fill_batch(batch)
            prompt = GAP_FILL_PROMPT.format(batch_items=batch_items)
            batch_results = prompt_json(prompt, model=model, expect=list, verbose=verbose)

            local_data = {s["id"]: s for s in batch}
            for r in batch_results:
                rid = str(r.get("id", ""))
                if rid in local_data:
                    # Merge local data (lemma, definition, pos) into result
                    r["lemma"] = local_data[rid]["lemma"]
                    r["definition"] = local_data[rid]["definition"]
                    r["pos"] = local_data[rid]["pos"]
                    # Force all properties to physical type
                    for p in r.get("properties", []):
                        p["type"] = "physical"
                    results.append(r)
                    completed_ids.add(rid)
                    print(f"    {r.get('lemma', '?')}: {len(r.get('properties', []))} physical properties")

            save_checkpoint(checkpoint_path, {
                "completed_ids": list(completed_ids),
                "synsets": results,
            })

        except RateLimitError as e:
            print(f"  RATE LIMITED — stopping: {e}")
            break
        except Exception as e:
            print(f"  BATCH FAILED: {e}")
            failed_batches += 1

        if delay > 0:
            time.sleep(delay)

    output = build_output(results, model=model, batch_size=batch_size)

    if output_file:
        output_file.parent.mkdir(exist_ok=True)
        with open(output_file, "w") as f:
            json.dump(output, f, indent=2)

    # Clean up checkpoint on success
    if failed_batches == 0 and checkpoint_path.exists():
        checkpoint_path.unlink()

    print(f"\nGap-fill complete!")
    print(f"  Synsets: {output['stats']['total_synsets']}")
    print(f"  Properties: {output['stats']['total_properties']}")
    print(f"  Failed batches: {failed_batches}")

    return output


def main():
    parser = argparse.ArgumentParser(
        description="Gap-fill physical properties for flagged synsets"
    )
    parser.add_argument(
        "--synset-ids", "-s", type=str, required=True,
        help="JSON file with audit output (must contain 'flagged_ids' key)",
    )
    parser.add_argument(
        "--db", type=str, required=True,
        help="Path to lexicon_v2.db",
    )
    parser.add_argument(
        "--output", "-o", type=str, required=True,
        help="Output JSON path",
    )
    parser.add_argument(
        "--model", "-m", type=str, default="sonnet",
        help="Claude model alias (default: sonnet)",
    )
    parser.add_argument(
        "--batch-size", "-b", type=int, default=20,
        help="Synsets per LLM call (default: 20)",
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
        "--verbose", "-v", action="store_true",
        help="Enable DEBUG logging",
    )
    args = parser.parse_args()

    if args.verbose:
        logging.basicConfig(level=logging.DEBUG, format="%(levelname)s: %(message)s")

    # Load flagged IDs from audit output
    audit_data = json.loads(Path(args.synset_ids).read_text())
    flagged_ids = audit_data.get("flagged_ids", audit_data)  # accept list or audit dict
    print(f"Flagged synsets: {len(flagged_ids)}")

    # Look up synset details from DB
    synsets = load_synsets_from_db(args.db, flagged_ids)
    print(f"Found in DB: {len(synsets)}")

    run_gap_fill(
        synsets,
        model=args.model,
        batch_size=args.batch_size,
        delay=args.delay,
        output_file=Path(args.output),
        resume=args.resume,
        verbose=args.verbose,
    )


if __name__ == "__main__":
    main()
