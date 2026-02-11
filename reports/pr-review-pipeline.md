# PR Review: Data Pipeline + Docs

**Reviewer:** Code Review Agent (Data Pipeline + Docs)
**Range:** 639f366..380d9bb
**Scope:** data-pipeline/, docs/, root config

---

### Strengths

1. **Well-structured pipeline runner** (`data-pipeline/run_pipeline.sh`): The script validates all prerequisites before proceeding, supports both `--full` (LLM) and pre-computed modes, uses `set -euo pipefail` for safety, and includes a confirmation prompt before consuming API calls. Step numbering provides clear progress output. Lines 17-68 are a model of defensive shell scripting.

2. **Idempotent restore script** (`data-pipeline/scripts/restore_db.sh`): Clean, minimal, does exactly one job. Deletes existing DB before restore, verifies table count on completion. This is the right approach for the database policy.

3. **Shared utilities in `utils.py`**: All path constants and the `normalise()` function are centralised in one module (`data-pipeline/scripts/utils.py`), keeping scripts DRY. The `EMBEDDING_DIM = 300` constant prevents magic numbers.

4. **Secrets policy compliance**: `spike_property_vocab.py:168-170` correctly loads `GEMINI_API_KEY` from environment and raises on absence. `run_pipeline.sh:59-62` validates the env var before starting `--full` mode. No API keys, tokens, or secrets appear in any code, config, or data files. The SQL dump contains only lexical data.

5. **Comprehensive test coverage**: 10 test files covering every pipeline stage. `test_validation.py` provides end-to-end verification including cosine similarity sanity checks on real embeddings (lines 48-69). Tests verify data integrity at scale (e.g., 100K+ synsets, 180K+ lemmas) rather than trivially passing.

6. **Schema design** (`docs/designs/schema-v2.sql`): Well-normalised with appropriate foreign keys, CHECK constraints, and indexes. Migration notes at the bottom provide useful context. The property vocabulary design with embeddings is a clean approach for fuzzy matching.

7. **SQL dump is properly wrapped** in `BEGIN TRANSACTION` / `COMMIT` for atomic restore. At 84 MB / 1M lines, it contains 107K synsets, 185K lemmas, 5K properties, 366K similarity pairs, and 1967 centroids -- all reasonable.

8. **LLM response handling** (`spike_property_vocab.py:131-163`): Handles markdown code block stripping, validates response is a list, merges LLM output with local data, warns on unknown IDs, and gracefully degrades on parse errors by returning empty property lists rather than crashing.

---

### Issues

#### Critical (Must Fix)

**C1. `curate_properties.py` has a missing `Path` import -- script will crash on import**

- File: `data-pipeline/scripts/curate_properties.py:11`
- `Path` is used as a type annotation on `load_fasttext_vectors(vec_path: Path)` but is never imported. The file imports from `utils` but `utils.py` does not export `Path`.
- Confirmed via `python3 -c "import curate_properties"` which raises `NameError: name 'Path' is not defined`.
- This means `curate_properties.py` cannot be imported or run at all. Running `run_pipeline.sh` step 7 ("Curate properties and add FastText embeddings") will fail.
- **Impact:** Pipeline is broken for fresh rebuilds. The existing SQL dump was presumably generated before this bug was introduced (possibly during the refactor in commit `e06971c`).
- **Fix:** Add `from pathlib import Path` to the imports in `curate_properties.py`.

#### Important (Should Fix)

**I1. `numpy` is missing from `requirements.txt`**

- File: `data-pipeline/requirements.txt`
- `07_compute_property_similarity.py:16` and `08_compute_synset_centroids.py:16` both `import numpy as np`.
- `requirements.txt` lists only `pytest`, `google-genai`, `tqdm`, `tenacity` -- no `numpy`.
- **Impact:** Fresh setup following the project instructions will fail when running steps 8-10 of the pipeline.
- **Fix:** Add `numpy>=1.24.0` (or appropriate version) to `requirements.txt`.

**I2. `tqdm` and `tenacity` are listed in `requirements.txt` but never used**

- File: `data-pipeline/requirements.txt:4-5`
- No pipeline script in the current codebase imports `tqdm` or `tenacity`. They may be left over from removed v1 scripts (commit `e06971c` removed v1 scripts).
- **Impact:** Unnecessary dependencies. Not harmful but misleading for contributors.
- **Fix:** Remove `tqdm` and `tenacity` from `requirements.txt`, or add them back to scripts if they were accidentally removed during refactoring.

**I3. No error handling or resource cleanup in import scripts**

- Files: `import_oewn.py`, `import_syntagnet.py`, `import_verbnet.py`, `curate_properties.py`, `populate_synset_properties.py`
- All scripts open SQLite connections with bare `sqlite3.connect()` calls and rely on reaching `conn.close()` at the end of `main()`. If any intermediate step raises an exception, connections are leaked and partial writes may be left uncommitted.
- Example: `import_oewn.py:62-71` opens both source and destination DBs but has no try/finally or context manager.
- **Impact:** On pipeline failure, the partially written database may be left in an inconsistent state. Since the pipeline always starts from a fresh DB (`run_pipeline.sh:99` deletes existing), this is mitigated but not eliminated -- a failure mid-import could leave an unrecoverable state if the user doesn't restart from scratch.
- **Fix:** Use context managers (`with sqlite3.connect(...) as conn:`) or try/finally blocks to ensure connections are closed and transactions are rolled back on error.

**I4. `TESTING.md` does not mention Python data pipeline tests**

- File: `TESTING.md`
- The file documents Go and TypeScript test commands but omits the 10 Python test files in `data-pipeline/scripts/`.
- **Impact:** New contributors won't know how to run pipeline validation tests.
- **Fix:** Add a Python/data-pipeline section, e.g.:
  ```bash
  cd data-pipeline && python -m pytest scripts/ -v
  ```

**I5. `property_similarity` and `synset_centroids` tables not in the canonical schema**

- File: `docs/designs/schema-v2.sql`
- The `07_compute_property_similarity.py` script creates `property_similarity` via `CREATE TABLE` (line 28), and `08_compute_synset_centroids.py` creates `synset_centroids` (line 26). Both use `DROP TABLE IF EXISTS` before creation.
- These tables exist in the SQL dump (confirmed) but are NOT defined in `schema-v2.sql`, which is the canonical schema used by `run_pipeline.sh:99` to create the initial empty DB.
- **Impact:** The schema documentation is incomplete. Anyone reading `schema-v2.sql` to understand the database will miss two important tables. This also means `restore_db.sh` works (because the dump includes the `CREATE TABLE` statements), but the canonical schema file is out of sync with reality.
- **Fix:** Add `property_similarity` and `synset_centroids` table definitions to `schema-v2.sql`. Alternatively, document that these tables are created by pipeline steps 8-10 and are not part of the initial schema.

**I6. `frequencies` table is empty -- no SUBTLEX-UK import in pipeline**

- File: `data-pipeline/run_pipeline.sh` (missing step)
- The schema defines a `frequencies` table (`schema-v2.sql:41-46`) and the PRD references SUBTLEX-UK for rarity badges (`Metaforge-PRD-2.md:347`). However, the pipeline runner has no step for importing frequency data, and the SQL dump contains 0 `INSERT INTO frequencies` rows.
- The PRD correctly lists this as an open question (line 348: "SUBTLEX-UK: Needs re-downloading").
- **Impact:** Rarity badges (Common/Uncommon/Rare/Archaic) will not work in the frontend. This is acknowledged but should be explicitly documented in the pipeline script or a README.
- **Fix:** Add a comment in `run_pipeline.sh` noting that the SUBTLEX-UK frequency import is pending, or add a placeholder step that prints a warning.

#### Minor (Nice to Have)

**M1. `07_compute_property_similarity.py` stores both directions of each pair (O(2n) storage)**

- File: `data-pipeline/scripts/07_compute_property_similarity.py:89-91`
- For each similar pair (a, b), both (a, b, sim) and (b, a, sim) are inserted. This doubles the 183K unique pairs to 366K rows.
- **Impact:** Extra storage in the SQL dump (~35K lines) and slightly larger DB. The bidirectional storage simplifies queries (no need for `OR` clauses) so this is a reasonable trade-off, but it should be documented.
- **Fix:** Add a comment explaining the bidirectional storage decision, or consider a view/query helper instead.

**M2. Inconsistent test file naming convention**

- Files: `test_06_compute_property_idf.py`, `test_07_compute_property_similarity.py`, `test_08_compute_synset_centroids.py` vs. `test_curate_properties.py`, `test_import_oewn.py`, etc.
- The numbered scripts (06, 07, 08) have test files that mirror the number prefix, while earlier scripts use descriptive names. This is a minor inconsistency.
- **Impact:** Purely cosmetic. Tests are discoverable by pytest either way.

**M3. Some test files redefine `LEXICON_V2` path instead of importing from `utils.py`**

- Files: `test_curate_properties.py:7`, `test_import_oewn.py:6`, `test_import_syntagnet.py:6`, `test_import_verbnet.py:6`, `test_synset_properties.py:7`, `test_validation.py:9`
- These files define `LEXICON_V2 = Path(__file__).parent.parent / "output" / "lexicon_v2.db"` locally, while `test_06_compute_property_idf.py:8`, `test_07_compute_property_similarity.py:8`, and `test_08_compute_synset_centroids.py:10` correctly import from `utils.py`.
- **Impact:** If the DB path ever changes, six test files would need updating independently. Fragile but low risk given the path is unlikely to change.
- **Fix:** Standardise all test files to `from utils import LEXICON_V2`.

**M4. CLAUDE.md references "GloVe embeddings" but pipeline actually uses FastText**

- File: `CLAUDE.md:22` states "Data: SQLite + GloVe embeddings + Gemini-extracted properties"
- The actual pipeline uses FastText 300d embeddings (`wiki-news-300d-1M.vec`), as documented in `utils.py:18-19`, `schema-v2.sql:141`, and `Metaforge-PRD-2.md:118`.
- **Impact:** Misleading to contributors who read CLAUDE.md for orientation.
- **Fix:** Change "GloVe" to "FastText" in CLAUDE.md.

**M5. `spike_property_vocab.py` uses `SQLUNET_DB` but pipeline creates `LEXICON_V2` first**

- File: `data-pipeline/scripts/spike_property_vocab.py:26` imports `SQLUNET_DB`
- The spike script queries the raw `sqlunet_master.db` directly (tables: `synsets`, `senses`, `words`) to select pilot synsets. This is correct for the initial spike/pilot extraction phase, but creates a coupling to the raw source DB format.
- **Impact:** Minimal -- the spike script is designed to run against the source, and the pipeline runner calls it at the right point. Just worth noting for future maintainers.

---

### Recommendations

1. **Add a `data-pipeline/README.md`** (only if the team wants it -- not creating proactively per project policy) documenting: prerequisites, how to run the pipeline, how to run tests, the dependency on raw source files in `data-pipeline/raw/`, and the known gap with SUBTLEX-UK.

2. **Consider pinning dependency versions** more tightly in `requirements.txt`. `google-genai>=0.1.0` is extremely loose -- a breaking change in the Gemini SDK could silently break the LLM extraction.

3. **The 84 MB SQL dump in git** will grow with each data refresh. Consider whether `git-lfs` would be appropriate for this file, or whether the dump should be generated as a CI artifact instead of committed. This is a trade-off: the current approach ensures reproducibility without requiring raw source data, which is valuable.

4. **Add `--check` or `--dry-run` mode to `run_pipeline.sh`** that validates prerequisites without executing, for CI use.

---

### Assessment

**Ready to merge?** With fixes

**Reasoning:** The pipeline design is sound and the data quality is well-validated by tests. However, the `curate_properties.py` import bug (C1) is a confirmed crash that prevents the pipeline from running end-to-end on a fresh setup, and the missing `numpy` dependency (I1) would cause steps 8-10 to fail. These two issues must be fixed before merge. The remaining Important issues (I3-I6) are quality-of-life improvements that could be addressed in a fast-follow commit.
