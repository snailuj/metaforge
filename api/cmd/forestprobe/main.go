// Command forestprobe runs the metaphor forest pipeline against the live
// model for a list of words and prints every judged path, kept or not, so
// prompts can be tuned by reading what the judge saw and said.
//
//	env -u ANTHROPIC_BASE_URL ANTHROPIC_API_KEY=... go run ./cmd/forestprobe \
//	    -words patience,river -out /tmp/probe
//
// -gen-prompt and -judge-prompt read a system prompt from a file in place
// of the built-in constant, for A/B runs without editing prompts.go.
package main

import (
	"context"
	"encoding/json"
	"flag"
	"fmt"
	"log"
	"os"
	"path/filepath"
	"strings"
	"sync"
	"time"

	"github.com/snailuj/metaforge/internal/forest"
	"github.com/snailuj/metaforge/internal/llm"
)

const callMaxTokens = 16000

// Haiku 5.5 list prices, dollars per million tokens, for the cost column.
const (
	inputPerMTok     = 0.10
	outputPerMTok    = 0.50
	cacheReadPerMTok = 0.01
)

type judged struct {
	Path    forest.Path
	Verdict *forest.Verdict
}

type result struct {
	Word      string
	Generated int
	Invalid   int
	Judged    []judged
	Forest    forest.Forest
	GenMS     int64
	JudgeMS   int64
	Usage     llm.Usage
	Err       error
}

func main() {
	words := flag.String("words", "patience,bureaucracy,river", "comma-separated source words")
	maxHops := flag.Int("max-hops", 3, "max hops per path")
	model := flag.String("model", "claude-haiku-5-5", "generator model")
	judgeModel := flag.String("judge-model", "", "judge model (default: -model)")
	effort := flag.String("effort", "low", "effort for both calls")
	minScore := flag.Int("min-score", 6, "keep threshold")
	genPrompt := flag.String("gen-prompt", "", "file holding a generator system prompt override")
	judgePrompt := flag.String("judge-prompt", "", "file holding a judge system prompt override")
	outDir := flag.String("out", "", "directory for raw JSON per word (optional)")
	parallel := flag.Int("parallel", 3, "words in flight at once")
	flag.Parse()

	if *judgeModel == "" {
		*judgeModel = *model
	}
	genSys := readOr(*genPrompt, forest.GeneratorSystemPrompt)
	judgeSys := readOr(*judgePrompt, forest.JudgeSystemPrompt)
	if *outDir != "" {
		if err := os.MkdirAll(*outDir, 0o755); err != nil {
			log.Fatalf("create out dir: %v", err)
		}
	}

	client := llm.NewAnthropic()
	list := strings.Split(*words, ",")
	results := make([]result, len(list))
	sem := make(chan struct{}, *parallel)
	var wg sync.WaitGroup
	for i, w := range list {
		wg.Add(1)
		go func() {
			defer wg.Done()
			sem <- struct{}{}
			defer func() { <-sem }()
			results[i] = probe(client, strings.TrimSpace(w), *maxHops, *model, *judgeModel, *effort, *minScore, genSys, judgeSys, *outDir)
		}()
	}
	wg.Wait()

	var total llm.Usage
	for _, r := range results {
		report(r, *minScore)
		total.InputTokens += r.Usage.InputTokens
		total.OutputTokens += r.Usage.OutputTokens
		total.CacheReadTokens += r.Usage.CacheReadTokens
	}
	fmt.Printf("\nTOTAL tokens in=%d out=%d cache_read=%d cost=$%.4f over %d words\n",
		total.InputTokens, total.OutputTokens, total.CacheReadTokens, cost(total), len(results))
}

func readOr(path, fallback string) string {
	if path == "" {
		return fallback
	}
	b, err := os.ReadFile(path)
	if err != nil {
		log.Fatalf("read prompt %s: %v", path, err)
	}
	return strings.TrimSpace(string(b))
}

// cost treats uncached input at the base rate; cache writes are ignored
// because the system prompts are a small share of each request.
func cost(u llm.Usage) float64 {
	return (float64(u.InputTokens)*inputPerMTok +
		float64(u.OutputTokens)*outputPerMTok +
		float64(u.CacheReadTokens)*cacheReadPerMTok) / 1e6
}

func probe(c llm.Completer, raw string, maxHops int, model, judgeModel, effort string, minScore int, genSys, judgeSys, outDir string) (r result) {
	ctx, cancel := context.WithTimeout(context.Background(), 3*time.Minute)
	defer cancel()

	word, err := forest.ParseSourceWord(raw)
	r.Word = raw
	if err != nil {
		r.Err = err
		return r
	}
	r.Word = word

	start := time.Now()
	genResp, err := c.Complete(ctx, llm.Request{
		Model: model, System: genSys, User: forest.GeneratorUserMessage(word, maxHops),
		Schema: forest.GeneratorSchema(), Effort: effort, MaxTokens: callMaxTokens,
	})
	r.GenMS = time.Since(start).Milliseconds()
	addUsage(&r.Usage, genResp.Usage)
	if err != nil {
		r.Err = fmt.Errorf("generate: %w", err)
		return r
	}
	save(outDir, word+".gen.json", genResp.Text)
	g, err := forest.ParseGenerated(genResp.Text)
	if err != nil {
		r.Err = err
		return r
	}
	all := forest.Flatten(g)
	valid, invalid := forest.Screen(word, maxHops, all)
	r.Generated, r.Invalid = len(all), invalid

	var verdicts []forest.Verdict
	if len(valid) > 0 {
		start = time.Now()
		judgeResp, err := c.Complete(ctx, llm.Request{
			Model: judgeModel, System: judgeSys, User: forest.JudgeUserMessage(word, valid),
			Schema: forest.JudgeSchema(), Effort: effort, MaxTokens: callMaxTokens,
		})
		r.JudgeMS = time.Since(start).Milliseconds()
		addUsage(&r.Usage, judgeResp.Usage)
		if err != nil {
			r.Err = fmt.Errorf("judge: %w", err)
			return r
		}
		save(outDir, word+".judge.json", judgeResp.Text)
		if verdicts, err = forest.ParseVerdicts(judgeResp.Text); err != nil {
			r.Err = err
			return r
		}
	}

	byIndex := map[int]forest.Verdict{}
	for _, v := range verdicts {
		byIndex[v.Index] = v
	}
	for i, p := range valid {
		j := judged{Path: p}
		if v, ok := byIndex[i+1]; ok {
			j.Verdict = &v
		}
		r.Judged = append(r.Judged, j)
	}
	r.Forest, _ = forest.Build(word, maxHops, minScore, valid, invalid, verdicts)
	if b, err := json.MarshalIndent(r.Forest, "", "  "); err == nil {
		save(outDir, word+".forest.json", string(b))
	}
	return r
}

func addUsage(dst *llm.Usage, u llm.Usage) {
	dst.InputTokens += u.InputTokens
	dst.OutputTokens += u.OutputTokens
	dst.CacheReadTokens += u.CacheReadTokens
}

func save(dir, name, body string) {
	if dir == "" {
		return
	}
	if err := os.WriteFile(filepath.Join(dir, name), []byte(body), 0o644); err != nil {
		log.Printf("save %s: %v", name, err)
	}
}

func report(r result, minScore int) {
	fmt.Printf("\n=== %s ===\n", r.Word)
	if r.Err != nil {
		fmt.Printf("ERROR: %v\n", r.Err)
		return
	}
	s := r.Forest.Stats
	fmt.Printf("gen %dms judge %dms | in=%d out=%d cache_read=%d $%.4f | generated=%d invalid=%d kept=%d rejected=%+v\n",
		r.GenMS, r.JudgeMS, r.Usage.InputTokens, r.Usage.OutputTokens, r.Usage.CacheReadTokens, cost(r.Usage),
		r.Generated, r.Invalid, s.Kept, s.Rejected)
	for _, j := range r.Judged {
		mark, verdict := "  ", "no verdict"
		if v := j.Verdict; v != nil {
			flags := []string{}
			for name, on := range map[string]bool{"broken_hop": v.BrokenHop, "drift": v.Drift, "literal": v.Literal, "cliche": v.Cliche} {
				if on {
					flags = append(flags, name)
				}
			}
			if len(flags) == 0 && v.Score >= minScore {
				mark = "✓ "
			}
			verdict = fmt.Sprintf("%d %v %s", v.Score, flags, v.Reason)
		}
		var chain strings.Builder
		chain.WriteString(r.Word)
		for i, w := range j.Path.Words {
			fmt.Fprintf(&chain, " -[%s]-> %s", j.Path.Grounds[i], w)
		}
		fmt.Printf("%s[%s]\n     %s\n     %q\n", mark, verdict, chain.String(), j.Path.Line)
	}
}
