# Metaphor Graph Stage A — Dry-Run Hardening Spec

**Date:** 2026-05-29
**Branch:** `metaphor-graph/enrich-stage-a` (continues the implemented Stage A)
**Supersedes (in part):** `docs/superpowers/specs/2026-05-28-metaphor-graph-enrichment-stage-a.md` — specifically its "Topic resolution" and "Path snapping" decisions for *endpoints* (see Fix 1). The original spec's path/property snapping stands.
**Memory anchors:** `stagea-topic-snap-fix`, `loop2-cohort-haiku-only`, `snapping-reconciliation-deferred`, `m03_cascade_winner_config`

---

## Why this exists

The implemented Stage A (7 tasks, committed) was exercised in a bounded single-batch dry-run on 2026-05-29. The run surfaced four defects that the mocked unit tests could not catch, plus one strategic finding. This spec scopes the fixes.

## Findings from the dry-run

1. **Topic snap coverage** — topic resolution used `snap_concept_string` (property vocab only): **127/200 (63.5%)**. `lookup_primary_synset` (full WordNet lemma→synset index) resolves **200/200**.
2. **Vehicle snap is creativity-regressive** — all four ingest modules resolve the *vehicle* via `snap_concept_string` too. On the 20-topic batch: Haiku (conventional) vehicles 87% snap; **Sonnet (creative) vehicles only 59%** — 41% silently dropped, and the dropped set is precisely the literary payload (`fermentation, abscess, palimpsest, crucible, rhizome, undertow, whetstone…`). `lookup_primary_synset` → 98%. The bug preferentially destroys our most original output.
3. **Cascade proposer never ran the cascade scorer** — `make_go_suggest_fn` started the Go binary with no flags → legacy mode. It also 404'd on plurals ("ideas") because legacy exact-match lacks the lemmatiser fallback.
4. **Batch not failure-isolated** — one proposer's error (the cascade 404) aborted the whole run before later proposers' ingest (so `haiku_sonnet_v1` got 0 bridges despite the Sonnet output existing).
5. **Strategic:** the stored 200-cohort is **Haiku-only** (Sonnet rewrite is systematically more creative) → Loop 2 findings are dead-metaphor-based (noted, not actioned here).

## Fixes (in scope)

| # | Fix | Touches |
|---|-----|---------|
| 1 | **Endpoint resolution → `lookup_primary_synset`.** Topics (pre-flight) and vehicles (all four ingest modules) resolve via `lookup_primary_synset`. **Path/property concepts keep `snap_concept_string`** — properties genuinely belong to the property vocab. Relocate `lookup_primary_synset` into `metaphor_graph.py` (snapping home); `evaluate_aptness` re-imports it (stable API). | metaphor_graph.py, evaluate_aptness.py, topics, haiku, inapt, sonnet, cascade |
| 2 | **Cascade in cascade mode.** `make_go_suggest_fn` passes `--cascade` and relies on S05's parity-tested defaults (which encode the M03 winner config: `concreteness_threshold=1.0, alpha=1.0, d_cap=0.77, ortony_scoring=jaccard_salience, composition=additive`). A verification step asserts the binary's cascade scoring still matches the crib pairs rather than re-passing a fragile Python→Go knob translation. | cascade |
| 3 | **Cascade word→Go alignment.** Pass the curated lemma for the pre-flight `topic_synset_id` to Go (falls back to the raw word when the synset has no curated lemma), killing the plural-404 class and reducing Go/Python divergence. Bridge label always uses the pre-flight synset (single source of truth). | cascade |
| 4 | **Batch failure-isolation.** Each proposer ingest (and each per-topic cascade call) runs in try/except; failures record to the progress markdown and the run continues. No single proposer error aborts the batch or remaining batches. | run (batch), cascade (per-topic) |
| 5 | **Sonnet reuse skip.** `run_sonnet_edits` reads the audit JSONL and skips topics already present (mirrors `synthesise_paths`'s existing log-skip), so re-runs and incremental cohorts don't re-spend Sonnet. | sonnet |

## Single source of truth for endpoints

After Fix 1+3, every proposer labels a bridge's topic with the **pre-flight `topic_synset_id`** and its vehicle with `lookup_primary_synset(vehicle)`. All four proposers therefore agree on the topic node, and creative vehicles survive. The cascade *score* still rides Go's internal re-resolution of the lemma we pass — best-effort alignment, residual divergence tracked below.

## Out of scope (DEFERRED — tracked as CAP-snap-recon in PIPELINE.md Backlog)

- **Full Go↔Python snap unification** — one deterministic shared snapper, or Go accepting a pre-resolved `synset_id`. Intersects the unmerged `loop` branch (its Go-side lemmatiser fallback would close the plural gap on the Go side) and the pending "merge loop-1 to main" decision.
- **Gloss-based sense accuracy** — `lookup_primary_synset` fixes *coverage* with a polysemy heuristic that ignores the per-topic `_gloss`. 100% resolution can still be wrong-sense. Gloss-grounded disambiguation is the accuracy lever.
- **Re-evaluation** of prior loop results once snapping is unified/accurate.
- **Sonnet over the full 200** — a genuine first spend (Haiku-only finding); execution decision, not code.

## Settled decisions

| Decision | Outcome |
|----------|---------|
| Endpoint resolver | `lookup_primary_synset`, relocated to `metaphor_graph.py`. |
| Path/property resolver | unchanged — `snap_concept_string`. |
| Cascade config | `--cascade` + S05 parity-tested defaults; verify, don't re-pass knobs. |
| Go word alignment | pass curated lemma of pre-flight synset; fall back to raw word. |
| Resilience | per-proposer + per-topic try/except; record and continue. |
| Sonnet reuse | skip-if-in-audit-log. |
| Snap reconciliation/accuracy | deferred, tracked CAP-snap-recon. |

## Tests / verification

- Each modified module keeps its unit test green and gains a targeted assertion for its change (endpoint resolver used; cascade passes `--cascade`; cascade falls back to raw word on no-curated-lemma; run continues past a raising proposer; Sonnet skips logged topics).
- Integration: re-run the bounded single-batch dry-run against a scratch DB copy; assert **all four proposers** populate bridges, the run does **not** crash, and the topic/vehicle snap rate matches the `lookup_primary_synset` numbers.
