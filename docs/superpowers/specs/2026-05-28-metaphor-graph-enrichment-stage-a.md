# Metaphor Graph Enrichment — Stage A Spec

**Date:** 2026-05-28
**Branch:** `metaphor-graph/enrich-stage-a` (off `metaphor-graph/schema-base`)
**Related:** `docs/superpowers/specs/2026-05-28-metaphor-graph-schema-design.md`
**Memory anchors:** `metaphor_graph_schema_base_landed.md`, `eval_as_preference_tracking_instrument.md`

---

## Goal

Populate `metaphor_bridges` + `metaphor_bridge_steps` with proposals from four proposers over the 200-topic Karpathy Loop 2 cohort. Idempotent batch enrichment, no judgments written. Sets up the substrate for the Stage B interactive eyeballer (separate, later spec).

## Proposers

| Proposer | Source | Path semantics |
|----------|--------|----------------|
| `cascade_v1` | Go `/forge/suggest` over the 200 topics | Shared curated properties from cascade scoring → one bridge per shared property |
| `haiku_v1` | Existing `metaphor_spike_apt_phase2_20260525T004154.jsonl` (reuse, no re-spend) | One bridge per `shared_features[i].concept` per vehicle |
| `haiku_sonnet_v1` | New Sonnet edit pass — full editorial rewrite of Haiku's list per topic | One bridge per Sonnet-output path concept per vehicle |
| `haiku_v1_inapt_synthesised` | Existing inapt Phase 2 JSONL + LLM-synthesised weak-dimension path | One bridge per synthesised weak-dimension concept; tag clearly so it never confounds the apt pool |

All four proposers write to the same `metaphor_bridges` table, deduped by `UNIQUE (topic_synset_id, vehicle_synset_id, proposer, path_hash)`.

## Topic resolution

`spike_2_topics.json` carries `{word, gloss, source}` for 200 topics — no `synset_id`. We snap each topic via `metaphor_graph.snap_concept_string` (NLTK + morphological + curated-vocab join). Outcomes:

- Snaps → record `topic_synset_id` and proceed for that topic across all proposers
- Doesn't snap → log + skip the topic across all proposers (recorded in a per-batch report)

This means the effective cohort may be < 200. We log the survival count; if drop-out is > 10% we surface it as a finding rather than silently proceeding.

POS-ambiguous snaps (e.g. "rain" — noun and verb both curated): take the snap_concept_string default (first match in NLTK POS order n,v,a,r — same order as snap_properties.py). The eyeballer will catch wrong-sense vehicles per-bridge later.

## Path snapping

Per bridge, each path concept (cascade shared property, Haiku `shared_features[].concept`, Sonnet path concept, synthesised weak-dimension concept) is snapped via the same helper. Outcomes per bridge:

- All path concepts snap → bridge inserted with full path
- Any path concept fails to snap → bridge skipped, log via `BridgeSnapFailure` with proposer + topic + vehicle + failing-concept-string

This matches the existing `insert_bridge_with_raw_path` contract — already tested.

## Inapt path synthesis (`haiku_v1_inapt_synthesised`)

Phase 2 inapt entries have `(vehicle, inapt_reason_type, explanation)` but no `shared_features`. We synthesise a single weak-dimension path concept per inapt entry:

- LLM call (Haiku, cheap): given `{topic, vehicle, inapt_reason_type, explanation}`, extract a single one-word concept that captures the weak dimension the explanation cites.
- Output: `{topic, vehicle, weak_concept}` triple
- Insert as bridge with `proposer='haiku_v1_inapt_synthesised'`, `rationale = explanation`, single-step path = `[weak_concept]`

Idempotency: re-running the synthesis call for a `(topic, vehicle)` already in the JSONL log is skipped (we keep a `haiku_v1_inapt_synthesised_paths.jsonl` log file in `data-pipeline/output/` that the synthesis script reads before deciding whether to call the LLM).

## Sonnet edit pass

Per topic, send Sonnet the full Haiku apt entry: topic, gloss, all Haiku vehicles + their shared_features. Prompt instructs full editorial rewrite — substitute weak vehicles, sharpen paths, return polished list of 10 vehicles each with 3-6 one-word path concepts. JSON-validated response.

Sonnet output is written verbatim to a new JSONL (`metaphor_graph_sonnet_edits_<TS>.jsonl`) for audit, then ingested as `proposer='haiku_sonnet_v1'` bridges.

When Sonnet returns the same `(topic, vehicle, path_concept)` triple as Haiku already produced, the dedup at insert time gives us *two* bridges (one per proposer) with the same `path_hash`. The eyeballer will collapse them as "concur" cards. That's the design payoff.

## Cascade enrichment

Per topic synset_id, call Go `/forge/suggest?word=<lemma>&limit=10` against a temporary Go binary started on a free port (reusing the `loop1_eyeball_harness.py` subprocess pattern). For each returned vehicle, the cascade response carries shared_properties (these are already curated property synsets) — insert one bridge per shared property, snapping the property concept to its curated synset_id.

If `/forge/suggest` returns < 10 vehicles for a topic (cascade-empty case), we record the underflow but don't fail the batch.

## Batching

200 topics → 10 batches of 20. Each batch:

1. Topic-snap pass: snap all 20 topics, record snap result
2. For surviving snapped topics, run each proposer ingest in turn:
   - `cascade_v1` ingest
   - `haiku_v1` ingest (read JSONL slice)
   - `haiku_sonnet_v1` LLM call + ingest
   - `haiku_v1_inapt_synthesised` LLM call + ingest (only for topics with inapt entries)
3. Commit at end of batch (single transaction per batch per proposer)
4. Append a row to a markdown checkpoint at `data-pipeline/output/metaphor_graph_enrich_progress.md` showing per-proposer bridge counts and snap drop-outs

Re-running is safe: idempotent on the schema's `UNIQUE` constraint, and we early-return from a batch if every proposer has already written for every topic in that batch.

## Scripts

| Script | Purpose |
|--------|---------|
| `data-pipeline/scripts/metaphor_graph_enrich_haiku.py` | Ingest existing Haiku Phase 2 JSONL → `haiku_v1` bridges |
| `data-pipeline/scripts/metaphor_graph_enrich_inapt.py` | LLM-synthesise weak-dim paths from Phase 2 inapt JSONL, then ingest → `haiku_v1_inapt_synthesised` bridges |
| `data-pipeline/scripts/metaphor_graph_enrich_cascade.py` | Subprocess Go binary, query `/forge/suggest`, ingest → `cascade_v1` bridges |
| `data-pipeline/scripts/metaphor_graph_enrich_sonnet.py` | Sonnet editorial-rewrite call, audit JSONL, ingest → `haiku_sonnet_v1` bridges |
| `data-pipeline/scripts/metaphor_graph_enrich_run.py` | Batch driver: walks 10 × 20 topics, calls the four ingest scripts in order per batch, writes progress markdown |

Each script is independently runnable for partial-recovery work (rerun just the cascade pass, etc.). The run script is the canonical batch driver.

## Tests

Each ingest script gets a unit test with a tiny fixture (1-3 topics):

- `test_metaphor_graph_enrich_haiku.py` — fixture JSONL, asserts correct row counts, asserts idempotency on re-run, asserts unsnappable-concept drops via `BridgeSnapFailure`
- `test_metaphor_graph_enrich_inapt.py` — mocked LLM response, asserts single-step path, asserts rationale carries explanation, asserts idempotency log skip
- `test_metaphor_graph_enrich_cascade.py` — mocked subprocess call returning canned `/forge/suggest` JSON, asserts vehicle + shared-property mapping
- `test_metaphor_graph_enrich_sonnet.py` — mocked Sonnet response, asserts ingest path
- `test_metaphor_graph_enrich_run.py` — drives all four with mocked LLM/subprocess, asserts batch boundary commits, asserts progress markdown lines, asserts idempotency on full re-run

Integration assertion: after a single-batch end-to-end run, `graph_edges` view returns zero metaphor_link rows (no judgments yet) but the underlying physical tables have bridges across all four proposers.

## Out of scope

- The interactive eyeballer (Stage B — separate spec)
- LLM-as-judge (future, once enough Julian judgments accumulate)
- Re-spending Haiku calls on the apt cohort (reusing the May 25 JSONL)
- Any new vocabulary curation (we use the existing curated synsets, drop on snap miss)
- Multi-sense topic disambiguation beyond `snap_concept_string`'s default-pick
- Vehicle synonym detection (if Sonnet writes "fire" and Haiku writes "flame", they're different vehicles — eyeballer can flag, not us)
- Backfill of `metaphor_judgments` (no judgments written here)

## Settled decisions

| Decision | Outcome |
|----------|---------|
| Stage A vs B coupling | Decoupled. Stage A is batch enrichment, no UI. Stage B is interactive eyeballer, separate spec. |
| Form factor | Stage A = scripts (no UI). Stage B = CLI (later). |
| Proposer scope | Cascade + Haiku + Haiku-Sonnet (separately recorded, β shape). |
| Topic cohort | 200 Karpathy Loop 2 topics from `spike_2_topics.json`. |
| Haiku reuse | Yes — ingest existing `metaphor_spike_apt_phase2_20260525T004154.jsonl`, no re-spend. |
| Inapt cohort | Synthesise single-step weak-dim path via cheap LLM call, ingest as separate proposer `haiku_v1_inapt_synthesised`. |
| Sonnet shape | Full editorial rewrite per topic (vehicles + paths editable). |
| Batch size | 20 topics × 10 batches = 200. |
| Branch base | Off `metaphor-graph/schema-base`. |

## Judgement-call additions (beyond what was explicitly discussed)

These are decisions I made while writing the spec — flag any you want to change:

1. **Separate `haiku_v1_inapt_synthesised` proposer** rather than tagging within `haiku_v1`. Keeps the apt pool clean; eyeballer can show/hide synthesised-inapt bridges as a class.
2. **Synthesis idempotency via a JSONL log file** (`haiku_v1_inapt_synthesised_paths.jsonl`) so re-runs don't re-spend the LLM call on entries already extracted.
3. **Batch boundary = single transaction per proposer per batch**. Crash mid-batch reverts just that proposer's batch slice; cleaner recovery than per-topic commits.
4. **Per-batch progress markdown** at `data-pipeline/output/metaphor_graph_enrich_progress.md`, append-only. Lets you eyeball batch outcomes without querying the DB.
5. **Topic snap drop-out > 10% surfaces as a finding** rather than continuing silently. If `snap_concept_string` can't resolve ~20+ topics that's a curated-vocab gap worth knowing about before sinking LLM money.
6. **Cascade harness reuses `loop1_eyeball_harness.py`'s subprocess pattern** (Go binary on free port, query, kill) rather than calling production. Keeps Stage A deterministic and not coupled to deploy state.
