---
id: T03
parent: S02
milestone: M001-yywgwj
key_files:
  - data-pipeline/sweeps/baseline_v2.yaml
  - data-pipeline/sweeps/README.md
  - .gitignore
key_decisions:
  - Installed PyYAML in data-pipeline/.venv to make the YAML sweep config loadable; system python3 already has yaml 6.0.1 so the verification gate can load it without venv activation. Did NOT add PyYAML to requirements.txt because T02 deliberately kept it as an optional dep — only sweep configs need it, and JSON configs work without.
  - Added data-pipeline/output/sweep_*.json and sweep_*.md to .gitignore (not the broader data-pipeline/output/*.json) so existing tracked eval JSONs stay tracked. Matches S01's pattern of committing config + schema, not raw output.
  - Did not block on negative separation_scores per task plan's explicit guidance — slice is about harness contract, not formula tuning.
duration: 
verification_result: passed
completed_at: 2026-05-02T15:35:50.554Z
blocker_discovered: false
---

# T03: feat(sweeps): commit baseline_v2.yaml + sweeps/README and demo run_sweep across jaccard_salience, jaccard_raw, cosine_salience on V2 DB

**feat(sweeps): commit baseline_v2.yaml + sweeps/README and demo run_sweep across jaccard_salience, jaccard_raw, cosine_salience on V2 DB**

## What Happened

Defined the slice's stated 3-variation baseline sweep against the live V2 lexicon and ran it end-to-end through the harness built in T02.

Created `data-pipeline/sweeps/baseline_v2.yaml` with three variations all at `threshold_percentile: 95`: `jaccard_salience` (current S01 baseline), `jaccard_raw` (control — does salience weighting help?), and `cosine_salience` (alternative formula motivated by S01's separation_score=0.0103 follow-up note). Pointed `mrr_reference` at `data-pipeline/output/eval_baseline_v2.json` so the joint MRR baseline (0.0073) appears in the report. Added a header comment in the YAML linking back to the slice goal and the S01 separation anchor. Created `data-pipeline/sweeps/README.md` (~30 lines) documenting how to add a sweep, how to run it, where artifacts go, and the gitignore policy.

Installed PyYAML into `data-pipeline/.venv` because the YAML config requires it (T02 deliberately kept PyYAML as an optional lazy import — see T02 decision). System python3 already had PyYAML 6.0.1, which means the verification gate (which does not source the venv) can also load the YAML config.

Updated `.gitignore` to add `data-pipeline/output/sweep_*.json` and `data-pipeline/output/sweep_*.md` so the reproducible artifacts stay out of git, matching S01's pattern of not committing eval JSON outputs.

Ran the sweep end-to-end: all 3 variations completed with `status: ok`, JSON has the expected provenance block (`git_commit=a2376e90`, timestamp, db_path, config_path, mrr_reference_value=0.0073), markdown report has 3 ranked data rows ordered by separation_score DESC, and per-variation INFO logs landed for start/finish/timing/score counts. Wall-clock was ~13.75 minutes (825414ms) — much higher than the plan's predicted "under 30 seconds" because aptness eval against the full V2 lexicon (1721 pairs+controls) is genuinely slow on this machine, but still well under the 30-minute slice ceiling. All three separation_scores came out negative (-0.0124, -0.0130, -0.0198) — per the task plan's explicit guidance, low/negative separation does NOT block: the slice is about the harness contract, not finding the winning formula. Numbers are noted here for S03/M2 follow-up tuning.

## Verification

Ran the sweep harness against the committed config: `data-pipeline/.venv/bin/python data-pipeline/scripts/run_sweep.py --config data-pipeline/sweeps/baseline_v2.yaml --output data-pipeline/output/sweep_baseline_v2.json --report data-pipeline/output/sweep_baseline_v2.md` → exit 0, INFO logs for each variation, both artifacts written. JSON shape verified: `len(d['variations'])==3`, all `status=='ok'`, `git_commit`/`timestamp`/`db_path`/`config_path` present at top level. Markdown row count: 4 (1 header + 3 data rows) via `grep -c '^| '`. Verified PyYAML loads in both venv and system python so the verification gate can run the same command. Three observed separation_scores: jaccard_salience=-0.0124 (aptness=0.0388), jaccard_raw=-0.0130 (aptness=0.0603), cosine_salience=-0.0198 (aptness=0.0474); MRR reference 0.0073.

## Verification Evidence

| # | Command | Exit Code | Verdict | Duration |
|---|---------|-----------|---------|----------|
| 1 | `data-pipeline/.venv/bin/python data-pipeline/scripts/run_sweep.py --config data-pipeline/sweeps/baseline_v2.yaml --output data-pipeline/output/sweep_baseline_v2.json --report data-pipeline/output/sweep_baseline_v2.md` | 0 | pass | 825414ms |
| 2 | `python -c 'import json; d=json.load(open("data-pipeline/output/sweep_baseline_v2.json")); assert len(d["variations"])==3; assert all(v.get("status")=="ok" for v in d["variations"]); assert d.get("git_commit")'` | 0 | pass | 80ms |
| 3 | `grep -c '^| ' data-pipeline/output/sweep_baseline_v2.md` | 0 | pass | 5ms |

## Deviations

Wall-clock ~13.75 min instead of plan's predicted "under 30 seconds". Aptness eval against the full V2 lexicon is genuinely slow on this machine; well under the 30-min ceiling and within the harness's expected operating envelope.

## Known Issues

All three variations produced negative separation_scores (apt mean < inapt mean). Task plan explicitly de-scopes this to S03/M2 — the salience-weighted property fingerprints don't currently separate apt from inapt metaphors at the 95th percentile threshold against the munch_inapt control set on the V2 DB. Possible causes for follow-up: control set composition, threshold percentile choice, or property-extraction quality on V2 vs V1.

## Files Created/Modified

- `data-pipeline/sweeps/baseline_v2.yaml`
- `data-pipeline/sweeps/README.md`
- `.gitignore`
