# Metaforge — Product Requirements Document

**Version:** 2.0
**Last Updated:** 2026-02-07
**Status:** Reconciled — this is the single authoritative PRD

Had a profound realisation that scope was creeping on me. Winding everything waaaay back to the OG.

**Note to Agents:** This document supersedes the original PRD (now deleted). All parked ideas from the original are preserved in the [Parked Ideas](#parked-ideas) section at the end. If something seems ambiguous or missing, ASK THE USER.

## Metaforge — Project Brief

### What This Actually Is

Metaforge is a spiritual successor to Visual Thesaurus, the browser-based word graph that let you click between springy nodes of meaning until you found the word you needed — or lost an hour you didn't plan to spend. Visual Thesaurus disappeared. We missed it. This is us rebuilding it, and seeing what else it could be.

At its core, Metaforge is a fast, browser-based visual dictionary and thesaurus. You search a word, and it blooms into a cluster of connected meanings — synonyms, antonyms, collocations, connotations, etymology, register, and usage examples. Click a neighbouring node and the whole graph reshuffles around it. The vibe shifts. Clusters darken or brighten depending on where you've wandered. Words you didn't know you were looking for turn up in the periphery.

It's a navigation tool for people whose minds like to wander off the known map.

Bolted onto this is a metaphor generator — an experimental feature that surfaces surprising semantic bridges between words. Part educational, part creative writing tool, part "let's see if this is even possible."

### The Problem (Honestly Stated)

Traditional dictionaries and thesauruses are flat. Alphabetised. Context-blind. They reduce the English language to lists, when the real territory is a graph — words pulling on each other through meaning, history, sound, and association.

Most native English speakers reliably use only 13,000–16,000 word families. For second-language learners, vocabulary acquisition (not grammar) is the single biggest factor in becoming proficient. In both cases, the tools available for *exploring* the language are stuck in a linear model inherited from monks and aristocratic snobs who did their best with what they had. We can do better now. Or at least different. More fun, for sure.

That said — there's a reason Visual Thesaurus doesn't exist anymore, and the honest assessment is that spatial word exploration might just be too niche to attract a mass audience. We're building this because we want to use it, and because we think a handful of other people will too. That's enough.

### Visual Metaphors Worth Exploring

The original Visual Thesaurus used a 2D force-directed graph — nodes connected by edges, with a satisfying springy physics. Words formed local clusters by meaning, and clicking a distant node would pull you along an edge into a new semantic neighbourhood. That mechanic — the feeling of *travelling* between clusters — is the thing to preserve.

Three candidate directions for how Metaforge renders the language graph:

**Force-directed graph (the classic).** Nodes and edges. Springy. Clusters form organically by semantic proximity. Closest to the original Visual Thesaurus experience. Could be 2D or 2.5D (layered depth without full 3D). Simple, proven, and the physics *feel* great when done right.

**Tidal pools.** Words cluster like barnacles on rocks — grouped by register, formality, or domain. Etymology provides depth (older roots sink lower). Clicking a word drains and refills the pool with its neighbours. A metaphor that rewards slow, curious browsing.

**City map.** Semantic fields as neighbourhoods. Collocations as streets. Register as altitude (formal language on the hill, slang down by the docks). A metaphor with serious stretch — you could layer in landmarks, districts, even a sense of "getting lost" in unfamiliar vocabulary. The most ambitious option and the hardest to get right, but potentially the most rewarding for sustained exploration.

These aren't mutually exclusive — Metaforge could ship with the force graph as default and offer alternative views as the project matures.

### What's In the Box

- **Search** — always visible, always under 100ms. Returns definitions, synonyms/antonyms, register, connotations, etymology, collocations/metonyms, and usage examples
- **Visual graph** — the core interaction; click, drag, travel between clusters
- **Metaphor generator** — experimental creative tool surfacing unexpected semantic connections
- **Themes** — at least two visual skins that completely change the look and feel
- **Curated datasets** — best-in-class lexical data, enriched using proprietary techniques, built on the sqlunet database

### What's Not In the Box (For Now)

The following features were explored but are parked until the core experience proves itself:

- Gamification (word hunts, leaderboards, word-of-the-day prizes)
- 3D starfield exploration
- Educational Tracks / Constellations for language learners
- Vocabulary testing tools for teachers and ESOL programmes
- Native app versions

Any of these could come back if there's genuine demand. None of them are the reason this project exists.

### Open Source and Non-Profit

Metaforge is free and open-source. The hosted web app will be owned by a Charitable Trust registered as a non-profit in New Zealand. Revenue covers servers and infrastructure only — no stipends, no royalties, no commercial ambitions. All code, data, and documentation live on GitHub. Enrichments to the underlying datasets will be contributed upstream to sqlunet where possible.

### Who It's For

Writers looking for the right word. Word nerds who enjoy pulling threads. Language learners building vocabulary through exploration rather than rote lists. Anyone who ever lost a pleasant half-hour in Visual Thesaurus and wondered where it went.

If that's twelve people, that's fine. It's public domain. Maybe someone will take what we've built and make something we haven't thought of yet.

---

## Design Principles

### 1. Utility First, Wonder Second

The thesaurus must work flawlessly. A user needing a synonym for "happy" must find it in under 3 seconds. The 3D graph enhances but never blocks access.

### 2. Progressive Depth

```
Layer 0: Functional thesaurus (search → results → copy)
Layer 1: Force graph visualisation (same data, rendered in 3D)
Layer 2: Enrichment (rarity badges, register, connotation)
Layer 3: Metaphor Forge (experimental creative tool)
Layer 4+: [Parked — etymology trails, constellations, collections near-horizon;
           game systems, gravity, wormholes deeper park]
```

Users naturally discover deeper layers through use. Nothing is gated. Each layer works independently — if the 3D graph breaks, the HUD panel still functions as a complete thesaurus.

### 3. Two Modes of Use

| Mode | User State | Design Priority |
|------|------------|-----------------|
| **Lookup** | "I need a word NOW" | Speed, scannability, clarity |
| **Explore** | "I wonder what's near this word..." | Beauty, surprise, serendipity |

The interface serves both simultaneously.

---

## Tech Stack

| Layer | Technology | Role |
|-------|------------|------|
| Physics | `d3-force-3d` | Force simulation in 3D (x, y, z) |
| Rendering | `3d-force-graph` (wraps Three.js) | WebGL scene, camera, lighting |
| Camera | Built-in `fly` control type | WASD movement + mouse look |
| Custom nodes | `nodeThreeObject` accessor | Any Three.js object per node |
| Frontend framework | Lit (web components) + Vite + TypeScript | Component architecture, dev tooling |
| Backend API | Go + Chi router | Stateless, self-hostable |
| Database | SQLite (lexicon_v2.db) | Self-contained, no external DB needed |
| Embeddings | FastText 300d (in-db BLOB) | Property similarity via cosine distance |
| LLM Enrichment | Gemini Flash 2.5 | Property extraction from synset definitions |
| Localisation | Mozilla Fluent (.ftl) | UI strings, i18n-ready |

---

## User Interface

### Layout

The UI is a full-viewport 3D force graph with a semi-transparent HUD overlay.

```
┌─────────────────────────────────────────────────────────────────────┐
│  [🔍 Search...]                                          [Settings] │
├───────────────────────┬─────────────────────────────────────────────┤
│                       │                                             │
│   HUD RESULTS PANEL   │         3D FORCE GRAPH                      │
│   (~60% opacity bg)   │         (WebGL canvas, full viewport)       │
│                       │                                             │
│   ┌─────────────────┐ │       ● melancholy                         │
│   │ melancholy      │ │      / │ \      \                           │
│   │ ────────────────│ │   ● sad  ● wistful  ● pensive              │
│   │ Uncommon | Poetic│ │    │         \                              │
│   └─────────────────┘ │  ● gloomy    ● sorrowful                   │
│                       │                                             │
│   Synonyms:           │                                             │
│   • sad               │                                             │
│   • sorrowful         │                                             │
│   • gloomy            │                                             │
│   • wistful           │                                             │
│   • pensive           │                                             │
│                       │                                             │
│   Antonyms:           │                                             │
│   • happy             │                                             │
│   • cheerful          │                                             │
│                       │                                             │
│   [▼ Collocations]    │                                             │
│   [▼ Etymology]       │                                             │
│                       │                                             │
├───────────────────────┴─────────────────────────────────────────────┤
│   "a melancholy autumn evening" — usage example                     │
└─────────────────────────────────────────────────────────────────────┘
```

**HUD Panel:**
- Semi-transparent background (~60% opacity, tuneable)
- User can see the 3D graph through the panel at all times
- Font colours/outlines chosen for legibility against variable 3D backgrounds
- Scannable text list of synonyms, antonyms, collocations
- Each word shows rarity badge and register
- Panel does not block camera controls — mouse-look disabled when hovering HUD, re-enabled on leave

**3D Force Graph:**
- Full viewport, renders behind HUD
- Nodes form springy clusters by semantic proximity
- Fly camera (WASD + mouse look) for free exploration
- Double-click a node to navigate (graph reshuffles around new word)

**Search Bar:** Always visible, top of viewport. Keyboard shortcut: `/`. Results appear as user types.

### Interaction Model

| Action | Input | Notes |
|--------|-------|-------|
| Select node | Single-click | Shows tooltip/detail in HUD |
| Navigate to word | Double-click node | New word becomes centre, graph reshuffles |
| Copy word | Right-click node | Clipboard copy, suppress context menu |
| Move camera | WASD keys | Fly mode |
| Look around | Mouse move | Fly mode mouse-look |
| Zoom | Scroll wheel | Native 3d-force-graph |
| Drag node | Click + hold + drag | Repositions node in simulation |
| Search | `/` key or click search bar | Focus search input |
| Keyboard nav | `Tab` through HUD results | `Enter` to select, `Escape` to close |

**Mouse-look state management:**
- Disabled during node drag (re-enabled on drop)
- Disabled when mouse is over HUD panel (re-enabled on mouse-leave)
- Enabled otherwise (default state in 3D canvas area)

---

## Core Thesaurus

The foundation. Everything else builds on this.

### Search
- Instant results as user types
- Exact lemma match for MVP (fuzzy matching deferred)
- Recent searches: quick access to previous lookups

### Results Display

For each word, display:
- The word itself
- Rarity badge: Common / Uncommon / Rare / Archaic (needs SUBTLEX-UK)
- Register badge: Formal / Neutral / Informal / Slang
- Connotation indicator: Positive / Neutral / Negative (subtle colour coding)
- Part of speech

### Relationship Types

| Type | Description | Node Colour |
|------|-------------|-------------|
| Synonyms | Words with similar meaning | Warm amber |
| Antonyms | Words with opposite meaning | Contrasting (TBD) |
| Hypernyms | Broader terms | Earthy brown |
| Hyponyms | Narrower terms | Sage green |
| Similar | Similar in meaning | Muted purple |
| Collocations | Frequently co-occurring words | TBD |

### Word Information

Selecting a word reveals in the HUD:
- Definition (clear, concise)
- Part of speech with inflections
- Usage examples (1-2 sentences)
- Rarity / Register
- Synonyms, antonyms, relations

---

## Visual Theme: Dark Academic

**MVP theme.** A refined, scholarly atmosphere — deep darks, warm golds, serif typography. Inspired by the Alchemist aesthetic but stripped of heavy decoration.

```css
--colour-bg-primary: #1a1a2e;       /* Deep navy-charcoal */
--colour-bg-secondary: #16213e;     /* Slightly lighter navy */
--colour-accent-gold: #d4af37;      /* Warm gold accent */
--colour-text-primary: #e8e0d4;     /* Warm off-white */
--colour-node-central: #d4af37;     /* Gold for searched word */
--colour-node-synonym: #c4956a;     /* Warm amber */
--colour-node-hypernym: #8b6f47;    /* Earthy brown */
--colour-node-hyponym: #6a8b6f;     /* Sage green */
--colour-node-similar: #7a6a8b;     /* Muted purple */
--font-heading: 'Playfair Display', Georgia, serif;
--font-body: 'Crimson Text', 'Times New Roman', serif;
```

**Second theme (future):** Light / hand-drawn. Possibly the original Alchemist style adapted. Explore with Nano Banana Pro. Not MVP.

---

## Metaphor Forge

An experimental creative tool for generating novel metaphors by finding non-obvious connections. Bolted onto the core thesaurus — uses the same graph infrastructure.

### How It Works

1. User enters a source word
2. System suggests structurally analogous but semantically distant words (catalysts)
3. Each suggestion includes shared properties explaining the bridge
4. Quality tiers: Legendary / Interesting / Strong / Obvious / Unlikely

### Backend (Already Built)

- `GET /forge/suggest?word={word}&threshold={float}&limit={int}`
- Returns source synset, properties, and sorted matches with tier classification
- Uses property similarity matrix with IDF weighting + synset centroid distances

### UI (Phase 2)

Forge UI design deferred to Phase 2. Will build on the force graph — forge results rendered as nodes with tier-based visual treatment.

---

## Accessibility

Target: **WCAG 2.1 AA**

The HUD panel is the accessible surface. The 3D graph is a visual enhancement — all information must be available through the HUD.

### Keyboard Navigation
- `/` — Focus search bar
- `Tab` — Move through results
- `Enter` — Select word
- `Escape` — Close panels, cancel
- Arrow keys — Navigate results list

### Screen Reader Support
- HUD uses semantic HTML + WAI-ARIA
- `role="search"` on search bar
- `aria-live="polite"` on results region
- `aria-label` on interactive elements
- `role="region"` with label on results panel
- 3D canvas gets `role="img"` with `aria-label` describing graph state

### Visual Accessibility
- Reduced motion: `prefers-reduced-motion` media query
- High contrast: `prefers-contrast` + manual toggle
- Colour-blind modes: alternative colour schemes (not just hue-dependent)
- Font scaling: respects browser zoom, HUD uses `rem` units

---

## Phasing

### Phase 1 (MVP): Core Thesaurus + 3D Force Graph
- Go API (done: `/thesaurus/lookup`, `/forge/suggest`, `/strings`, `/health`)
- `3d-force-graph` + fly controls + Dark Academic theme
- HUD results panel (semi-transparent overlay)
- Search, select, navigate, copy interactions
- Rarity/register badges (needs SUBTLEX-UK)

### Phase 2: Metaphor Forge UI
- Wire up existing `/forge/suggest` endpoint to the graph
- Forge-specific UI (source word + catalyst suggestions)
- Tier visualisation on nodes

### Phase 3: Near-Horizon Features
- Etymology trails
- Constellations
- Collections
- Second theme (light / hand-drawn)

### Phase 4+: Deeper Park
- See [Parked Ideas](#parked-ideas) below
- Revisit if demand/interest warrants

---

## Data Sources

1. **Open English WordNet** (via sqlunet_master.db) — 107k synsets, 185k+ lemmas, definitions, synonyms, hypernyms, hyponyms
2. **VerbNet** (selective) — 600+ verb classes, thematic roles, usage examples
3. **SyntagNet** — 87k collocation pairs for contiguity-based metonyms
4. **FastText embeddings** (300d) — similarity calculations, property vocabulary matching
5. **SUBTLEX-UK** — word frequency/rarity classification (needs re-downloading)
6. **Gemini Flash** — LLM-extracted properties for metaphor forge (1,967 synsets enriched, ~20K planned)

---

## Open Questions

1. **Prompt direction:** Blend structural + sensory properties for 20K enrichment run?
2. **SUBTLEX-UK:** Needs re-downloading for frequency/rarity data
3. **Antonyms:** `lexrelations` not imported from sqlunet — fast-follow after MVP
4. **Fuzzy search:** Exact lemma match only for now
5. **HUD opacity:** ~60% is a starting point — needs tuning against actual 3D content

---

## Parked Ideas

The following features were fully designed in the original PRD but are parked until the core experience proves itself. Nothing here is deleted — it's preserved for when/if we return to it.

### 3D Starfield / Celestial Visualisation

An alternative rendering where words become celestial bodies in a semantic solar system.

**Words as Celestial Bodies (LexiNodes):**
- Central Star: the currently selected word. Bright, prominent, centre of view
- Planets: strongly related words. Size indicates relationship strength
- Moons: secondary relationships or nuances
- Distant Stars: weakly related words. Visible but dim

**Visual Properties Encode Meaning:**

| Property | Encodes |
|----------|---------|
| Distance from centre | Relationship strength (closer = more similar) |
| Size | Word frequency or relationship strength |
| Brightness | Recency of visit (visited words glow brighter) |
| Colour hue | Semantic category or register |
| Orbital speed | Relationship type (synonyms orbit differently than antonyms) |

**Relationship layer toggles:**

| Layer | Default | Description |
|-------|---------|-------------|
| Synonyms | On | Core orbit around central star |
| Antonyms | On | Polar opposition across the space |
| Metonyms | Off | Associative trails and tethers |
| Etymology | Off | Root trails showing word lineage |
| Wormholes | Auto | Hidden until discovered |

### Gravity System

All words exert gravitational pull proportional to their frequency, creating navigation texture.

| Word Type | Gravity Strength | Examples |
|-----------|------------------|----------|
| Ultra-common | Very strong | the, is, and, to |
| High-frequency emotional | Strong | love, death, time, money, happy |
| Common words | Moderate | walk, think, house, small |
| Uncommon words | Weak | melancholy, ephemeral, sanguine |
| Rare words | Very weak | defenestration, petrichor |

**Gravity Wells:** high-gravity words as visible landmarks. Larger, more luminous bodies with visible gravity field effect. Navigation effects: approaching slows movement, passing near curves trajectory, breaking free requires sustained thrust.

**Skill element:** novice navigators get "trapped" in obvious word spaces; skilled navigators slingshot around wells for speed.

| Context | Gravity Behaviour |
|---------|-------------------|
| Normal thesaurus use | Gravity is visual only; no navigation impediment |
| Word Hunt (active) | Full gravity physics; wells are obstacles |
| Word Hunt (relaxed) | Reduced gravity; wells are landmarks only |

### Constellation System

Users build a personal map of their journey through the Metaforge.

**Automatic generation:** each visited word becomes a star; navigation paths become lines connecting stars. No manual action required.

**Minimap:** small icon in corner, shows simplified constellation. Pulses gently when new stars are added. Click to expand to full map view (2D star chart, dark field with stars connected by faint lines).

| Element | Appearance |
|---------|------------|
| Normal visited words | White/silver stars |
| Recently visited | Brighter glow |
| Older visits | Slightly dimmed |
| "Hunted" words | Gold glow |
| Rare words | Distinct colour (purple?) |
| Wormhole endpoints | Special connector line |
| Navigation paths | Faint lines between stars |

**Persistence:** without account in browser local storage; with account synced to server. Reset option and export as image.

### Collection System (Specimen Cabinet)

A personal vocabulary cabinet for pinning and collecting words.

**Adding words:** double-click to pin, long-press on mobile, "Pin" button in info panel. Sortable by date, alphabetical, rarity, category. Custom folders/tags.

**Word Badges:**

| Badge | Earned By |
|-------|-----------|
| Hunted | Found during Word Hunt |
| Rare | Word is uncommon in corpus |
| Endangered | Archaic or obsolete word |
| Wormhole | Discovered via wormhole connection |
| Forged | Used in Metaphor Forge |

**Rarity System:**

| Rarity | Description | Collector Value |
|--------|-------------|-----------------|
| Common | High frequency | Low |
| Uncommon | Moderate frequency | Medium |
| Rare | Low frequency | High |
| Archaic | Historically used, now rare | Very high |
| Endangered | At risk of falling out of use | Special |

**Word Families:** words sharing etymological roots form "genera." Completing all words from a root completes a "word family."

**Annotations:** users can add personal notes to collected words.

**Export:** JSON, CSV, printable PDF. "Linguistic passport" shareable summary.

### Wormholes (Surprising Connections)

Hidden connections between semantically distant but structurally analogous words.

**Example:** "Grief" ↔ "Anchor" — different domains (emotion vs nautical), shared structure (both hold something in place, preventing movement).

**Discovery triggers:**
1. Visit both endpoints in a single session
2. Linger on a word long enough to "sense" distant resonance
3. Use Metaphor Forge successfully with the pair
4. Navigate near an undiscovered wormhole (proximity trigger)

**Discovery moment:** dramatic animation (visual tear in space), sound effect, notification, naming opportunity, collection update with "Wormhole" badge, constellation update with special connector line.

**Wormhole travel:** once discovered, remains visible. Clicking instantly transports to other endpoint. Creates shortcuts through semantic space.

**Data source:** pre-computed from embedding distance (semantic dissimilarity) + relational overlap (structural similarity) + curated additions.

### Etymology Trails

Visual traces showing how words evolved from roots.

**Toggle behaviour:** off by default, toggle on to see root trails throughout visible space.

**Visual representation:** glowing trails connecting words sharing roots. Root nodes as special markers. Colour coded: Latin (gold), Greek (blue), Germanic (silver), Other (white).

**Example — viewing "telephone":** trail connects to "television", "telegraph", "telescope" (root: Greek "tele-" = far). Additional trail to "phone", "phonetic", "symphony" (root: Greek "phone-" = sound/voice).

### Word Hunt System

A daily quest to find a hidden word through semantic navigation.

**Core concept:** each day, a curated word is hidden. Users receive cryptic clues and navigate semantic space to find it.

**Modes:** Timed (full scoring, timer) and Relaxed (no timer, no scoring, just exploration).

**Progressive clues teach semantic relationships:**

| Clue Type | What It Teaches |
|-----------|-----------------|
| "Begin at X" | Starting vocabulary anchor |
| "Seek what is Y but not Z" | Synonym/antonym differentiation |
| "Relates to X as Y relates to Z" | Analogical reasoning |
| "Formal/informal contexts" | Register awareness |
| "Shares a root with X" | Etymology |
| "Follow the metonyms of X" | Associative thinking |

**Scoring (timed only):** base 1000, -1/second, -100/clue requested. Bonuses for fewer clues.

**Difficulty tiers:** Novice → Explorer (7-day streak) → Wayfinder (30-day) → Lexicon Master (100-day).

**Portal mechanic:** ~1 in 10 hunts, a gravity-well word contains a hidden portal leading directly to the target. Risk/reward for navigating gravity wells.

**Hunt generation:** target word selection, starting word, progressive clues, optional portal, difficulty calibration. Future: AI-assisted generation with human review.

### Ambient Soundscape

Generative audio that makes the Metaforge feel alive.

**Behaviour:** paused on load, fades in on first navigation, user-controllable.

**Semantic regions have tonal signatures:**

| Region Type | Sound Character |
|-------------|-----------------|
| Abstract/philosophical | Sustained, ethereal tones |
| Concrete/physical | Percussive, grounded sounds |
| Emotional words | Harmonic, melodic |
| Rare/archaic words | Mysterious, distant |
| Gravity wells | Low rumble, tension |

**Implementation:** Web Audio API, pre-composed stems layered by context, low CPU usage.

### Multiplayer & Social (Future)

- Daily leaderboards (opt-in)
- Friends list with score comparison
- "Race" mode: same hunt, same start, first to find wins
- Classroom integration (teacher sets hunt, students race)
- Public constellation gallery
- Share constellation as "guided tour"

### User Accounts & Sync (Future)

- Required for leaderboards, constellation sync, classroom features
- Simplest possible auth for self-hosted deployment
- Without account: everything stored in browser (IndexedDB)
- With account: sync to server