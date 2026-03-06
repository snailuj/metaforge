"""Gap-fill physical properties for synsets flagged by coverage audit.

Takes an audit report JSON (from audit_physical_coverage.py) and runs
a targeted prompt asking the LLM to add missing physical/sensory
properties. Existing properties are shown to avoid duplication.

Usage:
    python gap_fill_physical.py --db PATH --audit report.json -o gap_fill.json [--model sonnet]
"""
import argparse
import copy
import json
import logging
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from utils import LEXICON_V2

log = logging.getLogger(__name__)

GAP_FILL_PROMPT = """You are adding missing physical and sensory properties to word senses that lack them.

Below are word senses with their EXISTING properties. Your job is to add ONLY physical/sensory
properties that are missing. Do NOT duplicate any existing property.

Physical/sensory properties describe: texture, weight, temperature, luminosity, sound, colour,
shape, size, material, smell, taste, motion.

CONSTRAINTS:
- Every property MUST be exactly one word. No hyphens, no compounds, no spaces.
- Only add properties with type "physical".
- Do NOT repeat or rephrase any existing property.
- Add 3-6 physical properties per synset — enough to ground it, not more.
- Use the same JSON format: {{"text": "...", "salience": 0.0-1.0, "type": "physical", "relation": "..."}}
- "relation" is a short phrase linking the word to the property (e.g. "rock is heavy").

{batch_items}

Output ONLY a valid JSON array (no markdown, no explanation):
[{{"id": "...", "properties": [...]}}, ...]
"""


def build_gap_fill_prompt(batch_items_text: str) -> str:
    """Build the gap-fill prompt with batch items inserted."""
    return GAP_FILL_PROMPT.replace("{batch_items}", batch_items_text)


def format_gap_fill_items(items: list[dict]) -> str:
    """Format flagged synsets for the gap-fill prompt.

    Each item includes existing properties so the LLM avoids duplicates.
    """
    lines = []
    for item in items:
        lines.append(f"ID: {item['synset_id']}")
        lines.append(f"Word: {item['lemma']}")
        lines.append(f"Definition: {item['definition']}")
        existing = ", ".join(item.get("existing_properties", []))
        lines.append(f"Existing properties: {existing}")
        lines.append("")
    return "\n".join(lines)


def merge_gap_fill(existing_data: dict, gap_fill_results: list[dict]) -> dict:
    """Merge gap-fill properties into existing enrichment data.

    Appends new properties, skipping any whose text matches an existing property.
    Returns a new dict (does not mutate existing_data).
    """
    merged = copy.deepcopy(existing_data)

    synset_map = {s["id"]: s for s in merged.get("synsets", [])}

    for entry in gap_fill_results:
        sid = entry["id"]
        if sid not in synset_map:
            log.warning("gap-fill synset %s not in existing data, skipping", sid)
            continue

        if "properties" not in synset_map[sid]:
            synset_map[sid]["properties"] = []

        existing_texts = {p["text"] for p in synset_map[sid]["properties"]
                         if isinstance(p, dict)}

        for prop in entry.get("properties", []):
            if isinstance(prop, dict) and prop.get("text") not in existing_texts:
                synset_map[sid]["properties"].append(prop)
                existing_texts.add(prop["text"])

    return merged


def main():
    parser = argparse.ArgumentParser(
        description="Gap-fill physical properties for flagged synsets.",
    )
    parser.add_argument("--db", default=str(LEXICON_V2), help="lexicon database path")
    parser.add_argument("--audit", required=True, help="path to audit report JSON")
    parser.add_argument("-o", "--output", required=True, help="output gap-fill JSON path")
    parser.add_argument("--model", default="sonnet", help="LLM model (default: sonnet)")
    parser.add_argument("--batch-size", type=int, default=20, help="synsets per LLM call")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s: %(message)s",
    )

    with open(args.audit) as f:
        audit = json.load(f)

    flagged = audit.get("flagged", [])
    if not flagged:
        print("No synsets flagged — nothing to gap-fill.")
        return

    conn = sqlite3.connect(args.db)
    try:
        items = []
        for entry in flagged:
            sid = entry["synset_id"]
            row = conn.execute(
                "SELECT s.definition FROM synsets s WHERE s.synset_id = ?", (sid,)
            ).fetchone()
            lemma_row = conn.execute(
                "SELECT lemma FROM lemmas WHERE synset_id = ? LIMIT 1", (sid,)
            ).fetchone()
            if row and lemma_row:
                existing_texts = [p["text"] for p in entry.get("properties", [])
                                  if isinstance(p, dict)]
                items.append({
                    "synset_id": sid,
                    "lemma": lemma_row[0],
                    "definition": row[0],
                    "pos": entry["pos"],
                    "existing_properties": existing_texts,
                })
    finally:
        conn.close()

    print(f"Gap-filling {len(items)} synsets in batches of {args.batch_size}...")

    # Import claude_client only when actually calling the LLM
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "lib"))
    from claude_client import prompt_json, RateLimitError

    all_results = []
    for i in range(0, len(items), args.batch_size):
        batch = items[i:i + args.batch_size]
        batch_text = format_gap_fill_items(batch)
        prompt = build_gap_fill_prompt(batch_text)

        batch_num = i // args.batch_size + 1
        log.info("[%d/%d] Processing batch of %d synsets...",
                 batch_num,
                 (len(items) + args.batch_size - 1) // args.batch_size,
                 len(batch))

        batch_num = i // args.batch_size + 1
        try:
            results = prompt_json(prompt, model=args.model, expect=list)
            all_results.extend(results)
        except RateLimitError as exc:
            log.error("Rate limited at batch %d: %s — stopping.", batch_num, exc)
            break
        except Exception as exc:
            log.error("Batch %d failed: %s", batch_num, exc)
            continue

    output = {"synsets": all_results, "source": "gap_fill", "model": args.model}
    with open(args.output, "w") as f:
        json.dump(output, f, indent=2)

    print(f"\nGap-fill complete: {len(all_results)} synsets → {args.output}")


if __name__ == "__main__":
    main()
