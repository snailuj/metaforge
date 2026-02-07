# PRD Reconciliation Scratchpad

**Date:** 2026-02-07
**Purpose:** Capture decisions as we reconcile PRD (v1) and PRD-2, leading to a single authoritative PRD.

---

## Plan for PRD-2

1. PRD-2 becomes the single authoritative PRD
2. All parked ideas from PRD (Word Hunt, Constellations, Collections, Wormholes, Gravity, Etymology Trails, Ambient Soundscape, 3D Starfield) get copied into a "Parked Ideas" section at the end of PRD-2
3. PRD gets `git rm`'d — no idea loss

---

## Decided: Superseded by PRD-2

| PRD feature | Status |
|-------------|--------|
| 3D starfield / solar system / celestial bodies | **Parked** (not killed — may return) |
| Gravity system (frequency-based physics) | Parked |
| Word Hunt (daily quests, scoring, streaks) | Parked |
| Constellation system (personal journey map) | Parked |
| Collection system / specimen cabinet / badges | Parked |
| Wormholes (hidden connections, discovery mechanics) | Parked |
| Etymology trails (visual root traces) | Parked |
| Ambient soundscape | Parked |
| Multiplayer / leaderboards / classroom tools | Parked |
| User accounts / sync | Parked |
| Three.js / WebGPU as standalone rendering layer | **Replaced** — Three.js still used but via `3d-force-graph` |

## Decided: Carried Forward

| Element | Notes |
|---------|-------|
| Core thesaurus (search -> results -> copy) | Central to both PRDs |
| "Utility first, wonder second" | Reinforced by PRD-2 |
| Synonyms, antonyms, collocations, register, connotation | All still in scope |
| Metaphor Forge | Kept as experimental bolt-on |
| Desktop-first, browser-based | Same |
| Self-hosted, open-source (NZ Charitable Trust) | Same |
| Search always visible, always fast (<100ms) | Same |
| Keyboard navigation (`/` to focus, etc.) | Same |
| Click to copy, click to navigate | Same |
| Go backend + SQLite + embeddings | Same |
| Rarity/register badges on words | Same (once SUBTLEX-UK restored) |

---

## Decided: Stack

| Layer | Library | Role |
|-------|---------|------|
| Physics | `d3-force-3d` | Force simulation in 3D (x, y, z) |
| Rendering | `3d-force-graph` (wraps Three.js) | WebGL scene, camera, lighting |
| Camera | Built-in `fly` control type | WASD + mouse look |
| Custom nodes | `nodeThreeObject` accessor | Any Three.js object per node |
| Frontend framework | Lit (web components) + Vite + TypeScript | Same as before |

**Key insight:** No need to choose between force graph and 3D — `3d-force-graph` gives us both. The "pivot" to force graph doesn't sacrifice 3D at all.

---

## Decided: Results Panel (Ambiguous Point #1)

- **No drawer.** Keep a results panel (like PRD v1).
- Panel is a **HUD overlay** on top of the 3D WebGL canvas.
- Semi-transparent background (~60% opacity, may need tuning).
- User can see the 3D graph through the panel at all times.
- Camera controls (WASD + mouse look) remain active — panel doesn't block exploration.
- Font colours/outlines must be chosen carefully for legibility against variable 3D backgrounds.
- Fits the "look around while reading" use case.

---

## Decided: Progressive Depth Layers (Ambiguous Point #2)

Keep the layered model. Reframed for current scope:

```
Layer 0: Functional thesaurus (search -> results -> copy)
Layer 1: Force graph visualisation (same data, rendered in 3D)
Layer 2: Enrichment (rarity badges, register, connotation)
Layer 3: Metaphor Forge (experimental creative tool)
Layer 4+: [Parked — but etymology trails, constellations, and collections
            are likely fast-follows soon after MVP]
```

Principle preserved: "utility first, wonder second." Each layer works independently — if Layer 1 breaks, Layer 0 still functions.

**Near-horizon parked items** (revisit soon after MVP):
- Etymology trails
- Constellations
- Collections

**Deeper park** (revisit when demand/interest warrants):
- Word Hunt, Gravity, Wormholes, Soundscape, Multiplayer, Accounts

---

## Pending: Ambiguous Points Still to Discuss

## Decided: Interaction Model (Ambiguous Point #3)

| Action | Input | Notes |
|--------|-------|-------|
| **Select node** | Single-click | Shows tooltip/detail. Better touch compat for future mobile. |
| **Navigate to word** | Double-click node | New word becomes centre, graph reshuffles |
| **Copy word** | Right-click node | Clipboard copy, suppress context menu |
| **Move camera** | WASD keys | Fly mode, always active (except during drag / HUD hover) |
| **Look around** | Mouse move | Fly mode mouse-look |
| **Zoom** | Scroll wheel | Native `3d-force-graph` |
| **Drag node** | Click + drag node | Repositions node in simulation |
| **Search** | `/` key or click search bar | Focus search input |

**Mouse-look state management:**
- Mouse-look **disabled** when:
  - Dragging a node (re-enabled on drop)
  - Mouse is over HUD panel (re-enabled on mouse-leave)
- Mouse-look **enabled** otherwise (default state in 3D canvas area)

## Decided: Themes (Ambiguous Point #4)

**MVP theme: Dark Academic**
- Deep navy/charcoal backgrounds, warm gold accents, serif typography
- Inspired by the Alchemist aesthetic but stripped of heavy decoration
- Well-suited to 3D WebGL canvas (good contrast, atmospheric)
- Design tokens from earlier work still broadly applicable

**Second theme (future): Light / hand-drawn**
- Placeholder for a lighter skin — possibly the hand-drawn alchemical style adapted
- Explore whether Nano Banana Pro can adapt the original Alchemist concept for PRD-2's force graph
- Not MVP — marker for future refinement

**Two skins remain a goal**, just not both at launch.

## Decided: Phasing / Roadmap (Ambiguous Point #5)

**Phase 1 (MVP): Core Thesaurus + 3D Force Graph**
- Go API (already done: `/thesaurus/lookup`, `/forge/suggest`, `/strings`, `/health`)
- `3d-force-graph` + fly controls + Dark Academic theme
- HUD results panel (semi-transparent overlay)
- Search, select, navigate, copy interactions
- Rarity/register badges (needs SUBTLEX-UK)

**Phase 2: Metaphor Forge UI**
- Wire up existing `/forge/suggest` endpoint to the graph
- Forge-specific UI (source word + catalyst suggestions)
- Tier visualisation on nodes (legendary/strong/etc.)

**Phase 3: Near-Horizon Features**
- Etymology trails
- Constellations
- Collections
- Second theme (light / hand-drawn)

**Phase 4+: Deeper Park**
- Word Hunt, Gravity, Wormholes, Soundscape
- Multiplayer, Leaderboards, Accounts
- Revisit if demand/interest warrants

## Decided: Accessibility (Ambiguous Point #6)

**Principle:** HUD panel is the accessible surface. 3D graph is a visual enhancement (progressive depth — Layer 0 works without it).

**Carry forward from PRD:**

| Feature | Approach |
|---------|----------|
| Keyboard navigation | `/` focus search, `Tab` through results, `Enter` select, `Escape` close/cancel |
| Screen reader support | HUD panel uses semantic HTML + WAI-ARIA (roles, labels, live regions) |
| Reduced motion | `prefers-reduced-motion` media query — disable graph animations, transitions |
| High contrast | `prefers-contrast` media query + manual toggle |
| Colour-blind modes | Alternative colour schemes for node types (not just hue-dependent) |
| Font scaling | Respects browser zoom; HUD uses relative units (rem) |

**WAI-ARIA specifics for HUD:**
- `role="search"` on search bar
- `aria-live="polite"` on results region (announces updates)
- `aria-label` on interactive elements
- `role="region"` with label on results panel
- 3D canvas gets `role="img"` with `aria-label` describing the graph state

**Standard:** WCAG 2.1 AA as the target. Not every 3D interaction needs an accessible equivalent, but all *information* must be available through the HUD.

---

## All Ambiguous Points Resolved

Ready to proceed with:
1. Consolidate PRD-2 (add Parked Ideas section from PRD)
2. `git rm` PRD
3. Write the new frontend implementation plan against actual codebase
