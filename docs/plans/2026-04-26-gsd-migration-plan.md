# GSD Migration Plan — Metaforge

**Date:** 2026-04-26
**Status:** Ready to execute (all open questions resolved)
**Reviewed by:** Agent review — 14 findings (2 critical, 6 major, 4 minor, 2 nit). All addressed below.

## Current State

Metaforge predates GSD. It has 9 registered git worktrees (1 root on detached HEAD + 7 feature worktrees + 1 integration worktree for `main` in `.worktrees/`), minimal GSD scaffolding (only `CODEBASE.md` and runtime files), and no GSD project artifacts (no `PROJECT.md`, `STATE.md`, `REQUIREMENTS.md`, `DECISIONS.md`, or milestones).

The staging server at `metaforge.julianit.me` is deployed from `.worktrees/feat-freq-fam` and must be repointed before that worktree is removed.

### Branch Status

| Worktree | Branch | Merged to main? | Behind main | Unmerged commits | Recommendation |
|----------|--------|-----------------|-------------|------------------|----------------|
| (root) | detached HEAD (59817af1) | N/A | 229-file divergence | N/A | Reset to main (destructive — see 1.1) |
| sprint-zero | sprint-zero | Yes | 294 | 0 | **Prune** |
| feat-freq-fam | feat/freq-fam | Yes | 165 | 0 | **Prune** (after staging repoint — see 1.2a) |
| curated-vocab | feat/curated-property-vocabulary | Yes | 137 | 0 | **Prune** |
| feat--second-order-graph | feat/second-order-graph | Yes | 115 | 0 | **Prune** |
| feat--steal-shamelessly | feat/steal-shamelessly | Partially (PR #12 merged, 2 post-merge commits) | 3 | 2 | **Assess** — cherry-pick or rebase the 2 post-merge commits |
| feat--umami-analytics | feat/umami-analytics | No | 130 | 4 | **Assess** |
| review--cross-domain-metaphors | review/cross-domain-metaphors | No | 114 | 44 | **Assess** — likely a design exploration, park or archive |
| main | main | — | 0 | — | **Keep as integration branch** |

### What Exists (on main branch)

- Authoritative PRD: `Metaforge-PRD-2.md`
- Sprint Zero plan: `docs/plans/2026-01-26-sprint-zero.md`
- Design docs: `docs/designs/` (metaphor-forge, 3D graph, etc.)
- Performance notes: `docs/plans/2026-01-28-performance-tuning.md`
- CLAUDE.md with project context — main-branch version shows API MVP-complete, ~300 automated tests, staging deployed, data pipeline ~70% MVP-ready
- Deploy config for staging at `deploy/staging/`
- `.mcp.json` already configured for GSD workflow server (points to project root)
- `docs/reports/` already exists with `2026-02-22-cross-domain-scoring.md`

---

## Migration Steps

### Phase 1: Clean Up Git State

**1.1 Reset root to main**

The root repository is on detached HEAD at `59817af1`. This is NOT a trivially reattachable state — there is a **229-file divergence** between the detached HEAD tree and main. The commit `59817af1` sits on the sprint-zero lineage (a different tree structure from main), even though a same-message commit exists on main.

Pre-flight checks:

```
cd /home/agent/projects/metaforge
git status                     # Check for uncommitted work
git diff --stat HEAD main      # Confirm the 229-file divergence
```

Since the root has no important uncommitted work (GSD and Claude config are untracked and will survive), and all meaningful branches are preserved in worktrees:

```
git checkout -f main           # Force checkout — requires user approval (destructive)
```

If there IS uncommitted work worth keeping, stash first:

```
git stash
git checkout main
git stash pop                  # Resolve any conflicts
```

**1.2a Staging deployment — DECIDED: accept temporary downtime, redeploy from root in Phase 1.8**

The staging server at `metaforge.julianit.me` is deployed from `.worktrees/feat-freq-fam`. Removing the worktree will take the server down. User has accepted temporary downtime during migration — staging will be redeployed from root in Phase 1.8 (immediately after dependency restoration).

**1.2b Prune fully-merged worktrees**

Four worktrees have branches that are fully merged into main and have zero unmerged commits. These are stale and can be removed. The branches can be deleted since all work is in main.

```
# All safe to prune — staging downtime accepted:
git worktree remove --force .worktrees/sprint-zero
git worktree remove --force .worktrees/curated-vocab
git worktree remove --force .worktrees/feat--second-order-graph
git worktree remove --force .worktrees/feat-freq-fam

git branch -d sprint-zero
git branch -d feat/freq-fam
git branch -d feat/curated-property-vocabulary
git branch -d feat/second-order-graph
```

**1.3 Park unmerged worktrees — DECIDED: park all three**

All three branches are active development spikes. Remove the worktrees but preserve the branches for future work:

```
git worktree remove --force .worktrees/feat--steal-shamelessly
git worktree remove --force .worktrees/feat--umami-analytics
git worktree remove --force .worktrees/review--cross-domain-metaphors
# Branches feat/steal-shamelessly, feat/umami-analytics, review/cross-domain-metaphors
# are preserved as local branches — do NOT delete them
```

**1.4 Remove main worktree**

Once root is on `main`, the separate `.worktrees/main` worktree is redundant:

```
git worktree remove --force .worktrees/main
```

**1.5 Reconcile `.mcp.json` and working directory**

The `.mcp.json` has `GSD_WORKFLOW_PROJECT_ROOT=/home/agent/projects/metaforge`. After this migration, the root IS the primary working directory (on `main`). This is correct — no change needed to `.mcp.json`.

The previous convention ("always work in a worktree, not the root") is retired. Post-migration, work happens in the project root on `main`, or in GSD-managed worktrees under `.gsd/worktrees/<MID>/` during milestone execution (worktree isolation mode).

**1.6 Restore dependencies in root**

After checkout, the root needs its dependencies restored since each worktree had independent `node_modules`, venv, and database:

```
cd /home/agent/projects/metaforge/web && npm install
cd /home/agent/projects/metaforge/data-pipeline && python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
cd /home/agent/projects/metaforge && data-pipeline/scripts/restore_db.sh
```

**1.8 Redeploy staging from root**

With root on `main` and dependencies restored, redeploy staging immediately to minimise downtime. The deploy script at `deploy/staging/deploy.sh` is fully self-contained — it pulls, builds Go + frontend, generates configs from templates (substituting `__WORKTREE__`), installs systemd services, and runs health checks.

```
cd /home/agent/projects/metaforge
deploy/staging/deploy.sh
```

The script auto-detects the worktree root from its own location (`SCRIPT_DIR/../..`), so running from the project root means all `__WORKTREE__` substitutions point to `/home/agent/projects/metaforge` — correct for post-migration.

**Verification:** The script runs 4 health checks (API direct, API via Caddy, frontend, thesaurus lookup). All must pass. If any fail, check `systemctl status metaforge-api` and `metaforge-caddy`.

**1.9 Update `.gitignore`**

Add GSD runtime entries (project artifacts like `PROJECT.md` may be tracked later, but runtime files should not be committed):

```
# GSD runtime (system-managed)
.gsd/runtime/
.gsd/notifications.jsonl
.gsd/activity/
.gsd/worktrees/
.gsd/gsd.db
.gsd/gsd.db-wal
.gsd/gsd.db-shm
```

---

### Phase 2: Set GSD Isolation Mode — DECIDED: worktree

User selected `worktree` mode. GSD creates `.gsd/worktrees/<MID>/` per milestone — each gets a full git worktree on a `milestone/<MID>` branch, squash-merged back to main on completion.

Create `.gsd/PREFERENCES.md`. **Note:** the exact format should be verified against GSD documentation — the content below uses the key-value structure from GSD conventions:

```markdown
# GSD Preferences

taskIsolation:
  mode: worktree
  integrationBranch: main

unique_milestone_ids: true
```

---

### Phase 3: Create GSD Foundation Artifacts

**Important:** All content below should be synthesised from main-branch sources, not the stale detached HEAD. Main-branch CLAUDE.md reflects the actual current state: API MVP-complete, ~300 automated tests, staging server deployed, forge endpoint tuning in progress, data pipeline ~70% MVP-ready.

**3.1 PROJECT.md**

Synthesise from main-branch `CLAUDE.md`, `Metaforge-PRD-2.md`, and current codebase state. Should describe what Metaforge is *now* — not history.

Key content:
- Browser-based visual thesaurus with 3D force-directed graph
- Go headless API + Lit/Vite frontend + SQLite + FastText embeddings
- API MVP-complete, ~300 automated tests across Go/TS/Python
- Staging deployed at `metaforge.julianit.me`
- Data pipeline ~70% MVP-ready
- Self-hostable, no accounts in MVP, IndexedDB for local persistence

**3.2 REQUIREMENTS.md**

Extract from `Metaforge-PRD-2.md` using `gsd_requirement_save`. Key requirements:
- Core thesaurus lookup with synonym/antonym/related
- 3D force-directed graph visualisation
- Metaphor Forge creative mode
- HUD results panel
- Performance targets from PRD-2
- IndexedDB local persistence

**3.3 DECISIONS.md**

Seed with key architectural decisions already made:
- Go + chi for backend (stateless, self-hostable)
- Lit + Vite + TypeScript for frontend (no React/Vue)
- SQLite as data store (embedded, no external DB)
- FastText for embeddings
- Gemini for property extraction
- `3d-force-graph` library for 3D visualisation
- Shadow DOM via Lit web components
- UK English throughout

**3.4 KNOWLEDGE.md**

Seed from main-branch CLAUDE.md gotchas and memory entries:
- `@state()` re-render gotcha in Lit
- Shadow DOM `document.activeElement` returns host element
- 3d-force-graph ships inaccurate `.d.ts`
- Three.js WebGPU crashes in happy-dom (mock pattern)
- `sqlite3.connect()` with `with` doesn't close connection
- Go binary at `/usr/local/go/bin/go` needs PATH export

**3.5 STATE.md**

Auto-generated by GSD after milestone planning. Initial state: no active milestones.

---

### Phase 4: Map Existing Work to GSD Milestones

Based on `Metaforge-PRD-2.md` and main-branch `CLAUDE.md` design status:

**Completed (record but don't plan):**
- Sprint Zero — backend complete, ~300 automated tests, endpoints working, staging deployed

**Next milestone (use `gsd_milestone_generate_id` — do not hardcode ID):**
- Phase 1 MVP Frontend — 3D force graph + HUD results panel
  - This is the next stated phase in CLAUDE.md
  - Design is complete in PRD-2
  - Depends on completed Sprint Zero backend

**Future milestones (queue, don't plan yet):**
- Constellation feature (parked, near-horizon per PRD-2)
- Word Hunt (parked per PRD-2)

---

### Phase 5: Tidy Root Files

Several root-level files are pre-GSD planning artifacts that duplicate what GSD will manage:

| File | Action | Reason |
|------|--------|--------|
| `2026-01-25-mvp-implementation-plan.md` | Move to `docs/plans/` | Planning doc, not a root concern |
| `cc-reimagine-with-sqlunet.md` | Move to `docs/designs/` | Design exploration, not a root concern |
| `Metaforge-PRD-2.md` | Keep in root | Authoritative PRD, referenced everywhere |
| `TESTING.md` | Keep in root | Development standards |
| `CLAUDE.md` | Keep in root | Project context for Claude agents |
| `reports/` | Merge into `docs/reports/` | `docs/reports/` already exists with one file — merge, don't overwrite |

**Note:** `project-context-SKILL.md` exists only on the detached HEAD; it was deleted from main in commit `965f26cb`. No action needed — it will disappear when root checks out main.

---

### Phase 6: Remote Branch Cleanup (Optional)

Stale remote branches not associated with any active worktree:
- `origin/claude/execute-sprint-zero-task-5-UHJnC` — CI/agent artifact, safe to delete
- `origin/sqlunet-schema-v2` — old schema exploration, safe to delete
- Remote tracking branches for merged features (sprint-zero, freq-fam, curated-vocab, second-order-graph)

User confirmation required before deleting remote branches.

---

## Execution Order

1. **Phase 1.1** — Reset root to main (check git status first, force checkout)
2. **Phase 1.2** — Prune all fully-merged worktrees (sprint-zero, curated-vocab, second-order-graph, feat-freq-fam — staging downtime begins)
3. **Phase 1.3** — Park unmerged worktrees (remove worktrees, keep branches for steal-shamelessly, umami-analytics, cross-domain-metaphors)
4. **Phase 1.4** — Remove redundant main worktree
5. **Phase 1.5** — Verify `.mcp.json` points to root (should already be correct)
6. **Phase 1.6** — Restore dependencies (`npm install`, venv, DB restore)
7. **Phase 1.8** — **Redeploy staging** from root (`deploy/staging/deploy.sh` — staging back online)
8. **Phase 1.9** — Update `.gitignore` for GSD runtime files
9. **Phase 2** — Set GSD preferences (worktree isolation mode)
10. **Phase 3** — Create foundation artifacts (PROJECT.md, REQUIREMENTS.md, DECISIONS.md, KNOWLEDGE.md)
11. **Phase 4** — Plan first GSD milestone (use `gsd_milestone_generate_id`)
12. **Phase 5** — Tidy root files
13. **Phase 6** — Remote branch cleanup (approved)

All user gates resolved. Phases 1.1–1.7 are mechanical. Phase 2 is a single file write. Phase 3 requires synthesis from existing docs. Phase 4 requires planning with the user. Phases 5–6 are cleanup.

---

## Risks

| Risk | Mitigation |
|------|-----------|
| Root force-checkout destroys uncommitted work | Pre-flight `git status`; stash if anything valuable; untracked files (.gsd, .claude, .mcp.json) survive checkout |
| Staging server down after feat-freq-fam removal | Brief downtime during Phase 1.2–1.8; redeployed from root in Phase 1.8 with health check verification |
| Unmerged worktree work lost during pruning | Branches are preserved even after worktree removal; only delete branches after explicit user decision |
| GSD worktree mode conflicts with existing `.worktrees/` | Old `.worktrees/` fully cleaned up in Phase 1; GSD worktrees live under `.gsd/worktrees/` (different path) |
| Foundation artifacts diverge from PRD-2 | Cross-reference main-branch PRD-2 during creation; REQUIREMENTS.md tracks provenance |
| `.gsd/PREFERENCES.md` format incorrect | Verify format against GSD docs before writing; test with `gsd_milestone_generate_id` |
| Missing dependencies after worktree consolidation | Phase 1.6 explicitly restores npm, venv, and DB |

---

## Resolved Questions

1. **Unmerged branches** — **Park all three.** Active development spikes. Remove worktrees, keep branches.
2. **GSD isolation mode** — **Worktree mode.** GSD manages `.gsd/worktrees/<MID>/` per milestone.
3. **Staging deployment** — **Accept brief downtime.** Remove feat-freq-fam worktree, redeploy from root in Phase 1.8 — staging back online before GSD artifact creation begins.
4. **Remote branch cleanup** — **Approved.** Delete remote tracking branches for merged features + stale CI branches.

---

## Review Log

### Agent Review — 2026-04-26

**14 findings: 2 Critical, 6 Major, 4 Minor, 2 Nit**

| # | Severity | Finding | Resolution |
|---|----------|---------|------------|
| 1 | **Critical** | Detached HEAD analysis wrong — 229-file divergence, not clean checkout | Rewrote Phase 1.1 with force-checkout, pre-flight checks, stash option |
| 2 | **Critical** | Removing feat-freq-fam breaks live staging server | Added Phase 1.2a as hard blocking gate; staging must be repointed first |
| 3 | Major | `feat/steal-shamelessly` already partially merged via PR #12 | Updated branch status table and Phase 1.3 to note 2 post-merge commits |
| 4 | Major | `.mcp.json` cwd points to root, needs reconciliation | Added Phase 1.5 to confirm root is correct working directory post-migration |
| 5 | Major | Phase 3 uses stale detached-HEAD CLAUDE.md data | Added note to use main-branch sources; updated Phase 3.1 with correct state |
| 6 | Major | `.gsd/` and `.mcp.json` not in `.gitignore` | Added Phase 1.9 with specific gitignore entries for GSD runtime files |
| 7 | Major | No dependency restoration after worktree changes | Added Phase 1.6 with npm install, venv, DB restore |
| 8 | Major | Hardcoded M001 conflicts with GSD ID generation | Changed Phase 4 to use `gsd_milestone_generate_id`; removed hardcoded ID |
| 9 | Minor | `.gsd/PREFERENCES.md` format ambiguous | Added note to verify format against GSD docs |
| 10 | Minor | `project-context-SKILL.md` already deleted from main | Removed from Phase 5; added note explaining it only exists on detached HEAD |
| 11 | Minor | `reports/` move would collide with existing `docs/reports/` | Updated Phase 5 to say "merge into" rather than "move to" |
| 12 | Minor | Remote branch cleanup incomplete — missing stale CI branches | Added Phase 6 listing all stale remotes including `claude/...` and `sqlunet-schema-v2` |
| 13 | Nit | Worktree count description imprecise | Fixed: "7 feature worktrees + 1 integration worktree for main" |
| 14 | Nit | 228-file count from stale CODEBASE.md | Removed specific file count from "What Exists" |
