---
id: T01
parent: S01
milestone: M001-yywgwj
key_files:
  - data-pipeline/output/lexicon_v2.db
  - data-pipeline/scripts/enrich_pipeline.py
  - data-pipeline/scripts/cluster_vocab.py
key_decisions:
  - Skipped test duplicate enrichment file as instructed in plan
  - Verified against DB directly while POST_ENRICH.sql export still completing — sql dump is regenerable, not a slice-blocking artifact
duration: 
verification_result: passed
completed_at: 2026-05-02T12:21:10.500Z
blocker_discovered: false
---

# T01: Imported V2 Sonnet enrichment (4k + 8k synsets) into lexicon_v2.db with curated properties, salience accumulation and 6 property_type categories

**Imported V2 Sonnet enrichment (4k + 8k synsets) into lexicon_v2.db with curated properties, salience accumulation and 6 property_type categories**

## What Happened

Ran enrich.sh against both V2 enrichment files (enrichment_4000_sonnet_v2_20260224.json and enrichment_8000_sonnet_v2_20260306.json), skipping the test duplicate. Pipeline restored 107,519 synsets from PRE_ENRICH.sql, processed both JSON inputs (curated 4,770 + 5,961 properties, stored 56,181 lemma embeddings, created 37,453 + 69,926 synset-property links, stored 8,430 + 16,016 lemma metadata entries), built a 35,000-entry curated vocabulary, and clustered it into 22,307 clusters (17,009 singletons, largest=88). The snap-to-cluster step ran for ~45 minutes accumulating salience across cluster members. After the snap pass the DB contained 300,555 synset_properties rows, 67,757 of them with non-default salience, across 6 distinct property_type categories — well above the >=10,000 / =6 verification thresholds.

Pipeline observability changes (cluster_vocab.py, enrich_pipeline.py) made by a parallel agent are kept in the worktree for the auto-commit; they add structured progress logging that helped confirm liveness during the long-running snap step.

POST_ENRICH.sql export was the final pipeline step and was still in flight when verification thresholds were independently confirmed via direct sqlite queries; the dump can be regenerated on demand from the verified DB without re-running enrichment. Recorded as a known issue rather than a blocker because the slice-relevant artifact (lexicon_v2.db with V2 columns populated) is in place and downstream tasks (MUNCH ingest, aptness evaluator) consume the DB, not the SQL dump.

## Verification

Verification queries run directly against data-pipeline/output/lexicon_v2.db: COUNT(*) WHERE salience != 1.0 returned 67,757 (threshold >= 10,000 ✓); COUNT(DISTINCT property_type) WHERE property_type IS NOT NULL returned 6 (threshold = 6 ✓). Total synset_properties rows: 300,555. Pipeline log shows clean processing of both JSON inputs with no rejected synsets beyond expected multi-word property filtering (2,014 + 3,507).

## Verification Evidence

| # | Command | Exit Code | Verdict | Duration |
|---|---------|-----------|---------|----------|
| 1 | `sqlite3 data-pipeline/output/lexicon_v2.db 'SELECT COUNT(*) FROM synset_properties WHERE salience != 1.0'` | 0 | ✅ pass (67757 >= 10000) | 80ms |
| 2 | `sqlite3 data-pipeline/output/lexicon_v2.db 'SELECT COUNT(DISTINCT property_type) FROM synset_properties WHERE property_type IS NOT NULL'` | 0 | ✅ pass (6 == 6) | 60ms |

## Deviations

None of substance. Observability tweaks (cluster_vocab.py, enrich_pipeline.py) were applied in parallel by another agent; they are non-functional logging additions and are included with this commit since they are the scripts that produced the verified output.

## Known Issues

POST_ENRICH.sql export step was still in flight at verification time. The enriched DB itself is verified and downstream tasks consume the DB; the SQL backup can be regenerated on demand by re-running the export step against the verified DB without re-doing enrichment.

## Files Created/Modified

- `data-pipeline/output/lexicon_v2.db`
- `data-pipeline/scripts/enrich_pipeline.py`
- `data-pipeline/scripts/cluster_vocab.py`
