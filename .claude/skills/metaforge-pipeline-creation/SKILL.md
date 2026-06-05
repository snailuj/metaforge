---
name: metaforge-pipeline-creation
description: >
  Build the Metaforge lexicon database from raw linguistic sources. This is a
  rare operation — use it when creating the database from scratch, reproducing
  the build for a licensing audit, or verifying data provenance. Use this skill
  when the user mentions creating the lexicon database, missing or searching for PRE_ENRICH.sql, building the base database, importing from scratch, or needs to understand where the raw data comes from.
---

# Metaforge Pipeline Creation

Builds `lexicon_v2.db` from raw linguistic data sources. This is a one-time
operation — once built, updates and enrichments are managed via the
`metaforge-pipeline-management` skill.

Optionally outputs a snapshot as `PRE_ENRICH.sql`. Use this full-text dump of lexicon_v2.db to restore the database to its post-import state before any Metaforge-specific modications.

**See also:** `data-pipeline/CLAUDE.md` for architecture overview and key concepts.

## Data Sources

| Source | Description | Expected Path | Download URL | Licence |
|--------|-------------|---------------|--------------|---------|
| OEWN (via sqlunet) | Synsets, lemmas, relations | `data-pipeline/raw/sqlunet_master.db` | TODO | TODO |
| Brysbaert GPT Familiarity | Word familiarity ratings | `data-pipeline/input/multilex-en/*.xlsx` | TODO | TODO |
| SUBTLEX-UK | Subtitle word frequencies | `data-pipeline/input/subtlex-uk/*.xlsx` | TODO | TODO |
| SyntagNet | Collocation pairs | (bundled in sqlunet) | TODO | TODO |
| VerbNet | Verb classes, roles, examples | (bundled in sqlunet) | TODO | TODO |
| FastText (wiki-news-300d) | Word embeddings (300d) | `~/.local/share/metaforge/wiki-news-300d-1M.vec` | TODO | TODO |

> **Large files live in `~/.local/share/metaforge/`, NOT in the repo.**
> Worktrees symlink into the shared location: `data-pipeline/raw/wiki-news-300d-1M.vec`

## Prerequisites

1. **Download raw data files** and place them at the expected paths above
2. **Python venv** at the worktree root:
   ```bash
   python3 -m venv .venv && source .venv/bin/activate
   pip install -r data-pipeline/requirements.txt
   ```
3. **FastText vectors** symlinked: `data-pipeline/raw/wiki-news-300d-1M.vec` → `~/.local/share/metaforge/wiki-news-300d-1M.vec`

## Build

The entire build is handled by `data-pipeline/import_raw.sh`:

```bash
source .venv/bin/activate

# Build only
./data-pipeline/import_raw.sh

# Build and dump PRE_ENRICH.sql baseline
./data-pipeline/import_raw.sh --dump
```

The script performs these steps in order:

1. Create empty DB from `data-pipeline/SCHEMA.sql`
2. Import OEWN synsets (+ lexicographer `domainid`), lemmas, relations (`import_oewn.py`)
3. Import WordNet lexicographer domains (`import_domains.py`)
4. Import SemCor sense attributes — sensekey + tagcount (`import_semcor.py`)
5. Import BNC POS-resolved frequency (`import_bnc.py`)
6. Import seed-data provenance — sources + meta (`import_provenance.py`)
7. Import SyntagNet collocations (`import_syntagnet.py`)
8. Import VerbNet classes and roles (`import_verbnet.py`)
9. Import Brysbaert GPT familiarity (`import_familiarity.py`)
10. Backfill SUBTLEX-UK frequencies (`import_subtlex.py`)
11. Build curated vocabulary — 35k entries (`build_vocab.py`)
12. Build antonym pairs from WordNet relations (`build_antonyms.py`)
13. Import Brysbaert concreteness ratings (`import_concreteness.py`)
14. Verify row counts
15. (with `--dump`) Export as `PRE_ENRICH.sql`

> **Source DB name gotcha:** the import expects `data-pipeline/raw/sqlunet_master.db`. The shared copy is `~/.local/share/metaforge/sqlunet.db`; symlink it under the expected name so `import_raw.sh` finds it:
> `ln -sfn ~/.local/share/metaforge/sqlunet.db ~/.local/share/metaforge/sqlunet_master.db`

## Verification

The script prints row counts automatically. Expected values (approximate):

| Table | Expected Count |
|-------|---------------|
| synsets | ~120,000 |
| lemmas | ~160,000 |
| relations | ~80,000 |
| frequencies | ~60,000 |
| syntagms | ~35,000 |
| vn_classes | ~400 |
| property_vocab_curated | 35,000 |
| property_antonyms | ~576 |
| domains | 45 |
| sense_attributes | 185,129 (34,767 SemCor-tagged) |
| synsets (with domainid) | 107,519 (100%) |
| bnc_frequencies | 26,980 |
| seed_sources | 10 |
| enrichment | 0 |
| property_vocabulary | 0 |
| synset_properties | 0 |

## Key Files

| File | Purpose |
|------|---------|
| `data-pipeline/SCHEMA.sql` | Canonical DDL — all CREATE TABLE + CREATE INDEX statements |
| `data-pipeline/import_raw.sh` | Build orchestrator |
| `data-pipeline/output/PRE_ENRICH.sql` | Committed baseline dump (base data + empty enrichment schema) |
| `data-pipeline/scripts/utils.py` | Shared constants including hardcoded paths for raw data files |

## Notes

- The import scripts use **hardcoded paths** from `data-pipeline/scripts/utils.py` — they do not take CLI arguments for input files. Check each script's source before running in case paths have changed.
- **If you changed any script behaviour, table schemas, or data flow, update `data-pipeline/SCHEMA.sql`, `data-pipeline/CLAUDE.md`, and this skill before committing.**
