# The Bridge — design brief & prototype

*Status: prototype / design exploration. Brief accompanies `web/prototypes/bridge/index.html`.*
*Framing source: `docs/roadmap/PIPELINE.md` (The Bridge, Queued) + `docs/roadmap/programme-overview.md`.*

## The one-line

The Forge asks **"what is X like?"** and ranks vehicles. The Bridge asks **"why is X like Y?"** and returns the conceptual path between a SOURCE and a TARGET the writer *already* has in mind: `anger → heat → consuming → destruction → fire`. It is the *dual* of the Forge — graph traversal, not pointwise ranking.

## The UX problem

A genre-fiction writer rarely starts from nothing. They start from a collision they've already half-made: *"I want to say my character's grief is a glacier"*, *"is 'memory is a courtroom' doing real work or am I reaching?"*. The Forge can't answer this — it suggests vehicles, it doesn't *vet a pairing the writer brought*. The writer needs two things the Forge doesn't give:

1. **Confidence** — does this metaphor actually *land*, or is it a private association that won't survive contact with a reader? Right now the only test is "read it aloud and wince." The Bridge gives a second opinion with a *mechanism* attached.
2. **Mechanism** — *why* it works, made explicit. A writer who can see the load-bearing hop (`grief → weight → slow inexorable mass → glacier`) can lean on it, vary it, or notice the hop is doing no work and the metaphor is dead.

And the inverse, which is just as valuable: when a pairing has **no bridge** (or only a strained one), that is a signal — *this isn't a metaphor, it's a non-sequitur or a cliché so worn the path collapsed.* Telling the writer "we couldn't find an honest path" is a feature, not a failure.

## Product values (from PIPELINE.md)

- **Explanatory** (user-facing): surface the metaphor's mechanism so the writer can act on it.
- **Inapt-cohort generation** (internal): weak/no-path queries semi-supervisedly produce *inapt* examples, expanding the eval cohort beyond MUNCH. Every "no bridge" verdict a writer accepts or overrides is a labelled negative for the judge. The Bridge is a covert grading surface.

## The concept

A single horizontal **span** running SOURCE → TARGET, drawn literally as a bridge: two stone piers (the concepts the writer typed) and the **stepping-stones** between them (the intermediate concepts). Each stone is a hop; the **deck** connecting them is the relation. The writer reads left-to-right and the metaphor *assembles itself* — this is the reveal, and it is the whole emotional payload of the feature.

Three result states, all on the same span:

| State | Visual | Meaning |
|---|---|---|
| **Solid bridge** | Gold piers, lit stones, confident deck, strength meter high | Apt, well-attested path. Ship it. |
| **Weak bridge** | One stone flagged amber, a "long hop" gap in the deck, strength meter mid, caveat line | Path exists but leans on one strained leap. The writer should decide. |
| **No bridge** | The span doesn't close — far pier is faded, broken deck, the gap is named | We couldn't find an honest path. Probably not a metaphor (or a dead one). |

The strength of the *weakest hop* governs the verdict — a chain is only as strong as its longest leap. This mirrors the path-geometry finding in memory (`max_hop_cos` "one big leap" separates live/dead): we surface the single widest hop as the thing to scrutinise.

## Key interactions

1. **Input** — two fields, `SOURCE` and `TARGET`, with a literal *bridge glyph* between them and a "Cross" button. Three pre-loaded example chips below (`anger → fire`, `grief → glacier`, `memory → spreadsheet` [weak]) so the operator can hit the states instantly. Source/target are concepts, not search — autocomplete would resolve to a synset in the real thing.
2. **Reveal** — on Cross, the stones light up **left to right, one hop at a time** (~280ms stagger). The path *builds*. This is deliberately theatrical; it is the moment of insight the product sells.
3. **Per-hop justification** — each stone carries its concept word; the **deck segment before it** carries the relation that licenses the hop (`is felt as`, `consumes like`, `shares the property`). Clicking/hovering a hop expands a justification card: the relation, a one-line gloss of *why*, and (mock) edge provenance (`metaphor_bridges · 14 graded paths · live`).
4. **Strength meter** — a slim gold-to-amber bar reading the *weakest hop*, with a verdict word (`SOLID` / `LEANS` / `NO BRIDGE`).
5. **Act on a result** — `Copy line` (drops `grief is a glacier — slow, inexorable, grinding what it touches` to clipboard), `Send to draft` (mock: a confirming toast), and `Grade this` (the covert eval hook — thumbs that, in the real product, write an inapt/apt label).

## How a writer acts on it

The deliverable for the writer is never the graph — it's a **line they can paste into prose**. Each result composes a suggested phrasing from the path's adjectives/relations (`destruction`, `consuming` → "consuming, leaving ash"). The graph explains; the line ships. `Send to draft` is the bridge (sorry) back to wherever the writing happens.

## How it fits the product

- **Substrate is shared with the Forge.** Same nodes (concept-senses), same edges (semantic relations + concreteness gradient). The Bridge differs only at the *traversal* layer (bidirectional A* vs the Forge's 1-hop frontier). The brief assumes the planned `metaphor` package extraction lands first; the Bridge is a thin orchestrator on top.
- **Sits on `metaphor_bridges` edges** — currently **0 rows**, so this prototype uses **plausible mock paths**. The real path comes from harvested + judged edges (`(topic_synset → vehicle_synset, live/dead, tiers[])`). Until the harvest fills, the Bridge can fall back to live A* over the property/relation graph, but the *quality* story is the graded-edge substrate.
- **M04 dependency** — M04's ANN index over `synset_centroids` *is* the Bridge's embedding-prefilter A* layer. Build M04 first → Bridge is ~1.5 days of orchestration.
- **Aesthetic** — dark cosmic + antique. Reuses `web/src/styles/tokens.css` values directly (`--colour-bg-primary #1a1a2e`, `--colour-accent-gold #d4af37`, Playfair Display / Crimson Text / JetBrains Mono). The bridge motif fits the antique-engineering register (stone piers, surveyor's strength gauge) without leaving the cosmic palette.

## Open questions for the operator

1. **Directionality.** Is `anger → fire` the same query as `fire → anger`? Bidirectional A* is symmetric, but the *prose* isn't (we say "anger is fire", rarely "fire is anger"). Do we always orient SOURCE-as-tenor, or detect and offer both readings?
2. **What does "no bridge" *mean* to a writer?** Is it "this is a bad metaphor" (a judgement they may resent) or "we don't have data" (honest but deflating)? The copy matters enormously. Current prototype hedges: *"no honest path within 3 hops — this may be a fresh metaphor we haven't mapped, or not a metaphor at all."* Too wishy-washy?
3. **Hop count ceiling.** PIPELINE says 2–3 hops covers most apt metaphors. Do we *hide* longer paths (treat >3 as no-bridge) or show them dimmed as "a stretch"? Longer paths are exactly the over-reached metaphors a writer should be warned off — but they're also where novelty lives.
4. **The grading hook.** Should the writer-facing Bridge *visibly* ask "did this land for you?" (honest, gathers gold labels, but turns the tool into a chore) or harvest the signal silently from copy/send/dismiss behaviour? The prototype shows an explicit-but-optional `Grade this`.
5. **Strength = weakest hop?** I've asserted the chain is as strong as its widest leap (matches the `max_hop_cos` geometry signal). Alternative: average-hop strength, or a learned combiner. Weakest-hop is the most *legible* to a writer ("this one stone is shaky") — is legibility worth the possible accuracy loss?
6. **Where does `Send to draft` go?** There is no draft surface in Metaforge yet. Is this a clipboard-plus, a future scratchpad panel, or an integration (Scrivener/Obsidian/Docs)? Scopes a whole sub-feature.
