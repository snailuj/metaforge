# Plan — LLM Judge Agreement Harness + Two-Stage Judge (Stage 1 first)

**Status:** proposed (awaiting greenlight). Distilled from a background-agent draft + the
2026-06-10 bad_head correction. Design locked in memories `judge_bootstrap_direction`,
`grading_linkage_tag_semantics`, `head_extraction_broken_confirmed`, `grading_verdict_model_v2`.

## Goal & success criteria

Bring an LLM **judge** online that demonstrably tracks Julian's manual verdicts so he stops
being the throughput bottleneck. Build the **agreement eval harness first** (the unblocker),
then a **construction (linkage) judge — Stage 1**, then a **liveness/pairing judge — Stage 2**.
Both are pluggable candidate judges measured by the same harness.

"Judge online" = a callable `judge(few_shot, item) -> 0/1` scored by a topic-grouped harness
reporting **Cohen's κ per axis + confusion matrix + confidence band** against gold, with the
result JSON + markdown committed as evidence.

**Verified corpus (live grading-live JSONL, 2026-06-10):** 89 resolved verdicts / 21 topics.
- Stage-1 (linkage) positives: `linkage_effective` **bad 35 / good 54** (re-based from raw bad 11).
- Stage-2 (liveness) set: **all live/dead ≈ 85** (~48 live / 37 dead). **bad_head rows are
  INCLUDED** — bad_head is an intermediate mis-extraction (endpoints canonicalised), so the
  topic→vehicle pairing is always valid and a word-pairing judge is unaffected. (The 57-row
  bad_head-excluded set is the geometry-reliable subset — a *separate* path-signal workstream,
  not the judge training set.)

**κ gates (smoke-test regime, wide CIs ±~18pts on a ~29-item fold):**
- Stage 1 (the reachable first win): **κ ≥ 0.4** on linkage, confusion matrix not just majority-class.
- Stage 2 (coarse only): **κ ≥ 0.3** on binary live/dead. NOT targeting tier agreement (multi-thousand-label regime).
- Every κ reported with an empirical band over repeated folds; a point estimate whose band
  straddles 0 is "underpowered, not usable". Read the gate off the band, not the mean.

## Worktree / branch

`git worktree add .worktrees/judge-harness -b metaphor-graph/judge-harness main`. Python-only ML;
keep OFF the grading-UI branch and OFF grading-live (the live sidecar auto-commits there).
Harness only READS the grading JSONL. `python3 -m venv data-pipeline/.venv && pip install -r
data-pipeline/requirements.txt` — sklearn (`cohen_kappa_score`, `confusion_matrix`) already present,
no new dep. New scripts + colocated `test_*.py` in `data-pipeline/scripts/`. Gold path via
`grading_io.DEFAULT_VERDICTS_PATH` (resolves to the live grading-live copy).

## 1. Data prep — `judge_corpus.py` (+ tests)

Reuse, don't duplicate: `resolve_verdicts` + `normalise_judgement` from `grading_sidecar`
(latest-wins/supersede + v1→v2 axes; v1 rows get `tags=[]` so never bad_head-filtered).

- `load_resolved(path=None)` — read JSONL (skip+log malformed), resolve, normalise.
- `linkage_effective(rec)` — `bad if linkage=="bad" OR tags ∩ {bad_head,leap,merge}` (padding excluded).
  Regression guard: corpus bad ≈ 35 (`>= 30`).
- `construction_rows(records)` — Stage-1 rows (drop irrelevant); `y_link=1` if linkage_effective bad.
- `liveness_rows(records)` — keep `metaphor in (live,dead)`. **Do NOT drop bad_head** (pairing valid)
  and do NOT gate on linkage (orthogonality). `y_live=1` live. Corpus ≈ 85 (`>= 80`).
- `attach_chain_context(rows, chains, glosses)` — join chain steps + topic/vehicle glosses by
  signature; flag+log `chain_missing` rather than silently drop.

## 2. Agreement harness — `judge_harness.py` (+ tests)

Mirrors `learning_curve.py` (grouped CV, `_summarise` bands, `render_markdown_report`, argparse main);
unit = a candidate judge, metric = κ + confusion (not AUC). `JudgeFn = (few_shot, item) -> int`.

- `topic_folds(rows, n_repeats, seed)` — **leave-one-topic-out**; few-shot drawn only from remaining
  topics. Load-bearing test: no topic in both train+test; every topic held out once/repeat.
- `select_few_shot(train, k, seed, balance_axis)` — class-balanced, topic-disjoint, deterministic.
- `run_axis(rows, judge_fn, axis_key, k_shot, n_repeats, seed, cache)` — per fold×repeat call judge on
  held-out items; pool (y_true,y_pred); `cohen_kappa_score` + `confusion_matrix` + empirical band;
  report raw acc + majority baseline alongside. Judge errors → logged **abstention** (counted, excluded
  from κ), never crash; single-class folds skipped+logged. Tests use a pure-Python stub judge (κ=1 on
  perfect, ≈0 on random) — **no LLM in unit tests**.
- `render_markdown_report` + `main(--axis,--judge,--k-shot,--n-repeats,--seed,--model,-o,--cache,-v)`.

## 3. LLM call layer — reuse `lib/claude_client.py`

`prompt_json(prompt, model, expect, max_retries)` shells the `claude` CLI (no API key committed —
session auth; satisfies Secrets Policy). Import via the `sys.path.insert(.../lib)` shim used in
`metaphor_disambiguate.py`. **DI-`prompt_fn=None`** so unit tests inject a stub. Errors: `ParseError`/
`ClaudeError` → `ABSTAIN`; `SessionLimitError` re-raised to halt cleanly (cache makes resume free).
**Idempotency/caching:** content-addressed `sha256(model+prompt)` → JSONL cache (`output/judge_cache.jsonl`,
gitignored); cache hit = $0. Re-running a config costs nothing; only new (prompt,item) tuples spend.

## 4. Stage-1 construction judge — `judge_stage1.py` (+ tests) — BUILD FIRST

Structural rubric (NOT the persona): flag BAD if vehicle/head mis-extracted (`bad_head`), an
unjustified jump (`leap`), or two steps restate one concept (`merge`); padding (bloated-but-valid)
is GOOD. Show the ordered chain + glosses + topic-disjoint class-balanced few-shot. Strict JSON
`{"verdict":"good|bad"}`; default model `haiku` (parameterised). Measure via `run_axis` on
`construction_rows`; sweep k_shot/model; commit winning JSON+md. Gate κ ≥ 0.4.

## 5. Stage-2 liveness/pairing judge — `judge_stage2.py` (+ tests)

Adapt `liveness_judge_persona.md` ("Forge Reader") — **unit is the (topic, vehicle) PAIRING, not the
chain**: present only `topic(gloss) → vehicle(gloss)`, ask LIVE/DEAD. **Do NOT feed the intermediate
chain** (imports lazy-path noise). Trains/evals on the full ≈85-row live/dead set (bad_head included —
the endpoints it judges are correct). Default model `sonnet` (report Haiku baseline κ to quantify the
lift). Gate κ ≥ 0.3. Orthogonality check: Stage-1 verdict does NOT gate Stage-2 inputs.

## 6. Build order (TDD, atomic commits)

1. worktree+venv+scaffold smoke test. 2. `judge_corpus` (5 fns, golden-count checkpoints: 89/35/85).
3. `judge_harness` w/ stub judge (leakage assertion green; κ=1/≈0 on stubs — validated before any LLM).
4. `judge_llm` cache+abstain (offline). 5. `judge_stage1` (offline prompt/leakage tests → one guarded
cached live run → read gate). 6. `judge_stage2` (pairing-only test → guarded live run → gate). 7. findings
note + PIPELINE.md update; PR via `finishing-a-development-branch` (no direct-to-main).

## 7. Risks

- κ instability at small n → bands not point estimates; skip single-class folds.
- few-shot leakage → topic-disjoint enforced + asserted at fold AND prompt level (most-tested property).
- persona prompt sensitivity → A/B model+k via the κ harness, not blind hand-tuning.
- **Stage-1 κ < 0.2** ⇒ same failure mode as the broken Haiku extraction-evaluator
  (`head_extraction_broken_confirmed`) ⇒ the **extractor fix** is the real prerequisite; report and stop.
- class imbalance → κ is headline (chance-corrected); majority baseline shown beside it.
- `merge` currently inert (0 in live data); kept in the forcing set for forward-compat.

## 8. Out of scope

Tier judge; `metaphor_bridges` materialisation / path-geometry promotion; the head-extraction fix
itself (Stage 1 *detects*, doesn't fix); any forge-cascade change; grading-UI changes; any deploy.
