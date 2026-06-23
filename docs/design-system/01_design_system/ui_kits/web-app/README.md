# Metaforge — Web App UI Kit

A high-fidelity, **interactive** recreation of the Metaforge web app (the only shipped product). Open `index.html` and you get the real thing: search a word, watch it bloom into a graph, click neighbouring nodes to travel, filter by rarity, copy words.

> Faithful to the Lit source in [`snailuj/metaforge`](https://github.com/snailuj/metaforge) (`web/src/components/*.ts`, `web/src/styles/tokens.css`). These are cosmetic React/JSX recreations — not the production Lit + Three.js code.

## Run it
Open `ui_kits/web-app/index.html`. No build step — React + Babel load from CDN.

**Try:** type or click an example (hungriness, melancholy, desire, longing, hunger) → click any word **chip** in the panel or any **node** in the graph to navigate → toggle **Common / Unusual / Rare** to filter the graph → **right-click** a chip or node to "copy" (gold toast) → press **`/`** anywhere to focus search → **Esc** to clear.

## Components

| File | Component | Notes |
|------|-----------|-------|
| `data.js` | `window.MF_LEXICON` | A small fake lexicon (5 enriched words + stubs) mirroring the API's `LookupResult` shape. `lookup()`, `suggest()`, `rarityOf()`. |
| `SearchBar.jsx` | `<SearchBar>` | Frosted input, `/` shortcut, autocomplete dropdown (word · sense count · rarity badge · definition), keyboard nav. |
| `RarityFilters.jsx` | `<RarityFilters>` | Three tinted checkbox toggles. |
| `ResultsPanel.jsx` | `<ResultsPanel>` | The signature HUD: word + rarity badge, per-sense POS, meta badges (register/connotation), definition, usage example, and colour-coded word chips grouped by relation. |
| `WordGraph.jsx` | `<WordGraph>` | 2D stand-in for the 3D force graph — rarity-coloured serif labels on an even sunflower spread, thin springy edges, hover highlight, click-to-navigate. |
| `Toast.jsx` | `<Toast>` | Gold copy-confirmation pill. |
| `app.jsx` | `<App>` | Wires search → lookup → graph + panel, with idle/loading/ready/error states. |

## Faithfulness notes & known simplifications
- **The graph is 2D, not 3D.** The product uses `3d-force-graph` (Three.js) with fly/orbit camera. This kit renders a clean 2D SVG projection that matches the *look* (rarity-coloured serif `SpriteText`-style labels, gold central node, hairline edges) without the WebGL dependency. Dragging/zooming the 3D scene is not reproduced — the hint text is illustrative.
- **Graph node labels render in Playfair Display** here; in the product the WebGL `SpriteText` falls back to Georgia. Both are high-contrast serifs — visually equivalent.
- **"RESULTS-COLLOCATIONS"** appears as a raw label: this is faithful to the shipped build, where that Fluent string is missing and falls back to its key (visible in the reference screenshot).
- The data is a tiny curated subset, not the ~8,000-synset lexicon. Navigation never dead-ends — unknown related words resolve to a minimal stub entry.
- The **Metaphor Forge** UI is not built (Phase 2 in the product); its tier palette lives in `colors_and_type.css` and the design-system cards.
