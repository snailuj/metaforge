package llmlog

import (
	"bytes"
	"context"
	"io"
	"log/slog"
	"net/http"
	"net/http/httptrace"
	"strings"
	"sync"
	"sync/atomic"
	"time"

	"github.com/anthropics/anthropic-sdk-go/option"
)

// maxKeptBody bounds what one row holds of a response body; a forest
// answer is tens of kilobytes, so only a runaway stream hits it.
const maxKeptBody = 16 << 20

// recordTimeout bounds writing a row after the caller may have gone.
const recordTimeout = 5 * time.Second

// RunInfo ties model calls to the forest request that made them.
type RunInfo struct {
	ID, Origin, Word string
	MaxHops          int
}

type runKey struct{}
type labelKey struct{}

func WithRun(ctx context.Context, r RunInfo) context.Context {
	return context.WithValue(ctx, runKey{}, r)
}

// RunFrom returns the run set by WithRun, if any.
func RunFrom(ctx context.Context) (RunInfo, bool) {
	r, ok := ctx.Value(runKey{}).(RunInfo)
	return r, ok
}

// WithLabel names the step a call serves, such as forest_generate.
func WithLabel(ctx context.Context, label string) context.Context {
	return context.WithValue(ctx, labelKey{}, label)
}

// secretHeaders are replaced before a request's headers are stored.
var secretHeaders = []string{"X-Api-Key", "Authorization"}

// Middleware records every HTTP attempt the SDK makes, retries included,
// as one row. Recording never changes or fails the call: a row that cannot
// be written is logged and dropped.
func (s *Store) Middleware() option.Middleware {
	return func(req *http.Request, next option.MiddlewareNext) (*http.Response, error) {
		c := Call{Started: time.Now(), Method: req.Method, URL: req.URL.String()}
		if r, ok := RunFrom(req.Context()); ok {
			c.RunID, c.Origin, c.Word, c.MaxHops = r.ID, r.Origin, r.Word, r.MaxHops
		}
		c.Label, _ = req.Context().Value(labelKey{}).(string)
		c.RequestHeaders = redact(req.Header)

		if req.Body != nil {
			body, err := io.ReadAll(req.Body)
			req.Body.Close()
			if err != nil {
				slog.Error("llm call log: could not read request body", "err", err)
			}
			c.RequestBody = body
			req.Body = io.NopCloser(bytes.NewReader(body))
		}
		rf := parseRequestModel(c.RequestBody)
		c.Model, c.Streamed = rf.Model, rf.Stream
		maxTokens := rf.MaxTokens

		// Whether a request byte left decides if a failed call may be billed;
		// the error alone cannot say (a cancel or TLS failure looks the same
		// before and after sending).
		var sent atomic.Bool
		req = req.WithContext(httptrace.WithClientTrace(req.Context(), &httptrace.ClientTrace{
			WroteHeaders: func() { sent.Store(true) },
		}))
		resp, err := next(req)
		c.HeadersAfter = time.Since(c.Started)
		if err != nil {
			c.Error = err.Error()
			c.Total = c.HeadersAfter
			if !sent.Load() {
				c.PriceKnown = true // nothing was billed
			} else {
				// It may have reached the API, which bills a call the client
				// gave up on; whether it did is unknowable, so assume so.
				chargeCeiling(&c, maxTokens)
				c.CostUSD, c.PriceKnown = Cost(c.Model, c.Usage)
			}
			s.record(req.Context(), c)
			return resp, err
		}
		c.HTTPStatus = resp.StatusCode
		c.RequestID = resp.Header.Get("request-id")
		c.ResponseHeaders = resp.Header.Clone()
		resp.Body = &teeBody{rc: resp.Body, call: c, store: s, ctx: req.Context(), maxTokens: maxTokens}
		return resp, nil
	}
}

// chargeCeiling bills a call whose usage is unknown or under-reported at the
// most it could have cost: every output token allowed, and at least one
// input token per request byte.
func chargeCeiling(c *Call, maxTokens int64) {
	c.StopReason = "incomplete"
	c.Usage.OutputTokens = max(c.Usage.OutputTokens, maxTokens)
	c.Usage.InputTokens = max(c.Usage.InputTokens, int64(len(c.RequestBody)))
	slog.Warn("llm call log: usage unknown, charged at its ceiling", "run_id", c.RunID,
		"label", c.Label, "output_tokens", c.Usage.OutputTokens, "input_tokens", c.Usage.InputTokens)
}

func redact(h http.Header) map[string][]string {
	out := h.Clone()
	for _, k := range secretHeaders {
		if _, ok := out[k]; ok {
			out[k] = []string{"[redacted]"}
		}
	}
	return out
}

// teeBody keeps what the SDK reads and writes the row when it closes the
// body, which it always does, on success, error or cancellation.
type teeBody struct {
	rc    io.ReadCloser
	buf   bytes.Buffer
	n     int64
	call  Call
	store *Store
	ctx   context.Context
	once  sync.Once
	rerr  error
	// maxTokens is the request's output ceiling, used to bound the bill of
	// a response cut short.
	maxTokens int64
}

func (t *teeBody) Read(p []byte) (int, error) {
	n, err := t.rc.Read(p)
	if n > 0 {
		if t.n == 0 {
			t.call.FirstByteAfter = time.Since(t.call.Started)
		}
		t.n += int64(n)
		if room := maxKeptBody - t.buf.Len(); room > 0 {
			t.buf.Write(p[:min(n, room)])
		}
	}
	if err != nil && err != io.EOF {
		t.rerr = err
	}
	return n, err
}

func (t *teeBody) Close() error {
	// The SDK closes an error body before a retry without reading it. It is
	// small and says why the attempt failed, so read it in. A 200 body is
	// never drained: that could hold Close open on a long stream.
	if t.call.HTTPStatus != http.StatusOK {
		if _, err := io.Copy(io.Discard, io.LimitReader(t, maxKeptBody)); err != nil {
			slog.Debug("llm call log: error body unreadable", "status", t.call.HTTPStatus, "err", err)
		}
	}
	err := t.rc.Close()
	t.once.Do(func() {
		c := t.call
		c.Total = time.Since(c.Started)
		c.ResponseBody = t.buf.Bytes()
		c.ResponseBytes = t.n
		c.ResponseTruncated = t.n > int64(t.buf.Len())
		if t.rerr != nil {
			c.Error = t.rerr.Error()
		}
		stream := c.Streamed || strings.HasPrefix(http.Header(c.ResponseHeaders).Get("Content-Type"), "text/event-stream")
		if c.HTTPStatus == http.StatusOK {
			p := parseResponse(c.ResponseBody, stream)
			if p.Model != "" {
				c.Model = p.Model
			}
			c.StopReason, c.MessageID, c.Usage = p.StopReason, p.MessageID, p.Usage
			if !p.Complete {
				// The API bills what the model wrote before the client went,
				// which a cut body does not report.
				chargeCeiling(&c, t.maxTokens)
			}
			c.CostUSD, c.PriceKnown = Cost(c.Model, c.Usage)
		} else {
			c.PriceKnown = true // nothing was billed
		}
		t.store.record(t.ctx, c)
	})
	return err
}

func (s *Store) record(ctx context.Context, c Call) {
	ctx, cancel := context.WithTimeout(context.WithoutCancel(ctx), recordTimeout)
	defer cancel()
	if !c.PriceKnown {
		slog.Warn("llm call log: model has no price, charged at the dearest rate", "model", c.Model, "cost_usd", c.CostUSD)
	}
	if _, err := s.InsertCall(ctx, c); err != nil {
		s.lastWriteFailure.Store(time.Now().UnixMilli())
		slog.Error("llm call log: call not recorded, generation paused", "run_id", c.RunID, "label", c.Label,
			"status", c.HTTPStatus, "cost_usd", c.CostUSD, "err", err)
		return
	}
	s.lastWriteFailure.Store(0)
	slog.Debug("llm call recorded", "run_id", c.RunID, "label", c.Label, "status", c.HTTPStatus,
		"total_ms", c.Total.Milliseconds(), "cost_usd", c.CostUSD)
}

// LabelFrom returns the label set by WithLabel, or "".
func LabelFrom(ctx context.Context) string {
	l, _ := ctx.Value(labelKey{}).(string)
	return l
}
