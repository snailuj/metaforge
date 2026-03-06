# P3: Discriminative Evaluation Design

**Date:** 2026-02-25
**Status:** Approved
**Branch:** feat/steal-shamelessly

## Problem

MRR against a 274-pair ground truth measures recall of known (mostly conventional) metaphors. It does not measure whether the forge *actually produces good metaphors*. Without cross-domain distance (FastText), the forge returned pure synonyms (e.g. "anger → flip", "fire → burst") — and MRR was still improving because P1 salience and P2 concreteness filtered noise. With domain distance active, the output transforms: "anger → eructation (volcano)", "life → dance", "light → kiss". We need evaluation that measures this quality.

### Failure modes the current eval misses

1. **Synonym contamination** — high-overlap same-domain results crowding out cross-domain metaphors
2. **Noise** — weak property overlaps producing meaningless pairs ("mind → Jewish New Year")
3. **Cliché bias** — optimising MRR rewards finding "anger → fire" over discovering novel apt metaphors
4. **Aptness blindness** — no signal on whether top results are *genuinely good metaphors* vs technically high-scoring noise

## Design

Three-tier evaluation, each answering a different question:

### Tier 1: MRR Regression Check (existing)

**Question:** Have we broken the system's ability to find expected results?

- Unchanged from current `evaluate_mrr.py`
- Run against 274 ground-truth pairs
- **Not an optimisation target** — purely a regression guard
- Run: every commit

### Tier 2: Structural Discrimination — "Does the mechanism work?"

**Question:** Do cross-domain candidates score higher than same-domain candidates?

**Method:**
1. Select ~50 source words with good enrichment coverage (diverse POS, domains)
2. Query `/forge/suggest?limit=100` for each
3. Classify each result by domain distance:
   - Cross-domain: `distance > 0.5`
   - Same-domain: `distance < 0.3`
   - Ambiguous (0.3–0.5): excluded from comparison
4. Compare distributions

**Output metrics:**

| Metric | Description | Target |
|--------|-------------|--------|
| `cross_domain_ratio_top10` | Fraction of top-10 results that are cross-domain | > 0.6 |
| `median_score_ratio` | Cross-domain median composite / same-domain median composite | > 1.0 |
| `synonym_contamination` | Fraction of top-10 that are WordNet synonyms of source | < 0.2 |

**Key property:** Improves when the scoring formula prefers cross-domain matches, regardless of whether those matches appear in the ground truth. No overfit risk.

- Run: every commit (free, deterministic, API-only)

### Tier 3: LLM Aptness Judge — "Are the results actually good?"

**Question:** Of the metaphors the forge produces, how many are genuinely apt?

**Method:**
1. Query forge for ~30 source words, top 10 each (300 pairs)
2. Send each (source, vehicle, shared_properties) triple to Claude
3. Rate on a 3-point scale:
   - **Apt** — recognisable or creative metaphor
   - **Weak** — conceptual link exists but forced or vague
   - **Inapt** — no meaningful metaphorical mapping
4. Calibrate prompt with ~20 MUNCH apt/inapt pairs as examples

**Output metrics:**

| Metric | Description | Target |
|--------|-------------|--------|
| `aptness_rate` | Fraction rated apt | > 0.5 in top 10 |
| `inapt_rate` | Fraction rated inapt | < 0.1 |

- Run: after tuning changes (est. ~$0.10–0.50/run)
- Non-deterministic but stable in aggregate

### How they fit together

| Tier | Purpose | Frequency | Cost |
|------|---------|-----------|------|
| MRR | Regression guard | Every commit | Free |
| Structural discrimination | Mechanism check | Every commit | Free |
| LLM aptness judge | Quality audit | After tuning | ~$0.10–0.50 |

## Implementation notes

- Tier 2 script extends existing `evaluate_mrr.py` or lives alongside it as `evaluate_discrimination.py`
- Tier 3 is a separate script (`evaluate_aptness.py`) with its own output JSON
- Source word selection for Tiers 2/3: pick words with ≥5 forge results and diverse domains
- Synonym lookup uses existing WordNet relations table in lexicon_v2.db
- MUNCH dataset (Tong et al., 2024, ACL) provides calibration examples for the LLM judge: https://github.com/xiaoyuisrain/metaphor-understanding-challenge

## Dependencies

- FastText embeddings loaded in lexicon_v2.db (lemma_embeddings table) — required for domain distance
- Go API running with embeddings active
- For Tier 3: Claude API access (Anthropic SDK)

## Key insight from data exploration

Without domain distance, the forge output is entirely synonyms — MRR was a vanity metric measuring noise-filtering, not metaphor quality. With domain distance, genuine metaphors emerge ("anger → eructation", "life → dance", "light → kiss"). The evaluation must track whether the *mechanism* (cross-domain boosting) works, separately from whether the *output* is good.
