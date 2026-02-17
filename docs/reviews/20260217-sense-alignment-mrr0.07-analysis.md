# Per-Candidate Sense Alignment — MRR 0.0733

> 2026-02-17 — Follow-up to `20260216-curated-props-mrr0.05-learnings.md` (MRR 0.0525).

## What Changed

Three structural changes to the forge algorithm, all in this commit:

1. **Per-candidate sense alignment** (`GetForgeMatchesCuratedByLemma`): For polysemous words, each target is now matched against whichever source sense shares the most properties with it, via `ROW_NUMBER() OVER (PARTITION BY target_id ORDER BY shared_count DESC)`. Previously `GetSynsetIDForLemma` picked a single source synset up front, losing all other senses.

2. **Curated-only handler**: Stripped the legacy cosine-distance path entirely. No more `GetSynsetIDForLemma` → `GetSynset` → `GetForgeMatches` cascade. The handler calls `GetForgeMatchesCuratedByLemma(word, limit)` directly.

3. **Response carries per-match source context**: Each suggestion includes `source_synset_id`, `source_definition`, `source_pos` — the specific sense that aligned to that target. No more single source synset in the response header.

## Results

| Metric | v1 (0.0525) | v2 (0.0733) | Delta |
|--------|-------------|-------------|-------|
| **MRR** | **0.0525** | **0.0733** | **+39.6%** |
| Hit rate (target found) | 102 / 271 (38%) | 121 / 271 (45%) | +19 pairs |
| Miss rate | 169 / 271 (62%) | 150 / 271 (55%) | -19 pairs |

### Rank distribution

| Bucket | v1 | v2 | Delta |
|--------|----|----|-------|
| Rank 1 (exact) | 4 | 8 | +4 |
| Top 3 | 15 | 19 | +4 |
| Top 5 | 20 | 29 | +9 |
| Top 10 | 33 | 43 | +10 |
| Top 20 | 45 | 61 | +16 |
| Rank 21+ | 57 | 60 | +3 |

The biggest gain is in the top-10 and top-20 buckets — sense alignment is pulling targets up the rankings.

### MRR by tier

| Tier | v1 MRR | v2 MRR | Delta | v1 Found | v2 Found |
|------|--------|--------|-------|----------|----------|
| Strong | 0.0654 | 0.0919 | +41% | 33/82 | 48/82 |
| Medium | 0.0678 | 0.0835 | +23% | 47/102 | 47/102 |
| Weak | 0.0224 | 0.0437 | +95% | 22/87 | 26/87 |

Strong tier saw the biggest absolute improvement (+15 new hits). Weak tier nearly doubled its MRR — sense alignment is finding previously invisible connections.

### Standout successes (rank 1-2)

- **Rank 1:** `power → muscle`, `breath → wind`, `chaos → storm`, `shame → stain`, `urgency → drumbeat`, `resurrection → dawn`, `abstraction → cloud`, `pulse → drum`
- **Rank 2:** `fear → shadow`, `death → sleep`, `truth → mirror`, `torment → rack`, `clarity → crystal`, `creativity → forge`, `sweat → dew`

New rank-1 hits `power → muscle`, `shame → stain`, `abstraction → cloud`, and `pulse → drum` were all complete misses in v1.

## Pair-Level Changes

### Net movement: +37 new hits, -18 lost hits = +19 net

**37 new hits** (previously missed, now found):
- High quality (rank ≤ 10): `power → muscle` (1), `shame → stain` (1), `abstraction → cloud` (1), `fear → shadow` (2), `sweat → dew` (2), `nerve → wire` (3), `rhetoric → weapon` (4), `decline → sunset` (5), `joint → hinge` (8)
- Mid-range (rank 11-30): `numbness → ice` (13), `vulnerability → glass` (14), `spine → pillar` (16), `idea → seed` (19), `argument → war` (21), `flesh → clay` (23), `epiphany → thunderbolt` (29)
- Long tail (rank 31+): `hope → light` (40), `trust → bridge` (53), `theory → building` (63), `war → inferno` (83)

**Notably, `hope → light` was the signature failure** from the previous writeup (zero property overlap between the single chosen source synset and "light"). Sense alignment found it at rank 40 — not great, but no longer invisible.

### 18 lost hits

All were deep-ranked in v1 (rank 10-83):
- Best lost: `peace → harbour` (was rank 10)
- Most were rank 45+ in v1: `barrenness → tundra` (49), `sovereignty → fortress` (53), `improvisation → trapeze` (57), `rapture → flood` (60), `mortality → candle` (80)

These losses are a tradeoff of the new SQL structure. Per-candidate sense alignment changes which source synset each target is scored against, which reshuffles the entire ranking. Some marginal matches that squeaked in under the old single-synset approach now lose to better-aligned competitors.

### Biggest rank improvements

| Pair | v1 rank | v2 rank | Delta |
|------|---------|---------|-------|
| death → sleep | 83 | 2 | +81 |
| rage → storm | 62 | 4 | +58 |
| oppression → yoke | 68 | 21 | +47 |
| jealousy → poison | 46 | 7 | +39 |
| melody → stream | 63 | 24 | +39 |
| chaos → storm | 39 | 1 | +38 |
| gloom → overcast | 30 | 5 | +25 |
| urgency → drumbeat | 24 | 1 | +23 |
| hair → silk | 33 | 10 | +23 |

`death → sleep` jumping from rank 83 to rank 2 is the clearest vindication of sense alignment — the v1 single-synset approach likely picked a death sense with few properties overlapping "sleep", while v2 found the sense that shares them.

### Biggest regressions

| Pair | v1 rank | v2 rank | Delta |
|------|---------|---------|-------|
| infancy → bud | 28 | 83 | -55 |
| eye → window | 13 | 62 | -49 |
| momentum → avalanche | 5 | 43 | -38 |
| anxiety → knot | 28 | 63 | -35 |
| purity → snow | 12 | 45 | -33 |
| frustration → wall | 4 | 31 | -27 |
| transience → dew | 6 | 32 | -26 |

These regressions likely happen when sense alignment picks a "better-matched" source sense that has more overlap with *other* targets, pushing the intended target down. For example, `frustration → wall` may have benefited from a specific frustration sense in v1 that v2's best-sense-per-target logic doesn't select for "wall".

## Root Cause Analysis (150 misses)

The dominant failure mode from v1 persists: **properties don't bridge domains**. The enrichment prompt generates sense-specific properties that describe each concept in its own domain. Abstract sources get emotion/cognition words; concrete targets get physical/material words.

Sense alignment helps at the margins — it recovered 37 previously invisible pairs by trying all source senses — but it can't create bridge properties that don't exist in the vocabulary.

### What sense alignment fixed (from the v1 actionable items)

| v1 Item | Status |
|---------|--------|
| **#1 Fix `GetSynsetIDForLemma`** | Fixed — eliminated entirely. Sense alignment replaces single-synset selection. |
| **#2 Fix SQL LIMIT expansion** | Partially addressed — `GetForgeMatchesCuratedByLemma` deduplicates within the query structure, but the fundamental lemma-expansion issue persists in the final JOIN. |
| **#3 Dead threshold parameter** | Fixed — removed from handler, API, and eval script. |
| **#4 Multi-synset source matching** | Fixed — this IS sense alignment. Each target is scored against all source senses. |
| **#5 Embedding-based fuzzy overlap** | Not addressed — still exact curated property matches only. |
| **#6 Cross-domain bridge properties** | Not addressed — enrichment prompt unchanged. |
| **#7 Property vocabulary expansion** | Not addressed — 35K curated terms unchanged. |

### Remaining actionable improvements

1. **Fix the LIMIT regression** — The 18 lost hits and some regressions may be caused by the lemma JOIN expanding rows before the SQL LIMIT. A subquery selecting distinct target synset_ids before joining lemmas would fix this.

2. **Fuzzy property matching** — The 55% miss rate is dominated by zero-overlap pairs. Allowing embedding-similar property matches (e.g., "bright" on source matches "luminous" on target) would address this without changing the enrichment.

3. **Cross-domain enrichment prompt** — The highest-impact change remains asking the LLM "What physical/sensory qualities does this abstract concept metaphorically share with concrete things?" in addition to literal properties.

## Database Stats

| Metric | Value |
|--------|-------|
| Curated vocabulary | 35,000 |
| Synset-property links (curated) | ~20,762 |
| Hapax count | 1,784 (5.1%) |
| Avg properties per synset | 6.3 |

## Comparison Across All Iterations

| Metric | 2026-02-14 | 2026-02-16 | 2026-02-17 |
|--------|-----------|-----------|-----------|
| MRR | 0.0001 | 0.0525 | 0.0733 |
| Dominant fix | Coverage gap | Full enrichment | Sense alignment |
| Hit rate | ~0% | 38% | 45% |
| Rank-1 hits | 0 | 4 | 8 |
| Top-10 hits | ~0 | 33 | 43 |
