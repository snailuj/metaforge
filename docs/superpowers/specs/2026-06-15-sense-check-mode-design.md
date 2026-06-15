# Sense-Check Mode — Metaphor Grading Tool

**Date:** 2026-06-15
**Status:** Design (approved by operator; pending spec review)
**Branch:** `grading/sense-check-mode`

## Motivation

The Gloss Reconciliation pass (2026-06-15) found ~5% of chain endpoints snapped to the **wrong WordNet sense** — systematically, because the lemma resolver picks the lowest-id noun synset, which for emotion/state words is often a process-nominal ("the act of X") rather than the felt state (`apprehension`→arrest, `tension`→stretching). Topics 21/277 (7.6%), vehicles 79/1771 (4.5%). See `docs/inbox/2026-06-15-gloss-reconciliation-endpoints.md` and `data-pipeline/grading/sense_flags_provisional.jsonl`.

That finding came from an LLM subagent of **unmeasured accuracy**. We cannot evaluate a snapping fix against an unvalidated oracle: its precision is unknown, and — worse — its recall is unknown, so wrong-sense snaps it rated OK would remain as silent, unquantified noise.

This feature anchors sense-correctness to the **operator's human judgement**, exactly as the judge harness anchors liveness/linkage to the operator's verdicts. The subagent's flags become a cheap pre-sorter; the operator becomes ground truth. From a small human-labelled sample we can then measure: the true contamination rate (with a CI), the subagent's precision/recall, the silent-noise (false-negative) rate, and — crucially — the accuracy of any deterministic re-snapper, all in the operator's terms.

## Goal / Non-goals

**Goal:** a self-contained "sense-check" mode in the grading UI where the operator labels a stratified sample of chain **endpoints** as right/wrong sense (plus the intended sense), persisting to a separate provisional file that anchors downstream sense measurement and gold-cleaning.

**Non-goals (separate specs/plans):**
- The offline analysis harness (subagent precision/recall, contamination CI, silent-noise rate, re-snapper accuracy).
- The Gloss-Matched Snapper itself (tagcount + domain + gloss-match re-snap).
- Chain *step* sense-checking — the Step-Snap Audit, deferred to the Phrase-as-Node architecture work. This feature covers **endpoints only** (topic + vehicle).

## Architecture

Mirrors the blind re-grade feature (`mf-grade-regrade` + `routes/regrade.py` + a separate provisional file), the closest precedent: a self-contained view whose output must never mix with the gold judgements.

### Component — `mf-grade-sensecheck` (web)

A self-contained Lit component, mounted by `mf-app` as a 4th grade view alongside grade / walk / regrade. Props: `client` (a `Pick<>` of the sense-check client methods) and `glosses` (the existing `GlossMap`). Owns its own sample, cursor, and POSTs — like `mf-grade-regrade`, because its labels go to a separate file.

Phases: `idle → loading → labelling → done → error` (same shape as regrade).

**Per-item UI:**
- Always visible: `word · role · snapped gloss` (role = topic | vehicle).
- Verdict buttons: **Right / Wrong / Rare-but-better / Unsure**.
- On **Wrong** or **Rare-but-better**: a candidate-sense list unfolds — every WordNet sense of the lemma as `pos · gloss · tagcount` — and the operator taps the intended one (sets `intended_synset_id`).
- **Context** affordance (expandable, collapsed by default): reveals the pairing (topic → vehicle) and the chain(s) in which this endpoint appears, so the operator can resolve the sense against the metaphor the endpoint is serving. A distinct sense can occur in several chains, so it is chain*s*.
- On submit: POST the label, advance the cursor.

### Routes — `routes/sense_check.py` (sidecar, thin IO)

- `GET /api/grading/sense-check/sample?n_flagged&n_random&seed` → the stratified sample; each item carries `{role, word, snapped_synset_id, snapped_gloss, pos, candidates:[…], context:{pairing, chains}}`.
- `POST /api/grading/sense-check` → append one label to the separate file.

Both gated by `verify_secret` (bypassed in dev), like every grading route. Sampler + stratification maths live in a `grading_sidecar.sense_check` module; routes are thin wiring (mirrors `regrade.py` delegating to `regrade`).

### Sampling (live, seeded — `grading_sidecar/sense_check.py`)

Stratified draw over **distinct** endpoints `(role, word, snapped_synset_id)`:
- `n_flagged` drawn from `sense_flags_provisional.jsonl` (the subagent's WRONG_SENSE + RARE_OK rows).
- `n_random` drawn from the **unflagged** distinct endpoints (present in the chain files, absent from the flags). This OK stratum is what lets the analysis estimate the false-negative / silent-noise rate.
- Seeded for reproducibility (a fresh seed per session, like regrade). Already-labelled endpoints are excluded so successive sessions broaden coverage.
- Defaults: `n_flagged=40`, `n_random=40` (the agreed ~80-item first cut), expandable from the same view ("label another batch").

### Precompute — `sense_candidates_provisional.jsonl` (offline, DB-free sidecar)

`lemma → [{synset_id, pos, gloss, tagcount}]` for every lemma that can appear in the sample. Generated offline from the typed lexicon (`lexicon_v2.db`: `synsets` for gloss/pos, `sense_attributes.tagcount` for the dominant-sense prior), exactly like the `chain_glosses` precompute. The sidecar reads the file; it never touches the DB. Absence degrades the candidate list to "snapped sense only" (the operator can still mark Right/Wrong/Unsure, just cannot pick an intended sense), logged as a warning.

A small generator script — `data-pipeline/scripts/build_sense_candidates.py` — produces it from the chain endpoints' lemmas.

### Persistence — `sense_labels_provisional.jsonl` (new `paths` constant)

Append-only, one label per line:

```
{role, word, snapped_synset_id, verdict, intended_synset_id, chain_signature, ts}
```

- `verdict ∈ {right, wrong, rare_ok, unsure}`.
- `intended_synset_id`: set only for `wrong` / `rare_ok`; `null` otherwise.
- `chain_signature`: a representative chain the endpoint appeared in (traceability back to context); the label is keyed on the endpoint, not the chain.
- Latest-wins per `(role, word, snapped_synset_id)`.

Same separate-file safety property as `REGRADES_PATH`: never `JUDGEMENTS_PATH`. The `paths` comment will state why — a sense label is not a liveness/linkage verdict and must never be resolved as one.

## Data flow

```
offline:  chain endpoints ─ build_sense_candidates.py ─→ sense_candidates_provisional.jsonl
          Gloss Reconciliation subagent ─→ sense_flags_provisional.jsonl   (already produced)

request:  GET sample ─ sense_check.sample(flags, chains, labels, seed) ─→ stratified items
                       + candidates (precompute) + context (chains)        → mf-grade-sensecheck
submit:   POST label ─ append_jsonl ─→ sense_labels_provisional.jsonl       (separate file)
```

## Error handling

- POST failure: do not advance the cursor; surface the error, let the operator retry (no lost label) — same as regrade's `_onVerdict`.
- Missing candidate precompute: serve items with empty `candidates`, log a warning; the UI hides the intended-sense picker (Right/Wrong/Unsure still work).
- Sampled endpoint with no surviving chain (pruned line): skip it, do not 500 (mirrors regrade's missing-chain handling).
- Malformed lines in any provisional file: `read_jsonl_skip_malformed`.

## Testing (TDD)

**Python (sidecar):**
- Sampler: stratification (flagged vs random counts), seed determinism, exclusion of already-labelled endpoints, distinct-endpoint dedup.
- The separate-file invariant: a posted label lands in `SENSE_LABELS_PATH` and never in `JUDGEMENTS_PATH`.
- Candidate precompute loader shape; graceful degradation when absent.
- Route wiring: sample shape (candidates + context present), POST append.

**Web (happy-dom, mocked client):**
- Component phases (idle/loading/labelling/done/error).
- Verdict → on Wrong/Rare the candidate list appears, and selecting one sets `intended_synset_id` in the POST payload.
- Context expand shows the pairing + chains.
- POST goes to the sense-check client method (separate file); cursor advances; POST failure keeps the item.

## Judgement-call defaults (operator may veto)

- **80-item first cut** (40 flagged + 40 random-OK), expandable.
- **Reliability floor deferred** — sense calls are more objective than liveness; add a blind re-label slice only if consistency is later in doubt (the regrade machinery already exists).
- **Endpoints only** — chain steps go through the Step-Snap Audit under Phrase-as-Node.

## Follow-ups (out of scope here)

1. Offline analysis harness → subagent precision/recall, true contamination rate (CI), silent-noise rate, re-snapper accuracy — all against these human labels.
2. Gloss-Matched Snapper (tagcount + domain + gloss-match), evaluated against these labels, not the subagent.
3. Step-Snap Audit (Phrase-as-Node).
