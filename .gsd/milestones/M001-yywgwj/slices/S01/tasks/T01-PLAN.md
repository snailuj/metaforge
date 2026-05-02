---
estimated_steps: 1
estimated_files: 3
skills_used: []
---

# T01: Import V2 enrichment JSON into database

Run enrich.sh with both V2 enrichment files (enrichment_4000_sonnet_v2_20260224.json + enrichment_8000_sonnet_v2_20260306.json) to populate the database with structured properties. The pipeline restores from PRE_ENRICH.sql, imports V2 JSON, applies schema migrations (salience, property_type, relation columns), snaps to curated vocabulary with salience accumulation, and exports the updated SQL dump. Skip the test duplicate file.

## Inputs

- `data-pipeline/input/enrichment_4000_sonnet_v2_20260224.json`
- `data-pipeline/input/enrichment_8000_sonnet_v2_20260306.json`
- `data-pipeline/output/PRE_ENRICH.sql`

## Expected Output

- `data-pipeline/output/lexicon_v2.db with V2 columns populated`
- `data-pipeline/output/POST_ENRICH.sql backup`

## Verification

sqlite3 lexicon_v2.db 'SELECT COUNT(*) FROM synset_properties WHERE salience != 1.0' returns >= 10000; sqlite3 lexicon_v2.db 'SELECT COUNT(DISTINCT property_type) FROM synset_properties WHERE property_type IS NOT NULL' returns 6
