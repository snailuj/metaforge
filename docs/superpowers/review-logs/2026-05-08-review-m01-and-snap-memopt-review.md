# Review Log — M01 Eval Harness + Snap Memory-Opt Refactor

**Branch:** `review/m01-and-snap-memopt`
**Started:** 2026-05-08
**Diff base:** `e93d0d6b` (parent of M01 merge — pre-M01 main HEAD)
**Diff head:** `e509b264` (post-M02-merge HEAD = review branch HEAD)
**Configured adapters:** pr-review-toolkit, superpowers, standards, ux-designer
**Mode:** diff mode (`e93d0d6b..e509b264`)
**Max iterations:** 15

## Scope

M01 milestone deliverable + the snap memory-opt refactor that landed alongside M02. M01 had S03-only review previously (clean across 3 reviewers in iter5/6/7); this is the holistic pass covering S01 + S02 + the `perf(snap)` cursor-streaming refactor.

### In-scope code files

```
data-pipeline/SCHEMA.sql
data-pipeline/enrich.sh
data-pipeline/import_raw.sh
data-pipeline/scripts/cluster_vocab.py
data-pipeline/scripts/enrich_pipeline.py
data-pipeline/scripts/evaluate_aptness.py
data-pipeline/scripts/preprocess_munch.py
data-pipeline/scripts/run_sweep.py
data-pipeline/scripts/snap_properties.py
data-pipeline/scripts/test_evaluate_aptness.py
data-pipeline/scripts/test_preprocess_munch.py
data-pipeline/scripts/test_run_sweep.py
data-pipeline/scripts/test_snap_properties.py
data-pipeline/sweeps/baseline_v2.yaml
data-pipeline/sweeps/sensitivity_v2.yaml
```

(86 files total in diff; the rest are docs / fixture JSON / sweep result snapshots — out of code-review scope but reviewable as supporting artefacts.)

### Pre-existing failures to ignore

- 8 tests in `api/internal/handler/handler_test.go` failing due to absent test fixture DB. Confirmed pre-existing at the pre-M01 main HEAD. Not introduced by this work.

### Methodology caveats

- ux-designer is expected to be a no-op (backend / data-pipeline only — no UI changes).
- Python suite baseline on this branch: **512 passed, 1 skipped** (run 2026-05-08).

## Deferrals Ledger

| id | source | severity | item | scope_boundary | why_out_of_scope | status |
|----|--------|----------|------|----------------|-------------------|--------|
| D1 | type-design (round 1, item td-2) | important | PRAGMA foreign_keys never enabled — FK constraints are decorative across all `sqlite3.connect()` sites in the data-pipeline | Touches every connection site across `enrich_pipeline.py`, `cluster_vocab.py`, `snap_properties.py`, `evaluate_aptness.py`, `run_sweep.py`, `import_*.py`. Cross-cutting infra change spanning the whole pipeline, not specific to M01 or the snap memopt. | Enabling FK enforcement on the canonical `lexicon_v2.db` requires a prior FK-violation audit (orphaned synset_ids, dangling property_id refs, etc.). The audit is non-trivial and a wrong commit could break downstream operations during the M02 plan window. Right call is to schedule a dedicated phase: audit → fix violations → enable PRAGMA via a shared `open_lexicon_db` helper. Memory anchor: when the FK audit lands, this entry should be promoted out of the ledger. | active |
| D2 | type-design (round 1, item td-3) | low | VariationSpec/SweepConfig under-constrain primitives — invariants live only in the runtime validator, not in the type itself | Cosmetic typing improvement to `run_sweep.py` and the SweepConfig TypedDict — does not impact correctness, observability, or behaviour. | The runtime validator already enforces the invariants and is well-tested. Tightening the types via PEP 655 `Required[]` annotations is a typing-cleanup task that belongs to a typing-style pass, not the M01/snap-memopt review. Low-leverage to act on now. | active |
| D3 | type-design (round 1, item td-6) | low | PairScore.score `float \| None` could be split into a discriminated dataclass union | Refactor of the `PairScore` dataclass + every site that reads `result.score`, spanning `evaluate_aptness.py` and the test suite. | The reviewer themselves wrote: "I am NOT recommending this change in this PR. The current PairScore is a pragmatic balance ... Flagging because future cleanup work in this area should consider it; do not act on this alone." Concur: the existing `__post_init__` invariant + Literal status is a clean tagged-union encoding for this codebase. | active |
| D4 | superpowers (round 1, item sp-5) | low | `LOWER(lemma) = ?` lookup queries in `evaluate_aptness.py` defeat the existing index on the raw lemma column | Index/perf tuning in `evaluate_aptness.py:80-94` and possibly schema (functional index on `LOWER(lemma)`). | Performance, not correctness. Needs measurement-driven treatment (profile baseline_v2 + sensitivity_v2 runs to confirm the lookup actually dominates) — the right home is a future perf milestone after M02 has landed and the eval harness sees more sweep volume. | active |
| D5 | superpowers (round 1, item sp-7); standards adapter (round 3) escalation re-engagement | **important** (escalated round 3) | `enrich_pipeline.run_pipeline` holds a single connection across all enrichment files with inner per-step commits (`curate_properties`, `populate_synset_properties`, `populate_lemma_metadata` each call `conn.commit()`). A mid-loop failure on file N leaves files 1..N-1 committed, file N partially written via auto-commit, and the downstream `build_and_store / cluster_vocab / snap_properties / antonyms` stages never run — the DB ends up with curated properties present but no vocab, no clusters, no snap, no antonyms. Recovery today is "delete the DB and `restore_db.sh` from PRE_ENRICH.sql then re-run all files" — violating the project Idempotency standard ("recovery from errors does not require wasting the work of previous runs"). | Refactor of `enrich_pipeline.py:349-382` — wrap the per-file loop in a single transaction (commit only on all-files success), OR add a per-file checkpoint table so retries can resume. Either approach is non-trivial. | **Round 3 reframing:** the round-2 rejection rationale ("JSONL recoverability") was a category confusion — it addressed the snap diagnostic stream (`snap_dropped.jsonl` opens in `"w"` mode, recoverable on retry), NOT the DB-state partial-commit concern. The DB-state issue is structurally important under the Idempotency standard. The deferral-to-act framing remains correct (orchestration refactor is non-trivial and `enrich_pipeline.py` was not touched in any of M01 / snap memopt / round 1-3 fixes), but severity should reflect the actual exposure. Recommend gating on a dedicated pipeline-resilience phase before M02 begins enrichment-volume increase. | active (severity escalated round 3) |
| D6 | SCHEMA fixer (round 1, follow-up) | low | `snap_score` CHECK constraint NOT added — live DB has one row with `snap_score = 1.00000011920929` (float32 cosine drift over 1.0); `[-1.0, 1.0]` would reject it | Schema CHECK + one-time renorm of the 1 outlier row in `synset_properties_curated`. The clamp at write-time landed in round 2 (`7a334528`) so future writes are bounded; the remaining work is renorm + CHECK. | **Round 2 update:** clamp landed (`fix(snap): clamp best_score to [-1.0, 1.0] before persistence`) — D6 is now narrower in scope. Adding the CHECK now still rejects the existing `1.00000011920929` row until renormalised. The next snap rebuild against the canonical lexicon DB will overwrite that row with a clamped value, after which the CHECK lands without preconditions. Tied to the next snap-tuning pass (backlog: `JSJSJS — signal-weighted snap`). | active |
| D7 | type-design (round 2, item R2-8) | low | Test fixture DDL drift — three test files redefine `synset_properties_curated` / `synset_properties` without the new CHECK clauses. A regression that violates the constraints in production would still pass the test suite. | Adding CHECKs to test-fixture `CREATE TABLE` statements in `test_evaluate_aptness.py`, `test_run_sweep.py`, and the dozen-or-so fixtures in `test_snap_properties.py`. | The cleaner long-term shape is a shared test helper that loads `SCHEMA.sql` (single source of truth), but that's a test-infra refactor with broader implications than this review's scope. The round-2 inline-DDL mirror (`23fefe02`) ensures the canonical writer enforces the constraints; the test-fixture gap is a test-coverage improvement, not a production bug. Defer to a dedicated test-infra phase. | active |
| D8 | superpowers (round 2, item R2-15) | low | `_record_drop` would `KeyError` on a missing `"reason"` key. Speculative — all current call sites pass `reason=...`. | Defensive `record.get("reason", "unknown")` in `_record_drop`. | No actual bug today; flagging as a future-proofing concern. The right call is to add this as part of the same future hardening pass that tightens the deferred items above. | active |
| D9 | type-design (round 2, item R2-10) | cosmetic | The `unmatched: list[tuple[str, int, str, float]]` is the last positional-tuple lookalike in `snap_properties.py` that the `AccumulatedMatch` refactor was introduced to replace. | Replace with a `@dataclass(frozen=True) PendingMatch` mirroring `AccumulatedMatch`. | Cosmetic — local + transient (one pass, never persisted). The reviewer who raised it explicitly said "do not act on alone". Bundle with the next snap refactor. | active |
| D10 | type-design (round 2, item R2-11) | low | `SnapMethod` Literal, `_METHOD_RANK` keys, and the SCHEMA.sql + inline-DDL CHECK clauses must agree but have no compile-time link. Adding a fourth method tomorrow would be a 4-file change with no safety net. | A welding test that asserts `set(_METHOD_RANK.keys()) == set(typing.get_args(SnapMethod))` and that the CHECK string contains every member. | Defensive test against future drift, not a current bug. The current state is consistent across all four sites. Defer to the next snap-related refactor. | active |
| D11 | superpowers (round 2, item R2-16) | low | Round 1's `test_random_uniform_docstring_documents_union_size_dependency` pins keyword presence (`"union-size"`, `"cohort"`, `"sanity"\|"calibrated"`). Brittle to legitimate doc rewording. | Replace with a behaviour-focused test (determinism, order-symmetry over union shapes). | Test design tweak; the documented behaviour caveat is the load-bearing artefact, not the prose itself. Defer to a test-quality cleanup pass. | active |
| D12 | silent-failure-hunter (round 3, item SFH3-3) | low (pre-existing) | Module-import-time `nltk.download("wordnet", quiet=True)` in `snap_properties.py` is fire-and-forget — its bool return is discarded. A failed download (no internet, sandboxed CI, write-protected nltk_data) silently produces a delayed `LookupError` from `_lemmatiser.lemmatize(...)` deep inside Pass 1 with no contextual breadcrumb. | Check the return; on `False` log a WARNING noting wordnet wasn't installed and the morph stage will fail. | Pre-existing (not introduced by M01 / snap memopt). The real fix is part of a broader "logging-everywhere" pass that audits every module-init side-effect across `data-pipeline/scripts/`. Defer to that pass. | active |
| D13 | silent-failure-hunter (round 3, item SFH3-4) | low (pre-existing) | `import_raw.sh:107` and `enrich.sh:172` invoke `sqlite3 "$DB_PATH" < "$FILE"` without `-bail`. SQLite CLI continues past failed statements and exits 0 if any later statement succeeds — `set -euo pipefail` cannot escalate. A corrupted PRE_ENRICH.sql with one bad statement yields "imported successfully" followed by a missing-table failure hours later in `enrich_pipeline`. | Add `-bail` to the `sqlite3` invocations in both shell scripts. One-line change per script. | Pre-existing. Both shell scripts were unchanged in M01 / snap memopt / rounds 1-3. The fix belongs to the same shell-resilience pass that addresses other shell-script invariants (e.g. `set -e` propagation through `bash -c` subshells). | active |
| D14 | type-design (round 3, item TD3-3) | cosmetic | `raise AssertionError(...)` at the cast-drift site in `run_sweep.py` (added in `4ab93686`) semantically misrepresents the failure: it's a programming/contract drift (validator-vs-TypedDict), not a failed user-supplied assumption. `RuntimeError` (or a custom `ValidatorDriftError` subclass) would type-document intent more honestly. | Replace `raise AssertionError(...)` with `raise RuntimeError(...)` (or a custom subclass). | Cosmetic — the original concern (`-O` strip) is fully addressed by the explicit raise; the exception class choice is semantic polish. The deferral correctly treats this as a "next sweep refactor" item. | active |
| D15 | superpowers (round 3, item SP3-2) | cosmetic | `test_snap_accumulator_upgrades_method_when_higher_quality_match_arrives_later` doesn't pin cursor iteration order; the test relies on insertion-order being preserved by SQLite's primary-key cursor. A future schema tweak (covering index reorder) could silently flip which branch runs. | Add explicit `ORDER BY sp.property_id` in the production Pass 1 cursor (also helps reproducibility), or pin order in the test by exercising both insert orders. | Cosmetic — current behaviour is stable; combined assertions on `snap_method == 'exact'` and `vocab_id == 2` remain load-bearing today. Bundle with the next snap-touch refactor. | active |
| D16 | superpowers (round 3, item SP3-3) | low | After the first OSError on `_record_drop` JSONL write, `dropped_path = None` disables subsequent writes. Subsequent drop calls are silently no-op'd; only the first failure logs a WARNING. On a noisy run (read-only mount), thousands of subsequent drops are silently lost from the JSONL. | Either log a first-success-then-failure delta in the post-finally summary (e.g. "wrote N drops before write failure"), or accept the noise and log every Nth retry. | The per-reason summary log at the end of `snap_properties()` still reports drop COUNTS even when the JSONL write was disabled, so the operator gets aggregate signal. The lost detail is per-record diagnostic. Acceptable to defer to a logging-completeness pass. | active |

## Round Log

### Round 1 — 2026-05-08T18:30:00+13:00

**Pre-fix SHA:** `6e3ae227e4f4cad3ceb335bcab7b66339ef5e5ab` (review log header commit; baseline for git diff in subsequent rounds)
**Post-fix SHA:** `aa9a1e8c` (HEAD after fixes + test repair)
**Adapters dispatched (parallel):** pr-review-toolkit (3 agents: code-reviewer, silent-failure-hunter, type-design-analyzer), superpowers:code-reviewer, standards (general-purpose). ux-designer no-op (no UI files in scope).
**Tests:** Python suite — **522 passed, 1 skipped** (baseline 512+1; +10 new tests via fixes). Go suite skipped (pre-existing 8-test fixture gap, out of scope).

#### Adapter results — findings before triage

| Adapter | Result | Items |
|---------|--------|-------|
| pr-review-toolkit:code-reviewer | CLEAN (with sub-threshold notes) | 0 fixable |
| pr-review-toolkit:silent-failure-hunter | NOT CLEAN | 3 (1 critical, 2 low) |
| pr-review-toolkit:type-design-analyzer | NOT CLEAN | 8 (3 important, 5 low) |
| superpowers:code-reviewer | NOT CLEAN | 7 (3 important, 4 low) |
| standards (general-purpose) | NOT CLEAN | 3 (2 low, 1 cosmetic) |
| ux-designer | NO-OP (no UI files) | — |

**Total raw findings: 21.** After dedup (silent-failure / standards both flagged the snap silent-except; both flagged the cwd-write footgun): **17 distinct items.**

#### Triage decisions

| ID | Source | Severity | Item | Decision | Rationale |
|----|--------|----------|------|----------|-----------|
| sf-1 / std-1 | silent-failure / standards | critical | snap_properties.py:128-132 — silent broad-except on `vocab_clusters` load | **Fix** | Direct violation of "All Errors/Exceptions Handled" project standard |
| sf-2 / std-3 | silent-failure / standards | low | snap_dropped path resolves to cwd for `:memory:` DBs | **Fix** | One-line guard + log; cheap |
| sf-3 | silent-failure | low | Snap drop count not logged per-reason at WARNING | **Fix** | Replaces `print` with `log.warning`, mirrors `cluster_vocab.py:113` |
| td-1 | type-design | important | SCHEMA.sql lacks CHECK on salience / salience_sum / snap_method / snap_score | **Fix (partial — 3 of 4)** | Verified live DB satisfies salience/salience_sum/snap_method bounds. snap_score deferred (see D6 above). |
| td-2 | type-design | important | PRAGMA foreign_keys never enabled | **Defer (D1)** | Cross-cutting; needs FK-violation audit on lexicon_v2.db before flipping |
| td-3 | type-design | low | VariationSpec/SweepConfig PEP 655 tightening | **Defer (D2)** | Cosmetic typing; not in scope of this review |
| td-4 | type-design | low | `cast(SweepConfig, data)` lacks runtime guard | **Fix** | Belt-and-braces assert, 1 line |
| td-5 | type-design | important | Snap accumulator first-write-wins drops higher-quality methods | **Fix** | Real bug — silently degrades snap_method audit trail |
| td-6 | type-design | low | PairScore.score discriminated split | **Defer (D3)** | Reviewer themselves did not recommend in this PR |
| td-7 | type-design | low | YAML config: `scoring` field not validated at load | **Fix** | Boundary-validation policy, mirrors existing checks |
| td-8 | type-design | low | snap_method Literal alias | **Fix** | Mirrors `PairStatus` pattern; bundled into td-5's commit |
| std-2 | standards | low | `dropped_props` in-memory list undermines snap memopt goal | **Fix** | Stream to JSONL — matches the perf rationale of the snap memopt commit |
| sp-1 | superpowers | important | `load_inapt_controls` crashes on non-dict JSONL line | **Fix** | Documented intent is "tolerate truncated/garbled lines"; non-dict path missed |
| sp-2 | superpowers | important | Snap stats mix unique-keys and links in summary print | **Fix** | Observability drift — operator-facing metric |
| sp-3 | superpowers | important | `vocab_by_lemma` last-write-wins on lemma collision (non-deterministic) | **Fix** | ORDER BY tie-breaker matches `cluster_vocab.py`'s `min(members)` convention |
| sp-4 | superpowers | low | `_build_vocab_matrix` accepts dead `vocab_by_lemma` parameter | **Fix** | Drop unused param; signature now matches contract |
| sp-5 | superpowers | low | LOWER(lemma) defeats index — full table scan per lookup | **Defer (D4)** | Performance, needs measurement-driven treatment |
| sp-6 | superpowers | low | random_uniform docstring missing union-size dependency note | **Fix** | Doc-only fix |
| sp-7 | superpowers | low | enrich_pipeline partial-commit on mid-loop failure | **Defer (D5)** | Pre-existing orchestration concern, not introduced by M01 |

**Fixed: 12 distinct items (yielding 14 commits + 1 follow-up test-repair commit).**
**Deferred: 6 items (D1–D6 in the ledger; D6 surfaced during fixing).**

#### Fix commits (oldest first)

| SHA | Subject |
|-----|---------|
| `43d487d4` | fix(snap): narrow silent except on vocab_clusters load + log degradation |
| `ef0480e4` | fix(evaluate_aptness): skip non-dict JSONL lines in load_inapt_controls |
| `ea624466` | fix(sweep): validate scoring fn name at config-load boundary |
| `33da0d65` | fix(schema): tighten salience/snap_method/salience_sum CHECK constraints |
| `745c7d7a` | docs(evaluate_aptness): document random_uniform's union-size cohort assumption |
| `6cbad110` | refactor(sweep): assert required SweepConfig keys before cast |
| `b848bb6d` | fix(snap): accumulator upgrades snap_method on higher-quality match (bundles SnapMethod Literal + AccumulatedMatch dataclass) |
| `902352b2` | fix(snap): count snapped properties per-link not per-unique-key |
| `8a16cfd2` | fix(snap): stabilise vocab_by_lemma tie-breaker (lowest vocab_id wins) |
| `466fc6f0` | refactor(snap): drop unused vocab_by_lemma parameter from _build_vocab_matrix |
| `0a8ba54f` | feat(snap): log dropped properties per-reason at WARNING level |
| `4fcd7f1c` | perf(snap): stream snap_dropped to JSONL instead of buffering in memory |
| `50a70016` | fix(snap): skip snap_dropped.jsonl write for in-memory DBs |
| `aa9a1e8c` | test(sweep): use runtime monkeypatch trigger after scoring boundary tightening |

Test repair (`aa9a1e8c`) was a follow-up: the `ea624466` boundary tightening broke 4 pre-existing tests that used `scoring: nonexistent_<X>` to trigger runtime per-variation failure. Tests now monkeypatch `evaluate_aptness.evaluate` directly to inject runtime failure without tripping config-load.

#### Behaviour changes for downstream consumers (from snap_properties.py fixes)

- `snap_dropped.json` → **`snap_dropped.jsonl`** (one JSON object per line; streamed; smaller peak memory).
- `stats[snap_method]` counters now per-link (not per-unique-(sid, cluster_id)). `sum(stats.values())` now equals the input cursor row count.
- Snap_method **upgrade policy:** when two properties hit the same (sid, cluster_id) via different methods, higher-rank method wins (was: first-arrival wins). Order: exact > morphological > embedding. A small number of `synset_properties_curated` rows will have a different `snap_method` (and potentially `vocab_id` / `snap_score`) than before on the next rebuild. **This may affect M01 baseline metrics; re-running `baseline_v2.yaml` after the next DB rebuild is recommended.**
- Lemma-collision tie-breaker: deterministic lowest-vocab_id wins (was: unspecified order).
- Snap stage logging now via `logging` not `print` — CLI users invoking `snap_properties.py` directly will see different stdout output unless logging is configured for INFO/WARNING. `main()` does not configure logging by default; `enrich_pipeline.py` (the supported entrypoint) configures it correctly.

#### Files Modified

```
data-pipeline/SCHEMA.sql
data-pipeline/scripts/evaluate_aptness.py
data-pipeline/scripts/run_sweep.py
data-pipeline/scripts/snap_properties.py
data-pipeline/scripts/test_evaluate_aptness.py
data-pipeline/scripts/test_run_sweep.py
data-pipeline/scripts/test_snap_properties.py
```

#### Per-adapter four-section returns

The five adapters' verbatim four-section responses are too long to inline here without bloating the log. Each is captured as the matching task subagent return; the orchestrator parsed them into the triage table above. Re-dispatch in round 2 will re-receive the full review log + active Deferrals Ledger as handover context — the deferrals are the load-bearing artefact that subsequent reviewers must explicitly engage with under Pass 4.

#### Severity assessment & cumulative status

- **Items fixed:** 12 (1 critical, 5 important, 6 low)
- **Items deferred:** 6 (1 important — PRAGMA FK; 5 low — typing/perf/orchestration cleanup)
- **Round was clean?** No — round had fixes applied, so cannot be CLEAN by definition
- **Trend:** N/A (round 1)
- **Cumulative:** 1 round, 14 fix commits, 6 active deferrals.

### Round 2 — 2026-05-08T19:35:00+13:00

**Pre-fix SHA:** `dcc1b0eee` (round-1 docs commit)
**Post-fix SHA:** see HEAD after this round's commits
**Adapters dispatched (parallel):** pr-review-toolkit (3 agents), superpowers:code-reviewer, standards (general-purpose). ux-designer no-op.
**Tests:** Python suite — **533 passed, 1 skipped** (baseline 522+1 from round 1; +11 new tests via round 2 fixes).

#### Adapter results — findings before triage

| Adapter | Result | New Items |
|---------|--------|-----------|
| pr-review-toolkit:code-reviewer | NOT CLEAN | 3 (1 important, 2 low) |
| pr-review-toolkit:silent-failure-hunter | NOT CLEAN | 6 (1 high, 3 medium, 2 low) |
| pr-review-toolkit:type-design-analyzer | NOT CLEAN | 5 (1 important, 3 low, 1 cosmetic) |
| superpowers:code-reviewer | NOT CLEAN | 5 (all low) |
| standards (general-purpose) | NOT CLEAN | 3 (low) |
| ux-designer | NO-OP | — |

**Total raw new findings: 22.** After dedup (file-handle leak flagged by 3 reviewers; logging-config gap flagged by 2; residual prints flagged by 2): **13 distinct items.**

Round 2 also surfaced **deferral challenges**:
- D2 (PEP 655 typing): concur-with-defer, but rationale stale post-round-1 — type-design-analyzer noted that round-1 added validator ballast (`ea624466`, `6cbad110`) that PEP 655 could partially replace.
- D3 (PairScore split): concur-with-defer, but precedent shift — the round-1 `AccumulatedMatch` work establishes the same encoding pattern.
- D5 (enrich_pipeline partial-commit): standards adapter recommended escalating to "important". Re-reading: round 2 confirmed the JSONL artefact compound concern is bounded (`open(..., "w")` truncates on retry, so the diagnostic stream is recoverable). DB-side concern stands but is unchanged. Severity stays low.
- D6 (snap_score CHECK): challenged by 3 reviewers — clamp is one-line. **Acted: clamp landed in round 2 (`7a334528`).** D6 narrowed but stays active for the schema-CHECK + renorm step.

#### Triage decisions for round 2 findings

| ID | Source | Severity | Item | Decision |
|----|--------|----------|------|----------|
| R2-1 | sfh / prt / std | important | `dropped_fh` file handle leak — no try/finally despite docstring claim | **Fix** |
| R2-2 | sfh | medium | Narrowed `OperationalError` except still too broad — misleading "table not loaded" WARNING for locked-DB / disk-IO / readonly | **Fix** (string-match + re-raise non-table cases) |
| R2-3 | sfh | medium | run_sweep broad-except logs `str(exc)` only, no `exc_info=True` | **Fix** |
| R2-4 | sfh | medium | `open(dropped_path, "w")` unguarded — disk-full / RO-FS / permission errors | **Fix** (catch + WARN + continue diagnostic-only) |
| R2-5 | sfh / std | low | 5 residual `print()` calls after round 1's partial migration | **Fix** (finish migration to log.info) |
| R2-6 | sfh / std | low | `snap_properties.main()` doesn't configure logging — log.* dropped silently for direct CLI | **Fix** (basicConfig) |
| R2-7 | td | important | SCHEMA CHECK on `snap_method` is decorative — `snap_properties.py` does DROP+CREATE without CHECK | **Fix** (mirror CHECKs in inline DDL) |
| R2-8 | td | low | Test fixture DDL drift in 3 sites | **Defer (D7)** — test-coverage improvement, not production bug |
| R2-9 | td | low | `AccumulatedMatch.snap_score` lacks `__post_init__` invariant (embedding iff score) | **Fix** |
| R2-10 | td | cosmetic | `unmatched` 4-tuple positional lookalike | **Defer (D9)** — reviewer said "do not act alone" |
| R2-11 | td | low | SnapMethod / _METHOD_RANK / SCHEMA welding test missing | **Defer (D10)** — defensive against future drift |
| R2-12 | sp | low | docstring "closed in finally" claim — collapses into R2-1 | bundled into R2-1 fix |
| R2-13 | sp | low | `assert ... required_top_keys` stripped under `python -O` | **Fix** (replace with explicit raise) |
| R2-14 | sp | low | `_merge` vocab_id swap on rank upgrade undocumented + untested | **Fix** (docstring + test extension) |
| R2-15 | sp | low | `_record_drop` could KeyError on missing "reason" — speculative | **Defer (D8)** — no actual bug today |
| R2-16 | sp | low | `random_uniform` docstring keyword test brittleness | **Defer (D11)** — test design tweak |
| R2-17 | prt | low | Stage 3 `_build_vocab_matrix` non-deterministic on lemma-equiv rows | **Fix** (ORDER BY) |
| R2-18 | prt (paired with D6 challenge) | low | Add one-line clamp on snap_score before _merge | **Fix** (closes D6 partial) |

**Fixed: 12 distinct items (yielding 12 commits across 2 parallel subagents).**
**Newly deferred: 5 items (D7–D11). D6 narrowed by clamp landing.**

#### Fix commits (oldest first)

| SHA | Subject |
|-----|---------|
| `a8527482` | fix(sweep): include traceback in per-variation failure WARNING |
| `e33295c8` | fix(snap): close dropped_fh in finally so mid-stage exceptions don't leak handle |
| `c82a0a14` | fix(snap): re-raise OperationalError when not missing-table (no misleading WARNING) |
| `4ab93686` | refactor(sweep): replace cast-drift assert with explicit raise (-O safe) |
| `0b16291e` | fix(snap): catch OSError on dropped JSONL write so snap stage continues |
| `96bbff41` | fix(snap): configure logging.basicConfig in main() so CLI shows summary + drops |
| `23fefe02` | fix(snap): mirror SCHEMA CHECK constraints in inline DDL |
| `d8fd72aa` | fix(snap): enforce AccumulatedMatch snap_score↔method invariant in __post_init__ |
| `75d8c358` | fix(snap): stabilise _build_vocab_matrix order on lemma collision |
| `7a334528` | fix(snap): clamp best_score to [-1.0, 1.0] before persistence (closes D6 partial) |
| `0b1c5d7f` | feat(snap): finish print → log.info migration for progress lines |
| `5b1ab54d` | docs(snap): document vocab_id replacement on _merge upgrade + cover with test |

#### Behaviour changes for downstream consumers

- `snap_properties.main()` now configures `logging.basicConfig(level=INFO)`. Standalone CLI invocation will print INFO + WARNING lines that previously vanished.
- The narrowed `OperationalError` handler in `cluster_lookup` load now **re-raises** non-"no such table" cases (locked DB, disk IO, etc.) — operators previously got a misleading WARNING + degraded dedup; now the error propagates appropriately.
- The inline DDL in `snap_properties()` now enforces `salience_sum >= 0.0` and `snap_method IN (...)` CHECKs on `synset_properties_curated`. A future writer that violates either will raise `IntegrityError` from `executemany` rather than silently corrupting the table.
- Stage 3 embedding match is now deterministic on lemma-collision (lowest vocab_id wins, mirroring Stages 1-2).
- `snap_score` is clamped to `[-1.0, 1.0]` before persistence — future rebuilds will not produce values outside this range. The existing `1.00000011920929` row will be overwritten on the next snap rebuild.

#### Files Modified

```
data-pipeline/scripts/run_sweep.py
data-pipeline/scripts/snap_properties.py
data-pipeline/scripts/test_run_sweep.py
data-pipeline/scripts/test_snap_properties.py
```

#### Severity assessment & cumulative status

- **Items fixed this round:** 12 (2 important, 3 medium, 7 low)
- **Items deferred this round:** 5 new (D7–D11), all low or cosmetic
- **Round was clean?** No — fixes applied
- **Trend:** Severity decreasing — round 1 fixed 1 critical + 5 important; round 2 fixed 2 important + 3 medium + 7 low. Pattern moving from real bugs toward observability + test polish.
- **Cumulative:** 2 rounds, 26 fix commits, 11 active deferrals (D1–D11).

### Round 3 — 2026-05-08T20:55:00+13:00

**Pre-fix SHA:** `8745178c` (round 2 docs commit)
**Post-fix SHA:** see HEAD after this round
**Adapters dispatched (parallel):** pr-review-toolkit (3 agents), superpowers:code-reviewer, standards (general-purpose). ux-designer no-op.
**Tests:** Python suite — **535 passed, 1 skipped** (baseline 533+1 from round 2; +2 new tests via round 3 fixes).

#### Adapter results

| Adapter | Result | New Items |
|---------|--------|-----------|
| pr-review-toolkit:code-reviewer | NOT CLEAN | 1 (low — SCHEMA missing idx_spc_vocab) |
| pr-review-toolkit:silent-failure-hunter | NOT CLEAN | 4 (4 low — 2 sub-threshold from prior rounds, 2 new: json TypeError, outer close mask) |
| pr-review-toolkit:type-design-analyzer | NOT CLEAN | 5 (re-raises of D8/D9/D10 with stronger precedent + 1 new cosmetic AssertionError class + 1 new low DDL dedup framing) |
| superpowers:code-reviewer | NOT CLEAN | 3 (sub-threshold: outer close, test pin order, silent-drop subsequent) |
| standards (general-purpose) | NOT CLEAN | 1 escalation (D5 misclassified — orchestrator confused JSONL recoverability with DB-state) |
| ux-designer | NO-OP | — |

**Total raw new findings: 14** (after dedup of close-mask flagged by sfh+sp): **~12 distinct items.**

#### Triage decisions for round 3

| ID | Source | Severity | Decision |
|----|--------|----------|----------|
| TD3-1 / D8 re-raise | type-design | low | **Partially Fix** — widen `_record_drop` except to TypeError/ValueError covers JSON-serialisation side. KeyError-on-`reason` (D8 proper) remains active deferral. |
| TD3-2 / D10 re-raise | type-design | low | Defer — D10 already covers; rationale strengthened in ledger |
| TD3-3 (AssertionError class) | type-design | cosmetic | **Defer (D14)** — semantic polish, original `-O` concern fully addressed |
| TD3-4 / D10 extends | type-design | low | Defer — D10 already covers; rationale strengthened |
| TD3-5 / D9 re-raise | type-design | cosmetic | Defer — D9 already covers; rationale strengthened |
| STD3 D5 escalation | standards | important (re-class) | **Update D5 ledger entry** — reframe per category-confusion catch; severity escalated from low to important |
| SFH3-1 (json.dumps TypeError) | silent-failure-hunter | low | **Fix** |
| SFH3-2 (outer close mask) | silent-failure-hunter | low | **Fix** |
| SFH3-3 (nltk.download) | silent-failure-hunter | low | **Defer (D12)** — pre-existing, out of M01/snap-memopt scope |
| SFH3-4 (sqlite3 -bail) | silent-failure-hunter | low | **Defer (D13)** — pre-existing, shell-script scope |
| PRT3-1 (idx_spc_vocab missing in SCHEMA) | code-reviewer | low | **Fix** |
| SP3-1 (outer close mask) | superpowers | low | bundled with SFH3-2 fix |
| SP3-2 (test pin order) | superpowers | cosmetic | **Defer (D15)** |
| SP3-3 (silent-drop subsequent) | superpowers | low | **Defer (D16)** |

**Fixed: 3 distinct items (3 commits across 2 parallel subagents).**
**Newly deferred: 5 items (D12–D16). D5 reframed + severity escalated. D8 narrowed by partial overlap with SFH3-1 fix.**

#### Fix commits

| SHA | Subject |
|-----|---------|
| `c4819aec` | fix(schema): add missing idx_spc_vocab on synset_properties_curated |
| `70d470f0` | fix(snap): widen _record_drop except to JSON-serialisation errors so diagnostic stream stays diagnostic |
| `3f5595e1` | fix(snap): guard outer dropped_fh close so close-time error doesn't mask original |

#### Files Modified

```
data-pipeline/SCHEMA.sql
data-pipeline/scripts/snap_properties.py
data-pipeline/scripts/test_snap_properties.py
```

#### Severity assessment & cumulative status

- **Items fixed this round:** 3 (all low)
- **Items deferred this round:** 5 new (D12–D16) + 1 escalation (D5 reclassified)
- **Round was clean?** No — 3 fixes applied
- **Trend:** Severity decreasing strongly. Round 1: 1 critical, 5 important, 6 low fixed. Round 2: 2 important, 3 medium, 7 low. Round 3: 3 low. Most round-3 findings were re-raises of existing deferrals (with stronger precedent arguments) or sub-threshold hardening notes.
- **Nudge:** 3 consecutive rounds with declining severity; round 3 fixed only low items. **Diminishing returns territory** — consider stopping after round 4 if it returns CLEAN or near-CLEAN.
- **Cumulative:** 3 rounds, 29 fix commits, 16 active deferrals (D1–D16).

