# PR-2 Code Review: feat/freq-fam (34 commits)

**Range:** `e6b9c04..747059c` (86 files, 34 commits)
**Reviewers:** 3 parallel agents (frontend, backend, pipeline)

## Summary

| Area | Critical | Important | Minor |
|------|----------|-----------|-------|
| Frontend | 0 | 6 | 6 |
| Backend | 0 | 3 | 4 |
| Pipeline | 2 | 5 | 5 |
| **Total** | **2** | **14** | **15** |

---

## Frontend Review

### Strengths

- Clean separation of concerns — `client.ts` handles transport, `transform.ts` maps types, `colours.ts` isolates palette, each component owns rendering
- Robust error handling in API client (`client.ts:28-31`) — gracefully handles non-JSON error bodies
- 90 tests passing across 9 files; clever 3D graph Proxy mock strategy
- Double-lookup race guard (`mf-app.ts:148`) well-tested at `mf-app.test.ts:182-207`
- Good accessibility foundations — `aria-live`, `role="region"`, `role="button"`, keyboard Enter on word chips
- Proper WebGL cleanup in `mf-force-graph.ts:158-171`
- Fluent string files byte-identical (correctly synced)

### Issues

#### Critical — None

#### Important

**I-1. Stale response race in `doLookup`**
- `mf-app.ts:185-204` — If user types "fire" then "water" quickly, the slower "fire" response can overwrite "water" results
- Fix: Track a request counter; discard responses from superseded lookups

**I-2. Autocomplete dropdown doesn't close on outside click/blur**
- `mf-search-bar.ts` — No `focusout` or click-outside handler; dropdown persists when clicking elsewhere
- Fix: Add focusout handler with `requestAnimationFrame` guard

**I-3. Missing `aria-activedescendant` for keyboard-navigated listbox**
- `mf-search-bar.ts:327-344` — Screen readers can't announce which suggestion is highlighted during arrow-key nav
- Fix: Add `id` attrs to `<li>` items, set `aria-activedescendant` on input

**I-4. `showCommon`/`showUnusual`/`showRare` are public — should be `private`**
- `mf-app.ts:113-115` — Inconsistent with all other `@state()` fields which are `private`
- Fix: Add `private` modifier

**I-5. Word chip tooltip says "Click" but interaction is double-click**
- `ui.en-GB.ftl:17` — `word-chip-title = Click to look up...` but `mf-results-panel.ts:171` uses `@dblclick`
- Fix: Change string to "Double-click" or change interaction to `@click`

**I-6. `hiddenRarities` Set causes unnecessary re-renders**
- `mf-force-graph.ts:36` — Computed getter in `mf-app.ts:119-125` creates a new `Set` every render, always failing Lit's `===` identity check
- Fix: Memoise the Set reference or use `hasChanged` option

#### Minor

- M-1: `limit` param not configurable in autocomplete component
- M-2: `auto-load` suggest mode may emit redundant lookups
- M-3: No `scrollIntoView()` during keyboard navigation of suggestions
- M-4: No tests for `auto-load`/`inline` suggest mode paths
- M-5: Hardcoded rarity colours duplicate `colours.ts` constants
- M-6: `@state()` on suggestions array — works correctly (noted, no action needed)

---

## Backend Review

### Strengths

- Clean `blobconv` extraction — textbook layer violation fix
- `Tier.String()` bounds check with tests for positive overflow and negative values
- Rarity as non-fatal enrichment (`thesaurus.go:88-92`) — broken `frequencies` table doesn't crash lookups
- Well-designed autocomplete CTE query — limits before expensive subqueries
- Null safety with `sql.NullString` throughout
- Empty-slice guarantee — JSON serialises as `[]` not `null`
- Handler limit capping at 50, minimum prefix length of 2
- `slog.Error` on 500 responses for production debugging
- Index utilisation verified for LIKE queries

### Issues

#### Critical — None

#### Important

**I-1. LIKE metacharacter injection in autocomplete prefix**
- `thesaurus.go:291` — `prefix=%` matches all 185K lemmas via `LIKE '%%'`; forces full table scan
- Fix: Escape `%` and `_` before binding, use `ESCAPE '\'` in SQL

**I-2. `frequencies` table not in startup validation**
- `handler.go:42` — `requiredTables` omits `frequencies`, but `AutocompletePrefix` will 500 if table missing
- Fix: Add to `requiredTables` or wrap the JOIN in a table-existence check

**I-3. Unchecked `json.NewEncoder(w).Encode()` return value**
- `handler.go:173,196,237` — Violates project's "All Errors/Exceptions Handled" standard
- Fix: Log the error with `slog.Error`

#### Minor

- M-1: Residual `BlobToFloats` delegation tests duplicate `blobconv_test.go`
- M-2: `interface{}` vs `any` in `thesaurus.go:218,153`
- M-3: `Rarity` field removal from `db.Synset` — compatibility note
- M-4: `embeddings.EmbeddingDim` re-export is marginal dead code

---

## Pipeline Review

### Strengths

- Excellent resource cleanup with `try/finally` in importers
- Parameterised SQL throughout — no injection risks
- No hardcoded secrets — LLM via `claude -p` CLI inheriting env auth
- Crash-safe checkpoint persistence for long-running LLM workloads
- Fixture-vocabulary guard prevents benchmark contamination
- Clean separation: `import_raw.sh` (Phase 1) vs `enrich.sh` (Phase 2)
- Good test isolation — 129 tests across 7 files using in-memory SQLite
- UK English throughout
- Shell scripts use `set -euo pipefail`

### Issues

#### Critical

**C-1. 6 exploitation tests fail due to missing `improve_prompt` mock**
- `test_evolve_prompts.py` tests 7, 8, 9, 16, 20, 21 — mock `generate_tweak` and `evaluate` but NOT `improve_prompt`
- `improve_prompt` calls `invoke_claude` for real, crashes with `AttributeError`
- Fix: Add `@patch("evolve_prompts.improve_prompt")` to each of the 6 failing tests

**C-2. SQLite connection not closed on early exception in `enrich_properties.py`**
- `enrich_properties.py:355,480` — Connection opened outside `try/finally`; leaks on exception
- Violates project's documented connection-handling discipline (MEMORY.md)
- Fix: Wrap lines 378-479 in `try/finally` with `conn.close()` in `finally`

#### Important

**I-1. `test_import_familiarity.py` depends on real database state**
- All 9 tests connect to `lexicon_v2.db` — fails if full import pipeline hasn't run
- Fix: Add unit tests with in-memory SQLite matching `test_enrich_pipeline.py` patterns

**I-2. No test file for `import_subtlex.py`**
- SUBTLEX logic only indirectly tested via integration assertions
- Fix: Create `test_import_subtlex.py` with unit tests

**I-3. `load_familiarity` hardcodes column positions via tuple unpacking**
- `import_familiarity.py:59` — Crashes with `ValueError` if spreadsheet layout changes
- Fix: Use header-based indexing like `import_subtlex.py:33-36`

**I-4. `evaluate_mrr.py` has undocumented `sqlite3` CLI dependency**
- `evaluate_mrr.py:321` — calls `subprocess.run(["sqlite3", db_path])` for baseline restore
- Fix: Document or validate the dependency at function entry

**I-5. Variable name shadowing in `evolve_prompts.py:291`**
- `improved` holds a prompt string, then gets overwritten with a boolean
- Fix: Rename to `improved_prompt` for the string value

#### Minor

- M-1: `tqdm` in `requirements.txt` but never imported
- M-2: Unused `_` in `import_familiarity.py:59` tuple unpacking
- M-3: Mixed `typing.List`/`list` style in `enrich_properties.py`
- M-4: Unnecessary `sys.path.insert` in `enrich_pipeline.py:28`
- M-5: Full FastText file loaded into memory (~2.4GB) — fine for pipeline, noted for future

---

## Overall Assessment

**Ready to merge?** With fixes.

**Blocking (must fix before merge):**
- Pipeline C-1: 6 failing tests (missing mock — quick fix)
- Pipeline C-2: Connection leak in `enrich_properties.py` (quick fix)

**Should fix before or shortly after merge:**
- Frontend I-1: Stale response race (shows wrong results to user)
- Frontend I-6: `hiddenRarities` identity churn (performance in 3D context)
- Backend I-1: LIKE metacharacter injection (semantic bypass)
- Backend I-3: Unchecked encode errors (violates project standard)

**Everything else:** Polish and robustness improvements, none blocking.
