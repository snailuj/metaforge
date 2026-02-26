# Changelog & Backlog Tracking — Design

**Date:** 2026-02-27
**Status:** Approved

## Problem

Metaforge has no central place to record future work ideas, deferred items, or what shipped. Work items live in design docs, the PRD's "Parked Ideas" section, CLAUDE.md's design status table, and scattered conversation context. Ideas get lost between sessions. There is no changelog, no release tagging, and no way to track whether shipped features have been human-verified on staging.

## Goals

1. **Backlog:** Capture future work, limitations, and ideas as they arise during development — not after.
2. **Changelog:** Record user-visible changes in a format that's terse for internal use but expandable to contributor-facing or public release notes by LLM when needed.
3. **Agent integration:** Agents encounter the right instructions at the right workflow stages, automatically.
4. **Smoketest tracking:** Know which merged items have been human-verified on staging before cutting a release.

## Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Backlog system | GitHub Issues | Labels, milestones, search, close-on-merge workflow. Agents create via `gh`. |
| Changelog format | Keep a Changelog (keepachangelog.com) | Industry standard. Added/Changed/Fixed/Deprecated/Removed/Security under version headings. |
| Changelog accumulation | Branch-local `.changelog/<branch>.md` | Avoids merge conflicts — each branch writes to its own file. |
| Changelog squash | At PR/merge time | Branch file gets merged into `CHANGELOG.md` under `[Unreleased]`, then deleted. |
| Agent instructions | Three project-local skills with narrow trigger descriptions | One skill per workflow moment for reliable auto-invocation. |
| Smoketest tracking | `verified` label on issues/PRs | Human adds label after staging test. Release script only includes verified items. |
| Audience (initial) | Developer + agents | Terse, scannable entries. Expandable to contributor-facing or public release notes later via LLM. |

## GitHub Issue Labels

Create once on the repo:

| Label | Colour | Purpose |
|-------|--------|---------|
| `api` | blue | Go API layer |
| `data-pipeline` | green | Python pipeline layer |
| `frontend` | purple | Web/UI layer |
| `infra` | grey | CI/CD, deploy, VPS |
| `enhancement` | teal | New capability |
| `bug` | red | Something broken |
| `idea` | yellow | Unvalidated future work |
| `verified` | bright green | Human smoketested on staging |

**Issue title convention:** Terse, prefixed with layer. E.g. `data-pipeline: concreteness coverage ceiling at 68.8% (OOV synsets)`.

## Changelog Format

File: `CHANGELOG.md` at repo root. Follows keepachangelog.com.

```markdown
# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Added
- Concreteness regression with 4-model shootout (k-NN r=0.91, 68.8% coverage)

### Fixed
- argparse --verbose flag rejected after subcommand

## [0.1.0] - 2026-XX-XX

### Added
- Metaphor Forge API endpoint
- Core thesaurus search + force graph frontend
- ...
```

**Granularity:** One entry per user-visible change, not per commit.

**Branch-local accumulation:** During feature work, agents write entries to `.changelog/<branch-name>.md` — a flat list using Keep a Changelog categories. This file is gitignored (no noise in PRs) or committed (provides audit trail) — TBD during implementation.

## Agent Skills

Three project-local skills in `.claude/skills/`:

### 1. `backlog-capture`

**Description:** "Use when you encounter deferred work, a known limitation, or a future idea during development"

**Trigger:** During development — when an agent hits a ceiling, defers something, or spots an opportunity.

**Action:** Create a GitHub Issue via `gh issue create` with:
- Layer label (`api`, `data-pipeline`, `frontend`, `infra`)
- Type label (`enhancement`, `bug`, `idea`)
- Body with context: what was tried, why deferred, candidate solutions

### 2. `changelog-entry`

**Description:** "Use after committing a user-visible change to record it in the branch changelog"

**Trigger:** After committing code that adds, changes, fixes, or removes user-visible behaviour.

**Action:** Append an entry to `.changelog/<branch-name>.md` under the appropriate Keep a Changelog category. Skip for:
- Refactors with no behaviour change
- Test-only changes
- Documentation tweaks
- Intermediate TDD steps (the final feature commit gets the entry, not each red/green cycle)

### 3. `changelog-squash`

**Description:** "Use when finishing a branch or preparing a PR to merge changelog entries into CHANGELOG.md"

**Trigger:** When preparing a PR or finishing a development branch.

**Action:**
1. Read `.changelog/<branch-name>.md`
2. Merge entries into `CHANGELOG.md` under `[Unreleased]`, deduplicating with any existing entries
3. Delete the branch changelog file
4. Commit the updated `CHANGELOG.md`

## CLAUDE.md Integration

Add a single line to the Development Standards table in the worktree CLAUDE.md:

```markdown
| **Changelog & Backlog** | See skills: `backlog-capture`, `changelog-entry`, `changelog-squash` |
```

## Release Workflow

1. PR merges to main — `changelog-squash` fires, entries land in `[Unreleased]`
2. Deploy to staging
3. Human smoketests — adds `verified` label to the PR/issues
4. When ready to release: rename `[Unreleased]` to `[x.y.z] - YYYY-MM-DD`, create git tag
5. Only items with `verified` label on their associated PR/issue make it into the release section

## Cleanup Note

The `.claude-skills/` mirror in the repo (originally for Claude Code on the Web) is YAGNI now that VPS + Tailscale is in place. Should be removed as a separate cleanup task.

## Implementation

Three deliverables:
1. Create GitHub labels on the repo
2. Create the three skills in `.claude/skills/`
3. Seed `CHANGELOG.md` with historical entries (retrospectively from git log)
4. Update CLAUDE.md with the Development Standards reference
