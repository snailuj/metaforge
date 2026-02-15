# Curated Forge MRR Investigation

> 2026-02-14 — Post-deployment MRR evaluation returned catastrophically bad results.

## Observation

MRR: **0.0001** — only 1 match out of 1,900 evaluation pairs.

## Hypothesis 1: Coverage (likely dominant factor)

The snap audit showed **1,967 synsets** with curated properties out of **107,519 total synsets** — 1.8% coverage.

For the forge to return a match:
1. The **source** must be enriched (~1.8% chance)
2. The **target** must also be enriched (~1.8% chance)
3. They must share at least one curated property

If the MRR evaluation has ground-truth pairs drawn from the full 107K, most expected targets simply don't exist in the enriched set. An MRR of 0.0001 (1/1900) is roughly what you'd expect from random chance at that coverage level.

**Action:** Re-run MRR after 20K enrichment completes. Coverage should jump from 1.8% to ~18.6%, which fundamentally changes the addressable match pool.

## Hypothesis 2: No minimum overlap filter

The curated query (`GetForgeMatchesCurated`) returns everything with ≥1 shared property. Single-property matches flood results and push genuine matches down the ranking. The legacy path had a cosine distance threshold that acted as a quality gate; the curated path has nothing equivalent.

**Action:** Consider adding a `min_shared` parameter (default 2?) to filter out noise. Or use the threshold parameter (currently dead on curated path) for this purpose.

## Hypothesis 3: Sense collapse

Source word resolves to a single synset, which may not be the intended sense. See `docs/designs/sense-disambiguation.md`.

## Hypothesis 4: Dead threshold parameter

The `threshold` query parameter is parsed but completely ignored on the curated code path. It's only used in the legacy cosine-distance path. The response JSON still echoes it back, which is misleading.

**Action:** Either repurpose threshold for minimum overlap count on curated path, or remove it from the curated response.

## Next Steps

1. Wait for 20K enrichment and re-evaluate — coverage is likely the dominant factor
2. Add minimum overlap filtering to curated query
3. Stop echoing threshold in curated response (or repurpose it)
4. Investigate whether evaluation ground-truth pairs are within the enriched set
