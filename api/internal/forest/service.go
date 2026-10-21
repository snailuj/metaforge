package forest

import (
	"context"
	"errors"
	"fmt"
	"log/slog"
	"time"

	"github.com/snailuj/metaforge/internal/llm"
	"github.com/snailuj/metaforge/internal/observe"
)

// callMaxTokens leaves room for the adaptive thinking Haiku 5.5 runs by
// default; both calls are non-streaming.
const callMaxTokens = 16000

// Config selects models and the quality gate.
type Config struct {
	Model      string
	JudgeModel string
	Effort     string
	MinScore   int
}

// Service runs the generate, judge, build pipeline.
type Service struct {
	llm    llm.Completer
	cfg    Config
	Logger *slog.Logger // defaults to slog.Default()
}

func NewService(c llm.Completer, cfg Config) *Service {
	return &Service{llm: c, cfg: cfg, Logger: slog.Default()}
}

// callRecord is what the per-request log line reports for one LLM call.
type callRecord struct {
	latency time.Duration
	usage   llm.Usage
}

func (c callRecord) attrs(prefix string) []any {
	return []any{
		prefix + "_latency_ms", c.latency.Milliseconds(),
		prefix + "_input_tokens", c.usage.InputTokens,
		prefix + "_output_tokens", c.usage.OutputTokens,
		prefix + "_cache_read_tokens", c.usage.CacheReadTokens,
	}
}

// Generate grows a forest for source. It returns an error, wrapping the
// cause so callers can match context.DeadlineExceeded, when either call
// fails or returns output that cannot be used. It logs one summary line
// per request, success or failure.
func (s *Service) Generate(ctx context.Context, source string, maxHops int) (forest Forest, err error) {
	var gen, judge callRecord
	var judgeRan bool
	defer func() {
		attrs := []any{
			"word", source, "max_hops", maxHops,
			"model", s.cfg.Model, "judge_model", s.cfg.JudgeModel,
		}
		attrs = append(attrs, gen.attrs("gen")...)
		attrs = append(attrs, judge.attrs("judge")...)
		attrs = append(attrs, "judge_ran", judgeRan)
		if errors.Is(err, context.Canceled) {
			// The client went away; nothing failed on our side.
			s.Logger.Info("forest request", append(attrs, "outcome", "canceled", "error", err.Error())...)
			return
		}
		if err != nil {
			s.Logger.Error("forest request", append(attrs, "outcome", "error", "error", err.Error())...)
			return
		}
		r := forest.Stats.Rejected
		attrs = append(attrs,
			"generated", forest.Stats.Generated, "kept", forest.Stats.Kept,
			"rejected_invalid", r.Invalid, "rejected_low_score", r.LowScore,
			"rejected_broken_hop", r.BrokenHop, "rejected_drift", r.Drift,
			"rejected_cliche", r.Cliche, "rejected_literal", r.Literal,
			"outcome", "ok")
		s.Logger.Info("forest request", attrs...)
	}()

	genResp, err := s.call(ctx, "forest_generate", &gen, llm.Request{
		Model:     s.cfg.Model,
		System:    GeneratorSystemPrompt,
		User:      GeneratorUserMessage(source, maxHops),
		Schema:    GeneratorSchema(),
		Effort:    s.cfg.Effort,
		MaxTokens: callMaxTokens,
	})
	if err != nil {
		return Forest{}, fmt.Errorf("generate: %w", err)
	}
	generated, err := ParseGenerated(genResp.Text)
	if err != nil {
		return Forest{}, fmt.Errorf("generate: %w", err)
	}

	valid, invalid := Screen(source, maxHops, Flatten(generated))

	var verdicts []Verdict
	if len(valid) > 0 {
		judgeResp, err := s.call(ctx, "forest_judge", &judge, llm.Request{
			Model:     s.cfg.JudgeModel,
			System:    JudgeSystemPrompt,
			User:      JudgeUserMessage(source, valid),
			Schema:    JudgeSchema(),
			Effort:    s.cfg.Effort,
			MaxTokens: callMaxTokens,
		})
		judgeRan = true
		if err != nil {
			return Forest{}, fmt.Errorf("judge: %w", err)
		}
		if verdicts, err = ParseVerdicts(judgeResp.Text); err != nil {
			return Forest{}, fmt.Errorf("judge: %w", err)
		}
	}

	forest, ignored := Build(source, maxHops, s.cfg.MinScore, valid, invalid, verdicts)
	forest.Model = s.cfg.Model
	for _, idx := range ignored {
		s.Logger.Warn("forest: judge verdict ignored", "word", source, "index", idx, "paths_judged", len(valid))
	}
	return forest, nil
}

// call times one LLM call twice over: into rec for the request log line, and
// through observe, which stays a no-op unless timing is switched on.
func (s *Service) call(ctx context.Context, label string, rec *callRecord, req llm.Request) (llm.Response, error) {
	stop := observe.Start(label)
	start := time.Now()
	resp, err := s.llm.Complete(ctx, req)
	rec.latency, rec.usage = time.Since(start), resp.Usage
	stop("model", req.Model, "input_tokens", resp.Usage.InputTokens,
		"output_tokens", resp.Usage.OutputTokens, "cache_read_tokens", resp.Usage.CacheReadTokens)
	return resp, err
}
