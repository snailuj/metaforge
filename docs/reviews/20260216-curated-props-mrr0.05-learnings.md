# Curated Forge MRR Diagnostic — 0.0525

> 2026-02-16 — Full targeted evaluation after enriching all 2,162 synsets covering 274 test pairs.

Supersedes `20260214-curated-forge-mrr-investigation.md` (MRR 0.0001, diagnosed as coverage gap).

## Setup

- Enrichment: 2,162 synsets via `claude -p --model sonnet` (100% coverage, 0 failures)
- Baseline: `lexicon_v2.sql` restored into `eval_work.db`
- Pipeline: full curated pipeline (build_vocab → snap_properties → build_antonyms)
- Eval: 271 testable pairs (3 skipped), limit=200, threshold=0.7

## Results

| Metric | Value |
|--------|-------|
| **MRR** | **0.0525** |
| Pairs with rank (target found) | 102 / 271 (38%) |
| Pairs with no rank (target missing) | 169 / 271 (62%) |

### Rank distribution (102 hits)

| Bucket | Count |
|--------|-------|
| Rank 1 (exact) | 4 |
| Top 3 | 15 |
| Top 5 | 20 |
| Top 10 | 33 |
| Top 20 | 45 |
| Rank 21+ | 57 |

### MRR by tier

| Tier | MRR | Found | Total |
|------|-----|-------|-------|
| Strong | 0.0654 | 33 | 82 |
| Medium | 0.0678 | 47 | 102 |
| Weak | 0.0224 | 22 | 87 |

### Standout successes (rank 1–2)

- **Rank 1:** `resurrection → dawn`, `breath → wind`, `torment → rack`, `wrinkle → furrow`
- **Rank 2:** `anger → fire`, `life → stage`, `youth → spring`, `truth → mirror`, `clarity → crystal`, `creativity → forge`, `revolution → eruption`, `desolation → wasteland`

These succeed because both concepts genuinely share physical/sensory descriptors (e.g., `breath → wind` shares: atmospheric, rhythmic, flowing, vital, life-sustaining — 12 properties in common).

## Miss Root Cause Analysis

### Breakdown (169 misses)

| Cause | Count | % | Description |
|-------|-------|---|-------------|
| **Zero property overlap** | 149 | 88% | Source and target synsets share NO curated properties at all |
| **Outranked / LIMIT truncation** | 20 | 12% | Target IS a candidate but pushed out by rank or SQL LIMIT |

### Root Cause 1: Properties don't bridge domains (88% of misses)

The dominant failure mode. The enrichment prompt generates sense-specific properties that describe each concept in its own domain. Abstract sources get emotion/cognition words; concrete targets get physical/material words. The metaphorical bridge properties that would connect them aren't extracted for both sides.

**Example — `hope → light` (strong tier, rank=None):**
- hope's properties: acute, aim, ambitious, anticipate, aspiring, believing, bright...
- light's properties: absorb, adored, adventurous, aerated, agile, airy, alerting...
- Properties the forge's source synset shares with light: **0**
- Bridge properties a human would identify: bright, warm, guiding, illuminating

The properties describe *what each thing IS*, not *what abstract qualities it shares with things in other domains*. This is the fundamental limitation of the current enrichment prompt.

**Contrast with successful pairs:**
- `anger → fire` (17 shared): aggressive, destructive, explosive, ignite, hot, ferocious
- `wrinkle → furrow` (17 shared): crease, crumple, fold, indent, deform
- `truth → mirror` (8 shared): accurate, aligned, authentic, faithful, precise

Successes happen when the source and target are already "more like each other" — they share concrete sensory descriptors naturally. Most metaphors work precisely because the source and target are from *different* domains, which this algorithm penalises.

### Root Cause 2: SQL LIMIT counts lemma-expanded rows (12% of misses)

The Go query `GetForgeMatchesCurated` (db.go:401) joins `lemmas` to get word forms. This JOIN expands rows — each synset produces one row per lemma. The SQL `LIMIT 200` applies to these expanded rows, then Go deduplicates by synset_id.

**Measured effective unique synsets per LIMIT 200:**

| Source word | SQL rows | Unique synsets |
|-------------|----------|---------------|
| anger | 200 | 89 |
| turmoil | 200 | 82 |
| loyalty | 200 | 90 |
| spite | 200 | 78 |
| hope | 153 | 54 |
| fear | 80 | 41 |

A target at simulation rank 32+ may be cut by the 200-row limit. This causes 20 false negatives where the target IS a candidate (has shared properties) but gets squeezed out.

### Root Cause 3: `GetSynsetIDForLemma` joins wrong table

`GetSynsetIDForLemma` (db.go:485) picks the source synset by joining `synset_properties` (the **legacy** table), not `synset_properties_curated`. For 127 of 268 source words, this picks a different synset than the one with the most curated properties.

**Examples:**

| Word | Go picks (curated props) | Best available (curated props) |
|------|-------------------------|-------------------------------|
| tyranny | synset 77868 (3) | synset 99881 (9) |
| brevity | synset 60269 (5) | synset 70442 (10) |
| voice | synset 105752 (5) | synset 17973 (10) |
| panic | synset 30175 (6) | synset 99680 (10) |

The Go-picked synsets always have *some* curated properties (never 0), but often significantly fewer than the best available. Fewer source properties → fewer possible intersections → fewer candidates found.

### Non-issue: Lemma mismatch

Initial suspicion: the Go API returns one lemma per synset (e.g., "artillery" for the weapon synset), causing misses when the eval looks for "weapon". However, the eval (`evaluate_mrr.py:167`) matches by both `synset_id` AND `word`, so this is handled correctly.

### Non-issue: Snap method distribution

Snap method proportions are identical for hit and miss sources (77% exact, 15% morphological, 8% embedding). The snap pipeline is not differentially affecting quality.

## Database Stats

| Table | Rows |
|-------|------|
| property_vocab_curated | 35,000 |
| synset_properties_curated | 20,762 |
| property_antonyms | 576 |
| synsets with curated properties | 3,314 |

Source synset curated property count: mean=8.7, median=9, min=3, max=12.

## Actionable Improvements

### Bug fixes (low effort, immediate)

1. **Fix `GetSynsetIDForLemma`** — join `synset_properties_curated` instead of `synset_properties` when curated tables exist. Ensures the forge uses the synset with the richest curated property set.

2. **Fix SQL LIMIT expansion** — either:
   - Use a subquery to select unique synset_ids first, then join lemmas outside the LIMIT, or
   - Increase LIMIT to compensate (e.g., `LIMIT ? * 3`) and truncate after dedup

3. **Dead threshold parameter** — the `threshold` query param is ignored on the curated path. Either repurpose it (min_shared filter) or stop echoing it.

### Algorithm improvements (medium effort)

4. **Multi-synset source matching** — use curated properties from ALL source synsets, not just one. This captures more senses and more bridge properties. Risk: noise from irrelevant senses.

5. **Embedding-based fuzzy overlap** — instead of requiring exact curated property matches, allow "near-miss" matches where two curated properties are embedding-similar (e.g., "bright" on source matches "luminous" on target). The `property_vocab_curated` entries already have synset embeddings that could be leveraged.

### Enrichment improvements (high effort, highest impact)

6. **Cross-domain bridge properties in the enrichment prompt** — explicitly ask "What physical/sensory qualities does this abstract concept metaphorically share with concrete things?" in addition to literal properties. This directly addresses the 88% zero-overlap failure mode.

7. **Property vocabulary expansion** — 35K curated terms may be too sparse. The snap pipeline converts raw properties into curated vocabulary entries; if the curated vocabulary doesn't contain the bridge terms, they're lost even if the LLM generated them.

## Comparison with Previous Investigation

| Metric | 2026-02-14 | 2026-02-16 |
|--------|-----------|-----------|
| MRR | 0.0001 | 0.0525 |
| Enrichment coverage | 1.8% (1,967 synsets) | 100% of test pairs (3,314 synsets) |
| Dominant failure | Coverage gap | Property domain gap |
| Eval pairs | ~1,900 (random) | 271 (targeted) |

The coverage hypothesis from the earlier investigation was correct — enriching the test pairs improved MRR by ~500×. But the remaining 62% miss rate reveals the deeper algorithmic issue: sense-specific properties don't bridge abstract→concrete domains.
