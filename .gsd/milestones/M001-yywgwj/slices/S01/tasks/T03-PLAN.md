---
estimated_steps: 1
estimated_files: 3
skills_used: []
---

# T03: Acquire and preprocess MUNCH dataset

Clone the MUNCH dataset from github.com/xiaoyuisrain/metaphor-understanding-challenge (CC BY 4.0). Parse the JSON/CSV files to extract apt paraphrases (10,261) and inapt controls (1,492). Preprocess into a standardised evaluator-ready format: JSON lines with fields for metaphor text, paraphrase, aptness label (apt/inapt), and genre. Store in data-pipeline/fixtures/.

## Inputs

- `github.com/xiaoyuisrain/metaphor-understanding-challenge (public, CC BY 4.0)`

## Expected Output

- `data-pipeline/fixtures/munch_apt.jsonl`
- `data-pipeline/fixtures/munch_inapt.jsonl`

## Verification

wc -l munch_apt.jsonl returns >= 10000; wc -l munch_inapt.jsonl returns >= 1400; python -c to validate JSON structure of first 10 lines of each file
