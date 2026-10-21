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

// params builds the request. It sets no temperature, top_p, top_k or
// thinking: claude-haiku-5-5 rejects non-default sampling values with a 400.
func params(req Request) anthropic.MessageNewParams {
	maxTokens := req.MaxTokens
	if maxTokens <= 0 {
		maxTokens = defaultMaxTokens
	}
	return anthropic.MessageNewParams{
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
	}
}

// Complete sends a non-streaming request. API errors are returned wrapped,
// so callers can recover the *anthropic.Error with errors.As.
func (a *Anthropic) Complete(ctx context.Context, req Request) (Response, error) {
	msg, err := a.client.Messages.New(ctx, params(req))
	if err != nil {
		return Response{}, fmt.Errorf("anthropic messages: %w", err)
	}
	return result(msg)
}

// Stream sends a streaming request and calls onText with each text chunk as
// it arrives. The Response and its errors are the same as Complete's, so a
// caller must still treat chunks as provisional until Stream returns nil.
func (a *Anthropic) Stream(ctx context.Context, req Request, onText func(string)) (Response, error) {
	stream := a.client.Messages.NewStreaming(ctx, params(req))
	defer stream.Close()
	var msg anthropic.Message
	for stream.Next() {
		ev := stream.Current()
		if err := msg.Accumulate(ev); err != nil {
			return Response{}, fmt.Errorf("anthropic stream: %w", err)
		}
		if d, ok := ev.AsAny().(anthropic.ContentBlockDeltaEvent); ok {
			if t, ok := d.Delta.AsAny().(anthropic.TextDelta); ok && t.Text != "" {
				onText(t.Text)
			}
		}
	}
	if err := stream.Err(); err != nil {
		return Response{}, fmt.Errorf("anthropic stream: %w", err)
	}
	return result(&msg)
}

// result checks a finished message and extracts its JSON text.
func result(msg *anthropic.Message) (Response, error) {
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
