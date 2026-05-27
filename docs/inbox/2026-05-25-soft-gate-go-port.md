# Soft-gate Go port — spec

**Status:** Spec ratified 2026-05-27. Implementation plan to follow under `docs/plans/`.
**Branch:** `m04/soft-gate-go-port` (worktree `.worktrees/soft-gate-go-port`).

## Context

After loops 1-3 ratified a soft-gate sigmoid penalty plus several other cascade-config knobs in Python (`evaluate_cascade.py`), production `/forge/suggest` still scores with the older hard-gate config. Two layers diverge:

1. `api/internal/forge/cascade.go` — `CascadeConfig` is missing the loop-tuned knobs entirely (no `GateMode`, `GateAlpha`, `OrtonyWeight`, `OrtonyScoring`, `RerankExponent`, `ConcretenessBonusCoef`); `Alpha` and `DCap` defaults are stale.
2. `api/internal/handler/cascade_pipeline.go` — SQL CTE pre-filters `gate_dropped` rows at the DB layer (`:301`). In soft mode this filter removes the exact rows the soft gate is meant to rescue.

So the soft gate's OOD-coverage benefit (~30% of high-concreteness OOD topics rescued from empty-result) is invisible to users until both layers are ported.

## Scope decision (2026-05-27)

**Scope B — full loop-config port.** Land every Python `CascadeConfig` field in Go, with Python's production-blessed values as Go defaults. This preserves the spec's original acceptance criterion 3 (Python↔Go ratio parity) and removes future drift between the loop harness and production.

Rationale: the Karpathy-loop noise audit (`loop-meta` branch) showed individual Phase 2 commits are mostly within 1σ, but their *cumulative* effect plus the iter-17 Pareto trade (`ortony_weight=1.75` + `rerank_exponent=0.12`) drove the indisputable +50-pair-flip Lakoff lift. Importing only soft-gate would leave that load-bearing Lakoff signal on the floor in production.

## Confirmed defaults

Go `DefaultCascadeConfig` will return values that mirror Python's `PRODUCTION_CASCADE_CONFIG` exactly:

| Field (Go) | Field (Python) | Old Go default | New Go default | Source |
|---|---|---|---|---|
| `ConcretenessThreshold` | `concreteness_threshold` | 1.0 | 1.0 | unchanged |
| `Alpha` | `alpha` | 1.0 | **0.75** | L3-19 |
| `DCap` | `d_cap` | 0.77 | **0.68** | L1-6 |
| `Composition` | `composition` | additive | additive | unchanged |
| `RerankExponent` | `rerank_exponent` | — (absent) | **0.12** | L2-17 Pareto |
| `ConcretenessBonusCoef` | `concreteness_bonus_coef` | — (absent) | **0.002** | L1-10 |
| `OrtonyWeight` | `ortony_weight` | — (absent) | **1.75** | L2-17 Pareto |
| `OrtonyScoring` | `ortony_scoring` | — (absent) | `"jaccard_salience"` | structural |
| `GateMode` | `gate_mode` | — (absent) | **`GateModeSoft`** | matches Python production |
| `GateAlpha` | `gate_alpha` | — (absent) | **3.0** | L3-18 |

Note: M04/M05 fields already in Go (`Mode`, `EmbeddingDMin`, `EmbeddingDMax`, `EmbeddingTopK`, `Gamma`) stay as-is — they have no Python counterpart in the loop harness and are unaffected by this port.

## Design

### Layer 1 — `api/internal/forge/cascade.go`

**1a. Enum + struct extension.**

```go
type GateMode int
const (
    GateModeHard GateMode = iota
    GateModeSoft
)

type OrtonyScoring string
const (
    OrtonyScoringJaccardSalience OrtonyScoring = "jaccard_salience"
)
// Other scoring fns in Python (`jaccard_raw`, `cosine_salience`,
// `ortony_vehicle_salience`, `ortony_imbalance`, `ortony_log_ratio`,
// `random_uniform`) live in `evaluate_aptness.SCORING_FNS` and are used
// only by the sweep / aptness harness. Production scoring is fixed to
// `jaccard_salience`. Adding more Go scoring fns is out of scope for
// this port — extend if/when production needs them.

type CascadeConfig struct {
    // existing fields ...
    RerankExponent        float64
    ConcretenessBonusCoef float64
    OrtonyWeight          float64
    OrtonyScoring         OrtonyScoring
    GateMode              GateMode
    GateAlpha             float64
    // M04 / M05 fields unchanged
}
```

**1b. `DefaultCascadeConfig()`** updates to the values in the table above.

**1c. `Validate()`** extensions:
- `GateMode` must be `GateModeHard` or `GateModeSoft`.
- `GateAlpha` must be `> 0` and finite.
- `OrtonyWeight`, `RerankExponent`, `ConcretenessBonusCoef` must be `>= 0` and finite.
- `OrtonyScoring` must be one of the defined constants.

**1d. Sigmoid helper.** Stable-form `sigmoid(x float64) float64` mirroring `_sigmoid` in `evaluate_cascade.py` (positive-x and negative-x branches to avoid `math.Exp` overflow).

**1e. `EvaluateCascadePair` branching.** The scorer must mirror Python's `evaluate_cascade_pair` exactly:
- **Hard mode + sub-threshold:** existing behaviour — return `CascadeStatusGateDropped`, `FinalScore=0`.
- **Soft mode:** never gate-drop. Compute the cascade as usual through ortony + rerank + concreteness bonus + ortony_weight composition; then multiply by `sigmoid(GateAlpha * (signedDelta - ConcretenessThreshold))`. Status stays `CascadeStatusScored`. `GatePassed` reports `gateScore >= 0.5` for diagnostic continuity.
- **Missing concreteness:** still fails closed in *both* modes (this is the contract for data-quality issues, distinct from gating).

### Layer 2 — `api/internal/handler/cascade_pipeline.go`

Drop the `gate_dropped` WHERE clause in the cluster-mate CTE. **Keep** the `missing_concreteness` filter — that's a data-quality contract, not a gate. The new SQL invariant is: "SQL surfaces all candidates with concreteness data; Go decides what to do with them."

This is the **Option B** approach from the original spec (SQL agnostic of gate mode). Latency impact: small — extra rows are bounded by the existing top-K candidate cap; per-pair scoring is microseconds.

### Layer 3 — env-var wiring (`cmd/metaforge/main.go`)

Mirror the existing `METAFORGE_FORGE_CANDIDATES` pattern. New env vars:

| Env var | Type | Default | Notes |
|---|---|---|---|
| `METAFORGE_FORGE_GATE_MODE` | `hard` \| `soft` | `soft` | Operator override |
| `METAFORGE_FORGE_GATE_ALPHA` | float | `3.0` | Operator override |
| `METAFORGE_FORGE_ALPHA` | float | `0.75` | Operator override |
| `METAFORGE_FORGE_DCAP` | float | `0.68` | Operator override |
| `METAFORGE_FORGE_RERANK_EXPONENT` | float | `0.12` | Operator override |
| `METAFORGE_FORGE_CONCRETENESS_BONUS_COEF` | float | `0.002` | Operator override |
| `METAFORGE_FORGE_ORTONY_WEIGHT` | float | `1.75` | Operator override |
| `METAFORGE_FORGE_ORTONY_SCORING` | string | `jaccard_salience` | Operator override |

All parse errors fail loud at startup (don't silently fall back to default).

## Tests

Mirror Python's `test_evaluate_cascade.py` soft-gate suite (7 tests) one-for-one in `api/internal/forge/cascade_test.go`:

1. `TestSoftGateRescuesPreviouslyDroppedPair` — sub-threshold pair under soft mode returns `CascadeStatusScored` with `FinalScore > 0`.
2. `TestSoftGatePreservesClearPassScore` — clear-pass pair retains ≥85% of hard-mode score at `GateAlpha=3.0` (note: spec value updated from `2.0`).
3. `TestSoftGateMissingConcretenessStillFailsClosed` — soft mode does NOT change the missing-concreteness contract.
4. `TestSoftGateGatePassedDiagnostic` — `GatePassed` reflects `gateScore >= 0.5` regardless of final-score magnitude.
5. `TestSoftGateMonotonicInGateAlpha` — for a fixed sub-threshold pair, higher `GateAlpha` produces stricter penalty.
6. `TestSoftGateValidate` — invalid `GateAlpha` (≤0, NaN, Inf) rejected by `Validate()`.
7. `TestSoftGateGateModeDefault` — `DefaultCascadeConfig().GateMode == GateModeSoft`.

Plus existing-field coverage:
- `TestOrtonyWeightAppliedInComposition` — `OrtonyWeight=1.75` multiplies the ortony term as expected.
- `TestConcretenessBonusCoefScalesBonus` — sanity check on the additive bonus.
- `TestRerankExponentAffectsRerankBonus` — exponent applied correctly.

Integration test in `handler_cascade_test.go`:
- `TestHandlerSoftGateRescuesHighConcretenessTopic` — a high-concreteness topic (e.g. "boulder") returns a nonzero scored top-K under soft mode where hard mode returns empty.

**Python↔Go parity test.** A new harness script (Python side) that:
- Picks 50 pairs from the Phase 2 + Lakoff cohorts.
- Calls `evaluate_cascade_pair` in Python with `PRODUCTION_CASCADE_CONFIG`.
- Calls `/forge/suggest` (or a new debug endpoint) in Go with the same pair as candidate.
- Asserts `|python_final_score - go_final_score| < 1e-6` for every pair.

If the parity test fails on any pair, the Go scorer diverges from Python — block merge until aligned.

## Acceptance

1. All Python and Go cascade tests green (including the 10 new Go tests).
2. `loop1_eyeball_harness.py` re-run shows the previously-erroring 2 OOD topics (`pint`, `jump`) now return a scored top-K with `final_score` in `[0.01, 0.5]`.
3. Python↔Go parity test passes (≤1e-6 absolute deviation on all 50 sample pairs).
4. `loop_baseline.json` ratios reproduce within bootstrap-resample noise (σ ≈ 0.075 on the merged-main measurement) when Python and Go score the Phase 2 cohort under identical config.
5. Staging deploy: `metaforge-next.julianit.me` `/forge/suggest?word=boulder` returns nonzero scored candidates.

## Non-goals

- M04 cosine candidate generation (separate milestone, will land on top of this).
- Removing/refactoring M05 type-aligned `Gamma` (separate concern; preserved as-is).
- Removing the `multiplicative` composition mode (Python keeps it as a non-production option; Go can keep its existing implementation untouched).
