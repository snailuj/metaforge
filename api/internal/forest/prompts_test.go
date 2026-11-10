package forest

import (
	"encoding/json"
	"os"
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

// specBlock returns the fenced block that follows heading in the spec.
func specBlock(t *testing.T, spec, heading string) string {
	t.Helper()
	_, after, ok := strings.Cut(spec, heading+"\n\n```\n")
	if !ok {
		t.Fatalf("spec has no %q block", heading)
	}
	block, _, ok := strings.Cut(after, "\n```\n")
	if !ok {
		t.Fatalf("spec block under %q is not closed", heading)
	}
	return block
}

// Rule: the prompts in prompts.go are the prompts in the spec, so a reader of
// the spec sees what the models are told.
func TestPromptsMatchTheSpec(t *testing.T) {
	raw, err := os.ReadFile("../../../docs/plans/2026-10-21-metaphor-forest.md")
	if err != nil {
		t.Fatalf("read spec: %v", err)
	}
	spec := string(raw)
	if got := specBlock(t, spec, "### Generator system prompt"); got != GeneratorSystemPrompt {
		t.Errorf("generator prompt differs from the spec:\nspec: %q\ncode: %q", got, GeneratorSystemPrompt)
	}
	if got := specBlock(t, spec, "### Judge system prompt"); got != JudgeSystemPrompt {
		t.Errorf("judge prompt differs from the spec:\nspec: %q\ncode: %q", got, JudgeSystemPrompt)
	}
}

// Rule: the line continues an unstated "SOURCE is ENDPOINT", and the judge
// reads it that way.
func TestPromptsDescribeALineThatFollowsTheMetaphor(t *testing.T) {
	for _, want := range []string{
		`The reader already sees "SOURCE is ENDPOINT", so write ` + "`line`" + ` as what follows it: at most 16 words a writer could lift into prose, showing SOURCE as the endpoint. Do not open the line with SOURCE, the endpoint or "SOURCE is ENDPOINT", and start it with a capital letter.`,
	} {
		if !strings.Contains(GeneratorSystemPrompt, want) {
			t.Errorf("generator prompt lacks %q", want)
		}
	}
	for _, want := range []string{
		`then a line a writer might use. The line follows an unstated "SOURCE is ENDPOINT", so read it as continuing that sentence.`,
		`or the line, read after "SOURCE is ENDPOINT", swaps source and endpoint.`,
	} {
		if !strings.Contains(JudgeSystemPrompt, want) {
			t.Errorf("judge prompt lacks %q", want)
		}
	}
}
