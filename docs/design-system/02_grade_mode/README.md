# Handoff: Grade Mode (Metaforge)

## Overview
**Grade Mode** is a keyboard-first reviewing surface for grading *generated metaphors* — the
exemplar-collection tool that sits alongside the shipped **Browse** (thesaurus) mode. A metaphor
is a **chain**: a path from a source word across a few associative "bridge" steps to a target
word, e.g. `anchor → prevents drift → holds everything together → keystone`. The grader walks a
queue of candidate metaphors and assigns each a verdict; the graph behind the HUD lights the
chain under review and leaves coloured trails for everything already graded.

It is the inverse toggle of Browse: the live app's top-right pill reads **"Grade mode"**; inside
Grade Mode it reads **"Browse mode"**.

## About the design files
The files in this bundle are **design references implemented in HTML/React-JSX** — a faithful,
interactive prototype showing intended look and behaviour. They are **not** production code to
drop into the repo. The real product (`snailuj/metaforge`) is **Lit + TypeScript** with
components like `mf-app`, `mf-results-panel`, `mf-search-bar`, `mf-force-graph`, `mf-toast`.
The task is to **recreate this prototype as new Lit components** (`mf-grade-panel`,
`mf-grade-queue`, a Grade-mode branch in `mf-app`) using the repo's existing patterns, the real
`3d-force-graph`/Three.js renderer, and the canonical tokens in `web/src/styles/tokens.css`.

The prototype's 2D `GraphForge` is a **stand-in** for the shipped 3D graph — do not port it.
Reuse the real force graph and only add the Grade-mode overlays described under *Graph encoding*.

## Fidelity
**High-fidelity.** Final colours, typography, spacing, copy, interactions and keyboard model are
all intentional and should be reproduced precisely. Every colour is a design-system token — no
invented values. Where the prototype hand-rolls a value (a few gem-gradient stops), it is called
out below and should map to the nearest token in the real renderer.

---

## Screens / Views

### 1. Grade Mode (default view)
**Purpose:** grade a queue of generated metaphors, fast, by keyboard.

**Layout** — full-viewport fixed canvas (`overflow:hidden`, `touch-action:none`), the force graph
filling the whole viewport, with absolutely-positioned frosted HUD overlays:

- **Queue bar** — top-left (`top:1rem; left:1rem`). A vertical stack:
  - A segmented filter pill `[ Both | Ungraded | Graded ]` (frosted, gold hairline; selected
    segment = solid `--colour-accent-gold` ground with `--colour-bg-primary` text).
  - A progress line below it: `<gold>N</gold> / <total> graded` in `--colour-text-secondary`.
- **Mode toggle** — top-right (`top:1rem; right:1rem`), inline row: the Dark/Parchment theme
  toggle, then the **"Browse mode"** pill (`--wash-gold` ground, `--colour-accent-gold` text +
  1px gold border, `backdrop-filter: var(--hud-blur)`).
- **Rarity filters** — bottom-left (`bottom:2rem; left:1rem`), the existing
  Common/Unusual/Rare tinted checkboxes (`mf` RarityFilters), unchanged.
- **Grading panel (HUD)** — right rail. `top: calc(1rem + 3.5rem)`, `right:1rem`, `bottom:2rem`,
  width **23rem**, internal scroll with the thin gold scrollbar. Frosted glass:
  `background: var(--colour-bg-hud)`, `border:1px solid var(--hairline)`,
  `border-radius: var(--hud-radius)` (4px), `backdrop-filter: var(--hud-blur)`, padding ~1rem.
  Contents, top→bottom:
  1. **Re-grading banner** (only if this metaphor was already graded) — see Interactions.
  2. **Chain readout** — the metaphor under review, inline-wrapping, `--font-body` ~1.02rem,
     line-height 1.5, with a bottom hairline divider. Source word = `--colour-accent-gold`
     weight 600; target word = `--colour-chip-collocation` (slate-blue) weight 600; bridge
     steps = `--colour-text-secondary` *italic*; separators are ` → ` in `--colour-accent-gold-dim`.
  3. **Axis rows** — each is a label column (`flex: 0 0 4.6rem`, `--text-xs`, UPPERCASE,
     `letter-spacing: var(--tracking-label)`, `--colour-text-muted`) + a body column:
     - **METAPHOR** — three equal segmented buttons: `Live [L]` · `Dead [D]` · `Irrelevant [I]`.
     - **LINKAGE** — two equal segmented buttons: `Good (default)` · `Bad [B]`. Defaults to Good.
     - **TIER** — three pills (not segmented): `strong` · `ironic` · `surprising`. Single-select,
       toggle-off allowed (optional axis).
     - **CONFIDENCE** — three equal segmented buttons: `High [1]` · `Med [2]` · `Low [3]`.
  4. **Issue tags** — a wrap of four rounded pills: `merge` · `padding` · `leap` · `other`.
     Multi-select.
  5. **Note** — a `<textarea>`, placeholder `optional note — public repo, no secrets`,
     translucent dark fill, gold-hairline border, resizable vertically.
  6. **Footer row** — `Skip [S]` (ghost button) + `Save & next [↵]` (solid gold button;
     disabled/dimmed to 45% until a METAPHOR verdict is set).

### 2. Browse Mode (the shipped thesaurus — included for parity)
The existing Lookup/Explore app: centred top **search bar** with `/` hint + autocomplete,
**rarity filters** below it, left **results panel** (`mf-results-panel`), the force graph, and a
top-right **"Grade mode"** pill that returns to Grade Mode. No changes beyond wiring the toggle.

---

## Component → real-codebase mapping

| Prototype file | Real target |
|---|---|
| `app.jsx` (App) | a Grade-mode branch in `mf-app` (mode state, queue state, keyboard, edge-tint computation) |
| `GradingPanel.jsx` | **new** `mf-grade-panel` Lit component |
| queue bar + progress (in `app.jsx`) | **new** `mf-grade-queue` (or part of `mf-app` chrome) |
| `GraphForge.jsx` | **do not port** — reuse the shipped `mf-force-graph`; add the overlays in *Graph encoding* |
| `SearchBar.jsx`, `RarityFilters.jsx`, `ResultsPanel.jsx`, `Toast.jsx` | already exist as `mf-*` components — reuse as-is |
| `lexicon.js` | the real lookup API |
| `data-metaphors.js` | the real generated-metaphor + grade API (see *Data model*) |

---

## Interactions & Behaviour

**Keyboard (Grade Mode only; ignored while a text field is focused, where `Esc` blurs it):**
- `L` / `D` / `I` → set METAPHOR to live / dead / irrelevant
- `B` → toggle LINKAGE Good ⇄ Bad
- `1` / `2` / `3` → set CONFIDENCE high / med / low
- `S` → skip (advance without saving)
- `Enter` → **Save & next** (commits the working grade; no-op until METAPHOR is set)
- `←` / `→` (or `J` / `K`) → previous / next item in the filtered queue

TIER and issue-tags are click-only in the prototype — **open question**: bind keys for them too?
(Suggested: `Z/X/C` for tiers, `M/P/.../O` for tags — confirm with the product owner.)

**Save & advance.** On commit, the working grade is stamped with `at = new Date().toISOString()`
and written to the grades map; a toast fires `Graded "<source> → <target>"`; the queue advances
to the **next still-ungraded** item in the current filter (wrapping), or clamps at the end.

**Re-grading banner.** When the current item already carries a grade, the panel shows a
gold-bordered callout (`border:1px solid color-mix(in srgb, var(--colour-accent-gold) 45%, transparent)`,
`background: var(--wash-gold-soft)`), text in `--colour-text-secondary`:
> Re-grading — your previous verdict was **good linkage** / **live metaphor** at 31 May 2026 · 21:00.

The two verdict words are coloured by their axis token (linkage good→gold/bad→rose;
metaphor live→green/dead→rose/irrelevant→muted). Timestamp formatted en-GB
(`D Mon YYYY · HH:MM`). The panel also **pre-fills** all axes from the committed grade.

**Filters.** `Both` = whole queue; `Ungraded` = `grade == null`; `Graded` = `grade != null`.
Changing the filter resets the index to 0. Empty filter → a frosted "Nothing here — every
metaphor in this filter is done." panel in the right rail.

**Graph pan/zoom** (real app): keep the shipped 3D controls. The prototype's hint copy is
`Drag to pan · scroll to zoom · left-click a node to look up · right-click to copy`.

**Motion.** Per the DS: no bouncy easing. Toast = 200ms opacity fade. Selection state changes
~130ms. The force graph's settling is physical (the real renderer already handles this).

---

## Graph encoding (Grade-mode overlays on the real force graph)

The graph shows the **source word's generation graph** (nodes = words, rarity-tinted; central
source node gold). Grade Mode adds three overlays:

1. **Target rings.** Every metaphor's target node gets a thin ring in
   `--colour-chip-collocation` (slate-blue), radius ≈ node + 4.5px, 1.4px stroke, ~85% opacity.
2. **Active path.** The edges along the **current** item's `path` light up, coloured by the
   working grade (see resolver below), bright (full opacity, +weight, soft glow).
3. **Trails.** For every *other already-graded* metaphor, its `path` edges take a **faint**
   (~40% opacity) tint of that grade's colour, so the graph accumulates a history.

**Edge-colour resolver** (given a grade):
```
no metaphor verdict yet        → 'active'      → var(--colour-rarity-unusual)   (copper)
linkage === 'bad'              → 'dead'        → var(--colour-chip-antonym)     (dusty rose)
metaphor === 'live'            → 'live'/'good' → var(--colour-forge-interesting)(forest green)
metaphor === 'dead'            → 'dead'        → var(--colour-chip-antonym)     (dusty rose)
otherwise (irrelevant)         → 'irrelevant'  → var(--colour-text-muted)       (muted)
```
Precedence: current item's active path overrides any trail on the same edge. Default ungraded
edges use `--colour-edge-default`.

**Node rendering note (prototype only):** `GraphForge` fakes 3D gem nodes with radial-gradient
fills (gold/sage/copper/lilac stops) + a gloss highlight + contact shadow. The **real renderer
already draws the gem nodes** — don't reproduce the gradients; just apply the ring + edge tints.

---

## State management

- `mode`: `'grade' | 'browse'` (default `'grade'` for this surface).
- `theme`: `'dark' | 'parchment'`.
- `filters`: `{ common, unusual, rare }` booleans (shared rarity filter).
- **Grade mode:**
  - `grades`: `Map<metaphorId, Grade | null>` — committed verdicts, seeded from the API.
  - `qfilter`: `'both' | 'ungraded' | 'graded'`.
  - `idx`: index into the *filtered* queue.
  - `draft`: the working grade for the current item (seeded from its committed grade or blank
    `{ tags: [] }` when the current item changes).
  - derived: `filtered` (queue ∩ filter), `current` (filtered[idx]), `pathEdges` / `trailEdges`
    (from `grades` + `draft`), `gradedCount`.
- **Browse mode:** `bResult` (current lookup), `collapsed` (results-panel toggle).

### Data model
```ts
type Grade = {
  metaphor: 'live' | 'dead' | 'irrelevant';
  linkage:  'good' | 'bad';            // defaults to 'good'
  tier:     'strong' | 'ironic' | 'surprising' | null;
  confidence: 'high' | 'med' | 'low' | null;
  tags:     ('merge'|'padding'|'leap'|'other')[];
  note:     string;
  at:       string;                    // ISO 8601, set on commit
};
type Metaphor = {
  id: string;
  source: string; target: string;
  chain: string[];   // human-readable: [source, ...bridges, target]
  path:  string[];   // graph node ids whose connecting edges light up
  grade: Grade | null;
};
```
`chain` drives the readout; `path` drives the graph edges. They are distinct: `chain` has prose
bridge phrases, `path` has the node ids those bridges traverse.

---

## Design tokens (all from `web/src/styles/tokens.css` / `colors_and_type.css`)

**Type:** `--font-heading` Playfair Display (source word, panel titles) · `--font-body`
Crimson Text (everything else) · `--font-mono` JetBrains Mono (keyboard hints only).
Sizes via `--text-*`. Italics carry meaning (bridge steps, POS, usage).

**Colour roles used by Grade Mode:**
| Role | Token |
|---|---|
| Page ground | `--colour-bg-primary` |
| HUD glass / solid | `--colour-bg-hud` / `--colour-bg-hud-solid` |
| Accent / source node / commit button | `--colour-accent-gold` (+ `--colour-accent-gold-dim`) |
| Hairlines / washes | `--hairline`, `--hairline-soft`, `--wash-gold`, `--wash-gold-soft` |
| METAPHOR live | `--colour-forge-interesting` (green) |
| METAPHOR dead · LINKAGE bad · antonym edges | `--colour-chip-antonym` (rose) |
| METAPHOR irrelevant / trails-muted | `--colour-text-muted` |
| LINKAGE good | `--colour-accent-gold` |
| TIER strong | `--colour-forge-strong` |
| TIER ironic | `--colour-forge-ironic` |
| TIER surprising | `--colour-forge-complex` |
| Active path edge | `--colour-rarity-unusual` (copper) |
| Target ring / collocation | `--colour-chip-collocation` (slate-blue) |
| Rarity common/unusual/rare nodes | `--colour-rarity-common` / `-unusual` / `-rare` |
| Default / dim edges | `--colour-edge-default` / `--colour-edge-dim` |

> **Tier→colour is a design decision made here, not canonical.** The DS defines seven forge
> tiers; this tool exposes only strong/ironic/surprising and maps them to forge tokens. Confirm
> if the product owner wants the full seven-tier vocabulary instead.

**Radius:** `--hud-radius` (4px) on panels/inputs/segmented buttons; pills are fully rounded
(999px); badges 8px. **Shadows:** none — elevation is blur + translucency + gold hairline only.

---

## ⚠️ Theming gotcha (carried over from the prototype)
An element must not **both** declare a theme custom-property (via `data-theme`) **and** consume
it for its own `background` while a CSS `transition` is on that property — Chromium won't repaint
the declaring element on theme flip (cream panels float on a dark ground). Fix used here: put
`data-theme` on a **non-painting wrapper**, and paint the background on an **inner element that
only inherits** the token (no `background` transition on the declaring element). The real app's
token architecture already scopes `data-theme` to a wrapper, so this should be a non-issue if you
follow the existing `mf-app` pattern — just don't add a `background`-shorthand transition to the
themed root.

---

## Copy (verbatim, en-GB, sentence case)
- Filters: `Both` · `Ungraded` · `Graded`
- Progress: `{N} / {total} graded`
- Mode pills: `Browse mode` / `Grade mode`
- Axis labels (UPPERCASE): `METAPHOR` · `LINKAGE` · `TIER` · `CONFIDENCE`
- METAPHOR: `Live` · `Dead` · `Irrelevant` · LINKAGE: `Good (default)` · `Bad`
- TIER: `strong` · `ironic` · `surprising` · CONFIDENCE: `High` · `Med` · `Low`
- Tags: `merge` · `padding` · `leap` · `other`
- Note placeholder: `optional note — public repo, no secrets`
- Buttons: `Skip` · `Save & next`
- Toasts: `Graded "{source} → {target}"` · `Skipped` · `Copied "{word}"`
- Re-grading: `Re-grading — your previous verdict was {linkage} linkage / {metaphor} metaphor at {date}.`
- Empty: `Nothing here — every metaphor in this filter is done.`
- Graph hint: `Drag to pan · scroll to zoom · left-click a node to look up · right-click to copy`

## Screenshots (`screenshots/`)
- `grade-mode.png` — Grade Mode, dark, an ungraded item under review (copper active path).
- `grade-mode-regrading.png` — the Graded filter: Re-grading banner + pre-filled axes, green good/live trail.
- `browse-mode.png` — Browse Mode (the shipped thesaurus) for parity reference.
- `grade-mode-parchment.png` — Grade Mode in the Parchment skin (token swap only).

## Assets
None. No images, no icon set, no emoji (per the DS). The only "icons" are Unicode glyphs:
`→` (chain), `›` (node label affordance), `↵` (commit key hint), `«`/`»` (panel collapse).
Fonts load from Google Fonts via `@import` in `colors_and_type.css`.

## Files in this bundle
- `Grading Mode.html` — entry point; wires the scripts together.
- `app.jsx` — App shell: mode toggle, queue, keyboard, edge-tint computation, Browse wiring.
- `GradingPanel.jsx` — the right-rail grading HUD.
- `GraphForge.jsx` — 2D force-graph **stand-in** (reference for overlays only; do not port).
- `data-metaphors.js` — sample `anchor` graph + grading queue (mirrors the *Data model*).
- `SearchBar.jsx` · `RarityFilters.jsx` · `ResultsPanel.jsx` · `Toast.jsx` — DS components, reused.
- `lexicon.js` — sample lexicon for Browse + graph.
- `colors_and_type.css` — the design-system tokens (import of record).
