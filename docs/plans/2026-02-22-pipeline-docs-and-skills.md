# Pipeline Documentation and Skills — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Create comprehensive pipeline documentation and two skills so any agent can operate the data pipeline correctly.

**Architecture:** Three deliverables — a CLAUDE.md landing page, a pipeline management skill (4 enrichment lifecycle operations), and a pipeline creation skill (build base DB from raw sources). All documentation, no code changes.

**Tech Stack:** Markdown, Claude Code skills (SKILL.md format)

---

### Task 1: Write `data-pipeline/CLAUDE.md`

**Files:**
- Modify: `data-pipeline/CLAUDE.md`

**Step 1: Write the CLAUDE.md**

Replace the existing content with the full pipeline documentation. Structure:

```markdown
# Data Pipeline

## Overview

The data pipeline builds and enriches `lexicon_v2.db` — the SQLite database backing the Metaforge API. It has two phases:

1. **Creation** — import raw linguistic data sources into a base database (rare, ~once)
2. **Management** — enrich with LLM-extracted properties, evaluate quality (ongoing)

## Data Flow

```
Raw Sources (OEWN, Brysbaert, SUBTLEX, SyntagNet, VerbNet)
    ↓ import_*.py scripts
PRE_ENRICH.sql (base DB dump: WordNet + frequencies + curated vocab)
    ↓ restore_db.sh
lexicon_v2.db (empty enrichment tables)
    ↓ enrich_properties.py (LLM → JSON)
enrichment_*.json
    ↓ enrich_pipeline.py (JSON → DB)
lexicon_v2.db (enriched: properties, similarity, centroids, snapped curated links)
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

> **Large files live in `~/.local/share/metaforge/`, NOT in the repo.** Worktrees symlink into the shared location: `data-pipeline/raw/wiki-news-300d-1M.vec`

## Key Concepts

- **Property vocabulary** (`property_vocabulary`) — normalised property texts extracted by the LLM, with FastText embeddings. Each enrichment batch adds new properties.
- **Curated vocabulary** (`property_vocab_curated`) — 35k canonical vocabulary entries built from WordNet by `build_vocab.py`. The least-polysemous lemma per synset. Independent of enrichment.
- **Snapping** (`snap_properties.py`) — maps LLM-extracted properties to curated vocabulary entries via a 3-stage cascade: exact match → morphological normalisation → embedding cosine similarity → drop.
- **Enrichment** — LLM extracts 10-15 semantic properties per synset. Stored as JSON, then imported into the DB by `enrich_pipeline.py`.
- **MRR evaluation** — queries the Go API's `/forge/suggest` endpoint against a set of known metaphor pairs. Measures how well the forge ranks known metaphorical targets.

## Operations

There are **4 primary operations**. Other scripts in this directory are internal modules called by these entrypoints — do not invoke them directly.

### 1. Run LLM Enrichment

Extract properties from an LLM for a batch of synsets. **Costs API calls.**

```bash
source .venv/bin/activate
python data-pipeline/scripts/enrich_properties.py \
  --db data-pipeline/output/lexicon_v2.db \
  --size 2000 \
  --model sonnet \
  --strategy frequency \
  --output data-pipeline/output/enrichment_NNNN_model_YYYYMMDD.json \
  -v
```

Output: JSON file in `data-pipeline/output/`.

### 2. Import Enrichment

Load an enrichment JSON into the database. Runs the full pipeline: curate properties → link to synsets → compute IDF → pairwise similarity → centroids → rebuild curated vocab → snap → antonyms. **Requires FastText vectors.**

```bash
source .venv/bin/activate
python data-pipeline/scripts/enrich_pipeline.py \
  --db data-pipeline/output/lexicon_v2.db \
  --enrichment data-pipeline/output/enrichment_NNNN_model_YYYYMMDD.json \
  --fasttext ~/.local/share/metaforge/wiki-news-300d-1M.vec
```

**To rebuild from scratch** (e.g. after discovering data corruption):
```bash
# 1. Restore clean baseline
./data-pipeline/scripts/restore_db.sh data-pipeline/output/PRE_ENRICH.sql data-pipeline/output/lexicon_v2.db

# 2. Replay each enrichment JSON in order
python data-pipeline/scripts/enrich_pipeline.py --db ... --enrichment enrichment_1.json ...
python data-pipeline/scripts/enrich_pipeline.py --db ... --enrichment enrichment_2.json ...
```

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

## Skills

- **`metaforge-pipeline-management`** — detailed workflow for the 4 operations above
- **`metaforge-pipeline-creation`** — building the base DB from raw sources (rare)

## Database Policy

- **Never commit `.db` binaries** — they are gitignored.
- **Commit SQL text dumps** for reproducibility.
- **`PRE_ENRICH.sql`** — the committed baseline. Base WordNet data + curated vocab + antonyms + empty enrichment schema. Restore from this for a clean slate.
- **`lexicon_v2.sql`** — dump of the enriched DB. Updated after successful enrichment imports.

## Environment

- Python venv lives at the worktree root. If not present: `python3 -m venv .venv && source .venv/bin/activate && pip install -r data-pipeline/requirements.txt`
- FastText vectors: symlink `data-pipeline/raw/wiki-news-300d-1M.vec` → `~/.local/share/metaforge/wiki-news-300d-1M.vec`

## Doc Freshness

**After any commit that changes pipeline scripts, CLI arguments, table schemas, or data flow, update this file and the relevant skill before committing.** Stale docs compound — keep them current.
```

**Step 2: Review and commit**

```bash
git add data-pipeline/CLAUDE.md
git commit -m "docs(pipeline): comprehensive CLAUDE.md with operations, concepts, and data sources"
```

---

### Task 2: Create `metaforge-pipeline-management` skill

**Files:**
- Create: `.claude/skills/metaforge-pipeline-management/SKILL.md`

**Step 1: Write the skill**

Use the skill-creator skill to create the skill file. Content should cover:

- Description and triggers
- Prerequisites (venv, FastText vectors, DB exists)
- The 4 operations with exact commands, expected output, and error handling
- Restore from PRE_ENRICH workflow
- Dump enriched DB as lexicon_v2.sql workflow
- Final checklist item: "If you changed any script behaviour, CLI args, table schemas, or data flow, update `data-pipeline/CLAUDE.md`"

Key details to include per operation:

**Run LLM enrichment:**
- Requires: `--output` (mandatory), `--strategy` (random or frequency), `--model`
- Output naming convention: `enrichment_NNNN_model_YYYYMMDD.json`
- Warn about API costs before running

**Import enrichment:**
- Requires: FastText vectors at `~/.local/share/metaforge/wiki-news-300d-1M.vec` or `data-pipeline/raw/wiki-news-300d-1M.vec`
- Pipeline steps: curate → link → IDF → similarity → centroids → vocab → snap → antonyms
- Verify after: check orphan count is 0 (`SELECT COUNT(*) FROM synset_properties sp LEFT JOIN property_vocabulary pv ON pv.property_id = sp.property_id WHERE pv.property_id IS NULL`)
- Never use INSERT OR REPLACE in property_vocabulary

**Re-snap properties:**
- Default threshold: 0.7
- Recreates `synset_properties_curated` table

**Evaluate MRR:**
- Starts Go API server on specified port (default 9090, use 9091+ to avoid conflicts)
- Server is started/stopped automatically by the script
- Metaphor pairs file: `data-pipeline/fixtures/metaphor_pairs_v2.json`

**Step 2: Commit**

```bash
git add .claude/skills/metaforge-pipeline-management/SKILL.md
git commit -m "feat(skills): pipeline management skill — 4 enrichment lifecycle operations"
```

---

### Task 3: Create `metaforge-pipeline-creation` skill

**Files:**
- Create: `.claude/skills/metaforge-pipeline-creation/SKILL.md`

**Step 1: Write the skill**

Use the skill-creator skill to create the skill file. Content should cover:

- Description and triggers
- Data source table (with TODO download URLs, expected paths, licensing column)
- Pre-requisites: raw data files downloaded and placed in correct locations
- Step-by-step build order:
  1. Create empty DB
  2. `import_oewn.py --source sqlunet_master.db --db lexicon_v2.db` — synsets, lemmas, relations
  3. `import_familiarity.py` — Brysbaert GPT familiarity → frequencies table
  4. `import_subtlex.py` — SUBTLEX-UK backfill → frequencies table (zipf, frequency columns)
  5. `import_syntagnet.py` — SyntagNet collocation pairs → syntagms table
  6. `import_verbnet.py` — VerbNet → vn_classes, vn_roles, vn_examples, vn_class_members
  7. `build_vocab.py --db lexicon_v2.db` — 35k curated vocabulary → property_vocab_curated
  8. `build_antonyms.py --db lexicon_v2.db` — antonym pairs → property_antonyms
  9. Create empty enrichment schema tables (enrichment, property_vocabulary, synset_properties + indexes)
  10. Dump as `PRE_ENRICH.sql`: `sqlite3 lexicon_v2.db .dump > PRE_ENRICH.sql`
- Verification: expected row counts for each table
- Note: check exact CLI args by reading each script's argparse before running — args may have changed since this skill was written

**Step 2: Commit**

```bash
git add .claude/skills/metaforge-pipeline-creation/SKILL.md
git commit -m "feat(skills): pipeline creation skill — build base DB from raw sources"
```

---

### Task 4: Commit the design doc

**Files:**
- Already written: `docs/plans/2026-02-22-pipeline-docs-and-skills-design.md`

**Step 1: Commit**

```bash
git add docs/plans/2026-02-22-pipeline-docs-and-skills-design.md
git commit -m "docs: pipeline documentation and skills design"
```
