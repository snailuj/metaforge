package enrich

import (
	"context"
	"encoding/json"
	"fmt"
	"io"
	"log/slog"
	"net/http"
	"net/url"
	"strconv"
	"strings"
	"time"

	"github.com/snailuj/metaforge/internal/llmlog"
)

// Origin labels the enricher's requests in the server's call log.
const Origin = "enrichment"

// maxForestBody bounds what is read of one forest answer.
const maxForestBody = 4 << 20

// Client talks to a Metaforge API over HTTP.
type Client struct {
	base string
	http *http.Client
}

// NewClient's timeout must outlast the server's forest deadline (75 s).
func NewClient(base string, timeout time.Duration) *Client {
	return &Client{base: strings.TrimRight(base, "/"), http: &http.Client{Timeout: timeout}}
}

func (c *Client) Budget(ctx context.Context) (llmlog.BudgetStatus, error) {
	var st llmlog.BudgetStatus
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, c.base+"/forge/budget", nil)
	if err != nil {
		return st, fmt.Errorf("budget request: %w", err)
	}
	resp, err := c.http.Do(req)
	if err != nil {
		return st, fmt.Errorf("budget request: %w", err)
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		return st, fmt.Errorf("budget request: status %d", resp.StatusCode)
	}
	if err := json.NewDecoder(io.LimitReader(resp.Body, 1<<16)).Decode(&st); err != nil {
		return st, fmt.Errorf("decode budget: %w", err)
	}
	return st, nil
}

// Forest always asks for a newly generated forest (fresh=1). A non-200
// answer is a result, not an error; errors are transport failures.
func (c *Client) Forest(ctx context.Context, word string, maxHops int) (ForestResult, error) {
	q := url.Values{"word": {word}, "max_hops": {strconv.Itoa(maxHops)}, "fresh": {"1"}}
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, c.base+"/forge/forest?"+q.Encode(), nil)
	if err != nil {
		return ForestResult{}, fmt.Errorf("forest request: %w", err)
	}
	req.Header.Set("Accept", "application/json")
	req.Header.Set("X-Metaforge-Origin", Origin)
	resp, err := c.http.Do(req)
	if err != nil {
		return ForestResult{}, fmt.Errorf("forest request for %q: %w", word, err)
	}
	defer resp.Body.Close()

	res := ForestResult{Status: resp.StatusCode, BudgetExhausted: resp.Header.Get("X-Forest-Budget") == "exhausted",
		PoolFull: resp.Header.Get("X-Forest-Pool") == "full"}
	if s := resp.Header.Get("Retry-After"); s != "" {
		if n, err := strconv.Atoi(s); err == nil {
			res.RetryAfter = time.Duration(n) * time.Second
		}
	}
	if s := resp.Header.Get("X-Forest-Cost-USD"); s != "" {
		if f, err := strconv.ParseFloat(s, 64); err == nil {
			res.CostUSD, res.CostKnown = f, true
		} else {
			slog.Warn("enrich: unreadable cost header", "word", word, "value", s)
		}
	}
	body, err := io.ReadAll(io.LimitReader(resp.Body, maxForestBody))
	if err != nil {
		return res, fmt.Errorf("read forest for %q: %w", word, err)
	}
	if res.Status == http.StatusOK {
		var f struct {
			Endpoints []json.RawMessage `json:"endpoints"`
		}
		if err := json.Unmarshal(body, &f); err != nil {
			slog.Warn("enrich: forest body did not decode", "word", word, "err", err)
		}
		res.Endpoints = len(f.Endpoints)
	}
	return res, nil
}
