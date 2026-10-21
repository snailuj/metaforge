package forest

import (
	"encoding/json"
	"strings"
	"testing"
)

// Rule: each schema constant is a closed object schema, so structured
// output cannot smuggle extra keys past the parser.
func TestSchemasAreClosedObjects(t *testing.T) {
	for name, raw := range map[string]string{
		"generator": generatorSchemaJSON,
		"judge":     judgeSchemaJSON,
	} {
		var schema map[string]any
		if err := json.Unmarshal([]byte(raw), &schema); err != nil {
			t.Fatalf("%s schema is not valid JSON: %v", name, err)
		}
		if schema["type"] != "object" || schema["additionalProperties"] != false {
			t.Errorf("%s schema root is not a closed object: %v", name, schema)
		}
	}
	if GeneratorSchema()["required"] == nil || JudgeSchema()["required"] == nil {
		t.Error("parsed schemas lost their required lists")
	}
}

func TestPromptsAreNonTrivial(t *testing.T) {
	if !strings.HasPrefix(GeneratorSystemPrompt, "You are the Forge.") ||
		!strings.Contains(GeneratorSystemPrompt, "`ground`") ||
		!strings.HasSuffix(GeneratorSystemPrompt, "drop it.") {
		t.Error("generator prompt does not match the spec's opening, backtick terms or ending")
	}
	if !strings.HasPrefix(JudgeSystemPrompt, "You are the Forge Reader:") ||
		!strings.HasSuffix(JudgeSystemPrompt, "at most 10 words, per path.") {
		t.Error("judge prompt does not match the spec's opening or ending")
	}
}

// Rule: structured output writes keys in the schema's property order, so
// the order is part of the prompt. A facet names its word before growing
// branches; a verdict names its path, then reasons, then flags, then scores.
func TestSchemasKeepPropertyOrderWhenMarshalled(t *testing.T) {
	for name, tc := range map[string]struct {
		schema map[string]any
		order  []string
	}{
		"generator facet": {GeneratorSchema(), []string{`"word"`, `"ground"`, `"line"`, `"branches"`}},
		"judge verdict":   {JudgeSchema(), []string{`"index"`, `"reason"`, `"broken_hop"`, `"drift"`, `"literal"`, `"cliche"`, `"score"`}},
	} {
		raw, err := json.Marshal(tc.schema)
		if err != nil {
			t.Fatalf("%s: marshal: %v", name, err)
		}
		s, last := string(raw), -1
		for _, key := range tc.order {
			i := strings.Index(s, key+":")
			if i < last {
				t.Errorf("%s: %s is out of order in %s", name, key, s)
			}
			last = i
		}
	}
}
