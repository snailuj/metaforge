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
| `docs/designs/metaphor-forge.md` | ✓ Complete - Sprint Zero feature |
| `MetaforgeConcept.png` | Visual reference (antique + cosmic themes) |

## Architecture

- **Backend:** Go headless API (stateless, self-hostable)
- **Frontend:** Lit + Vite + TypeScript + `3d-force-graph` (browser-first)
- **Data:** SQLite + GloVe embeddings + Gemini-extracted properties
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
| **Frequent Commits** | Commit after each green test. Small, atomic commits. Never batch up changes. |
| **CI/CD** | All commits trigger automated tests. No merging with failing tests. |
| **Canary Releases** | New features deploy to subset first. Monitor before full rollout. |

**If you're about to write code without a failing test, STOP.**

---

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
