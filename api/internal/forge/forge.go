// Package forge implements the Metaphor Forge 5-tier matching algorithm.
// It ranks synset matches based on property overlap and semantic distance.
package forge

import (
	"math"
	"sort"
)

// Tier represents the quality tier of a metaphor match.
type Tier int

const (
	TierLegendary Tier = iota // High shared + low contrast
	TierComplex               // High shared + high contrast (simultaneously alike and opposed)
	TierIronic                // Low shared + high contrast (ironic metaphor)
	TierStrong                // Moderate shared, low/no contrast
	TierUnlikely              // Low everything
)

func (t Tier) String() string {
	names := [...]string{"legendary", "complex", "ironic", "strong", "unlikely"}
	if int(t) < 0 || int(t) >= len(names) {
		return "unknown"
	}
	return names[t]
}

// Thresholds for tier classification
const (
	MinOverlap    = 2 // Minimum shared properties for "moderate" overlap
	StrongOverlap = 4 // Shared properties for "strong" overlap
)

// MinContrastOverlap is the minimum antonymous properties for contrast-based tiers.
const MinContrastOverlap = 3

// ClassifyTierCurated determines tier from shared and contrast property counts.
// Used with the curated vocabulary (set-intersection matching, no cosine distance).
func ClassifyTierCurated(shared, contrast int) Tier {
	highShared := shared >= StrongOverlap
	moderateShared := shared >= MinOverlap
	highContrast := contrast >= MinContrastOverlap

	switch {
	case highShared && highContrast:
		return TierComplex
	case !moderateShared && highContrast:
		return TierIronic
	case highShared:
		return TierLegendary
	case moderateShared:
		return TierStrong
	default:
		return TierUnlikely
	}
}

// Match represents a candidate metaphor match.
type Match struct {
	SynsetID         string   `json:"synset_id"`
	Word             string   `json:"word"`
	Definition       string   `json:"definition,omitempty"`
	SharedProperties []string `json:"shared_properties,omitempty"`
	OverlapCount     int      `json:"overlap_count"`
	Tier             Tier     `json:"-"`
	TierName         string   `json:"tier"`
	SourceSynsetID   string   `json:"source_synset_id,omitempty"`
	SourceDefinition string   `json:"source_definition,omitempty"`
	SourcePOS        string   `json:"source_pos,omitempty"`
	DomainDistance   float64  `json:"domain_distance,omitempty"`
	CompositeScore   float64  `json:"composite_score,omitempty"`
}

// Alpha is the tuneable weight for the cross-domain distance bonus.
// Beta compresses the overlap scale: 1.0 = linear, 0.5 = sqrt, 0 = ignore overlap.
const (
	Alpha = 1.0
	Beta  = 0.5
)

// CompositeScore computes overlap^Beta × (1 + Alpha × domainDistance).
// Beta < 1 compresses the overlap scale so domain distance has more
// influence on ranking across overlap tiers.
func CompositeScore(overlapCount int, domainDistance float64) float64 {
	return math.Pow(float64(overlapCount), Beta) * (1.0 + Alpha*domainDistance)
}

// SortByTier sorts matches by tier (best first), then by composite score.
func SortByTier(matches []Match) []Match {
	sorted := make([]Match, len(matches))
	copy(sorted, matches)

	sort.Slice(sorted, func(i, j int) bool {
		// Primary: tier (lower = better)
		if sorted[i].Tier != sorted[j].Tier {
			return sorted[i].Tier < sorted[j].Tier
		}
		// Secondary: composite score (higher = better)
		return sorted[i].CompositeScore > sorted[j].CompositeScore
	})

	return sorted
}
