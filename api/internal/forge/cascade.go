// Cascade scorer: concreteness gate → jaccard_salience Ortony rank →
// cosine-distance re-rank. Mirrors data-pipeline/scripts/evaluate_cascade.py
// — divergences from the Python ground truth in the smoke crib are port bugs.
package forge

import "math"

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

// CascadeConfig pins the cascade hyperparameters. Use DefaultCascadeConfig
// for the production-blessed winner config.
type CascadeConfig struct {
	ConcretenessThreshold float64
	Alpha                 float64
	DCap                  float64
	Composition           Composition
}

// DefaultCascadeConfig returns the production-blessed winner config from
// the M03 Stage-2 sweep (separation +0.1779).
func DefaultCascadeConfig() CascadeConfig {
	return CascadeConfig{
		ConcretenessThreshold: 1.0,
		Alpha:                 1.0,
		DCap:                  0.77,
		Composition:           CompositionAdditive,
	}
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
			rb := ReRankBonus(d, cfg.DCap)
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

	return CascadeResult{
		FinalScore:     &final,
		GatePassed:     true,
		OrtonyScore:    &ortony,
		CosineDistance: cosDist,
		ReRankBonus:    bonus,
		Status:         CascadeStatusScored,
	}
}
