// Package llmlog keeps every model call the API makes, forever: the raw
// HTTP request and response, timings, usage and cost. It is an append-only
// record (nothing is evicted or updated) that serves as an eval bench and
// as the ledger the weekly spend cap reads.
package llmlog

import (
	"bytes"
	"compress/gzip"
	"context"
	"database/sql"
	"encoding/json"
	"fmt"
	"io"
	"log/slog"
	"time"

	_ "github.com/mattn/go-sqlite3"
)

// Bodies are gzipped: JSON compresses well and the file only grows.
// Times are unix milliseconds (UTC) for range queries, with an ISO copy
// for people reading the file.
const schema = `
CREATE TABLE IF NOT EXISTS llm_calls (
	id                  INTEGER PRIMARY KEY AUTOINCREMENT,
	started_ms          INTEGER NOT NULL,
	started_at          TEXT    NOT NULL,
	headers_ms          REAL,
	first_byte_ms       REAL,
	total_ms            REAL,
	run_id              TEXT,
	origin              TEXT,
	label               TEXT,
	word                TEXT,
	max_hops            INTEGER,
	method              TEXT,
	url                 TEXT,
	model               TEXT,
	streamed            INTEGER NOT NULL DEFAULT 0,
	http_status         INTEGER,
	error               TEXT,
	request_id          TEXT,
	message_id          TEXT,
	stop_reason         TEXT,
	input_tokens        INTEGER NOT NULL DEFAULT 0,
	output_tokens       INTEGER NOT NULL DEFAULT 0,
	cache_read_tokens   INTEGER NOT NULL DEFAULT 0,
	cache_write_tokens  INTEGER NOT NULL DEFAULT 0,
	cost_usd            REAL    NOT NULL DEFAULT 0,
	price_known         INTEGER NOT NULL DEFAULT 1,
	request_headers     TEXT,
	request_body_gz     BLOB,
	response_headers    TEXT,
	response_body_gz    BLOB,
	response_bytes      INTEGER,
	response_truncated  INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_llm_calls_started ON llm_calls(started_ms, cost_usd);
CREATE INDEX IF NOT EXISTS idx_llm_calls_run ON llm_calls(run_id);
CREATE INDEX IF NOT EXISTS idx_llm_calls_word ON llm_calls(word);

CREATE TABLE IF NOT EXISTS forest_runs (
	id          INTEGER PRIMARY KEY AUTOINCREMENT,
	run_id      TEXT    NOT NULL,
	started_ms  INTEGER NOT NULL,
	started_at  TEXT    NOT NULL,
	total_ms    REAL,
	word        TEXT    NOT NULL,
	max_hops    INTEGER NOT NULL,
	origin      TEXT,
	fingerprint TEXT,
	outcome     TEXT    NOT NULL,
	error       TEXT,
	cost_usd    REAL,
	forest_gz   BLOB
);
CREATE INDEX IF NOT EXISTS idx_forest_runs_word ON forest_runs(word, max_hops);
CREATE INDEX IF NOT EXISTS idx_forest_runs_run ON forest_runs(run_id);
`

// Call is one HTTP exchange with the model API. A retried request is
// several Calls with the same RunID and Label.
type Call struct {
	Started        time.Time
	HeadersAfter   time.Duration // until response headers arrived
	FirstByteAfter time.Duration // until the first body byte; zero if none
	Total          time.Duration // until the body was closed

	RunID, Origin, Label, Word string
	MaxHops                    int

	Method, URL, Model string
	Streamed           bool
	HTTPStatus         int
	Error              string
	RequestID          string // the API's request-id header
	MessageID          string
	StopReason         string
	Usage              Usage
	CostUSD            float64
	PriceKnown         bool

	RequestHeaders, ResponseHeaders map[string][]string
	RequestBody, ResponseBody       []byte
	ResponseBytes                   int64 // bytes read, including any not kept
	ResponseTruncated               bool
}

// Run is one forest request: what the user (or the enricher) got back.
type Run struct {
	ID          string
	Started     time.Time
	Total       time.Duration
	Word        string
	MaxHops     int
	Origin      string
	Fingerprint string
	Outcome     string // ok | error | timeout | canceled
	Error       string
	CostUSD     float64
	Forest      []byte // the forest as JSON; nil when none was built
}

// Store is safe for concurrent use, and for several processes sharing one
// file (staging and production both write the same ledger).
type Store struct {
	db *sql.DB
}

func Open(path string) (*Store, error) {
	db, err := sql.Open("sqlite3", path+"?_journal_mode=WAL&_busy_timeout=10000&_synchronous=NORMAL")
	if err != nil {
		return nil, fmt.Errorf("open llm call log %s: %w", path, err)
	}
	db.SetMaxOpenConns(1)
	if _, err := db.Exec(schema); err != nil {
		db.Close()
		return nil, fmt.Errorf("create llm call log schema in %s: %w", path, err)
	}
	var n int
	if err := db.QueryRow(`SELECT COUNT(*) FROM llm_calls`).Scan(&n); err != nil {
		db.Close()
		return nil, fmt.Errorf("count llm calls in %s: %w", path, err)
	}
	slog.Info("llm call log opened", "path", path, "calls", n)
	return &Store{db: db}, nil
}

func (s *Store) Close() error { return s.db.Close() }

func (s *Store) InsertCall(ctx context.Context, c Call) (int64, error) {
	reqBody, err := gz(c.RequestBody)
	if err != nil {
		return 0, err
	}
	respBody, err := gz(c.ResponseBody)
	if err != nil {
		return 0, err
	}
	res, err := s.db.ExecContext(ctx, `INSERT INTO llm_calls (
		started_ms, started_at, headers_ms, first_byte_ms, total_ms,
		run_id, origin, label, word, max_hops,
		method, url, model, streamed, http_status, error, request_id, message_id, stop_reason,
		input_tokens, output_tokens, cache_read_tokens, cache_write_tokens, cost_usd, price_known,
		request_headers, request_body_gz, response_headers, response_body_gz, response_bytes, response_truncated
	) VALUES (?,?,?,?,?, ?,?,?,?,?, ?,?,?,?,?,?,?,?,?, ?,?,?,?,?,?, ?,?,?,?,?,?)`,
		c.Started.UnixMilli(), c.Started.UTC().Format(time.RFC3339Nano),
		msf(c.HeadersAfter), msf(c.FirstByteAfter), msf(c.Total),
		c.RunID, c.Origin, c.Label, c.Word, c.MaxHops,
		c.Method, c.URL, c.Model, c.Streamed, c.HTTPStatus, c.Error, c.RequestID, c.MessageID, c.StopReason,
		c.Usage.InputTokens, c.Usage.OutputTokens, c.Usage.CacheReadTokens, c.Usage.CacheWriteTokens, c.CostUSD, c.PriceKnown,
		headersJSON(c.RequestHeaders), reqBody, headersJSON(c.ResponseHeaders), respBody, c.ResponseBytes, c.ResponseTruncated,
	)
	if err != nil {
		return 0, fmt.Errorf("insert llm call: %w", err)
	}
	return res.LastInsertId()
}

// GetCall reads one call back, bodies decompressed.
func (s *Store) GetCall(ctx context.Context, id int64) (Call, error) {
	var c Call
	var startedMs int64
	var headersMs, firstMs, totalMs float64
	var reqH, respH sql.NullString
	var reqB, respB []byte
	err := s.db.QueryRowContext(ctx, `SELECT started_ms, headers_ms, first_byte_ms, total_ms,
		run_id, origin, label, word, max_hops, method, url, model, streamed, http_status, error,
		request_id, message_id, stop_reason, input_tokens, output_tokens, cache_read_tokens, cache_write_tokens,
		cost_usd, price_known, request_headers, request_body_gz, response_headers, response_body_gz,
		response_bytes, response_truncated FROM llm_calls WHERE id = ?`, id).Scan(
		&startedMs, &headersMs, &firstMs, &totalMs,
		&c.RunID, &c.Origin, &c.Label, &c.Word, &c.MaxHops, &c.Method, &c.URL, &c.Model, &c.Streamed, &c.HTTPStatus, &c.Error,
		&c.RequestID, &c.MessageID, &c.StopReason, &c.Usage.InputTokens, &c.Usage.OutputTokens, &c.Usage.CacheReadTokens, &c.Usage.CacheWriteTokens,
		&c.CostUSD, &c.PriceKnown, &reqH, &reqB, &respH, &respB, &c.ResponseBytes, &c.ResponseTruncated)
	if err != nil {
		return Call{}, fmt.Errorf("read llm call %d: %w", id, err)
	}
	c.Started = time.UnixMilli(startedMs).UTC()
	c.HeadersAfter, c.FirstByteAfter, c.Total = ms(headersMs), ms(firstMs), ms(totalMs)
	if c.RequestBody, err = gunzip(reqB); err != nil {
		return Call{}, err
	}
	if c.ResponseBody, err = gunzip(respB); err != nil {
		return Call{}, err
	}
	c.RequestHeaders, c.ResponseHeaders = parseHeaders(reqH.String), parseHeaders(respH.String)
	return c, nil
}

// SpentSince sums the cost of every call started at or after t.
func (s *Store) SpentSince(ctx context.Context, t time.Time) (float64, error) {
	var usd float64
	if err := s.db.QueryRowContext(ctx, `SELECT COALESCE(SUM(cost_usd), 0) FROM llm_calls WHERE started_ms >= ?`,
		t.UnixMilli()).Scan(&usd); err != nil {
		return 0, fmt.Errorf("sum llm spend: %w", err)
	}
	return usd, nil
}

// RunCost sums the calls of one forest request, retries included.
func (s *Store) RunCost(ctx context.Context, runID string) (float64, error) {
	var usd float64
	if err := s.db.QueryRowContext(ctx, `SELECT COALESCE(SUM(cost_usd), 0) FROM llm_calls WHERE run_id = ?`,
		runID).Scan(&usd); err != nil {
		return 0, fmt.Errorf("sum cost of run %s: %w", runID, err)
	}
	return usd, nil
}

func (s *Store) RecordRun(ctx context.Context, r Run) error {
	body, err := gz(r.Forest)
	if err != nil {
		return err
	}
	if _, err := s.db.ExecContext(ctx, `INSERT INTO forest_runs
		(run_id, started_ms, started_at, total_ms, word, max_hops, origin, fingerprint, outcome, error, cost_usd, forest_gz)
		VALUES (?,?,?,?,?,?,?,?,?,?,?,?)`,
		r.ID, r.Started.UnixMilli(), r.Started.UTC().Format(time.RFC3339Nano), msf(r.Total),
		r.Word, r.MaxHops, r.Origin, r.Fingerprint, r.Outcome, r.Error, r.CostUSD, body); err != nil {
		return fmt.Errorf("record forest run %s: %w", r.ID, err)
	}
	return nil
}

// Durations are stored as fractional milliseconds.
func ms(f float64) time.Duration  { return time.Duration(f * float64(time.Millisecond)) }
func msf(d time.Duration) float64 { return float64(d) / float64(time.Millisecond) }

func gz(b []byte) ([]byte, error) {
	if b == nil {
		return nil, nil
	}
	var buf bytes.Buffer
	w := gzip.NewWriter(&buf)
	if _, err := w.Write(b); err != nil {
		return nil, fmt.Errorf("gzip body: %w", err)
	}
	if err := w.Close(); err != nil {
		return nil, fmt.Errorf("gzip body: %w", err)
	}
	return buf.Bytes(), nil
}

func gunzip(b []byte) ([]byte, error) {
	if b == nil {
		return nil, nil
	}
	r, err := gzip.NewReader(bytes.NewReader(b))
	if err != nil {
		return nil, fmt.Errorf("gunzip body: %w", err)
	}
	out, err := io.ReadAll(r)
	if err != nil {
		return nil, fmt.Errorf("gunzip body: %w", err)
	}
	return out, nil
}

func headersJSON(h map[string][]string) any {
	if h == nil {
		return nil
	}
	b, err := json.Marshal(h)
	if err != nil {
		slog.Error("llm call log: could not encode headers", "err", err)
		return nil
	}
	return string(b)
}

func parseHeaders(s string) map[string][]string {
	if s == "" {
		return nil
	}
	var h map[string][]string
	if err := json.Unmarshal([]byte(s), &h); err != nil {
		slog.Error("llm call log: stored headers did not decode", "err", err)
		return nil
	}
	return h
}
