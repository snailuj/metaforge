package llm

import (
	"context"
	"fmt"
	"strings"

	"github.com/anthropics/anthropic-sdk-go"
	"github.com/anthropics/anthropic-sdk-go/option"
)

// defaultMaxTokens leaves headroom for the adaptive thinking Haiku 5.5
// runs by default, which counts against max_tokens.
const defaultMaxTokens = 16000

// Anthropic implements Completer on the official SDK.
type Anthropic struct {
	client anthropic.Client
}

// NewAnthropic builds a client. With no options the SDK reads
// ANTHROPIC_API_KEY and ANTHROPIC_BASE_URL from the environment.
func NewAnthropic(opts ...option.RequestOption) *Anthropic {
	return &Anthropic{client: anthropic.NewClient(opts...)}
}

// Complete sends a non-streaming request. It sets no temperature, top_p,
// top_k or thinking: claude-haiku-5-5 rejects non-default sampling values
// with a 400. API errors are returned wrapped, so callers can recover the
// *anthropic.Error with errors.As.
func (a *Anthropic) Complete(ctx context.Context, req Request) (Response, error) {
	maxTokens := req.MaxTokens
	if maxTokens <= 0 {
		maxTokens = defaultMaxTokens
	}

	msg, err := a.client.Messages.New(ctx, anthropic.MessageNewParams{
		Model:     anthropic.Model(req.Model),
		MaxTokens: maxTokens,
		System: []anthropic.TextBlockParam{{
			Text:         req.System,
			CacheControl: anthropic.NewCacheControlEphemeralParam(),
		}},
		Messages: []anthropic.MessageParam{
			anthropic.NewUserMessage(anthropic.NewTextBlock(req.User)),
		},
		OutputConfig: anthropic.OutputConfigParam{
			Effort: anthropic.OutputConfigEffort(req.Effort),
			Format: anthropic.JSONOutputFormatParam{Schema: req.Schema},
		},
	})
	if err != nil {
		return Response{}, fmt.Errorf("anthropic messages: %w", err)
	}

	resp := Response{
		StopReason: string(msg.StopReason),
		Usage: Usage{
			InputTokens:     msg.Usage.InputTokens,
			OutputTokens:    msg.Usage.OutputTokens,
			CacheReadTokens: msg.Usage.CacheReadInputTokens,
		},
	}

	switch msg.StopReason {
	case anthropic.StopReasonRefusal:
		return resp, fmt.Errorf("model refused the request (stop_reason=refusal)")
	case anthropic.StopReasonMaxTokens:
		return resp, fmt.Errorf("output truncated (stop_reason=max_tokens after %d tokens)", msg.Usage.OutputTokens)
	}

	for _, block := range msg.Content {
		if tb, ok := block.AsAny().(anthropic.TextBlock); ok && strings.TrimSpace(tb.Text) != "" {
			resp.Text = tb.Text
			return resp, nil
		}
	}
	return resp, fmt.Errorf("response held no text block with JSON (stop_reason=%s)", msg.StopReason)
}
