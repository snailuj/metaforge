# Model-call ledger and paced enrichment

_2026-11-04. Owner asks: keep every model answer forever (the full request and response, for metadata such as response-time drift; an eval bench in the making), and run enrichment night and day through the API to grow the forest cache, capped at USD 20 a week. The cap includes live user spend._

## What was built

**Ledger** (`api/internal/llmlog`). An SDK middleware records every HTTP attempt the API makes to the model API, retries and failures included, as one row of `llm_calls` in an append-only SQLite file (`METAFORGE_LLM_LOG`). Nothing is evicted or updated.

| Column group | Contents |
|---|---|
| Who asked | `run_id` (one forest request), `origin` (`web`, `enrichment`; self-declared via `X-Metaforge-Origin`), `label` (`forest_generate`, `forest_judge`), `word`, `max_hops` |
| Timing | `started_ms` / `started_at`, `headers_ms`, `first_byte_ms`, `total_ms` (fractional ms) |
| Outcome | `http_status`, `error`, `request_id` (Anthropic's), `message_id`, `stop_reason`, `model`, `streamed` |
| Money | the four usage counts, `cost_usd`, `price_known` (0: unknown model, priced at the dearest card) |
| Raw | `request_headers` (API key redacted), `request_body_gz`, `response_headers`, `response_body_gz` (gzip; SSE text for streams), `response_bytes`, `response_truncated` (over 16 MB) |

`forest_runs` holds one row per forest request: outcome (`ok`, `error`, `timeout`, `canceled`), pipeline fingerprint, total cost and the forest as built, gzipped. Join on `run_id`. Low-scoring and rejected paths are in the judge's raw response; the built forest holds only kept ones.

Reading a body: `SELECT response_body_gz FROM llm_calls WHERE id = ?`, then `gzip.decompress` in Python or `zcat`.

Prices (`price.go`) are list prices as of 2026-10-06, with Haiku 5.5's long-prompt card. Usage is kept raw, so `cost_usd` can be recomputed if a price was wrong.

**Weekly cap** (`llmlog.Budget`). `METAFORGE_WEEKLY_BUDGET_USD` (default 20, 0 for none) over a rolling 7 days of every recorded call. Staging and production write the same file (`/var/lib/metaforge/llm_calls.db`), so the cap covers both. Live users are never stopped (owner's call, 2026-11-04); their spend counts toward the cap, so heavy live use slows enrichment. When the week's spend reaches the cap, enrichment requests (`X-Metaforge-Origin: enrichment`) stop generating: they get a pooled forest with `X-Forest-Budget: exhausted`, or 503 when the pool is empty. The cap can therefore be exceeded by live use alone. For enrichment, a ledger that cannot be read counts as spent, and so does a failed write for five minutes after it (that call's spend is invisible to the cap); a configured ledger that will not open disables generation. Spend is checked before a forest starts, so the cap can be overshot by the forests already in flight (at most 4, about $0.003 each).

**Weekly ceiling** (added 2026-11-04, owner's choice of an abuse-only stop). `METAFORGE_WEEKLY_CEILING_USD` (default 50, 0 for none) over the same rolling week and ledger. When all recorded spend reaches it, nobody generates, live users included: a pooled forest is served with `X-Forest-Budget: ceiling`, or 429 with `Retry-After: 3600` when the pool is empty. An unreadable ceiling counts as reached. Normal use stays far below it; it bounds what an attack can spend in a week. The enricher idles on any `X-Forest-Budget` value.

`GET /forge/budget` (direct loopback only: requests with `X-Forwarded-For` or from another host get 404) returns `{cap_usd, spent_usd, remaining_usd, window_start, exhausted}`. Each generated JSON forest carries `X-Forest-Cost-USD`.

**Enricher** (`api/cmd/enrich`, `api/internal/enrich`). Walks a word list (`-words FILE`, or `-lexicon DB -top N`: the most frequent words with a noun or adjective sense), asking for one `fresh=1` forest per word per pass, with `X-Metaforge-Origin: enrichment`. Before each forest it reads `/forge/budget`:

- it keeps `-reserve` (default $5) of the cap for live users, and waits 15 minutes while the week's total spend is above `cap - reserve`;
- it spaces forests at `cost estimate / ((cap - reserve) / week)`, so enrichment alone never outspends its share; the estimate is a running average of `X-Forest-Cost-USD`;
- it refuses to run against a server with no cap.

Progress (`pass`, `index`, totals, cost estimate, last request time) is written atomically, and synced, after each forest. Resumption is best effort: a crash between a forest and its save repeats that word, at the cost of one extra forest. A forest whose cost the server could not read leaves the estimate unchanged. 429 and transport errors retry the same word; a bad word or failed generation moves on. It stops after `-passes` (default 10, the pool size); 0 runs forever.

## Deploy

1. `deploy/production/deploy.sh` and `deploy/staging/deploy.sh` now create `/var/lib/metaforge` (owned by `agent`) and point both APIs at the shared ledger.
2. `deploy/enrich/deploy.sh` checks the API's cap is above the reserve, builds `api/enrich` and installs `metaforge-enrich.service` against the production API (`--no-start` installs it and stops any running copy).
3. Watch: `journalctl -u metaforge-enrich -f`, `curl -s 127.0.0.1:8080/forge/budget`.

## Sizes

At Haiku 5.5 prices a forest is about $0.001-0.003, so a $15 enrichment allowance is several thousand forests a week. Each forest is two to three rows of tens of kilobytes before gzip; expect the ledger to grow by the order of 100 MB a week at full pace. Nothing prunes it, by design.

## Open

- Spend made outside this API (the grading sidecar, scripts using the same key) is not in the ledger and not under the cap.
- Prices are hand-kept; check them when models change.
