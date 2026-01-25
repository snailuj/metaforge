# Core Thesaurus Design

**Status:** Design Complete  
**Priority:** High (Foundation for all other features)  
**Dependencies:** String Handling (cross-cutting)

---

## Overview

The Core Thesaurus provides the foundational search and word lookup functionality that all other Metaforge features build upon. It follows the "Utility First" principle with fast, accurate word discovery while maintaining the modular architecture needed for future enhancements.

---

## Search System

**Input:** Prominent search bar with keyboard shortcut `/` for quick access

**Behavior:** Live Results Panel updates as user types (simple debounce for performance). 3D visualization only updates on explicit word click to prevent jarring camera movements.

**Algorithm:** "Best Match + Suggestions" approach
- Valid inputs: Show closest semantic match
- Typos/unknown words: Display "Word not found" with 3-5 helpful suggestions
- Future enhancement: Hybrid semantic + spelling matching (post-MVP)

**Performance:** Simple debounce (tunable delay) to maintain responsiveness

---

## Results Panel Architecture

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
- **WordNet:** Definitions, synonyms, antonyms, hypernyms, hyponyms, part of speech, usage examples
- **ConceptNet:** Broader relations (HasProperty, UsedFor, PartOf) — metonyms via SymbolOf pending research
- **Frequency Corpus:** SUBTLEX-UK or similar for rarity classification (Common/Uncommon/Rare/Archaic) — MVP
- **Etymology Database:** Etymological WordNet (2013) — research spike only, not wired into MVP

**Derived Data:**
- **Word Embeddings:** Semantic similarity for search and matching
- **Pre-computed Indexes:** Fast debounced search results

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

| Spike | Source | Purpose | MVP Outcome |
|-------|--------|---------|-------------|
| Etymology | Etymological WordNet (2013) | Assess coverage, patchiness | Report on usability |
| Metonyms | ConceptNet `SymbolOf` + related edges | Assess what's actually there | Report on usability |
| Connotation | ConceptNet sentiment edges | Assess reliability | Report on usability |
| Gemini Enrichment | Gemini Flash extraction | Compare to DB sources | Quality comparison |

---

## Gemini Enrichment (Parallel Research Path)

Extend Metaphor Forge property extraction to also capture enrichment data in a single LLM call.

**Additional fields to extract:**
- Metonyms (2-3 per word)
- Connotation (positive/neutral/negative)
- Register (formal/neutral/informal/slang)
- Usage example (1-2 sentences)

**Cost estimates:**
- Pilot (1k synsets): ~$5
- Full corpus (~120k synsets): ~$50-75 one-time

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
- WordNet data integrity validation
- ConceptNet relation verification
- Frequency analysis accuracy checks
- Cross-reference validation between data sources
- **Random Sampling:** Build-time analysis of random word samples from WordNet/ConceptNet to investigate data quality and coverage gaps (manual investigation, not CI/CD)

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

1. **Frequency Data:** Process SUBTLEX-UK or similar for rarity badges
2. **Research Spikes:** Pull etymology, metonym, connotation sources for investigation
3. **Gemini Pilot:** Extend property extraction to include enrichment fields
4. **Implementation Planning:** Create detailed technical roadmap
5. **TDD Setup:** Establish test framework and write failing tests
6. **Core Implementation:** Build search system and results panel
7. **Integration:** Connect with 3D visualisation system
8. **Testing:** Comprehensive test coverage and performance optimisation