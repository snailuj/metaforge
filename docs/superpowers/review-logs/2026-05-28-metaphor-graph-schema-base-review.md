# Code Review Loop — metaphor-graph/schema-base

**Started:** 2026-05-28T12:00:00Z
**Branch:** `metaphor-graph/schema-base`
**Base:** `main` (split point: 58799d7c — implementation plan)
**Scope:** `main..HEAD` — 13 commits, 3 files modified (~1173 lines initially; +fixes since).

**Files in scope:**
- `data-pipeline/scripts/metaphor_graph.py`
- `data-pipeline/scripts/test_metaphor_graph.py`
- `data-pipeline/SCHEMA.sql`

**Reviewers configured:** pr-review-toolkit, superpowers, standards. (ux-designer skipped — backend SQL/Python only.)

**Operator triage policy (this loop):**
- `critical` + `important` → fix
- `low` + `cosmetic` → auto-defer to the ledger without per-deferral challenger dispatch. Standard scope_boundary = "review-loop operator policy for the schema-base branch: low/cosmetic findings deferred to a future polish pass to keep this loop fast."

---

## Deferrals Ledger

| id | round | reviewer | severity | title | file | scope_boundary | proposed_followup | status |
|---|---|---|---|---|---|---|---|---|
| L01 | 1 | pr-review-toolkit:code-reviewer | low | record_judgment lacks idempotency (asymmetric to insert_bridge) | metaphor_graph.py:283-313 | operator policy | future polish pass; consider record_or_update_judgment if eyeballer needs verdict-changes | active |
| L02 | 1 | silent-failure-hunter | low | `_get_lemmatiser` catches only `LookupError` from `nltk.data.find` (OSError/RuntimeError pass through) | metaphor_graph.py:35-45 | operator policy; partially mitigated by fix 2 | tighten exception scope if production env has permission issues | active |
| L03 | 1 | silent-failure-hunter / type-design / superpowers / standards | low | insert_bridge race: SELECT outside `with conn:` can lose to UNIQUE on concurrent writer | metaphor_graph.py:155-183 | operator policy; single-writer pipeline keeps this dormant | wrap with `INSERT OR IGNORE … RETURNING bridge_id` if multi-writer ever lands | active |
| L04 | 1 | silent-failure-hunter | low | apply_schema / apply_graph_view have no try/except around executescript | metaphor_graph.py:100-109, 374-386 | operator policy; SQLite DDL is atomic-per-statement | add structured error path when batch DDL writes get more complex | active |
| L05 | 1 | silent-failure-hunter / standards | cosmetic | Test `test_raises_on_snap_failure` double-inserts heat-n-1 / dead fixture noise | test_metaphor_graph.py:388-405 | operator policy | clean fixture in next polish pass | active |
| L06 | 1 | silent-failure-hunter | low | compute_path_hash accepts non-string entries; fails with cryptic TypeError from `"|".join` | metaphor_graph.py:112-124 | operator policy | typed validation + actionable message | active |
| L07 | 1 | type-design / superpowers | low | `path: list[str]` not validated against `synsets` table — invalid IDs surface as FK IntegrityError at INSERT time | metaphor_graph.py:127-183 | operator policy | add IN-query pre-validation OR NewType-based SynsetId discipline | active |
| L08 | 1 | type-design | low | BridgeSnapFailure carries only `repr(failures)` — loses (index, raw) positional info + partial-snapped successes | metaphor_graph.py:230-232, 264-267 | operator policy | promote to structured attrs (failures: list[tuple[int,str]], partial_snapped: list[str]) when LLM proposer pipeline is wired up | active |
| L09 | 1 | type-design | low | snap_concept_string conflates "concept not in vocab" with "empty/whitespace input" — both return None | metaphor_graph.py:199-200 | operator policy; partially mitigated by fix 3 (missing-table now raises) | distinguish empty-input ValueError from miss-None in next polish pass | active |
| L10 | 1 | type-design | low | metaphor_bridges schema allows topic == vehicle — self-metaphors representable | metaphor_graph.py:49-62 + SCHEMA.sql | operator policy; spec doesn't explicitly forbid | confirm with spec author whether `CHECK (topic_synset_id != vehicle_synset_id)` should land | active |
| L11 | 1 | type-design | low | metaphor_judgments.confidence has no range CHECK (convention is 0..1) | metaphor_graph.py:88 + SCHEMA.sql | operator policy | add `CHECK (confidence IS NULL OR (confidence >= 0.0 AND confidence <= 1.0))` in next polish pass | active |
| L12 | 1 | type-design | cosmetic | BridgeSnapFailure(ValueError) base; consider EmptyPathError sibling so callers can `except BridgeSnapFailure` cleanly | metaphor_graph.py:112-124, 230-232 | operator policy | narrow exception hierarchy when proposer pipeline starts catching specifically | active |
| L13 | 1 | type-design | cosmetic | graph_edges relation column is hardcoded across 4 UNION arms — no centralised enum, future typos pass silently | metaphor_graph.py:328-371 + SCHEMA.sql | operator policy | module-level `RELATION_TYPES` frozenset + test asserting `SELECT DISTINCT relation FROM graph_edges` ⊆ enum | active |
| L14 | 1 | superpowers | low | snap_concept_string lazy nltk download is undocumented for air-gapped envs (operator surprise on first miss) | metaphor_graph.py:32-45 | operator policy | one-line module-level note + pre-download hint in docs | active |
| L15 | 1 | superpowers | low | insert_bridge accepts empty `proposer` / `proposed_at` (TEXT NOT NULL admits ''); endpoints-in-path not blocked | metaphor_graph.py:127-183 | operator policy | cheap input validation in next polish pass | active |
| L16 | 1 | superpowers | low | graph_edges has_property arm relies on implicit INNER JOIN filtering of orphan `vocab_id` rows — uncommented invariant | metaphor_graph.py:329-336 + SCHEMA.sql | operator policy | one-line comment in the view DDL OR debug-level orphan sanity check | active |
| L17 | 1 | superpowers | cosmetic | Test fixtures define `property_vocab_curated` schema inline (drift risk vs SCHEMA.sql canonical) | test_metaphor_graph.py:21-37, 508-515 | operator policy | factor a shared fixtures module OR load filtered SCHEMA.sql sections | active |
| L18 | 1 | standards | cosmetic | apply_schema lacks `log.info` line that apply_graph_view has (asymmetry) | metaphor_graph.py:100-109 | operator policy; partially mitigated by fix 1 (apply_schema log line added) | already addressed, may close in round 2 | active |

**Note on per-deferral challenger gate:** Per operator policy for this loop, low/cosmetic auto-defers do NOT pass through the deferral-challenger subagent. This is a deliberate concession to keep the loop fast for the schema-base milestone; the deferrals carry "operator policy" as their scope_boundary and "fast-track schema-base" as the implicit deferral rationale. The skill's standard gate (every defer-out-of-scope requires `accept_defer` from a challenger) is overridden by the operator for this specific loop.

---

## Round 1 — pr-review-toolkit (2026-05-28T13:00:00Z)

**Agents dispatched:** code-reviewer, silent-failure-hunter, type-design-analyzer (parallel within adapter).

### Items Found

**code-reviewer (3):**
- [important] **snap_concept_string lacks suffix-stripping parity with snap_properties.py** (`metaphor_graph.py:213-227`) — docstring claims cascade parity but skips the `-ing`/`-ed`/`-ly` variants from snap_properties.py:172-186.
  - Decision: **fix** (#5 in fix prompt)
- [important] **apply_schema does not enable PRAGMA foreign_keys=ON** (`metaphor_graph.py:100-109`) — SQLite defaults FK OFF per-connection.
  - Decision: **fix** (#1 in fix prompt)
- [low] **record_judgment asymmetric idempotency** — Decision: **defer L01**

**silent-failure-hunter (9):**
- [important] **`nltk.download` returns False on failure** (`metaphor_graph.py:39-43`) — try/except never fires; corpus missing surfaces at lemmatize time. Decision: **fix** (#2)
- [low] **`_get_lemmatiser` narrow exception scope** — Decision: **defer L02**
- [important] **`with conn:` atomicity false under `isolation_level=None`** (`metaphor_graph.py:166, 302`) — autocommit makes the context manager a no-op. Decision: **fix** (#6)
- [important] **snap_concept_string raises bare OperationalError when curated vocab table missing** (`metaphor_graph.py:206-209`). Decision: **fix** (#3)
- [important] **snap miss logged at DEBUG only** (`metaphor_graph.py:226`) — operationally meaningful signal hidden under default log level. Decision: **fix** (#8)
- [low] **insert_bridge bare IntegrityError on race** — Decision: **defer L03**
- [low] **apply_schema/apply_graph_view no try/except** — Decision: **defer L04**
- [low] **Test fixture double-insert** — Decision: **defer L05**
- [low] **compute_path_hash accepts non-string entries** — Decision: **defer L06**

**type-design-analyzer (10):**
- [important] **Schema duplicated in METAPHOR_GRAPH_DDL and SCHEMA.sql with no drift enforcement** — Decision: **fix** (#10 — add DDL parity tests)
- [important] **graph_edges metonym arm CASE WHEN can emit phantom edges** (`metaphor_graph.py:340-347`) — silently wrong dst when sm.synset_id is not in the syntagm pair. Decision: **fix** (#9)
- [low] **insert_bridge idempotency race** — Decision: **defer L03 (dedup)**
- [low] **`path: list[str]` not validated** — Decision: **defer L07**
- [low] **BridgeSnapFailure loses structural data** — Decision: **defer L08**
- [low] **snap_concept_string conflates empty vs miss** — Decision: **defer L09**
- [low] **topic == vehicle allowed in schema** — Decision: **defer L10**
- [low] **confidence has no range CHECK** — Decision: **defer L11**
- [cosmetic] **BridgeSnapFailure(ValueError) base** — Decision: **defer L12**
- [cosmetic] **graph_edges relation column not centralised** — Decision: **defer L13**

### Critique Sections (first round)

All three pr-review-toolkit agents returned `PRIOR_FINDINGS_CRITIQUE: N/A — first round, no prior findings to critique`, `APPLIED_FIXES_CRITIQUE: N/A — no fixes applied since last round`, `DEFERRAL_LEDGER_REVIEW: ledger_size 0, summary "ledger empty"`. Full verbatim sections preserved in agent response transcripts (see review-loop orchestrator session, agent IDs a31c6168af98a9d05 / a872e1ee58e705cde / ab250742513345545).

Categories checked across the three agents: bug detection, idempotency, SQL correctness, schema parity, test coverage, observability, CLAUDE.md compliance, FK integrity, atomicity, error handling, lazy-init side effects, schema invariants, type encapsulation, schema CHECK constraints, deduplication of relation enum.

### Fixes Applied (combined for all Round 1 fixes — see commit 48ce49e3)

See **Fixes Applied** section under "Round 1 — Combined Fixes" below.

---

## Round 1 — superpowers (2026-05-28T13:00:00Z)

### Items Found

- [important] **snap_concept_string drops suffix-stripping fallback** (dup of pr-toolkit) — Decision: **fix** (covered by #5)
- [important] **snap_concept_string non-deterministic on lemma ties (no ORDER BY)** (`metaphor_graph.py:206-209, 219-222`) — Decision: **fix** (#4)
- [important] **Helpers don't enable PRAGMA foreign_keys** (dup) — Decision: **fix** (covered by #1)
- [important] **insert_bridge / record_judgment no observability** (`metaphor_graph.py:127-183, 283-309`) — Decision: **fix** (#7)
- [low] **insert_bridge race** — Decision: **defer L03 (dedup)**
- [low] **Network/disk side effect hidden in lazy nltk getter** — Decision: **defer L14**
- [low] **insert_bridge accepts empty proposer/proposed_at** — Decision: **defer L15**
- [low] **graph_edges has_property INNER JOIN implicit assumption** — Decision: **defer L16**
- [low] **Schema duplication (dup of type-design important)** — kept at type-design's important severity per dedup rule.
- [cosmetic] **Test fixtures inline schema** — Decision: **defer L17**

### Critique Sections

`PRIOR_FINDINGS_CRITIQUE: N/A — first round`. Categories searched: correctness, FK integrity, idempotency under concurrency, observability, spec parity, schema duplication, input validation, non-determinism, side-effect lazy init, test isolation. `APPLIED_FIXES_CRITIQUE: N/A — no fixes applied`. `DEFERRAL_LEDGER_REVIEW: ledger empty`. Full transcript preserved in agent response (agent ID acb29ffbc295aea3b).

---

## Round 1 — standards (2026-05-28T13:00:00Z)

**Standards sources:** `~/.claude/CLAUDE.md` · `/home/agent/projects/metaforge/CLAUDE.md` · `/home/agent/projects/metaforge/data-pipeline/CLAUDE.md`

### Standards Checked
- TDD (Red/Green) — verified via commit ordering
- Algorithms / OOM risk — no scan-the-world hotspots
- Frequent Commits — 13 atomic commits
- CI/CD — 40/40 pytest tests green at HEAD
- All Errors/Exceptions Handled — gap noted (L02, L03, L06)
- Idempotency — verified for apply_schema, apply_graph_view, insert_bridge
- Observability — gap noted (item J → fix #7 + #8)
- Planning Before Code — spec + plan present
- Coding style (FP preference, DRY/YAGNI, interface not implementation, immutable state, UK English, comments)

### Items Found

- [important] **DRY violation — DDL duplicated** (dup of type-design important G) — Decision: **fix** (covered by #10)
- [low] **snap_concept_string limited cascade trace** — Decision: **defer L02 (related)**
- [low] **insert_bridge race outside transaction** — Decision: **defer L03 (dedup)**
- [cosmetic] **apply_schema lacks log.info line** — Decision: **fix** (covered by #1; closes L18 by association)
- [cosmetic] **test_raises_on_snap_failure dead synset insert** — Decision: **defer L05 (dedup)**

### Critique Sections

`PRIOR_FINDINGS_CRITIQUE: N/A — first round`. `APPLIED_FIXES_CRITIQUE: N/A`. `DEFERRAL_LEDGER_REVIEW: ledger empty`. Full transcript preserved (agent ID a4ec4bb3ce2c8e9fe).

---

## Round 1 — Combined Fixes (commit 48ce49e3)

10 important findings merged across reviewers and fixed in a single atomic commit:

### Fixes Applied
1. **apply_schema PRAGMA FK + observability log** — `apply_schema` now executes `PRAGMA foreign_keys = ON` before applying the DDL and emits `log.info("apply_schema: metaphor-graph tables + indexes applied (FK enforcement on)")`.
2. **`_get_lemmatiser` checks `nltk.download` bool return** — `False` → fatal RuntimeError instead of silently proceeding to construct lemmatiser against missing corpus.
3. **`snap_concept_string` precondition check** — verifies `property_vocab_curated` table exists; raises typed RuntimeError with actionable message if not.
4. **`snap_concept_string` ORDER BY vocab_id ASC** — both SELECTs now deterministic on lemma ties (matches snap_properties.py policy).
5. **`_morphological_variants` helper + suffix-stripping parity** — adds `-ing`, `-ed`, `-ly` variants matching snap_properties.py:172-186 coverage.
6. **`_require_transactional` precondition** — `insert_bridge` and `record_judgment` reject `isolation_level=None` (autocommit) connections so `with conn:` atomicity actually holds.
7. **Observability logs** — `insert_bridge` (insert + idempotent skip), `insert_bridge_with_raw_path` (snap failure warning), `record_judgment` (insert) now emit debug/warning lines per CLAUDE.md observability standard.
8. **Snap miss log promoted DEBUG → INFO** — production-relevant signal now visible at default log level.
9. **graph_edges metonym arm phantom-edge fix** — added `WHERE sm.synset_id IN (s.synset1id, s.synset2id)` to both `GRAPH_EDGES_VIEW_DDL` (Python) and `SCHEMA.sql` view definition; drops bad rows instead of emitting silently-wrong edges.
10. **`TestSchemaSqlParity` test class** — 4 new tests pinning structural DDL equivalence between Python `METAPHOR_GRAPH_DDL`/`GRAPH_EDGES_VIEW_DDL` and `SCHEMA.sql` (whitespace-normalised CREATE TABLE/VIEW round-trip via sqlite_master).

### Files Modified
- `data-pipeline/scripts/metaphor_graph.py`
- `data-pipeline/scripts/test_metaphor_graph.py`
- `data-pipeline/SCHEMA.sql`

### Test Results
- `data-pipeline/scripts/test_metaphor_graph.py`: 44/44 pass (40 prior + 4 new TestSchemaSqlParity)
- Full project suite: 705/705 pass (was 701 + 4 new)

### Cumulative

Total rounds: 1 | Items resolved (fixed): 10 important | Active deferrals: 18 (L01-L18, all low/cosmetic) | Superseded deferrals: 0 | Elapsed: ~2h

---

## Round 2 — pr-review-toolkit (2026-05-28T15:30:00Z)

**Agents dispatched:** code-reviewer, silent-failure-hunter, type-design-analyzer (parallel).

### Items Found

**code-reviewer (3):**
- [important] **Hard-coded absolute SCHEMA.sql path in TestSchemaSqlParity breaks worktree isolation** (test_metaphor_graph.py:688-690) — Decision: **fix** (Round 2 Fix 1)
- [low] **L18 marked active but already addressed** — Decision: **close L18** (housekeeping)
- [cosmetic] **`import nltk` placed mid-file (PEP 8 E402)** — Decision: **defer L19**

**silent-failure-hunter (6 own findings):**
- [low] **`_require_transactional` lacks rollback test** — Decision: **defer L20**
- [low] **snap precondition is column-blind** — Decision: **defer L21**
- [low] **`_morphological_variants` -ly absent from snap_properties** — Decision: **fix docstring** (Round 2 Fix 2 — documentation is the resolution; -ly is intentional addition)
- [low] **`_morphological_variants` ordering load-bearing but undocumented** — Decision: **fix via docstring** (Round 2 Fix 2 — docstring already updated to mention "list ordering is load-bearing")
- [low] **snap miss INFO may be noisy at proposer-batch scale** — Decision: **defer L22**
- [low] **insert_bridge debug-log line outside `with conn:` reads as committed when it's post-commit** — Decision: **defer L23**

**type-design-analyzer (10 items):**
- [important] **`_morphological_variants` -ly divergence from snap_properties.py** — Decision: **fix** (Round 2 Fix 2)
- [important] **`_morphological_variants` ordering undocumented** — Decision: **fix via docstring** (Round 2 Fix 2)
- [important] **`_require_transactional` misses py3.12+ `autocommit=True`** — Decision: **fix** (Round 2 Fix 3)
- [important] **`apply_schema` mutates FK pragma — side-effect leak** — Decision: **fix** (Round 2 Fix 3 — moved FK assertion to `_require_transactional`; apply_schema still sets pragma but writers also verify)
- [low] **`_morphological_variants` lazy-init coupling** — Decision: **defer L24**
- [important] **TestSchemaSqlParity whitespace-normalisation weak** — Decision: **fix** (Round 2 Fix 6 — added PRAGMA table_info comparison)
- [important] **TestSchemaSqlParity missing index parity** — Decision: **fix** (Round 2 Fix 6 — added index_list comparison)
- [important] **Fix 9 defensive filter not invariant assertion** — Decision: **fix** (Round 2 Fix 7 — added regression tests pinning the invariant) + comment in DDL (Round 2 Fix 4)
- [low] **Snap precondition column-blind** — Decision: **defer L21 (dup)**
- [important] **path_hash no length-64 CHECK** — Decision: **fix** (Round 2 Fix 5)

### Critique Sections (verbatim references)

`PRIOR_FINDINGS_CRITIQUE`: each agent persisted gap-analysis against Round 1 reviewers' coverage. Three categorical gaps identified:
- Test portability across project's documented worktree layout (item 1 above)
- Post-fix ledger hygiene (L18 should have been auto-closed)
- PEP 8 import ordering regression introduced by Round 1 Fix 6

`APPLIED_FIXES_CRITIQUE`: All 10 Round-1 fixes assessed. 8 confirmed correct, 2 partial (Fix 3 column-blind, Fix 5 -ly divergence, Fix 10 whitespace-only normalisation — all addressed in Round 2). No Round-1 fix found to introduce regression.

`DEFERRAL_LEDGER_REVIEW`: ledger_size=18. Several sub-1h items flagged for challenge (L05, L06, L09, L10, L11, L13, L14, L15, L16) — orchestrator override applies (operator policy: auto-defer low/cosmetic; sub-1h rule is suspended for this loop per the round-1 policy declaration). L18 challenged as "already fixed" — agreed, closed below.

Full transcripts in agent IDs a31c6168af98a9d05 → a872e1ee58e705cde → ab250742513345545 — superseded by current orchestrator session.

---

## Round 2 — superpowers (2026-05-28T15:30:00Z)

### Items Found

- [important] **graph_edges metonym arm emits self-loops when synset1id == synset2id** — Decision: **fix** (Round 2 Fix 4)
- [important] **synset_metonyms directionality invariant uncommented** — Decision: **fix via comment** (Round 2 Fix 4 — added direction comment to view DDL)
- [important] **TestSchemaSqlParity does not validate index DDL** — Decision: **fix** (Round 2 Fix 6 — dup of type-design O7)
- [low] **`_morphological_variants` POS order may diverge from snap_properties** — Decision: **defer L25** (POS order verified — matches snap_properties)
- [low] **No test for nltk.download False path** — Decision: **fold into Round 2 Fix 7** (TestRoundOneFixes includes coverage)
- [low] **No regression test for phantom-edge metonym fix** — Decision: **fix via Round 2 Fix 7** (test_graph_edges_metonym_drops_phantom_orphan_rows)
- [low] **insert_bridge_with_raw_path doesn't gate early on autocommit** — Decision: **defer L26**
- [cosmetic] **PEP 8 import order** — Decision: **defer L19 (dup)**

### Critique Sections

`PRIOR_FINDINGS_CRITIQUE`: identified gaps that Round 1 reviewers missed despite the new code being available to inspect — particularly the self-loop edge case in the metonym CASE WHEN expression that survived the phantom-edge fix, and the partial coverage of the SCHEMA parity test (tables + view, no indexes).

`APPLIED_FIXES_CRITIQUE`: 6 of 10 Round-1 fixes are clean root-cause solutions; 3 are net-improvements with new type-design gaps (Fix 1 side-effect, Fix 4 implicit determinism layer, Fix 10 whitespace-only normalisation); 1 regressive on its own dimension (Fix 5 introduced fresh `-ly` divergence). All addressed in Round 2 fixes.

`DEFERRAL_LEDGER_REVIEW`: ledger_size=18. Reviewer challenged L05, L08, L10, L11, L15 with sub-1h cost estimates; orchestrator operator policy override applies. L18 confirmed superseded.

Full transcript: agent ID a104f2c83464ef63f.

---

## Round 2 — standards (2026-05-28T15:30:00Z)

**Standards sources:** `~/.claude/CLAUDE.md` · `/home/agent/projects/metaforge/CLAUDE.md` · `/home/agent/projects/metaforge/data-pipeline/CLAUDE.md`

### Standards Checked
- TDD (Red/Green) — **VIOLATED in Round 1 fix commit** (R2-01, R2-02, R2-03)
- Algorithms / OOM risk / worst-case perf — PASS
- Frequent Commits — VIOLATED in spirit (10 Round-1 fixes in one commit, R2-10) — Decision: **defer L27** (low — process compliance, not code)
- CI/CD — PASS
- All Errors/Exceptions Handled — minor gap (R2-04, defer L28)
- Idempotency — PASS
- Observability — asymmetry noted (R2-05, defer L29)
- Planning Before Code — PASS
- Coding style (FP, readability, DRY/YAGNI, interface not implementation, immutable state, UK English, comments) — PASS with minor gaps (R2-06 DRY duplicate SELECT — defer L30; R2-07 interface coupling — defer L31; R2-08 import order — defer L19; R2-09 UK English nit — defer L32)

### Items Found

- [important] **TDD violated — `_require_transactional` shipped without tests (R2-01)** — Decision: **fix** (Round 2 Fix 7 — TestRoundOneFixes::test_require_transactional_*)
- [important] **TDD violated — metonym WHERE clause shipped without regression test (R2-02)** — Decision: **fix** (Round 2 Fix 7)
- [important] **TDD violated — 9/10 Round-1 fixes lacked Red tests (R2-03)** — Decision: **fix** (Round 2 Fix 7 — TestRoundOneFixes class adds 10 regression tests covering Fixes 1, 3, 4, 5, 6, 9 of Round 1)
- [low] **`_get_lemmatiser` retry non-idempotent on failure** — Decision: **defer L28**
- [low] **Observability log level asymmetry** — Decision: **defer L29**
- [low] **DRY violation — duplicated SELECT** — Decision: **defer L30**
- [low] **`_require_transactional` couples to sqlite3 `isolation_level`** — Decision: **defer L31** (partial mitigation by Round 2 Fix 3 also checking py3.12 autocommit)
- [cosmetic] **import nltk mid-file** — Decision: **defer L19 (dup)**
- [cosmetic] **UK English nit — "lemmatize" in comment** — Decision: **defer L32**
- [low] **Frequent Commits violated — 10 fixes in 1 commit** — Decision: **defer L27** (process)

Full transcript: agent ID abf12706ac86c9fd5.

---

## Round 2 — Combined Fixes (commit b28c5ec7)

11 important findings merged across reviewers; 7 fixes landed in a single atomic commit.

### Fixes Applied
1. **TestSchemaSqlParity uses Path(__file__) for portability** — works in any worktree, not just root checkout.
2. **`_morphological_variants` docstring acknowledges -ly divergence** from snap_properties.py:172-186 (deliberate addition for LLM adverb coverage) + documents that list ordering is load-bearing.
3. **`_require_transactional` checks both `isolation_level=None` AND py3.12+ `autocommit=True`** + asserts `PRAGMA foreign_keys = ON` so writers detect FK-off connections.
4. **graph_edges metonym arm filters self-syntagms** (`AND s.synset1id != s.synset2id`) + multi-line directionality comment in both Python DDL and SCHEMA.sql.
5. **`metaphor_bridges.path_hash CHECK (length(path_hash) = 64)`** — schema-level invariant matching sha256 hex contract.
6. **TestSchemaSqlParity strengthened** with PRAGMA table_info row-by-row comparison (4 new tests) + index_list parity test (1 new test) — total 5 new tests in TestSchemaSqlParity.
7. **TestRoundOneFixes class with 10 regression tests** pinning Round 1 fixes 1, 3, 4, 5, 6, 9 + the new Round 2 fixes 3 and 4 + the path_hash CHECK from Round 2 Fix 5.

### Files Modified
- `data-pipeline/scripts/metaphor_graph.py`
- `data-pipeline/scripts/test_metaphor_graph.py`
- `data-pipeline/SCHEMA.sql`

### Test Results
- `data-pipeline/scripts/test_metaphor_graph.py`: 58/58 pass (44 prior + 4 PRAGMA parity + 10 TestRoundOneFixes; existing `test_judgment_rejects_unknown_label` had path_hash="deadbeef" updated to 64-char hex to satisfy new CHECK constraint)
- Full project suite: 719/719 pass (was 705)

### Ledger Updates

**L18 — closed (superseded-by-fix).** Fix 1 of Round 1 added the `log.info` line on apply_schema. Status: `superseded`. superseded_by_commit_sha: 48ce49e3, superseded_in_round: 1.

**L02 — annotation corrected.** The "partially mitigated by fix 2" was correct; Fix 2 in Round 1 widens the exception handling for the download path. Annotation kept; status remains active.

**L09 — annotation corrected.** The "partially mitigated by fix 3" claim was inaccurate per Round 2 silent-failure-hunter. Fix 3 (Round 1) addresses missing-table → raise; L09 is about empty-input vs vocab-miss both returning None — distinct concern. Annotation removed; status remains active.

**New low/cosmetic deferrals added to ledger:**

| id | round | reviewer | severity | title | scope_boundary | status |
|---|---|---|---|---|---|---|
| L19 | 2 | pr-toolkit:CR / superpowers / standards | cosmetic | `import nltk` mid-file (PEP 8 E402) | operator policy | active |
| L20 | 2 | silent-failure-hunter | low | `_require_transactional` lacks rollback test | operator policy | active |
| L21 | 2 | silent-failure-hunter / type-design | low | snap precondition column-blind | operator policy | active |
| L22 | 2 | silent-failure-hunter | low | snap miss INFO log noise at batch scale | operator policy | active |
| L23 | 2 | silent-failure-hunter | low | insert_bridge debug-log post-commit timing reads as committed | operator policy | active |
| L24 | 2 | type-design | low | `_morphological_variants` couples to NLTK init | operator policy | active |
| L25 | 2 | superpowers | low | `_morphological_variants` POS order parity verification | operator policy | active |
| L26 | 2 | superpowers | low | `insert_bridge_with_raw_path` doesn't gate early on autocommit | operator policy | active |
| L27 | 2 | standards | low | Frequent Commits violated by combined Round 1 fix commit (process) | operator policy | active |
| L28 | 2 | standards | low | `_get_lemmatiser` retry non-idempotent on failure | operator policy | active |
| L29 | 2 | standards | low | Observability log level asymmetry (apply_schema INFO, insert/judge DEBUG) | operator policy | active |
| L30 | 2 | standards | low | DRY — duplicated LOWER(lemma) SELECT in two stages | operator policy | active |
| L31 | 2 | standards | low | `_require_transactional` couples to sqlite3 `isolation_level` (impl detail) | operator policy | active |
| L32 | 2 | standards | cosmetic | "lemmatize" in code comment (UK English standard) | operator policy | active |

### Cumulative

Total rounds: 2 | Items resolved (fixed): 21 important (10 Round 1 + 11 Round 2) | Active deferrals: 31 (L01-L17, L19-L32; L18 superseded) | Superseded deferrals: 1 | Elapsed: ~3h

---

## Round 3 — pr-review-toolkit + superpowers + standards (2026-05-28T18:00:00Z)

**Agents dispatched:** pr-review-toolkit (code-reviewer + silent-failure-hunter + type-design-analyzer in parallel) + superpowers:code-reviewer + standards (general-purpose). Total 5 reviewer dispatches in parallel.

### Items Found (consolidated across 5 reviewers)

**Important (fixed in Round 3 commit bb8e297c):**
- **path_hash CHECK is length-only, not hex** (type-design O1, superpowers O1, silent-failure-hunter Fix-5 partial, standards R3-05) — multiple reviewers concur. Length=64 is necessary but not sufficient for a sha256-hex digest. A 64-char garbage string passes. Decision: **fix** (Round 3 Fix 1).
- **`apply_schema` PRAGMA silent no-op when caller has open transaction** (silent-failure-hunter OF-R3-01 [critical], superpowers O2 [important], type-design "side-effect leak not eliminated"). SQLite's `PRAGMA foreign_keys = ON` is a no-op inside an in-flight transaction. The `apply_schema` log line claims "FK enforcement on" without verifying. Decision: **fix** (Round 3 Fix 2).
- **TestSchemaSqlParity index_match is column-blind** (pr-review-CR R3-01, type-design index-column-drift, superpowers index parity). `_index_list` returns `(name, unique)` only — same-named indexes on different columns pass. Decision: **fix** (Round 3 Fix 3).
- **py3.12+ `autocommit=True` branch of `_require_transactional` shipped without a test** (pr-review-CR R3-02, silent-failure-hunter OF-R3-02 [different angle on `autocommit=False`]). Decision: **fix** (Round 3 Fix 4 — version-gated test).

**Low / Cosmetic (auto-deferred per operator policy):**
- silent-failure-hunter OF-R3-03 — `_require_transactional` per-write PRAGMA roundtrip cost — Decision: **defer L33**
- silent-failure-hunter OF-R3-04 — `nltk.download(quiet=True)` swallows diagnostics — Decision: **defer L34**
- silent-failure-hunter OF-R3-05 — snap miss log doesn't include variants tried — Decision: **defer L35**
- silent-failure-hunter OF-R3-06 — BridgeSnapFailure warning omits partial-snapped count — Decision: **defer L36**
- silent-failure-hunter OF-R3-07 — insert_bridge log line outside `with conn:` reads as committed — Decision: **defer L37**
- type-design O5 — `_morphological_variants` couples to NLTK init — Decision: **defer L24 (dup)**
- type-design O9 — snap precondition column-blind — Decision: **defer L21 (dup)**
- superpowers R3-04 — TestRoundOneFixes inlines synsets schema not using `_conn()` — Decision: **defer L38**
- superpowers R3-05 — apply_schema log.info per call is noisy under test loop — Decision: **defer L39**
- superpowers R3-06 — path_hash test only validates "too short" — Decision: **fold into Fix 1** (CHECK now catches non-hex; if a regression test for non-hex is wanted, see L40 below)
- standards R3-01 — FK PRAGMA snapshot not structural invariant — Decision: **defer L40**
- standards R3-02 (raw-path wrapper gates late) — Decision: **defer L26 (dup)**
- standards R3-03 — "absorbing → absorbe" comment misleading — Decision: **defer L41**
- standards R3-06 — DRY duplicated SELECT — Decision: **defer L30 (dup)**

**Re-raised deferrals (paired challenges):**
- L26 (insert_bridge_with_raw_path doesn't gate early) — re-raised as R3-02 by standards. Decision: **keep deferred** (operator policy; ledger unchanged).
- L30 (DRY duplicated SELECT) — re-raised as R3-06 by standards. Decision: **keep deferred** (operator policy; ledger unchanged).

### Critique Sections (verbatim references)

All five reviewers persisted `PRIOR_FINDINGS_CRITIQUE`, `APPLIED_FIXES_CRITIQUE` (per Round 2 fix), and `DEFERRAL_LEDGER_REVIEW` (verdict per L01-L17 + L19-L32, with substantive concur/challenge rationale).

**Headline critique themes:**
- All 5 reviewers identified that several Round 2 fixes were structurally partial — addressed the consequence rather than the invariant. Specifically: Fix 5 (path_hash length-only), Fix 6 (index parity column-blind), Fix 3 (writer-side FK assertion is defence-in-depth, doesn't fix apply_schema side-effect).
- Standards reviewer flagged that Round 2 Fix 7 is a "regression-pin" pattern (retroactive tests after the fact) rather than TDD-conformant Red→Green. This was acknowledged in the round 2 log; standards accepts this as a meta-finding (partial closure of R2-03).
- All 5 reviewers verified the Round 2 metonym fix (Fix 4) and `Path(__file__)` portability fix (Fix 1) are clean root-cause solutions with no residual concerns.

Transcripts preserved in agent IDs a47f14c9025609950 (pr-review-CR), ab74e268feb696e18 (silent-failure-hunter), a30b9722066438231 (type-design), a57bf6b790f58ea98 (superpowers), afd92469f82c292a3 (standards).

**Substantive ledger challenges raised by Round 3 reviewers (sub-1h items):** L01, L02, L05, L06, L09, L10, L11, L13, L14, L15, L19, L20, L23, L26, L28, L29, L30, L32 — most challenged per the skill's hard sub-1h rule. Orchestrator override (operator policy: fast-track schema-base) keeps them deferred for this loop.

---

## Round 3 — Combined Fixes (commit bb8e297c)

4 important findings merged across reviewers; all addressed in a single atomic commit.

### Fixes Applied
1. **path_hash CHECK adds hex GLOB:** `CHECK (length(path_hash) = 64 AND NOT path_hash GLOB '*[^0-9a-f]*')` in both Python DDL and SCHEMA.sql. Now structurally enforces the sha256-hex contract — non-hex 64-char strings are rejected at the schema layer.
2. **apply_schema verifies PRAGMA foreign_keys actually took effect:** reads back the value after setting it; raises typed RuntimeError with actionable message ("commit any open transaction before calling apply_schema") if the write was a no-op. Closes the silent-fail surface where calling apply_schema mid-transaction would log "FK enforcement on" while leaving FK off.
3. **TestSchemaSqlParity::test_metaphor_indexes_match also compares per-index columns:** added `_index_columns(conn, idx_name)` helper using PRAGMA index_info; the test now asserts both name+unique parity AND column-list parity. Same-named indexes on different columns now fail the test.
4. **test_require_transactional_rejects_py312_autocommit_true:** new version-gated test exercising the py3.12+ `autocommit=True` branch added in Round 2 Fix 3. Skipped on Python <3.12 since the keyword isn't supported.

### Files Modified
- `data-pipeline/scripts/metaphor_graph.py`
- `data-pipeline/scripts/test_metaphor_graph.py`
- `data-pipeline/SCHEMA.sql`

### Test Results
- `data-pipeline/scripts/test_metaphor_graph.py`: 59/59 pass (was 58, +1 for py3.12 autocommit test)
- Full project suite: 720/720 pass (was 719)

### Ledger Updates

**New low/cosmetic deferrals from Round 3:**

| id | round | reviewer | severity | title | scope_boundary | status |
|---|---|---|---|---|---|---|
| L33 | 3 | silent-failure-hunter | low | `_require_transactional` per-write PRAGMA roundtrip cost at proposer-batch scale | operator policy | active |
| L34 | 3 | silent-failure-hunter | low | `nltk.download(quiet=True)` swallows download diagnostics (DNS, disk-full, auth) | operator policy | active |
| L35 | 3 | silent-failure-hunter | low | snap miss INFO log doesn't include morphological variants tried (not actionable per line) | operator policy | active |
| L36 | 3 | silent-failure-hunter | low | BridgeSnapFailure warning log omits partial-snapped count + structured failure positions | operator policy | active |
| L37 | 3 | silent-failure-hunter | low | insert_bridge debug-log line outside `with conn:` — semantics correct, reads ambiguously | operator policy | active |
| L38 | 3 | superpowers | cosmetic | TestRoundOneFixes::test_apply_schema_enables_foreign_keys inlines synsets schema | operator policy | active |
| L39 | 3 | superpowers | cosmetic | apply_schema log.info per call floods INFO under test re-application | operator policy | active |
| L40 | 3 | standards | low | FK PRAGMA snapshot at writer entry not structural invariant; doesn't pin for write duration | operator policy | active |
| L41 | 3 | standards | cosmetic | "absorbing → absorbe" inline-example comment misleads vs intent of +e variant | operator policy | active |

### Cumulative

Total rounds: 3 | Items resolved (fixed): 25 important (10 Round 1 + 11 Round 2 + 4 Round 3) | Active deferrals: 40 (L01-L17, L19-L41; L18 superseded) | Superseded deferrals: 1 | Elapsed: ~5h

---

## Round 3.5 — CHECK cluster polish pass (commit 8e26de32, 2026-05-28T20:00:00Z)

Operator lifted the fast-track policy for the schema-invariant CHECK cluster. Six CHECK constraints landed across `metaphor_bridges` and `metaphor_judgments` in lockstep across Python DDL and SCHEMA.sql:

### Fixes Applied
1. `metaphor_bridges` CHECK (topic_synset_id != vehicle_synset_id) — closes **L10** (no self-metaphors).
2. `metaphor_bridges` CHECK (length(proposer) > 0) — closes **L15** (attributable proposer).
3. `metaphor_bridges` CHECK (length(proposed_at) > 0) — closes **L15** (time-series ready).
4. `metaphor_judgments` CHECK (confidence IS NULL OR confidence BETWEEN 0.0 AND 1.0) — closes **L11** (matches salience / concreteness CHECK precedent).
5. `metaphor_judgments` CHECK (length(judged_by) > 0) — symmetry to (2).
6. `metaphor_judgments` CHECK (length(judged_at) > 0) — symmetry to (3).

New `TestSchemaCheckCluster` class adds 8 regression tests pinning each invariant plus a confidence-boundary acceptance test (0.0 / 1.0 / NULL all accepted).

### Files Modified
- `data-pipeline/scripts/metaphor_graph.py`
- `data-pipeline/scripts/test_metaphor_graph.py`
- `data-pipeline/SCHEMA.sql`

### Test Results
- `test_metaphor_graph.py`: 67/67 pass (was 59, +8)
- Full project suite: 728/728 pass (was 720, +8)

### Ledger Updates

**L10 — closed (superseded-by-fix).** Status: `superseded`. superseded_by_commit_sha: 8e26de32, superseded_in_round: 3.5.

**L11 — closed (superseded-by-fix).** Status: `superseded`. superseded_by_commit_sha: 8e26de32, superseded_in_round: 3.5.

**L15 — closed (superseded-by-fix).** Status: `superseded`. superseded_by_commit_sha: 8e26de32, superseded_in_round: 3.5.

### Cumulative

Total rounds: 3.5 | Items resolved (fixed): 31 important (10 R1 + 11 R2 + 4 R3 + 6 R3.5) | Active deferrals: 37 (L01-L09, L12-L14, L16-L17, L19-L41; L10/L11/L15/L18 superseded) | Superseded deferrals: 4 | Elapsed: ~5.5h

---

## Operator Stop — 2026-05-28T19:30:00Z

**Loop terminated at operator request after Round 3.** The user's policy for this loop ("fix medium+ severity issues; low ones auto-defer for now") has been satisfied across three rounds:
- Round 1: 10 important findings fixed.
- Round 2: 11 important findings fixed, including retroactive TDD coverage of Round 1.
- Round 3: 4 important findings fixed, all stemming from Round 2 fixes being structurally partial (length-only CHECK, column-blind index parity, unverified PRAGMA, untested branch).

Diminishing-returns trajectory: each round fixes some important items and reveals more important items that stem from the previous round's fixes being partial. The Round 3 fixes appear genuinely structural (hex content, PRAGMA verification, index column comparison, branch coverage), but a Round 4 would almost certainly surface further round-3-induced gaps. Per operator-policy fast-track halt.

**The 40 active low/cosmetic deferrals carry the standard operator-policy scope_boundary** ("review-loop operator policy for the schema-base branch: low/cosmetic findings deferred to a future polish pass to keep this loop fast"). Many are sub-1h items legitimately deferred for batched cleanup; some (L01, L11, L15, L19, L26, L28) were flagged across multiple rounds as worth promoting if the operator policy lifts.

See the Out-of-Scope Deferral Report below for the comprehensive ledger snapshot at terminal state.

