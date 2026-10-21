package forest

import (
	"regexp"
	"testing"
)

// Rule: the fingerprint names everything that shapes a forest, so a cached
// forest is served only to the configuration that made it.
func TestFingerprintTracksEveryConfigField(t *testing.T) {
	base := Config{Model: "m", JudgeModel: "j", Effort: "low", MinScore: 6, MinPaths: 3}
	fp := Fingerprint(base)
	if !regexp.MustCompile(`^[0-9a-f]{16}$`).MatchString(fp) {
		t.Fatalf("fingerprint %q is not 16 hex characters", fp)
	}
	if Fingerprint(base) != fp {
		t.Error("fingerprint is not stable for an equal config")
	}
	for name, c := range map[string]Config{
		"model":       {Model: "m2", JudgeModel: "j", Effort: "low", MinScore: 6, MinPaths: 3},
		"judge model": {Model: "m", JudgeModel: "j2", Effort: "low", MinScore: 6, MinPaths: 3},
		"effort":      {Model: "m", JudgeModel: "j", Effort: "medium", MinScore: 6, MinPaths: 3},
		"min score":   {Model: "m", JudgeModel: "j", Effort: "low", MinScore: 7, MinPaths: 3},
		"min paths":   {Model: "m", JudgeModel: "j", Effort: "low", MinScore: 6, MinPaths: 0},
	} {
		if Fingerprint(c) == fp {
			t.Errorf("changing %s left the fingerprint unchanged", name)
		}
	}
}
