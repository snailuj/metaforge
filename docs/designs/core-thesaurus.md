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
- Separate tabs for Synonyms, Antonyms, Metonyms
- Internal sense-grouping when expanded
- Clean visual separation

### Strategy B - Flat Similarity List
- Single ranked list by semantic similarity
- Fastest to scan but mixes meanings
- Simple implementation

**Word Entry Display:**
- Word itself
- Rarity/register badges (TBD for MVP)
- Part of speech
- Connotation indicators (subtle colour coding)

**Progressive Disclosure:** Essential info by default, expandable sections for etymology and word family details

---

## Interaction Model

**Database Words** (russet colour + slight underline):
- **Left-click:** Navigate to word (updates 3D visualization)
- **Right-click:** Copy word to clipboard

**UI Elements** (tabs, buttons, etc.):
- **Left-click:** Standard UI interactions
- **Right-click:** No special behavior

---

## Word Information System

**Essential Layer (always visible):**
- Definition
- Part of speech with inflections
- 1-2 usage examples
- Connotation indicators (positive/neutral/negative colour coding)

**Expandable Sections:**
- **Etymology:** Word origin and root connections (TBD for MVP)
- **Word Family:** Related words sharing etymological roots
- **Usage Context:** Register and rarity details with corpus frequency
- **Related Forms:** Inflections, derivatives, compounds

**Visual Design:** Clean typography with word prominently displayed, russet colour/underline for database words throughout

---

## Data Sources & Structure

**Primary Sources:**
- **WordNet:** Definitions, synonyms, antonyms, hypernyms, hyponyms, part of speech, usage examples
- **ConceptNet:** Broader relations (HasProperty, UsedFor, PartOf, metonyms)
- **Corpus Frequency:** Custom analysis for rarity classification (Common/Uncommon/Rare/Archaic)
- **Etymology Database:** External integration (TBD for MVP - research needed)

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
- Research and select etymology database source
- Choose and process corpus for frequency analysis
- Implement random sampling for data quality investigation

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

## Next Steps

1. **Data Acquisition:** Research etymology database and corpus sources
2. **Implementation Planning:** Create detailed technical roadmap
3. **TDD Setup:** Establish test framework and write failing tests
4. **Core Implementation:** Build search system and results panel
5. **Integration:** Connect with 3D visualization system
6. **Testing:** Comprehensive test coverage and performance optimization