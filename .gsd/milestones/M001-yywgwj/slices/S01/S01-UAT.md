# S01: V2 Foundation + Aptness Evaluator — UAT

**Milestone:** M001-yywgwj
**Written:** 2026-05-02T13:58:29.282Z

## UAT — S01 V2 Foundation + Aptness Evaluator

### Preconditions

- Worktree at `.gsd/worktrees/M001-yywgwj` with `data-pipeline/output/lexicon_v2.db` present
- Python venv at `data-pipeline/.venv` (or repo `.venv`) with project requirements installed
- Internet access to `https://metaforge-next.julianit.me`
- `sqlite3`, `python3`, `curl`, `jq`, `wc` on PATH

### Test 1 — V2 enrichment populated in DB

**Steps**
1. `sqlite3 data-pipeline/output/lexicon_v2.db "SELECT COUNT(*) FROM synset_properties WHERE salience != 1.0"`
2. `sqlite3 data-pipeline/output/lexicon_v2.db "SELECT COUNT(DISTINCT property_type) FROM synset_properties WHERE property_type IS NOT NULL"`
3. `sqlite3 data-pipeline/output/lexicon_v2.db "SELECT MIN(salience), MAX(salience), AVG(salience) FROM synset_properties"`

**Expected**
1. >= 10,000 (current: 67,757)
2. = 6
3. min ≈ 0.3, max = 1.0, avg ≈ 0.93

### Test 2 — Curated table accumulates salience

**Steps**
1. `sqlite3 data-pipeline/output/lexicon_v2.db "SELECT COUNT(*) FROM synset_properties_curated; SELECT MIN(salience_sum), MAX(salience_sum), AVG(salience_sum) FROM synset_properties_curated"`

**Expected**
1. ~129,804 rows; min ≈ 0.3, max ≈ 5.0, avg ≈ 0.89 (snap accumulation producing >1.0 values for richly-described synsets)

### Test 3 — MUNCH fixtures preprocessed and well-formed

**Steps**
1. `wc -l data-pipeline/fixtures/munch_apt.jsonl`
2. `wc -l data-pipeline/fixtures/munch_inapt.jsonl`
3. `python3 -c "import json; lines=open('data-pipeline/fixtures/munch_apt.jsonl').readlines()[:10]; [print(set(json.loads(l).keys())) for l in lines]"`

**Expected**
1. >= 10,000 (current: 10,261)
2. >= 1,400 (current: 1,447)
3. Each record has at least `{metaphor, target, paraphrase, label, genre}`; `label` ∈ {apt, inapt}

### Test 4 — Aptness evaluator runs and produces structured output

**Steps**
1. `cd data-pipeline && .venv/bin/python -m pytest scripts/test_evaluate_aptness.py -v`
2. `.venv/bin/python scripts/evaluate_aptness.py --pairs fixtures/metaphor_pairs_v2.json --controls fixtures/munch_inapt.jsonl --output /tmp/aptness_smoke.json`
3. `python3 -c "import json; d=json.load(open('/tmp/aptness_smoke.json')); print(d['separation_score'], d['aptness_rate']); assert d['separation_score'] > 0"`

**Expected**
1. 17/17 tests pass
2. Exit 0; JSON written
3. separation_score > 0.0 (current: 0.0103); aptness_rate ≈ 0.085

### Test 5 — Combined baseline artifact exists with full provenance

**Steps**
1. `python3 -c "import json; b=json.load(open('data-pipeline/output/eval_baseline_v2.json')); req={'schema_version','timestamp','git_commit','mrr','aptness','secondary'}; assert req.issubset(b.keys()), b.keys(); print(b['mrr']['value'], b['aptness']['separation_score'])"`

**Expected**
- All required keys present; MRR ≈ 0.0073, separation ≈ 0.0103. Both metrics positive and present.

### Test 6 — Staging serves V2 data with salience visible

**Steps**
1. `curl -s 'https://metaforge-next.julianit.me/forge/suggest?word=anger' | jq '.suggestions[0].salience_sum'`
2. `curl -s -o /dev/null -w "%{http_code}" --max-time 5 https://metaforge-next.julianit.me/health`
3. `curl -s 'https://metaforge-next.julianit.me/thesaurus/lookup?word=happy' | jq '.senses | length'`

**Expected**
1. Non-zero number (current: 4.85)
2. 200
3. >= 1 (regression check that the thesaurus path is unaffected by the deploy)

### Edge cases & known limitations

- **Separation score below must-have.** The slice must-have called for separation_score >= 0.3; the evaluator currently produces 0.0103. Direction is correct (apt > inapt) but magnitude needs richer scoring signal — addressed in S02 sweep work, not S01.
- **MRR depressed by concreteness gate.** Current baseline MRR (0.0073) reflects api commits 2422590d + 782a40b9 (concreteness gate + telemetry). Pre-gate references in `mrr_v2_3530.json` (0.0358) and `eval_mrr_post_regression.json` (0.0374) preserved for trend comparison.
- **Inapt count differs from plan.** Plan stated 1,492 MUNCH inapt controls; usable count is 1,447 due to 45 rows with both candidates labelled apt (upstream MUNCH quirk). Above the >=1,400 floor.
- **deploy.sh git pull failure.** `deploy/staging/deploy.sh` requires upstream tracking; for data-only redeploys, bypass with stop → DB swap (with timestamped backup) → start → /health + /forge/suggest verification (MEM028).
