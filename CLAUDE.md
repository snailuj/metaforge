# Metaforge - Project Context

A browser-based visual thesaurus combining utility with 3D exploration.

## Quick Links

| Document | Purpose |
|----------|---------|
| `Metaforge-PRD.md` | Full product requirements |
| `IMPLEMENTATION-PLAN.md` | Technical architecture and phases |
| `docs/plans/2026-01-26-sprint-zero.md` | Sprint Zero implementation plan (executing) |
| `docs/plans/2026-01-28-performance-tuning.md` | Performance optimisation notes and scaling strategies |
| `docs/designs/` | Feature brainstorms (start here for design context) |
| `docs/designs/metaphor-forge.md` | ✓ Complete - Sprint Zero feature |
| `MetaforgeConcept.png` | Visual reference (antique + cosmic themes) |

## Architecture

- **Backend:** Go headless API (stateless, self-hostable)
- **Frontend:** TypeScript + Three.js/WebGPU (browser-first)
- **Data:** SQLite + GloVe embeddings + Gemini-extracted properties
- **Storage:** IndexedDB for local user data (no accounts in MVP)

## Current Phase

**Sprint Zero: Metaphor Forge** - proving out the data pipeline before 3D work.

Design complete. Ready for implementation planning.

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

## Coding Style

- **Paradigm:** FP over OOP, but pragmatic
- **Priority:** Readability over cleverness
- **DRY / YAGNI:** No premature abstraction, no speculative features
- **Language:** UK English spelling (optimise, colour)

## Design Status

| Feature | Status |
|---------|--------|
| Metaphor Forge | ✓ Design complete |
| Core Thesaurus | ◐ Started |
| 3D Visualization | ○ Not started |
| Word Hunt | ○ Not started |
| Constellation | ○ Not started |
