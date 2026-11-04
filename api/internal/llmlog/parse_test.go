package llmlog

import "testing"

func TestParseJSONResponse(t *testing.T) {
	body := []byte(`{"id":"msg_1","type":"message","model":"claude-haiku-5-5","stop_reason":"end_turn",
		"usage":{"input_tokens":120,"output_tokens":340,"cache_read_input_tokens":2000,"cache_creation_input_tokens":0}}`)
	got := parseResponse(body, false)
	want := parsed{Model: "claude-haiku-5-5", StopReason: "end_turn", MessageID: "msg_1",
		Usage: Usage{InputTokens: 120, OutputTokens: 340, CacheReadTokens: 2000}}
	if got != want {
		t.Fatalf("got %+v, want %+v", got, want)
	}
}

// A stream reports input usage in message_start and the running output
// total in each message_delta; the last delta is the bill.
func TestParseStreamResponse(t *testing.T) {
	body := []byte("event: message_start\n" +
		`data: {"type":"message_start","message":{"id":"msg_2","model":"claude-haiku-5-5","usage":{"input_tokens":50,"output_tokens":1,"cache_read_input_tokens":900,"cache_creation_input_tokens":10}}}` + "\n\n" +
		"event: content_block_delta\n" +
		`data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"{\"a\":"}}` + "\n\n" +
		"event: message_delta\n" +
		`data: {"type":"message_delta","delta":{"stop_reason":"end_turn"},"usage":{"output_tokens":700}}` + "\n\n" +
		"event: message_stop\n" + `data: {"type":"message_stop"}` + "\n\n")
	got := parseResponse(body, true)
	want := parsed{Model: "claude-haiku-5-5", StopReason: "end_turn", MessageID: "msg_2",
		Usage: Usage{InputTokens: 50, OutputTokens: 700, CacheReadTokens: 900, CacheWriteTokens: 10}}
	if got != want {
		t.Fatalf("got %+v, want %+v", got, want)
	}
}

func TestParseErrorBodyYieldsNoUsage(t *testing.T) {
	got := parseResponse([]byte(`{"type":"error","error":{"type":"overloaded_error","message":"Overloaded"}}`), false)
	if got != (parsed{}) {
		t.Fatalf("got %+v, want zero", got)
	}
}

func TestParseRequest(t *testing.T) {
	got := parseRequestModel([]byte(`{"model":"claude-haiku-5-5","max_tokens":16000,"stream":true}`))
	if got.Model != "claude-haiku-5-5" || !got.Stream {
		t.Fatalf("got %+v", got)
	}
}
