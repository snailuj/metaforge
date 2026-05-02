---
estimated_steps: 1
estimated_files: 3
skills_used: []
---

# T05: Record baseline metrics and save as reference artifact

Run both evaluate_mrr.py and the new evaluate_aptness.py against the V2-enriched database to establish combined baseline metrics. Save results as a JSON artifact that S02's sweep harness will use as the reference baseline. Record: MRR, hit rate, aptness rate, separation score, unique property count, hapax rate, average properties per synset.

## Inputs

- `data-pipeline/output/lexicon_v2.db`
- `data-pipeline/fixtures/metaphor_pairs_v2.json`
- `data-pipeline/fixtures/munch_inapt.jsonl`

## Expected Output

- `data-pipeline/output/eval_baseline_v2.json with MRR + aptness_rate + separation_score`

## Verification

Baseline JSON artifact exists at data-pipeline/output/eval_baseline_v2.json; contains both MRR and aptness metrics; MRR value >= 0.030
