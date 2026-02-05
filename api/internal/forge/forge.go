// Package forge implements the Metaphor Forge 5-tier matching algorithm.
// It ranks synset matches based on property overlap and semantic distance.
package forge

import "sort"

// Tier represents the quality tier of a metaphor match.
type Tier int

const (
	TierLegendary   Tier = iota // High distance + strong overlap (4+)
	TierInteresting             // High distance + weak overlap (1)
	TierStrong                  // High distance + moderate overlap (2-3)
	TierObvious                 // Low distance + any overlap
	TierUnlikely                // Low distance + weak overlap
)

func (t Tier) String() string {
	return [...]string{"legendary", "interesting", "strong", "obvious", "unlikely"}[t]
}

// Thresholds for tier classification
const (
	HighDistanceThreshold = 0.6 // Semantic distance above which concepts are "far"
	MinOverlap            = 2   // Minimum shared properties for "moderate" overlap
	StrongOverlap         = 4   // Shared properties for "strong" overlap
)

// Match represents a candidate metaphor match.
type Match struct {
	SynsetID         string   `json:"synset_id"`
	Word             string   `json:"word"`
	Definition       string   `json:"definition,omitempty"`
	SharedProperties []string `json:"shared_properties,omitempty"`
	OverlapCount     int      `json:"overlap_count"`
	Distance         float64  `json:"distance"`
	Tier             Tier     `json:"-"`
	TierName         string   `json:"tier"`
}

// ClassifyTier determines the quality tier based on distance and overlap.
//
// The algorithm rewards "surprising" connections:
// - High distance = concepts are semantically far apart
// - High overlap = concepts share many structural properties
// - Legendary = far apart but share many properties (best metaphors)
func ClassifyTier(distance float64, overlap int) Tier {
	highDistance := distance > HighDistanceThreshold
	strongOverlap := overlap >= StrongOverlap
	moderateOverlap := overlap >= MinOverlap

	switch {
	case highDistance && strongOverlap:
		return TierLegendary
	case highDistance && !moderateOverlap:
		return TierInteresting
	case highDistance && moderateOverlap:
		return TierStrong
	case !highDistance && moderateOverlap:
		return TierObvious
	default:
		return TierUnlikely
	}
}

// NormaliseDistances rescales distances to [0, 1] based on the min/max
// within the result set. This ensures tier classification works relative
// to each word's candidate pool, not on absolute centroid distances
// (which cluster narrowly due to shared-property discovery bias).
func NormaliseDistances(distances []float64) []float64 {
	if len(distances) == 0 {
		return distances
	}

	min, max := distances[0], distances[0]
	for _, d := range distances[1:] {
		if d < min {
			min = d
		}
		if d > max {
			max = d
		}
	}

	span := max - min
	if span == 0 {
		// All distances identical — return as-is
		result := make([]float64, len(distances))
		copy(result, distances)
		return result
	}

	result := make([]float64, len(distances))
	for i, d := range distances {
		result[i] = (d - min) / span
	}
	return result
}

// SortByTier sorts matches by tier (best first), then by overlap count.
func SortByTier(matches []Match) []Match {
	sorted := make([]Match, len(matches))
	copy(sorted, matches)

	sort.Slice(sorted, func(i, j int) bool {
		// Primary: tier (lower = better)
		if sorted[i].Tier != sorted[j].Tier {
			return sorted[i].Tier < sorted[j].Tier
		}
		// Secondary: overlap count (higher = better)
		if sorted[i].OverlapCount != sorted[j].OverlapCount {
			return sorted[i].OverlapCount > sorted[j].OverlapCount
		}
		// Tertiary: distance (higher = more surprising)
		return sorted[i].Distance > sorted[j].Distance
	})

	return sorted
}
