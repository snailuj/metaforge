# Design brief — 3D Graph Navigation + 2nd-Order Edge Nodes

*Prototype: `web/prototypes/graph-nav/index.html` (no-build, mock data). Screenshot: `/tmp/prototypes/graph-nav.png`.*
*Status: design exploration — something concrete to react to, not a plan of record.*

---

## The UX problem

Metaforge's graph view (`web/src/components/mf-force-graph.ts`) renders a word's
neighbourhood as a 3D force-directed constellation. Two needs collide there, and
the prototype shows one answer that serves both:

1. **2nd-order edge nodes (MVP-required "2nd-Order Edge Node Rendering").** A
   thesaurus neighbourhood is more than first-hop synonyms. The interesting
   structure is *edges of edges* — what a neighbour is itself related to — and,
   for Metaforge specifically, **bridge nodes: a node that is itself a
   relationship** ("melancholy → JOY *via the gravity-well bridge*", the
   "gravity well (JOY)" object already drawn in `MetaforgeConcept.png`). Dump all
   of that into the scene at once and you get hairball: the writer loses the word
   they came for. So the question is *how 2nd-order and bridge nodes appear
   without clutter, and expand only on demand.*

2. **An accessible, keyboard/touch-navigable path through the scene.** Today the
   WebGL `<canvas>` is a black box to the keyboard and to assistive tech — you
   cannot Tab to a node, there is no focus ring, nothing is announced. The UX
   review flagged this, and it bites the operator directly: he works on mobile
   via remote control, where orbiting a 3D camera with a thumb is miserable. We
   need a **linear "walk the graph" affordance** — next/prev through the
   neighbourhood with a visible focus ring and an `aria-live` readout of *where
   you are* — that is simultaneously (a) the AT fallback and (b) a genuinely nicer
   way to explore on a phone.

These are one feature because the linear walk is *also* how you discover and
expand 2nd-order nodes without a mouse: stepping onto a node reveals its
second-order ring; the same gesture works for sighted-mouse, keyboard, and touch.

## The concept

**One graph, two synchronised faces.** The spatial constellation (left) and a
linear, fully accessible **"walk" list** (right) are two renderings of the *same*
small graph with a *single shared cursor*. Move the cursor in either face and the
other follows. The list is not a degraded fallback bolted on afterwards — it is a
first-class navigator that happens to also satisfy WCAG.

Three node *orders*, drawn with decreasing prominence so the eye keeps the word
it came for:

- **Central (order 0)** — the looked-up word. Gold, glowing, centre (`--colour-node-central #d4af37`).
- **First-order (order 1)** — direct relations on the inner orbit. Coloured by
  relation type (synonym copper, hypernym russet, hyponym green, similar violet).
- **Second-order (order 2)** — relations-of-relations. **Hidden by default**,
  shown as a faint count badge on their first-order parent ("+4"). They fan out
  on demand into a dim outer arc, never competing with order-1 for attention
  (mirrors today's `EDGE_COLOUR_DIM` / `linkWidth 0.5` treatment for order-2 in
  the real component).

**Bridge nodes** are the special case the product cares about: a node that *is* a
relationship. Drawn as a distinct **lozenge / diamond** (not a disc) sitting *on*
the edge it represents, with a one-line gloss ("a metaphor bridge: melancholy
weighs like JOY's gravity well"). They read as "this connection is itself a
thing you can stand on", which is exactly the forge's mental model.

### Expand-on-demand, three ways in

| Gesture | Spatial face | Linear face |
|---|---|---|
| **Reveal 2nd-order** | click/tap a first-order node's "+N" badge | press **E** / tap **Expand** on the focused row; children inject as indented child rows |
| **Walk** | — (orbit with mouse) | **↓/↑** or **Next/Prev** moves the cursor; **Home** returns to centre |
| **Cross a bridge** | click the lozenge | **Enter** on a bridge row "crosses" it, re-centring on the far node |

Every cursor move fires an **`aria-live` position readout**: *"melancholy,
central node. 5 direct relations. Currently on 'sorrowful', synonym, 2 of 5.
Press E to reveal 4 further relations."* That sentence is the whole accessibility
story in one string — order, role, position-in-ring, and the available next move.

## Key interactions (what the prototype demonstrates)

- **Shared cursor** — focus ring is identical in both faces; arrow-keys and the
  list buttons drive both; clicking a spatial node selects the matching list row.
- **Progressive disclosure of order-2** — order-2 nodes start collapsed behind a
  count badge; expand fans them into a dim outer arc *and* injects indented child
  rows; collapse removes both. No re-layout thrash of the order-1 ring.
- **Bridge crossing** — the gravity-well bridge from the concept art is a
  first-class, focusable lozenge; "crossing" it re-centres the graph.
- **`aria-live` readout** — a visually-styled-but-screen-reader-authoritative
  status line announces every move; `role=tree` semantics on the list, `aria-expanded`
  on nodes with hidden children, roving `tabindex`.
- **Three concrete examples** — *melancholy* (emotion, the concept-art case, with
  a JOY gravity-well bridge), *anchor* (concrete noun → ship/security/tattoo
  hyponyms, a "hold ↔ heaviness" bridge), and *forge* (the product's own verb,
  bridging to "crucible"). A small example switcher swaps the dataset.

## How it fits the product

- **Replaces nothing yet; informs `mf-force-graph.ts`.** The real component
  already distinguishes `order: 0|1|2` (`GraphNode.order`) and already dims
  order-2 edges. What it lacks is (a) the collapse/expand state machine for
  order-2, (b) any non-canvas navigator, and (c) bridge-node rendering. This
  prototype is the target those three should aim at.
- **Bridge = `metaphor_bridges`.** The lozenge maps onto the bridge-centric
  schema already landed (`metaphor_graph_schema_base_landed`) and the
  path-geometry signal work — a bridge node is a materialised metaphor edge with
  a head/gloss. The graph view becomes the place a writer *encounters* a forged
  metaphor, not just a thesaurus.
- **Accessibility is a product constraint, not a nicety.** The schools/colleges
  market (`product_constraints_education_sovereignty`) needs AT-reachable UI;
  the operator's mobile-remote workflow needs touch-first navigation. The walk
  list pays both.
- **Aesthetic continuity** — reuses the dark cosmic + antique tokens verbatim
  (`web/src/styles/tokens.css`): `#1a1a2e` ground, gold `#d4af37` centre, copper
  `#c4956a` synonyms, Playfair/Crimson type. The gravity-well bridge is the same
  motif as `MetaforgeConcept.png`.

## Open questions for the operator

1. **List-first or canvas-first on mobile?** The real component already drops to a
   flat fallback below 900px (`threeDLoaded`). Should the **walk list become the
   *primary* mobile view** (canvas as optional eye-candy), given orbiting on a
   phone is the pain point — or keep canvas primary with the list as a drawer?
2. **How many 2nd-order nodes before we summarise?** A high-degree word
   ("light", "run") could have hundreds of order-2 nodes. Cap the fan at *N* and
   show "+213 more →" that opens a filtered sub-search? What's the cap?
3. **Are bridges always visible, or also progressive?** Drawing every metaphor
   bridge could itself be clutter. Show bridges only when one endpoint is
   focused/expanded, or always-on as "constellation lines"?
4. **Does "crossing a bridge" navigate (re-centre) or just preview?** Re-centring
   loses your place in the current neighbourhood; a preview/peek keeps context but
   adds modality. The prototype assumes re-centre — is that right?
5. **Roving focus vs. live filter interplay.** The real component has a
   rarity/path visibility filter. When a node is hidden by the filter, should the
   walk cursor skip it silently, or announce "hidden by filter"?
6. **One readout string or two?** Should the `aria-live` line and the visible
   status line carry identical text (simpler), or should the visible line be
   terser with the verbose version reserved for AT?
