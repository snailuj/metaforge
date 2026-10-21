# Metaphor forest: streaming to the panel

Status: draft for approval, 2026-10-21. Extends `docs/plans/2026-10-21-metaphor-forest.md`. Owner's choice: stream rather than pre-fill the cache.

## Why

A word's first Forge waits 10-30 s: the generator call takes 7-20 s and the judge 3-7 s, and nothing shows until both finish. Streaming shows judged metaphors while the rest are still being written.

## Rule

The graph shows the forging: hops appear as the generator writes them, unjudged paths flicker like lightning, rejected paths fade out, and kept paths settle. The panel list only ever holds judged, kept metaphors. Owner's call, 2026-10-21: a path that flickers and drops is a feature, not a glitch.

## How it works

1. The generator call streams (`Messages.NewStreaming` in the Go SDK). A small scanner watches the streamed JSON and reports each hop object and each facet object as soon as its closing brace arrives.
2. Each finished hop is sent at once as a `hop` event, so the graph grows a path word by word.
3. Each finished facet is screened. Paths that fail screening (loops, broken shape) get a `rejected` event straight away. The rest go to a judge call for that facet, so judging overlaps generation. Judge calls for one request run concurrently (at most 4).
4. When a facet's verdicts arrive, each of its paths gets a `kept` or `rejected` event, and the server sends a `forest` event: the merged forest of everything kept so far, in today's response shape. The panel list renders from `forest` snapshots only, so it never shows an unjudged path.
5. When the generator ends, the thin-output retry still applies: fewer than 3 valid paths in total starts one more streamed generator call.
6. The last event is `done` and carries the final forest in today's response shape plus stats. Only this final forest goes into the cache. A cancelled or failed stream stores nothing.

## API contract

`GET /forge/forest?word=<w>&max_hops=<n>[&fresh=1]` with `Accept: text/event-stream` streams. Without that header the endpoint answers exactly as today, so `forestprobe`, older clients and tests keep working.

- Validation, limiter and not-configured errors still answer before the stream starts, with today's status codes and JSON bodies (400, 429 with Retry-After, 503).
- `event: hop`, `data: {"path_id": "f1", "facet": 1, "from": "patience", "to": "dormant seed", "ground": "..."}` (a branch hop carries `f1b0` and starts from the facet word or the previous hop) as each hop is written. `path_id` names facet and branch; the first hop of a facet is shared by its branches.
- Path ids: `f<i>` is facet `i`'s own path (source to the facet word; it only gets a verdict when the facet has a line), `f<i>b<j>` is branch `j` of facet `i`, whose path starts with facet `i`'s hop. Indices are 0-based and keep counting across the thin-output retry, so ids never repeat within one stream. `facet` in a `hop` event is `i`. Words in `from` and `to` are normalised as node ids are.
- A pending node or link stays on the graph while any pending or kept path uses it, and fades once none does.
- `event: rejected`, `data: {"path_id": "f1b2", "reason": "low_score" | "invalid" | "broken_hop" | "drift" | "cliche" | "literal" | "duplicate"}`.
- `event: kept`, `data: {"path_id": "f1b2", "endpoint": "<endpoint id>", "score": 7}`.
- `event: forest`, `data: <Forest>` after each judged facet. The forest is the same shape as the 200 body today.
- `event: done`, `data: <Forest>` once, then the server closes the stream.
- `event: error`, `data: {"error": "...", "kind": "failed" | "timeout"}` if a model call fails after the stream started. Snapshots already sent stay valid.
- A cache hit streams a single `done` event.
- A comment line `: keepalive` every 10 s stops proxies from closing an idle stream.

## Judge per facet

Today one judge call sees every path. Per facet, each call sees 2-4 paths from one first hop. Expect up to 4 judge calls per forest instead of 1. The system prompt is repeated in each, so cost rises from about $0.001 to about $0.0015 per forest (estimate, not measured). The judge's scores may drift when it sees fewer paths at once; the full-stack check compares kept counts against the tuning log.

## Frontend

- `api/client.ts`: a `streamForest` function reads the event stream with `fetch` and a `ReadableStream`, so the existing AbortController cancels it.
- `forest/state.ts`: a new `streaming` request state holds the latest snapshot. Each snapshot replaces the shown forest; its `seq` check still drops events from a superseded request.
- Panel: metaphors appear in the list as they arrive. The status line reads "Forging... 4 metaphors so far" until `done`.
- Graph: `hop` events add pending nodes and links to the overlay. Pending links flicker (opacity and particle bursts on a short random cycle). On `rejected`, a path's links and any nodes no kept path uses fade out over about 600 ms. On `kept`, its links stop flickering and take the live colouring. Existing nodes keep their positions, so the graph grows rather than jumps.
- With reduced motion set, pending links show dashed and still, and rejected ones disappear without the fade.
- Cancel during a stream keeps what has arrived and says so, the same as cancel with a forest already shown.
- A stream error keeps what has arrived and shows the error with today's "kept" wording.

## Deploy

- Caddy passes `text/event-stream` through and flushes it at once, so neither Caddyfile changes.
- `forestWriteTimeout` (90 s) still bounds a whole stream.

## Tests (red first)

- Scanner: facets come out in order, whole, from JSON split at every byte offset, including braces inside strings.
- Service: with a fake streaming completer, the first `hop` arrives before the generator finishes; every path that got a `hop` ends with exactly one `kept` or `rejected`; every `forest` snapshot only holds kept paths; the final forest equals today's `Build` output for the same verdicts.
- Handler: SSE framing, errors before the stream keep today's status codes, error mid-stream, cache hit as one `done`, no Accept header gives the old JSON.
- Client and state: snapshots replace the list, pending paths resolve once each, a stale seq is dropped, cancel and error keep kept content and clear pending paths.
