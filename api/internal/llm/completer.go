// Package llm abstracts the language-model call behind a small interface so
// callers can be tested against a fake.
package llm

import "context"

// Request is one structured-output completion.
type Request struct {
	Model     string
	System    string
	User      string
	Schema    map[string]any // JSON schema the response must satisfy
	Effort    string         // low | medium | high | xhigh | max
	MaxTokens int64          // zero means the implementation default
}

// Usage is the token accounting of one call.
type Usage struct {
	InputTokens     int64
	OutputTokens    int64
	CacheReadTokens int64
}

// Response carries the JSON document the model produced.
type Response struct {
	Text       string
	Usage      Usage
	StopReason string
}

// Completer returns an error rather than a partial Response whenever the
// output cannot be trusted as the full JSON document (refusal, truncation,
// missing text).
type Completer interface {
	Complete(ctx context.Context, req Request) (Response, error)
}

// Streamer is a Completer that can also hand over text as it is generated.
type Streamer interface {
	Completer
	Stream(ctx context.Context, req Request, onText func(string)) (Response, error)
}
