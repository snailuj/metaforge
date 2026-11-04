package llmlog

import "regexp"

// Usage is the token accounting of one API response, as the API reports it.
type Usage struct {
	InputTokens      int64 `json:"input_tokens"`
	OutputTokens     int64 `json:"output_tokens"`
	CacheReadTokens  int64 `json:"cache_read_input_tokens"`
	CacheWriteTokens int64 `json:"cache_creation_input_tokens"`
}

// rateCard is USD per million tokens.
type rateCard struct {
	input, output, cacheRead float64
}

// cacheWriteFactor is the 5-minute cache write premium over the input rate;
// the forest prompts use only the default 5-minute TTL.
const cacheWriteFactor = 1.25

// longPromptTokens is where Haiku 5.5 switches to its long-prompt card.
const longPromptTokens = 100_000

// Prices are Anthropic first-party list prices as of 2026-10-06. Every call
// row keeps its raw usage, so a wrong or stale figure here can be corrected
// by recomputing cost_usd later.
var prices = map[string]rateCard{
	"claude-haiku-5-5":  {0.10, 0.50, 0.01},
	"claude-sonnet-5-5": {2.00, 10.00, 0.20},
	"claude-opus-5-5":   {4.00, 20.00, 0.20},
	"claude-fable-5-1":  {10.00, 50.00, 0.25},
}

var haikuLong = rateCard{0.50, 2.50, 0.05}

// snapshotDate is the -YYYYMMDD suffix a response may name its model by.
var snapshotDate = regexp.MustCompile(`-\d{8}$`)

// dearest prices a model missing from the table, so the weekly cap stops
// early rather than overspends.
var dearest = rateCard{10.00, 50.00, 1.00}

// Cost returns the USD cost of one response, and false when the model is
// not in the price table and was priced at the dearest card.
func Cost(model string, u Usage) (float64, bool) {
	model = snapshotDate.ReplaceAllString(model, "")
	card, known := prices[model]
	if !known {
		card = dearest
	}
	if model == "claude-haiku-5-5" && u.InputTokens+u.CacheReadTokens+u.CacheWriteTokens > longPromptTokens {
		card = haikuLong
	}
	usd := float64(u.InputTokens)*card.input +
		float64(u.OutputTokens)*card.output +
		float64(u.CacheReadTokens)*card.cacheRead +
		float64(u.CacheWriteTokens)*card.input*cacheWriteFactor
	return usd / 1e6, known
}
