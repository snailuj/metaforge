package forge

import (
	"math"
	"strings"
	"testing"
)

// mustGamma is a test helper that constructs a GammaWeight via NewGamma
// or fails the test on construction error. Use this in place of the
// pre-struct-wrap `cfg.Gamma = 1.0` assignment idiom — the unexported
// field on GammaWeight forbids direct literal assignment, forcing all
// test-side construction through the same validated boundary as
// production main.go.
func mustGamma(t *testing.T, v float64) GammaWeight {
	t.Helper()
	g, err := NewGamma(v)
	if err != nil {
		t.Fatalf("mustGamma(%v): %v", v, err)
	}
	return g
}

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

func TestCascadeCosineDistanceWithANorm_RejectsBadANorm(t *testing.T) {
	a := []float32{1, 0, 0}
	b := []float32{0, 1, 0}
	cases := []struct {
		name  string
		aNorm float64
	}{
		{"zero", 0},
		{"negative", -1.0},
		{"NaN", math.NaN()},
		{"+Inf", math.Inf(1)},
		{"-Inf", math.Inf(-1)},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			d, ok := CascadeCosineDistanceWithANorm(a, tc.aNorm, b)
			if ok {
				t.Errorf("aNorm=%v: want ok=false, got d=%v ok=true", tc.aNorm, d)
			}
		})
	}
}

func TestCascadeCosineDistanceWithANorm_AcceptsGoodANorm(t *testing.T) {
	a := []float32{1, 0, 0}
	b := []float32{1, 0, 0}
	aNorm := math.Sqrt(1.0) // = 1
	d, ok := CascadeCosineDistanceWithANorm(a, aNorm, b)
	if !ok {
		t.Fatalf("want ok=true for valid aNorm")
	}
	if d > 1e-9 {
		t.Errorf("identical vectors should give distance ~0, got %v", d)
	}
}

func TestCascadeConfig_DefaultsMatchProductionWinner(t *testing.T) {
	c := DefaultCascadeConfig()
	if c.ConcretenessThreshold != 1.0 {
		t.Errorf("threshold: want 1.0, got %v", c.ConcretenessThreshold)
	}
	if c.Alpha != 1.0 {
		t.Errorf("alpha: want 1.0, got %v", c.Alpha)
	}
	if c.DCap != 0.77 {
		t.Errorf("d_cap: want 0.77, got %v", c.DCap)
	}
	if c.Composition != CompositionAdditive {
		t.Errorf("composition: want additive, got %v", c.Composition)
	}
}

func TestEvaluateCascadePair_GateDroppedOnLowSignedDelta(t *testing.T) {
	res := EvaluateCascadePair(CascadeInputs{
		TopicConcreteness:   floatPtr(4.0),
		VehicleConcreteness: floatPtr(4.5),
	}, DefaultCascadeConfig())
	if res.Status != CascadeStatusGateDropped {
		t.Errorf("want gate_dropped, got %v", res.Status)
	}
	if res.FinalScore == nil || *res.FinalScore != 0.0 {
		t.Errorf("gate_dropped final_score: want 0.0, got %v", res.FinalScore)
	}
}

func TestEvaluateCascadePair_MissingConcreteness(t *testing.T) {
	res := EvaluateCascadePair(CascadeInputs{
		TopicConcreteness:   nil,
		VehicleConcreteness: floatPtr(4.5),
	}, DefaultCascadeConfig())
	if res.Status != CascadeStatusMissingConcreteness {
		t.Errorf("want missing_concreteness, got %v", res.Status)
	}
}

func TestEvaluateCascadePair_NoPropertiesAfterGate(t *testing.T) {
	res := EvaluateCascadePair(CascadeInputs{
		TopicConcreteness:   floatPtr(2.0),
		VehicleConcreteness: floatPtr(4.5),
		TopicProperties:     map[int64]float64{},
		VehicleProperties:   map[int64]float64{1: 0.5},
	}, DefaultCascadeConfig())
	if res.Status != CascadeStatusNoProperties {
		t.Errorf("want no_properties, got %v", res.Status)
	}
	if !res.GatePassed {
		t.Error("no_properties must have gate_passed=true")
	}
}

func TestEvaluateCascadePair_ScoredAdditive_NoBonus(t *testing.T) {
	// signed delta 2.5 → gate passes; jaccard=1; cos_dist=0 → bonus=0; final=1
	res := EvaluateCascadePair(CascadeInputs{
		TopicConcreteness:   floatPtr(2.0),
		VehicleConcreteness: floatPtr(4.5),
		TopicProperties:     map[int64]float64{1: 1.0, 2: 1.0},
		VehicleProperties:   map[int64]float64{1: 1.0, 2: 1.0},
		TopicCentroid:       []float32{1, 0, 0},
		VehicleCentroid:     []float32{1, 0, 0},
	}, DefaultCascadeConfig())
	if res.Status != CascadeStatusScored {
		t.Fatalf("want scored, got %v", res.Status)
	}
	if res.FinalScore == nil || math.Abs(*res.FinalScore-1.0) > 1e-9 {
		t.Errorf("final_score: want 1.0, got %v", res.FinalScore)
	}
}

func TestEvaluateCascadePair_ScoredAdditive_WithBonus(t *testing.T) {
	// jaccard=1; cos_dist=1 → bonus=clip(1/0.77)=1; additive: 1 + 1*1 = 2
	res := EvaluateCascadePair(CascadeInputs{
		TopicConcreteness:   floatPtr(2.0),
		VehicleConcreteness: floatPtr(4.5),
		TopicProperties:     map[int64]float64{1: 1.0, 2: 1.0},
		VehicleProperties:   map[int64]float64{1: 1.0, 2: 1.0},
		TopicCentroid:       []float32{1, 0, 0},
		VehicleCentroid:     []float32{0, 1, 0},
	}, DefaultCascadeConfig())
	if res.Status != CascadeStatusScored {
		t.Fatalf("want scored, got %v", res.Status)
	}
	if res.FinalScore == nil || math.Abs(*res.FinalScore-2.0) > 1e-9 {
		t.Errorf("final_score: want 2.0, got %v", res.FinalScore)
	}
}

func TestEvaluateCascadePair_FailOpenOnMissingCentroid(t *testing.T) {
	res := EvaluateCascadePair(CascadeInputs{
		TopicConcreteness:   floatPtr(2.0),
		VehicleConcreteness: floatPtr(4.5),
		TopicProperties:     map[int64]float64{1: 1.0, 2: 1.0},
		VehicleProperties:   map[int64]float64{1: 1.0, 2: 1.0},
		TopicCentroid:       nil,
		VehicleCentroid:     nil,
	}, DefaultCascadeConfig())
	if res.Status != CascadeStatusScored {
		t.Fatalf("want scored (fail-open), got %v", res.Status)
	}
	if res.FinalScore == nil || math.Abs(*res.FinalScore-1.0) > 1e-9 {
		t.Errorf("final_score: want 1.0 (ortony only), got %v", res.FinalScore)
	}
	if res.CosineDistance != nil || res.ReRankBonus != nil {
		t.Error("missing centroid must leave cosine_distance + re_rank_bonus nil")
	}
}

func floatPtr(v float64) *float64 { return &v }

func TestCandidateSource_ValidRecognisesKnownTags(t *testing.T) {
	for _, s := range []CandidateSource{SourceCluster, SourceEmbedding, SourceBoth} {
		if !s.Valid() {
			t.Errorf("CandidateSource(%q).Valid() = false, want true", s)
		}
	}
}

func TestCandidateSource_ValidRejectsUnknown(t *testing.T) {
	for _, s := range []CandidateSource{"", "neither", "cluster_only", "embedding_only"} {
		if CandidateSource(s).Valid() {
			t.Errorf("CandidateSource(%q).Valid() = true, want false", s)
		}
	}
}

func TestCandidateMode_ValidRecognisesKnownModes(t *testing.T) {
	for _, s := range []CandidateMode{ModeCluster, ModeEmbedding, ModeUnion} {
		if !s.Valid() {
			t.Errorf("CandidateMode(%q).Valid() = false, want true", s)
		}
	}
}

func TestCandidateMode_ValidRejectsUnknown(t *testing.T) {
	for _, s := range []CandidateMode{"", "cluster", "embedding", "both", "all"} {
		if CandidateMode(s).Valid() {
			t.Errorf("CandidateMode(%q).Valid() = true, want false", s)
		}
	}
}

func TestParseCandidateMode_AcceptsKnownModes(t *testing.T) {
	for _, s := range []string{"cluster_only", "embedding_only", "union"} {
		m, err := ParseCandidateMode(s)
		if err != nil {
			t.Errorf("ParseCandidateMode(%q): unexpected error: %v", s, err)
		}
		if string(m) != s {
			t.Errorf("ParseCandidateMode(%q): got %q, want %q", s, m, s)
		}
	}
}

func TestParseCandidateMode_RejectsUnknownAndEmpty(t *testing.T) {
	for _, s := range []string{"", "cluster", "embedding", "both", "all", "CLUSTER_ONLY"} {
		_, err := ParseCandidateMode(s)
		if err == nil {
			t.Errorf("ParseCandidateMode(%q): want error, got nil", s)
		}
	}
}

func TestCascadeConfig_DefaultIsValid(t *testing.T) {
	cfg := DefaultCascadeConfig()
	if err := cfg.Validate(); err != nil {
		t.Errorf("DefaultCascadeConfig must validate: %v", err)
	}
	if cfg.Mode != ModeCluster {
		t.Errorf("default Mode: want %q (pre-sweep), got %q",
			ModeCluster, cfg.Mode)
	}
	if cfg.EmbeddingDMin != 0.4 || cfg.EmbeddingDMax != 0.85 || cfg.EmbeddingTopK != 100 {
		t.Errorf("default embedding knobs: got dMin=%v dMax=%v topK=%v",
			cfg.EmbeddingDMin, cfg.EmbeddingDMax, cfg.EmbeddingTopK)
	}
}

func TestCascadeConfig_ValidateRejectsBadFields(t *testing.T) {
	base := DefaultCascadeConfig()

	cases := []struct {
		name string
		mut  func(c *CascadeConfig)
		want string
	}{
		{"unknown sources", func(c *CascadeConfig) { c.Mode = "all" }, "CandidateMode"},
		{"negative dMin", func(c *CascadeConfig) { c.EmbeddingDMin = -0.1 }, "EmbeddingDMin"},
		{"dMin above 2", func(c *CascadeConfig) { c.EmbeddingDMin = 2.5 }, "EmbeddingDMin"},
		{"dMax not above dMin", func(c *CascadeConfig) { c.EmbeddingDMax = c.EmbeddingDMin }, "EmbeddingDMax"},
		{"topK zero", func(c *CascadeConfig) { c.EmbeddingTopK = 0 }, "EmbeddingTopK"},
		{"topK negative", func(c *CascadeConfig) { c.EmbeddingTopK = -5 }, "EmbeddingTopK"},
		{"invalid composition", func(c *CascadeConfig) { c.Composition = "weird" }, "Composition"},
		{"negative alpha", func(c *CascadeConfig) { c.Alpha = -0.1 }, "Alpha"},
		{"NaN alpha", func(c *CascadeConfig) { c.Alpha = math.NaN() }, "Alpha"},
		{"zero dCap", func(c *CascadeConfig) { c.DCap = 0 }, "DCap"},
		{"negative dCap", func(c *CascadeConfig) { c.DCap = -1 }, "DCap"},
		{"NaN concreteness threshold", func(c *CascadeConfig) { c.ConcretenessThreshold = math.NaN() }, "ConcretenessThreshold"},
		{"topK above ceiling", func(c *CascadeConfig) { c.EmbeddingTopK = EmbeddingTopKCeiling + 1 }, "EmbeddingTopK"},
		// Direct struct-literal construction is the ONLY way to forge an
		// invalid GammaWeight now (same-package only). These three rows
		// exercise the defence-in-depth Validate branch — the same branch
		// that future deserialisation paths would rely on.
		{"negative gamma", func(c *CascadeConfig) { c.Gamma = GammaWeight{v: -0.1} }, "Gamma"},
		{"NaN gamma", func(c *CascadeConfig) { c.Gamma = GammaWeight{v: math.NaN()} }, "Gamma"},
		{"Inf gamma", func(c *CascadeConfig) { c.Gamma = GammaWeight{v: math.Inf(1)} }, "Gamma"},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			c := base
			tc.mut(&c)
			err := c.Validate()
			if err == nil {
				t.Fatalf("want error mentioning %q, got nil", tc.want)
			}
			if !strings.Contains(err.Error(), tc.want) {
				t.Errorf("want error containing %q, got %v", tc.want, err)
			}
		})
	}
}

func TestCascadeConfig_Validate_RejectsGammaWithMultiplicative(t *testing.T) {
	// γ-sweep only validated additive composition. Gamma>0 combined with
	// multiplicative yields an untested score shape — fail loud at startup.
	cfg := DefaultCascadeConfig()
	cfg.Composition = CompositionMultiplicative
	cfg.Gamma = mustGamma(t, 0.5)
	err := cfg.Validate()
	if err == nil {
		t.Fatal("want error for Gamma>0 + CompositionMultiplicative, got nil")
	}
	msg := err.Error()
	if !strings.Contains(msg, "Gamma") {
		t.Errorf("error must mention Gamma, got %v", msg)
	}
	if !strings.Contains(msg, "multiplicative") && !strings.Contains(msg, "Multiplicative") {
		t.Errorf("error must mention multiplicative composition, got %v", msg)
	}
}

func TestGammaWeight_ZeroValueIsValidAndZero(t *testing.T) {
	// DefaultCascadeConfig relies on the GammaWeight zero value
	// representing "M05 dormant" (v=0). The struct-wrap change means
	// the zero value is GammaWeight{} rather than GammaWeight(0); pin
	// the contract so a future refactor (e.g. adding a "constructed via
	// NewGamma" sentinel field) can't silently break the dormant default.
	var g GammaWeight
	if g.Value() != 0 {
		t.Errorf("zero-value GammaWeight: want Value()==0, got %v", g.Value())
	}
	cfg := DefaultCascadeConfig()
	if cfg.Gamma.Value() != 0 {
		t.Errorf("DefaultCascadeConfig.Gamma: want Value()==0 (M05 dormant), got %v",
			cfg.Gamma.Value())
	}
	if err := cfg.Validate(); err != nil {
		t.Errorf("DefaultCascadeConfig must validate with zero-value Gamma: %v", err)
	}
}

func TestNewGamma_RejectsNegativeNaNInf(t *testing.T) {
	// NewGamma is the operator-boundary cast for the γ env/flag value.
	// A GammaWeight value is proof of validity at construction —
	// negative, NaN, and ±Inf raw inputs must error rather than producing
	// an invalid newtype that only Validate() would catch later.
	cases := []struct {
		name string
		in   float64
	}{
		{"negative", -0.1},
		{"NaN", math.NaN()},
		{"PosInf", math.Inf(1)},
		{"NegInf", math.Inf(-1)},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			defer func() {
				if r := recover(); r != nil {
					t.Fatalf("NewGamma(%v) panicked: %v", tc.in, r)
				}
			}()
			_, err := NewGamma(tc.in)
			if err == nil {
				t.Fatalf("NewGamma(%v) want error, got nil", tc.in)
			}
		})
	}
}

func TestNewGamma_AcceptsZeroAndPositive(t *testing.T) {
	// Zero (M05 disabled) and any finite positive weight are valid.
	cases := []float64{0, 0.5, 2.0, 1e9}
	for _, v := range cases {
		t.Run("", func(t *testing.T) {
			g, err := NewGamma(v)
			if err != nil {
				t.Fatalf("NewGamma(%v) unexpected error: %v", v, err)
			}
			if g.Value() != v {
				t.Errorf("NewGamma(%v) round-trip: got %v", v, g.Value())
			}
		})
	}
}

func TestTypeDiversityBonus_EmptyInputsReturnZero(t *testing.T) {
	b, n := TypeDiversityBonus(nil, nil)
	if b != 0 || n != 0 {
		t.Errorf("nil inputs: want (0,0), got (%v,%v)", b, n)
	}
	b, n = TypeDiversityBonus([]int64{1, 2}, nil)
	if b != 0 || n != 0 {
		t.Errorf("nil types map: want (0,0), got (%v,%v)", b, n)
	}
	b, n = TypeDiversityBonus(nil, map[int64]string{1: "sensorimotor"})
	if b != 0 || n != 0 {
		t.Errorf("nil shared: want (0,0), got (%v,%v)", b, n)
	}
}

func TestTypeDiversityBonus_SingleTypeReturnsZero(t *testing.T) {
	shared := []int64{1, 2, 3}
	types := map[int64]string{1: "sensorimotor", 2: "sensorimotor", 3: "sensorimotor"}
	b, n := TypeDiversityBonus(shared, types)
	if b != 0 {
		t.Errorf("single type bonus: want 0, got %v", b)
	}
	if n != 1 {
		t.Errorf("distinct count: want 1, got %d", n)
	}
}

func TestTypeDiversityBonus_TwoTypesNormalisedToFifth(t *testing.T) {
	shared := []int64{1, 2}
	types := map[int64]string{1: "sensorimotor", 2: "behaviour"}
	b, n := TypeDiversityBonus(shared, types)
	want := 1.0 / 5.0 // (2-1)/(6-1)
	if math.Abs(b-want) > 1e-9 {
		t.Errorf("two-type bonus: want %v, got %v", want, b)
	}
	if n != 2 {
		t.Errorf("distinct count: want 2, got %d", n)
	}
}

func TestTypeDiversityBonus_AllSixTypesGivesOne(t *testing.T) {
	shared := []int64{1, 2, 3, 4, 5, 6}
	types := map[int64]string{
		1: "sensorimotor", 2: "behaviour", 3: "functional",
		4: "effect", 5: "emotional", 6: "social",
	}
	b, n := TypeDiversityBonus(shared, types)
	if math.Abs(b-1.0) > 1e-9 {
		t.Errorf("six-type bonus: want 1.0, got %v", b)
	}
	if n != 6 {
		t.Errorf("distinct count: want 6, got %d", n)
	}
}

func TestTypeDiversityBonus_OtherAndEmptyExcluded(t *testing.T) {
	// "other" and empty strings don't count as distinct types — they're
	// the M04 v2 audit's normalisation residue, not a discriminating signal.
	shared := []int64{1, 2, 3, 4}
	types := map[int64]string{
		1: "sensorimotor", 2: "other", 3: "", 4: "behaviour",
	}
	b, n := TypeDiversityBonus(shared, types)
	want := 1.0 / 5.0 // only 2 canonical: sensorimotor + behaviour
	if math.Abs(b-want) > 1e-9 {
		t.Errorf("with other/empty: want %v, got %v", want, b)
	}
	if n != 2 {
		t.Errorf("distinct count: want 2, got %d", n)
	}
}

func TestEvaluateCascadePair_GammaZeroSkipsTypeBonus(t *testing.T) {
	// M05 must be a no-op when Gamma=0 (default).
	cfg := DefaultCascadeConfig()
	cfg.Gamma = mustGamma(t, 0.0)
	tConc := 3.0
	vConc := 4.5
	in := CascadeInputs{
		TopicConcreteness:   &tConc,
		VehicleConcreteness: &vConc,
		TopicProperties:     map[int64]float64{1: 0.9, 2: 0.8},
		VehicleProperties:   map[int64]float64{1: 0.7, 2: 0.6},
		ClusterTypes:        map[int64]string{1: "sensorimotor", 2: "behaviour"},
	}
	res := EvaluateCascadePair(in, cfg)
	if res.TypeDiversityBonus != nil {
		t.Errorf("Gamma=0: TypeDiversityBonus should be nil, got %v", *res.TypeDiversityBonus)
	}
	if res.SharedTypesCount != 0 {
		t.Errorf("Gamma=0: SharedTypesCount should be 0 (M03/M04 short-circuit), got %d", res.SharedTypesCount)
	}
}

func TestEvaluateCascadePair_GammaPositiveLiftsFinalScore(t *testing.T) {
	// Same inputs as Gamma=0 but with Gamma=1.0 — final_score should
	// increase by (gamma * type_diversity_bonus) = (1.0 * 0.2) = 0.2.
	cfg := DefaultCascadeConfig()
	cfg.Gamma = mustGamma(t, 0.0)
	tConc := 3.0
	vConc := 4.5
	in := CascadeInputs{
		TopicConcreteness:   &tConc,
		VehicleConcreteness: &vConc,
		TopicProperties:     map[int64]float64{1: 0.9, 2: 0.8},
		VehicleProperties:   map[int64]float64{1: 0.7, 2: 0.6},
		ClusterTypes:        map[int64]string{1: "sensorimotor", 2: "behaviour"},
	}
	baseline := EvaluateCascadePair(in, cfg)

	cfg.Gamma = mustGamma(t, 1.0)
	with := EvaluateCascadePair(in, cfg)

	if baseline.FinalScore == nil || with.FinalScore == nil {
		t.Fatalf("FinalScore unexpectedly nil: baseline=%v with=%v", baseline.FinalScore, with.FinalScore)
	}
	delta := *with.FinalScore - *baseline.FinalScore
	want := 1.0 * (1.0 / 5.0) // gamma * normalised distinct-type count
	if math.Abs(delta-want) > 1e-9 {
		t.Errorf("Gamma=1 lift: want delta=%v, got %v (baseline=%v with=%v)",
			want, delta, *baseline.FinalScore, *with.FinalScore)
	}
	if with.TypeDiversityBonus == nil {
		t.Errorf("with Gamma>0: TypeDiversityBonus should be set")
	}
	if with.SharedTypesCount != 2 {
		t.Errorf("SharedTypesCount: want 2, got %d", with.SharedTypesCount)
	}
}

func TestEvaluateCascadePair_GammaPositive_ZeroDistinctTypes_DiagnosticsConsistent(t *testing.T) {
	// When M05 evaluates a pair but the shared overlap yields <2 distinct
	// canonical types (single type, or only "other"/unknown), the two
	// diagnostic fields must agree on "M05 evaluated this pair":
	// TypeDiversityBonus pointer set (to 0.0) AND SharedTypesCount reflects
	// the count from that evaluation. Prior behaviour left the pointer nil
	// (because `if tb > 0`) but populated SharedTypesCount — readers had no
	// way to distinguish "M05 didn't run" from "M05 ran and scored zero".
	cfg := DefaultCascadeConfig()
	cfg.Gamma = mustGamma(t, 1.0)
	tConc := 3.0
	vConc := 4.5

	// Case 1: single distinct type in overlap → distinct=1, bonus=0.
	in1 := CascadeInputs{
		TopicConcreteness:   &tConc,
		VehicleConcreteness: &vConc,
		TopicProperties:     map[int64]float64{1: 0.9, 2: 0.8},
		VehicleProperties:   map[int64]float64{1: 0.7, 2: 0.6},
		ClusterTypes:        map[int64]string{1: "sensorimotor", 2: "sensorimotor"},
	}
	res1 := EvaluateCascadePair(in1, cfg)
	if res1.TypeDiversityBonus == nil {
		t.Errorf("single-type overlap: TypeDiversityBonus pointer must be set when M05 ran (got nil)")
	} else if *res1.TypeDiversityBonus != 0.0 {
		t.Errorf("single-type overlap: bonus value should be 0.0, got %v", *res1.TypeDiversityBonus)
	}
	if res1.SharedTypesCount != 1 {
		t.Errorf("single-type overlap: SharedTypesCount want 1, got %d", res1.SharedTypesCount)
	}

	// Case 2: zero discriminating types ("other" + unknown) → distinct=0.
	in2 := CascadeInputs{
		TopicConcreteness:   &tConc,
		VehicleConcreteness: &vConc,
		TopicProperties:     map[int64]float64{1: 0.9, 2: 0.8},
		VehicleProperties:   map[int64]float64{1: 0.7, 2: 0.6},
		ClusterTypes:        map[int64]string{1: "other", 2: ""},
	}
	res2 := EvaluateCascadePair(in2, cfg)
	if res2.TypeDiversityBonus == nil {
		t.Errorf("zero-discriminating overlap: TypeDiversityBonus pointer must be set when M05 ran (got nil)")
	} else if *res2.TypeDiversityBonus != 0.0 {
		t.Errorf("zero-discriminating overlap: bonus value should be 0.0, got %v", *res2.TypeDiversityBonus)
	}
	if res2.SharedTypesCount != 0 {
		t.Errorf("zero-discriminating overlap: SharedTypesCount want 0, got %d", res2.SharedTypesCount)
	}
}

func TestEvaluateCascadePair_GammaPositiveNoClusterTypesIsZero(t *testing.T) {
	// If ClusterTypes is nil (pre-M05 DB), the bonus is suppressed even
	// with Gamma>0 — the function returns the M03/M04 score unchanged.
	cfg := DefaultCascadeConfig()
	cfg.Gamma = mustGamma(t, 1.0)
	tConc := 3.0
	vConc := 4.5
	in := CascadeInputs{
		TopicConcreteness:   &tConc,
		VehicleConcreteness: &vConc,
		TopicProperties:     map[int64]float64{1: 0.9, 2: 0.8},
		VehicleProperties:   map[int64]float64{1: 0.7, 2: 0.6},
		ClusterTypes:        nil,
	}
	res := EvaluateCascadePair(in, cfg)
	if res.TypeDiversityBonus != nil {
		t.Errorf("nil ClusterTypes: TypeDiversityBonus should be nil, got %v", *res.TypeDiversityBonus)
	}
}

func TestEvaluateCascadePair_EmptyClusterTypes_NoBonus(t *testing.T) {
	// Doc on CascadeInputs.ClusterTypes promises that EvaluateCascadePair
	// "skips the type-diversity bonus computation regardless of Gamma"
	// when ClusterTypes is nil OR empty. A non-nil empty map must
	// short-circuit cleanly: TypeDiversityBonus must stay nil (M05
	// did not evaluate) and the function must not allocate a shared
	// slice for an evaluation it can't perform.
	cfg := DefaultCascadeConfig()
	cfg.Gamma = mustGamma(t, 1.0)
	tConc := 3.0
	vConc := 4.5
	in := CascadeInputs{
		TopicConcreteness:   &tConc,
		VehicleConcreteness: &vConc,
		TopicProperties:     map[int64]float64{1: 0.9, 2: 0.8},
		VehicleProperties:   map[int64]float64{1: 0.7, 2: 0.6},
		ClusterTypes:        map[int64]string{}, // non-nil, empty
	}
	res := EvaluateCascadePair(in, cfg)
	if res.TypeDiversityBonus != nil {
		t.Errorf("empty ClusterTypes: TypeDiversityBonus should be nil (M05 short-circuited), got %v",
			*res.TypeDiversityBonus)
	}
	if res.SharedTypesCount != 0 {
		t.Errorf("empty ClusterTypes: SharedTypesCount should be 0, got %d", res.SharedTypesCount)
	}
}
