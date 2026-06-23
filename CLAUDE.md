# Metaforge - Project Context

A browser-based visual thesaurus combining utility with 3D exploration.

## ⚠️ Read Before Anything Else

**Always read `docs/roadmap/PIPELINE.md` before answering "what's next", "what should I work on", "where are we", or any milestone-level question.** It is the single source of truth for current and queued work. Do not rely on memory or recap from prior sessions for pipeline state — read the file. The `metaforge-pipeline` skill (if registered) does this automatically; this instruction guarantees the behaviour even without the skill.

## Quick Links

| Document | Purpose |
|----------|---------|
| `docs/roadmap/PIPELINE.md` | **Programme pipeline + single capture funnel** — the one source of truth for the whole forward-work lifecycle: Inbox → Backlog → Queued → Next → Active → Done. Capture raw ideas into its `## Inbox`; read first when starting milestone-level work. |
| `docs/roadmap/programme-overview.md` | Programme-level overview — what Metaforge is, current state, milestone sequence rationale |
| `docs/decisions/log.md` | Append-only register of architectural and convention decisions |
| `Metaforge-PRD-2.md` | **Authoritative PRD** (supersedes original, parked ideas from original included) |
| `docs/plans/2026-01-26-sprint-zero.md` | Sprint Zero implementation plan (backend complete) |
| `docs/plans/2026-01-28-performance-tuning.md` | Performance optimisation notes and scaling strategies |
| `docs/designs/` | Feature brainstorms (start here for design context) |
| `docs/plans/` | Detailed implementation plans |
| `docs/designs/metaphor-forge.md` | Sprint Zero feature |
| `MetaforgeConcept.png` | Visual reference (antique + cosmic themes) |
| `data-pipeline/grading/` + `data-pipeline/grading_sidecar/` | Metaphor Grading Tool — bootstrap-loop instrument (single-user web grading mode + FastAPI sidecar). See spec at `docs/superpowers/specs/2026-05-30-metaphor-grading-tool-design.md` and plan at `docs/superpowers/plans/2026-05-30-metaphor-grading-tool.md`. |

## Architecture

- **Backend:** Go headless API (stateless, self-hostable)
- **Frontend:** Lit + Vite + TypeScript + `3d-force-graph` (browser-first)
- **Data:** SQLite + FastText embeddings + Claude-extracted properties
- **Storage:** IndexedDB for local user data (no accounts in MVP)

## Current Phase: Phase 1 (MVP)
- API MVP-complete
- Basic Thesaurus and Graph navigation complete
- Staging server deployed at https://metaforge.julianit.me/
- Live testing confirmed on multiple browsers and phones
- ~300 automated tests across all code surfaces

**Forge endpoint tuning in progress. Data pipeline 70% MVP-ready. Substack teaser post drafted with Opus. Eval harness (M01) shipped — discriminative aptness rate is now the primary forge KPI; MRR is a secondary regression check.**

**Next:** see `docs/roadmap/PIPELINE.md` (M02 — Asymmetric Ortony Scoring is the next algorithm milestone). Metaphor Forge UI also queued.

**Required for MVP-complete:**
- **Improve forge aptness** — V2 baseline (2026-05-03): aptness_rate 0.0849, separation_score 0.0103. Target: separation_score > 0.3. Closing the gap is the work of M02 (Ortony) → M03 (Cascade) → M04 (Type-aligned).
- 2nd-Order Edge Node Rendering
- 2-3 Substack posts
- Sem-sim distance between words visually rendered
- 20k word enrichment
- CI/CD pipeline
- Testing, Polish for MVP

## Grading tool — when active

The Metaphor Grading Tool (`data-pipeline/grading_sidecar/` + grading mode in `mf-app`) is an active-learning bootstrap-loop instrument: Julian grades Sonnet-generated metaphor chains (live/dead/bad_path/irrelevant), bad_path examples feed the next round's prompt. Deployed at `metaforge-next.julianit.me` via path-scoped Caddy routing (`/api/grading/*`); the production URL graceful-degrades via the `/api/grading/healthz` probe. JSONL data committed under `data-pipeline/grading/` with `_provisional` markers (auto-commit every 15 min while sidecar runs). See `docs/superpowers/specs/2026-05-30-metaphor-grading-tool-design.md` for the authoritative design.

**⚠️ Deploy topology (since 2026-06-01):** the live sidecar runs from the **`.worktrees/next`** worktree on branch **`grading-live`** — NOT the main checkout. Switching the main checkout's branch does **not** affect the live grading tool, and grading verdicts auto-commit to `grading-live`. The data + autocommit location is pinned by `Environment=PYTHONPATH=.../.worktrees/next/data-pipeline/` in `deploy/grading/metaforge-grading.service` (`paths.py` derives both from it). Cutover/redeploy = `sudo deploy/grading/deploy.sh` (installs the unit + restart; it does not git-pull). Do not "fix" the sidecar by repointing it at the main checkout. See memory `grading_ux_round3_landed`.

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
| **Idempotency** | Batch functions must be idempotent to ensure composability and recovery from errors does not require wasting the work of previous runs |
| **Observability** | Output to logs not just for errors and warnings, but to enable tracing of control flow and data transformations. Collect timing behind feature-flags for all complex or potentially long-running routines. Timer functions must devolve to NO-OP when the feature-flag is disabled and in all production deployments |
| **Pipeline** | `docs/roadmap/PIPELINE.md` is the single source of truth for active / next / queued / backlog milestones. Read it when starting milestone-level work; update it on any state change. The `metaforge-pipeline` skill surfaces a quick report. |
| **Captures & backlog (single funnel)** | One source of truth: `docs/roadmap/PIPELINE.md`. Capture raw ideas/observations/limitations into its `## Inbox (untriaged captures)` with zero friction (no triage at capture time). Triage periodically: promote each item **verbatim** down into Backlog → Queued → Next, or discard. There is **no** separate captures file and no parallel backlog. |
| **Decisions** | Settled architectural/convention choices → `docs/decisions/log.md` (append-only). Findings/spike reports/working notes → dated `docs/inbox/*.md` (reference material, not backlog). |
| **GitHub issues** | Reserved for **externally-facing** work only — licensing, public infra, community-visible items. Internal engineering work lives in the PIPELINE.md funnel, not in issues. `changelog-entry`/`changelog-squash` skills remain available for CHANGELOG.md tracking but are not mandatory. |

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
- **Comments:** Explain intent, constraints, or gotchas — never restate what the code already says

## Design Status

| Feature | Design | Implementation |
|---------|--------|----------------|
| Metaphor Forge | ✓ Complete | ✓ Backend complete |
| Core Thesaurus | ✓ Complete | ✓ Backend complete, Frontend not started |
| 3D Force Graph | ✓ Complete (PRD-2) | ○ Not started |
| Word Hunt | Parked | Parked |
| Constellation | Parked (near-horizon) | Parked |
