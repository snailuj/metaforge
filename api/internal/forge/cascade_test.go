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
