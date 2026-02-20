package forge

import "testing"

func TestClassifyTierIronic(t *testing.T) {
	tier := ClassifyTierCurated(1, 4) // low shared, high contrast
	if tier != TierIronic {
		t.Errorf("expected ironic, got %s", tier)
	}
}

func TestClassifyTierComplex(t *testing.T) {
	tier := ClassifyTierCurated(4, 4) // high shared, high contrast
	if tier != TierComplex {
		t.Errorf("expected complex, got %s", tier)
	}
}

func TestClassifyTierCuratedLegendary(t *testing.T) {
	tier := ClassifyTierCurated(5, 0) // high shared, no contrast
	if tier != TierLegendary {
		t.Errorf("expected legendary, got %s", tier)
	}
}

func TestClassifyTierCuratedStrong(t *testing.T) {
	tier := ClassifyTierCurated(3, 0) // moderate shared, no contrast
	if tier != TierStrong {
		t.Errorf("expected strong, got %s", tier)
	}
}

func TestClassifyTierCuratedUnlikely(t *testing.T) {
	tier := ClassifyTierCurated(1, 0) // low shared, no contrast
	if tier != TierUnlikely {
		t.Errorf("expected unlikely, got %s", tier)
	}
}
