package llmlog

import (
	"context"
	"fmt"
	"net/http"
	"net/http/httptest"
	"strings"
	"sync/atomic"
	"testing"

	"github.com/anthropics/anthropic-sdk-go/option"

	"github.com/snailuj/metaforge/internal/llm"
)

const okMessage = `{"id":"msg_9","type":"message","role":"assistant","model":"claude-haiku-5-5",
"content":[{"type":"text","text":"{\"ok\":true}"}],"stop_reason":"end_turn",
"usage":{"input_tokens":100,"output_tokens":200,"cache_read_input_tokens":0,"cache_creation_input_tokens":0}}`

func client(t *testing.T, s *Store, url string) *llm.Anthropic {
	t.Helper()
	return llm.NewAnthropic(
		option.WithBaseURL(url), option.WithAPIKey("sk-secret"),
		option.WithMiddleware(s.Middleware()),
	)
}

func req() llm.Request {
	return llm.Request{Model: "claude-haiku-5-5", System: "sys", User: "user text", Effort: "low",
		Schema: map[string]any{"type": "object"}}
}

func callCtx() context.Context {
	ctx := WithRun(context.Background(), RunInfo{ID: "run-7", Origin: "enrichment", Word: "longing", MaxHops: 3})
	return WithLabel(ctx, "forest_generate")
}

func allCalls(t *testing.T, s *Store) []Call {
	t.Helper()
	rows, err := s.db.Query(`SELECT id FROM llm_calls ORDER BY id`)
	if err != nil {
		t.Fatal(err)
	}
	var ids []int64
	for rows.Next() {
		var id int64
		if err := rows.Scan(&id); err != nil {
			t.Fatal(err)
		}
		ids = append(ids, id)
	}
	rows.Close()
	var out []Call
	for _, id := range ids {
		c, err := s.GetCall(context.Background(), id)
		if err != nil {
			t.Fatal(err)
		}
		out = append(out, c)
	}
	return out
}

func TestMiddlewareRecordsAWholeCall(t *testing.T) {
	s := openTemp(t)
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("request-id", "req_abc")
		w.Header().Set("Content-Type", "application/json")
		fmt.Fprint(w, okMessage)
	}))
	defer srv.Close()

	if _, err := client(t, s, srv.URL).Complete(callCtx(), req()); err != nil {
		t.Fatal(err)
	}
	calls := allCalls(t, s)
	if len(calls) != 1 {
		t.Fatalf("calls = %d, want 1", len(calls))
	}
	c := calls[0]
	if c.RunID != "run-7" || c.Origin != "enrichment" || c.Word != "longing" || c.MaxHops != 3 || c.Label != "forest_generate" {
		t.Errorf("context not recorded: %+v", c)
	}
	if c.Model != "claude-haiku-5-5" || c.HTTPStatus != 200 || c.RequestID != "req_abc" || c.StopReason != "end_turn" || c.MessageID != "msg_9" {
		t.Errorf("response fields wrong: %+v", c)
	}
	if c.Usage.InputTokens != 100 || c.Usage.OutputTokens != 200 || !near(c.CostUSD, (100*0.10+200*0.50)/1e6) || !c.PriceKnown {
		t.Errorf("usage or cost wrong: %+v %v", c.Usage, c.CostUSD)
	}
	if !strings.Contains(string(c.RequestBody), `"user text"`) || string(c.ResponseBody) != okMessage {
		t.Errorf("bodies not kept whole: %s / %s", c.RequestBody, c.ResponseBody)
	}
	if v := c.RequestHeaders["X-Api-Key"]; len(v) != 1 || v[0] != "[redacted]" {
		t.Errorf("api key not redacted: %v", c.RequestHeaders)
	}
	if c.Total <= 0 || c.HeadersAfter > c.Total {
		t.Errorf("timings wrong: headers %v total %v", c.HeadersAfter, c.Total)
	}
}

func TestMiddlewareRecordsEveryRetryAttempt(t *testing.T) {
	s := openTemp(t)
	var n atomic.Int32
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		if n.Add(1) == 1 {
			w.Header().Set("retry-after-ms", "1") // keeps the retry fast
			w.WriteHeader(529)
			fmt.Fprint(w, `{"type":"error","error":{"type":"overloaded_error","message":"Overloaded"}}`)
			return
		}
		fmt.Fprint(w, okMessage)
	}))
	defer srv.Close()

	if _, err := client(t, s, srv.URL).Complete(callCtx(), req()); err != nil {
		t.Fatal(err)
	}
	calls := allCalls(t, s)
	if len(calls) != 2 || calls[0].HTTPStatus != 529 || calls[1].HTTPStatus != 200 {
		t.Fatalf("want a 529 row then a 200 row, got %+v", calls)
	}
	if calls[0].CostUSD != 0 || !strings.Contains(string(calls[0].ResponseBody), "overloaded_error") {
		t.Errorf("failed attempt row wrong: %+v", calls[0])
	}
}

func TestMiddlewareRecordsAStream(t *testing.T) {
	s := openTemp(t)
	stream := "event: message_start\n" +
		`data: {"type":"message_start","message":{"id":"msg_s","type":"message","role":"assistant","model":"claude-haiku-5-5","content":[],"stop_reason":null,"usage":{"input_tokens":40,"output_tokens":1}}}` + "\n\n" +
		"event: content_block_start\n" +
		`data: {"type":"content_block_start","index":0,"content_block":{"type":"text","text":""}}` + "\n\n" +
		"event: content_block_delta\n" +
		`data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"{\"ok\":true}"}}` + "\n\n" +
		"event: content_block_stop\n" + `data: {"type":"content_block_stop","index":0}` + "\n\n" +
		"event: message_delta\n" +
		`data: {"type":"message_delta","delta":{"stop_reason":"end_turn"},"usage":{"output_tokens":90}}` + "\n\n" +
		"event: message_stop\n" + `data: {"type":"message_stop"}` + "\n\n"
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "text/event-stream")
		fmt.Fprint(w, stream)
	}))
	defer srv.Close()

	if _, err := client(t, s, srv.URL).Stream(callCtx(), req(), func(string) {}); err != nil {
		t.Fatal(err)
	}
	calls := allCalls(t, s)
	if len(calls) != 1 {
		t.Fatalf("calls = %d", len(calls))
	}
	c := calls[0]
	if !c.Streamed || c.Usage.InputTokens != 40 || c.Usage.OutputTokens != 90 || c.StopReason != "end_turn" || string(c.ResponseBody) != stream {
		t.Fatalf("stream row wrong: %+v body=%q", c, c.ResponseBody)
	}
	if c.FirstByteAfter <= 0 {
		t.Errorf("first byte time not recorded")
	}
}

func TestMiddlewareRecordsTransportFailure(t *testing.T) {
	s := openTemp(t)
	srv := httptest.NewServer(http.HandlerFunc(func(http.ResponseWriter, *http.Request) {}))
	url := srv.URL
	srv.Close() // nothing listens: every attempt fails to connect

	if _, err := client(t, s, url).Complete(callCtx(), req()); err == nil {
		t.Fatal("want an error")
	}
	calls := allCalls(t, s)
	if len(calls) == 0 {
		t.Fatal("failed attempts were not recorded")
	}
	if calls[0].Error == "" || calls[0].HTTPStatus != 0 || !strings.Contains(string(calls[0].RequestBody), "user text") {
		t.Fatalf("failure row wrong: %+v", calls[0])
	}
}
