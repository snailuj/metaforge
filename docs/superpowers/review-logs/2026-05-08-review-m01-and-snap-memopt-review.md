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
| D5 | superpowers (round 1, item sp-7) | low | `enrich_pipeline.run_pipeline` holds a single connection across all enrichment files; partial mid-loop failure leaves some files committed and downstream curated/cluster/snap stages unrun | Refactor of `enrich_pipeline.py:349-382` orchestration — would either move per-step commits up to the orchestrator (large blast radius) or wrap the per-file loop in a single transaction (changes recovery semantics). | `enrich_pipeline.py` was not added by M01; the orchestration concern is pre-existing and the snap memopt commit did not interact with it. `INSERT OR IGNORE` partially bounds the inconsistency window. The right home is a dedicated pipeline-resilience phase that can also address the Go-handler missing-fixture issue and re-test idempotency end-to-end. |  active |
| D6 | SCHEMA fixer (round 1, follow-up) | low | `snap_score` CHECK constraint NOT added — live DB has one row with `snap_score = 1.00000011920929` (float32 cosine drift over 1.0); `[-1.0, 1.0]` would reject it | Defensive clamp in `snap_properties.py` before persistence (e.g. `score = max(-1.0, min(1.0, score))`) plus a one-time renormalisation of the 5,156 existing rows. The schema CHECK can land safely after both. | Adding the strict CHECK without first clamping would reject a legitimate near-perfect embedding match. The fixer left a documented inline comment in `SCHEMA.sql` flagging the deferral. The right home is a small follow-up task tied to the next snap-tuning pass (already on the backlog as `JSJSJS — signal-weighted snap`). | active |

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

