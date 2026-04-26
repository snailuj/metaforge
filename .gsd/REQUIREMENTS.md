# Requirements

This file is the explicit capability and coverage contract for the project.

## Active

### R001 — Core thesaurus lookup — search returns definitions, synonyms, antonyms, register, connotations, etymology, rarity badges, collocations, and usage examples in under 3 seconds
- Class: functional
- Status: active
- Description: Core thesaurus lookup — search returns definitions, synonyms, antonyms, register, connotations, etymology, rarity badges, collocations, and usage examples in under 3 seconds
- Why it matters: The primary value prop — a fast, functional thesaurus that works flawlessly. If scope shrinks, this survives.
- Source: Metaforge-PRD-2.md §Design Principles #1
- Validation: Search for common words returns complete results in < 3s on staging

### R002 — 3D force-directed graph visualisation — words rendered as nodes connected by edges, with springy physics. Click a node to recentre the graph around it.
- Class: functional
- Status: active
- Description: 3D force-directed graph visualisation — words rendered as nodes connected by edges, with springy physics. Click a node to recentre the graph around it.
- Why it matters: Core interaction model inherited from Visual Thesaurus — the feeling of travelling between semantic clusters is the thing to preserve.
- Source: Metaforge-PRD-2.md §Visual Metaphors
- Validation: Graph renders with physics, click navigation works, clusters form by semantic proximity

### R003 — Metaphor Forge — experimental creative tool surfacing unexpected semantic bridges between words via shared property dimensions
- Class: functional
- Status: active
- Description: Metaphor Forge — experimental creative tool surfacing unexpected semantic bridges between words via shared property dimensions
- Why it matters: The differentiator from a plain thesaurus — part educational, part creative writing tool. Makes Metaforge worth building beyond a Visual Thesaurus clone.
- Source: Metaforge-PRD-2.md §What's In the Box
- Validation: Forge suggest endpoint returns meaningful cross-domain metaphor suggestions with shared property explanations

### R004 — HUD results panel — always-visible search results panel that functions as a complete thesaurus independently of the 3D graph
- Class: functional
- Status: active
- Description: HUD results panel — always-visible search results panel that functions as a complete thesaurus independently of the 3D graph
- Why it matters: Progressive depth: if the graph breaks, the HUD still works. Utility first, wonder second.
- Source: Metaforge-PRD-2.md §Design Principles #2
- Validation: HUD displays full thesaurus results without requiring graph interaction

### R005 — Search latency under 100ms for autocomplete, under 3 seconds for full lookup including graph render
- Class: non-functional
- Status: active
- Description: Search latency under 100ms for autocomplete, under 3 seconds for full lookup including graph render
- Why it matters: Lookup mode users need a word NOW — speed is the primary design priority for this mode.
- Source: Metaforge-PRD-2.md §What's In the Box
- Validation: Measure P95 latency for autocomplete and full lookup on staging

### R006 — Local-first with IndexedDB — user preferences and history stored locally, no accounts or server-side user data in MVP
- Class: non-functional
- Status: active
- Description: Local-first with IndexedDB — user preferences and history stored locally, no accounts or server-side user data in MVP
- Why it matters: Self-hostable, privacy-respecting, no infrastructure cost for user data. Aligns with non-profit model.
- Source: Metaforge-PRD-2.md §Open Source and Non-Profit
- Validation: App works offline for cached words, preferences persist across sessions via IndexedDB

## Traceability

| ID | Class | Status | Primary owner | Supporting | Proof |
|---|---|---|---|---|---|
| R001 | functional | active | none | none | Search for common words returns complete results in < 3s on staging |
| R002 | functional | active | none | none | Graph renders with physics, click navigation works, clusters form by semantic proximity |
| R003 | functional | active | none | none | Forge suggest endpoint returns meaningful cross-domain metaphor suggestions with shared property explanations |
| R004 | functional | active | none | none | HUD displays full thesaurus results without requiring graph interaction |
| R005 | non-functional | active | none | none | Measure P95 latency for autocomplete and full lookup on staging |
| R006 | non-functional | active | none | none | App works offline for cached words, preferences persist across sessions via IndexedDB |

## Coverage Summary

- Active requirements: 6
- Mapped to slices: 6
- Validated: 0
- Unmapped active requirements: 0
