package llm

import (
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
)

// sseMessage builds a Messages API event stream whose text block arrives in chunks.
func sseMessage(stopReason string, chunks ...string) string {
	var b strings.Builder
	ev := func(name, data string) { fmt.Fprintf(&b, "event: %s\ndata: %s\n\n", name, data) }
	ev("message_start", `{"type":"message_start","message":{"id":"msg_1","type":"message","role":"assistant","model":"claude-haiku-5-5","content":[],"stop_reason":null,"stop_sequence":null,"usage":{"input_tokens":120,"output_tokens":1,"cache_read_input_tokens":30,"cache_creation_input_tokens":0}}}`)
	ev("content_block_start", `{"type":"content_block_start","index":0,"content_block":{"type":"text","text":""}}`)
	for _, c := range chunks {
		q, _ := json.Marshal(c)
		ev("content_block_delta", `{"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":`+string(q)+`}}`)
	}
	ev("content_block_stop", `{"type":"content_block_stop","index":0}`)
	ev("message_delta", `{"type":"message_delta","delta":{"stop_reason":"`+stopReason+`","stop_sequence":null},"usage":{"output_tokens":45}}`)
	ev("message_stop", `{"type":"message_stop"}`)
	return b.String()
}

func serveStream(t *testing.T, body string, captured *map[string]any) *httptest.Server {
	t.Helper()
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		raw, _ := io.ReadAll(r.Body)
		if captured != nil {
			_ = json.Unmarshal(raw, captured)
		}
		w.Header().Set("Content-Type", "text/event-stream")
		_, _ = w.Write([]byte(body))
	}))
	t.Cleanup(srv.Close)
	return srv
}

// Rule: Stream hands over every text chunk in order as it arrives, and its
// Response matches what Complete would return for the same message.
func TestAnthropicStreamDeliversChunksAndFullResponse(t *testing.T) {
	var got map[string]any
	srv := serveStream(t, sseMessage("end_turn", `{"x":`, ` "a`, `b"}`), &got)
	var chunks []string
	resp, err := newTestCompleter(srv).Stream(context.Background(), testRequest(), func(s string) { chunks = append(chunks, s) })
	if err != nil {
		t.Fatalf("Stream: %v", err)
	}
	if strings.Join(chunks, "|") != `{"x":| "a|b"}` {
		t.Errorf("chunks = %q", chunks)
	}
	if resp.Text != `{"x": "ab"}` {
		t.Errorf("Text = %q", resp.Text)
	}
	if resp.Usage.InputTokens != 120 || resp.Usage.OutputTokens != 45 || resp.Usage.CacheReadTokens != 30 {
		t.Errorf("Usage = %+v", resp.Usage)
	}
	if got["stream"] != true {
		t.Errorf("request did not ask for a stream: %v", got["stream"])
	}
	oc, _ := got["output_config"].(map[string]any)
	if oc == nil || oc["effort"] != "medium" {
		t.Errorf("output_config = %v", got["output_config"])
	}
}

// Rule: a streamed response that cannot be trusted as the whole JSON document
// is an error, exactly as for Complete.
func TestAnthropicStreamRejectsUntrustworthyResponses(t *testing.T) {
	for _, stop := range []string{"refusal", "max_tokens"} {
		srv := serveStream(t, sseMessage(stop, `{"x":`), nil)
		if _, err := newTestCompleter(srv).Stream(context.Background(), testRequest(), func(string) {}); err == nil {
			t.Errorf("%s: want error", stop)
		}
	}
	srv := serveStream(t, sseMessage("end_turn"), nil)
	if _, err := newTestCompleter(srv).Stream(context.Background(), testRequest(), func(string) {}); err == nil {
		t.Errorf("no text: want error")
	}
}

func TestAnthropicStreamHTTPErrorIsReturned(t *testing.T) {
	srv := serve(t, 529, `{"type":"error","error":{"type":"overloaded_error","message":"busy"}}`, nil)
	if _, err := newTestCompleter(srv).Stream(context.Background(), testRequest(), func(string) {}); err == nil {
		t.Fatal("want error")
	}
}
