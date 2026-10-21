package llm

import (
	"context"
	"encoding/json"
	"errors"
	"io"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"github.com/anthropics/anthropic-sdk-go"
	"github.com/anthropics/anthropic-sdk-go/option"
)

var testSchema = map[string]any{
	"type":                 "object",
	"additionalProperties": false,
	"required":             []any{"x"},
	"properties":           map[string]any{"x": map[string]any{"type": "string"}},
}

func testRequest() Request {
	return Request{
		Model:     "claude-haiku-5-5",
		System:    "You are the Forge.",
		User:      "SOURCE: patience",
		Schema:    testSchema,
		Effort:    "medium",
		MaxTokens: 16000,
	}
}

// messageJSON builds a Messages API response body.
func messageJSON(stopReason string, content string) string {
	return `{"id":"msg_1","type":"message","role":"assistant","model":"claude-haiku-5-5",` +
		`"content":` + content + `,"stop_reason":"` + stopReason + `","stop_sequence":null,` +
		`"usage":{"input_tokens":120,"output_tokens":45,"cache_read_input_tokens":30,"cache_creation_input_tokens":0}}`
}

// newTestCompleter points the SDK at srv explicitly: the container sets
// ANTHROPIC_BASE_URL, so nothing here may rely on ambient environment.
func newTestCompleter(srv *httptest.Server) *Anthropic {
	return NewAnthropic(
		option.WithBaseURL(srv.URL),
		option.WithAPIKey("test"),
		option.WithMaxRetries(0),
	)
}

func serve(t *testing.T, status int, body string, captured *map[string]any) *httptest.Server {
	t.Helper()
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		raw, _ := io.ReadAll(r.Body)
		if captured != nil {
			if err := json.Unmarshal(raw, captured); err != nil {
				t.Errorf("request body is not JSON: %v", err)
			}
		}
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(status)
		_, _ = w.Write([]byte(body))
	}))
	t.Cleanup(srv.Close)
	return srv
}

func TestAnthropicCompleteRequestShape(t *testing.T) {
	var got map[string]any
	srv := serve(t, 200, messageJSON("end_turn", `[{"type":"text","text":"{\"x\":\"y\"}"}]`), &got)

	resp, err := newTestCompleter(srv).Complete(context.Background(), testRequest())
	if err != nil {
		t.Fatalf("Complete: %v", err)
	}

	if got["model"] != "claude-haiku-5-5" {
		t.Errorf("model = %v", got["model"])
	}
	if got["max_tokens"] != float64(16000) {
		t.Errorf("max_tokens = %v", got["max_tokens"])
	}
	oc, _ := got["output_config"].(map[string]any)
	if oc["effort"] != "medium" {
		t.Errorf("output_config.effort = %v", oc["effort"])
	}
	format, _ := oc["format"].(map[string]any)
	if format["type"] != "json_schema" {
		t.Errorf("output_config.format.type = %v", format["type"])
	}
	schema, _ := format["schema"].(map[string]any)
	if schema["type"] != "object" || schema["additionalProperties"] != false {
		t.Errorf("output_config.format.schema = %v", schema)
	}

	system, _ := got["system"].([]any)
	if len(system) != 1 {
		t.Fatalf("system blocks = %v", got["system"])
	}
	block, _ := system[0].(map[string]any)
	if block["text"] != "You are the Forge." {
		t.Errorf("system text = %v", block["text"])
	}
	cc, _ := block["cache_control"].(map[string]any)
	if cc["type"] != "ephemeral" {
		t.Errorf("system cache_control = %v", block["cache_control"])
	}

	// Non-default sampling params return 400 on claude-haiku-5-5, and
	// Haiku 5.5 runs adaptive thinking by default.
	for _, key := range []string{"temperature", "top_p", "top_k", "thinking", "stream"} {
		if _, present := got[key]; present {
			t.Errorf("request must not carry %q", key)
		}
	}

	msgs, _ := got["messages"].([]any)
	if len(msgs) != 1 {
		t.Fatalf("messages = %v", got["messages"])
	}

	if resp.Text != `{"x":"y"}` {
		t.Errorf("Text = %q", resp.Text)
	}
	if resp.Usage != (Usage{InputTokens: 120, OutputTokens: 45, CacheReadTokens: 30}) {
		t.Errorf("Usage = %+v", resp.Usage)
	}
	if resp.StopReason != "end_turn" {
		t.Errorf("StopReason = %q", resp.StopReason)
	}
}

func TestAnthropicCompleteDefaultsMaxTokens(t *testing.T) {
	var got map[string]any
	srv := serve(t, 200, messageJSON("end_turn", `[{"type":"text","text":"{}"}]`), &got)
	req := testRequest()
	req.MaxTokens = 0

	if _, err := newTestCompleter(srv).Complete(context.Background(), req); err != nil {
		t.Fatalf("Complete: %v", err)
	}
	if got["max_tokens"] != float64(16000) {
		t.Errorf("max_tokens = %v, want the 16000 default", got["max_tokens"])
	}
}

func TestAnthropicCompleteSkipsNonTextBlocks(t *testing.T) {
	content := `[{"type":"thinking","thinking":"hm","signature":"s"},{"type":"text","text":"{\"x\":\"y\"}"}]`
	srv := serve(t, 200, messageJSON("end_turn", content), nil)

	resp, err := newTestCompleter(srv).Complete(context.Background(), testRequest())
	if err != nil {
		t.Fatalf("Complete: %v", err)
	}
	if resp.Text != `{"x":"y"}` {
		t.Errorf("Text = %q", resp.Text)
	}
}

// Rule: a response that cannot be trusted as the full JSON document is
// an error, whatever else it carries.
func TestAnthropicCompleteRejectsUntrustworthyResponses(t *testing.T) {
	textBlock := `[{"type":"text","text":"{\"x\":\"y\"}"}]`
	cases := []struct {
		name       string
		stopReason string
		content    string
		wantErr    string
	}{
		{"refusal", "refusal", textBlock, "refus"},
		{"max_tokens", "max_tokens", textBlock, "max_tokens"},
		{"no content", "end_turn", `[]`, "no text"},
		{"only thinking", "end_turn", `[{"type":"thinking","thinking":"hm","signature":"s"}]`, "no text"},
		{"empty text", "end_turn", `[{"type":"text","text":"  "}]`, "no text"},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			srv := serve(t, 200, messageJSON(tc.stopReason, tc.content), nil)

			_, err := newTestCompleter(srv).Complete(context.Background(), testRequest())
			if err == nil {
				t.Fatal("expected an error")
			}
			if !strings.Contains(err.Error(), tc.wantErr) {
				t.Errorf("error %q does not mention %q", err, tc.wantErr)
			}
		})
	}
}

func TestAnthropicCompleteHTTPErrorKeepsStatus(t *testing.T) {
	body := `{"type":"error","error":{"type":"invalid_request_error","message":"bad effort"}}`
	srv := serve(t, 400, body, nil)

	_, err := newTestCompleter(srv).Complete(context.Background(), testRequest())
	if err == nil {
		t.Fatal("expected an error")
	}
	var apierr *anthropic.Error
	if !errors.As(err, &apierr) {
		t.Fatalf("error %v does not wrap *anthropic.Error", err)
	}
	if apierr.StatusCode != 400 {
		t.Errorf("StatusCode = %d", apierr.StatusCode)
	}
}

func TestAnthropicCompleteHonoursContextCancellation(t *testing.T) {
	srv := serve(t, 200, messageJSON("end_turn", `[{"type":"text","text":"{}"}]`), nil)
	ctx, cancel := context.WithCancel(context.Background())
	cancel()

	_, err := newTestCompleter(srv).Complete(ctx, testRequest())
	if !errors.Is(err, context.Canceled) {
		t.Errorf("error = %v, want context.Canceled", err)
	}
}
