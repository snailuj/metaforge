# Metaforge Implementation Plan

---

## ⚠️ NON-NEGOTIABLE DEVELOPMENT STANDARDS ⚠️

**These apply to ALL phases. No exceptions. No shortcuts.**

| Standard | What It Means |
|----------|---------------|
| **TDD (Red/Green)** | Write failing test FIRST. Then write minimal code to pass. Then refactor. Every feature, every bugfix. |
| **Frequent Commits** | Commit after each green test. Small, atomic commits. Never batch up changes. |
| **CI/CD** | All commits trigger automated test runs. No merging with failing tests. Automated deployment pipeline. |
| **Canary Releases** | New features deploy to subset of users first. Monitor for errors before full rollout. |

**If you're about to write code without a failing test, STOP.**

**If you have uncommitted green tests, STOP and commit.**

---

## Architecture Decision

**Headless API + Thin Client**

```
┌─────────────────────────────────────────────────────┐
│              Metaforge API (Go)                     │
│         Stateless, self-hostable                    │
├─────────────────────────────────────────────────────┤
│  GET  /search?q={term}                              │
│  GET  /word/{lemma}                                 │
│  GET  /word/{lemma}/relations?type={syn|ant|met}    │
│  GET  /forge/suggest?source={word}                  │
│  POST /forge                                        │
│  GET  /hunt/today                                   │
│  GET  /wormholes/near?word={word}                   │
└──────────┬────────────────────┬─────────────────────┘
           │                    │
    ┌──────▼──────┐      ┌──────▼──────┐
    │ Browser     │      │ Native      │
    │ (Three.js/  │      │ (Unity/     │
    │  WebGPU)    │      │  Godot)     │
    │             │      │  [Future]   │
    └─────────────┘      └─────────────┘
```

**Rationale:**
- Clean separation of data logic and rendering
- Browser-first for accessibility (writers need instant access)
- Native client can be added later if browser performance insufficient
- Client-side caching to tune latency vs memory trade-off
- Go backend: efficient, scalable, neat

---

## Visual Direction

**Theme: Antique/Alchemical** (primary)

- Sepia/parchment aesthetic with brass/wood UI elements
- Central word as golden sun with detailed surface
- Planets with painterly textures, realistic lighting (lit/dark sides)
- Gravity wells as tornado vortices
- Scroll-style results panel, telescope motifs

**Why antique first:**
- Easier for browser (less post-processing than cosmic glow effects)
- Painterly style is forgiving - doesn't require photorealism
- User preference aligns with pragmatic choice
- Cosmic theme can be added as "deluxe" option later

**Rendering approach:**
- Exclusive toggle for relationship types (one at a time)
- Reduces scene complexity and improves clarity
- Animate transitions when switching types

---

## Tech Stack

| Layer | Technology | Rationale |
|-------|------------|-----------|
| Backend API | Go + Chi router | Efficient, user preference |
| Database | SQLite (embedded) | Self-contained, no external DB needed |
| Embeddings | Binary file + kd-tree | Fast similarity lookups |
| Frontend | TypeScript + Vite | Modern tooling, fast HMR |
| 3D Rendering | Three.js + WebGPU | Browser-first, upgrade path to native |
| State | Zustand | Minimal, FP-friendly |
| Caching | IndexedDB | Tune cache size for latency/memory |

---

## Data Sources

1. **Open English WordNet** - definitions, synonyms, antonyms
2. **ConceptNet 5.7** (filtered to English) - HasProperty, UsedFor, PartOf relations
3. **GloVe embeddings** (100d) - similarity calculations
4. **Word frequency corpus** - rarity classification

---

## MVP Scope

**Includes:**
- Core thesaurus (search, results, copy)
- 3D visualization (antique theme)
- Metaphor Forge (key differentiator)
- Basic constellation
- Word Hunt (daily quest)

**Excludes from MVP:**
- Wormhole discovery (Phase 2 - uses same infra as Forge)
- Etymology trails (Phase 2)
- Collection system with badges (Phase 2)
- Ambient soundscape (Phase 3)
- User accounts/sync (Phase 4)
- Native client (if needed)

---

## Implementation Phases

### Phase 0: Data Pipeline + Metaphor Forge (Sprint Zero)

**Goal:** Prove out the data infrastructure with a tangible demo

| Task | Description |
|------|-------------|
| 0.1 | Set up Go project structure |
| 0.2 | Import WordNet SQLite, design schema |
| 0.3 | Filter and import ConceptNet relations |
| 0.4 | Load GloVe embeddings, build kd-tree index |
| 0.5 | Implement `/forge/suggest` endpoint |
| 0.6 | Implement `/forge` endpoint (generate metaphor) |
| 0.7 | Simple CLI or curl-based testing |

**Deliverable:** `curl localhost:8080/forge/suggest?source=grief` returns catalyst suggestions

**Why first:**
- Forces embedding + similarity infrastructure
- Same foundation needed for wormholes
- Tangible demo before 3D complexity
- Validates the differentiating feature

### Phase 1: Core API

| Task | Description |
|------|-------------|
| 1.1 | `/search` endpoint with fuzzy matching |
| 1.2 | `/word/{lemma}` - full word info |
| 1.3 | `/word/{lemma}/relations` - filtered by type |
| 1.4 | Add rarity/register classification |
| 1.5 | API tests |

**Deliverable:** Complete thesaurus API

### Phase 2: Browser Client - Thesaurus

| Task | Description |
|------|-------------|
| 2.1 | Vite + TypeScript scaffolding |
| 2.2 | API client with caching layer (IndexedDB) |
| 2.3 | Search bar with instant results |
| 2.4 | Results panel (antique scroll style) |
| 2.5 | Copy-to-clipboard |
| 2.6 | Keyboard navigation (`/` to search, Tab, Enter) |

**Deliverable:** Functional text thesaurus in browser

### Phase 3: 3D Visualization

| Task | Description |
|------|-------------|
| 3.1 | Three.js + WebGPU setup |
| 3.2 | Antique theme: parchment background, UI frame |
| 3.3 | Central sun rendering (golden, detailed) |
| 3.4 | Planet rendering with PBR lighting |
| 3.5 | Orbital layout from similarity data |
| 3.6 | Camera controls (orbit, zoom, WASD) |
| 3.7 | Word selection (click planet to navigate) |
| 3.8 | Relationship type toggle with transitions |
| 3.9 | Gravity well visualization (vortex) |

**Deliverable:** Interactive 3D semantic solar system

### Phase 4: Metaphor Forge UI

| Task | Description |
|------|-------------|
| 4.1 | Forge panel (alchemical aesthetic) |
| 4.2 | Source word selection |
| 4.3 | Catalyst suggestions display |
| 4.4 | Forge animation |
| 4.5 | Metaphor output with bridge explanation |
| 4.6 | Grimoire (saved metaphors) |

**Deliverable:** Full Metaphor Forge experience

### Phase 5: Constellation

| Task | Description |
|------|-------------|
| 5.1 | Visit tracking (IndexedDB) |
| 5.2 | Path recording |
| 5.3 | Minimap rendering (2D star chart) |
| 5.4 | Full map expansion |
| 5.5 | Click-to-navigate from constellation |

**Deliverable:** Personal journey map

### Phase 6: Word Hunt

| Task | Description |
|------|-------------|
| 6.1 | Hunt data format (JSON schema) |
| 6.2 | `/hunt/today` endpoint |
| 6.3 | Hunt mode UI overlay |
| 6.4 | Progressive clue system |
| 6.5 | Timer + scoring (timed mode) |
| 6.6 | Relaxed mode (no timer) |
| 6.7 | Victory state + streak tracking |

**Deliverable:** Daily semantic quest

### Phase 7: Polish

| Task | Description |
|------|-------------|
| 7.1 | Performance audit (target 60fps) |
| 7.2 | Cache tuning |
| 7.3 | Accessibility (keyboard, screen reader basics) |
| 7.4 | Error handling |
| 7.5 | Deployment setup (self-hosted) |

**Deliverable:** MVP complete

---

## Directory Structure

```
metaforge/
├── api/                          # Go backend
│   ├── cmd/
│   │   └── metaforge/
│   │       └── main.go
│   ├── internal/
│   │   ├── db/                   # SQLite access
│   │   ├── embeddings/           # Vector operations
│   │   ├── forge/                # Metaphor generation
│   │   ├── hunt/                 # Daily hunt logic
│   │   └── search/               # Fuzzy search
│   ├── data/
│   │   ├── lexicon.db            # WordNet + ConceptNet
│   │   ├── embeddings.bin        # GloVe vectors
│   │   └── hunts/                # Daily hunt JSON
│   ├── go.mod
│   └── go.sum
├── web/                          # Browser client
│   ├── src/
│   │   ├── api/                  # API client + cache
│   │   ├── components/
│   │   │   ├── layout/           # AppShell, SearchBar, ResultsPanel
│   │   │   ├── three/            # 3D components
│   │   │   ├── forge/            # Metaphor Forge UI
│   │   │   ├── constellation/    # Minimap, FullMap
│   │   │   └── hunt/             # Hunt mode UI
│   │   ├── stores/               # Zustand stores
│   │   ├── lib/                  # Utilities
│   │   └── types/
│   ├── public/
│   │   └── textures/             # Planet textures, UI assets
│   ├── package.json
│   └── vite.config.ts
├── data-pipeline/                # Python preprocessing
│   ├── scripts/
│   │   ├── 01_import_wordnet.py
│   │   ├── 02_filter_conceptnet.py
│   │   ├── 03_process_embeddings.py
│   │   └── 04_compute_wormholes.py
│   └── requirements.txt
├── Metaforge-PRD.md
└── README.md
```

---

## Key Files to Create

| File | Purpose |
|------|---------|
| `api/cmd/metaforge/main.go` | API entry point |
| `api/internal/db/schema.sql` | Database schema |
| `api/internal/forge/forge.go` | Metaphor generation logic |
| `api/internal/embeddings/kdtree.go` | Similarity lookups |
| `web/src/api/client.ts` | API client with caching |
| `web/src/components/three/SemanticSpace.tsx` | Main 3D canvas |
| `web/src/components/three/Planet.tsx` | Word planet rendering |
| `data-pipeline/scripts/01_import_wordnet.py` | Data import |

---

## Verification Plan

### Phase 0 (Forge)
```bash
# Start API
cd api && go run ./cmd/metaforge

# Test forge suggestion
curl "localhost:8080/forge/suggest?source=grief"
# Expected: {"suggestions": ["anchor", "stone", "tide", "shadow"]}

# Test forge generation
curl -X POST "localhost:8080/forge" -d '{"source":"grief","catalyst":"anchor"}'
# Expected: {"metaphor":"Grief is an anchor","bridge":"Both hold something in place"}
```

### Phase 2 (Thesaurus)
```bash
cd web && npm run dev
# Open localhost:5173
# Type "melancholy" in search
# Verify results appear <100ms
# Click word to copy, verify clipboard
```

### Phase 3 (3D)
- 3D scene renders with central sun
- Related words appear as planets
- Click planet navigates to that word
- Toggle relationship types, verify smooth transition
- Check FPS with browser DevTools (target: 60fps)

### Phase 6 (Hunt)
- Start daily hunt
- Verify clues display progressively
- Navigate to target word
- Verify victory animation and streak update

---

## Open Questions (Resolved)

| Question | Decision |
|----------|----------|
| UI Framework | TypeScript + minimal framework (Three.js manages 3D) |
| 3D Library | Three.js with WebGPU renderer |
| Backend | Go |
| Data pipeline | Python preprocessing |
| First milestone | Metaphor Forge (Phase 0) |
| Visual theme | Antique/alchemical (primary) |
| Relationship display | Exclusive toggle (one type at a time) |

---

## Risks

| Risk | Mitigation |
|------|------------|
| Browser 3D performance | Antique theme is lighter; native client as fallback |
| ConceptNet size | Filter aggressively to English + useful relations |
| Metaphor quality | Start with curated bridges; improve algorithm over time |
| Hunt content | Curate initial hunts manually; build editor tool later |
