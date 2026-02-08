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

- **Search** — always visible, always under 100ms. Returns definitions, synonyms/antonyms, register, connotations, etymology, rarity badges, collocations/metonyms, and usage examples
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
┌─────────────────────────────────────────────────────────────────────────────────────────────────────┐
│                                                      [ Search...]                      [Settings]   │
├────────────────────────┬────────────────────────────────────────────────────────────────────────────┤
│                        │                                                                            │
│   HUD RESULTS PANEL    │                                                                            │
│   (~60% opacity bg)    │                                                                            │
│   (font-outline ??)    │                                                                            │
│   (font-scale 0.7)     │                                                                            │
│  ┌──────────────────┐  │                                                                            │
│  │ melancholy       │  │                                                                            │
│  │ ─────────────────│  │                                                                            │
│  │ Uncommon | Poetic│  │                                                                            │
│  └──────────────────┘  │                                  3D FORCE GRAPH                            │
│                        │                           (WebGL canvas, full viewport)                    │
│    Synonyms:           │                                                                            │
│   • sad                │                                                                            │
│   • gloomy             │                      ● melancholy     ● wistful                            │
│   • wistful            │                    / │ \      \      /                                     │
│   • pensive            │                   /  │  \      \    /                                      │
│   • sorrowful          │                  /   │   \      \  /                                       │
│                        │             sad ●    ●    \       ● pensive                                │
│   Antonyms:            │                   gloomy   \                                               │
│   • happy              │                             \               •                              │
│   • cheerful           │                              ● sorrowful   /                               │
│   [▼ Collocations]     │                                      /  \ /                                │
│   [▼ Etymology]        │                                     •    •                                 │
│                        │                                     │     \                                │
│________________________│                                     •      •                               │
│                                                                                                     │
│                                                                                                     │
│                                                                                                     │
├─────────────────────────────────────────────────────────────────────┬───────────────────────────────┘
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

The following features were fully designed in the original PRD but are parked until the core experience proves itself. Nothing here is deleted — it's preserved verbatim for when/if we return to it.

### 3D Visualisation System

The semantic solar system that transforms lookup into exploration.

#### Visual Representation

**Words as Celestial Bodies (LexiNodes):**

- **Central Star:** The currently selected word. Bright, prominent, centre of view
- **Planets:** Strongly related words. Size indicates relationship strength
- **Moons:** Secondary relationships or nuances
- **Distant Stars:** Weakly related words. Visible but dim

**Visual Properties Encode Meaning:**

| Property | Encodes |
|----------|---------|
| Distance from centre | Relationship strength (closer = more similar) |
| Size | Word frequency or relationship strength |
| Brightness | Recency of visit (visited words glow brighter) |
| Colour hue | Semantic category or register |
| Orbital speed | Relationship type (synonyms orbit differently than antonyms) |

#### Relationship Modes

**Layered visibility** rather than discrete modes. Users toggle layers on/off:

| Layer | Default | Description |
|-------|---------|-------------|
| Synonyms | On | Core orbit around central star |
| Antonyms | On | Polar opposition across the space |
| Metonyms | Off | Associative trails and tethers |
| Etymology | Off | Root trails showing word lineage |
| Wormholes | Auto | Hidden until discovered |

**Synonym View:**
- Synonyms form tight cluster around central star
- Proximity indicates semantic similarity
- Subtle colour variations denote register/connotation

**Antonym View:**
- Antonyms appear diametrically opposite
- Contrasting colours (warm vs cool)
- Distance represents degree of opposition

**Metonym View:**
- Metonyms appear as nebulae or clusters
- Connected via visible "gravitational tethers"
- Clicking tether reveals relationship type (part-for-whole, symbol-for-referent, etc)

#### Navigation

**Camera Controls:**

- **Orbit:** Click and drag to orbit around current centre
- **Zoom:** Scroll wheel to move closer/farther
- **Fly:** WASD keys or right-click drag to move freely through space

**Navigation Feel:**

Navigation should feel like piloting a spacecraft:

- Smooth acceleration and deceleration
- Momentum carries you forward
- Gravity wells create drag (see Gravity System)
- Skilled navigators learn efficient paths

#### Visual Feedback

- **Hover:** Word glows, label appears
- **Selection:** Smooth transition as new word becomes centre
- **Previously visited:** Words glow brighter (luminosity gradient)
- **Rare words:** Distinct visual treatment (special glow or particle effect)

#### Performance Considerations

- **Dynamic loading:** Only render visible region plus buffer
- **Level of detail:** Distant words render as simple points
- **Spatial indexing:** Efficient lookup for nearby words

---

### Gravity System

All words exert gravitational pull. This creates navigation texture and reflects linguistic reality -- common words dominate thought.

#### How Gravity Works

**Every word has gravity** proportional to its frequency:

| Word Type | Gravity Strength | Examples |
|-----------|------------------|----------|
| Ultra-common | Very strong | the, is, and, to |
| High-frequency emotional | Strong | love, death, time, money, happy |
| Common words | Moderate | walk, think, house, small |
| Uncommon words | Weak | melancholy, ephemeral, sanguine |
| Rare words | Very weak | defenestration, petrichor |

#### Gravity Wells

High-gravity words are "gravity wells" -- visible landmarks that pull navigation toward them.

**Visual representation:**
- Larger, more luminous bodies
- Visible "gravity field" effect (subtle distortion or glow)
- Gravitational influence radius shown on approach

**Navigation effects:**
- Approaching a gravity well slows movement
- Passing near a well curves your trajectory
- Breaking free requires sustained thrust away

**Skill element:**
- Novice navigators get "trapped" in obvious word spaces
- Skilled navigators slingshot around wells for speed
- Finding rare words requires navigating past common ones

#### Gravity in Different Contexts

| Context | Gravity Behaviour |
|---------|-------------------|
| Normal thesaurus use | Gravity is visual only; no navigation impediment |
| Word Hunt (active) | Full gravity physics; wells are obstacles |
| Word Hunt (relaxed) | Reduced gravity; wells are landmarks only |

---

### Constellation System

Users build a personal map of their journey through the Metaforge.

#### Automatic Generation

As users navigate:

1. **Each visited word becomes a star** in their personal constellation
2. **Navigation paths become lines** connecting stars
3. **The constellation grows organically** with use

No manual action required -- exploration naturally builds the map.

#### The Constellation View

**Minimap (always visible):**
- Small icon in corner of visualisation panel
- Shows simplified version of user's constellation
- Pulses gently when new stars are added

**Full Map View (on click):**
- Clicking minimap expands to full constellation view
- Replaces 3D visualisation panel temporarily
- 2D representation -- like a real star chart
- Dark field with stars connected by faint lines

**Visual Elements:**

| Element | Appearance |
|---------|------------|
| Normal visited words | White/silver stars |
| Recently visited | Brighter glow |
| Older visits | Slightly dimmed |
| "Hunted" words | Gold glow |
| Rare words | Distinct colour (purple?) |
| Wormhole endpoints | Special connector line |
| Navigation paths | Faint lines between stars |

**Interaction:**
- Hover over star to see word
- Click any star to:
    - Minimise constellation back to minimap
    - Load 3D visualisation
    - Navigate to that word

#### Persistence

- **Without account:** Stored in browser local storage
- **With account:** Synced to server
- **Reset option:** "Start a new constellation" clears history
- **Export:** Download constellation as image (shareable)

#### Future Features

- Public constellation gallery
- Share constellation as "guided tour"
- Compare constellations with friends
- Teacher-assigned constellation challenges

---

### Collection System

A personal vocabulary cabinet for pinning and collecting words.

#### The Specimen Cabinet

Users curate a personal collection of favourite or interesting words.

**Adding words:**
- Double-click any word to pin it
- Long-press on mobile
- "Pin" button in word info panel

**Collection organisation:**
- Words displayed in a grid or list
- Sortable by: date added, alphabetical, rarity, category
- User can create custom folders/tags

#### Word Badges

Collected words display earned badges:

| Badge | Earned By |
|-------|-----------|
| Hunted | Found during Word Hunt |
| Rare | Word is uncommon in corpus |
| Endangered | Archaic or obsolete word |
| Wormhole | Discovered via wormhole connection |
| Forged | Used in Metaphor Forge |

#### Rarity System

Words are classified by corpus frequency:

| Rarity | Description | Collector Value |
|--------|-------------|-----------------|
| Common | High frequency | Low |
| Uncommon | Moderate frequency | Medium |
| Rare | Low frequency | High |
| Archaic | Historically used, now rare | Very high |
| Endangered | At risk of falling out of use | Special |

**Discovery messages:**
- "You discovered a rare word!" (toast notification)
- "This word is endangered -- help keep it alive!"

#### Word Families

Words sharing etymological roots form "genera":

- Collecting all words from a root completes a "word family"
- Visual indicator shows completion progress
- Completed families earn special recognition

#### Annotations

Users can add personal notes to collected words:
- "Used this in my story about the lighthouse"
- "Perfect for describing autumn"

#### Export & Sharing

- **Export collection:** JSON, CSV, or printable PDF
- **"Linguistic passport":** Shareable summary of collection stats
- **Future:** Public profiles showing collection highlights

---

### Wormholes (Surprising Connections)

Hidden connections between semantically distant but structurally analogous words.

#### What Are Wormholes?

Wormholes connect words that:
- Belong to different semantic domains (high distance)
- Share deep structural properties (analogous relationships)

**Example:** "Grief" ↔ "Anchor"
- Different domains (emotion vs nautical)
- Shared structure: Both hold something in place, preventing movement

#### Discovery Mechanics

Wormholes are **hidden until discovered**. Discovery triggers:

1. **Visit both endpoints** in a single session
2. **Linger on a word** long enough to "sense" distant resonance
3. **Use Metaphor Forge** successfully with the pair
4. **Navigate near** an undiscovered wormhole (proximity trigger)

#### Discovery Moment

When discovered:

1. **Dramatic animation:** Visual tear in space connecting two distant points
2. **Sound effect:** Distinctive "wormhole open" audio cue
3. **Notification:** "You discovered a wormhole between [Word A] and [Word B]!"
4. **Naming opportunity:** User can give the wormhole a personal name
5. **Collection update:** Both words added to collection with "Wormhole" badge
6. **Constellation update:** Special connector line appears on map

#### Wormhole Travel

Once discovered:
- Wormhole remains visible on subsequent visits
- Clicking the wormhole instantly transports to the other endpoint
- Creates shortcuts through semantic space

#### Treasure Display

Discovered wormholes appear in:
- **Collection:** Special "Wormholes" section
- **Constellation:** Distinctive connection lines
- **Profile:** Bragging rights -- "12 wormholes discovered"

#### Wormhole Data Source

Wormholes are pre-computed based on:
- Embedding distance (semantic dissimilarity)
- ConceptNet relational overlap (structural similarity)
- Curated additions for particularly surprising/educational connections

---

### Etymology Trails

Visual traces showing how words evolved from roots.

#### Toggle Behaviour

Etymology is a visibility layer:
- **Off by default:** Clean thesaurus view
- **Toggle on:** Root trails appear throughout visible space

#### Visual Representation

When enabled:
- **Glowing trails** connect words sharing roots
- **Root nodes:** Ancient roots appear as special markers
- **Colour coding:** Latin (gold), Greek (blue), Germanic (silver), Other (white)

#### Trail Navigation

- Click any trail to highlight the full word family
- Navigate along trails to explore etymological relationships
- "Ancestor words" (extinct forms) appear as ghostly markers

#### Educational Value

Etymology trails teach:
- Why words are related ("salary" from "salt")
- Language history (Latin influence on English)
- Word formation patterns (prefixes, suffixes, roots)

#### Example

Viewing "telephone":
- Trail connects to "television", "telegraph", "telescope"
- Root node: Greek "tele-" (far)
- Additional trail to "phone", "phonetic", "symphony"
- Root node: Greek "phone-" (sound/voice)

---

### Word Hunt System

A daily quest to find a hidden word through semantic navigation.

#### Core Concept

Each day, a curated word is hidden in the Metaforge. Users receive cryptic clues and must navigate semantic space to find it. The hunt teaches vocabulary and relationships through play.

#### Hunt Modes

| Mode | Description | Audience |
|------|-------------|----------|
| **Timed** | Full scoring, timer running | Competitive players |
| **Relaxed** | No timer, no scoring, just exploration | Casual learners |

Users choose mode before starting.

#### Daily Reset

- New word at midnight (user's local time)
- Previous day's hunt remains available for 24 hours (marked "yesterday")
- Streak tracking for consecutive completions

#### Clue System

**Progressive clues:**
```
Clue 1 (Starting point): "Begin at OCEAN"
Clue 2 (Direction):      "Seek what is vast but not wet"
Clue 3 (Relationship):   "The answer is an antonym of 'confined'"
Clue 4 (Register):       "Writers use this word in poetry, rarely in essays"
Clue 5 (Final hint):     "Rhymes with 'ace'"

Answer: SPACE
```

**Clue types teach semantic relationships:**

| Clue Type | What It Teaches |
|-----------|-----------------|
| "Begin at X" | Starting vocabulary anchor |
| "Seek what is Y but not Z" | Synonym/antonym differentiation |
| "Relates to X as Y relates to Z" | Analogical reasoning |
| "Formal/informal contexts" | Register awareness |
| "Shares a root with X" | Etymology |
| "Follow the metonyms of X" | Associative thinking |

**Clue request:**
- Users can request next clue at any time
- In timed mode: clue requests reduce score
- In relaxed mode: unlimited clues, no penalty

#### Scoring (Timed Mode Only)

```
Base score:     1000 points
Time penalty:   -1 point per second
Clue penalty:   -100 points per clue requested (after Clue 1)

Bonuses:
  +200  for finding without Clue 5
  +500  for finding without Clues 4 or 5
  +1000 for finding with only Clue 1 (legendary)
```

#### Navigation During Hunt

**Starting state:**
- User placed at starting word (Clue 1)
- Timer begins (timed mode) or not (relaxed mode)
- Full gravity physics activate
- Visualisation enters "Hunt mode" with subtle visual shift

**Hunt navigation:**
- Full spaceship feel -- momentum, gravity, slingshots
- All relationship layers visible (synonyms, antonyms, metonyms)
- Wormholes remain hidden but discoverable (lucky shortcut!)
- Gravity wells are obstacles requiring skill to navigate

**Click-to-copy pauses hunt:**
- If user clicks to copy a word (for their actual writing), hunt pauses
- Timer stops, "Hunt Paused" indicator appears
- Resume button to continue
- Prevents hunt from interfering with thesaurus utility

#### Portal Mechanic

Occasionally (approximately 1 in 10 hunts), a gravity-well word contains a hidden portal:

- Portal leads directly to the target word
- Creates risk/reward: "Do I fight through this gravity well hoping for a portal?"
- Portals are scripted per-hunt (future: AI-generated)
- Discovery is a delightful surprise

#### Finding the Target

When user navigates to the correct word:

1. **Triumphant animation:** Word "unlocks" with visual celebration
2. **Sound effect:** Victory audio
3. **Score display:** (Timed mode) Final score with breakdown
4. **Collection update:** Word added with "Hunted" badge
5. **Streak update:** Consecutive day count incremented
6. **Constellation update:** New star with gold glow

#### Personal Records

Tracked statistics:
- Best time (overall)
- Best score (overall)
- Longest streak (consecutive days)
- "Legendary finds" count (Clue 1 only)
- Total hunts completed

#### Difficulty Tiers

As users improve, difficulty scales:

| Tier | Unlocked After | Features |
|------|----------------|----------|
| **Novice** | Default | 5 clues; generous time; weak gravity |
| **Explorer** | 7-day streak | 4 clues; moderate gravity |
| **Wayfinder** | 30-day streak | 3 clues; strong gravity; longer paths |
| **Lexicon Master** | 100-day streak | 2 clues; brutal gravity; obscure words |

Users can always drop to lower tier for relaxed play.

#### Vocabulary Level Tailoring (Future)

Hunts should match user's vocabulary level:
- Track which words user knows (from lookups, collections)
- Target words should be learnable but not frustrating
- "Just beyond current vocabulary" is the sweet spot
- Adaptive difficulty based on hunt success rate

#### Hunt Generation

**Daily hunt components:**
1. Target word selection (curated or algorithmic)
2. Starting word (semantically distant but reachable)
3. Progressive clues (teaching path)
4. Optional portal placement
5. Difficulty calibration

**AI-Assisted Generation (Admin Tool, Future):**
- AI selects target word based on criteria
- AI generates clue sequence
- AI validates hunt is solvable (pathfinding)
- Human reviews before publishing

#### Multiplayer (Future)

**Asynchronous:**
- Daily leaderboards (opt-in)
- Friends list with score comparison
- Weekly tournaments with themed hunts

**Synchronous:**
- "Race" mode: same hunt, same start, first to find wins
- Spectator mode for tournaments
- Classroom integration (teacher sets hunt, students race)

---

### Ambient Soundscape

Generative audio that makes the Metaforge feel alive.

#### Behaviour

- **On load:** Sound is paused/muted
- **On first navigation:** Sound fades in gradually
- **User control:** Can be turned off in settings; preference persists
- **If explicitly disabled:** Remains off until user re-enables

#### Sound Design

**Semantic regions have tonal signatures:**

| Region Type | Sound Character |
|-------------|-----------------|
| Abstract/philosophical | Sustained, ethereal tones |
| Concrete/physical | Percussive, grounded sounds |
| Emotional words | Harmonic, melodic |
| Rare/archaic words | Mysterious, distant |
| Gravity wells | Low rumble, tension |

**Movement creates music:**
- Navigation speed affects rhythm
- Changing regions creates melodic transitions
- Discovering wormholes has distinctive sound
- Hunt victory has triumphant audio

#### Implementation Notes

- Web Audio API for generative sound
- Pre-composed stems that layer based on context
- Low CPU usage (runs efficiently in background)
- Graceful degradation if audio fails

---

### Future Considerations

#### Phase 1 (MVP)

- Core thesaurus functionality
- 3D visualisation with synonyms/antonyms
- Basic constellation (auto-generated)
- Word Hunt (daily, single-player)

#### Phase 2

- Metonym layer
- Etymology trails
- Collection system with badges
- Wormhole discovery

##### New Ideas 20260207

1. Consider vocabularysize.com [see Collaborators & Networking](./docs/gtm/collaborators-and-networking-202602.md#vocabularysizecom).
[UPDATE Feb 7: we are shelving this idea for now -- turns into a marketing sharkfest to try and eat your competitors. Fuck that. Fuck them all. We just build what we need and want, for us. I sure as hell ain't going back to school.]
Based upon their seemingly authoritative comments, this app may provide considerable utility for non-native English speakers looking to increase their vocabulary, and educators looking to measure their students' vocab. Therefore:
    - ESOL Student Track Design
    - Vocabulary Size Testing Track Design

2. Also investigate whether, and if so how, it would benefit the app to replace word frequency calcs with *word familiarity* as described in [AI-based estimates of word familiarity](docs/designs/research/AI-based%20estimates%20of%20word%20familiarity%20final.pdf), which I downloaded from the [this page](https://osf.io/zq49t/files/kf9vg) on the Open Science Foundation's website while retrieving the latest SUBTLEX-UK dataset (OSF hosts the canonical version apparently).

3. Do a proper survey of the [field of "vocabulary studies"](docs/gtm/collaborators-and-networking-202602.md#list-from-vocabularysizecoms-faq-section) (or whatever it calls itself). The link is a head-start in that direction perhaps.

#### Phase 3

- Metaphor Forge
- Ambient soundscape
- Hunt difficulty tiers

#### Phase 4

- User accounts and sync
- Multiplayer hunts
- Leaderboards
- Classroom/teacher tools

#### Phase 5

- AI-assisted hunt generation
- Vocabulary level adaptation
- Additional languages
- Mobile app (if demand)

---

### Open Questions (from original PRD)

1. **User accounts:** Required for leaderboards and sync. What's the simplest auth approach for self-hosted?
2. **Hunt curation:** Who creates daily hunts? Volunteer curators? Algorithmic? AI-assisted?
3. **Moderation:** If user constellations become public, how do we handle inappropriate naming?
4. **Mobile:** If demand emerges, what's the mobile UX? Separate app or responsive web?

---

### Appendix: Example Hunt

**Target word:** EPHEMERAL

**Clues:**
```
Clue 1: "Begin at FOREVER"
Clue 2: "Seek its opposite — what does not last"
Clue 3: "Not 'temporary' — something more poetic"
Clue 4: "From Greek, meaning 'lasting only a day'"
Clue 5: "Begins with E, ends with L"
```

**Teaching path:**
- Clue 1 → Clue 2: Antonym relationship
- Clue 2 → Clue 3: Register distinction (common vs poetic)
- Clue 3 → Clue 4: Etymology as differentiator
- Clue 4 → Clue 5: Final letter hint if needed

**Optimal navigation:**
1. Start at FOREVER
2. Navigate to antonym region
3. Pass through TEMPORARY, FLEETING
4. Arrive at EPHEMERAL

**Gravity wells encountered:** ETERNAL, TIME, MOMENT (common words in this region)

**Possible portal:** MOMENT might contain portal (thematic connection to "lasting only a day")