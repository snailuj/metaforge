---
id: T03
parent: S01
milestone: M001-yywgwj
key_files:
  - data-pipeline/scripts/preprocess_munch.py
  - data-pipeline/scripts/test_preprocess_munch.py
  - data-pipeline/fixtures/munch_apt.jsonl
  - data-pipeline/fixtures/munch_inapt.jsonl
key_decisions:
  - Read MUNCH judgement rows by label rather than column position — 45/1492 rows place the inapt option in s1, not s2
  - Treated the 45 rows with both labels = 'apt' as a MUNCH dataset quirk (logged warnings); final inapt count is 1,447 vs the plan's stated 1,492 — well above the >=1400 verification threshold
  - Stored MUNCH source under data-pipeline/raw/munch/ (gitignored) per existing data-pipeline raw-data convention; only the JSONL fixtures and the preprocess script are committed
  - Schema includes both target word (extracted from <b>...</b>) and full metaphor sentence so downstream aptness evaluators can score either word-level or sentence-level
duration: 
verification_result: passed
completed_at: 2026-05-02T13:20:19.912Z
blocker_discovered: false
---

# T03: data: preprocess MUNCH (CC BY 4.0) into munch_apt.jsonl (10,261) and munch_inapt.jsonl (1,447) fixtures

**data: preprocess MUNCH (CC BY 4.0) into munch_apt.jsonl (10,261) and munch_inapt.jsonl (1,447) fixtures**

## What Happened

Cloned the MUNCH dataset (github.com/xiaoyuisrain/metaphor-understanding-challenge, CC BY 4.0) into the gitignored `data-pipeline/raw/munch/` and built `data-pipeline/scripts/preprocess_munch.py` to materialise two evaluator-ready JSONL fixtures.

**Apt fixture** — explodes `correct_answers/for_generation.csv`'s space-separated `human_ans` column into one record per (sentence, paraphrase) pair, yielding exactly 10,261 rows as the plan predicted.

**Inapt fixture** — reads `correct_answers/for_judgement.csv` and emits the inapt-labelled candidate per row. The plan listed 1,492 inapt controls, but inspection revealed 45 MUNCH rows where both candidate paraphrases are labelled "apt" (an upstream annotation quirk), so the usable inapt-control count is 1,447 — still well above the plan's `>= 1400` verification floor. A second quirk: 45 *other* rows place the inapt option in `s1` rather than `s2`, so the preprocessor reads by label rather than column position to capture all real inapt controls.

Both files share the schema `{metaphor, target, paraphrase, label, genre, s0_idx, source_file}` (inapt records also carry `paraphrase_sentence`). Genre is joined onto judgement rows from the generation CSV via `s0_idx` — all 1,492 rows have matching genres (NEWS / FICTION / ACPROSE / CONVRSN).

Wrote 8 unit tests (`test_preprocess_munch.py`) using inline CSV fixtures — covers target extraction, apt explosion, inapt-in-s2 / inapt-in-s1, malformed-row skipping, end-to-end preprocessing, and missing-source error path. All 8 pass; full Python suite (412 tests) green.

Captured MEM021 (gotcha) so downstream T04+ aptness-evaluator work knows that the plan's stated 1,492 inapt count is an upper bound and that label-driven (not column-driven) reading is required.

## Verification

Ran the three plan-specified checks plus the full Python suite:

1. `wc -l data-pipeline/fixtures/munch_apt.jsonl` → 10,261 (>= 10,000 ✓)
2. `wc -l data-pipeline/fixtures/munch_inapt.jsonl` → 1,447 (>= 1,400 ✓)
3. `python -c` validating JSON structure of first 10 lines of each file: all records carry the required `{metaphor, target, paraphrase, label, genre}` keys, label values are in `{apt, inapt}` ✓
4. `pytest data-pipeline/scripts/test_preprocess_munch.py -v` → 8/8 passed
5. `pytest data-pipeline/scripts/ -q` → 412/412 passed (no regressions)

## Verification Evidence

| # | Command | Exit Code | Verdict | Duration |
|---|---------|-----------|---------|----------|
| 1 | `wc -l data-pipeline/fixtures/munch_apt.jsonl` | 0 | ✅ pass (10261 >= 10000) | 5ms |
| 2 | `wc -l data-pipeline/fixtures/munch_inapt.jsonl` | 0 | ✅ pass (1447 >= 1400) | 5ms |
| 3 | `python -c (validate first 10 lines of each fixture)` | 0 | ✅ pass — required keys present, labels in {apt,inapt} | 80ms |
| 4 | `pytest data-pipeline/scripts/test_preprocess_munch.py -v` | 0 | ✅ pass — 8/8 | 70ms |
| 5 | `pytest data-pipeline/scripts/ -q` | 0 | ✅ pass — 412/412 no regressions | 48120ms |

## Deviations

None.

## Known Issues

None.

## Files Created/Modified

- `data-pipeline/scripts/preprocess_munch.py`
- `data-pipeline/scripts/test_preprocess_munch.py`
- `data-pipeline/fixtures/munch_apt.jsonl`
- `data-pipeline/fixtures/munch_inapt.jsonl`
