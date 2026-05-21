package forge

import (
	"math"
	"testing"
)

func TestJaccardSalience_PerfectOverlap(t *testing.T) {
	a := map[int64]float64{1: 1.0, 2: 1.0}
	b := map[int64]float64{1: 1.0, 2: 1.0}
	if got := JaccardSalience(a, b); math.Abs(got-1.0) > 1e-9 {
		t.Errorf("expected 1.0, got %v", got)
	}
}

func TestJaccardSalience_DisjointReturnsZero(t *testing.T) {
	a := map[int64]float64{1: 0.5}
	b := map[int64]float64{2: 0.5}
	if got := JaccardSalience(a, b); got != 0.0 {
		t.Errorf("expected 0.0, got %v", got)
	}
}

func TestJaccardSalience_EmptyInputsReturnZero(t *testing.T) {
	if got := JaccardSalience(nil, nil); got != 0.0 {
		t.Errorf("expected 0.0 for nil/nil, got %v", got)
	}
	if got := JaccardSalience(map[int64]float64{}, map[int64]float64{1: 0.5}); got != 0.0 {
		t.Errorf("expected 0.0 for empty/full, got %v", got)
	}
}

func TestJaccardSalience_AsymmetricSalienceMatchesPython(t *testing.T) {
	// pa = {1:0.8, 2:0.4, 3:0.1}, pb = {1:0.2, 2:0.6, 4:0.9}
	// shared = {1,2}; num = min(0.8,0.2)+min(0.4,0.6) = 0.6
	// union = {1,2,3,4}; den = 0.8+0.6+0.1+0.9 = 2.4
	// score = 0.6/2.4 = 0.25
	a := map[int64]float64{1: 0.8, 2: 0.4, 3: 0.1}
	b := map[int64]float64{1: 0.2, 2: 0.6, 4: 0.9}
	if got := JaccardSalience(a, b); math.Abs(got-0.25) > 1e-9 {
		t.Errorf("expected 0.25, got %v", got)
	}
}

func TestReRankBonus_BelowZeroReturnsZero(t *testing.T) {
	if got := ReRankBonus(-0.1, 0.77); got != 0.0 {
		t.Errorf("want 0.0, got %v", got)
	}
}

func TestReRankBonus_AtCapReturnsOne(t *testing.T) {
	if got := ReRankBonus(0.77, 0.77); math.Abs(got-1.0) > 1e-9 {
		t.Errorf("want 1.0, got %v", got)
	}
}

func TestReRankBonus_AboveCapSaturatesAtOne(t *testing.T) {
	if got := ReRankBonus(1.5, 0.77); got != 1.0 {
		t.Errorf("want 1.0, got %v", got)
	}
}

func TestReRankBonus_LinearBelowCap(t *testing.T) {
	if got := ReRankBonus(0.385, 0.77); math.Abs(got-0.5) > 1e-9 {
		t.Errorf("want 0.5, got %v", got)
	}
}

func TestCascadeCosineDistance_Identical(t *testing.T) {
	v := []float32{1, 0, 0}
	d, ok := CascadeCosineDistance(v, v)
	if !ok {
		t.Fatal("ok=false on identical")
	}
	if math.Abs(d) > 1e-6 {
		t.Errorf("want ~0, got %v", d)
	}
}

func TestCascadeCosineDistance_Orthogonal(t *testing.T) {
	d, ok := CascadeCosineDistance([]float32{1, 0}, []float32{0, 1})
	if !ok {
		t.Fatal("ok=false on orthogonal")
	}
	if math.Abs(d-1.0) > 1e-6 {
		t.Errorf("want ~1.0, got %v", d)
	}
}

func TestCascadeCosineDistance_DimMismatchReturnsNotOk(t *testing.T) {
	if _, ok := CascadeCosineDistance([]float32{1, 0, 0}, []float32{1, 0}); ok {
		t.Error("expected ok=false on dim mismatch")
	}
}

func TestCascadeCosineDistance_ZeroNormReturnsNotOk(t *testing.T) {
	if _, ok := CascadeCosineDistance([]float32{0, 0, 0}, []float32{1, 0, 0}); ok {
		t.Error("expected ok=false on zero norm")
	}
}
