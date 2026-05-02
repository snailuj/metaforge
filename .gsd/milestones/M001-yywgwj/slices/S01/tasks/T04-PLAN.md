---
estimated_steps: 1
estimated_files: 2
skills_used: []
---

# T04: Build discriminative aptness evaluator

Build a Python script that scores metaphor pairings as apt or inapt. The evaluator takes a list of (target, vehicle) pairs, runs them through the forge scoring pipeline, and classifies each as apt or inapt using MUNCH-calibrated thresholds. Primary metrics: aptness rate (proportion of top-10 results classified apt), separation score (mean apt score minus mean inapt control score). Uses existing forge API or direct DB queries for scoring. Outputs structured JSON with per-pair scores and aggregate statistics.

## Inputs

- `data-pipeline/fixtures/metaphor_pairs_v2.json`
- `data-pipeline/fixtures/munch_inapt.jsonl`
- `data-pipeline/output/lexicon_v2.db`

## Expected Output

- `data-pipeline/scripts/evaluate_aptness.py`
- `Structured JSON output with aptness_rate, separation_score, per_pair_scores`

## Verification

python evaluate_aptness.py --pairs data-pipeline/fixtures/metaphor_pairs_v2.json --controls data-pipeline/fixtures/munch_inapt.jsonl produces JSON output with separation_score > 0.0; test suite passes
