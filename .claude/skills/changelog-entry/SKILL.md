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
