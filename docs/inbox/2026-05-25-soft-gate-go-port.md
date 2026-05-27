# Soft-gate Go port — follow-up

**Status:** open (queued, post-loop-2)

## Context

`evaluate_cascade.py` now supports `gate_mode='soft'` with a sigmoid penalty centred at `concreteness_threshold`. The Python loop harness uses this and measures cohort impact directly. **Production `/forge/suggest` does not yet pick it up** — Go's cascade still uses a hard gate, and (more importantly) Go's SQL CTE pre-filters `gate_dropped` candidates *before* the scorer ever sees them (`api/internal/handler/cascade_pipeline.go:301`).

So the soft-gate's OOD coverage benefit — recovering the ~30% of OOD topics that the hard gate kills — is invisible to users until Go is ported.

## What needs to change

Two layers, both in Go:

### 1. `api/internal/forge/cascade.go` — Config + scorer

Add the two new fields to `CascadeConfig`:

```go
type GateMode int
const (
    GateModeHard GateMode = iota
    GateModeSoft
)

type CascadeConfig struct {
    // ...existing fields...
    GateMode  GateMode  // default: GateModeHard
    GateAlpha float64   // default: 2.0
}
```

Mirror the Python validation in `Validate()`: `GateMode` must be hard or soft; `GateAlpha` must be > 0.

In `evaluateCascadePair` (or equivalent), branch on `GateMode`:

- **Hard**: existing behaviour. Sub-threshold pairs return `CascadeStatusGateDropped`, `FinalScore=0`.
- **Soft**: never drop. Compute `gateScore := sigmoid(GateAlpha * (signedDelta - ConcretenessThreshold))`. Multiply into final_score after all other stages. Status stays `CascadeStatusScored`. `GatePassed` reflects `gateScore >= 0.5` (diagnostic continuity).

Add a stable-form sigmoid helper (mirror `_sigmoid` in `evaluate_cascade.py`).

### 2. `api/internal/handler/cascade_pipeline.go` — CTE filter

The SQL CTE that fetches candidates currently filters out `gate_dropped` rows at the database layer (see comment on line 301). In soft mode this filter is wrong — it removes exactly the pairs soft mode is meant to rescue.

Options:
- **Option A:** Push `gate_mode` into the SQL CTE and skip the filter when soft. Cleanest, but couples SQL to Go config.
- **Option B:** Always fetch all candidates with both concreteness scores (drop only `missing_concreteness`), let the scorer handle gate logic. Slightly more rows per query but `evaluateCascadePair` is fast and the row volume is bounded by the existing `top_k` candidate cap. Probably the right move — keeps SQL agnostic of gate mode.

Option B is the recommended approach. The SQL change is small; the win is a simpler invariant ("SQL surfaces all candidates with concreteness, Go decides what to do with them").

## Tests

Mirror the 7 Python tests in `api/internal/forge/cascade_test.go`. Especially:

- `TestSoftGateRescuesPreviouslyDroppedPair` — a sub-threshold pair returns `CascadeStatusScored` with `FinalScore > 0`.
- `TestSoftGatePreservesClearPassScore` — clear-pass pair retains >85% of hard-mode score at `gate_alpha=2.0`.
- `TestSoftGateMissingConcretenessStillFailsClosed` — soft mode does NOT change the missing-concreteness contract.
- Integration test at `handler_cascade_test.go` level: a very-concrete topic (e.g. "boulder") returns nonzero scored candidates under soft mode where hard mode returns the empty set.

## Wiring

Add env var `METAFORGE_FORGE_GATE_MODE` (`hard`|`soft`, default `hard`) and `METAFORGE_FORGE_GATE_ALPHA` (default `2.0`). Mirror the existing `METAFORGE_FORGE_CANDIDATES` pattern in `cmd/metaforge/main.go`.

## Why post-loop-2?

The Python loop will tune `gate_alpha`. Porting before tuning means rebuilding twice. Land the port after the loop ratifies the production `gate_alpha`, then commit the tuned value as the Go default.

## Acceptance

- All Python and Go cascade tests green.
- `loop1_eyeball_harness.py` re-run shows the previously-erroring 6 OOD topics now return scored candidates (status='scored', final_score in [0.01, 0.5] range).
- `loop_baseline.json` ratios reproduce within bootstrap-resample noise between Python and Go scoring of the same cohort under the same gate mode + alpha.
