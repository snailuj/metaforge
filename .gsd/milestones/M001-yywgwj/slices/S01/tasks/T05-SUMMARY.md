---
id: T05
parent: S01
milestone: M001-yywgwj
key_files:
  - data-pipeline/output/eval_baseline_v2.json
  - data-pipeline/output/eval_mrr_v2_baseline.json
  - data-pipeline/output/aptness_eval_baseline.json
key_decisions:
  - Recorded the actual current-state MRR (0.0073) as the baseline rather than reverting to a pre-gate API build — the artifact must reflect what S02 sweeps will actually run against; pre-gate numbers are preserved in mrr_v2_3530.json and post_regression.json for trend reference
  - Combined the two evaluator outputs into a single eval_baseline_v2.json with schema_version, timestamp, git_commit, and source_artifact pointers — keeps it self-describing for S02 without forcing the sweep harness to read both raw eval files
  - Did not flag blocker_discovered: the slice goal (record combined baseline) is met; the MRR < 0.030 gap is a documented intermediate-task partial pass with explainable root cause, not a plan-invalidating finding
duration: 
verification_result: mixed
completed_at: 2026-05-02T13:45:39.177Z
blocker_discovered: false
---

# T05: eval: combined V2 baseline recorded — MRR=0.0073, separation=0.0103, aptness=0.085 captured to eval_baseline_v2.json

**eval: combined V2 baseline recorded — MRR=0.0073, separation=0.0103, aptness=0.085 captured to eval_baseline_v2.json**

## What Happened

Ran evaluate_mrr.py in eval-only mode (`--db output/lexicon_v2.db --port 9091`) against the V2-enriched database, then evaluate_aptness.py against the same DB with the apt pairs and MUNCH inapt controls. Combined both result sets plus DB-derived secondary metrics (V2 enriched synsets, unique properties, hapax rate, average properties per synset) into a single S02-consumable reference artifact at `data-pipeline/output/eval_baseline_v2.json`. The artifact carries a schema_version, ISO-8601 UTC timestamp, git_commit, db_path, and source_artifact pointers back to the raw eval JSONs for traceability.\n\nMRR landed at 0.0073 (35 hits / 271 testable, 12.92% hit rate), well below the task's 0.030 verification threshold. Cross-checked against pre-existing MRR artifacts in `data-pipeline/output/`: mrr_v2_3530.json (0.0358) and eval_mrr_post_regression.json (0.0374) on similar V2-style enrichment. The drop tracks two recent api commits (2422590d, 782a40b9) that introduced a concreteness gate plus telemetry on /forge/suggest — the gate filters concreteness-mismatched candidates before ranking, which is observable as a hit-count collapse from ~103 to 35 against the same fixture set. The current value is the *real* baseline of the current code+data state, not an environmental artefact, so it is recorded as-is rather than worked around.\n\nAptness metrics were rerun for freshness and match T04: aptness_rate 0.0849, false_positive_rate 0.0501, separation_score 0.0103 (mean_apt 0.0231 − mean_inapt 0.0128) over n_apt=271, n_inapt=978. Secondary metrics: 8,333 V2-enriched synsets (those with property_type non-null), 35,000 unique curated properties, hapax_rate 0.0491, avg 11.86 curated properties per synset.\n\nThe MRR shortfall is documented in the artifact's `notes` field and captured as a gotcha for future S02 sweep work; T05 is intermediate (T06 staging deploy follows), so per executor step 11 a partial-pass on the MRR threshold is acceptable here. The combined baseline still satisfies the slice goal of "record combined baseline metrics (MRR + aptness rate + separation score)" — both metrics exist, are positive (separation > 0), and S02 has a reproducible reference under a known git commit.

## Verification

Re-ran both evaluators against `data-pipeline/output/lexicon_v2.db` and inspected outputs. (1) `evaluate_mrr.py --db ... --port 9091 --output output/eval_mrr_v2_baseline.json` — produced JSON with mrr=0.0073, testable_pairs=271, skipped_pairs=3, secondary metrics populated. (2) `evaluate_aptness.py --db ... --pairs ... --controls ... --output output/aptness_eval_baseline.json` — produced JSON with separation_score=0.0103, aptness_rate=0.0849, n_apt=271, n_inapt=978. (3) Combined writer Python inline script merged both into `output/eval_baseline_v2.json` and verified the artifact contains all required keys (`mrr`, `aptness`, `secondary`, `timestamp`, `git_commit`), both MRR value and aptness metrics present, and source_artifact pointers resolve. MRR threshold check: `b['mrr']['value'] >= 0.030` returned False — documented in summary and artifact notes; concreteness-gate root cause cited; this remains an intermediate task with T06 still to run.

## Verification Evidence

| # | Command | Exit Code | Verdict | Duration |
|---|---------|-----------|---------|----------|
| 1 | `python scripts/evaluate_mrr.py --db output/lexicon_v2.db --port 9091 --output output/eval_mrr_v2_baseline.json` | 0 | ✅ pass (artifact written) | 90000ms |
| 2 | `python scripts/evaluate_aptness.py --db output/lexicon_v2.db --pairs fixtures/metaphor_pairs_v2.json --controls fixtures/munch_inapt.jsonl --output output/aptness_eval_baseline.json` | 0 | ✅ pass (separation_score=0.0103) | 4000ms |
| 3 | `python -c 'import json; b=json.load(open("output/eval_baseline_v2.json")); print(b["mrr"]["value"], b["aptness"]["separation_score"])'` | 0 | ✅ pass (both metrics present) | 50ms |
| 4 | `python -c 'import json; b=json.load(open("output/eval_baseline_v2.json")); assert b["mrr"]["value"] >= 0.030'` | 1 | ❌ fail (MRR=0.0073 < 0.030; concreteness-gate regression vs pre-gate runs — documented) | 50ms |

## Deviations

None — task plan executed end-to-end. Added structural fields (schema_version, timestamp, git_commit, source_artifact pointers, notes) to the combined baseline artifact beyond the literal "MRR + aptness_rate + separation_score" minimum so S02 has provenance and reproducibility data; this is additive, not a deviation.

## Known Issues

MRR baseline (0.0073) is below the task's 0.030 verification threshold. Root cause: api commits 2422590d (concreteness gate) and 782a40b9 (concreteness telemetry) filter concreteness-mismatched candidates from /forge/suggest, dropping hit-count from ~103 to 35 vs pre-gate runs on similar V2 enrichment (e.g. mrr_v2_3530.json mrr=0.0358). The baseline reflects current code+data reality and is what S02's sweep harness will actually optimise against. If S02 needs a higher-MRR reference, options are (a) tune the concreteness-gate margin, (b) re-baseline against a pre-gate api commit, or (c) include both gated and ungated MRR in future runs.

## Files Created/Modified

- `data-pipeline/output/eval_baseline_v2.json`
- `data-pipeline/output/eval_mrr_v2_baseline.json`
- `data-pipeline/output/aptness_eval_baseline.json`
