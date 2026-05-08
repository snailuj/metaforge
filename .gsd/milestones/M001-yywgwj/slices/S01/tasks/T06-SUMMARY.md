---
id: T06
parent: S01
milestone: M001-yywgwj
key_files:
  - /home/agent/projects/metaforge/.worktrees/next/data-pipeline/output/lexicon_v2.db
  - /home/agent/projects/metaforge/.worktrees/next/data-pipeline/output/lexicon_v2.sql
key_decisions:
  - Bypassed deploy/staging/deploy.sh — its `git pull --ff-only` requires upstream tracking that neither the M001 milestone branch nor the staging branch has, and api/web are byte-identical with staging branch (so the rebuild + service-reinstall steps would be no-ops with risk of disrupting working systemd/Caddy config). Did the operative payload manually: stop → swap db (and sql) → start → verify.
  - Backed up the prior staging DB to lexicon_v2.db.bak.<epoch> rather than deleting — staging was previously running on the pre-V2 dump so this gives a clean rollback target if T07+ uncovers issues with the V2 dataset under live traffic.
duration: 
verification_result: passed
completed_at: 2026-05-02T13:53:55.671Z
blocker_discovered: false
---

# T06: deploy: V2-enriched lexicon_v2.db serving on metaforge-next.julianit.me — forge salience visible, /health 200

**deploy: V2-enriched lexicon_v2.db serving on metaforge-next.julianit.me — forge salience visible, /health 200**

## What Happened

Deployed the V2-enriched database (333 MB, 10,943 enriched synsets, 129,804 curated property rows) to metaforge-next.julianit.me. Took the data-only path: stopped `metaforge-api-staging`, swapped `next/data-pipeline/output/lexicon_v2.db` (backed up the prior 239 MB pre-V2 file with a timestamped suffix), synced the regenerable `lexicon_v2.sql` dump alongside it, restarted the service, and verified.

Did NOT run `deploy/staging/deploy.sh` end-to-end. Two reasons: (1) the script's first step is `git pull --ff-only`, which fails because neither our `milestone/M001-yywgwj` branch nor the staging worktree's `staging` branch has an upstream configured; (2) `git diff 78f9bb7c..HEAD -- api/ web/` is empty — the Go binary at `next/api/metaforge` and `next/web/dist/` already match our code, so a full rebuild would be a no-op. Confirmed the existing binary already implements salience_sum (db.go:109 `SalienceSum float64 `json:"salience_sum"`) and the cluster_id-keyed schema, so it serves V2 data unchanged.

Verified the canonical checks: `curl 'metaforge-next.julianit.me/forge/suggest?word=anger' | jq '.suggestions[0].salience_sum'` → 4.85; `curl /health` → 200. The forge response shows real V2 enrichment — `dustup` is the top suggestion for "anger" with shared_properties [charged, heated, escalate, interpersonal, confrontational], salience_sum 4.85, tier "legendary". Thesaurus path also confirmed working (`/thesaurus/lookup?word=happy` returns senses). Captured the staging-deploy pattern as MEM024 so future data-only deploys skip the broken `deploy.sh` git step.

## Verification

Ran the two verification commands specified in the task plan against the live staging endpoint. Both pass. Inspected systemd journal to confirm the new process loaded the swapped DB path and is serving requests with 200 status.

## Verification Evidence

| # | Command | Exit Code | Verdict | Duration |
|---|---------|-----------|---------|----------|
| 1 | `curl -s 'https://metaforge-next.julianit.me/forge/suggest?word=anger' | jq '.suggestions[0].salience_sum'` | 0 | ✅ pass — returned 4.85 (non-zero, V2 salience visible) | 1200ms |
| 2 | `curl -s -o /dev/null -w '%{http_code}' --max-time 5 https://metaforge-next.julianit.me/health` | 0 | ✅ pass — returned 200 | 150ms |
| 3 | `sqlite3 next/data-pipeline/output/lexicon_v2.db 'SELECT COUNT(*) FROM synset_properties_curated; SELECT COUNT(DISTINCT synset_id) FROM synset_properties_curated;'` | 0 | ✅ pass — 129804 curated rows / 10943 enriched synsets confirms V2 dataset on staging disk | 80ms |
| 4 | `systemctl is-active metaforge-api-staging` | 0 | ✅ pass — active | 30ms |
| 5 | `curl -s 'https://metaforge-next.julianit.me/thesaurus/lookup?word=happy'` | 0 | ✅ pass — thesaurus path returns senses (regression check) | 1411ms |

## Deviations

Did not invoke deploy/staging/deploy.sh end-to-end. Rationale logged in narrative + keyDecisions: git pull blocked by no-upstream, and api/ + web/ are unchanged from the staging branch baseline (78f9bb7c). Operative steps (DB swap + service bounce + health check) executed manually and verified.

## Known Issues

deploy/staging/deploy.sh's git pull step will continue to fail in auto-mode until the staging branch (or whichever branch is being deployed from) has a working upstream, OR the script gracefully handles "no upstream". Worth tracking as a small backlog item to make the script robust for future redeploys; not a blocker for this slice.

## Files Created/Modified

- `/home/agent/projects/metaforge/.worktrees/next/data-pipeline/output/lexicon_v2.db`
- `/home/agent/projects/metaforge/.worktrees/next/data-pipeline/output/lexicon_v2.sql`
