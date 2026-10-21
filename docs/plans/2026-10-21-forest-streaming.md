# Metaphor forest: streaming to the panel

Status: draft for approval, 2026-10-21. Extends `docs/plans/2026-10-21-metaphor-forest.md`. Owner's choice: stream rather than pre-fill the cache.

## Why

A word's first Forge waits 10-30 s: the generator call takes 7-20 s and the judge 3-7 s, and nothing shows until both finish. Streaming shows judged metaphors while the rest are still being written.

## Rule

Every metaphor the panel shows has passed the judge. Streaming changes when a path appears, never which paths appear.

## How it works

1. The generator call streams (`Messages.NewStreaming` in the Go SDK). A small scanner watches the streamed JSON and hands over each facet object as soon as its closing brace arrives.
2. Each finished facet is screened and sent to its own judge call at once, so judging overlaps generation. Judge calls for one request run concurrently (at most 4).
3. After each judged facet, the server merges everything kept so far and sends the whole forest so far as one server-sent event. The client replaces its forest with each snapshot, so it never merges anything itself. A snapshot is a few KB, so resending it costs nothing that matters.
4. When the generator ends, the thin-output retry still applies: fewer than 3 valid paths in total starts one more streamed generator call.
5. The last event is `done` and carries the final forest in today's response shape plus stats. Only this final forest goes into the cache. A cancelled or failed stream stores nothing.

## API contract

`GET /forge/forest?word=<w>&max_hops=<n>[&fresh=1]` with `Accept: text/event-stream` streams. Without that header the endpoint answers exactly as today, so `forestprobe`, older clients and tests keep working.

- Validation, limiter and not-configured errors still answer before the stream starts, with today's status codes and JSON bodies (400, 429 with Retry-After, 503).
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
- Graph: new nodes and links join the overlay on each snapshot. Existing nodes keep their positions, so the graph grows rather than jumps.
- Cancel during a stream keeps what has arrived and says so, the same as cancel with a forest already shown.
- A stream error keeps what has arrived and shows the error with today's "kept" wording.

## Deploy

- Caddy passes `text/event-stream` through and flushes it at once, so neither Caddyfile changes.
- `forestWriteTimeout` (90 s) still bounds a whole stream.

## Tests (red first)

- Scanner: facets come out in order, whole, from JSON split at every byte offset, including braces inside strings.
- Service: with a fake streaming completer, the first snapshot is emitted before the generator finishes; every snapshot only holds judged paths; the final forest equals today's `Build` output for the same verdicts.
- Handler: SSE framing, errors before the stream keep today's status codes, error mid-stream, cache hit as one `done`, no Accept header gives the old JSON.
- Client and state: snapshots replace content, a stale seq is dropped, cancel and error keep partial content.
