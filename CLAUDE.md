# Metaforge - Project Context

A browser-based visual thesaurus combining utility with 3D exploration.

## Quick Links

| Document | Purpose |
|----------|---------|
| `Metaforge-PRD-2.md` | **Authoritative PRD** (supersedes original, includes parked ideas) |
| `docs/plans/20260207-prd-reconciliation-scratchpad.md` | Decision log from PRD reconciliation |
| `docs/plans/2026-01-26-sprint-zero.md` | Sprint Zero implementation plan (backend complete) |
| `docs/plans/2026-01-28-performance-tuning.md` | Performance optimisation notes and scaling strategies |
| `docs/designs/` | Feature brainstorms (start here for design context) |
| `docs/plans/` | Detailed implementation plans |
| `docs/designs/metaphor-forge.md` | Sprint Zero feature |
| `MetaforgeConcept.png` | Visual reference (antique + cosmic themes) |

## Architecture

- **Backend:** Go headless API (stateless, self-hostable)
- **Frontend:** Lit + Vite + TypeScript + `3d-force-graph` (browser-first)
- **Data:** SQLite + FastText embeddings + Claude-extracted properties
- **Storage:** IndexedDB for local user data (no accounts in MVP)

## Current Phase

**Sprint Zero backend complete.** Forge + Thesaurus endpoints working, 38 Go tests passing.

Next: Phase 1 MVP frontend — 3D force graph + HUD results panel.

---

## Superpowers Skills

The superpowers skills are bundled in this repo for portability (CCotW, remote sessions):
- Location: `.claude-skills/claude-plugins-official/superpowers/4.1.1/skills/`
- Mirrors global structure: `~/.claude/plugins/cache/claude-plugins-official/superpowers/4.1.1/`
- Use with Skill tool as normal

---

## ⚠️ DEVELOPMENT STANDARDS - NON-NEGOTIABLE ⚠️

| Standard | Meaning |
|----------|---------|
| **TDD (Red/Green)** | Write failing test FIRST. Then minimal code to pass. Then refactor. Every feature, every bugfix. |
| **Algorithms** | During code-review always evaluate worst-case performance and scalability. Design the shape of your data for algorithmic fit. Recognise OOM risk and proactively filter, stream and paginate to avoid OOM errors. |
| **Frequent Commits** | Commit after each green test. Small, atomic commits. Never batch up changes. |
| **CI/CD** | All commits trigger automated tests. No merging with failing tests. |
| **Canary Releases** | New features deploy to subset first. Monitor before full rollout. |
| **All Errors/Exceptions Handled**| Even if the error is recoverable or negligible it should be logged, and if not recoverable it must escalate to callers. |
| **Observability** | Output to logs not just for errors and warnings, but to enable tracing of control flow and data transformations. Collect timing behind feature-flags for all complex or potentially long-running routines. Timer functions must devolve to NO-OP when the feature-flag is disabled and in all production deployments |

**If you're about to write code without a failing test, STOP.**

---

## Commands

### Setup

```bash
# Python venv (data pipeline)
python3 -m venv .venv && source .venv/bin/activate
pip install -r data-pipeline/requirements.txt

# Frontend
cd web && npm install
```

### Tests

```bash
# Go (from api/)
cd api && go test ./...

# Python (from repo root)
source .venv/bin/activate && python -m pytest data-pipeline/scripts/ -v

# Frontend (from web/)
cd web && npm test
```

### Dev Servers

```bash
# Go API
cd api && go run ./cmd/metaforge --db ../data-pipeline/output/lexicon_v2.db --port 8080

# Frontend
cd web && npm run dev
```

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

## Secrets Policy

- **NEVER commit API keys, tokens, passwords, or other secrets** to the repo or database — not in code, config, SQL dumps, comments, or test fixtures.
- Secrets must be loaded from environment variables or external files that are gitignored (e.g. `~/.gemini_api_key`).
- **Encrypted secrets require human approval** before being added to the repo. A human must be in the loop for any encryption/decryption workflow to ensure accountability.
- If you encounter a secret in staged changes, **stop and alert the user** before committing.

## Coding Style

- **Paradigm:** FP over OOP, but pragmatic
- **Priority:** Readability over cleverness
- **DRY / YAGNI:** No premature abstraction, no speculative features
- **Language:** UK English spelling (optimise, colour)

## Design Status

| Feature | Design | Implementation |
|---------|--------|----------------|
| Metaphor Forge | ✓ Complete | ✓ Backend complete |
| Core Thesaurus | ✓ Complete | ✓ Backend complete, ○ Frontend not started |
| 3D Force Graph | ✓ Complete (PRD-2) | ○ Not started |
| Word Hunt | Parked | Parked |
| Constellation | Parked (near-horizon) | Parked |
