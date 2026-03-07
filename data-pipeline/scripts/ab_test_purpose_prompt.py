"""A/B test: purpose-framed prompt vs baseline v2 prompt.

Runs the same 100 synsets through a modified prompt that explains
the metaphor engine use case, then compares property distributions.

Usage:
    python ab_test_purpose_prompt.py --db lexicon_v2.db --synset-ids ids.json \
      --baseline checkpoint_enrich.json --output ab_results.json
"""

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

from enrich_properties import (
    extract_batch,
    format_batch_items_v2,
    get_frequency_ranked_synsets,
    load_checkpoint,
    save_checkpoint,
    BATCH_PROMPT_V2,
)

OUTPUT_DIR = Path(__file__).parent.parent / "output"

# Purpose-framed v2 prompt — identical structure, added context
PURPOSE_PROMPT_V2 = """You are extracting sensory and behavioural properties for specific word senses, with salience weights and metadata.

These properties power a metaphor discovery engine that finds cross-domain conceptual links between unrelated words. For example, "anger" connects to "fire" via shared properties like "destructive", "consuming", "intense". Prioritise properties that could bridge between concepts from different domains — the more transferable and evocative a property, the more valuable it is.

CRITICAL: The definition tells you WHICH sense of the word to analyse. Many words have multiple meanings — focus ONLY on the sense described in the definition.

For each word sense, provide:

1. **usage_example**: A natural sentence using the word in this specific sense.

2. **properties**: 10-15 properties, each as a JSON object:
   - "text": 1-2 word property (short, evocative)
   - "salience": 0.0-1.0 — how immediately/strongly this property comes to mind for this concept
     - 0.9-1.0: Defining, inescapable (fire → hot, ice → cold)
     - 0.6-0.8: Strong association (fire → dangerous, ice → slippery)
     - 0.3-0.5: Secondary/contextual (fire → ancient, ice → seasonal)
   - "type": one of "physical", "behaviour", "effect", "functional", "emotional", "social"
   - "relation": short phrase linking word to property (e.g. "fire emits heat")

   Property types:
   - physical: texture, weight, temperature, luminosity, sound, colour. Physical properties are the primary bridge for cross-domain metaphors (concrete → abstract).
   - behaviour: speed, rhythm, intensity, duration, pattern of movement
   - effect: what it causes, its consequences, its aftermath
   - functional: what it does, enables, or is used for
   - emotional: feelings it evokes or is associated with
   - social: cultural, relational, or status associations

3. **lemma_metadata**: For EACH listed lemma, provide:
   - "lemma": the word form
   - "register": "formal", "neutral", "informal", or "slang"
   - "connotation": "positive", "neutral", or "negative"

Example:

Word: candle
Lemmas: candle, taper
Definition: stick of wax with a wick; gives light when burning

{{"id": "oewn-candle-n", "usage_example": "She lit a candle and watched the flame flicker in the draught.", "properties": [{{"text": "warm", "salience": 0.9, "type": "physical", "relation": "candle emits warmth"}}, {{"text": "flickering", "salience": 0.85, "type": "behaviour", "relation": "flame flickers"}}, {{"text": "ephemeral", "salience": 0.7, "type": "effect", "relation": "candle burns away"}}, {{"text": "luminous", "salience": 0.8, "type": "physical", "relation": "candle gives light"}}, {{"text": "waxy", "salience": 0.75, "type": "physical", "relation": "made of wax"}}, {{"text": "fragile", "salience": 0.6, "type": "physical", "relation": "wick is delicate"}}, {{"text": "aromatic", "salience": 0.5, "type": "effect", "relation": "scented candles smell"}}, {{"text": "ceremonial", "salience": 0.4, "type": "social", "relation": "used in rituals"}}, {{"text": "intimate", "salience": 0.65, "type": "emotional", "relation": "evokes closeness"}}, {{"text": "ancient", "salience": 0.3, "type": "social", "relation": "pre-electric lighting"}}], "lemma_metadata": [{{"lemma": "candle", "register": "neutral", "connotation": "positive"}}, {{"lemma": "taper", "register": "formal", "connotation": "neutral"}}]}}

Now extract properties for each of these word senses:

{batch_items}

Output ONLY a valid JSON array (no markdown, no explanation):
[{{"id": "...", "usage_example": "...", "properties": [...], "lemma_metadata": [...]}}, ...]
"""


def analyse_properties(synsets: list[dict]) -> dict:
    """Compute property distribution stats for a set of synsets."""
    type_counts = Counter()
    all_props = []
    physical_per_synset = []
    unique_props = set()

    for s in synsets:
        props = s.get("properties", [])
        phys_count = 0
        for p in props:
            text = p["text"] if isinstance(p, dict) else p
            ptype = p.get("type", "unknown") if isinstance(p, dict) else "unknown"
            type_counts[ptype] += 1
            all_props.append(text)
            unique_props.add(text)
            if ptype == "physical":
                phys_count += 1
        physical_per_synset.append(phys_count)

    total = len(all_props)
    return {
        "total_properties": total,
        "unique_properties": len(unique_props),
        "uniqueness_ratio": round(len(unique_props) / total, 3) if total else 0,
        "avg_per_synset": round(total / len(synsets), 2) if synsets else 0,
        "avg_physical_per_synset": round(
            sum(physical_per_synset) / len(physical_per_synset), 2
        ) if physical_per_synset else 0,
        "type_distribution": {
            k: {"count": v, "pct": round(v / total * 100, 1)}
            for k, v in sorted(type_counts.items(), key=lambda x: -x[1])
        },
        "top_20_properties": dict(Counter(all_props).most_common(20)),
    }


def main():
    parser = argparse.ArgumentParser(description="A/B test purpose-framed prompt")
    parser.add_argument("--db", required=True, help="Path to lexicon_v2.db")
    parser.add_argument("--synset-ids", required=True, help="JSON array of synset IDs")
    parser.add_argument("--baseline", required=True, help="Checkpoint/enrichment JSON with baseline results")
    parser.add_argument("--output", "-o", required=True, help="Output comparison JSON")
    parser.add_argument("--model", default="sonnet", help="Model alias (default: sonnet)")
    parser.add_argument("--batch-size", type=int, default=20, help="Batch size (default: 20)")
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()

    # Load synset IDs
    synset_ids = json.loads(Path(args.synset_ids).read_text())
    print(f"A/B test: {len(synset_ids)} synsets")

    # Load baseline results
    baseline_data = json.loads(Path(args.baseline).read_text())
    baseline_synsets = baseline_data.get("synsets") or baseline_data.get("results") or []
    baseline_by_id = {s["id"]: s for s in baseline_synsets}
    baseline_100 = [baseline_by_id[sid] for sid in synset_ids if sid in baseline_by_id]
    print(f"Baseline: {len(baseline_100)} synsets matched")

    # Look up synsets from DB for the purpose-framed run
    import sqlite3
    conn = sqlite3.connect(args.db)
    placeholders = ",".join("?" for _ in synset_ids)
    cursor = conn.execute(f"""
        WITH ranked_lemmas AS (
            SELECT s.synset_id, s.definition, s.pos, l.lemma,
                GROUP_CONCAT(l2.lemma) AS all_lemmas,
                ROW_NUMBER() OVER (
                    PARTITION BY s.synset_id
                    ORDER BY COALESCE(f.familiarity, 0) DESC, l.lemma
                ) AS rn
            FROM synsets s
            JOIN lemmas l ON l.synset_id = s.synset_id
            JOIN lemmas l2 ON l2.synset_id = s.synset_id
            LEFT JOIN frequencies f ON f.lemma = l.lemma
            WHERE s.synset_id IN ({placeholders})
            GROUP BY s.synset_id, l.lemma
        )
        SELECT synset_id, definition, lemma, pos, all_lemmas
        FROM ranked_lemmas WHERE rn = 1
    """, synset_ids)
    db_synsets = [
        {"id": str(r[0]), "definition": r[1], "lemma": r[2], "pos": r[3],
         "all_lemmas": list(set(r[4].split(",")))}
        for r in cursor.fetchall()
    ]
    conn.close()
    print(f"DB lookup: {len(db_synsets)} synsets")

    # Run purpose-framed enrichment
    checkpoint_path = OUTPUT_DIR / "checkpoint_ab_test.json"
    if checkpoint_path.exists():
        state = json.loads(checkpoint_path.read_text())
        completed_ids = set(state["completed_ids"])
        # Unified format uses 'synsets', legacy uses 'results'
        results = state.get("synsets") or state.get("results") or []
        print(f"Resuming: {len(completed_ids)} already done")
    else:
        completed_ids = set()
        results = []

    remaining = [s for s in db_synsets if s["id"] not in completed_ids]
    num_batches = (len(remaining) + args.batch_size - 1) // args.batch_size

    for batch_idx in range(num_batches):
        start = batch_idx * args.batch_size
        end = min(start + args.batch_size, len(remaining))
        batch = remaining[start:end]
        print(f"  Batch {batch_idx + 1}/{num_batches}...")

        try:
            batch_results = extract_batch(
                batch, model=args.model,
                prompt_template=PURPOSE_PROMPT_V2,
                formatter=format_batch_items_v2,
                verbose=args.verbose,
            )
            for r in batch_results:
                results.append(r)
                completed_ids.add(r["id"])
                print(f"    {r.get('lemma', '?')}: {len(r.get('properties', []))} props")

            save_checkpoint(checkpoint_path, {
                "completed_ids": list(completed_ids),
                "synsets": results,
            })
        except Exception as e:
            print(f"  BATCH FAILED: {e}")

    # Compare
    print(f"\n{'='*60}")
    print(f"COMPARISON: {len(baseline_100)} baseline vs {len(results)} purpose-framed")
    print(f"{'='*60}")

    baseline_stats = analyse_properties(baseline_100)
    purpose_stats = analyse_properties(results)

    for label, stats in [("BASELINE (v2)", baseline_stats), ("PURPOSE-FRAMED", purpose_stats)]:
        print(f"\n--- {label} ---")
        print(f"  Total properties: {stats['total_properties']}")
        print(f"  Unique properties: {stats['unique_properties']}")
        print(f"  Uniqueness ratio: {stats['uniqueness_ratio']}")
        print(f"  Avg per synset: {stats['avg_per_synset']}")
        print(f"  Avg physical/synset: {stats['avg_physical_per_synset']}")
        print(f"  Type distribution:")
        for t, d in stats["type_distribution"].items():
            print(f"    {t}: {d['count']} ({d['pct']}%)")

    # Compute deltas
    deltas = {
        "uniqueness_ratio": round(purpose_stats["uniqueness_ratio"] - baseline_stats["uniqueness_ratio"], 3),
        "avg_physical_per_synset": round(
            purpose_stats["avg_physical_per_synset"] - baseline_stats["avg_physical_per_synset"], 2
        ),
        "unique_properties": purpose_stats["unique_properties"] - baseline_stats["unique_properties"],
    }
    print(f"\n--- DELTAS (purpose - baseline) ---")
    for k, v in deltas.items():
        sign = "+" if v > 0 else ""
        print(f"  {k}: {sign}{v}")

    # Save full comparison
    output = {
        "baseline": baseline_stats,
        "purpose_framed": purpose_stats,
        "deltas": deltas,
        "synset_count": len(synset_ids),
    }
    Path(args.output).write_text(json.dumps(output, indent=2))
    print(f"\nSaved to {args.output}")

    # Clean up checkpoint
    if checkpoint_path.exists():
        checkpoint_path.unlink()


if __name__ == "__main__":
    main()
