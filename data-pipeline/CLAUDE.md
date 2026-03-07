# Data Pipeline

## Overview

The data pipeline builds and enriches `lexicon_v2.db` — the SQLite database backing the Metaforge API. It has two phases:

1. **Creation** — import raw linguistic data sources into a base database (rare, ~once)
2. **Management** — enrich with LLM-extracted properties, evaluate quality (ongoing)

## Data Flow

```
Raw Sources (OEWN, Brysbaert, SUBTLEX, SyntagNet, VerbNet)
    ↓ import_raw.sh (SCHEMA.sql + import_*.py + build_*.py)
PRE_ENRICH.sql (base DB dump: WordNet + frequencies + curated vocab)
    ↓ restore_db.sh
lexicon_v2.db (empty enrichment tables)
    ↓ enrich.sh DB --enrich TO_JSON (LLM → JSON)
enrichment_*.json (full enrichment from LLM)
    ↓ enrich.sh DB --from-json [JSON1, JSON2, ...] (JSON → DB)
lexicon_v2.db (enriched: properties, snapped curated links)
    ↓ evaluate_mrr.py
MRR score + results JSON
```

## Data Sources

| Source | Description | Expected Path | Download URL | Licence |
|--------|-------------|---------------|--------------|---------|
| OEWN (via sqlunet) | Synsets, lemmas, relations | `data-pipeline/raw/sqlunet_master.db` | TODO | TODO |
| Brysbaert GPT Familiarity | Word familiarity ratings | `data-pipeline/input/multilex-en/*.xlsx` | TODO | TODO |
| SUBTLEX-UK | Subtitle word frequencies | `data-pipeline/input/subtlex-uk/*.xlsx` | TODO | TODO |
| SyntagNet | Collocation pairs | (bundled in sqlunet) | TODO | TODO |
| VerbNet | Verb classes, roles, examples | (bundled in sqlunet) | TODO | TODO |
| FastText (wiki-news-300d) | Word embeddings (300d) | `~/.local/share/metaforge/wiki-news-300d-1M.vec` | TODO | TODO |
| Brysbaert Concreteness | Concreteness ratings (1-5) for 37k lemmas | `data-pipeline/input/brysbaert-concreteness/` | [GitHub](https://github.com/ArtsEngine/concreteness) | CC-BY |

> **Large files live in `~/.local/share/metaforge/`, NOT in the repo.** Worktrees symlink into the shared location: `data-pipeline/raw/wiki-news-300d-1M.vec`

## Key Concepts

- **Property vocabulary** (`property_vocabulary`) — normalised property texts extracted by the LLM, with FastText embeddings. Each enrichment batch adds new properties.
- **Curated vocabulary** (`property_vocab_curated`) — 35k canonical vocabulary entries built from WordNet by `build_vocab.py`. The least-polysemous lemma per synset. Independent of enrichment.
- **Snapping** (`snap_properties.py`) — maps LLM-extracted properties to curated vocabulary entries via a 3-stage cascade: exact match → morphological normalisation → embedding cosine similarity → drop.
- **Enrichment** — LLM extracts 10-15 semantic properties per synset. Stored as JSON, then imported into the DB by `enrich_pipeline.py`.
- **Concreteness regression** (`predict_concreteness.py`) — trains Ridge/SVR/k-NN/Random Forest regressors on Brysbaert concreteness scores + FastText 300d embeddings. The winning model fills concreteness scores for unrated synsets (target: 80%+ coverage). Reversible via `evals.sh revert`.
- **MRR evaluation** — queries the Go API's `/forge/suggest` endpoint against a set of known metaphor pairs. Measures how well the forge ranks known metaphorical targets.

## Operations

There are **4 primary operations**. Other scripts in this directory are internal modules called by these entrypoints — do not invoke them directly.

### 1. Run LLM Enrichment

Extract properties from an LLM for a batch of synsets. **Costs API calls.**

```bash
./data-pipeline/enrich.sh --db data-pipeline/output/lexicon_v2.db \
  --enrich --size 2000 --model sonnet --strategy frequency \
  --output data-pipeline/output/enrichment_2000_sonnet_YYYYMMDD.json
```

Run `./data-pipeline/enrich.sh --help` for full argument reference (includes `--resume`, `--verbose`, `--schema-version`, etc.).

Output: JSON file in `data-pipeline/output/`.

### 2. Import Enrichment

Load one or more enrichment JSONs into the database. Restores from `PRE_ENRICH.sql` (which includes Brysbaert concreteness ground truth), runs the full pipeline (curate → link → snap → antonyms → concreteness fill), and dumps the result. The output DB is API-ready.

```bash
./data-pipeline/enrich.sh --db data-pipeline/output/lexicon_v2.db \
  --from-json data-pipeline/output/enrichment_*.json
```

**To rebuild from scratch** (e.g. after discovering data corruption), use the same command — `enrich.sh --from-json` restores from `PRE_ENRICH.sql` automatically.

**Critical:** The pipeline uses `INSERT OR IGNORE` for idempotency. Never change this to `INSERT OR REPLACE` — it breaks property_id foreign keys and causes silent data loss.

### 3. Re-snap Properties (standalone)

Re-run the 3-stage snap cascade without re-importing. Useful for tuning the embedding threshold or after changing the curated vocabulary.

```bash
source .venv/bin/activate
python data-pipeline/scripts/snap_properties.py \
  --db data-pipeline/output/lexicon_v2.db \
  --threshold 0.7
```

### 4. Evaluate MRR

Start the Go API server and query it against known metaphor pairs.

```bash
source .venv/bin/activate

# Pre-built DB (eval-only, no pipeline, no API calls)
python data-pipeline/scripts/evaluate_mrr.py --db data-pipeline/output/lexicon_v2.db --port 9091 -v -o results.json

# Pre-computed enrichment (restore + pipeline, no API calls)
python data-pipeline/scripts/evaluate_mrr.py --enrichment FILE --port 9091 -v -o results.json

# Live LLM enrichment (restore + enrich + pipeline, costs API calls)
python data-pipeline/scripts/evaluate_mrr.py --enrich --size 700 --model sonnet --port 9091 -v -o results.json
```

### 5. Concreteness Regression

Predict concreteness scores for unrated synsets using FastText embeddings + scikit-learn regression. Three side-effect-free subcommands:

```bash
# Evaluate 4 models — writes JSON only, never touches the DB
./data-pipeline/evals.sh shootout -o data-pipeline/output/concreteness_shootout.json

# Fill gaps with the winning model — writes predictions to DB
./data-pipeline/evals.sh fill --shootout data-pipeline/output/concreteness_shootout.json

# Revert to Brysbaert-only state — deletes all regression predictions
./data-pipeline/evals.sh revert
```

Run `./data-pipeline/evals.sh --help` for full argument reference.

### 6. Audit Physical Coverage

Scan enrichment JSON (or live checkpoint) for synsets with insufficient physical properties. POS-dependent thresholds: nouns >= 4, verbs >= 2, adjectives >= 2.

```bash
source .venv/bin/activate

# Audit a completed enrichment JSON
python data-pipeline/scripts/audit_physical_coverage.py \
  --input data-pipeline/output/enrichment_8000_sonnet_v2_20260306.json \
  --output data-pipeline/output/flagged_physical.json

# Audit the live checkpoint (while enrichment is still running)
python data-pipeline/scripts/audit_physical_coverage.py \
  --input data-pipeline/output/checkpoint_enrich.json \
  --output data-pipeline/output/flagged_physical.json

# Exclude already gap-filled synsets on re-audit
python data-pipeline/scripts/audit_physical_coverage.py \
  --input data-pipeline/output/checkpoint_enrich.json \
  --exclude data-pipeline/output/gap_fill_physical.json \
  --output data-pipeline/output/flagged_physical.json
```

### 7. Gap-Fill Physical Properties

Targeted second-pass enrichment for flagged synsets. Calls the LLM with a physical-only prompt. Output is enrichment-format JSON compatible with `enrich.sh --from-json`.

```bash
source .venv/bin/activate

python data-pipeline/scripts/gap_fill_physical.py \
  --synset-ids data-pipeline/output/flagged_physical.json \
  --db data-pipeline/output/lexicon_v2.db \
  --model sonnet \
  --output data-pipeline/output/gap_fill_physical.json

# Resume from checkpoint after interruption
python data-pipeline/scripts/gap_fill_physical.py \
  --synset-ids data-pipeline/output/flagged_physical.json \
  --db data-pipeline/output/lexicon_v2.db \
  --model sonnet \
  --output data-pipeline/output/gap_fill_physical.json \
  --resume
```

Import both enrichment and gap-fill together:

```bash
./data-pipeline/enrich.sh --db data-pipeline/output/lexicon_v2.db \
  --from-json data-pipeline/output/enrichment_8000.json \
              data-pipeline/output/gap_fill_physical.json
```

`INSERT OR IGNORE` deduplicates — no collision between main enrichment and gap-fill properties.

## Skills

- **`metaforge-pipeline-management`** — detailed workflow for the 4 operations above
- **`metaforge-pipeline-creation`** — building the base DB from raw sources (rare)

## Shell Scripts

| Script | Purpose |
|--------|---------|
| `import_raw.sh` | Build base DB from raw sources, optionally dump `PRE_ENRICH.sql` |
| `enrich.sh` | Restore from `PRE_ENRICH.sql` + run enrichment + pipeline + dump `lexicon_v2.sql` |
| `export.sh` | VACUUM + dump enriched DB as `lexicon_v2.sql` |
| `scripts/restore_db.sh` | Restore any SQL dump into a fresh DB |
| `evolve_trials.sh` | Crash-recovery wrapper for evolutionary prompt optimisation |
| `evals.sh` | Concreteness regression: shootout / fill / revert |

## Database Policy

- **Never commit `.db` binaries** — they are gitignored.
- **Commit SQL text dumps** for reproducibility.
- **`SCHEMA.sql`** — canonical DDL for all tables and indexes. Used by `import_raw.sh` to create an empty database.
- **`PRE_ENRICH.sql`** — the committed baseline. Base WordNet data + curated vocab + antonyms + empty enrichment schema. Restore from this for a clean slate.
- **`lexicon_v2.sql`** — dump of the enriched DB. Updated after successful enrichment imports (via `export.sh`).

## Environment

- Python venv lives at the worktree root. If not present: `python3 -m venv .venv && source .venv/bin/activate && pip install -r data-pipeline/requirements.txt`
- FastText vectors: symlink `data-pipeline/raw/wiki-news-300d-1M.vec` → `~/.local/share/metaforge/wiki-news-300d-1M.vec`

## Doc Freshness

**After any commit that changes pipeline scripts, CLI arguments, table schemas, or data flow, update this file and the relevant skill before committing.** Stale docs compound — keep them current.
