# Changelog & Backlog Tracking — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Set up GitHub Issue labels, three agent skills for backlog/changelog management, seed CHANGELOG.md with historical entries, and update CLAUDE.md.

**Architecture:** GitHub Issues as backlog (with layer + type labels), Keep a Changelog format with branch-local accumulation, three narrow-trigger skills in `.claude/skills/`.

**Tech Stack:** GitHub CLI (`gh`), Markdown, Claude Code skills (SKILL.md format).

**Design doc:** `docs/plans/2026-02-27-changelog-and-backlog-design.md`

---

### Task 1: Create GitHub Issue labels

Create the project-specific labels. Some defaults already exist (`bug`, `enhancement`) — update their colours for consistency, add the rest.

**Files:** None (GitHub API only)

**Step 1: Create and update labels**

```bash
# Layer labels
gh label create "api" --color "1D76DB" --description "Go API layer" --force
gh label create "data-pipeline" --color "0E8A16" --description "Python pipeline layer" --force
gh label create "frontend" --color "7B2D8B" --description "Web/UI layer" --force
gh label create "infra" --color "6A737D" --description "CI/CD, deploy, VPS" --force

# Type labels (update existing where needed)
gh label edit "bug" --color "D73A4A" --description "Something broken"
gh label edit "enhancement" --color "1AC0C6" --description "New capability"
gh label create "idea" --color "FEF2C0" --description "Unvalidated future work" --force

# Status labels
gh label create "verified" --color "2EA44F" --description "Human smoketested on staging" --force
```

**Step 2: Verify labels exist**

Run: `gh label list --limit 20`
Expected: All 8 labels visible with correct colours and descriptions.

**Step 3: Commit**

No files to commit — labels are GitHub-side only.

---

### Task 2: Create `backlog-capture` skill

The skill that fires when agents encounter deferred work, known limitations, or future ideas during development.

**Files:**
- Create: `.claude/skills/backlog-capture/SKILL.md`

**Step 1: Create the skill**

```markdown
---
name: backlog-capture
description: >
  Use when you encounter deferred work, a known limitation, or a future idea
  during development. Creates a GitHub Issue with layer and type labels to
  capture context while it's fresh.
---

# Backlog Capture

When you encounter something that should be tracked but isn't part of the
current task — a limitation, a deferred improvement, a future idea — create
a GitHub Issue immediately.

## When to Use

- You hit a ceiling or limitation (e.g. coverage gap, performance cliff)
- You defer something to stay focused on the current task
- You spot an opportunity for improvement outside current scope
- You notice a bug that isn't blocking current work

## How to Create the Issue

```bash
gh issue create \
  --title "<layer>: <terse description>" \
  --label "<layer-label>,<type-label>" \
  --body "<context>"
```

### Title Convention

Prefix with the layer, keep it terse:
- `data-pipeline: concreteness coverage ceiling at 68.8% (OOV synsets)`
- `api: rate limiting on /forge endpoints`
- `frontend: 2nd-order edge node rendering`

### Labels

**Layer** (pick one): `api`, `data-pipeline`, `frontend`, `infra`

**Type** (pick one): `enhancement`, `bug`, `idea`

### Body

Include enough context for someone (or an agent) encountering the issue cold:
- What was tried or observed
- Why it was deferred
- Candidate solutions if known
- Link to relevant code, design docs, or eval results

## Example

```bash
gh issue create \
  --title "data-pipeline: concreteness coverage ceiling at 68.8% (OOV synsets)" \
  --label "data-pipeline,enhancement" \
  --body "$(cat <<'BODY'
## Context

The concreteness regression (k-NN r=0.91) fills scores for synsets that have
at least one lemma in FastText vocabulary. 33,592 synsets have no in-vocabulary
lemmas, capping coverage at 68.8% vs the 80% target.

## Options

1. **Definition-based embeddings** — encode synset definitions with a sentence
   transformer, use those as features when lemma embeddings are unavailable.
2. **Larger vocabulary model** — FastText wiki-news-300d has 1M words. The
   crawl-300d model has 2M. May recover some OOV lemmas.
3. **Subword embeddings** — FastText's .bin format supports subword inference
   for OOV words (vs .vec which is lookup-only).

## References

- Shootout results: `data-pipeline/output/concreteness_shootout.json`
- Design: `docs/plans/2026-02-25-fasttext-concreteness-regression-design.md`
BODY
)"
```
```

**Step 2: Verify skill is discoverable**

Run: `ls .claude/skills/backlog-capture/SKILL.md`
Expected: File exists.

**Step 3: Commit**

```bash
git add .claude/skills/backlog-capture/SKILL.md
git commit -m "feat(skills): add backlog-capture skill for GitHub Issue creation"
```

---

### Task 3: Create `changelog-entry` skill

The skill that fires after committing a user-visible change.

**Files:**
- Create: `.claude/skills/changelog-entry/SKILL.md`

**Step 1: Create the skill**

```markdown
---
name: changelog-entry
description: >
  Use after committing a user-visible change to record it in the branch
  changelog. Maintains a branch-local changelog file that gets squashed into
  CHANGELOG.md at PR time.
---

# Changelog Entry

After committing code that adds, changes, fixes, or removes user-visible
behaviour, append an entry to the branch changelog.

## When to Use

- After committing a new feature or capability
- After committing a bug fix
- After committing a breaking change or deprecation
- After committing a security fix

## When NOT to Use

- Refactors with no behaviour change
- Test-only changes
- Documentation tweaks
- Intermediate TDD steps (the final feature commit gets the entry, not each
  red/green cycle)
- Dependency updates with no user-visible effect

## How to Record

Append to `.changelog/<branch-name>.md` using Keep a Changelog categories.

The branch name comes from: `git branch --show-current`

### Categories

- **Added** — new features or capabilities
- **Changed** — changes to existing functionality
- **Fixed** — bug fixes
- **Deprecated** — soon-to-be-removed features
- **Removed** — removed features
- **Security** — vulnerability fixes

### Format

```markdown
### Added
- Concreteness regression with 4-model shootout (k-NN r=0.91, 68.8% coverage)
```

**One entry per user-visible change.** Keep entries terse — these are for
internal use. They can be expanded into contributor-facing or public release
notes later.

If the file doesn't exist yet, create it with the first entry. If it already
exists, append under the appropriate category heading (create the heading if
it doesn't exist).

## Example Workflow

```bash
# After committing a feature:
BRANCH=$(git branch --show-current)
# Append to .changelog/$BRANCH.md:
#
# ### Added
# - SVR subsampling for large training sets (svr_max_samples param)
```
```

**Step 2: Verify skill is discoverable**

Run: `ls .claude/skills/changelog-entry/SKILL.md`
Expected: File exists.

**Step 3: Commit**

```bash
git add .claude/skills/changelog-entry/SKILL.md
git commit -m "feat(skills): add changelog-entry skill for branch-local changelog accumulation"
```

---

### Task 4: Create `changelog-squash` skill

The skill that fires when finishing a branch or preparing a PR.

**Files:**
- Create: `.claude/skills/changelog-squash/SKILL.md`

**Step 1: Create the skill**

```markdown
---
name: changelog-squash
description: >
  Use when finishing a branch or preparing a PR to merge changelog entries
  into CHANGELOG.md. Reads the branch-local changelog, merges entries under
  [Unreleased], and deletes the branch file.
---

# Changelog Squash

When finishing a development branch or preparing a PR, merge the branch
changelog into the main CHANGELOG.md.

## When to Use

- Before creating a PR
- When the `finishing-a-development-branch` skill is invoked
- When explicitly asked to prepare a branch for merge

## Procedure

1. **Read** `.changelog/<branch-name>.md`
2. **Merge** entries into `CHANGELOG.md` under the `## [Unreleased]` heading
   - If a category heading (e.g. `### Added`) already exists under
     `[Unreleased]`, append the new entries to it
   - If the category heading doesn't exist, create it
   - Deduplicate — don't add entries that already exist
3. **Delete** `.changelog/<branch-name>.md`
4. **Commit** the updated `CHANGELOG.md` and the deletion

## If No Branch Changelog Exists

If `.changelog/<branch-name>.md` doesn't exist, check git log for the branch
and offer to generate entries retrospectively. If the user declines, skip —
not every branch needs changelog entries (e.g. docs-only branches).

## If CHANGELOG.md Doesn't Exist

Create it with the standard Keep a Changelog header:

```markdown
# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]
```

Then merge the branch entries under `[Unreleased]`.

## Category Order

When creating new category headings, use this order:
1. Added
2. Changed
3. Fixed
4. Deprecated
5. Removed
6. Security
```

**Step 2: Verify skill is discoverable**

Run: `ls .claude/skills/changelog-squash/SKILL.md`
Expected: File exists.

**Step 3: Commit**

```bash
git add .claude/skills/changelog-squash/SKILL.md
git commit -m "feat(skills): add changelog-squash skill for PR-time changelog merge"
```

---

### Task 5: Seed CHANGELOG.md with historical entries

Create `CHANGELOG.md` at repo root with retrospective entries from git history. Group under `[Unreleased]` since no versions have been tagged yet.

**Files:**
- Create: `CHANGELOG.md`

**Step 1: Generate historical entries**

Review the git log across main and the current branch. Distill into user-visible changes (not every commit — one entry per feature/fix). Group by Keep a Changelog categories.

Key changes to capture from git history:

**Added:**
- Metaphor Forge API endpoint (`/forge/suggest`)
- Core thesaurus search + force graph frontend
- Curated property vocabulary with WordNet-derived canonical entries
- Cross-domain metaphor scoring with cascade pipeline
- Concreteness gate (P2) with soft margin + POS gate
- Discrimination eval with rank AUC metric
- Concreteness regression — 4-model shootout (k-NN r=0.91, 68.8% coverage)
- Brysbaert concreteness ratings import (max aggregation per synset)
- SyntagNet collocation pairs, VerbNet classes/roles
- FastText 300d embedding similarity in forge scoring
- Property snapping — 3-stage cascade (exact, morphological, cosine)
- Enrichment pipeline with Claude LLM extraction
- Staging deployment at metaforge.julianit.me

**Changed:**
- Enrichment schema v2 — structured properties with domain/salience

**Fixed:**
- Cosine distance clamping in CompositeScore
- Deterministic lemma SQL ordering
- Input normalisation for forge queries
- argparse --verbose after subcommand

**Removed:**
- Dead IDF, similarity, and centroid computation code
- Dead property_similarity, synset_centroids tables

**Step 2: Write CHANGELOG.md**

Create the file with the header and entries from Step 1. All entries go under `[Unreleased]` since there are no release tags yet.

**Step 3: Commit**

```bash
git add CHANGELOG.md
git commit -m "docs: seed CHANGELOG.md with retrospective entries from git history"
```

---

### Task 6: Update CLAUDE.md and create .changelog/.gitkeep

Add the Development Standards reference and ensure the `.changelog/` directory exists.

**Files:**
- Modify: `CLAUDE.md` (worktree root)
- Create: `.changelog/.gitkeep`

**Step 1: Add to CLAUDE.md Development Standards table**

Add a new row to the `⚠️ DEVELOPMENT STANDARDS - NON-NEGOTIABLE ⚠️` table:

```markdown
| **Changelog & Backlog** | See skills: `backlog-capture`, `changelog-entry`, `changelog-squash`. Record issues during dev, changelog entries after user-visible commits, squash at PR time. |
```

**Step 2: Create .changelog directory**

```bash
mkdir -p .changelog
touch .changelog/.gitkeep
```

**Step 3: Verify skills appear in listing**

The three new skills should appear when the agent's skill list is refreshed. Verify by checking the `.claude/skills/` directory:

Run: `ls -d .claude/skills/*/`
Expected: `backlog-capture/`, `changelog-entry/`, `changelog-squash/`, plus existing skills.

**Step 4: Commit**

```bash
git add CLAUDE.md .changelog/.gitkeep
git commit -m "docs: add changelog & backlog standard to CLAUDE.md, create .changelog dir"
```

---

### Task 7: Create first backlog issue (concreteness coverage)

Exercise the `backlog-capture` skill by creating the concreteness coverage issue that prompted this whole system.

**Files:** None (GitHub API only)

**Step 1: Create the issue**

```bash
gh issue create \
  --title "data-pipeline: concreteness coverage ceiling at 68.8% (OOV synsets)" \
  --label "data-pipeline,enhancement" \
  --body "$(cat <<'BODY'
## Context

The concreteness regression (k-NN r=0.91) fills scores for synsets that have
at least one lemma in FastText vocabulary. 33,592 synsets have no in-vocabulary
lemmas, capping coverage at 68.8% vs the 80% target.

## Options

1. **Definition-based embeddings** — encode synset definitions with a sentence
   transformer, use those as features when lemma embeddings are unavailable.
2. **Larger vocabulary model** — FastText wiki-news-300d has 1M words. The
   crawl-300d model has 2M. May recover some OOV lemmas.
3. **Subword embeddings** — FastText's .bin format supports subword inference
   for OOV words (vs .vec which is lookup-only).

## References

- Shootout results: \`data-pipeline/output/concreteness_shootout.json\`
- Design: \`docs/plans/2026-02-25-fasttext-concreteness-regression-design.md\`
BODY
)"
```

**Step 2: Verify issue exists**

Run: `gh issue list --limit 5`
Expected: New issue visible with correct labels.

**Step 3: No commit needed** — this is GitHub-side only.

---

## Summary

| Task | What | Commit |
|------|------|--------|
| 1 | Create GitHub Issue labels | None (GitHub API) |
| 2 | `backlog-capture` skill | `feat(skills): add backlog-capture skill` |
| 3 | `changelog-entry` skill | `feat(skills): add changelog-entry skill` |
| 4 | `changelog-squash` skill | `feat(skills): add changelog-squash skill` |
| 5 | Seed `CHANGELOG.md` with history | `docs: seed CHANGELOG.md` |
| 6 | Update `CLAUDE.md` + `.changelog/` dir | `docs: add changelog & backlog standard` |
| 7 | First backlog issue (concreteness) | None (GitHub API) |

**Total: 7 tasks, 5 commits, 0 tests** (this is tooling/docs, not code)
