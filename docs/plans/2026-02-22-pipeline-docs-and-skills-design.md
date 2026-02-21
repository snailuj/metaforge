# Pipeline Documentation and Skills — Design

**Date:** 2026-02-22
**Status:** Approved

## Problem

The data pipeline has no comprehensive documentation. Agents working in this directory lack context about data sources, the enrichment lifecycle, and which scripts are entrypoints vs internal modules. A recent bug (orphaned property IDs from `INSERT OR REPLACE`) went undetected across sessions because there was no shared knowledge base explaining how the pipeline fits together.

## Deliverables

### 1. `data-pipeline/CLAUDE.md` — Pipeline landing page

Overview document for any agent or human entering the data-pipeline directory.

**Sections:**
- **Architecture** — what the pipeline produces (lexicon_v2.db), two phases (creation vs management), data flow
- **Data sources** — OEWN, Brysbaert, SUBTLEX-UK, SyntagNet, VerbNet, FastText. Table with download URLs (placeholders for user to fill), expected file paths, licensing column
- **Key concepts** — property vocabulary, curated vocabulary (build_vocab), snapping (3-stage cascade: exact → morphological → embedding), enrichment (LLM-extracted properties), MRR evaluation
- **Operations** — the 4 entrypoints with example commands, plus restore from PRE_ENRICH.sql
- **Links to skills** — pointers to the two skills for detailed workflows
- **Policies** — large files policy (`~/.local/share/metaforge/`), database policy (never commit .db, dump as SQL), secrets policy
- **Doc-freshness instruction** — standing instruction: "After any commit that changes pipeline scripts, schema, or data flow, update this file and the relevant skill before committing."

### 2. Skill — `metaforge-pipeline-management`

Covers the enrichment lifecycle — the 4 operations an agent should invoke on a built database.

**Triggers:** "run enrichment", "import enrichment", "rebuild database", "evaluate MRR", "snap properties"

| Operation | Script | Notes |
|-----------|--------|-------|
| Run LLM enrichment | `enrich_properties.py` | Outputs JSON. Costs API calls. |
| Import enrichment | `enrich_pipeline.py` | JSON → DB. Bundles curate + link + IDF + similarity + centroids + vocab + snap + antonyms. Requires FastText vectors. |
| Re-snap properties | `snap_properties.py` | Standalone re-snap for threshold tuning or vocab changes. |
| Evaluate MRR | `evaluate_mrr.py` | Starts Go API, queries forge, reports MRR. |

**Also covers:**
- Restore from `PRE_ENRICH.sql` (clean slate)
- Dump enriched DB as `lexicon_v2.sql` after successful import
- Doc-update reminder as final checklist item

**Does NOT cover:** creating the base DB from raw sources.

### 3. Skill — `metaforge-pipeline-creation`

Covers building the base database from raw sources — a rare operation, but documented for reproducibility and licensing audits.

**Triggers:** "create lexicon database", "build base database", "import from scratch"

**Steps in order:**
1. Download/locate raw data sources (with URLs + expected paths)
2. Create empty DB
3. `import_oewn.py` — synsets, lemmas, relations from sqlunet_master.db
4. `import_familiarity.py` — Brysbaert GPT familiarity
5. `import_subtlex.py` — SUBTLEX-UK backfill
6. `import_syntagnet.py` — collocation pairs
7. `import_verbnet.py` — classes, roles, examples
8. `build_vocab.py` — 35k curated vocabulary from WordNet
9. `build_antonyms.py` — antonym pairs from WordNet relations
10. Create empty enrichment schema tables + indexes
11. Dump as `PRE_ENRICH.sql`

**Includes:** data source table with download URLs (placeholders), expected paths, licensing column.

## Design decisions

- **4 entrypoints, not N scripts** — other scripts (build_vocab, snap_properties, build_antonyms, etc.) are internal to the pipeline. They can be run standalone but are not promoted as primary operations. Future refactoring may move them to underscore-prefixed modules or a `__main__.py` package.
- **Doc freshness via convention** — CLAUDE.md instruction + skill checklist item, not CI or hooks. Low-friction, works today. Revisit if staleness recurs.
- **PRE_ENRICH.sql as the reset point** — the committed baseline for rebuilding. Contains base WordNet data + curated vocabulary + antonyms + empty enrichment schema with indexes. No enrichment-derived data.
