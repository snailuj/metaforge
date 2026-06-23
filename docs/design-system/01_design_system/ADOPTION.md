# Job 1 — Adopt the unified Metaforge Design System

## Why
The repo should have **one** design system. The shipped `web/src/styles/tokens.css` has drifted:
it is **dark-only**, and visual values are likely hardcoded in places rather than pulled from
tokens. This folder's `colors_and_type.css` is the **canonical** version to converge on. The
target architecture:

- **Structural tokens** (type, spacing, radius, blur, hud sizing) live once in `:root` — theme-agnostic.
- **Every `--colour-*` token** is scoped to a theme block: `:root, [data-theme="dark"] { … }`
  and `[data-theme="parchment"] { … }`.
- **Translucent washes / hairlines / badge fills are derived** from the base tokens with
  `color-mix()` (e.g. `--hairline: color-mix(in srgb, var(--colour-accent-gold) 22%, transparent)`),
  so they re-tint automatically — you never hand-maintain a second set of rgba values.
- A skin is selected by setting `data-theme="dark" | "parchment"` on **any wrapper**; the entire
  subtree re-skins. **No component knows which theme is active** — components reference semantic
  tokens only.

## What to do

1. **Diff & reconcile tokens.** Treat the 61 custom properties below as the contract. Bring
   `tokens.css` in line with `colors_and_type.css`: same names (note the British spelling
   `--colour-*`), same structural-vs-themed split. Keep any genuinely new tokens the repo has
   added, but fold them into the same structure (themed if they're colours).

2. **Add the Parchment skin.** Port the entire `[data-theme="parchment"]` block from
   `colors_and_type.css`. Parchment overrides only `--colour-*` (plus softens `--hud-blur` to
   `blur(2px)` and warms the hairlines). Because washes are `color-mix()`-derived, nothing else
   needs a second value.

3. **De-hardcode the components.** Audit `mf-app`, `mf-results-panel`, `mf-search-bar`,
   `mf-force-graph`, `mf-toast` (and any others) for literal colours / rgba. Replace each with the
   matching semantic token (`var(--colour-bg-hud)`, `var(--hairline)`, `var(--colour-rarity-unusual)`,
   `var(--wash-gold)`, …). After this, flipping `data-theme` should reskin everything.

4. **Wire the theme switch.** Set `data-theme` on a single high wrapper (the existing `mf-app`
   shell is the natural home). The `ui_kits/web-app/` reference shows a working Dark/Parchment
   toggle.

5. **Adopt the type recipes.** `colors_and_type.css` defines reusable recipes
   (`.mf-word-hero`, `.mf-definition`, `.mf-pos`, `.mf-section-label`, `.mf-chip`, `.mf-usage`,
   `.mf-mono`). Map the `mf-*` components onto these (Playfair Display for the searched word and
   panel titles; Crimson Text for body/UI; JetBrains Mono only for the `/` hint; italics for POS
   and usage examples).

## ⚠️ Theming gotcha (do not reintroduce)
An element must not **both** declare a theme custom-property (via `data-theme`) **and** consume it
for its own `background` while a CSS `transition` is on that `background` — Chromium won't repaint
the declaring element on a theme flip (you get cream panels floating on a dark ground). Keep
`data-theme` on a **non-painting wrapper** and paint the background on an **inner element that only
inherits** the token, or simply avoid a `background`-shorthand transition on the themed root.

## Acceptance
- Every card in `preview/` renders correctly in **both** `data-theme="dark"` and
  `data-theme="parchment"` with no per-theme overrides beyond the token blocks.
- The `ui_kits/web-app/` toggle behaviour is reproduced in the real app: one attribute flip
  reskins search bar, results panel, graph HUD, toast, filters.
- No `mf-*` component contains a literal colour/rgba that should be a token.

## Token contract — the 61 custom properties
**Structural (`:root`, theme-agnostic):**
`--font-heading --font-body --font-mono`
`--text-2xl --text-xl --text-lg --text-md --text-sm --text-xs --text-2xs`
`--leading-tight --leading-normal --tracking-label --tracking-badge`
`--space-xs --space-sm --space-md --space-lg --space-xl`
`--hud-width --hud-radius --hud-blur --hud-border`
`--wash-gold --wash-gold-soft --hairline --hairline-soft` (derived via `color-mix`)

**Themed (`--colour-*`, per skin):**
`--colour-bg-primary --colour-bg-secondary --colour-bg-hud --colour-bg-hud-solid`
`--colour-text-primary --colour-text-secondary --colour-text-muted`
`--colour-accent-gold --colour-accent-gold-dim`
`--colour-node-central --colour-node-synonym --colour-node-hypernym --colour-node-hyponym --colour-node-similar`
`--colour-chip-collocation --colour-chip-antonym`
`--colour-rarity-common --colour-rarity-unusual --colour-rarity-rare`
`--colour-connotation-positive --colour-connotation-neutral --colour-connotation-negative --colour-register`
`--colour-forge-legendary --colour-forge-complex --colour-forge-interesting --colour-forge-ironic --colour-forge-strong --colour-forge-obvious --colour-forge-unlikely`
`--colour-edge-default --colour-edge-dim --colour-edge-highlight --colour-error`

> Build against **semantic tokens only**. Never guess a token name — an unresolved `var()` falls
> back silently to a browser default. The full names + values are in `colors_and_type.css`, and
> every role is explained in `DESIGN_SYSTEM_GUIDE.md`.

## Files
- `colors_and_type.css` — canonical tokens + type recipes (import of record).
- `DESIGN_SYSTEM_GUIDE.md` — the full system guide.
- `preview/` — specimen cards (visual acceptance targets).
- `ui_kits/web-app/` — reference implementation built correctly against the unified system.
- `assets/MetaforgeConcept.png` — concept art (aspirational only; not shipped).
