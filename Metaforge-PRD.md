# Metaforge

## Product Requirements Document

**Version:** 2.0
**Last Updated:** 2026-01-25
**Status:** Design Complete, Pending Technical Review

---

## Executive Summary

Metaforge is a browser-based visual thesaurus that transforms vocabulary exploration into a spatial adventure. It combines the utility of a fully-featured thesaurus with the wonder of navigating a semantic universe.

**Primary constraint:** Metaforge must function as a feature-complete, easy-to-use thesaurus first. All game mechanics and exploration features enhance but never obstruct core utility.

**Target audience:** Young adults, students, and creative writers -- anyone from a 12-year-old writing their first story to an adult novelist seeking the perfect word.

**Platform:** Desktop-first (writers use laptops), browser-based, fully self-hosted, open-source, no paid API dependencies.

---

## Design Principles

### 1. Utility First, Wonder Second

The thesaurus must work flawlessly. A user needing a synonym for "happy" must find it in under 3 seconds. Game elements are layered on top, never blocking access.

### 2. Progressive Depth

```
Layer 0: Functional thesaurus (search → results → copy)
Layer 1: Beautiful visualisation (same data, rendered as space)
Layer 2: Enrichment (etymology, rarity, collections)
Layer 3: Creative tools (Metaphor Forge, constellations)
Layer 4: Game systems (Word Hunt)
```

Users naturally discover deeper layers through use. Nothing is gated or hidden from thesaurus functionality.

### 3. Two Modes of Use

| Mode | User State | Design Priority |
|------|------------|-----------------|
| **Lookup** | "I need a word NOW" | Speed, scannability, clarity |
| **Explore** | "I wonder what's near this word..." | Beauty, surprise, serendipity |

The interface serves both simultaneously.

### 4. Spaceship Navigation

Moving through the Metaforge should feel like piloting a craft through space. Words exert gravitational pull. Skilled navigators learn to slingshot around gravity wells, finding efficient paths through semantic space.

---

## User Interface Layout

```
┌─────────────────────────────────────────────────────────────────────┐
│  [Search...]                            [Hunt] [Forge] [Settings]   │
├───────────────────────┬─────────────────────────────────────────────┤
│                       │                                             │
│   RESULTS PANEL       │         3D VISUALISATION                    │
│                       │                                             │
│   ┌─────────────────┐ │              ★ melancholy                   │
│   │ melancholy      │ │             /    \      \                   │
│   │ ───────────────-│ │        ○ sad    ○ wistful  ○ pensive        │
│   │ Uncommon | Poetic │           |         \                       │
│   └─────────────────┘ │       ○ gloomy      ○ sorrowful             │
│                       │                                             │
│   Synonyms:           │                    ◉ ← gravity well (JOY)   │
│   • sad        [copy] │                                             │
│   • sorrowful  [copy] │                                             │
│   • gloomy     [copy] │                                             │
│   • wistful    [copy] │                                             │
│   • pensive    [copy] │                                             │
│                       │                                             │
│   Antonyms:           │                                             │
│   • happy      [copy] │                                             │
│   • cheerful   [copy] │                                             │
│   • joyful     [copy] │                                             │
│                       │ ┌─────┐                                     │
│   [▼ Metonyms]        │ │ ✧ ✧ │ ← constellation minimap            │
│   [▼ Etymology]       │ │✧ ✧✧ │                                    │
│                       │ └─────┘                                     │
├───────────────────────┴─────────────────────────────────────────────┤
│   "a melancholy autumn evening" — usage example                     │
└─────────────────────────────────────────────────────────────────────┘
```

### Panel Descriptions

**Search Bar:** Always visible, always prominent. Keyboard shortcut: `/`. Autocomplete with live results.

**Results Panel:** Scannable text list of synonyms, antonyms, and metonyms. Each word shows rarity badge and register. Click to copy. Right-click to navigate (make that word the new centre).

**3D Visualisation:** The semantic solar system. Words rendered as celestial bodies. Current word is the central star. Related words orbit based on relationship type and strength.

**Constellation Minimap:** Small icon in corner showing user's personal constellation. Click to expand to full map view.

**Usage Example:** Shows the current word used in context. Helps users judge appropriateness.

### Interaction Model

| Action | Input |
|--------|-------|
| Search | Type in search bar or press `/` |
| Copy word | Click word in results panel |
| Navigate to word | Right-click word (panel or visualisation) |
| Orbit camera | Drag in visualisation |
| Zoom | Scroll wheel |
| Fly/Pan | WASD keys or right-click drag |
| Open constellation | Click minimap |
| Pin to collection | Double-click or long-press word |

---

## Core Thesaurus System

The foundation. Everything else builds on this.

### Search

- **Instant results:** Results appear as user types
- **Fuzzy matching:** Handles typos and partial matches
- **Recent searches:** Quick access to previous lookups

### Results Display

For each word, display:

- **The word itself**
- **Rarity badge:** Common / Uncommon / Rare / Archaic
- **Register badge:** Formal / Neutral / Informal / Slang
- **Connotation indicator:** Positive / Neutral / Negative (subtle colour coding)
- **Part of speech:** Noun, verb, adjective, etc

### Relationship Types

| Type | Description | Visual Representation |
|------|-------------|----------------------|
| **Synonyms** | Words with similar meaning | Close orbit around central star |
| **Antonyms** | Words with opposite meaning | Positioned opposite the central star, contrasting colours |
| **Metonyms** | Words related by association | Connected via visible "tethers" or trails |

### Word Information

Selecting a word reveals:

- **Definition:** Clear, concise meaning
- **Part of speech:** With inflections
- **Usage examples:** 1-2 sentences showing the word in context
- **Rarity/Register:** How common, how formal
- **Etymology:** Word origin (expandable)

### Results Ordering

- **Default:** Similarity (closest synonyms first)
- **Future options:** Alphabetical, frequency, register
- **Architecture note:** Design data layer to support configurable ordering

---

## 3D Visualisation System

The semantic solar system that transforms lookup into exploration.

### Visual Representation

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

### Relationship Modes

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

### Navigation

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

### Visual Feedback

- **Hover:** Word glows, label appears
- **Selection:** Smooth transition as new word becomes centre
- **Previously visited:** Words glow brighter (luminosity gradient)
- **Rare words:** Distinct visual treatment (special glow or particle effect)

### Performance Considerations

- **Dynamic loading:** Only render visible region plus buffer
- **Level of detail:** Distant words render as simple points
- **Spatial indexing:** Efficient lookup for nearby words

---

## Gravity System

All words exert gravitational pull. This creates navigation texture and reflects linguistic reality -- common words dominate thought.

### How Gravity Works

**Every word has gravity** proportional to its frequency:

| Word Type | Gravity Strength | Examples |
|-----------|------------------|----------|
| Ultra-common | Very strong | the, is, and, to |
| High-frequency emotional | Strong | love, death, time, money, happy |
| Common words | Moderate | walk, think, house, small |
| Uncommon words | Weak | melancholy, ephemeral, sanguine |
| Rare words | Very weak | defenestration, petrichor |

### Gravity Wells

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

### Gravity in Different Contexts

| Context | Gravity Behaviour |
|---------|-------------------|
| Normal thesaurus use | Gravity is visual only; no navigation impediment |
| Word Hunt (active) | Full gravity physics; wells are obstacles |
| Word Hunt (relaxed) | Reduced gravity; wells are landmarks only |

---

## Constellation System

Users build a personal map of their journey through the Metaforge.

### Automatic Generation

As users navigate:

1. **Each visited word becomes a star** in their personal constellation
2. **Navigation paths become lines** connecting stars
3. **The constellation grows organically** with use

No manual action required -- exploration naturally builds the map.

### The Constellation View

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

### Persistence

- **Without account:** Stored in browser local storage
- **With account:** Synced to server
- **Reset option:** "Start a new constellation" clears history
- **Export:** Download constellation as image (shareable)

### Future Features

- Public constellation gallery
- Share constellation as "guided tour"
- Compare constellations with friends
- Teacher-assigned constellation challenges

---

## Collection System

A personal vocabulary cabinet for pinning and collecting words.

### The Specimen Cabinet

Users curate a personal collection of favourite or interesting words.

**Adding words:**
- Double-click any word to pin it
- Long-press on mobile
- "Pin" button in word info panel

**Collection organisation:**
- Words displayed in a grid or list
- Sortable by: date added, alphabetical, rarity, category
- User can create custom folders/tags

### Word Badges

Collected words display earned badges:

| Badge | Earned By |
|-------|-----------|
| Hunted | Found during Word Hunt |
| Rare | Word is uncommon in corpus |
| Endangered | Archaic or obsolete word |
| Wormhole | Discovered via wormhole connection |
| Forged | Used in Metaphor Forge |

### Rarity System

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

### Word Families

Words sharing etymological roots form "genera":

- Collecting all words from a root completes a "word family"
- Visual indicator shows completion progress
- Completed families earn special recognition

### Annotations

Users can add personal notes to collected words:
- "Used this in my story about the lighthouse"
- "Perfect for describing autumn"

### Export & Sharing

- **Export collection:** JSON, CSV, or printable PDF
- **"Linguistic passport":** Shareable summary of collection stats
- **Future:** Public profiles showing collection highlights

---

## Wormholes (Surprising Connections)

Hidden connections between semantically distant but structurally analogous words.

### What Are Wormholes?

Wormholes connect words that:
- Belong to different semantic domains (high distance)
- Share deep structural properties (analogous relationships)

**Example:** "Grief" ↔ "Anchor"
- Different domains (emotion vs nautical)
- Shared structure: Both hold something in place, preventing movement

### Discovery Mechanics

Wormholes are **hidden until discovered**. Discovery triggers:

1. **Visit both endpoints** in a single session
2. **Linger on a word** long enough to "sense" distant resonance
3. **Use Metaphor Forge** successfully with the pair
4. **Navigate near** an undiscovered wormhole (proximity trigger)

### Discovery Moment

When discovered:

1. **Dramatic animation:** Visual tear in space connecting two distant points
2. **Sound effect:** Distinctive "wormhole open" audio cue
3. **Notification:** "You discovered a wormhole between [Word A] and [Word B]!"
4. **Naming opportunity:** User can give the wormhole a personal name
5. **Collection update:** Both words added to collection with "Wormhole" badge
6. **Constellation update:** Special connector line appears on map

### Wormhole Travel

Once discovered:
- Wormhole remains visible on subsequent visits
- Clicking the wormhole instantly transports to the other endpoint
- Creates shortcuts through semantic space

### Treasure Display

Discovered wormholes appear in:
- **Collection:** Special "Wormholes" section
- **Constellation:** Distinctive connection lines
- **Profile:** Bragging rights -- "12 wormholes discovered"

### Wormhole Data Source

Wormholes are pre-computed based on:
- Embedding distance (semantic dissimilarity)
- ConceptNet relational overlap (structural similarity)
- Curated additions for particularly surprising/educational connections

---

## Etymology Trails

Visual traces showing how words evolved from roots.

### Toggle Behaviour

Etymology is a visibility layer:
- **Off by default:** Clean thesaurus view
- **Toggle on:** Root trails appear throughout visible space

### Visual Representation

When enabled:
- **Glowing trails** connect words sharing roots
- **Root nodes:** Ancient roots appear as special markers
- **Colour coding:** Latin (gold), Greek (blue), Germanic (silver), Other (white)

### Trail Navigation

- Click any trail to highlight the full word family
- Navigate along trails to explore etymological relationships
- "Ancestor words" (extinct forms) appear as ghostly markers

### Educational Value

Etymology trails teach:
- Why words are related ("salary" from "salt")
- Language history (Latin influence on English)
- Word formation patterns (prefixes, suffixes, roots)

### Example

Viewing "telephone":
- Trail connects to "television", "telegraph", "telescope"
- Root node: Greek "tele-" (far)
- Additional trail to "phone", "phonetic", "symphony"
- Root node: Greek "phone-" (sound/voice)

---

## Metaphor Forge

A creative tool for generating novel metaphors by finding non-obvious connections.

### Concept: Alchemy, Not Lists

The Forge presents metaphor creation as active combination, not passive retrieval.

### Forge Interface

```
┌─────────────────────────────────────────────────────┐
│                 METAPHOR FORGE                      │
├─────────────────────────────────────────────────────┤
│                                                     │
│   SOURCE WORD          CATALYST                     │
│   ┌─────────┐         ┌─────────┐                  │
│   │  GRIEF  │    +    │    ?    │                  │
│   └─────────┘         └─────────┘                  │
│                                                     │
│   Suggested Catalysts:                              │
│   • Anchor (holds in place)                        │
│   • Stone (heavy, immovable)                       │
│   • Tide (comes in waves)                          │
│   • Shadow (follows you)                           │
│                                                     │
│   [FORGE]                                          │
│                                                     │
└─────────────────────────────────────────────────────┘
```

### Forging Process

1. **Source word:** User drags current word to the Forge (or clicks "Forge" button)
2. **Catalyst suggestions:** System suggests structurally analogous but distant words
3. **Selection:** User chooses a catalyst (or enters their own)
4. **Animation:** Forge animates -- collision, fusion, sparks
5. **Result:** Metaphor artifact is created

### Metaphor Output

Each forged metaphor includes:

- **The metaphor:** "Grief is an anchor"
- **The bridge:** Explanation of the structural connection ("Both hold something firmly in place, preventing movement")
- **Variations:**
    - Simple: "[Source] is a [Target]"
    - Explanatory: "Think of [Source] as a [Target], because both [Bridge]"
    - Nuanced: "The [aspect of Source] is like the [aspect of Target]"
- **Example sentence:** "Grief can be an anchor, holding you fast in the harbour of sorrow"

### Quality Tiers

Metaphors are rated by quality:

| Tier | Criteria | Visual |
|------|----------|--------|
| Common | Obvious connections, low distance | Bronze glow |
| Rare | Surprising but clear, moderate distance | Silver glow |
| Legendary | Genuinely novel, high distance + strong bridge | Gold glow |

### Risk/Reward

- Common words yield common metaphors
- Rare specimens risk failure but can yield legendary results
- Failed forges reveal *why* the connection didn't work (educational)

### The Grimoire

Forged metaphors are stored in a personal "Grimoire":
- Organised by source word, quality tier, or date
- Searchable and browsable
- Exportable for use in writing

### Backend Logic

**Analyse source properties:**
- Semantic properties from embeddings
- ConceptNet relations (HasProperty, UsedFor, IsA)
- Common collocations and domains

**Find candidates:**
- High embedding distance (different domain)
- Relational overlap (shared abstract properties)
- Filter nonsensical combinations

**Generate output:**
- Template-based metaphor construction
- Bridge explanation from shared properties

---

## Word Hunt System

A daily quest to find a hidden word through semantic navigation.

### Core Concept

Each day, a curated word is hidden in the Metaforge. Users receive cryptic clues and must navigate semantic space to find it. The hunt teaches vocabulary and relationships through play.

### Hunt Modes

| Mode | Description | Audience |
|------|-------------|----------|
| **Timed** | Full scoring, timer running | Competitive players |
| **Relaxed** | No timer, no scoring, just exploration | Casual learners |

Users choose mode before starting.

### Daily Reset

- New word at midnight (user's local time)
- Previous day's hunt remains available for 24 hours (marked "yesterday")
- Streak tracking for consecutive completions

### Clue System

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

### Scoring (Timed Mode Only)

```
Base score:     1000 points
Time penalty:   -1 point per second
Clue penalty:   -100 points per clue requested (after Clue 1)

Bonuses:
  +200  for finding without Clue 5
  +500  for finding without Clues 4 or 5
  +1000 for finding with only Clue 1 (legendary)
```

### Navigation During Hunt

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

### Portal Mechanic

Occasionally (approximately 1 in 10 hunts), a gravity-well word contains a hidden portal:

- Portal leads directly to the target word
- Creates risk/reward: "Do I fight through this gravity well hoping for a portal?"
- Portals are scripted per-hunt (future: AI-generated)
- Discovery is a delightful surprise

### Finding the Target

When user navigates to the correct word:

1. **Triumphant animation:** Word "unlocks" with visual celebration
2. **Sound effect:** Victory audio
3. **Score display:** (Timed mode) Final score with breakdown
4. **Collection update:** Word added with "Hunted" badge
5. **Streak update:** Consecutive day count incremented
6. **Constellation update:** New star with gold glow

### Personal Records

Tracked statistics:
- Best time (overall)
- Best score (overall)
- Longest streak (consecutive days)
- "Legendary finds" count (Clue 1 only)
- Total hunts completed

### Difficulty Tiers

As users improve, difficulty scales:

| Tier | Unlocked After | Features |
|------|----------------|----------|
| **Novice** | Default | 5 clues; generous time; weak gravity |
| **Explorer** | 7-day streak | 4 clues; moderate gravity |
| **Wayfinder** | 30-day streak | 3 clues; strong gravity; longer paths |
| **Lexicon Master** | 100-day streak | 2 clues; brutal gravity; obscure words |

Users can always drop to lower tier for relaxed play.

### Vocabulary Level Tailoring (Future)

Hunts should match user's vocabulary level:
- Track which words user knows (from lookups, collections)
- Target words should be learnable but not frustrating
- "Just beyond current vocabulary" is the sweet spot
- Adaptive difficulty based on hunt success rate

### Hunt Generation

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

### Multiplayer (Future)

**Asynchronous:**
- Daily leaderboards (opt-in)
- Friends list with score comparison
- Weekly tournaments with themed hunts

**Synchronous:**
- "Race" mode: same hunt, same start, first to find wins
- Spectator mode for tournaments
- Classroom integration (teacher sets hunt, students race)

---

## Ambient Soundscape

Generative audio that makes the Metaforge feel alive.

### Behaviour

- **On load:** Sound is paused/muted
- **On first navigation:** Sound fades in gradually
- **User control:** Can be turned off in settings; preference persists
- **If explicitly disabled:** Remains off until user re-enables

### Sound Design

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

### Implementation Notes

- Web Audio API for generative sound
- Pre-composed stems that layer based on context
- Low CPU usage (runs efficiently in background)
- Graceful degradation if audio fails

---

## Accessibility

The visualisation enhances but never replaces text functionality.

### Keyboard Navigation

- `/` Focus search bar
- `Tab` Move through results
- `Enter` Copy selected word
- `Shift+Enter` Navigate to selected word
- `Escape` Close panels, cancel hunt
- Arrow keys Navigate results list

### Screen Reader Support

- Results panel is fully accessible text
- Word information announced on selection
- Hunt clues and status announced
- Constellation provides text description

### Visual Accessibility

- **Reduced motion:** Option to disable animations
- **High contrast:** Toggle for visibility
- **Colour blind modes:** Alternative colour schemes
- **Font scaling:** Respects browser zoom

### Hunt Accessibility

- Relaxed mode for users who can't use timed challenges
- All clues available as text
- Victory achieved through any valid navigation path

---

## Data Requirements

### Lexical Database

**Primary sources:**
- WordNet: Definitions, synonyms, antonyms, hypernyms, hyponyms
- ConceptNet: Broader relations (HasProperty, UsedFor, PartOf, etc)
- Word frequency corpus: For rarity classification
- Etymology database: For root trails

**Derived data:**
- Word embeddings: For similarity calculations
- Pre-computed wormholes: Distant but structurally similar pairs
- Pre-computed metaphor bridges: For Forge suggestions

### Data Format

- Static JSON/SQLite for core vocabulary
- No runtime API calls to external services
- All data bundled or self-hosted
- Caching strategy for performance

---

## Technical Considerations

*To be expanded in Technical Review*

### Frontend

- React or similar for UI state management
- Three.js or Babylon.js for WebGL 3D rendering
- Web Audio API for soundscape
- Local storage for user data (no-account mode)

### Backend (if needed)

- Static file hosting may suffice for core functionality
- Optional backend for:
    - User accounts and sync
    - Leaderboards
    - Hunt generation
- Python or Node.js

### Performance

- Dynamic loading: Only visible region + buffer
- Level of detail: Distant words as simple points
- Spatial indexing: k-d trees for efficient neighbour lookup
- Target: 60fps on mid-range hardware

---

## Future Considerations

### Phase 1 (MVP)

- Core thesaurus functionality
- 3D visualisation with synonyms/antonyms
- Basic constellation (auto-generated)
- Word Hunt (daily, single-player)

### Phase 2

- Metonym layer
- Etymology trails
- Collection system with badges
- Wormhole discovery

### Phase 3

- Metaphor Forge
- Ambient soundscape
- Hunt difficulty tiers

### Phase 4

- User accounts and sync
- Multiplayer hunts
- Leaderboards
- Classroom/teacher tools

### Phase 5

- AI-assisted hunt generation
- Vocabulary level adaptation
- Additional languages
- Mobile app (if demand)

---

## Open Questions

1. **User accounts:** Required for leaderboards and sync. What's the simplest auth approach for self-hosted?
2. **Hunt curation:** Who creates daily hunts? Volunteer curators? Algorithmic? AI-assisted?
3. **Moderation:** If user constellations become public, how do we handle inappropriate naming?
4. **Mobile:** If demand emerges, what's the mobile UX? Separate app or responsive web?

---

## Appendix: Example Hunt

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
