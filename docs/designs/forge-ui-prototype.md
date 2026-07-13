# Forge UI — session-conditioned generation front-end

*Design brief + prototype walkthrough · 2026-06-24*

Prototype: `web/prototypes/forge-ui/index.html` (single-file, no-build, mock data)
Screenshot: `/tmp/prototypes/forge-ui.png`

---

## 1. The UX problem

Metaforge's product thesis is **forge, not index**. Metaphors are *positional goods*:
the value of a fresh topic→vehicle image collapses the moment it is published as a
list and everyone reaches for the same one (rust-to-cliché). So the Forge must **not**
present as a search box over a static dictionary of metaphors. It has to feel like an
**instrument a writer plays** — one that produces images *conditioned on this session*
(this topic, this blend, this mood) that no other writer will have generated in quite
the same configuration.

The design problem, concretely:

- A search box invites the wrong mental model ("look up the answer"). We want
  "compose a request, then steer the results until one lands."
- The differentiator is **session conditioning** — a second-topic **blend** and a set
  of **sensibility knobs** (register, concreteness, surprise, darkness). These have to
  feel *load-bearing and live*: turning a knob must visibly reshape the candidate set,
  not just re-sort it.
- Each candidate is a **topic→vehicle image** plus a one-line read of *why it lands*.
  The writer needs to triage fast: most are skimmed, one or two stop the eye.
- The **keep / dismiss / refine** loop is the whole point twice over. For the writer
  it is how they curate toward a usable image. For the product it is the **invisible
  bootstrap signal** — the kept set is supervision for the distilled taste-judge, and
  it must *never* read as "you are training our model", just "you are keeping the good
  ones."

## 2. The concept

A two-column writer's console on the dark-cosmic / antique palette.

**Left — the Forge bench (the request you compose).**
- A primary **Topic** field (gold), the thing you are writing about.
- An optional **Blend** field (copper) — a second topic the Forge folds in. Blend is
  the headline differentiator: `grief × tide` produces a different field of images than
  `grief` alone. A clear `⌥ blend off` affordance makes the single-topic case first-class.
- Four **sensibility knobs** as horizontal sliders with named poles, not numbers:
  - **Register** — plain ↔ ornate
  - **Concreteness** — abstract ↔ tactile
  - **Surprise** — expected ↔ uncanny
  - **Darkness** — luminous ↔ shadowed
  Each knob shows a one-word *live read-out* of where it sits ("tactile", "uncanny").
  Moving a knob re-renders the candidate column immediately — the instrument responds.
- A **Forge** action (the primary gold button) and a quiet "the judge gated N dim ones"
  line so the taste-gate is felt but never in the way.

**Right — the candidate column (what the Forge returns).**
Each candidate is a card:
- The **image** rendered as `topic → vehicle` in display type, with the blend shown as
  a faint provenance when active (`grief ×tide → undertow`).
- A **one-line read** — the Forge Reader's voice, *why this lands* ("the pull that
  takes you out past your depth without a sound").
- A **tier ribbon** drawn from the real classifier vocabulary
  (*legendary / strong / ironic / complex*) plus a thin **aptness meter**.
- Three actions on every card: **Keep** (✓), **Dismiss** (✕), **Refine** (↻ "more
  like this"). Keep slides the card into a **Kept rail** at the bottom; dismiss fades
  it and frees the slot; refine re-seeds the knobs toward that card's character and
  re-forges.

**Bottom — the Kept rail.**
A horizontal shelf of the images the writer has kept this session, each a compact
`topic→vehicle` token they can copy into a draft. A quiet note frames it honestly:
*"Your kept set stays yours — it quietly teaches the Forge your taste."* This is the
invisible bootstrap, surfaced as a benefit to the writer, never as labelling work.

## 3. Key interactions (what the prototype demonstrates)

1. **Forge** — type a topic (optionally a blend), hit Forge → the candidate column
   populates with staggered reveal. Three worked examples are wired:
   `grief`, `grief × tide`, and `the city × a wound`.
2. **Knobs reshape live** — dragging *Surprise* toward *uncanny* or *Darkness* toward
   *shadowed* swaps in different candidates and re-reads the meters, demonstrating that
   conditioning is continuous, not a filter toggle. (Mock: knob position selects among
   pre-authored candidate sets so the reshaping is legible.)
3. **Blend on/off** — toggling the blend field rewrites the images (`undertow` only
   appears when `tide` is folded in) so the differentiator is unmistakable.
4. **Keep / dismiss / refine** — keep pushes a token onto the Kept rail and shows the
   running "teaching the Forge" line; dismiss frees the slot; refine nudges the knobs
   toward the card and re-forges around it.

## 4. How it fits the product

- **Endpoint.** Sits on the existing cascade `GET /forge/suggest` (`api/internal/handler`,
  `forge.Match`). The card's image = `Word`; the tier ribbon = `forge.Tier`
  (`legendary/complex/ironic/strong/unlikely`); the one-line read is *new* copy the
  distilled judge / generator must produce (today's `SharedProperties` is the
  placeholder mechanism behind it).
- **Conditioning is the new contract.** Topic is `word` today. **Blend** and the four
  **knobs** are *new request parameters* the generator must consume — this prototype is
  partly a spec proposal for what `/forge/suggest` (or a successor `/forge/generate`)
  should accept. Knobs map naturally onto generation controls, not onto the cascade's
  property filter.
- **The judge gates, the rail teaches.** The "gated N dim ones" line is the distilled
  taste-judge culling below threshold (Stage-2 liveness, currently κ 0.332 — marginal).
  The **Kept rail** is the edge-harvest substrate: each keep is a candidate
  `metaphor_bridges` row `(topic_synset → vehicle_synset, live, tiers[])` — supervision
  that *learns from* edges and never *serves* them. Forge-not-index, end to end.
- **Aesthetic.** Reuses `web/src/styles/tokens.css` verbatim (gold `#d4af37`, copper
  `#c4956a`, bg `#1a1a2e`/`#16213e`, Playfair/Crimson/JetBrains Mono), the starfield,
  and the same console chrome as the Bridge and Graph-Nav prototypes.

## 5. Open questions for the operator

1. **Knobs vs. presets.** Four continuous sliders are expressive but can paralyse. Do
   we ship continuous knobs, or named **moods** as presets ("noir", "elegiac",
   "clinical") that *set* the knobs — with the sliders as an "advanced" reveal? The
   prototype shows continuous; presets may be the better first run.
2. **Does Blend earn its slot in v1?** Blend is the strongest expression of
   forge-not-index, but it doubles the request surface and the generator cost. Ship
   single-topic-only first and add blend once the judge is trusted, or lead with blend
   as the headline?
3. **What is the one-line read, mechanically?** It is the most product-defining copy on
   screen. Generated per-candidate by the model (cost, latency)? Or templated from the
   bridge's intermediate hops? It cannot be the raw `SharedProperties` list — that reads
   like debug.
4. **Refine semantics.** "More like this" could mean (a) nudge the knobs toward the
   card and re-forge, or (b) hold the vehicle's *domain* and vary the image, or (c)
   keep the image and offer phrasings. The prototype shows (a); (b)/(c) may be more
   useful to a writer mid-sentence.
5. **How visible should "teaching the Forge" be?** Naming it builds trust (your taste,
   your tool) but risks the *tagging-fear* failure mode (writers self-censor what they
   keep if they think it is published/observed). Confirm the framing: *kept set is
   private to the session/account, never a public list.*
6. **Tier vocabulary on the writer's surface.** `legendary/ironic/complex` is fun but
   editorial. Do writers want the tier label at all, or just the aptness meter + the
   read? (Internally the tier still drives ranking.)
