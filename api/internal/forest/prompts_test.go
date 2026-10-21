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
