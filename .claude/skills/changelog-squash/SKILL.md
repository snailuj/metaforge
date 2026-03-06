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
