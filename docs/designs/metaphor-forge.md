# Metaforge Brainstorm: Metaphor Forge Design

**Date:** 2026-01-25
**Status:** Backend implemented (Sprint Zero) — API serving suggestions, frontend not started

---

## ⚠️ DEVELOPMENT STANDARDS (applies to all implementation) ⚠️

- **TDD Red/Green:** Failing test first, then code, then refactor
- **Frequent commits:** Commit after each green test
- **CI/CD:** Automated test runs on all commits
- **Canary releases:** Deploy to subset first, monitor, then full rollout

---

## Context

The Metaphor Forge is Sprint Zero - we're building it first to prove out the data pipeline before tackling 3D visualization. It's also the key differentiator for Metaforge.

**The core challenge:** Given a source word like "grief", find structurally analogous but semantically distant words like "anchor" - because both "hold something in place".

---

## Decided: Property Extraction via LLM

### Approach

Use Gemini Flash API to pre-compute abstract/structural properties for word senses during the data pipeline build. Store properties in SQLite for fast runtime lookup.

### Why This Approach

- ConceptNet alone has spotty coverage of abstract properties
- LLM extracts properties humans would recognise
- One-time build cost (~$1.50 for 2k synsets via Gemini 2.5 Flash), no runtime LLM dependency
- Properties are inspectable/editable if results are odd

### Pilot Scope

- 2,000 synsets for initial quality evaluation (stratified: 40% nouns, 40% verbs, 20% adjectives)
- Batch 20 synsets per API call (configurable via `--batch-size`)
- JSON array output (single object with synsets, property frequency, stats)

> **Sprint Zero Decision:** Replaced hand-curated seed list with algorithmic stratified sampling by POS. More systematic and reproducible than manual curation. Next run targets ~20K synsets prioritised by lemma reachability (synsets reachable by 3+ lemmas).

---

## Decided: Prompt Design

### Final Prompt

```
You are extracting abstract structural properties from word senses to enable metaphor generation.

For each word sense, identify 5-10 properties that describe what the thing DOES, how it BEHAVES, or what ROLE it plays.

Focus on properties that could plausibly apply to things in OTHER domains. Avoid:
- Physical-only attributes (color, size, material)
- Domain-specific jargon
- Category labels (tool, animal, emotion)

Input:
anchor.n.01 | a mechanical device that prevents a vessel from moving
river.n.01 | a large natural stream of water
grief.n.01 | intense sorrow caused by loss
illuminate.v.01 | make lighter or brighter
time.n.01 | the continuum of experience in which events pass
stubborn.a.01 | tenaciously unwilling to yield
whisper.v.01 | speak softly, without vibration of the vocal cords
bridge.n.01 | a structure that allows passage over an obstacle

Output:
{"id": "anchor.n.01", "properties": ["holds_in_place", "prevents_drift", "provides_stability", "heavy", "deployed_deliberately", "connects_to_ground"]}
{"id": "river.n.01", "properties": ["flows", "carries_things", "has_source_and_destination", "shaped_by_terrain", "can_overflow", "erodes_over_time", "follows_path_of_least_resistance"]}
{"id": "grief.n.01", "properties": ["heavy", "comes_in_waves", "holds_in_place", "isolating", "gradually_subsides", "triggered_unexpectedly", "requires_processing"]}
{"id": "illuminate.v.01", "properties": ["reveals_hidden_things", "dispels_darkness", "enables_seeing", "can_be_harsh_or_soft", "draws_attention", "requires_source"]}
{"id": "time.n.01", "properties": ["flows_forward", "cannot_be_reversed", "heals", "erodes", "runs_out", "measured_but_subjective", "precious"]}
{"id": "stubborn.a.01", "properties": ["resists_change", "holds_position", "requires_force_to_move", "can_be_strength_or_weakness", "persists"]}
{"id": "whisper.v.01", "properties": ["intimate", "secretive", "requires_closeness", "easily_missed", "suggests_importance", "excludes_others"]}
{"id": "bridge.n.01", "properties": ["connects_separated_things", "enables_crossing", "spans_gap", "requires_support_on_both_ends", "can_be_burned"]}

---

Input:
{batch of synset_id | definition pairs}

Output:
```

### Key Design Decisions

- **Sense disambiguation:** Use WordNet synset definitions to disambiguate polysemous words (bank the landform vs bank the institution)
- **Minimal response:** Only return `id` and `properties` - we rehydrate other fields from local data
- **JSON array format:** Single response with all results (changed from JSONL for simpler parsing)
- **Diverse few-shots:** Examples cover nouns, verbs, adjectives; concrete and abstract; multiple domains

> **⚠️ Drift Check — Prompt Focus Shift:** The design prompt above emphasises **abstract structural properties** — what things DO, how they BEHAVE, what ROLE they play (e.g. "holds_in_place", "prevents_drift", "connects_separated_things"). The implemented prompt (`spike_property_vocab.py`) emphasises **sensory and behavioural properties** — physical qualities, texture, weight, temperature, luminosity (e.g. "warm", "flickering", "luminous", "fragile").
>
> These produce different kinds of metaphors. Structural properties enable the design's "grief ↔ anchor" insight (both "hold something in place"). Sensory properties produce experiential connections. **The next enrichment run (20K synsets) is the opportunity to decide: should the prompt return to the original structural focus, blend both, or stay sensory?** See `spike_property_vocab.py:BATCH_PROMPT` for the current prompt.

---

## Decided: Matching Algorithm

### Two-Track Hybrid with Visual Tiers

We calculate matches across all candidates, categorize into tiers, and display all with visual quality indicators. Users see the full spectrum and choose what's useful.

### Algorithm

```
1. Single mega-query (GetForgeMatches): find candidates via property_similarity
   matrix (IDF-weighted), fetch synset details + pre-computed centroids in one CTE
2. For each candidate, compute cosine distance from pre-computed synset centroids
3. Count exact property overlap (shared property text matches)
4. Assign tier using distance + exact overlap:
   - Legendary: distance > 0.6 && overlap >= 4 (strong overlap)
   - Interesting: distance > 0.6 && overlap < 2 (wild cards)
   - Strong: distance > 0.6 && overlap >= 2 (moderate overlap)
   - Obvious: distance <= 0.6 && overlap >= 2
   - Unlikely: distance <= 0.6 && overlap < 2
5. Sort by tier (Legendary → Interesting → Strong → Obvious → Unlikely)
6. Within tier, sort by overlap_count (descending), then distance (descending)
7. Return all with tier labels
```

> **Sprint Zero Implementation Note:** The original design described exact property matching. The implementation adds two layers of sophistication:
> - **Fuzzy candidate discovery:** Uses a pre-computed property_similarity matrix (cosine similarity on FastText 300d embeddings, threshold ≥ 0.5) so that semantically similar properties (not just identical strings) surface candidates. IDF weighting ensures distinctive properties count more.
> - **Pre-computed synset centroids:** Average of property embeddings stored in `synset_centroids` table, eliminating N+1 queries. Cosine distance computed in-memory from centroids.
> - **Tier classification still uses exact overlap** — only identical property text counts toward tier thresholds. This is deliberate: fuzzy matching broadens the candidate pool, but tier quality is based on precise structural overlap.

### Display Order and Visual Treatment

| Tier | Position | Criteria | Color (parameterized) |
|------|----------|----------|----------------------|
| **Legendary** | 1st | High distance + strong overlap | Golden + glow |
| **Interesting** | 2nd | High distance + weak overlap (rare wild cards) | Green + glow |
| **Strong** | 3rd | High distance + meets threshold | Golden yellow |
| **Obvious** | 4th | Low distance + good overlap | Russet |
| **Unlikely** | 5th | Low distance + weak overlap | Slate grey |

**Accessibility:** Each tier has a numeric rank announced for screen readers.

**Note:** This 5-tier system supersedes the PRD's original 3-tier (Common/Rare/Legendary). Update PRD accordingly.

### Thresholds (configurable — see `forge.go`)

| Constant | Value | Meaning |
|----------|-------|---------|
| `HighDistanceThreshold` | 0.6 | Cosine distance above which concepts are "far" |
| `MinOverlap` | 2 | Minimum shared properties for "moderate" overlap |
| `StrongOverlap` | 4 | Shared properties for "strong" / legendary overlap |

API defaults: `threshold=0.7` (property similarity), `limit=50` (max results)

---

## Decided: Bridge Explanations

> **Sprint Zero Status:** Not yet implemented. The API returns `shared_properties` in the response, providing the raw data for hints, but there is no hint reveal mechanism or progressive disclosure. This is a frontend concern.

### No Automatic Explanations - Progressive Hints Instead

The "aha" moment comes from the user connecting the dots themselves. We provide hints, not answers.

### Hint System

1. **Initial state:** Just show the metaphor pair - "grief ↔ anchor"
2. **First hint (free):** "These share 3 properties"
3. **Progressive hints:** Reveal one property at a time if user asks
   - Hint 2: "Both hold something in place"
   - Hint 3: "Both are heavy"
   - etc.
4. **User's job:** Construct the full metaphorical sentence themselves

### Future (Phase 4+ with accounts)

- **Paid feature:** LLM elaboration for users who want richer explanations (recoups API cost)
- **Social:** User-generated interpretations visible to friends/class
- **Global stat:** "47 others forged this" count (deferred to Phase 4)

---

## Decided: Failed Forge Handling

### No "Failed" State

With the 5-tier visual system, we always return results. Even weak matches (Obvious, Unlikely) are shown but visually demoted.

**Only hard filter:** Words with zero shared properties (true noise).

Users scroll through the spectrum and decide what's useful. The slate grey "Unlikely" matches are there if someone wants to explore them.

**Future (Grimoire):** Option to hide Unlikely tier matches.

---

## Decided: Grimoire Data Model

> **Sprint Zero Status:** Not yet implemented. Entirely a frontend concern (IndexedDB). Backend provides all required data in the `/forge/suggest` response.

### MVP Schema

```typescript
interface ForgedMetaphor {
  id: string;                    // UUID
  source_word: string;           // "grief"
  catalyst_word: string;         // "anchor"
  tier: Tier;                    // Legendary | Interesting | Strong | Obvious | Unlikely
  shared_properties: string[];   // ["holds_in_place", "heavy"]
  user_interpretation?: string;  // User's written explanation (optional)
  created_at: Date;
}
```

### Storage

IndexedDB (local, no account needed for MVP).

### UX Flow

1. User forges metaphor, sees result with tier glow
2. CTA text box: "What does this connection mean to you?"
3. User types interpretation (or leaves blank)
4. Clicks "Save to Grimoire"
5. Animation: card whisks away to Grimoire icon in header
6. Stored locally

### Grimoire View

- List of saved metaphors
- Each card shows: source ↔ catalyst, tier glow, user's interpretation
- Future: filterable by tier (e.g., hide Unlikely)

---

## Next Steps

1. ~~**Update PRD:** Replace 3-tier quality system with 5-tier~~ — **Not done, still needed**
2. ~~**Curate seed list:** Pick 500 metaphor-worthy words for the pilot~~ — **Done** (replaced with stratified sampling)
3. ~~**Set up data pipeline:** Python scripts to extract WordNet synsets~~ — **Done** (`run_pipeline.sh`)
4. ~~**Run pilot extraction:** Process 1k synsets through Gemini Flash~~ — **Done** (2K synsets, `property_pilot_2k.json`)
5. ~~**Evaluate quality:** Review properties, identify gaps or biases~~ — **Done** (IDF, similarity matrix, centroids computed)
6. ~~**Implement matching algorithm:** TDD - test each tier classification~~ — **Done** (`forge.go`, `forge_test.go`)
7. ~~**Build Forge API endpoint:** Go backend serving suggestions~~ — **Done** (`GET /forge/suggest`)
8. **Build Forge UI:** Results with tier colours, hint system, Grimoire save — **Not started**

### New Next Steps (from Sprint Zero)

9. **Resolve prompt drift:** Decide structural vs sensory property focus before 20K enrichment run
10. **Scale enrichment:** Run ~20K synsets (prioritised by lemma reachability, ~$15)
11. **Integrate Fluent:** String handling for all UI chrome (see `string-handling.md`)
12. **Build frontend:** Forge UI with tier visuals, hint system, Grimoire

---

## Related Documents

- `Metaforge-PRD.md` - Full product requirements (needs 5-tier update)
- `IMPLEMENTATION-PLAN.md` - Technical implementation phases
- `MetaforgeConcept.png` - Visual concept art (antique + cosmic themes)
