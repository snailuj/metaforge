# Graph-native feature specs — Bridge · Graph-nav · Forge · Phrase-as-Node

*(operator-directed spec, 2026-06-25, via Q&A after the first — rejected — round of separate-page mockups. Supersedes the standalone-surface framing in the `*-prototype.md` briefs. Prototypes must be rebuilt to THIS.)*

## Cross-cutting principles (apply to every feature)

1. **The 3D force graph is the ONLY interface.** The only other surface is the existing **collapsible ("collapso") panels**. No new full-page layouts, no separate screens. Every feature is a *behaviour of the graph* + *content in a panel* + at most a *filter-row control*.
2. **Cinematic.** It must feel like navigating a 3D world — a game, not "a web 2.0 app with lipstick." High production value. **⇒ Prototypes are built on the REAL 3D engine** (`3d-force-graph` / three.js), not flat HTML/SVG.
3. **The Thesaurus always functions** — unchanged — in every mode (standard / Forge / Bridge). Base graph behaviour is always-on; features layer over it, never replace it.
4. **Reuse the tuned UI.** Top-left **collapsible info panel** (focused word + COMMON/UNUSUAL/RARE badge, POS, definition, relation groups `BROADER TERMS` / `SIMILAR` with clickable terms); centre-top **search bar** (`/` shortcut); the **Common / Unusual / Rare** rarity filter; **WASD/QE flight**; DOM labels; gold focused node; dark cosmic + antique palette (`web/src/styles/tokens.css`).
5. **Public / non-privileged surfaces only.** No grading-tool wiring at this stage.

## A. The Bridge (source → target)

- **Invoke — hybrid dual-search.** Completing a word in the **first** search field pans that node (the **topic**) into view and selects it. A **"to…"** field specifies the second word (the **vehicle**); completing it pans the vehicle into view and selects it. Both nodes are now selected. **The prototype's job is to answer "how do we show this?"** — the dual-selection + camera-pan choreography.
- **Render the path — light up the current constellation.** Both endpoint nodes render *just like the Thesaurus* — i.e. **all** their edges (synonyms, hyponyms, etc.), not only the metaphor path. Metaphor-path edges get a **special linkage outline** AND the edge itself **behaves obviously differently** from synonyms/hyponyms (e.g. curved instead of straight, dashed instead of solid). **If there is more than one path between topic and vehicle, render them all.**
- **Justification — edge labels only.** The "why this hop" sits on the edge; no panel involvement.
- **No / weak bridge — stay unconnected + status.** The nodes don't link; a status line explains there's no strong path.

## B. 3D graph navigation + 2nd-order edge nodes (the cinematic base)

- **2nd-order = both** relationship-as-a-node (bridge nodes — the "gravity well (JOY)" motif) **and** neighbours-of-neighbours. **Not** a hard 2-hop lock: render a **fog-of-war** that fades nodes (and their edges) with distance, going **invisible beyond ~2–3 hops**, to keep the scene legible.
- **Reveal — bloom on approach/focus.** A node's further neighbours expand in as you focus / fly near it.
- **Select a node — fly to it + bloom.** The camera travels to the node and its neighbours expand in; **the current world persists** (the thesaurus keeps functioning — no hard scene reset).
- **Camera — free flight + click-to-fly.** Keep WASD/QE manual flight **and** let the camera auto-travel to a clicked node.

## C. Forge UI (session-conditioned generation)

- **Candidates — both.** Forged vehicles bloom as **nodes** attached to the topic node in the graph **and** appear as **ranked detail in the panel**.
- **Sensibility knobs — sliders in a collapsible panel.**
- **Knobs for v1 — Register · Darkness · Surprise.** (Concreteness dropped for v1.)
- **Input — single topic now, blend as a visible "+ add".** Forge from one topic; a discoverable "+ blend" affordance adds a second topic.

## D. Phrase-as-Node (public surface)

- **Visibility — Forge / Bridge only.** The plain thesaurus stays mostly single-word; phrase nodes surface when forging/bridging.
- **Phrase node visual — a wider pill/label, fed by its parts.** It carries **incoming edges from the subject, object, verb and modifiers** (the phrase node aggregates its constituent words compositionally).
- **Senses — lemma as a central body with sense sub-nodes orbiting it.** **Do NOT fabricate edges** linking the senses to the central body or to each other — *except* in the rare cases where a real link exists (derived from thesaurus / forge / bridge).
- **`vec:` phrases (no WordNet synset, e.g. "pressed flower") — Forge/Bridge only for now.** Appearing in the normal thesaurus graph is **possible future work, scoped separately.**

---

*Build note: the four `web/prototypes/<feature>/` flat mockups + their `docs/designs/*-prototype.md` briefs were the first (rejected) round — kept for the ideas, but the build target is now graph-native on the real engine per the above.*
