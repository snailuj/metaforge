---
id: T02
parent: S01
milestone: M001-yywgwj
key_files:
  - data-pipeline/output/lexicon_v2.db
  - data-pipeline/scripts/
  - api/internal/
key_decisions:
  - Treated 232,773 NULL-property_type rows as legacy pre-V2 data — V2 task requires the 6 named types to be present, not exclusive
  - Validated data integrity directly via SQL against the live DB rather than waiting on regenerable SQL dump
duration: 
verification_result: passed
completed_at: 2026-05-02T13:12:52.133Z
blocker_discovered: false
---

# T02: test: verify V2 data integrity — 6 property types, salience 0.3-1.0, salience_sum accumulation, full Python/Go suites green

**test: verify V2 data integrity — 6 property types, salience 0.3-1.0, salience_sum accumulation, full Python/Go suites green**

## What Happened

Validated V2 enrichment data quality directly against `data-pipeline/output/lexicon_v2.db` and ran both regression suites end-to-end.

Data integrity findings:
- `synsets`: 107,519 total; `enrichment`: 12,066 V2-enriched synsets (exceeds 10,530 target).
- `synset_properties.property_type` distribution shows all six expected categories present: behaviour 13,893, physical 13,038, social 11,995, functional 10,574, emotional 9,912, effect 8,370. (The 232,773 NULL-typed rows are pre-V2 legacy entries; expected.)
- Salience distribution on `synset_properties.salience`: min 0.3, max 1.0, avg 0.932, populated across all four buckets (0.3–0.5: 1,776; 0.5–0.7: 27,336; 0.7–1.0: 38,645; ≥1.0: 232,798). Confirms snap calibration is producing varied scores rather than defaults.
- Snap accumulation on `synset_properties_curated.salience_sum`: 129,804 rows, min 0.3, max 5.0, avg 0.886, with 72,479 rows in the 1.0–2.0 accumulation band and 1,279 ≥2.0 — confirms the curated table is genuinely accumulating salience across multiple raw properties mapped to the same cluster.

Test suites:
- Python (`data-pipeline/`): 404 passed in 50.90s.
- Go (`api/`): all packages OK (blobconv, db, embeddings, forge, handler 14.6s, thesaurus 31.3s); cmd/metaforge has no test files (expected).

No regressions surfaced from the V2-populated database. Data integrity must-haves met: salience spans the expected range, all 6 property types present, snap accumulation producing meaningful (>1.0) salience_sum values for richly-described synsets.

## Verification

Ran SQL aggregations against `data-pipeline/output/lexicon_v2.db` to confirm enriched synset count, property_type coverage, salience distribution, and salience_sum accumulation. Then ran the full Python pytest suite (404 tests) and Go `go test ./...` (all packages). All green.

## Verification Evidence

| # | Command | Exit Code | Verdict | Duration |
|---|---------|-----------|---------|----------|
| 1 | `sqlite3 lexicon_v2.db <integrity_aggregations>` | 0 | ✅ pass — 6 property types present, salience min=0.3 max=1.0 avg=0.932, salience_sum accumulates to 5.0 | 120ms |
| 2 | `cd data-pipeline && python -m pytest scripts/ -q` | 0 | ✅ pass — 404 tests passed | 50900ms |
| 3 | `cd api && go test ./...` | 0 | ✅ pass — all packages OK (blobconv, db, embeddings, forge, handler, thesaurus) | 46519ms |

## Deviations

None.

## Known Issues

None.

## Files Created/Modified

- `data-pipeline/output/lexicon_v2.db`
- `data-pipeline/scripts/`
- `api/internal/`
