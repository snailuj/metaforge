# Core Thesaurus Design

**Status:** Design Complete — data layer partially implemented (Sprint Zero), no frontend
**Priority:** High (Foundation for all other features)
**Dependencies:** String Handling (cross-cutting)

---

## Overview

The Core Thesaurus provides the foundational search and word lookup functionality that all other Metaforge features build upon. It follows the "Utility First" principle with fast, accurate word discovery while maintaining the modular architecture needed for future enhancements.

---

## Search System

> **Sprint Zero Status:** Not yet implemented. The API has `GetSynsetIDForLemma` for exact lemma lookup (prefers enriched synsets) but no fuzzy search, suggestions, or debounced search endpoint.

**Input:** Prominent search bar with keyboard shortcut `/` for quick access

**Behavior:** Live Results Panel updates as user types (simple debounce for performance). 3D visualization only updates on explicit word click to prevent jarring camera movements.

**Algorithm:** "Best Match + Suggestions" approach
- Valid inputs: Show closest semantic match
- Typos/unknown words: Display "Word not found" with 3-5 helpful suggestions
- Future enhancement: Hybrid semantic + spelling matching (post-MVP)

**Performance:** Simple debounce (tunable delay) to maintain responsiveness

---

## Results Panel Architecture

> **Sprint Zero Status:** Not yet implemented (frontend). No rendering strategies exist yet.

**Modular Strategy Pattern:** Three rendering algorithms swappable via feature flags

### Strategy A - Group by Sense (Default)
- Shows word's definition first
- Synonyms/antonyms grouped by specific meaning
- Ensures context-appropriate word selection

### Strategy C - Categorical Tabs
- Separate tabs for Synonyms, Antonyms (Metonyms tab added Phase 2+ pending research)
- Internal sense-grouping when expanded
- Clean visual separation

### Strategy B - Flat Similarity List
- Single ranked list by semantic similarity
- Fastest to scan but mixes meanings
- Simple implementation

**Word Entry Display:**
- Word itself
- Rarity badges (MVP — Common/Uncommon/Rare/Archaic via frequency corpus)
- Register badges (Phase 2 — piggybacks on frequency infrastructure)
- Part of speech
- Connotation indicators (Phase 2 — pending research spike)

**Progressive Disclosure:** Essential info by default, expandable sections for etymology and word family details

---

## Interaction Model

### Mouse Interaction (A/B Testable)

**Database Words** (russet colour + slight underline):

| Action | Option A (Traditional) | Option B (Thesaurus-First) |
|--------|------------------------|---------------------------|
| Left-click | Navigate to word | Copy to clipboard |
| Right-click | Context menu (copy, navigate) | Navigate to word |

Feature-flagged for A/B testing. Option A shown as default pending user research.

**UI Elements** (tabs, buttons, etc.):
- **Left-click:** Standard UI interactions
- **Right-click:** No special behaviour

### Keyboard Navigation

| Key | Action |
|-----|--------|
| `/` | Focus search bar |
| `Enter` | Navigate to selected word |
| `Spacebar` | Copy selected word to clipboard |
| `Tab` / `Shift+Tab` | Move through results |
| `Arrow keys` | Navigate results list |
| `Escape` | Close panels, cancel actions |

---

## Word Information System

**Essential Layer (always visible):**
- Definition
- Part of speech with inflections
- 1-2 usage examples (from WordNet where available, gracefully omit when not)
- Connotation indicators (Phase 2 — pending research spike)

**Results Ordering:** Semantic similarity only for MVP. Configurable sort options (alphabetical, frequency, register) in Phase 2.

**Expandable Sections:**
- **Etymology:** Word origin and root connections (Phase 2 — pending research spike)
- **Word Family:** Related words sharing etymological roots (Phase 2)
- **Usage Context:** Rarity details with corpus frequency (MVP), register (Phase 2)
- **Related Forms:** Inflections, derivatives, compounds

**Visual Design:** Clean typography with word prominently displayed, russet colour/underline for database words throughout

---

## Data Sources & Structure

**Primary Sources:**
- **SQLunet (OEWN/WordNet):** Definitions, synonyms, antonyms, hypernyms, hyponyms, part of speech — via `sqlunet_master.db`
- **VerbNet** (via SQLunet): Semantic roles, classes, usage examples for verb senses
- **SyntagNet** (via SQLunet): Collocation pairs for contiguity metonyms
- **FrameNet** (via SQLunet): Frame metadata — schema exists, not yet populated
- **Frequency Corpus:** SUBTLEX-UK or similar for rarity classification (Common/Uncommon/Rare/Archaic)
- **Etymology Database:** Etymological WordNet (2013) — research spike only, not wired into MVP

> **⚠️ Drift Check — ConceptNet dropped:** The original design relied on ConceptNet for broader relations (HasProperty, UsedFor, PartOf) and metonyms (SymbolOf). **ConceptNet was never integrated.** Instead, SQLunet provides the integrated data layer, and Gemini LLM extraction handles property enrichment. This appears to be a deliberate choice (Gemini produces better abstract properties than ConceptNet's spotty coverage), but ConceptNet's role for **non-property relations** (UsedFor, PartOf, SymbolOf for metonyms) has no replacement. Should these relations be extracted via Gemini too, or is ConceptNet still worth investigating for these specific edge types?

> **Sprint Zero Status — Frequency data:** The `frequencies` table exists in the schema but is **empty**. No frequency corpus has been imported. Rarity badges cannot work until this is addressed. Consider: SUBTLEX-UK, or derive frequency proxy from lemma polysemy count (number of synsets per lemma).

**Derived Data:**
- **Word Embeddings:** FastText 300d vectors for property similarity and synset centroid computation
- **Pre-computed Indexes:** Property similarity matrix, synset centroids, IDF weights

**Storage:** Server-side SQLite database accessed via Go API, thin client makes HTTP requests

**Architectural Decision Note (2026-01-25):** 
Evaluated local SQLite + social API hybrid approach vs server-side queries. Local-first considered for offline performance, privacy, and scalability. However, rejected due to:
- 50-100MB database download size (too large for initial load)
- Complex search performance requirements on edge devices
- DevOps complexity of database updates and versioning
- Writers primarily use laptops with good internet connectivity

Server-side queries chosen for simplicity, performance consistency, and proven reliability. Future Julian can revisit if use cases change.

**Data Acquisition Tasks (Post-Design):**
- Process SUBTLEX-UK or similar frequency corpus for rarity badges
- Implement random sampling for data quality investigation

---

## Research Spikes (MVP)

Investigate data sources without committing to wire them into the UI. Compare existing databases against Gemini enrichment.

| Spike | Source | Purpose | MVP Outcome | Sprint Zero Status |
|-------|--------|---------|-------------|--------------------|
| Etymology | Etymological WordNet (2013) | Assess coverage, patchiness | Report on usability | **Not started** |
| Metonyms | ConceptNet `SymbolOf` + related edges | Assess what's actually there | Report on usability | **Not started** (ConceptNet not integrated; SyntagNet imported but metonyms not ranked) |
| Connotation | ConceptNet sentiment edges | Assess reliability | Report on usability | **Not started** |
| Gemini Enrichment | Gemini Flash extraction | Compare to DB sources | Quality comparison | **Done for properties** (2K synsets). Additional fields not yet extracted. |

---

## Gemini Enrichment (Parallel Research Path)

Extend Metaphor Forge property extraction to also capture enrichment data in a single LLM call.

**Additional fields to extract:**
- Metonyms (2-3 per word)
- Connotation (positive/neutral/negative)
- Register (formal/neutral/informal/slang)
- Usage example (1-2 sentences)

> **⚠️ Drift Check — Enrichment scope narrower than designed:** The current pipeline extracts **properties only**. The enrichment table schema has columns for connotation, register, usage_example, and model_used — but only `model_used` is populated. The `synset_metonyms` junction table exists but is empty. **The 20K enrichment run is the opportunity to add these fields to the prompt**, capturing everything in one pass as originally designed. This would populate the enrichment table fully and enable rarity/register badges in the thesaurus UI.

**Cost estimates:**
- Pilot (2k synsets, properties only): ~$1.50 actual
- Next run (~20k synsets, full enrichment): ~$15 estimated
- Full corpus (~107k synsets): ~$75-100 one-time

**Approach:** Run pilot alongside existing DB research. Compare quality. If Gemini wins, process full corpus. One-time batch enrichment, results stored permanently.

**Potential outcome:** If LLM enrichment proves reliable, create a modern open dataset filling gaps in frozen NLP databases (Etymological WordNet 2013, ConceptNet 2019)

---

## Error Handling & Edge Cases

**Word Not Found:** "Word not found" with 3-5 semantic suggestions + spelling guidance

**Empty Results:** Definition with "No synonyms/antonyms found" + related concept suggestions

**Invalid Input:** "Please enter a valid word" with search examples

**Performance:** "Searching..." indicator if debounce delay exceeded

**Loading:** Brief spinner during initial API calls, client remains lightweight

---

## Testing Strategy

**Unit Tests:**
- Search input parsing and validation
- Each rendering strategy (A, B, C) with test data
- Copy-to-clipboard functionality
- Debounce timing behavior

**Integration Tests:**
- End-to-end search flow (input → results → navigation)
- Navigation between words
- Error state handling
- Feature flag switching between strategies

**Performance Tests:**
- Search response time under load
- Database query optimization
- Memory usage with large result sets

**Data Quality Tests:**
- WordNet/OEWN data integrity validation
- VerbNet/SyntagNet relation verification
- Frequency analysis accuracy checks (when frequency corpus imported)
- Cross-reference validation between data sources
- **Random Sampling:** Build-time analysis of random word samples to investigate data quality and coverage gaps (manual investigation, not CI/CD)

---

## Implementation Notes

**Modularity Requirements:**
- Strategy pattern for result rendering algorithms
- Feature flags for A/B testing and algorithm switching
- Clean separation between data layer and presentation layer
- Testable components with dependency injection

**Performance Considerations:**
- Server-side caching for common search queries
- Efficient database indexing on Go backend
- Minimal client memory footprint (thin client architecture)

**Accessibility:**
- Full keyboard navigation support
- Screen reader compatibility for all word data
- High contrast mode support for russet colour indicators

---

## Phase 2 Features (Post-MVP)

- Recent searches (quick access to previous lookups)
- Register badges
- Connotation indicators
- Etymology display (pending research spike)
- Metonyms tab in Strategy C (pending research spike)
- Configurable results ordering (alphabetical, frequency, register)

---

## Next Steps

1. **Frequency Data:** Process SUBTLEX-UK or similar for rarity badges — **Not started** (frequencies table empty)
2. **Research Spikes:** Pull etymology, metonym, connotation sources for investigation — **Not started**
3. ~~**Gemini Pilot:** Extend property extraction to include enrichment fields~~ — **Partially done** (properties extracted, additional fields not yet)
4. ~~**Implementation Planning:** Create detailed technical roadmap~~ — **Done** (`docs/plans/2026-01-26-sprint-zero.md`)
5. ~~**TDD Setup:** Establish test framework and write failing tests~~ — **Done** (Go test suite)
6. **Core Implementation:** Build search system and results panel — **Not started** (no search endpoint, no frontend)
7. **Integration:** Connect with 3D visualisation system — **Not started**
8. **Testing:** Comprehensive test coverage and performance optimisation — **In progress** (backend tests exist, no frontend tests)

### New Next Steps (from Sprint Zero)

9. **Extend enrichment prompt** to capture connotation, register, usage_example, metonyms alongside properties
10. **Populate synset_metonyms** from SyntagNet data (pipeline step needed)
11. **Build search API endpoint** with fuzzy matching and suggestions
12. **Integrate Fluent** string handling (see `string-handling.md`)
