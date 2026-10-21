# Metaphor forest: live forge on the 3D graph

Status: approved 2026-10-21. Supersedes the static-index forge approach for the user-facing feature. `/forge/suggest`, the cascade and the grading tool stay as they are.

## Why

The static forge stalled because "no runtime LLM, under 100 ms" forced metaphors into a precomputed index:

1. Property-cluster overlap retrieves near-synonyms. 70% of apt pairs share no cluster.
2. The aptness eval contrasts dead metaphors with near-synonyms, so it cannot see liveness.
3. Snapping LLM phrases to single-word WordNet synsets put the wrong sense on 33% of chains and capped the judge.
4. A judged index needs thousands of labels; there were 90.

The owner relaxed the no-runtime-LLM requirement on 2026-10-21. A cheap model now generates a forest of metaphor paths per request, and a second call judges them.

## Requirement

A 3D force graph of words linked by the semantics they share. From one source word, live and novel metaphors appear on the graph as a branching forest: paths of 1 to N hops from the source to several metaphorical endpoints. Live means apt and vivid; dead means clichéd. Each request may return a different forest.

## Design decisions

| Decision | Choice |
|---|---|
| Nodes | The model's own words and phrases (at most 4 words), normalised: lower-case, trimmed, inner whitespace collapsed. No WordNet snapping. Node id is the normalised word, which matches the browse graph's bare-word ids. |
| Edges | Directed along the path, source outward. Each carries the grounds (shared qualities) that join its two words. |
| Branching | Forced by the output schema: 3-4 facets of the source, each a first hop with 2-4 branches continuing from it. |
| Quality gate | Second call (judge) scores each path 0-10 with flags. Keep score >= 6 and no flag. The UI marks >= 7 as live. |
| Hops | `max_hops` 1-5, default 3. |
| Model | `claude-haiku-5-5`, effort `medium`, both calls. Env-configurable. |
| Caching | None. |
| Spend guard | Global: 4 concurrent, 30 forests per minute. Env-configurable. |
| Base graph | The forest overlays the thesaurus graph for the looked-up word; thesaurus links dim while a forest is shown. |

## API contract

`GET /forge/forest?word=<w>&max_hops=<1..5>`

`word`: required. After normalisation, 1-40 characters of letters, spaces, hyphens and apostrophes. Anything else is 400. This also keeps arbitrary text out of the prompt.

200 response:

```json
{
  "source": "patience",
  "max_hops": 3,
  "model": "claude-haiku-5-5",
  "nodes": [
    {"id": "patience", "word": "patience", "role": "source"},
    {"id": "dormant seed", "word": "dormant seed", "role": "hop"},
    {"id": "seed vault", "word": "seed vault", "role": "endpoint"}
  ],
  "edges": [
    {"source": "patience", "target": "dormant seed", "grounds": ["waits intact until conditions allow"]},
    {"source": "dormant seed", "target": "seed vault", "grounds": ["stays viable for centuries"]}
  ],
  "endpoints": [
    {
      "id": "seed vault",
      "path": ["patience", "dormant seed", "seed vault"],
      "grounds": ["waits intact until conditions allow", "stays viable for centuries"],
      "line": "His patience was a seed vault: everything kept viable against the thaw.",
      "score": 7,
      "reason": "preservation made literal and cold"
    }
  ],
  "stats": {
    "generated": 14,
    "kept": 8,
    "rejected": {"invalid": 1, "low_score": 3, "broken_hop": 1, "drift": 0, "cliche": 1, "literal": 0, "duplicate": 0}
  }
}
```

- `role` is `source`, `hop` or `endpoint`. A node that ends any kept path is `endpoint`, even if another path passes through it.
- `endpoints` is sorted by score descending, then path length ascending.
- `path[i]` to `path[i+1]` is joined by `grounds[i]`.
- An empty forest (every path rejected) is still 200 with empty `nodes` apart from the source, and empty `edges` and `endpoints`.

Errors, all `{"error": "<message>"}`:

| Status | When |
|---|---|
| 400 | missing or invalid `word`, `max_hops` outside 1-5 |
| 429 | concurrency or per-minute cap hit; sets `Retry-After` |
| 502 | model error, refusal, `max_tokens` stop, or unparseable output |
| 503 | no API key configured: `metaphor forest is not configured on this server` |
| 504 | request deadline exceeded |

## Backend

- `api/internal/llm`: a `Completer` interface (system, user, JSON schema, model, effort, max tokens -> JSON bytes plus usage) and an Anthropic implementation using the official Go SDK (`github.com/anthropics/anthropic-sdk-go`) with structured output (`output_config.format`), `output_config.effort`, and `cache_control` on the system prompt. Tests use a fake.
- `api/internal/forest`:
  - `prompts.go`: the two system prompts and schemas below, as constants.
  - `build.go`: pure functions. Flatten facets to paths; validate; apply verdicts; merge survivors into nodes, edges and endpoints. Most tests live here.
  - `service.go`: generate, then judge, then build. Logs per request: word, max_hops, model, per-call latency, input, output and cache-read tokens, generated, kept and rejected counts by reason. Timers through the existing `observe` package.
  - `limiter.go`: non-blocking concurrency semaphore plus a fixed one-minute window counter, injectable clock.
- Handler `GET /forge/forest`, registered in `api/cmd/metaforge/main.go`. Raise the server write timeout to 90 s; per-request deadline 75 s.
- Env: `ANTHROPIC_API_KEY`, `METAFORGE_FOREST_MODEL`, `METAFORGE_FOREST_JUDGE_MODEL`, `METAFORGE_FOREST_EFFORT`, `METAFORGE_FOREST_MIN_SCORE`, `METAFORGE_FOREST_MAX_CONCURRENT`, `METAFORGE_FOREST_PER_MINUTE`.

### Path validation (reject as `invalid`)

- a hop word empty after normalisation, longer than 4 words or 60 characters
- an empty ground, or a ground longer than 80 characters
- an empty line on a path end, or a line longer than 200 characters
- path length 0 or greater than `max_hops`
- a path that revisits a word, including the source
- the judge returned no verdict for the path
- the path is beyond the first 24 the model produced, in model order (extras are never judged)

Grounds and lines have inner whitespace, newlines included, collapsed to single spaces, so a path stays on one line of the judge's message. Paths that fail validation are never sent to the judge.

Then reject flagged paths (first matching flag in the order `broken_hop`, `drift`, `literal`, `cliche`) and paths scoring below the minimum (`low_score`). When two kept paths end at the same endpoint, keep the higher score (then the shorter path, then the earlier one); the others count as `duplicate`. Every generated path is either kept or in exactly one `rejected` bucket, so `kept` plus the `rejected` counts equal `generated`.

## Frontend

- `web/src/api/client.ts` `fetchForest(word, maxHops)` and types in `web/src/types/api.ts`. Map 503, 429 and 504 to distinct user-facing messages.
- A pure transform from the forest response to graph nodes and links, merged into the browse graph by bare-word id.
- `mf-force-graph`: metaphor links in their own colour with directional particles flowing outward; endpoints larger and always labelled; hover on an endpoint lights its whole path and dims the rest; thesaurus links dim while a forest is shown.
- A forest panel: Forge / New forest, max hops 1-5, loading and error states, and the endpoint list (line, path with grounds, score). Focus or hover on an item lights its path. It is the accessible surface and must work at phone width.
- UI state machine: `docs/plans/2026-10-21-metaphor-forest-ui-states.md`.

## Prompts

### Generator system prompt

```
You are the Forge. Given a source word, you find fresh, apt metaphors for it and show the path of shared qualities that leads to each one.

Your reader is a genre-fiction writer (SF, fantasy, horror, thriller, crime). A live metaphor makes their reader stop and see the source anew. A dead one gets skimmed past.

## The shape of the forest
Grow a forest from SOURCE. Pick 3 or 4 facets: different sides of SOURCE (what it does, what it leaves behind, how it fails, what it costs, how it feels from inside).

Each facet starts with one hop: a word or short phrase (at most 3 words) that shares one concrete, nameable quality with SOURCE. Name that quality as the facet's `ground` (at most 6 words).

From each facet word, grow 2 to 4 branches. A branch continues with 1 or more further hops, each sharing a named quality (`ground`) with the word before it. A path is SOURCE, then the facet word, then the branch's hops. No path may be longer than MAX_HOPS hops in total. Mix lengths across the forest.

The last word of each path is its endpoint, the vehicle. "SOURCE is ENDPOINT" must work as a fresh, apt metaphor. Write it as `line`: one sentence a writer could lift into prose, at most 16 words. In the line, SOURCE is the thing being described and the endpoint is what it is seen as. Never swap them.

If the facet word is itself a strong endpoint, give the facet a `line`; otherwise leave the facet's `line` empty.

Every ground must be true of both words it joins. Every endpoint must still connect back to SOURCE through its chain of grounds. All endpoints must differ.

## What makes a metaphor live
- The endpoint comes from a different domain from SOURCE. Something physically part of SOURCE, found with it, or made by it is not a metaphor: a river is not a culvert, a forest is not a sawmill. A synonym walk is not a metaphor.
- The best vehicles are specific, named things with mechanics: an instrument, a craft process, a technical object, an institution, a biological process. The register, not words to reuse: verdigris, moraine, dead letter, taxidermy, cargo cult, annealing, tidemark, escrow, orrery.
- Process vehicles land because they carry a mechanism: annealing, winnowing, rendering, triangulation.
- Decay and body-horror vehicles punch above their weight for this audience.
- A reader must get it without a dictionary. Specific beats obscure.
- Elemental nouns are usually dead: fire, water, storm, stone, light, ice, shadow.
- Never use these worn vehicles: wound, ghost, hearth, drowning, fever, undertow, volcano, journey, amber, palimpsest, mycelium, fermentation, tapestry, labyrinth, mirror.
- Familiar means dead. If the pairing is a stock phrase or idiom, drop it.
```

Generator user message:

```
SOURCE: {word}
MAX_HOPS: {max_hops}
```

Generator output schema:

```json
{
  "type": "object",
  "additionalProperties": false,
  "required": ["facets"],
  "properties": {
    "facets": {
      "type": "array",
      "items": {
        "type": "object",
        "additionalProperties": false,
        "required": ["word", "ground", "line", "branches"],
        "properties": {
          "word": {"type": "string"},
          "ground": {"type": "string"},
          "line": {"type": "string"},
          "branches": {
            "type": "array",
            "items": {
              "type": "object",
              "additionalProperties": false,
              "required": ["hops", "line"],
              "properties": {
                "hops": {
                  "type": "array",
                  "items": {
                    "type": "object",
                    "additionalProperties": false,
                    "required": ["word", "ground"],
                    "properties": {
                      "word": {"type": "string"},
                      "ground": {"type": "string"}
                    }
                  }
                },
                "line": {"type": "string"}
              }
            }
          }
        }
      }
    }
  }
}
```

Flattening: a facet with a non-empty `line` yields the path `[facet]`. Each branch yields `[facet, ...branch.hops]` with the branch's `line`.

### Judge system prompt

```
You are the Forge Reader: a working genre-fiction novelist and acquiring editor with an unsentimental eye for the difference between a live image and a dead one. You have a slush pile and a deadline, and most things are average.

You will get a source word and numbered metaphor paths. Each path walks from the source through hops to an endpoint, with the shared quality ("ground") named at each hop, and ends with a line a writer might use.

Score each path for liveness, 0 to 10, judging the source-to-endpoint pairing first. The hops matter as evidence that the bridge is real.

- 0-2 dead: a cliché or stock idiom, or no real jump to a different domain, or an incoherent chain.
- 3-4 inert: valid but flat and obvious, or a synonym walk.
- 5-6 serviceable: mildly fresh, usable in a draft, not memorable.
- 7-8 live: fresh, surprising yet apt; the pairing makes you see the source anew.
- 9-10 electric: the rare line a professional would steal.

Calibration:
- loneliness -> separateness -> encircling water -> inaccessible shore -> island: 8
- envy -> copper surface -> green patina -> verdigris: 8
- certainty -> unshakeable ground -> bedrock: 7
- discontent -> emptiness -> craving -> hunger: 5
- longing -> desire -> want -> need: 3
- anger -> heat -> rising temperature -> fire: 1

Flag each path, true or false:
- broken_hop: some ground is not true of both words it joins.
- drift: the endpoint no longer connects back to the source, or the line swaps source and endpoint.
- literal: the endpoint is physically part of, found with, or made by the source, so the pairing is a fact, not a metaphor.
- cliche: the pairing or the line is a stock phrase.

A reader must get the image without a dictionary; obscure is not fresh. Do not reward a cliché for being clear. Do not punish an image for being pulpy or vivid. Give one terse reason, at most 10 words, per path.
```

Judge user message:

```
SOURCE: {word}

1. {source} -[{ground}]-> {word} -[{ground}]-> {endpoint} | {line}
2. ...
```

Judge output schema:

```json
{
  "type": "object",
  "additionalProperties": false,
  "required": ["verdicts"],
  "properties": {
    "verdicts": {
      "type": "array",
      "items": {
        "type": "object",
        "additionalProperties": false,
        "required": ["index", "score", "broken_hop", "drift", "literal", "cliche", "reason"],
        "properties": {
          "index": {"type": "integer"},
          "score": {"type": "integer"},
          "broken_hop": {"type": "boolean"},
          "drift": {"type": "boolean"},
          "literal": {"type": "boolean"},
          "cliche": {"type": "boolean"},
          "reason": {"type": "string"}
        }
      }
    }
  }
}
```

Scores outside 0-10 are clamped. Unknown indices are ignored and logged.

## Open

- Live prompt tuning waits on an API key in the cloud environment. Gotcha for that session: Claude Code cloud containers set `ANTHROPIC_BASE_URL` for their own use, and the Go SDK reads it, so start the API with `env -u ANTHROPIC_BASE_URL` or the calls go to the wrong host. The key lives in the environment variable `METAFORGE_ANTHROPIC_API_KEY`, not `ANTHROPIC_API_KEY`, so Claude Code itself never picks it up; map it at launch: `env -u ANTHROPIC_BASE_URL ANTHROPIC_API_KEY="$METAFORGE_ANTHROPIC_API_KEY" ./metaforge ...`. A network secret cannot carry it: `api.anthropic.com` is on the container proxy's no-proxy list, so no header injection reaches it, and the API expects `x-api-key`, not `Authorization: Bearer`. Tune on a mix of abstract sources (patience, bureaucracy) and concrete ones (river), where the probe produced literal endpoints.
- Full-stack check against a stand-in model server passed on 2026-10-21 (contract, request shape, 400/503 paths, UI order, no raw string ids in the forest panel). Real latency and cost per forest are not measured yet.
- A live-versus-dead eval to replace the aptness KPI is a follow-up.
