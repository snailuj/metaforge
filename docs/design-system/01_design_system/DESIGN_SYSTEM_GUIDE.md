# Metaforge — Design System

> A browser-based **visual thesaurus and metaphor generator**. Search a word and it blooms into a cluster of connected meanings — synonyms, antonyms, collocations, connotations, and usage examples — rendered as a springy, force-directed graph you can fly through. Click a neighbouring node and the whole graph reshuffles around it.

Metaforge is the spiritual successor to the much-missed **Visual Thesaurus**. It is **open-source, CC-BY-SA, runs no LLMs at runtime, ships zero trackers, and is safe for all ages.** The hosted app is operated by a New Zealand Charitable Trust — revenue covers servers only, no commercial ambitions.

This design system captures the **shipped MVP "Dark Academic" theme**: deep navy night, warm gold, serif typography, and a rarity-coloured semantic graph.

---

## Sources used to build this system

Everything here was reverse-engineered from the real product. Explore these further to build more faithfully:

| Source | What it gave us |
|--------|-----------------|
| **GitHub — [snailuj/metaforge](https://github.com/snailuj/metaforge)** | The canonical source of truth. `web/src/styles/tokens.css` (colour & type tokens), Lit component styles (`mf-results-panel`, `mf-search-bar`, `mf-app`, `mf-toast`, `mf-force-graph`), `web/src/graph/colours.ts` (rarity/relation/forge palettes), `strings/v1/ui.en-GB.ftl` (all UI copy). |
| **[Metaforge PRD v2](https://github.com/snailuj/metaforge/blob/main/Metaforge-PRD-2.md)** | Product brief, design principles, theme spec, the two-mode (Lookup / Explore) philosophy, voice & ethos. |
| **`MetaforgeConcept.png`** (in repo root, copied to `assets/`) | Concept art showing two aspirational theme directions: a neon-celestial dark theme and a hand-drawn parchment/cartographic theme. **Aspirational only** — the shipped MVP is the muted Dark Academic theme documented here. |
| **`uploads/Screenshot 2026-05-31 214355.png`** | The live shipped UI ("hungriness" lookup). The definitive reference for the Dark Academic look. |

> **Note for the reader:** if you have access to the GitHub repo, read `web/src/components/*.ts` and `web/src/styles/tokens.css` directly — the Lit components are short, well-factored, and define every visual detail precisely.

---

## What the product is (and isn't)

**Two modes of use, served simultaneously:**

| Mode | User state | Design priority |
|------|-----------|-----------------|
| **Lookup** | "I need a word NOW" | Speed, scannability, clarity — the HUD panel is a complete thesaurus on its own |
| **Explore** | "I wonder what's near this word…" | Beauty, surprise, serendipity — the 3D graph rewards wandering |

**The layout** is a full-viewport 3D force graph with a semi-transparent HUD overlay:
- **Search bar** — always visible, centred top, `/` keyboard shortcut, autocomplete dropdown.
- **Rarity filters** — three checkboxes (Common / Unusual / Rare) below the search bar, each tinted its rarity colour.
- **Results panel** — left HUD, ~320px, frosted glass. Word title + rarity badge, then one block per sense: POS, meta badges, definition, usage example, and colour-coded word chips grouped by relation (synonyms, broader, narrower, similar, antonyms, collocations).
- **3D graph** — nodes are serif `SpriteText` labels coloured by rarity, the central word in gold; springy edges; orbit/fly camera.
- **Toast** — gold pill, bottom-centre, e.g. `Copied "petrichor"`.

**Surfaces in scope for this system:** the **Web App** (the only shipped product). The Metaphor Forge UI is Phase 2 (palette defined, UI not yet built). There is no marketing site, no mobile app, no docs site yet.

---

## CONTENT FUNDAMENTALS

The voice is **literary, calm, and quietly clever** — a knowledgeable friend who loves words, never a chirpy SaaS app. It trusts the reader's intelligence and gets out of the way.

**Spelling & locale — British English (en-GB), always.**
- `colour`, `visualisation`, `localisation`, `centre`, `organise`. The CSS tokens are literally named `--colour-*`. Honour this everywhere.

**Casing — sentence case for everything.** No Title Case In Buttons. Labels that are *categorical* go **UPPERCASE with letter-spacing** (`SYNONYMS`, `BROADER TERMS`, `UNUSUAL`) — this is a typographic device, not capitalisation of prose.

**Punctuation & typography.**
- Real ellipsis character `…`, never three dots: `Search for a word…`, `Looking up…`.
- Words under discussion are wrapped in **straight double quotes**: `Copied "word"`, `"{word}" was not found in the thesaurus.`
- Em-dashes and en-dashes used freely in prose (the PRD is full of them).

**Person.** Second person for instructions to the user (`Type a word to explore`). First-person-plural, candid and self-aware, in product/marketing voice (the PRD: *"We missed it. This is us rebuilding it."* / *"If that's twelve people, that's fine."*). Never corporate "we are excited to announce."

**Tone is honest to a fault.** The product openly admits its own niche: *"spatial word exploration might just be too niche to attract a mass audience. We're building this because we want to use it."* Embrace candour over hype.

**Brevity.** UI strings are tiny and functional. Status messages are 2–4 words (`Looking up…`, `Type a word to explore`). Errors are plain and kind (`Something went wrong. Please try again.`).

**No emoji. No exclamation marks in UI.** The atmosphere is scholarly and unhurried. (Discovery toasts in *parked* gamification ideas use a single `!`, but the shipped thesaurus does not.)

**Verbatim copy examples (from `ui.en-GB.ftl`):**
```
search-placeholder   = Search for a word…
status-idle          = Type a word to explore
status-loading       = Looking up…
error-generic        = Something went wrong. Please try again.
results-word-not-found = "{$word}" was not found in the thesaurus.
word-chip-title      = Click to look up, right-click to copy
toast-copied         = Copied "{$word}"
panel-expand         = Explore »
results-synonyms     = Synonyms
results-broader      = Broader terms
results-narrower     = Narrower terms
```

**Lexicon.** Words for relation types are precise and slightly scholarly: *synonyms, broader terms, narrower terms, similar, antonyms, collocations*. Rarity is *common / unusual / rare* (the PRD also references *archaic / endangered* for future collection features). Metaphor quality tiers: *legendary, complex, interesting, ironic, strong, obvious, unlikely*.

---

## VISUAL FOUNDATIONS

The aesthetic is **"Dark Academic"** — a refined, scholarly night. Think a library reading room after hours, lit by a single brass lamp. Inspired by an alchemist's study but stripped of heavy decoration.

**Colour & vibe.** A deep navy-charcoal canvas (`#1a1a2e`) with one warm gold accent (`#d4af37`) and warm off-white text (`#e8e0d4`). **Never pure black, never pure white, never pure grey** — every neutral is warmed (taupe `#a89f94`, slate `#6b6560`). The graph adds three earthy semantic hues — **sage** (common), **copper** (unusual), **lilac** (rare) — plus relation tints (copper synonyms, brown hypernyms, sage hyponyms, muted-purple similar, slate-blue collocations, dusty-rose antonyms). The overall feeling is **muted, warm, low-saturation, candlelit.** Saturation is restrained — these are dusty pigments, not neon.

**Typography.** All-serif, which is rare and distinctive for an app.
- **Playfair Display** — high-contrast display serif for the searched word and panel titles. Elegant, editorial.
- **Crimson Text** — a readable old-style serif for body, UI, definitions, chips. (Note: graph node `SpriteText` labels render in Georgia as a WebGL-safe fallback.)
- **JetBrains Mono** — used sparingly, only for the `/` shortcut hint.
- Italics carry semantic weight: part-of-speech tags and usage examples are italic.

**Backgrounds.** Flat dark navy — **no gradients, no images, no patterns, no texture** in the shipped MVP. Depth comes entirely from the 3D graph behind the glass and from translucency, not from decoration. (The concept art's nebula/parchment backgrounds are aspirational, not shipped.)

**Surfaces & "glass".** The HUD is the signature surface: `rgba(22,33,62,0.6)` fill + `backdrop-filter: blur(8px)` + a **1px hairline gold border at 20% opacity** + **4px** radius. You see the living graph through every panel. This frosted-glass-over-graph is the core visual motif — use it for search bar, results panel, dropdowns.

**Corner radius.** A single, tight **4px** radius (`--hud-radius`) on panels and inputs. Badges are pill-shaped (`8px`). Word chips get a tiny `3px`. **Nothing is heavily rounded** — the mood is precise and scholarly, not soft/friendly.

**Borders & dividers.** Hairlines, always low-opacity gold or low-opacity off-white. Section dividers inside the panel are `1px solid rgba(212,175,55,0.1)`. Usage examples use a `2px` gold left-rule at 30% opacity.

**Shadows.** Essentially none — this is a flat, translucent system. There are **no drop shadows** on cards. Elevation is communicated by blur + translucency + the gold hairline, not by box-shadow. (The only "glow" is the gold loading ring and node hover borders.)

**Badges & chips.** Two families:
- *Rarity / meta badges* — pill (`8px`), `~10px` uppercase letter-spaced text, a **tinted translucent background at ~20% opacity** with matching saturated text colour (e.g. unusual = `rgba(196,149,106,0.2)` bg + `#c4956a` text).
- *Word chips* — inline, coloured by relation type, `3px` radius, transparent until hover. Hover = `rgba(212,175,55,0.15)` gold wash. Focus = `1px` gold outline.

**Hover states.** Subtle gold washes — `rgba(212,175,55,0.12–0.15)` background on chips, suggestions, and toggles. Cursor becomes `pointer` over graph nodes; hovered nodes gain a thin rounded border in their own colour plus a faint `rgba(0,0,0,0.2)` backplate.

**Press / active states.** No shrink/scale tricks. Selection in the suggestion list = the same gold wash plus `aria-selected`. The interaction language is restrained.

**Animation & motion.** Minimal and tasteful. A 200ms `cubic-bezier(0,0,0.08,1)` slide for the collapsing panel; 150ms background fades on chips; a 1s linear gold **spinner ring** while loading; 200ms opacity fade on the toast. The big motion is *physical*, not CSS — the d3-force graph's springy settling (high velocity decay `0.85`, slow alpha decay) and smooth camera damping (`dampingFactor: 0.05`). **No bounces, no playful easing** — motion is calm and weighty, like objects with mass.

**Transparency & blur** are load-bearing, not decorative: they let the graph remain visible through the HUD at all times (PRD: *"the user can see the 3D graph through the panel at all times"*). Use `backdrop-filter: blur(8px)` on any floating surface.

**Layout rules.** Full-viewport fixed canvas; `overflow: hidden` on `html, body`; `touch-action: none` (the graph owns gestures). Floating HUD elements are absolutely positioned: search centred top, filters below it, results panel pinned left (top-`calc(1rem + 3.5rem)` to bottom-`2rem`), toast bottom-centre. The panel scrolls internally with a thin gold scrollbar (`scrollbar-color: var(--colour-accent-gold-dim) transparent`). Responsive: under 768px the results panel collapses behind a toggle.

**Imagery.** None in the shipped product — the "imagery" *is* the generative graph. Node colour vibe is warm and earthy. If you must add imagery for marketing, keep it dark, warm, low-saturation, slightly grainy/etched — in the spirit of the parchment concept art.

---

## ICONOGRAPHY

Metaforge is **almost entirely icon-free** — a deliberate, text-first scholarly choice. The shipped UI uses **no icon font, no SVG icon set, and no emoji.**

- **Glyph-as-icon.** The few "icons" are typographic: the **`/`** search-shortcut hint (rendered in JetBrains Mono), and the **`»`** (right guillemet, `\u00BB`) on the *Explore »* expand button / **`«`** for collapse. These are real Unicode characters, not images.
- **The graph nodes are the iconography.** Meaning is carried by coloured serif word-labels (`SpriteText`) and the central word's larger gold node — colour and size *are* the visual language. There are no pictographic node glyphs in the MVP.
- **Checkboxes** in the rarity filter are native HTML inputs, each `accent-color`-ed to its rarity hue (sage/copper/lilac).
- **Concept-art only (not shipped):** the aspirational designs show a magnifying-glass on search, a wrench/cross for "Forge", a gear for "Settings", and a small constellation minimap. If you build the Settings/Forge/Hunt chrome, **substitute a thin-stroke line-icon set** to match the hairline aesthetic — **[Lucide](https://lucide.dev)** (1.5–2px stroke, rounded caps) is the closest CDN match. **Flag any icon you add as a substitution** — there is no canonical icon set in the codebase.

> Rule of thumb: reach for a **word or a Unicode glyph** before an icon. When an icon is unavoidable, use thin-stroke Lucide tinted in gold or a muted neutral, never filled or multicolour.

---

## Theming / skins

Metaforge is built to wear **more than one skin** (the PRD lists "at least two visual skins" as a core deliverable). Theming is handled entirely through **token swaps** — no component knows which theme is active.

**How it works.** `colors_and_type.css` keeps all *structural* tokens (type, spacing, radius) theme-agnostic in `:root`, and scopes every `--colour-*` token to a theme block:
```css
:root, [data-theme="dark"] { /* Dark Academic — the shipped MVP (default) */ }
[data-theme="parchment"]   { /* Parchment — light / cartographic skin   */ }
```
Set `data-theme="dark"` or `data-theme="parchment"` on any wrapper element and its entire subtree re-skins. Translucent washes (hover states, hairlines, badge fills) are **derived from the base tokens with `color-mix()`**, so they re-tint automatically — you never hand-maintain a second set of rgba values. Build components against the **semantic tokens only** (`var(--colour-bg-hud)`, `var(--colour-rarity-unusual)`, `var(--hairline)`) and they theme for free. The web-app UI kit has a live **Dark / Parchment** toggle (top-right) demonstrating this.

**Theme 1 — Dark Academic (default, shipped).** Documented in full above. Deep navy, warm gold, frosted glass over a dark graph.

**Theme 2 — Parchment (light / cartographic).** A warm aged-paper ground (`#d6c4a1`), sepia ink (`#3b2d1a`), burnt antique gold (`#9c6b15`). Rarity & relation hues are **darkened for contrast on light paper** (forest / burnt-copper / aubergine instead of sage / copper / lilac). The HUD's heavy blur softens to `blur(2px)` and the hairline warms — a scroll, not glass. This is the **flat palette foundation** for the skin.

> **Not yet built (future design exploration):** the *ornate* parchment chrome from the concept art — rolled-scroll panels, a brass-telescope search bar, hand-drawn constellations, a blackletter display face for the searched word. Those need real illustration assets and deliberate design; the current Parchment theme is an honest flat-colour skin, not the full decorative treatment. Ask when you want to push it further.

## Index / manifest

Root files:
- **`README.md`** — this file: product context, sources, content & visual foundations, iconography.
- **`colors_and_type.css`** — all colour + type tokens (base + semantic) and reusable type recipes. **Import this in every artifact.**
- **`SKILL.md`** — Agent Skill manifest for using this system in Claude Code.
- **`assets/`** — `MetaforgeConcept.png` (two-theme concept art).
- **`preview/`** — design-system specimen cards (colours, type, components, spacing) shown in the Design System tab.
- **`ui_kits/web-app/`** — high-fidelity, interactive recreation of the Metaforge web app (Lit-faithful components in React/JSX + `index.html` click-through prototype).

### Font note
**Playfair Display, Crimson Text, and JetBrains Mono** are all genuine Google Fonts (the product's real choices). This system loads them from the Google Fonts CDN via `@import` in `colors_and_type.css` rather than bundling `.woff2` files. If you need offline/self-hosted fonts, download these three families and drop them in a `fonts/` folder — **flagged for the user.**
