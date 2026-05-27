// Cascade scorer: concreteness gate → jaccard_salience Ortony rank →
// cosine-distance re-rank. Mirrors data-pipeline/scripts/evaluate_cascade.py
// — divergences from the Python ground truth in the smoke crib are port bugs.
package forge

import (
	"fmt"
	"math"
)

// JaccardSalience returns Σ min(pa[c],pb[c]) over shared keys divided by
// Σ max(pa[c],pb[c]) over the union. Returns 0.0 for empty inputs or
// degenerate union.
func JaccardSalience(pa, pb map[int64]float64) float64 {
	if len(pa) == 0 || len(pb) == 0 {
		return 0.0
	}
	var num, den float64
	for c, va := range pa {
		if vb, shared := pb[c]; shared {
			if va < vb {
				num += va
			} else {
				num += vb
			}
			if va > vb {
				den += va
			} else {
				den += vb
			}
		} else {
			den += va
		}
	}
	for c, vb := range pb {
		if _, shared := pa[c]; !shared {
			den += vb
		}
	}
	if den == 0 {
		return 0.0
	}
	return num / den
}

// ReRankBonus is the monotonic-up-to-cap reward shape: clip(d/dCap, 0, 1).
// dCap ≤ 0 returns 0 defensively.
func ReRankBonus(d, dCap float64) float64 {
	if dCap <= 0 {
		return 0.0
	}
	r := d / dCap
	if r < 0.0 {
		return 0.0
	}
	if r > 1.0 {
		return 1.0
	}
	return r
}

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

// CascadeCosineDistance returns 1 − cosine_similarity ∈ [0, 2]. The bool
// is false on dim mismatch OR zero-norm input — both surface as
// 'missing centroid' upstream, not as a degenerate 1.0 like the legacy
// embeddings.CosineDistance helper.
func CascadeCosineDistance(a, b []float32) (float64, bool) {
	if len(a) != len(b) || len(a) == 0 {
		return 0, false
	}
	var dot, na, nb float64
	for i := range a {
		dot += float64(a[i]) * float64(b[i])
		na += float64(a[i]) * float64(a[i])
		nb += float64(b[i]) * float64(b[i])
	}
	if na == 0 || nb == 0 {
		return 0, false
	}
	sim := dot / (math.Sqrt(na) * math.Sqrt(nb))
	if sim > 1.0 {
		sim = 1.0
	} else if sim < -1.0 {
		sim = -1.0
	}
	return 1.0 - sim, true
}

// CascadeCosineDistanceWithANorm is CascadeCosineDistance with `a`'s norm
// precomputed by the caller. Used by hot-path scans (e.g. the M04
// embedding-band candidate scan) where the same `a` vector is compared
// against thousands of `b` vectors and recomputing |a| per call wastes
// ~Σ|a| × O(len(a)) ops. Pass aNorm = math.Sqrt(Σ a[i]²) once outside
// the loop. Returns (0, false) on dim mismatch or aNorm/bNorm == 0.
func CascadeCosineDistanceWithANorm(a []float32, aNorm float64, b []float32) (float64, bool) {
	if len(a) != len(b) || len(a) == 0 {
		return 0, false
	}
	if aNorm <= 0 || math.IsNaN(aNorm) || math.IsInf(aNorm, 0) {
		return 0, false
	}
	var dot, nb float64
	for i := range a {
		dot += float64(a[i]) * float64(b[i])
		nb += float64(b[i]) * float64(b[i])
	}
	if nb == 0 {
		return 0, false
	}
	sim := dot / (aNorm * math.Sqrt(nb))
	if sim > 1.0 {
		sim = 1.0
	} else if sim < -1.0 {
		sim = -1.0
	}
	return 1.0 - sim, true
}

// CascadeStatus routes a pair into one of four attrition / scored buckets,
// mirroring the Python CascadeStatus literal type.
type CascadeStatus string

const (
	CascadeStatusScored              CascadeStatus = "scored"
	CascadeStatusGateDropped         CascadeStatus = "gate_dropped"
	CascadeStatusMissingConcreteness CascadeStatus = "missing_concreteness"
	CascadeStatusNoProperties        CascadeStatus = "no_properties"
)

// Composition picks the final-score combiner. Production winner: additive.
type Composition string

const (
	CompositionAdditive       Composition = "additive"
	CompositionMultiplicative Composition = "multiplicative"
)

// Valid reports whether c is one of the two known composition modes.
// CascadeConfig.Validate() consults this so an invalid value fails loud
// at startup rather than silently dropping the re-rank bonus.
func (c Composition) Valid() bool {
	switch c {
	case CompositionAdditive, CompositionMultiplicative:
		return true
	}
	return false
}

// CandidateSource tags a single candidate row with the generation path
// that produced it. Distinct from CandidateMode (the config-side enum
// that chooses which paths to run) — a `union` request can produce rows
// tagged cluster, embedding, OR both. Purely diagnostic in M04 v1; a
// future co-generation scoring bonus may key off SourceBoth.
type CandidateSource string

const (
	SourceCluster   CandidateSource = "cluster"
	SourceEmbedding CandidateSource = "embedding"
	SourceBoth      CandidateSource = "both"
)

// Valid reports whether s is one of the three known per-row source tags.
// Unknown values indicate a structural bug (untagged candidate, manual
// JSON tampering); callers may use this on the boundary between trusted
// internal code and untrusted inputs.
func (s CandidateSource) Valid() bool {
	switch s {
	case SourceCluster, SourceEmbedding, SourceBoth:
		return true
	}
	return false
}

// CandidateMode is the config-side enum: which generation paths to
// run for each cascade request. Maps to METAFORGE_FORGE_CANDIDATES /
// --candidate-sources. Different value set from CandidateSource — see
// the per-row CandidateSource doc above.
type CandidateMode string

const (
	ModeCluster   CandidateMode = "cluster_only"
	ModeEmbedding CandidateMode = "embedding_only"
	ModeUnion     CandidateMode = "union"
)

// Valid reports whether m is one of the three known config modes.
// CascadeConfig.Validate() consults this at startup so an invalid env
// value fails loud instead of silently falling back to a default.
func (m CandidateMode) Valid() bool {
	switch m {
	case ModeCluster, ModeEmbedding, ModeUnion:
		return true
	}
	return false
}

// ParseCandidateMode is the validated constructor for CandidateMode.
// Used at the env/flag boundary in main.go so an invalid operator-supplied
// value fails loud at the cast site, not via downstream CascadeConfig.Validate().
func ParseCandidateMode(s string) (CandidateMode, error) {
	m := CandidateMode(s)
	if !m.Valid() {
		return "", fmt.Errorf("invalid candidate mode %q: must be one of cluster_only|embedding_only|union", s)
	}
	return m, nil
}

// GammaWeight is the M05 type-diversity-bonus weight on EvaluateCascadePair.
// The struct wrap with an unexported field makes operator-supplied env/flag
// values an unforgeable validation-gated boundary cast (NewGamma) — direct
// literal assignment `cfg.Gamma = 1.0` no longer compiles, so callers
// cannot bypass NewGamma's negative/NaN/±Inf check. Mirrors the
// ParseCandidateMode / Composition.Valid pattern but stronger:
// the defined-type form (`type GammaWeight float64`) was bypassable by
// untyped numeric literals. CascadeConfig.Validate() remains the second
// line of defence for any future deserialisation path that constructs a
// GammaWeight outside NewGamma.
//
// The zero value `GammaWeight{}` is valid and represents M05 dormant
// (v=0), matching the DefaultCascadeConfig's "M05 off" intent.
type GammaWeight struct{ v float64 }

// Value returns the underlying float64. Callers compare against zero
// (M05 dormant check) and multiply by the type-diversity bonus through
// this accessor — the unexported field forbids direct read.
func (g GammaWeight) Value() float64 { return g.v }

// NewGamma constructs a validated GammaWeight from a raw float64. Returns
// an error for negative, NaN, or ±Inf inputs. Use this at the operator
// entry point (env/flag boundary) so an invalid value fails loud at the
// cast site, not via downstream CascadeConfig.Validate().
func NewGamma(v float64) (GammaWeight, error) {
	if v < 0 || math.IsNaN(v) || math.IsInf(v, 0) {
		return GammaWeight{}, fmt.Errorf("Gamma %v must be ≥ 0 and finite", v)
	}
	return GammaWeight{v: v}, nil
}

// CascadeConfig pins the cascade hyperparameters. Use DefaultCascadeConfig
// for the production-blessed winner config.
type CascadeConfig struct {
	ConcretenessThreshold float64
	Alpha                 float64
	DCap                  float64
	Composition           Composition

	// RerankExponent is the power transform exponent applied to (d/DCap) in
	// the rerank stage. Zero (the zero value) falls back to linear (exponent=1)
	// so DefaultCascadeConfig stays backward-compatible until task 6 sets the
	// production-tuned value of 0.12. Mirrors Python's rerank_exponent.
	RerankExponent float64

	// M04 candidate-generation knobs.
	Mode          CandidateMode // M04 candidate-generation mode: cluster_only / embedding_only / union
	EmbeddingDMin float64       // inclusive lower band on cosine distance
	EmbeddingDMax float64       // inclusive upper band; must satisfy DMax > DMin
	EmbeddingTopK int           // cap on per-request embedding candidates

	// M05 type-aligned scoring.
	Gamma GammaWeight // weight on the type-diversity bonus in EvaluateCascadePair.
	// 0 disables M05 (M03/M04 behaviour preserved). Calibration sweep on
	// the Lakoff cohort picks the production value. Composition with the
	// existing additive cascade: final = ortony + Alpha·cosBonus + Gamma·typeBonus
}

// DefaultCascadeConfig returns the production-blessed winner config from
// the M03 Stage-2 sweep (separation +0.1779) plus the pre-sweep M04
// candidate-generation defaults. Mode is ModeCluster (M03 behaviour)
// until the M04 sweep ratifies ModeUnion.
//
// Gamma is ratified at 1.0 by the M05 Phase 2 Lakoff γ-sweep
// (2026-05-24). With pre-flight diagnostics confirming 100% of the
// cohort is data-resolvable and limit=10000 eliminating ranking-cutoff
// confound, the sweep produced a clean monotone signal:
//
//   γ=0.00 → separation=-0.2546   γ=0.50 → -0.1230
//   γ=0.25 → separation=-0.1888   γ=1.00 → +0.0086
//                                 γ=2.00 → +0.2717
//
// γ=1.0 brings the apt cohort to parity with the inapt survivors
// (separation ≈ 0) — the conservative "turn the signal on" choice.
// γ=2.0 scores higher in the sweep but the magnitude rides on n=1
// inapt and would overweight one design dimension across the broader
// thesaurus traffic that does not share the Lakoff cohort's
// cross-domain bias. See data-pipeline/sweeps/m05_lakoff_gamma_phase2_verdict.md.
//
// In-package direct GammaWeight{} construction is idiomatic here: 1.0
// is a compile-time-known valid literal, and NewGamma exists to guard
// the *operator entry point* (env/flag boundary), not in-package
// production defaults.
func DefaultCascadeConfig() CascadeConfig {
	return CascadeConfig{
		ConcretenessThreshold: 1.0,
		Alpha:                 1.0,
		DCap:                  0.77,
		Composition:           CompositionAdditive,
		Mode:                  ModeCluster,
		EmbeddingDMin:         0.4,
		EmbeddingDMax:         0.85,
		EmbeddingTopK:         100,
		Gamma:                 GammaWeight{v: 1.0},
	}
}

// EmbeddingTopKCeiling is the safety upper bound on EmbeddingTopK.
// Modern mattn/go-sqlite3 builds have SQLITE_MAX_VARIABLE_NUMBER=32766
// (SQLite ≥3.32, May 2020). 10000 is ~3× safety margin and matches the
// lab-mode canary's needs. SQLite ≤3.31 ships the historical 999
// limit, which would break this ceiling — chunking the IN-clause in
// db.getSynsetRowsBatch is the right cross-platform fix and is parked
// as an M04 v2 backlog item.
const EmbeddingTopKCeiling = 10000

// Validate enforces invariants on CascadeConfig before the handler
// accepts the config. Called at startup from main.go after env/flag
// parsing so bad values fail loud instead of silently degrading the
// scorer.
func (c CascadeConfig) Validate() error {
	if !c.Mode.Valid() {
		return fmt.Errorf("CandidateMode %q is not one of cluster_only|embedding_only|union", c.Mode)
	}
	if !c.Composition.Valid() {
		return fmt.Errorf("Composition %q is not one of additive|multiplicative", c.Composition)
	}
	if c.Alpha < 0 || math.IsNaN(c.Alpha) || math.IsInf(c.Alpha, 0) {
		return fmt.Errorf("Alpha %v must be ≥ 0 and finite", c.Alpha)
	}
	if c.DCap <= 0 || math.IsNaN(c.DCap) || math.IsInf(c.DCap, 0) {
		return fmt.Errorf("DCap %v must be > 0 and finite", c.DCap)
	}
	if math.IsNaN(c.ConcretenessThreshold) || math.IsInf(c.ConcretenessThreshold, 0) {
		return fmt.Errorf("ConcretenessThreshold %v must be finite", c.ConcretenessThreshold)
	}
	if c.EmbeddingDMin < 0.0 || c.EmbeddingDMin > 2.0 {
		return fmt.Errorf("EmbeddingDMin %v out of range [0, 2]", c.EmbeddingDMin)
	}
	if c.EmbeddingDMax <= c.EmbeddingDMin || c.EmbeddingDMax > 2.0 {
		return fmt.Errorf("EmbeddingDMax %v must be > EmbeddingDMin (%v) and ≤ 2.0",
			c.EmbeddingDMax, c.EmbeddingDMin)
	}
	if c.EmbeddingTopK <= 0 {
		return fmt.Errorf("EmbeddingTopK %d must be > 0", c.EmbeddingTopK)
	}
	if c.EmbeddingTopK > EmbeddingTopKCeiling {
		return fmt.Errorf("EmbeddingTopK %d exceeds ceiling %d (SQLite IN-clause variable limit safety)",
			c.EmbeddingTopK, EmbeddingTopKCeiling)
	}
	// Defence-in-depth: NewGamma guarantees these invariants on its
	// outputs, but a future deserialisation path (JSON/SQL config) could
	// build a GammaWeight outside NewGamma. Cheap to keep.
	if gv := c.Gamma.Value(); gv < 0 || math.IsNaN(gv) || math.IsInf(gv, 0) {
		return fmt.Errorf("Gamma %v must be ≥ 0 and finite", gv)
	}
	// γ-sweep only ratified the additive shape `final = ortony + Alpha·cosBonus
	// + Gamma·typeBonus`. With multiplicative composition the resulting shape
	// is `ortony*(1+Alpha*cos) + Gamma*tb`, which no sweep has validated —
	// fail loud rather than silently scoring on an untested combiner.
	if c.Gamma.Value() > 0 && c.Composition == CompositionMultiplicative {
		return fmt.Errorf("Gamma>0 is only validated with Composition=additive; got Gamma=%v with Composition=%s. Set Gamma=0 or Composition=additive.",
			c.Gamma.Value(), c.Composition)
	}
	return nil
}

// CascadeInputs bundles per-pair data for EvaluateCascadePair. Pointer
// concreteness so callers express 'absent' as nil. Nil/empty maps and
// nil centroids are valid 'absent' signals — the function routes them
// into the right status without panicking.
type CascadeInputs struct {
	TopicConcreteness   *float64
	VehicleConcreteness *float64
	TopicProperties     map[int64]float64
	VehicleProperties   map[int64]float64
	TopicCentroid       []float32
	VehicleCentroid     []float32

	// M05: cluster_id → dominant_type lookup, populated by the handler
	// from db.CascadeCache.ClusterTypes. Optional — when nil or empty,
	// EvaluateCascadePair skips the type-diversity bonus computation
	// regardless of Gamma. Empty-string values for a cluster_id mean
	// "type unknown" (pre-M05 DB with NULL dominant_type, or empty
	// cluster); these contribute zero to distinct-type count.
	ClusterTypes map[int64]string
}

// CascadeResult mirrors the Python CascadeResult — pointer fields are nil
// when the corresponding stage didn't run.
type CascadeResult struct {
	FinalScore     *float64
	GatePassed     bool
	OrtonyScore    *float64
	CosineDistance *float64
	ReRankBonus    *float64
	Status         CascadeStatus

	// M05 diagnostics — set only when Gamma > 0 and ClusterTypes was provided.
	TypeDiversityBonus *float64 // [0, 1] — (distinct_types - 1) / 5, clamped at 0
	SharedTypesCount   int      // 0..6 — count of distinct discriminating canonical types in the overlap (excludes "other" and unknown)
}

// TypeDiversityMaxDistinct is the canonical count of distinct property
// types used to normalise the type-diversity bonus to [0, 1]. The M04 v2
// audit confirms the LLM enrichment produces 6 canonical types
// (sensorimotor, behaviour, functional, effect, emotional, social). The
// "other" bucket exists for normalisation residue (~0.04% of rows) but
// is not counted as a distinct discriminating type — a metaphor whose
// shared overlap is one canonical type plus "other" is still
// effectively mono-typed.
const TypeDiversityMaxDistinct = 6

// TypeDiversityBonus returns the normalised distinct-type count over a
// shared cluster set. Inputs:
//
//   - shared: cluster_ids that appear in both topic and vehicle property
//     maps (the M03 jaccard intersection). May be empty.
//   - clusterTypes: cluster_id → dominant_type lookup. Missing entries
//     and empty-string values count as "unknown" and contribute zero.
//
// Returns (bonus ∈ [0, 1], distinctTypes ∈ [0, 6]) where bonus is
// `max(0, distinctTypes-1) / (TypeDiversityMaxDistinct-1)`. The
// 'minus 1' encodes the M05 hypothesis that any single shared type is
// expected (random within-domain overlap) and the discrimination signal
// starts at 2 distinct types.
func TypeDiversityBonus(shared []int64, clusterTypes map[int64]string) (float64, int) {
	if len(shared) == 0 || len(clusterTypes) == 0 {
		return 0.0, 0
	}
	seen := make(map[string]struct{}, len(shared))
	for _, cid := range shared {
		t, ok := clusterTypes[cid]
		if !ok || t == "" || t == "other" {
			continue
		}
		seen[t] = struct{}{}
	}
	distinct := len(seen)
	if distinct < 2 {
		return 0.0, distinct
	}
	denom := float64(TypeDiversityMaxDistinct - 1)
	return float64(distinct-1) / denom, distinct
}

// EvaluateCascadePair runs the three-stage cascade. Never panics on
// data-shape issues. The handler's SQL CTE may have pre-filtered gate
// rejects; this function still re-checks so unit tests cover the gate
// logic directly.
func EvaluateCascadePair(in CascadeInputs, cfg CascadeConfig) CascadeResult {
	if in.TopicConcreteness == nil || in.VehicleConcreteness == nil {
		return CascadeResult{Status: CascadeStatusMissingConcreteness}
	}
	signed := *in.VehicleConcreteness - *in.TopicConcreteness
	if signed < cfg.ConcretenessThreshold {
		zero := 0.0
		return CascadeResult{FinalScore: &zero, Status: CascadeStatusGateDropped}
	}

	if len(in.TopicProperties) == 0 || len(in.VehicleProperties) == 0 {
		return CascadeResult{GatePassed: true, Status: CascadeStatusNoProperties}
	}
	ortony := JaccardSalience(in.TopicProperties, in.VehicleProperties)

	var cosDist, bonus *float64
	if in.TopicCentroid != nil && in.VehicleCentroid != nil {
		if d, ok := CascadeCosineDistance(in.TopicCentroid, in.VehicleCentroid); ok {
			cosDist = &d
			exp := cfg.RerankExponent
			if exp == 0 {
				exp = 1.0 // back-compat: zero means "not set", use linear shape
			}
			rb := ReRankBonusPow(d, cfg.DCap, exp)
			bonus = &rb
		}
	}

	final := ortony
	if bonus != nil {
		switch cfg.Composition {
		case CompositionAdditive:
			final = ortony + cfg.Alpha*(*bonus)
		case CompositionMultiplicative:
			final = ortony * (1.0 + cfg.Alpha*(*bonus))
		}
	}

	// M05 type-diversity bonus. Composition is additive (mirrors the
	// production-winner additive cascade) and Gamma=0 by default so the
	// scoring math reduces to M03/M04 exactly when M05 is disabled.
	// When M05 runs (Gamma>0 + ClusterTypes provided), both diagnostic
	// fields are populated together so downstream readers can distinguish
	// "M05 didn't run" (pointer nil, count 0) from "M05 ran and scored
	// zero" (pointer set to 0.0, count reflects evaluation).
	var typeBonus *float64
	sharedTypesCount := 0
	// Tighten the gate to len > 0 (was != nil): the CascadeInputs.ClusterTypes
	// docstring promises a clean short-circuit for nil OR empty, and an
	// empty non-nil map still entered the loop pre-fix, allocating the
	// shared slice for an evaluation that TypeDiversityBonus would
	// immediately reject on len(clusterTypes)==0.
	if cfg.Gamma.Value() > 0 && len(in.ClusterTypes) > 0 {
		shared := make([]int64, 0, len(in.TopicProperties))
		for cid := range in.TopicProperties {
			if _, dual := in.VehicleProperties[cid]; dual {
				shared = append(shared, cid)
			}
		}
		tb, distinct := TypeDiversityBonus(shared, in.ClusterTypes)
		sharedTypesCount = distinct
		typeBonus = &tb
		if tb > 0 {
			final = final + cfg.Gamma.Value()*tb
		}
	}

	return CascadeResult{
		FinalScore:         &final,
		GatePassed:         true,
		OrtonyScore:        &ortony,
		CosineDistance:     cosDist,
		ReRankBonus:        bonus,
		Status:             CascadeStatusScored,
		TypeDiversityBonus: typeBonus,
		SharedTypesCount:   sharedTypesCount,
	}
}
