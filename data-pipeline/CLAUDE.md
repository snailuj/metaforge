
### Data Pipeline

```bash
# Restore lexicon DB from SQL dump
./data-pipeline/scripts/restore_db.sh

# Run enrichment pipeline (requires FastText vectors + venv)
python data-pipeline/scripts/enrich_pipeline.py --db PATH --enrichment FILE --fasttext PATH

# MRR evaluation — three modes:

# 1. Pre-built DB (eval-only, no pipeline, no API calls)
python data-pipeline/scripts/evaluate_mrr.py --db PATH --port 9091 -v -o results.json

# 2. Pre-computed enrichment (restore + pipeline, no API calls)
python data-pipeline/scripts/evaluate_mrr.py --enrichment FILE --port 9091 -v -o results.json

# 3. Live LLM enrichment (restore + enrich + pipeline, costs API calls)
python data-pipeline/scripts/evaluate_mrr.py --enrich --size 700 --model sonnet --port 9091 -v -o results.json
```

---

## Large Files Policy

- **FastText vectors and other large assets** live in `~/.local/share/metaforge/`, NOT in the repo
- Worktrees symlink into the shared location: `data-pipeline/raw/wiki-news-300d-1M.vec`
- Never commit large binary assets to the repo

## Database Policy

- **Never commit `.db` binaries** — they are gitignored.
- **Commit SQL text dumps** (`sqlite3 <db> .dump > <file>.sql`) containing schema + data.
- **Dumps must be idempotent:** restore into a fresh SQLite database via `restore_db.sh`.
- Current dump: `data-pipeline/output/lexicon_v2.sql`
- Restore script: `data-pipeline/scripts/restore_db.sh`