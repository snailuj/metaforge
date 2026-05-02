# S01: V2 Foundation + Aptness Evaluator

**Goal:** Import 10,530 V2-enriched synsets, acquire and preprocess the MUNCH dataset (CC BY 4.0), build a discriminative aptness evaluator calibrated against MUNCH inapt controls, record combined baseline metrics (MRR + aptness rate + separation score), and deploy to staging.
**Demo:** Run aptness evaluator on 50 known-good pairs + 50 MUNCH inapt controls, display per-pair scores and aggregate separation statistics alongside V2 baseline MRR

## Must-Haves

- synset_properties has V2 columns populated (salience != 1.0 default, property_type non-null) for >= 10,000 synsets; MUNCH dataset cloned and preprocessed into evaluator-ready format; aptness evaluator separates apt from inapt controls with > 0.3 separation score; baseline metrics recorded as JSON artifact; staging forge endpoint returns salience-weighted results

## Proof Level

- This slice proves: V2 import verified by data integrity checks and test suites; evaluator verified by running against known apt + MUNCH inapt pairs with measurable separation; staging verified by health check and API response inspection

## Integration Closure

V2 database deployed to staging; evaluator script callable from S02 sweep harness with consistent input/output contract (JSON in, JSON out); baseline artifact provides reference for all future comparisons

## Verification

- Eval results logged as structured JSON artifacts with timestamps for trend tracking

## Tasks

- [ ] **T01: Import V2 enrichment JSON into database** `est:30m`
  Run enrich.sh with both V2 enrichment files (enrichment_4000_sonnet_v2_20260224.json + enrichment_8000_sonnet_v2_20260306.json) to populate the database with structured properties. The pipeline restores from PRE_ENRICH.sql, imports V2 JSON, applies schema migrations (salience, property_type, relation columns), snaps to curated vocabulary with salience accumulation, and exports the updated SQL dump. Skip the test duplicate file.
  - Files: `data-pipeline/enrich.sh`, `data-pipeline/scripts/enrich_pipeline.py`, `data-pipeline/output/lexicon_v2.db`
  - Verify: sqlite3 lexicon_v2.db 'SELECT COUNT(*) FROM synset_properties WHERE salience != 1.0' returns >= 10000; sqlite3 lexicon_v2.db 'SELECT COUNT(DISTINCT property_type) FROM synset_properties WHERE property_type IS NOT NULL' returns 6

- [ ] **T02: Verify data integrity and run test suites** `est:15m`
  Validate V2 data quality: check salience distribution spans 0.3-1.0 (not all defaults), all 6 property types present (physical, behaviour, effect, functional, emotional, social), snap accumulation producing meaningful salience_sum values in curated table. Run Python test suite (data-pipeline) and Go test suite (api/) to confirm no regressions from the V2-populated database.
  - Files: `data-pipeline/scripts/test_enrich_pipeline.py`, `data-pipeline/scripts/test_enrich_properties.py`, `api/internal/db/db_test.go`, `api/internal/forge/forge_test.go`
  - Verify: python -m pytest data-pipeline/scripts/ -v passes; cd api && go test ./... passes; salience distribution check shows values across 0.3-1.0 range

- [ ] **T03: Acquire and preprocess MUNCH dataset** `est:30m`
  Clone the MUNCH dataset from github.com/xiaoyuisrain/metaphor-understanding-challenge (CC BY 4.0). Parse the JSON/CSV files to extract apt paraphrases (10,261) and inapt controls (1,492). Preprocess into a standardised evaluator-ready format: JSON lines with fields for metaphor text, paraphrase, aptness label (apt/inapt), and genre. Store in data-pipeline/fixtures/.
  - Files: `data-pipeline/fixtures/munch_apt.jsonl`, `data-pipeline/fixtures/munch_inapt.jsonl`, `data-pipeline/scripts/preprocess_munch.py`
  - Verify: wc -l munch_apt.jsonl returns >= 10000; wc -l munch_inapt.jsonl returns >= 1400; python -c to validate JSON structure of first 10 lines of each file

- [ ] **T04: Build discriminative aptness evaluator** `est:1h`
  Build a Python script that scores metaphor pairings as apt or inapt. The evaluator takes a list of (target, vehicle) pairs, runs them through the forge scoring pipeline, and classifies each as apt or inapt using MUNCH-calibrated thresholds. Primary metrics: aptness rate (proportion of top-10 results classified apt), separation score (mean apt score minus mean inapt control score). Uses existing forge API or direct DB queries for scoring. Outputs structured JSON with per-pair scores and aggregate statistics.
  - Files: `data-pipeline/scripts/evaluate_aptness.py`, `data-pipeline/scripts/test_evaluate_aptness.py`
  - Verify: python evaluate_aptness.py --pairs data-pipeline/fixtures/metaphor_pairs_v2.json --controls data-pipeline/fixtures/munch_inapt.jsonl produces JSON output with separation_score > 0.0; test suite passes

- [ ] **T05: Record baseline metrics and save as reference artifact** `est:30m`
  Run both evaluate_mrr.py and the new evaluate_aptness.py against the V2-enriched database to establish combined baseline metrics. Save results as a JSON artifact that S02's sweep harness will use as the reference baseline. Record: MRR, hit rate, aptness rate, separation score, unique property count, hapax rate, average properties per synset.
  - Files: `data-pipeline/scripts/evaluate_mrr.py`, `data-pipeline/scripts/evaluate_aptness.py`, `data-pipeline/fixtures/metaphor_pairs_v2.json`
  - Verify: Baseline JSON artifact exists at data-pipeline/output/eval_baseline_v2.json; contains both MRR and aptness metrics; MRR value >= 0.030

- [ ] **T06: Deploy V2 database to staging** `est:15m`
  Deploy the V2-enriched database to metaforge-next.julianit.me via deploy/staging/deploy.sh. Verify the forge endpoint returns results with salience weighting visible in the response. Confirm health check passes and the staging site serves the updated data independently of production.
  - Files: `deploy/staging/deploy.sh`, `data-pipeline/output/lexicon_v2.db`
  - Verify: curl -s metaforge-next.julianit.me/forge/suggest?word=anger | jq '.suggestions[0].salience_sum' returns a non-zero value; curl -s metaforge-next.julianit.me/health returns 200

## Files Likely Touched

- data-pipeline/enrich.sh
- data-pipeline/scripts/enrich_pipeline.py
- data-pipeline/output/lexicon_v2.db
- data-pipeline/scripts/test_enrich_pipeline.py
- data-pipeline/scripts/test_enrich_properties.py
- api/internal/db/db_test.go
- api/internal/forge/forge_test.go
- data-pipeline/fixtures/munch_apt.jsonl
- data-pipeline/fixtures/munch_inapt.jsonl
- data-pipeline/scripts/preprocess_munch.py
- data-pipeline/scripts/evaluate_aptness.py
- data-pipeline/scripts/test_evaluate_aptness.py
- data-pipeline/scripts/evaluate_mrr.py
- data-pipeline/fixtures/metaphor_pairs_v2.json
- deploy/staging/deploy.sh
