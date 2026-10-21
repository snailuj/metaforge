package forest

import (
	"crypto/sha256"
	"encoding/hex"
	"fmt"
)

// pipelineRevision covers what the fingerprint cannot see: code that changes
// what the models are shown or how verdicts become a forest (the judge
// message format, path validation, Build). Bump it with such a change so
// cached forests from the old pipeline stop being served.
const pipelineRevision = "2026-10-21.1"

// Fingerprint identifies the pipeline that makes a forest: prompts, output
// schemas, models, effort, gates and pipelineRevision. Forest caches key on
// it, so retuning any of these starts fresh pools.
func Fingerprint(cfg Config) string {
	h := sha256.New()
	for _, part := range []string{
		pipelineRevision,
		GeneratorSystemPrompt, generatorSchemaJSON,
		JudgeSystemPrompt, judgeSchemaJSON,
		fmt.Sprintf("%+v", cfg),
	} {
		// Length-prefix each part so no two splits hash alike.
		fmt.Fprintf(h, "%d:%s", len(part), part)
	}
	return hex.EncodeToString(h.Sum(nil))[:16]
}
