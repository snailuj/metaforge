# Audit + Gap-Fill Physical Properties — Design

**Date:** 2026-03-06
**Branch:** feat/steal-shamelessly
**Status:** Approved

## Problem

The v2 enrichment prompt produces an average of 2.4 physical properties per noun, with 72% of nouns falling below the target of 4. Physical properties are critical for cross-domain metaphor discovery (concrete → abstract mappings).

## Solution

Two new scripts that run in parallel with the main enrichment:

1. **`audit_physical_coverage.py`** — scans enrichment JSON (or live checkpoint) and flags synsets with insufficient physical properties
2. **`gap_fill_physical.py`** — targeted second pass on flagged synsets only, using a physical-only prompt

## Architecture

### audit_physical_coverage.py

- **Input:** checkpoint JSON or enrichment JSON (`--input FILE`)
- **Output:** JSON array of flagged synset IDs + summary stats (`--output FILE`)
- **Logic:** Count properties where `type == "physical"`. POS-dependent thresholds:
  - Nouns: >= 4 physical properties
  - Verbs: >= 2 physical properties
  - Adjectives: >= 2 physical properties
- **Exclusion:** `--exclude FILE` skips synset IDs already gap-filled (optional)
- **Stdout:** summary — total synsets, flagged count, percentage, breakdown by POS
- **Error handling:** If checkpoint JSON is truncated mid-write, catch `json.JSONDecodeError` and retry after 1 second (one retry only)

### gap_fill_physical.py

- **Input:** `--synset-ids FILE` (JSON array from audit) + `--db PATH` (to look up definitions)
- **Output:** enrichment-format JSON (`--output FILE`) compatible with `enrich.sh --from-json`
- **Prompt:** Physical-only — "List 4-6 physical/sensory properties for this noun." Single-word constraint.
- **Batching:** `--batch-size`, `--model`, `--delay` args matching `enrich_properties.py` conventions
- **Checkpoint:** `checkpoint_gap_fill.json` for independent resume
- **Output format:** Same `{"synsets": [...]}` shape as main enrichment. Each synset contains only physical properties.
- **RateLimitError:** breaks the batch loop (same policy as main enrichment)

### Integration

```bash
# 1. Audit checkpoint while enrichment runs
python audit_physical_coverage.py \
  --input data-pipeline/output/checkpoint_enrich.json \
  --output data-pipeline/output/flagged_physical.json

# 2. Gap-fill in parallel with main enrichment
python gap_fill_physical.py \
  --synset-ids data-pipeline/output/flagged_physical.json \
  --db data-pipeline/output/lexicon_v2.db \
  --model sonnet \
  --output data-pipeline/output/gap_fill_physical.json

# 3. Import both together after main enrichment completes
./data-pipeline/enrich.sh --db data-pipeline/output/lexicon_v2.db \
  --from-json data-pipeline/output/enrichment_8000_sonnet_v2_20260306.json \
              data-pipeline/output/gap_fill_physical.json
```

### Collision handling

`synset_properties` has a composite PRIMARY KEY `(synset_id, property_id)`. Combined with `INSERT OR IGNORE`:
- Same synset + same property text → silently ignored
- Same synset + new property text → inserted

No need to deduplicate across JSONs. No changes to `enrich.sh` or `enrich_pipeline.py`.

### Concurrency

No locking or snapshots needed. The audit script reads the checkpoint file once. Python's `json.dump` + `close` on small files is effectively atomic on Linux. Truncated reads caught via `json.JSONDecodeError` + one retry.

## Key decisions

- **Additional-only prompt** (not full re-enrichment) — simpler prompt, avoids model confusion
- **POS-dependent thresholds** — nouns need more physical properties than verbs/adjectives
- **Same output format** as main enrichment — reuses existing import pipeline unchanged
- **Independent checkpoint** — gap-fill can resume without affecting main enrichment
