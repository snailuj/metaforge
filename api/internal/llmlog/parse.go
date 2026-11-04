package llmlog

import (
	"bufio"
	"bytes"
	"encoding/json"
)

// parsed is what a row keeps, as columns, from a response body. The body
// itself is kept whole, so anything not lifted here can be read later.
type parsed struct {
	Model      string
	StopReason string
	MessageID  string
	Usage      Usage
	// Complete is false for a body cut short: a stream with no final
	// message_delta, or JSON that does not decode. Its usage under-counts.
	Complete bool
}

type wireMessage struct {
	ID         string `json:"id"`
	Model      string `json:"model"`
	StopReason string `json:"stop_reason"`
	Usage      *Usage `json:"usage"`
}

// parseResponse lifts model, stop reason and usage from a Messages API
// body: one JSON message, or a server-sent event stream. Anything it cannot
// read leaves the zero value; it never fails, since the raw body is kept.
func parseResponse(body []byte, stream bool) parsed {
	if !stream {
		var m wireMessage
		if json.Unmarshal(body, &m) != nil || m.Usage == nil {
			return parsed{}
		}
		return parsed{Model: m.Model, StopReason: m.StopReason, MessageID: m.ID, Usage: *m.Usage, Complete: true}
	}

	var p parsed
	sc := bufio.NewScanner(bytes.NewReader(body))
	sc.Buffer(make([]byte, 64*1024), len(body)+1)
	for sc.Scan() {
		line, ok := bytes.CutPrefix(sc.Bytes(), []byte("data:"))
		if !ok {
			continue
		}
		var ev struct {
			Type    string      `json:"type"`
			Message wireMessage `json:"message"`
			Delta   struct {
				StopReason string `json:"stop_reason"`
			} `json:"delta"`
			Usage *Usage `json:"usage"`
		}
		if json.Unmarshal(bytes.TrimSpace(line), &ev) != nil {
			continue
		}
		switch ev.Type {
		case "message_start":
			p.Model, p.MessageID = ev.Message.Model, ev.Message.ID
			if ev.Message.Usage != nil {
				p.Usage = *ev.Message.Usage
			}
		case "message_delta":
			if ev.Delta.StopReason != "" {
				p.StopReason = ev.Delta.StopReason
				p.Complete = true
			}
			// output_tokens in a delta is cumulative; input fields, when
			// present, restate the total.
			if u := ev.Usage; u != nil {
				p.Usage.OutputTokens = u.OutputTokens
				p.Usage.InputTokens = max(p.Usage.InputTokens, u.InputTokens)
				p.Usage.CacheReadTokens = max(p.Usage.CacheReadTokens, u.CacheReadTokens)
				p.Usage.CacheWriteTokens = max(p.Usage.CacheWriteTokens, u.CacheWriteTokens)
			}
		}
	}
	return p
}

type requestFields struct {
	Model     string `json:"model"`
	Stream    bool   `json:"stream"`
	MaxTokens int64  `json:"max_tokens"`
}

// parseRequestModel reads the model and stream flag from a request body.
func parseRequestModel(body []byte) requestFields {
	var r requestFields
	_ = json.Unmarshal(body, &r) // a body it cannot read is still stored raw
	return r
}
