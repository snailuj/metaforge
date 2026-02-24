package forge

import (
	"math"
	"testing"
)

func TestClassifyTierIronic(t *testing.T) {
	tier := ClassifyTierCurated(1.0, 4) // low shared, high contrast
	if tier != TierIronic {
		t.Errorf("expected ironic, got %s", tier)
	}
}

func TestClassifyTierComplex(t *testing.T) {
	tier := ClassifyTierCurated(4.0, 4) // high shared, high contrast
	if tier != TierComplex {
		t.Errorf("expected complex, got %s", tier)
	}
}

func TestClassifyTierCuratedLegendary(t *testing.T) {
	tier := ClassifyTierCurated(5.0, 0) // high shared, no contrast
	if tier != TierLegendary {
		t.Errorf("expected legendary, got %s", tier)
	}
}

func TestClassifyTierCuratedStrong(t *testing.T) {
	tier := ClassifyTierCurated(3.0, 0) // moderate shared, no contrast
	if tier != TierStrong {
		t.Errorf("expected strong, got %s", tier)
	}
}

func TestClassifyTierCuratedUnlikely(t *testing.T) {
	tier := ClassifyTierCurated(1.0, 0) // low shared, no contrast
	if tier != TierUnlikely {
		t.Errorf("expected unlikely, got %s", tier)
	}
}

func TestCompositeScore_HighDistanceBoosts(t *testing.T) {
	// With Beta=0.5: sqrt(6)*1.1 = 2.69, sqrt(4)*1.7 = 3.40
	synonym := CompositeScore(6.0, 0.1)
	crossDomain := CompositeScore(4.0, 0.7)
	if crossDomain <= synonym {
		t.Errorf("cross-domain (%.2f) should beat synonym (%.2f)", crossDomain, synonym)
	}
}

func TestCompositeScore_ZeroOverlapAlwaysZero(t *testing.T) {
	score := CompositeScore(0.0, 0.9)
	if score != 0.0 {
		t.Errorf("expected 0, got %.2f", score)
	}
}

func TestCompositeScore_ZeroDistanceReturnsCompressedOverlap(t *testing.T) {
	// With Beta=0.5: sqrt(5) * 1.0 ≈ 2.236
	score := CompositeScore(5.0, 0.0)
	expected := math.Sqrt(5.0)
	if math.Abs(score-expected) > 0.001 {
		t.Errorf("expected %.3f, got %.3f", expected, score)
	}
}

func TestCompositeScore_FloatInput(t *testing.T) {
	// Verify CompositeScore works with float64 salience sum
	score := CompositeScore(3.5, 0.5)
	// 3.5^0.5 * (1 + 1.0 * 0.5) = 1.8708... * 1.5 = 2.806...
	expected := math.Pow(3.5, 0.5) * 1.5
	if math.Abs(score-expected) > 0.001 {
		t.Errorf("expected %.3f, got %.3f", expected, score)
	}
}

func TestCompositeScore_ClampsDistanceAboveOne(t *testing.T) {
	// CosineDistance can return up to 2.0 for opposite vectors.
	// CompositeScore should clamp to 1.0 so the multiplier caps at (1 + Alpha).
	atOne := CompositeScore(4.0, 1.0)
	atTwo := CompositeScore(4.0, 2.0)
	if atTwo != atOne {
		t.Errorf("distance=2.0 (%.3f) should equal distance=1.0 (%.3f) after clamping", atTwo, atOne)
	}
}

func TestCompositeScore_NegativeDistanceClampsToZero(t *testing.T) {
	atZero := CompositeScore(4.0, 0.0)
	atNeg := CompositeScore(4.0, -0.5)
	if atNeg != atZero {
		t.Errorf("negative distance (%.3f) should equal zero distance (%.3f) after clamping", atNeg, atZero)
	}
}

func TestSortByTier_UsesCompositeScore(t *testing.T) {
	matches := []Match{
		{Word: "synonym", OverlapCount: 6, Tier: TierLegendary, CompositeScore: 6.6},
		{Word: "metaphor", OverlapCount: 4, Tier: TierLegendary, CompositeScore: 6.8},
	}
	sorted := SortByTier(matches)
	if sorted[0].Word != "metaphor" {
		t.Errorf("expected metaphor first, got %s", sorted[0].Word)
	}
}
