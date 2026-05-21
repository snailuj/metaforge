# Review Loop — M03-S05 Forge Integration

**Branch:** `m03/cascade-gate-and-rank`
**Base:** `251b41b1` (M03 cascade Python work + retro)
**Head at start:** `3223aef4`
**Adapters:** pr-review-toolkit, superpowers, standards, ux-designer (no-op — no UI files in scope)

## Scope

17 commits since base, +3934 lines / −17:

```
api/cmd/metaforge/main.go                    (+7/-2)   — --cascade flag
api/internal/db/cascade.go                   (+228)    — CascadeCandidate, batch props, gate-pushdown CTE
api/internal/db/cascade_cache.go             (+109)    — CascadeCache eager load
api/internal/db/cascade_cache_test.go        (+71)
api/internal/db/cascade_test.go              (+152)
api/internal/forge/cascade.go                (+194)    — JaccardSalience, ReRankBonus, CascadeCosineDistance, EvaluateCascadePair
api/internal/forge/cascade_parity_test.go    (+206)    — Python-parity test
api/internal/forge/cascade_test.go           (+212)
api/internal/forge/forge.go                  (+9)      — Match cascade fields
api/internal/forge/forge_test.go             (+29)
api/internal/handler/handler.go              (+177/-15)— cascade branch
api/internal/handler/handler_cascade_test.go (+146)
docs/plans/2026-05-21-m03-s05-forge-integration.md (+2020)
docs/plans/2026-05-21-m03-s05-smoke-test-crib.md   (+245)
docs/roadmap/M04-cosine-candidate-gen-roadmap.md   (+128)
docs/roadmap/PIPELINE.md                           (+18/-2)
```

## Deferrals Ledger

(empty at loop start)

---
