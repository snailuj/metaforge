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
