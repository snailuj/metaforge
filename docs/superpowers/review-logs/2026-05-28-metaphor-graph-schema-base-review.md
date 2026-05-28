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
