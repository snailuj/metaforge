---
estimated_steps: 1
estimated_files: 4
skills_used: []
---

# T02: Verify data integrity and run test suites

Validate V2 data quality: check salience distribution spans 0.3-1.0 (not all defaults), all 6 property types present (physical, behaviour, effect, functional, emotional, social), snap accumulation producing meaningful salience_sum values in curated table. Run Python test suite (data-pipeline) and Go test suite (api/) to confirm no regressions from the V2-populated database.

## Inputs

- `data-pipeline/output/lexicon_v2.db`

## Expected Output

- `All tests green`
- `Salience distribution summary`

## Verification

python -m pytest data-pipeline/scripts/ -v passes; cd api && go test ./... passes; salience distribution check shows values across 0.3-1.0 range
