---
name: metaforge-pipeline-management
description: >
  Detailed workflow for operating the Metaforge data pipeline — the 4 enrichment
  lifecycle operations. Use this skill whenever the user asks to run enrichment,
  import enrichment, rebuild the database, evaluate MRR, snap properties, or
  anything related to managing the lexicon_v2.db enrichment data. Also use when
  you see errors from pipeline scripts or need to restore the database from a
  clean baseline.
---

# Metaforge Pipeline Management

Manages the enrichment lifecycle for `lexicon_v2.db`. Four operations, plus
restore and dump workflows.

**See also:** `data-pipeline/CLAUDE.md` for architecture overview and key concepts.

## Prerequisites

Before running any operation:

1. **Python venv** — must exist at the worktree root:
   ```bash
   source .venv/bin/activate
   ```
   If missing: `python3 -m venv .venv && source .venv/bin/activate && pip install -r data-pipeline/requirements.txt`

2. **FastText vectors** — required for Import Enrichment and Re-snap:
   - Primary: `~/.local/share/metaforge/wiki-news-300d-1M.vec`
   - Symlink: `data-pipeline/raw/wiki-news-300d-1M.vec`
   - If neither exists, the pipeline will fail. Ask the user to download them.

3. **Database exists** — `data-pipeline/output/lexicon_v2.db`
   - If missing, restore from `PRE_ENRICH.sql` (see Restore workflow below)

---

## Operation 1: Run LLM Enrichment

Extract semantic properties from an LLM for a batch of synsets. **This costs API calls — warn the user before running.**

```bash
source .venv/bin/activate
python data-pipeline/scripts/enrich_properties.py \
  --size 2000 \
  --model sonnet \
  --strategy frequency \
  --output data-pipeline/output/enrichment_NNNN_model_YYYYMMDD.json \
  -v
```

**Arguments:**
- `--output` (required) — output file path. Follow naming convention: `enrichment_{size}_{model}_{YYYYMMDD}.json`
- `--size` — number of synsets to enrich (default: 2000)
- `--model` — Claude model alias: `haiku`, `sonnet`, `opus` (default: haiku)
- `--strategy` — `random` (POS-stratified) or `frequency` (by familiarity, excludes already-enriched)
- `--resume` — resume from checkpoint if interrupted
- `--synset-ids` — JSON file with specific synset IDs to enrich
- `--verbose` — debug logging for raw LLM request/response

**Output:** JSON file in `data-pipeline/output/`. Do not modify this file — it is the replayable source of truth for that enrichment batch.

**Expected duration:** ~1 min per 20 synsets (1 batch). 2000 synsets ≈ 100 batches ≈ 2-3 min.

The script reads synsets from `data-pipeline/output/lexicon_v2.db` (hardcoded default from `utils.LEXICON_V2`).

---

## Operation 2: Import Enrichment

Load an enrichment JSON into the database. Runs the full downstream pipeline:
curate properties → link to synsets → snap to curated vocab → antonyms.

```bash
source .venv/bin/activate
python data-pipeline/scripts/enrich_pipeline.py \
  --db data-pipeline/output/lexicon_v2.db \
  --enrichment data-pipeline/output/enrichment_NNNN_model_YYYYMMDD.json \
  --fasttext ~/.local/share/metaforge/wiki-news-300d-1M.vec
```

**Arguments:**
- `--db` (required) — path to lexicon DB
- `--enrichment` (required) — enrichment JSON file
- `--fasttext` — path to FastText .vec file (default: `~/.local/share/metaforge/wiki-news-300d-1M.vec`)
**Expected duration:** ~5-10 min (dominated by FastText loading and snap cascade).

**Verify after import:**
```sql
-- Check for orphaned property links (MUST be 0)
SELECT COUNT(*) FROM synset_properties sp
LEFT JOIN property_vocabulary pv ON pv.property_id = sp.property_id
WHERE pv.property_id IS NULL;
```

If orphan count > 0, the database is corrupted. Restore from `PRE_ENRICH.sql` and replay all enrichment JSONs (see Restore workflow).

**Critical:** The pipeline uses `INSERT OR IGNORE` for idempotency. Never change this to `INSERT OR REPLACE` — it deletes the existing row (and its auto-increment property_id), then inserts a new row with a new ID. All existing `synset_properties` references to the old ID become orphaned. This caused 60% data loss in a previous incident.

---

## Operation 3: Re-snap Properties

Re-run the 3-stage snap cascade without re-importing. Useful for tuning the embedding similarity threshold or after changes to the curated vocabulary.

```bash
source .venv/bin/activate
python data-pipeline/scripts/snap_properties.py \
  --db data-pipeline/output/lexicon_v2.db \
  --threshold 0.7
```

**Arguments:**
- `--db` — path to lexicon DB
- `--threshold` — embedding similarity threshold (default: 0.7)

**What it does:** Recreates the `synset_properties_curated` table by mapping each property in `synset_properties` to the nearest entry in `property_vocab_curated` via:
1. Exact text match
2. Morphological normalisation match
3. Embedding cosine similarity (above threshold)
4. Drop (no match found)

---

## Operation 4: Evaluate MRR

Start the Go API server and query it against known metaphor pairs. Measures how well the forge ranks known metaphorical targets.

```bash
source .venv/bin/activate

# Pre-built DB (eval-only, no pipeline, no API calls)
python data-pipeline/scripts/evaluate_mrr.py \
  --db data-pipeline/output/lexicon_v2.db \
  --port 9091 -v -o results.json

# Pre-computed enrichment (restore + pipeline, no API calls)
python data-pipeline/scripts/evaluate_mrr.py \
  --enrichment data-pipeline/output/enrichment_NNNN_model_YYYYMMDD.json \
  --port 9091 -v -o results.json

# Live LLM enrichment (restore + enrich + pipeline, costs API calls)
python data-pipeline/scripts/evaluate_mrr.py \
  --enrich --size 700 --model sonnet \
  --port 9091 -v -o results.json
```

**Key arguments:**
- `--db` / `--enrichment` / `--enrich` — mutually exclusive mode selectors
- `--port` — API server port (default: 9090, use 9091+ to avoid conflicts with running servers)
- `--output` — output results JSON
- `--pairs` — metaphor pairs file (default: `data-pipeline/fixtures/metaphor_pairs_v2.json`)
- `--limit` — max suggestions per query (default: 200)
- `--verbose` — debug logging

The script starts and stops the Go API server automatically. The server must be buildable: `cd api && go build ./cmd/metaforge`.

---

## Restore from PRE_ENRICH.sql (clean slate)

When the database is corrupted or you need to rebuild from scratch:

```bash
# 1. Restore clean baseline
./data-pipeline/scripts/restore_db.sh \
  data-pipeline/output/PRE_ENRICH.sql \
  data-pipeline/output/lexicon_v2.db

# 2. Replay each enrichment JSON in order
source .venv/bin/activate
python data-pipeline/scripts/enrich_pipeline.py \
  --db data-pipeline/output/lexicon_v2.db \
  --enrichment data-pipeline/output/enrichment_2000_sonnet_20260210.json \
  --fasttext ~/.local/share/metaforge/wiki-news-300d-1M.vec

python data-pipeline/scripts/enrich_pipeline.py \
  --db data-pipeline/output/lexicon_v2.db \
  --enrichment data-pipeline/output/enrichment_2000_sonnet_20260211.json \
  --fasttext ~/.local/share/metaforge/wiki-news-300d-1M.vec

# ... repeat for each enrichment JSON in chronological order
```

`PRE_ENRICH.sql` contains: base WordNet data + frequencies + curated vocabulary (35k) + antonyms (576) + empty enrichment schema tables with indexes.

**Alternative:** `enrich.sh` wraps the restore + enrich/import + pipeline + dump cycle in a single command:
```bash
# From existing JSON:
./data-pipeline/enrich.sh --db data-pipeline/output/lexicon_v2.db \
  --from-json data-pipeline/output/enrichment_NNNN_model_YYYYMMDD.json

# Full LLM enrichment:
./data-pipeline/enrich.sh --db data-pipeline/output/lexicon_v2.db \
  --enrich --size 2000 --model sonnet \
  --output data-pipeline/output/enrichment_NNNN_model_YYYYMMDD.json
```

---

## Dump Enriched DB

After a successful import, dump the enriched DB using `export.sh`:

```bash
./data-pipeline/export.sh --db data-pipeline/output/lexicon_v2.db
```

This VACUUMs the DB and dumps to `data-pipeline/output/lexicon_v2.sql` with a row-count summary.

---

## Final Checklist

After completing any pipeline operation:

- [ ] Verify orphan count is 0 (after import)
- [ ] Dump DB as `lexicon_v2.sql` if data changed
- [ ] **If you changed any script behaviour, CLI args, table schemas, or data flow, update `data-pipeline/CLAUDE.md` and this skill before committing.**
