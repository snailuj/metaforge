# Phrase-as-Node (sense-SET architecture) — design brief

*Status: design brief + prototype (Block 2, the load-bearing architecture upgrade). Not implemented.*
*Companion mockup: `web/prototypes/phrase-as-node/index.html` · screenshot: `/tmp/prototypes/phrase-as-node.png`*

---

## 1. The UX problem

Today **every node in Metaforge is a single-word WordNet synset.** That one
representational choice is the root of three separately-observed symptoms
(PIPELINE.md "THE UNIFYING INSIGHT" — *same disease, three sites*):

1. **Vehicle-skip.** The most evocative vehicles Phase B is now generating —
   `pressed flower`, `wax cylinder`, `supersaturation`, `groundwater`,
   `cloisonné`, `whitespace` — are multi-word or rare, so they **do not snap to
   a synset and are dropped: "no synset."** The diversity nudge is working
   precisely well enough to expose the next bottleneck: the single-word-synset
   requirement filters out exactly the live-metaphor register we want.
2. **`bad_head` (≈30/44 tagged).** A phrase is *impoverished* down to its head
   noun — `buried wound → wound`, `pressed flower → flower` — and the modifier
   that carried the metaphor is lost. This is **not** a syntactic parse error
   (the deterministic head-extractor fixes 0/44 tagged); it is the node contract
   throwing the phrase away.
3. **`merge`.** A multi-word phrase smuggled across serial single-word nodes —
   step C only follows from A+B *combined* — breaks the context-free-hop
   invariant the graph relies on.

Layered on top is a **second** representational mismatch the operator's grading
surfaced: metaphor is **sense-forgiving**. When the operator splits a node's
senses, he marks **66.6% of a lemma's WordNet senses apt** (mean 3.18 apt senses
per split, split-rate 44.5% and rising). Collapsing a word to *one* synset
throws away ~⅔ of its live sense-fertility. `glance` is not "the look (n)" — for
metaphor it is *simultaneously* the brief look (n), to glance-briefly (v), and to
glance-off at an angle (v), and several of those can be the apt image at once.

So the node is wrong **twice over**: it drops the phrase (collapses to head),
*and* it drops the sense-set (collapses to one synset). Both losses destroy
exactly the material that makes a metaphor live.

## 2. The concept

**Node contract = phrase + sense-SET.**

- The **phrase** is first-class. `pressed flower` is the node, displayed and
  graded as `pressed flower`, never silently reduced to `flower`.
- The node carries a **sense-SET**, not one synset: an ordered set of apt
  WordNet senses (the operator's "split" made durable), with the rest available
  but un-ticked. Sense becomes a *generative knob the compositor resolves at
  realisation*, not a disambiguation the pipeline must get exactly right.
- A phrase with **no synset at all** is still a first-class node, backed by a
  **FastText phrase-vector** instead of a synset id. It can be an edge endpoint,
  it can be graded, it just carries a `vec:` provenance tag instead of `syn:`.
  No more "no synset" drop.

The visual grammar in the mockup makes the contract legible at a glance:

| State | Glyph | Meaning |
|---|---|---|
| **single synset** | one solid gold ring, `syn:` | the old contract, unchanged — back-compatible |
| **sense-SET** | a ring of **petals**, lit ones = apt senses | several senses apt at once; count shown (`3 of 5 senses live`) |
| **no-synset phrase** | dashed amethyst ring, `vec:` | FastText-vector node; first-class, never dropped |
| **impoverished (legacy)** | faded head + struck-through modifier | what `bad_head` *was* — shown as the before-state we're fixing |

## 3. Key interactions

The mockup demonstrates three concrete examples end-to-end:

**A. `pressed flower` — the rescued multi-word vehicle.**
Shown in the graph as a single phrase node (not `flower`). A "before" toggle
reveals the old impoverishment (`pressed` struck through, snapping back to
`flower`). The node has no clean synset for the *phrase*, so it is a `vec:`
node — and it still becomes a first-class edge endpoint for `nostalgia → pressed
flower`. This is the vehicle-skip fix made visible.

**B. `glance` — the sense-SET.**
The grading sense-check shows the lemma fanned into its candidate senses:
`look (n) · glance-briefly (v) · glance-off (v) · skim (v) · flick-through (v)`.
The operator can tick **several at once** (this is the existing `split` verdict,
elevated from a flag to the node's actual shape). The mockup shows 3 of 5 ticked,
the petal-ring lighting up to match, and the apt set flowing straight into the
verdict payload (`apt_synset_ids: [...]`). This reuses the real sense-check
vocabulary (`right / wrong / rare_ok / unsure / split / skip` + candidate
multi-select) from `mf-grade-sensecheck.ts` — so it's the same instrument, not a
new one.

**C. `buried wound` — impoverishment caught and repaired.**
A grading card shows the chain `grief → buried wound → scar`. The middle node is
flagged `bad_head` in the old contract (impoverished to `wound`). The phrase-as-
node card restores `buried` and offers the sense-SET, turning a `bad_head` reject
into a gradeable live edge. One disease, one fix, shown at the third site.

The grading verdict flow is preserved: the sense-SET selection rides into the
verdict as `apt_synset_ids` (already the shape `mf-grade-sensecheck` POSTs for a
`split`); a `vec:` node rides as `endpoint_ref: "vec:pressed_flower"` instead of a
synset id. **No new verdict file, no change to the gold judgement schema** — the
operator north star ("grading IS Metaforge in editor mode") is respected.

## 4. How it fits the product

- **This is Block 2** in the metaphor-graph sequence (Stock Run → Remediation →
  **Phrase-as-Node** → First Completion → Compositor). It lands *before* path
  completion because the only completion signal found (`max_hop_cos` path
  geometry) reads intermediate steps, and mis-snapped steps are an uncontrolled
  variable — the steps must be sense-clean first, and the node contract decides
  how a step is represented and snapped.
- **It is the substrate, not the runtime.** The harvested edge is the *seed*; the
  **compositor** (forge runtime) realises a seed with modifiers and register. The
  sense-SET is exactly the generative latitude the compositor needs — it picks
  the apt sense per session rather than the pipeline guessing one. This is the
  forge-not-index thesis: more apt sense-edges from the same pairing is
  *generative richness*, not a disambiguation chore.
- **Back-compatible.** A plain single-synset node is just a sense-SET of size 1
  with a `syn:` ref — the old corpus reads unchanged; `emit-the-sense` already
  emits the gloss per node, so the migration is additive.

## 5. Open questions for the operator

1. **Edge keying with a sense-SET.** Does a `whisper → glance` edge become **one
   edge with an apt-set** (`{look-n, glance-briefly-v, glance-off-v}`), or **N
   sense-keyed edges** (one per apt sense)? PIPELINE leans N (per-sense edge
   splitting for completion/geometry), but the *grading verdict* is one act. The
   prototype shows one verdict producing N edges — confirm that's the contract.
2. **`vec:` nodes in path geometry.** A FastText-vector phrase has a vector
   (geometry works) but no WordNet relations (no hypernym/hyponym edges). Are
   `vec:` nodes endpoint-only, or can they be intermediate steps? (Endpoint-only
   is the conservative MVP; the mockup assumes that.)
3. **How aggressively to fan the sense-SET in the UI.** Show all WordNet senses
   for the lemma, or only the top-k by SemCor tagcount? Too many petals is noise;
   too few re-introduces the single-sense collapse. The mockup shows 5; is that
   the right ceiling, or should it be tagcount-thresholded?
4. **Phrase canonicalisation.** `pressed flower` vs `pressed-flower` vs
   `flower (pressed)` — what is the canonical key, and does the modifier order
   matter for de-duplication? (Affects edge de-dup and the harvest store.)
5. **Display in the live forge graph (non-grading).** A phrase node is wider than
   a word node; the mockup uses a pill rather than a ring for phrases. Does that
   read in a dense 3d-force-graph, or do we need a hover-expand (collapsed to
   head, expands to full phrase on focus)?
