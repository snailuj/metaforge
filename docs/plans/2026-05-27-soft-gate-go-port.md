# Soft-gate Go port — implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Port the loop-tuned Python `CascadeConfig` to Go in full (scope B), so production `/forge/suggest` scores identically to `data-pipeline/scripts/evaluate_cascade.py` under the same config, and the soft-gate sigmoid rescues high-concreteness OOD topics that the hard gate kills.

**Architecture:** Add the missing `CascadeConfig` fields and scoring stages to `api/internal/forge/cascade.go`, drop the `signed_delta >= threshold` filter from the candidate-fetch SQL CTE in `api/internal/db/cascade.go`, wire env vars in `cmd/metaforge/main.go`, and validate end-to-end via a new Python↔Go parity harness plus a re-run of `loop1_eyeball_harness.py`.

**Tech Stack:** Go (`api/`, `cmd/metaforge/main.go`), Python (`data-pipeline/scripts/`, pytest), SQLite (`data-pipeline/output/lexicon_v2.db`).

**Spec:** `docs/inbox/2026-05-25-soft-gate-go-port.md` (ratified 2026-05-27, scope B).

---

## File Structure

| File | Purpose | Change shape |
|---|---|---|
| `api/internal/forge/cascade.go` | `CascadeConfig`, `EvaluateCascadePair`, `Validate`, `DefaultCascadeConfig`. | Extend struct (6 new fields). Add sigmoid helper. Insert weight/bonus/sigmoid stages mirroring Python. Update defaults + validation. |
| `api/internal/forge/cascade_test.go` | Unit tests. | Add 10 new tests (7 soft-gate + 3 field-coverage). |
| `api/internal/db/cascade.go` | Candidate-fetch SQL CTE. | Drop the `(scv.score - sct.score) >= ?` WHERE clause; bound parameter list shrinks by one. |
| `api/internal/db/cascade_test.go` | DB-layer tests. | Add coverage that sub-threshold concreteness rows now surface. |
| `api/internal/handler/cascade_pipeline.go` | Wires DB rows into `EvaluateCascadePair`. | Update the line-301 comment (filter is gone); ensure scorer handles all rows including those that now route to `gate_dropped` (hard mode) or scored-with-penalty (soft mode). |
| `api/internal/handler/handler_cascade_test.go` | Handler integration. | Add `TestHandlerSoftGateRescuesHighConcretenessTopic`. |
| `api/cmd/metaforge/main.go` | Env var wiring. | Add 8 new env vars mirroring the `METAFORGE_FORGE_*` pattern. |
| `data-pipeline/scripts/parity_test_go_vs_python.py` | New parity harness. | Picks 50 pairs from the Phase 2 + Lakoff cohorts, scores each in Python and via Go (subprocess + `/forge/suggest`), asserts ≤1e-6 absolute deviation. |

---

## Task Ordering Note

Tasks 1-5 each add one Python field to the Go config. Each task:
1. Writes a failing test against the *intended* scoring behaviour with the new field.
2. Adds the struct field + scoring logic.
3. Re-runs tests, expects pass.
4. Commits.

Tasks 6-7 finalise defaults and validation in one sweep. Task 8 drops the SQL filter (smallest commit, biggest behaviour change). Tasks 9-12 are wiring + integration. Task 13 is verification.

Each scoring-logic change in tasks 1-5 must keep older tests green — there are existing tests that use `DefaultCascadeConfig`, so the defaults stay backward-compatible until task 6 flips them to loop-tuned values.

---

### Task 1: Add `RerankExponent` field and apply it in `ReRankBonus`

**Files:**
- Modify: `api/internal/forge/cascade.go` (CascadeConfig struct + ReRankBonus + EvaluateCascadePair)
- Test: `api/internal/forge/cascade_test.go`

- [ ] **Step 1: Write failing tests**

Add to `cascade_test.go`:

```go
func TestReRankBonus_LinearWhenExponentOne(t *testing.T) {
	// exponent=1.0 must reproduce the historical linear shape.
	got := ReRankBonusPow(0.5, 1.0, 1.0)
	if math.Abs(got-0.5) > 1e-9 {
		t.Errorf("expected 0.5 for d=0.5 dCap=1.0 exp=1.0, got %v", got)
	}
}

func TestReRankBonus_ExponentBelowOneAmplifiesSmallDistances(t *testing.T) {
	// d/dCap = 0.5; exp=0.5 → sqrt(0.5) ≈ 0.707.
	got := ReRankBonusPow(0.5, 1.0, 0.5)
	if math.Abs(got-math.Sqrt(0.5)) > 1e-9 {
		t.Errorf("expected sqrt(0.5), got %v", got)
	}
}

func TestReRankBonus_ExponentAboveOneSuppressesSmallDistances(t *testing.T) {
	// d/dCap = 0.5; exp=2.0 → 0.25.
	got := ReRankBonusPow(0.5, 1.0, 2.0)
	if math.Abs(got-0.25) > 1e-9 {
		t.Errorf("expected 0.25, got %v", got)
	}
}

func TestReRankBonus_SaturatesAtOneRegardlessOfExponent(t *testing.T) {
	for _, exp := range []float64{0.12, 0.5, 1.0, 2.0} {
		got := ReRankBonusPow(2.0, 1.0, exp)
		if math.Abs(got-1.0) > 1e-9 {
			t.Errorf("exp=%v saturation broke: got %v", exp, got)
		}
	}
}

func TestRerankExponent_AppliedInEvaluateCascadePair(t *testing.T) {
	// Build a pair that reaches the rerank stage. ortony=0.5, cos d=0.34,
	// dCap=0.68, exp=0.12 → bonus = (0.34/0.68)^0.12 = 0.5^0.12 ≈ 0.92.
	// Alpha=0.75, additive composition, ortony_weight=1.0.
	// Expect final ≈ 0.5 + 0.75 * 0.92 = 1.19 (close to).
	cfg := CascadeConfig{
		ConcretenessThreshold: 1.0, Alpha: 0.75, DCap: 0.68,
		Composition: CompositionAdditive,
		RerankExponent: 0.12,
		// other fields zero/default — Validate not called for this test.
	}
	tc, vc := 2.0, 4.0
	in := CascadeInputs{
		TopicConcreteness:   &tc,
		VehicleConcreteness: &vc,
		TopicProperties:     map[int64]float64{1: 1.0, 2: 1.0},
		VehicleProperties:   map[int64]float64{1: 1.0, 2: 1.0}, // ortony=1.0
		// Centroids set to produce cos distance ≈ 0.34 — use orthogonal-ish vectors:
		TopicCentroid:   []float32{1.0, 0.0, 0.5},
		VehicleCentroid: []float32{0.7, 0.5, 0.5},
	}
	r := EvaluateCascadePair(in, cfg)
	if r.Status != CascadeStatusScored || r.FinalScore == nil {
		t.Fatalf("expected scored, got %v", r.Status)
	}
	// Compute expected from the same arithmetic — keeps the test honest if
	// the centroid choice changes later.
	d, _ := CascadeCosineDistance(in.TopicCentroid, in.VehicleCentroid)
	want := 1.0 + cfg.Alpha*math.Pow(d/cfg.DCap, cfg.RerankExponent)
	if math.Abs(*r.FinalScore-want) > 1e-6 {
		t.Errorf("final mismatch: got %v want %v", *r.FinalScore, want)
	}
}
```

- [ ] **Step 2: Run tests to verify they fail**

```
cd api && go test ./internal/forge/ -run "TestReRankBonus_|TestRerankExponent_" -v
```

Expected: FAIL (undefined `ReRankBonusPow`, undefined `RerankExponent`).

- [ ] **Step 3: Add the field and the power-aware helper**

Edit `api/internal/forge/cascade.go`:

```go
// After ReRankBonus, add:

// ReRankBonusPow is ReRankBonus with a power transform on the open
// interval (0, 1). exponent=1.0 reproduces ReRankBonus exactly. Used
// inside EvaluateCascadePair when CascadeConfig.RerankExponent is set.
// Saturation guards at 0 and 1 are independent of exponent.
func ReRankBonusPow(d, dCap, exponent float64) float64 {
	if dCap <= 0 {
		return 0.0
	}
	ratio := d / dCap
	if ratio <= 0.0 {
		return 0.0
	}
	if ratio >= 1.0 {
		return 1.0
	}
	return math.Pow(ratio, exponent)
}
```

Extend the struct (in the `CascadeConfig` declaration):

```go
type CascadeConfig struct {
	ConcretenessThreshold float64
	Alpha                 float64
	DCap                  float64
	Composition           Composition
	RerankExponent        float64 // power transform on (d/DCap) in the rerank stage. 1.0 = linear (back-compat).

	// ... existing M04 / M05 fields ...
}
```

Wire it into `EvaluateCascadePair`. Find the line:

```go
rb := ReRankBonus(d, cfg.DCap)
```

Replace with:

```go
exp := cfg.RerankExponent
if exp == 0 {
	exp = 1.0 // back-compat: zero means "not set", use linear shape
}
rb := ReRankBonusPow(d, cfg.DCap, exp)
```

- [ ] **Step 4: Run tests to verify pass**

```
cd api && go test ./internal/forge/ -v
```

Expected: all green (new 5 tests pass; existing tests still pass because `RerankExponent` defaults to zero → linear shape).

- [ ] **Step 5: Commit**

```bash
git add api/internal/forge/cascade.go api/internal/forge/cascade_test.go
git commit -m "feat(cascade): RerankExponent field — power transform on rerank bonus

Mirrors Python's rerank_exponent (production-tuned to 0.12 at L2-17). Zero
value falls back to linear shape so DefaultCascadeConfig stays
backward-compatible until task 6 flips the default."
```

---

### Task 2: Add `ConcretenessBonusCoef` field and apply post-composition bonus

**Files:**
- Modify: `api/internal/forge/cascade.go`
- Test: `api/internal/forge/cascade_test.go`

- [ ] **Step 1: Write failing tests**

```go
func TestConcretenessBonusCoef_ZeroDisables(t *testing.T) {
	// With coef=0, post-composition score equals pre-bonus score.
	cfg := CascadeConfig{
		ConcretenessThreshold: 1.0, DCap: 0.68,
		Composition: CompositionAdditive,
		ConcretenessBonusCoef: 0.0,
	}
	tc, vc := 1.0, 4.0
	in := CascadeInputs{
		TopicConcreteness:   &tc,
		VehicleConcreteness: &vc,
		TopicProperties:     map[int64]float64{1: 1.0},
		VehicleProperties:   map[int64]float64{1: 1.0}, // ortony=1.0
	}
	r := EvaluateCascadePair(in, cfg)
	if r.Status != CascadeStatusScored {
		t.Fatalf("expected scored, got %v", r.Status)
	}
	if math.Abs(*r.FinalScore-1.0) > 1e-9 {
		t.Errorf("coef=0 must not add bonus: got %v", *r.FinalScore)
	}
}

func TestConcretenessBonusCoef_AppliedToResidual(t *testing.T) {
	// vc - tc = 3.0; threshold = 1.0; residual = 2.0; coef = 0.1.
	// Expected bonus = 0.1 * 2.0 = 0.2 added to final.
	cfg := CascadeConfig{
		ConcretenessThreshold: 1.0, DCap: 0.68,
		Composition: CompositionAdditive,
		ConcretenessBonusCoef: 0.1,
	}
	tc, vc := 1.0, 4.0
	in := CascadeInputs{
		TopicConcreteness:   &tc,
		VehicleConcreteness: &vc,
		TopicProperties:     map[int64]float64{1: 1.0},
		VehicleProperties:   map[int64]float64{1: 1.0},
	}
	r := EvaluateCascadePair(in, cfg)
	if r.Status != CascadeStatusScored {
		t.Fatalf("expected scored, got %v", r.Status)
	}
	want := 1.0 + 0.1*2.0
	if math.Abs(*r.FinalScore-want) > 1e-9 {
		t.Errorf("expected %v, got %v", want, *r.FinalScore)
	}
}

func TestConcretenessBonusCoef_OnlyAppliesAboveThreshold(t *testing.T) {
	// Pair JUST at threshold: residual=0; bonus=0.
	cfg := CascadeConfig{
		ConcretenessThreshold: 1.0, DCap: 0.68,
		Composition: CompositionAdditive,
		ConcretenessBonusCoef: 0.5,
	}
	tc, vc := 1.0, 2.0 // signed_delta = 1.0 = threshold
	in := CascadeInputs{
		TopicConcreteness:   &tc,
		VehicleConcreteness: &vc,
		TopicProperties:     map[int64]float64{1: 1.0},
		VehicleProperties:   map[int64]float64{1: 1.0},
	}
	r := EvaluateCascadePair(in, cfg)
	if math.Abs(*r.FinalScore-1.0) > 1e-9 {
		t.Errorf("at-threshold pair must not get bonus: got %v", *r.FinalScore)
	}
}
```

- [ ] **Step 2: Run tests, verify FAIL**

```
cd api && go test ./internal/forge/ -run "TestConcretenessBonusCoef_" -v
```

- [ ] **Step 3: Add field + implementation**

In `CascadeConfig`:

```go
ConcretenessBonusCoef float64 // additive bonus on signed-delta residual above threshold. 0 disables.
```

In `EvaluateCascadePair`, after the existing composition block and *before* the M05 type-diversity bonus:

```go
// Stage 4: concreteness-delta residual bonus. Mirrors Python evaluate_cascade.py.
// Only positive residuals contribute; the gate guarantees signed >= threshold
// in hard mode, but in soft mode we may have signed < threshold and the
// residual is then negative — clamp to 0 by gating on the sign.
if cfg.ConcretenessBonusCoef > 0.0 {
	residual := signed - cfg.ConcretenessThreshold
	if residual > 0.0 {
		final = final + cfg.ConcretenessBonusCoef*residual
	}
}
```

- [ ] **Step 4: Run tests**

```
cd api && go test ./internal/forge/ -v
```

Expected: all green.

- [ ] **Step 5: Commit**

```bash
git add api/internal/forge/cascade.go api/internal/forge/cascade_test.go
git commit -m "feat(cascade): ConcretenessBonusCoef — additive bonus on delta residual

Mirrors Python's concreteness_bonus_coef (production-tuned to 0.002 at L1-10).
Coef=0 disables stage entirely so existing tests using DefaultCascadeConfig
continue to pass."
```

---

### Task 3: Add `OrtonyWeight` field and apply as pre-composition multiplier

**Files:**
- Modify: `api/internal/forge/cascade.go`
- Test: `api/internal/forge/cascade_test.go`

- [ ] **Step 1: Write failing test**

```go
func TestOrtonyWeight_MultipliesOrtonyTerm(t *testing.T) {
	// ortony=0.5 raw, weight=1.75 → weighted=0.875.
	// No centroid → final = weighted_ortony.
	cfg := CascadeConfig{
		ConcretenessThreshold: 1.0,
		Composition: CompositionAdditive,
		OrtonyWeight: 1.75,
	}
	tc, vc := 1.0, 3.0
	in := CascadeInputs{
		TopicConcreteness:   &tc,
		VehicleConcreteness: &vc,
		TopicProperties:     map[int64]float64{1: 0.5, 2: 1.0},
		VehicleProperties:   map[int64]float64{1: 0.5, 2: 0.0, 3: 1.0},
		// no centroids → no rerank bonus
	}
	r := EvaluateCascadePair(in, cfg)
	if r.Status != CascadeStatusScored {
		t.Fatalf("expected scored, got %v", r.Status)
	}
	// ortony (jaccard_salience) computed by JaccardSalience helper —
	// compute expected the same way to stay decoupled from internal
	// representation choices.
	wantOrt := JaccardSalience(in.TopicProperties, in.VehicleProperties)
	want := wantOrt * 1.75
	if math.Abs(*r.FinalScore-want) > 1e-9 {
		t.Errorf("expected weighted=%v, got final=%v", want, *r.FinalScore)
	}
	// Diagnostic: raw OrtonyScore field stays unweighted.
	if math.Abs(*r.OrtonyScore-wantOrt) > 1e-9 {
		t.Errorf("OrtonyScore diagnostic should be raw, got %v want %v",
			*r.OrtonyScore, wantOrt)
	}
}

func TestOrtonyWeight_ZeroFallsBackToOne(t *testing.T) {
	// Zero value means "not set" — apply identity (1.0) so existing
	// configs that don't set OrtonyWeight behave unchanged.
	cfg := CascadeConfig{
		ConcretenessThreshold: 1.0,
		Composition: CompositionAdditive,
		OrtonyWeight: 0.0,
	}
	tc, vc := 1.0, 3.0
	in := CascadeInputs{
		TopicConcreteness:   &tc,
		VehicleConcreteness: &vc,
		TopicProperties:     map[int64]float64{1: 1.0},
		VehicleProperties:   map[int64]float64{1: 1.0},
	}
	r := EvaluateCascadePair(in, cfg)
	if math.Abs(*r.FinalScore-1.0) > 1e-9 {
		t.Errorf("OrtonyWeight=0 should behave as 1.0, got %v", *r.FinalScore)
	}
}
```

- [ ] **Step 2: Run tests, verify FAIL**

```
cd api && go test ./internal/forge/ -run "TestOrtonyWeight_" -v
```

- [ ] **Step 3: Add field + implementation**

In `CascadeConfig`:

```go
OrtonyWeight float64 // multiplicative weight on the ortony term pre-composition. 0 treated as 1.0.
```

In `EvaluateCascadePair`, after the line `ortony := JaccardSalience(...)`, before the composition block:

```go
ortonyWeight := cfg.OrtonyWeight
if ortonyWeight == 0 {
	ortonyWeight = 1.0 // back-compat: zero means "not set", identity weight
}
weightedOrtony := ortony * ortonyWeight
```

Then replace `final := ortony` and the composition cases:

```go
final := weightedOrtony
if bonus != nil {
	switch cfg.Composition {
	case CompositionAdditive:
		final = weightedOrtony + cfg.Alpha*(*bonus)
	case CompositionMultiplicative:
		final = weightedOrtony * (1.0 + cfg.Alpha*(*bonus))
	}
}
```

(Keep the diagnostic `OrtonyScore: &ortony` unchanged — raw ortony, not weighted.)

- [ ] **Step 4: Run tests**

```
cd api && go test ./internal/forge/ -v
```

Expected: green.

- [ ] **Step 5: Commit**

```bash
git add api/internal/forge/cascade.go api/internal/forge/cascade_test.go
git commit -m "feat(cascade): OrtonyWeight — multiplicative weight on ortony term

Mirrors Python's ortony_weight (production-tuned to 1.75 at L2-17 — the
Pareto commit that drove the Lakoff +50-pair-flip lift). Weight=0 falls
back to 1.0 so DefaultCascadeConfig is backward-compatible."
```

---

### Task 4: Add `OrtonyScoring` enum (jaccard_salience only)

**Files:**
- Modify: `api/internal/forge/cascade.go`
- Test: `api/internal/forge/cascade_test.go`

- [ ] **Step 1: Write failing tests**

```go
func TestOrtonyScoring_DefaultIsJaccardSalience(t *testing.T) {
	cfg := DefaultCascadeConfig()
	if cfg.OrtonyScoring != OrtonyScoringJaccardSalience {
		t.Errorf("expected jaccard_salience, got %q", cfg.OrtonyScoring)
	}
}

func TestOrtonyScoring_ValidateRejectsUnknown(t *testing.T) {
	cfg := DefaultCascadeConfig()
	cfg.OrtonyScoring = OrtonyScoring("not_a_real_scoring")
	if err := cfg.Validate(); err == nil {
		t.Fatal("Validate should reject unknown scoring")
	} else if !strings.Contains(err.Error(), "OrtonyScoring") {
		t.Errorf("error should name field: %v", err)
	}
}

func TestOrtonyScoring_EmptyValidatesAsDefault(t *testing.T) {
	// Empty value (zero value of OrtonyScoring) must be accepted and
	// behave identically to jaccard_salience. This keeps callers that
	// don't set the field working.
	cfg := DefaultCascadeConfig()
	cfg.OrtonyScoring = ""
	if err := cfg.Validate(); err != nil {
		t.Errorf("empty value should validate, got %v", err)
	}
}
```

- [ ] **Step 2: Run, verify FAIL**

```
cd api && go test ./internal/forge/ -run "TestOrtonyScoring_" -v
```

- [ ] **Step 3: Add enum + field**

In `cascade.go`:

```go
// OrtonyScoring picks the pointwise scoring function. Only
// jaccard_salience is implemented in Go — other Python sweep-side
// scoring fns (jaccard_raw, cosine_salience, ortony_vehicle_salience,
// ortony_imbalance, ortony_log_ratio, random_uniform) live in
// evaluate_aptness.SCORING_FNS and stay Python-only. Adding more Go
// scoring fns is out of scope until production needs them.
type OrtonyScoring string

const (
	OrtonyScoringJaccardSalience OrtonyScoring = "jaccard_salience"
)

func (s OrtonyScoring) Valid() bool {
	switch s {
	case "", OrtonyScoringJaccardSalience:
		return true
	}
	return false
}
```

Add to `CascadeConfig`:

```go
OrtonyScoring OrtonyScoring // production fixed to jaccard_salience; "" treated as default.
```

Add to `Validate()` (early in the function, before any numeric checks):

```go
if !c.OrtonyScoring.Valid() {
	return fmt.Errorf("OrtonyScoring %q is not a known scoring function", c.OrtonyScoring)
}
```

- [ ] **Step 4: Run tests**

```
cd api && go test ./internal/forge/ -v
```

Expected: 2/3 pass, `TestOrtonyScoring_DefaultIsJaccardSalience` still fails (default is "" until task 6).

That's expected. Note that this test is locking in the post-task-6 behaviour. Mark with `t.Skip` until task 6, or leave failing as a planned-failing-until-task-6 — preferred: just write the test once, accept that this *one* test stays red until task 6 fixes the default. Document the dependency clearly in the test's docstring.

Alternative cleaner sequencing: defer `TestOrtonyScoring_DefaultIsJaccardSalience` to task 6 and add it there. **Do that** — it keeps every task green when committed.

So for this task: drop `TestOrtonyScoring_DefaultIsJaccardSalience`. Keep the other two.

- [ ] **Step 5: Commit**

```bash
git add api/internal/forge/cascade.go api/internal/forge/cascade_test.go
git commit -m "feat(cascade): OrtonyScoring enum — jaccard_salience only

Production scoring is fixed to jaccard_salience. Adds the enum + Validate
hook. Default value flip lands in task 6 along with the other defaults."
```

---

### Task 5: Add `GateMode` + `GateAlpha` + sigmoid helper + branch in scorer

**Files:**
- Modify: `api/internal/forge/cascade.go`
- Test: `api/internal/forge/cascade_test.go`

- [ ] **Step 1: Write failing tests** (the 7-test soft-gate suite)

```go
func TestSigmoid_AtZeroReturnsHalf(t *testing.T) {
	if got := sigmoid(0); math.Abs(got-0.5) > 1e-12 {
		t.Errorf("sigmoid(0) = %v, want 0.5", got)
	}
}

func TestSigmoid_StableAtLargePositive(t *testing.T) {
	// math.Exp(1000) overflows; the stable form must return ~1.0.
	if got := sigmoid(1000); got <= 0.99 || got > 1.0 {
		t.Errorf("sigmoid(1000) = %v, want ~1.0", got)
	}
}

func TestSigmoid_StableAtLargeNegative(t *testing.T) {
	if got := sigmoid(-1000); got < 0.0 || got >= 0.01 {
		t.Errorf("sigmoid(-1000) = %v, want ~0.0", got)
	}
}

func TestSoftGateRescuesPreviouslyDroppedPair(t *testing.T) {
	cfg := CascadeConfig{
		ConcretenessThreshold: 1.0,
		Composition: CompositionAdditive,
		GateMode: GateModeSoft,
		GateAlpha: 3.0,
	}
	tc, vc := 4.0, 3.5 // signed=-0.5; sub-threshold but soft should still score
	in := CascadeInputs{
		TopicConcreteness:   &tc,
		VehicleConcreteness: &vc,
		TopicProperties:     map[int64]float64{1: 1.0},
		VehicleProperties:   map[int64]float64{1: 1.0},
	}
	r := EvaluateCascadePair(in, cfg)
	if r.Status != CascadeStatusScored {
		t.Fatalf("soft mode must keep status=scored even sub-threshold, got %v", r.Status)
	}
	if r.FinalScore == nil || *r.FinalScore <= 0 {
		t.Fatalf("expected positive final, got %v", r.FinalScore)
	}
	// gate_score = sigmoid(3.0 * (-0.5 - 1.0)) = sigmoid(-4.5) ≈ 0.011.
	// ortony = 1.0, final = 1.0 * 0.011 ≈ 0.011.
	want := sigmoid(3.0 * (-1.5))
	if math.Abs(*r.FinalScore-want) > 1e-6 {
		t.Errorf("final %v != want %v", *r.FinalScore, want)
	}
}

func TestSoftGatePreservesClearPassScore(t *testing.T) {
	cfgHard := CascadeConfig{
		ConcretenessThreshold: 1.0,
		Composition: CompositionAdditive,
		GateMode: GateModeHard,
	}
	cfgSoft := cfgHard
	cfgSoft.GateMode = GateModeSoft
	cfgSoft.GateAlpha = 3.0
	tc, vc := 1.0, 4.0 // signed=3.0; well above threshold
	in := CascadeInputs{
		TopicConcreteness:   &tc,
		VehicleConcreteness: &vc,
		TopicProperties:     map[int64]float64{1: 1.0},
		VehicleProperties:   map[int64]float64{1: 1.0},
	}
	rh := EvaluateCascadePair(in, cfgHard)
	rs := EvaluateCascadePair(in, cfgSoft)
	if rh.FinalScore == nil || rs.FinalScore == nil {
		t.Fatal("both modes must score this pair")
	}
	ratio := *rs.FinalScore / *rh.FinalScore
	if ratio < 0.85 {
		t.Errorf("soft mode lost too much score at clear pass: ratio=%v", ratio)
	}
}

func TestSoftGateMissingConcretenessStillFailsClosed(t *testing.T) {
	cfg := CascadeConfig{
		ConcretenessThreshold: 1.0,
		Composition: CompositionAdditive,
		GateMode: GateModeSoft,
		GateAlpha: 3.0,
	}
	in := CascadeInputs{
		TopicConcreteness:   nil,
		VehicleConcreteness: nil,
		TopicProperties:     map[int64]float64{1: 1.0},
		VehicleProperties:   map[int64]float64{1: 1.0},
	}
	r := EvaluateCascadePair(in, cfg)
	if r.Status != CascadeStatusMissingConcreteness {
		t.Errorf("soft mode must NOT rescue missing-concreteness: got %v", r.Status)
	}
}

func TestSoftGateGatePassedDiagnostic(t *testing.T) {
	cfg := CascadeConfig{
		ConcretenessThreshold: 1.0,
		Composition: CompositionAdditive,
		GateMode: GateModeSoft,
		GateAlpha: 3.0,
	}
	// gate_score = sigmoid(3*(-0.5-1)) ≈ 0.011 → GatePassed=false
	tc1, vc1 := 4.0, 3.5
	in1 := CascadeInputs{TopicConcreteness: &tc1, VehicleConcreteness: &vc1,
		TopicProperties: map[int64]float64{1: 1.0}, VehicleProperties: map[int64]float64{1: 1.0}}
	r1 := EvaluateCascadePair(in1, cfg)
	if r1.GatePassed {
		t.Errorf("expected GatePassed=false at gate_score < 0.5, got true")
	}
	// gate_score = sigmoid(3*(3-1)) = sigmoid(6) ≈ 0.998 → GatePassed=true
	tc2, vc2 := 1.0, 4.0
	in2 := CascadeInputs{TopicConcreteness: &tc2, VehicleConcreteness: &vc2,
		TopicProperties: map[int64]float64{1: 1.0}, VehicleProperties: map[int64]float64{1: 1.0}}
	r2 := EvaluateCascadePair(in2, cfg)
	if !r2.GatePassed {
		t.Errorf("expected GatePassed=true at gate_score > 0.5, got false")
	}
}

func TestSoftGateMonotonicInGateAlpha(t *testing.T) {
	// Fixed sub-threshold pair. Higher alpha → stricter penalty → lower final.
	tc, vc := 4.0, 3.5
	in := CascadeInputs{
		TopicConcreteness:   &tc,
		VehicleConcreteness: &vc,
		TopicProperties:     map[int64]float64{1: 1.0},
		VehicleProperties:   map[int64]float64{1: 1.0},
	}
	mk := func(a float64) float64 {
		cfg := CascadeConfig{
			ConcretenessThreshold: 1.0,
			Composition: CompositionAdditive,
			GateMode: GateModeSoft,
			GateAlpha: a,
		}
		return *EvaluateCascadePair(in, cfg).FinalScore
	}
	if !(mk(5.0) < mk(3.0) && mk(3.0) < mk(1.0)) {
		t.Errorf("not monotonic: alpha 5=%v 3=%v 1=%v", mk(5.0), mk(3.0), mk(1.0))
	}
}
```

- [ ] **Step 2: Run, verify FAIL**

```
cd api && go test ./internal/forge/ -run "TestSoftGate|TestSigmoid_" -v
```

- [ ] **Step 3: Add enum, field, sigmoid, and scorer branch**

```go
// GateMode picks the concreteness-gate behaviour.
type GateMode int

const (
	GateModeHard GateMode = iota // existing cliff: sub-threshold pairs return gate_dropped
	GateModeSoft                 // sigmoid penalty: sub-threshold pairs score with attenuation
)

func (m GateMode) Valid() bool {
	return m == GateModeHard || m == GateModeSoft
}
```

Add to `CascadeConfig`:

```go
GateMode  GateMode
GateAlpha float64 // sigmoid steepness for soft mode. Must be > 0 in soft mode.
```

Stable-form sigmoid (next to other math helpers in `cascade.go`):

```go
// sigmoid is the numerically-stable logistic σ(x) = 1/(1+e^-x). Mirrors
// data-pipeline/scripts/evaluate_cascade.py:_sigmoid. Splits on sign of x
// to avoid math.Exp overflow at large |x| (the cascade can produce
// alpha*delta on the order of ±tens).
func sigmoid(x float64) float64 {
	if x >= 0 {
		z := math.Exp(-x)
		return 1.0 / (1.0 + z)
	}
	z := math.Exp(x)
	return z / (1.0 + z)
}
```

In `EvaluateCascadePair`, change the hard-gate check from:

```go
if signed < cfg.ConcretenessThreshold {
	zero := 0.0
	return CascadeResult{FinalScore: &zero, Status: CascadeStatusGateDropped}
}
```

to:

```go
if cfg.GateMode == GateModeHard && signed < cfg.ConcretenessThreshold {
	zero := 0.0
	return CascadeResult{FinalScore: &zero, Status: CascadeStatusGateDropped}
}
```

(In soft mode, fall through to the scoring stages.)

Then at the end of the scoring path, just before the `return CascadeResult{...}`:

```go
gatePassed := true
if cfg.GateMode == GateModeSoft {
	gateScore := sigmoid(cfg.GateAlpha * (signed - cfg.ConcretenessThreshold))
	final = final * gateScore
	gatePassed = gateScore >= 0.5
}
```

Update the return to set `GatePassed: gatePassed` (replacing the static `GatePassed: true`).

- [ ] **Step 4: Run tests**

```
cd api && go test ./internal/forge/ -v
```

Expected: green.

- [ ] **Step 5: Commit**

```bash
git add api/internal/forge/cascade.go api/internal/forge/cascade_test.go
git commit -m "feat(cascade): soft-gate sigmoid penalty mode

Adds GateMode (Hard|Soft) + GateAlpha + stable-form sigmoid helper.
Mirrors data-pipeline/scripts/evaluate_cascade.py gate_mode='soft'.
Hard mode is the default until task 6 flips to soft."
```

---

### Task 6: Update `DefaultCascadeConfig` to loop-tuned production values

**Files:**
- Modify: `api/internal/forge/cascade.go`
- Test: `api/internal/forge/cascade_test.go`

- [ ] **Step 1: Write failing tests**

```go
func TestDefaultCascadeConfig_LoopTunedValues(t *testing.T) {
	c := DefaultCascadeConfig()
	cases := []struct {
		name string
		got  float64
		want float64
	}{
		{"ConcretenessThreshold", c.ConcretenessThreshold, 1.0},
		{"Alpha", c.Alpha, 0.75},
		{"DCap", c.DCap, 0.68},
		{"RerankExponent", c.RerankExponent, 0.12},
		{"ConcretenessBonusCoef", c.ConcretenessBonusCoef, 0.002},
		{"OrtonyWeight", c.OrtonyWeight, 1.75},
		{"GateAlpha", c.GateAlpha, 3.0},
	}
	for _, tc := range cases {
		if math.Abs(tc.got-tc.want) > 1e-9 {
			t.Errorf("%s: got %v, want %v", tc.name, tc.got, tc.want)
		}
	}
	if c.Composition != CompositionAdditive {
		t.Errorf("Composition: got %v, want additive", c.Composition)
	}
	if c.OrtonyScoring != OrtonyScoringJaccardSalience {
		t.Errorf("OrtonyScoring: got %q, want jaccard_salience", c.OrtonyScoring)
	}
	if c.GateMode != GateModeSoft {
		t.Errorf("GateMode: got %v, want GateModeSoft", c.GateMode)
	}
}
```

- [ ] **Step 2: Run, verify FAIL**

```
cd api && go test ./internal/forge/ -run TestDefaultCascadeConfig_LoopTunedValues -v
```

- [ ] **Step 3: Update `DefaultCascadeConfig()`**

```go
func DefaultCascadeConfig() CascadeConfig {
	return CascadeConfig{
		ConcretenessThreshold: 1.0,
		Alpha:                 0.75,
		DCap:                  0.68,
		Composition:           CompositionAdditive,
		RerankExponent:        0.12,
		ConcretenessBonusCoef: 0.002,
		OrtonyWeight:          1.75,
		OrtonyScoring:         OrtonyScoringJaccardSalience,
		GateMode:              GateModeSoft,
		GateAlpha:             3.0,

		// M04 / M05 fields unchanged.
		Mode:          ModeCluster,
		EmbeddingDMin: 0.4,
		EmbeddingDMax: 0.85,
		EmbeddingTopK: 100,
		Gamma:         GammaWeight{v: 1.0},
	}
}
```

Update the docstring above `DefaultCascadeConfig` to reference the loop ratification source (loop-3 iter 19 end / L2-17 Pareto) rather than the older M03 sweep narrative. Briefly: the older Sweep-2 numbers stay in the design log but the production defaults now reflect the Karpathy loops.

- [ ] **Step 4: Run all forge tests**

```
cd api && go test ./internal/forge/ -v
```

Expected: green. Other tests that constructed `DefaultCascadeConfig()` will now get loop-tuned values — verify none of them assert on the old defaults. If any do, those assertions need to be updated to the new defaults (this is a deliberate breaking change for the defaults; assertion drift is expected and tracked).

If any test breaks because it relied on `DefaultCascadeConfig().GateMode == GateModeHard` semantics, set GateMode explicitly in that test rather than reverting the default.

- [ ] **Step 5: Commit**

```bash
git add api/internal/forge/cascade.go api/internal/forge/cascade_test.go
git commit -m "feat(cascade): DefaultCascadeConfig adopts loop-tuned production values

Mirrors PRODUCTION_CASCADE_CONFIG in data-pipeline/scripts/evaluate_loop_harness.py.
GateMode=Soft makes soft-rescue the production default; operator can flip
back via METAFORGE_FORGE_GATE_MODE=hard (wired in task 11)."
```

---

### Task 7: Extend `Validate()` for all new fields

**Files:**
- Modify: `api/internal/forge/cascade.go`
- Test: `api/internal/forge/cascade_test.go`

- [ ] **Step 1: Write failing tests**

```go
func TestValidate_RerankExponentMustBePositiveOrZero(t *testing.T) {
	cfg := DefaultCascadeConfig()
	cfg.RerankExponent = -0.1
	if err := cfg.Validate(); err == nil {
		t.Error("expected error for negative RerankExponent")
	}
	cfg.RerankExponent = math.NaN()
	if err := cfg.Validate(); err == nil {
		t.Error("expected error for NaN RerankExponent")
	}
}

func TestValidate_ConcretenessBonusCoefMustBeNonNegFinite(t *testing.T) {
	cfg := DefaultCascadeConfig()
	cfg.ConcretenessBonusCoef = -0.001
	if err := cfg.Validate(); err == nil {
		t.Error("expected error for negative ConcretenessBonusCoef")
	}
	cfg.ConcretenessBonusCoef = math.Inf(1)
	if err := cfg.Validate(); err == nil {
		t.Error("expected error for Inf ConcretenessBonusCoef")
	}
}

func TestValidate_OrtonyWeightMustBeNonNegFinite(t *testing.T) {
	cfg := DefaultCascadeConfig()
	cfg.OrtonyWeight = -1.0
	if err := cfg.Validate(); err == nil {
		t.Error("expected error for negative OrtonyWeight")
	}
}

func TestValidate_GateModeMustBeValid(t *testing.T) {
	cfg := DefaultCascadeConfig()
	cfg.GateMode = GateMode(42)
	if err := cfg.Validate(); err == nil {
		t.Error("expected error for invalid GateMode")
	}
}

func TestValidate_GateAlphaMustBePositiveInSoftMode(t *testing.T) {
	cfg := DefaultCascadeConfig()
	cfg.GateMode = GateModeSoft
	cfg.GateAlpha = 0.0
	if err := cfg.Validate(); err == nil {
		t.Error("expected error for GateAlpha=0 in soft mode")
	}
	cfg.GateAlpha = -1.0
	if err := cfg.Validate(); err == nil {
		t.Error("expected error for negative GateAlpha in soft mode")
	}
}

func TestValidate_GateAlphaIgnoredInHardMode(t *testing.T) {
	cfg := DefaultCascadeConfig()
	cfg.GateMode = GateModeHard
	cfg.GateAlpha = 0.0
	if err := cfg.Validate(); err != nil {
		t.Errorf("hard mode should accept GateAlpha=0: %v", err)
	}
}
```

- [ ] **Step 2: Run, verify FAIL**

```
cd api && go test ./internal/forge/ -run TestValidate_ -v
```

- [ ] **Step 3: Extend `Validate()`**

Append to the existing checks in `Validate()`:

```go
if !c.GateMode.Valid() {
	return fmt.Errorf("GateMode %v is not one of GateModeHard|GateModeSoft", c.GateMode)
}
if c.GateMode == GateModeSoft {
	if c.GateAlpha <= 0 || math.IsNaN(c.GateAlpha) || math.IsInf(c.GateAlpha, 0) {
		return fmt.Errorf("GateAlpha %v must be > 0 and finite in soft mode", c.GateAlpha)
	}
}
if c.RerankExponent < 0 || math.IsNaN(c.RerankExponent) || math.IsInf(c.RerankExponent, 0) {
	return fmt.Errorf("RerankExponent %v must be >= 0 and finite", c.RerankExponent)
}
if c.ConcretenessBonusCoef < 0 || math.IsNaN(c.ConcretenessBonusCoef) || math.IsInf(c.ConcretenessBonusCoef, 0) {
	return fmt.Errorf("ConcretenessBonusCoef %v must be >= 0 and finite", c.ConcretenessBonusCoef)
}
if c.OrtonyWeight < 0 || math.IsNaN(c.OrtonyWeight) || math.IsInf(c.OrtonyWeight, 0) {
	return fmt.Errorf("OrtonyWeight %v must be >= 0 and finite", c.OrtonyWeight)
}
```

- [ ] **Step 4: Run all tests**

```
cd api && go test ./internal/forge/ -v
```

Expected: green.

- [ ] **Step 5: Commit**

```bash
git add api/internal/forge/cascade.go api/internal/forge/cascade_test.go
git commit -m "feat(cascade): Validate() covers all loop-tuned config fields"
```

---

### Task 8: Drop SQL CTE concreteness filter

**Files:**
- Modify: `api/internal/db/cascade.go`
- Test: `api/internal/db/cascade_test.go`

- [ ] **Step 1: Inspect the SQL**

Read `api/internal/db/cascade.go` lines 130-220 (`shared_gated` CTE). The line to remove is:

```sql
WHERE (scv.score - sct.score) >= ?
```

and the corresponding parameter binding (one `float64` argument that maps to `ConcretenessThreshold`). The two INNER JOINs against `synset_concreteness` STAY — they enforce the missing-concreteness contract at the DB layer.

- [ ] **Step 2: Write a failing DB-layer test**

Add to `api/internal/db/cascade_test.go`:

```go
func TestCandidateFetch_SurfacesSubThresholdRows(t *testing.T) {
	// Fixture: insert two candidates for a topic — one above threshold,
	// one sub-threshold. Pre-fix, only one row returns. Post-fix, both
	// return (the scorer will gate-drop or soft-score depending on mode,
	// but the DB layer must surface both).

	// ... (set up fixture: minimal DB with source_synsets, per_sense_*
	// tables, synset_concreteness rows for a topic + 2 vehicle candidates)

	// Topic concreteness: 4.0. Vehicle A: 5.0 (above-threshold). Vehicle B: 3.5 (sub-threshold).
	// Call the candidate-fetch path with ConcretenessThreshold=1.0.
	// Assert both vehicles appear in the result set.

	// (See existing fixture builders in cascade_test.go — reuse them.)
}
```

This test will require new fixture rows. Mirror the existing `*Fixture` helper pattern.

- [ ] **Step 3: Run, verify FAIL**

```
cd api && go test ./internal/db/ -run TestCandidateFetch_SurfacesSubThresholdRows -v
```

- [ ] **Step 4: Drop the WHERE clause + parameter**

In `api/internal/db/cascade.go`:

1. Delete the line `WHERE (scv.score - sct.score) >= ?`.
2. Remove the corresponding `args = append(args, threshold)` (or equivalent argument-binding) call.
3. Rename the `shared_gated` CTE if appropriate (e.g. to `shared_with_concreteness`) and update the comment block above the SQL: "INNER JOIN on synset_concreteness still enforces missing-concreteness; the gate threshold is enforced *only* in Go now."

Look for the call-site that passes `cfg.ConcretenessThreshold` into the query — drop the arg from the call too.

- [ ] **Step 5: Run all DB tests**

```
cd api && go test ./internal/db/ -v
```

Expected: green. Existing tests that relied on SQL pre-filtering may need their fixtures updated (some rows that previously didn't surface will now surface; the scorer downstream handles them correctly per tasks 1-7).

- [ ] **Step 6: Commit**

```bash
git add api/internal/db/cascade.go api/internal/db/cascade_test.go
git commit -m "fix(db): SQL CTE surfaces all candidates with concreteness, gate moves to Go

Drops 'WHERE (scv.score - sct.score) >= ?' from shared_gated CTE so soft
mode can rescue sub-threshold candidates. Missing-concreteness still
filtered SQL-side via INNER JOIN. New invariant: 'SQL surfaces all
candidates with concreteness; Go decides what to do with them.'"
```

---

### Task 9: Update handler comment + verify downstream

**Files:**
- Modify: `api/internal/handler/cascade_pipeline.go`
- Test: existing handler tests run

- [ ] **Step 1: Update the line-301 comment**

Find:

```go
// SQL CTE already filtered gate_dropped + missing_concreteness,
// so the only attrition we can see here is no_properties.
```

Replace with:

```go
// SQL CTE only filters missing_concreteness (INNER JOIN on
// synset_concreteness). Gate decisions are made by EvaluateCascadePair
// — in hard mode we may see gate_dropped here; in soft mode every pair
// with concreteness returns scored (possibly with a sigmoid penalty).
```

Check the surrounding `if res.Status != forge.CascadeStatusScored` block — under hard mode, gate_dropped rows now flow through this branch. Whatever the branch does (increment `droppedNonScored`, continue) is correct behaviour. Verify by reading.

- [ ] **Step 2: Run all handler tests**

```
cd api && go test ./internal/handler/ -v
```

Expected: green. If any test relied on "no gate_dropped rows surface from SQL," update its expectations.

- [ ] **Step 3: Commit**

```bash
git add api/internal/handler/cascade_pipeline.go
git commit -m "docs(handler): update comment — SQL CTE no longer pre-filters gate_dropped"
```

---

### Task 10: Integration test — soft-gate rescues high-concreteness topic at handler level

**Files:**
- Test: `api/internal/handler/handler_cascade_test.go` (or wherever cascade integration lives)

- [ ] **Step 1: Find the existing handler integration test**

```
cd api && grep -rn "func Test.*Cascade.*Handler\|func TestHandler.*Cascade" internal/handler/
```

Read the existing pattern. Mirror it.

- [ ] **Step 2: Write the failing test**

```go
func TestHandlerSoftGateRescuesHighConcretenessTopic(t *testing.T) {
	// "boulder" has concreteness ~4.8 — hard gate kills every cluster-mate
	// because vehicle_c - 4.8 >= 1.0 is unreachable for almost any
	// vehicle in the vocab. Soft gate should surface a nonzero scored
	// top-K.

	// Set up handler with DefaultCascadeConfig (GateMode=Soft).
	// Query /forge/suggest?word=boulder&limit=20.
	// Expect at least 5 candidates with status=scored, final_score > 0.

	// (Use the existing test-DB fixture pattern.)
}
```

- [ ] **Step 3: Run, verify FAIL** (until the prior tasks are merged, the soft-gate path doesn't exist)

This test depends on tasks 1-9 being landed. If running this task in isolation, expect FAIL until prior tasks merge.

- [ ] **Step 4: After running all prior task changes, verify pass**

```
cd api && go test ./internal/handler/ -run TestHandlerSoftGateRescuesHighConcretenessTopic -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add api/internal/handler/handler_cascade_test.go
git commit -m "test(handler): soft gate rescues high-concreteness topic (boulder)

Validates the end-to-end flow: SQL surfaces all candidates → soft-gate
sigmoid penalty → nonzero scored top-K for a topic that hard mode kills."
```

---

### Task 11: Wire env vars in `cmd/metaforge/main.go`

**Files:**
- Modify: `api/cmd/metaforge/main.go`

- [ ] **Step 1: Read the existing pattern**

Look at the existing `METAFORGE_FORGE_CANDIDATES`, `METAFORGE_FORGE_EMB_DMIN`, etc. flags. The pattern uses helpers `envOrDefault`, `envFloat`, `envInt`.

- [ ] **Step 2: Add the new flags before the `cascadeCfg := forge.DefaultCascadeConfig()` block**

```go
gateMode := flag.String("gate-mode",
	envOrDefault("METAFORGE_FORGE_GATE_MODE", "soft"),
	"concreteness gate mode: hard | soft")
gateAlpha := flag.Float64("gate-alpha",
	envFloat("METAFORGE_FORGE_GATE_ALPHA", 3.0),
	"soft-gate sigmoid steepness; ignored in hard mode")
alpha := flag.Float64("forge-alpha",
	envFloat("METAFORGE_FORGE_ALPHA", 0.75),
	"rerank composition weight (alpha in `ortony + alpha*bonus`)")
dCap := flag.Float64("forge-dcap",
	envFloat("METAFORGE_FORGE_DCAP", 0.68),
	"distance cap for rerank bonus saturation")
rerankExp := flag.Float64("forge-rerank-exp",
	envFloat("METAFORGE_FORGE_RERANK_EXPONENT", 0.12),
	"power transform on rerank ratio (d/DCap)^exp")
concBonus := flag.Float64("forge-concreteness-bonus-coef",
	envFloat("METAFORGE_FORGE_CONCRETENESS_BONUS_COEF", 0.002),
	"additive bonus coef on concreteness residual above threshold")
ortonyWeight := flag.Float64("forge-ortony-weight",
	envFloat("METAFORGE_FORGE_ORTONY_WEIGHT", 1.75),
	"multiplicative weight on the ortony term")
ortonyScoring := flag.String("forge-ortony-scoring",
	envOrDefault("METAFORGE_FORGE_ORTONY_SCORING", "jaccard_salience"),
	"ortony scoring function (only jaccard_salience implemented)")
```

After `flag.Parse()` (or the equivalent point) and the existing `cascadeCfg := forge.DefaultCascadeConfig()`, before `Validate`:

```go
switch *gateMode {
case "hard":
	cascadeCfg.GateMode = forge.GateModeHard
case "soft":
	cascadeCfg.GateMode = forge.GateModeSoft
default:
	log.Fatalf("METAFORGE_FORGE_GATE_MODE/-gate-mode %q is not 'hard' or 'soft'", *gateMode)
}
cascadeCfg.GateAlpha = *gateAlpha
cascadeCfg.Alpha = *alpha
cascadeCfg.DCap = *dCap
cascadeCfg.RerankExponent = *rerankExp
cascadeCfg.ConcretenessBonusCoef = *concBonus
cascadeCfg.OrtonyWeight = *ortonyWeight
cascadeCfg.OrtonyScoring = forge.OrtonyScoring(*ortonyScoring)
```

The `Validate()` call later will catch invalid values.

- [ ] **Step 3: Build**

```
cd api && go build ./...
```

Expected: clean.

- [ ] **Step 4: Smoke test**

```
cd api && go build -o metaforge ./cmd/metaforge
METAFORGE_FORGE_GATE_MODE=hard ./metaforge --db ../data-pipeline/output/lexicon_v2.db --port 9192 &
PID=$!
sleep 2
curl -s 'http://127.0.0.1:9192/health' | head -1
kill $PID
```

Expected: API starts cleanly, `/health` returns 200.

- [ ] **Step 5: Commit**

```bash
git add api/cmd/metaforge/main.go
git commit -m "feat(forge): env vars for all loop-tuned cascade knobs

Adds METAFORGE_FORGE_GATE_MODE, _GATE_ALPHA, _ALPHA, _DCAP,
_RERANK_EXPONENT, _CONCRETENESS_BONUS_COEF, _ORTONY_WEIGHT,
_ORTONY_SCORING. All default to the loop-tuned production values.
Invalid values fail loud at startup."
```

---

### Task 12: Python↔Go parity test

**Files:**
- Create: `data-pipeline/scripts/parity_test_go_vs_python.py`
- Test: smoke-test from CLI

- [ ] **Step 1: Write the parity test**

```python
"""Python↔Go cascade-scorer parity check.

Picks 50 (topic_synset_id, vehicle_synset_id) pairs from the Phase 2 + Lakoff
cohorts, scores each side-by-side, asserts |python_final - go_final| < 1e-6.

Requires the Go binary built and the same lexicon_v2.db both sides.
"""
from __future__ import annotations

import json
import os
import signal
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

import requests

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "data-pipeline" / "scripts"))

from evaluate_cascade import CascadeConfig, evaluate_cascade_pair  # noqa: E402
from evaluate_loop_harness import PRODUCTION_CASCADE_CONFIG  # noqa: E402

DB_PATH = REPO_ROOT / "data-pipeline" / "output" / "lexicon_v2.db"
BINARY = REPO_ROOT / "api" / "metaforge"
PORT = 9193
SAMPLE_SIZE = 50
TOLERANCE = 1e-6


def start_api():
    env = os.environ.copy()
    env.update({
        "METAFORGE_FORGE_CASCADE": "1",
        "METAFORGE_FORGE_GATE_MODE": PRODUCTION_CASCADE_CONFIG.gate_mode,
        "METAFORGE_FORGE_GATE_ALPHA": str(PRODUCTION_CASCADE_CONFIG.gate_alpha),
        "METAFORGE_FORGE_ALPHA": str(PRODUCTION_CASCADE_CONFIG.alpha),
        "METAFORGE_FORGE_DCAP": str(PRODUCTION_CASCADE_CONFIG.d_cap),
        "METAFORGE_FORGE_RERANK_EXPONENT": str(PRODUCTION_CASCADE_CONFIG.rerank_exponent),
        "METAFORGE_FORGE_CONCRETENESS_BONUS_COEF": str(PRODUCTION_CASCADE_CONFIG.concreteness_bonus_coef),
        "METAFORGE_FORGE_ORTONY_WEIGHT": str(PRODUCTION_CASCADE_CONFIG.ortony_weight),
        "METAFORGE_FORGE_ORTONY_SCORING": PRODUCTION_CASCADE_CONFIG.ortony_scoring,
    })
    proc = subprocess.Popen(
        [str(BINARY), "--db", str(DB_PATH), "--port", str(PORT), "--cascade"],
        env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    base = f"http://127.0.0.1:{PORT}"
    for _ in range(20):
        try:
            r = requests.get(f"{base}/health", timeout=0.5)
            if r.ok:
                return proc, base
        except Exception:
            pass
        time.sleep(0.5)
    proc.send_signal(signal.SIGTERM)
    raise RuntimeError("Go API didn't come up")


def pick_pairs(conn, n):
    """Picks n diverse pairs from Phase 2 + Lakoff cohorts."""
    # Read from spike_2_topics.json + lakoff_topics.json; pick `n` total.
    # Returns list of (topic_id, vehicle_id, cohort) tuples.
    # ... (implementation detail — mirror loop1_eyeball_pick_topics.py shape)
    raise NotImplementedError("fill in based on cohort fixture layout")


def score_python(conn, topic_id, vehicle_id, cfg):
    r = evaluate_cascade_pair(conn, topic_id, vehicle_id, cfg)
    if r.status == "scored":
        return r.final_score
    return None


def score_go_via_suggest(base, topic_word, expected_vehicle_lemma):
    """Calls /forge/suggest and finds the candidate matching the vehicle lemma."""
    r = requests.get(f"{base}/forge/suggest",
                     params={"word": topic_word, "limit": 200},
                     timeout=5)
    r.raise_for_status()
    for cand in r.json().get("candidates", []):
        if cand["lemma"] == expected_vehicle_lemma:
            return cand["final_score"]
    return None


def main():
    proc, base = start_api()
    try:
        conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
        try:
            pairs = pick_pairs(conn, SAMPLE_SIZE)
            mismatches = []
            for (tid, vid, cohort, topic_word, veh_lemma) in pairs:
                p = score_python(conn, tid, vid, PRODUCTION_CASCADE_CONFIG)
                g = score_go_via_suggest(base, topic_word, veh_lemma)
                if p is None or g is None:
                    print(f"SKIP {tid}->{vid} ({cohort}): python={p} go={g}")
                    continue
                if abs(p - g) > TOLERANCE:
                    mismatches.append((tid, vid, cohort, p, g, abs(p - g)))
            if mismatches:
                print(f"PARITY FAIL: {len(mismatches)} pairs over tolerance:")
                for m in mismatches[:10]:
                    print(f"  {m}")
                sys.exit(1)
            print(f"PARITY OK: {SAMPLE_SIZE} pairs within {TOLERANCE}")
        finally:
            conn.close()
    finally:
        proc.send_signal(signal.SIGTERM)
        proc.wait(timeout=5)


if __name__ == "__main__":
    main()
```

The `pick_pairs` function needs concrete implementation against the cohort fixture files. Use `loop1_eyeball_pick_topics.py` as the structural reference.

- [ ] **Step 2: Implement `pick_pairs`**

Read `data-pipeline/scripts/spike_2_topics.json` and `data-pipeline/scripts/lakoff_topics.json` (or the canonical fixture paths). For each cohort, pick (n/2) random apt pairs + (n/2) random inapt pairs. Need to resolve topic_word → synset_id and vehicle_lemma → synset_id through the same `lookup_primary_synset` path Go uses (or capture these from the harness's existing scoring).

- [ ] **Step 3: Run the parity test**

```bash
source .venv/bin/activate
cd api && go build -o metaforge ./cmd/metaforge && cd ..
python data-pipeline/scripts/parity_test_go_vs_python.py
```

Expected: `PARITY OK: 50 pairs within 1e-06`.

- [ ] **Step 4: If parity fails**

Diff the cascade math step-by-step. The most likely divergence sources:
- Float-precision in JaccardSalience (Python uses dict iteration order, Go uses map iteration order — but the math is commutative; should not affect result).
- Different cosine-distance clamping behaviour.
- ortony_weight applied at wrong stage.
- concreteness_bonus_coef applied in wrong order (must be POST-composition, PRE soft-gate).

Add a diagnostic logging mode to `evaluate_cascade_pair` and `EvaluateCascadePair` that dumps per-stage intermediates if `METAFORGE_CASCADE_DEBUG=1`, run both sides, diff.

- [ ] **Step 5: Commit**

```bash
git add data-pipeline/scripts/parity_test_go_vs_python.py
git commit -m "test(parity): Python↔Go cascade-scorer parity harness (50 pairs)

Picks 50 pairs from Phase 2 + Lakoff cohorts, scores both sides under
PRODUCTION_CASCADE_CONFIG, asserts |delta| < 1e-6 on all. Used as the
acceptance criterion 3 gate for the soft-gate Go port."
```

---

### Task 13: Re-run `loop1_eyeball_harness.py` for OOD verification

**Files:**
- No code change; produces `data-pipeline/output/loop1_eyeball_report.md`.

- [ ] **Step 1: Run the OOD harness**

```bash
source .venv/bin/activate
cd api && go build -o metaforge ./cmd/metaforge && cd ..
python data-pipeline/scripts/loop1_eyeball_pick_topics.py
python data-pipeline/scripts/loop1_eyeball_harness.py
```

- [ ] **Step 2: Verify the previously-erroring topics now score**

The post-merge eyeball run on main showed 2/20 OOD topics erroring under hard gate: `pint` (c=4.43) and `jump v` (c=4.52). Under soft mode, both should now return scored top-K with `final_score` ∈ [0.01, 0.5].

Open `data-pipeline/output/loop1_eyeball_report.md` and verify the new sections for `pint` and `jump` no longer show `**ERROR:** no_suggestions`.

- [ ] **Step 3: Commit the report**

```bash
git add data-pipeline/output/loop1_eyeball_report.md data-pipeline/output/loop1_eyeball_results.json
git commit -m "docs(eyeball): re-run OOD harness post soft-gate Go port

pint (c=4.43) and jump v (c=4.52) now return scored top-K under soft mode."
```

---

## Verification (final pass)

After all 13 tasks land:

```bash
# Full test suite
cd api && go test ./... && cd ..
source .venv/bin/activate && python -m pytest data-pipeline/scripts/ -v

# Parity gate
python data-pipeline/scripts/parity_test_go_vs_python.py

# Baseline numeric reproduction
python data-pipeline/scripts/evaluate_loop_harness.py --mode baseline --out /tmp/post_port_baseline.json
# Expect Phase 2 median ≈ 2.0878, Lakoff ≈ 0.8856 — same as the pre-port baseline.
```

If all three pass, merge `m04/soft-gate-go-port` → `main` via PR.

---

## Self-review checklist (orchestrator)

- [ ] All 13 tasks completed in order; no task left half-done.
- [ ] Every commit has a passing test suite at HEAD.
- [ ] No placeholders in implementation steps (each code block compiles or runs as written).
- [ ] Spec acceptance criteria all green:
  1. Go + Python tests green
  2. `pint` / `jump` return scored candidates
  3. Python↔Go parity < 1e-6
  4. Baseline reproduces within bootstrap σ
  5. Staging deploy returns nonzero candidates for `boulder`
- [ ] No backwards-compatibility shims left for removed Python knobs (e.g. no orphan `Alpha=1.0` references in tests).
