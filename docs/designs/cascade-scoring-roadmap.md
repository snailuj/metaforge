# Cascade Scoring Roadmap

**Date:** 2026-02-23
**Context:** Discussion following the Steal Shamelessly research report (`docs/research/steal-shamelessly-report.md`) and its critique by a council of LLMs (`docs/research/steal-shamelessly-report-critique.md`).

---

## Response to Critique

The critique is sharp and the cascade-over-composite insight is genuinely valuable. But I'd push back on a few points.

### Where the critique is right

**Point 2 (Cascade filters, not Franken-scoring)** — This is the strongest practical advice. Concreteness as a hard gate (discard immediately if target more concrete than vehicle) is much better than weighting it into a composite. "Thin the herd before the expensive calculations" is exactly right and fits naturally into our existing pipeline architecture — we already filter by domain distance threshold. The general principle: binary gates early, fragile/expensive signals late, only on survivors.

**Point 3 (MRR will decrease with novelty)** — Sharpest insight in the whole critique. If we successfully generate novel apt metaphors absent from the 274-pair gold set, MRR literally punishes us for it. We can't optimise for creativity AND answer-key matching. MRR remains useful as a regression test (are we still finding the obvious ones?) but shouldn't be the primary KPI. Discriminative aptness — statistical separation from inapt controls — is a better north star.

### Where I'd push back

**Point 1 (Ortony vs LRA impedance mismatch)** — Valid in theory, irrelevant in practice right now. The research report presented these as options across a spectrum; my actual recommendation was to implement salience scoring *alone* first. LRA was Tier 2, "requires architecture evolution." We were never going to sum them in the same equation. The critique is attacking a strawman composite that nobody proposed building. That said, the architectural guidance (hierarchical subordination, switching mechanism) is sound for when we do eventually add relational signals.

**Point 4 (McRae typing as mandatory filter)** — This is where the critique goes wrong. It says "filter out the vibes and keep only the physics." But metaphor *works through* abstract properties. "Anger is a volcano" succeeds partly through physical properties (erupts, hot) but equally through abstract ones (destructive, uncontrollable, builds-pressure, releases-suddenly). Enforcing strict McRae physical taxonomy would strip out exactly the properties that make cross-domain metaphors function.

The reporting bias problem is real — LLMs do under-report obvious physical norms. But the solution isn't to discard everything that doesn't fit a physical taxonomy. It's to *supplement* the extraction prompt to explicitly demand sensory/physical properties alongside the abstract ones the LLM naturally produces. Both types carry signal; neither alone is sufficient.

---

## Cascade Architecture

The critique reinforces starting with salience scoring but refines *how*:

1. **Salience scoring (Ortony)** — still the right first move, but implement as the primary ranking signal, not added to a composite sum
2. **Concreteness** — implement as a hard gate (discard), not a score multiplier
3. **Affective alignment** — implement as a late-stage re-ranker on the top N survivors, not as part of the initial retrieval score
4. **Evaluation** — start building discriminative aptness evaluation alongside MRR from the beginning

```
Retrieve candidates (property overlap)
  → Gate: concreteness(vehicle) > concreteness(target)
    → Rank: Ortony salience score
      → Re-rank top N: affective alignment, SPV, novelty
```

Rather than: `score = w1*overlap + w2*salience + w3*concreteness + w4*affect + w5*SPV`

---

## LRA — Why delay?

LRA is accepted as *important* but not as a prerequisite for salience scoring. Here's why sequencing matters:

**They solve different problems.** Salience scoring fixes a known, measured deficiency — our IDF weighting is theoretically wrong for metaphor (treats globally rare = valuable, when metaphor needs vehicle-locally-salient = valuable). This is a scoring formula fix on existing data. LRA is a fundamentally different *retrieval* mechanism — it changes what candidates we find, not how we rank them.

**LRA requires a data structure we don't have.** Our entire pipeline extracts flat properties (`[destructive, hot, consuming]`). LRA needs relational triples (`<fire, causes, destruction>`, `<fire, produces, heat>`). That's a re-enrichment of all 20k synsets with a different prompt, a new storage schema, a new matching engine, and new evaluation. It's not an incremental change — it's a parallel retrieval path.

**It will be *easier* to implement after salience, not harder.** The cascade architecture we're building (retrieve → gate → rank → re-rank) is designed for exactly this. LRA slots in as an alternative retrieval path at the top of the cascade. The critique's own Option 1B.2 says it: "Apply LRA first to generate candidates, use Ortony salience as a post-ranking filter." If we build salience scoring and the cascade now, LRA plugs into the front of that cascade later without re-engineering anything downstream.

So: not avoiding it, just building the architecture that makes it a clean addition rather than a rewrite.

---

## MuseScorer — Why include?

The MuseScorer insight is: **don't cluster to compress, cluster to measure rarity.** Their dynamic codebook approach — K-NN retrieval against existing buckets, LLM judges whether a new idea fits or gets its own bucket — directly measures originality. We tried clustering to *improve matching* (wrong direction, killed signal). MuseScorer uses clustering to *score novelty* (right direction, preserves signal).

There are two ways this could plug in:

**As evaluation** — replace/supplement MRR with a novelty-aware aptness metric. For each generated metaphor, measure: is it a cliche (falls into a high-frequency bucket) or novel (singleton/low-frequency bucket)? Combined with the discriminative aptness approach from the critique, this gives us a KPI that actually rewards creativity.

**As a scoring signal** — a novelty bonus in the re-rank stage of the cascade. After salience ranking produces the top N, boost candidates that occupy rare buckets. This directly addresses the "don't reward cliche" problem.

The practical blocker is that MuseScorer needs a codebook of existing metaphors to measure against. We'd need to either build one from our 274-pair gold set (too small) or harvest one from a corpus. That's non-trivial data work.

---

## Prioritised Roadmap

| Priority | What | Why now |
|----------|------|---------|
| **1** | Salience scoring (Ortony) | Fixes known-wrong IDF scoring. Immediate MRR signal. |
| **2** | Concreteness gate | Hard filter, cheap, prunes bad candidates early |
| **3** | Discriminative evaluation | Must stop optimising for MRR before it distorts decisions |
| **3** | MuseScorer-style novelty | Needed to evaluate *and* score novelty; pairs with discriminative eval |
| **4** | Affective alignment | Late-stage re-ranker on top N survivors |
| **5** | LRA relational retrieval | New retrieval path; slots into front of cascade architecture |

Items 3 are co-prioritised because they solve the same problem (evaluation methodology) from complementary angles.

---

## Progress

- [x] Priority 1: Salience scoring — v2 enrichment schema, pipeline, Go scoring (Phases 1-7 complete, Phase 8 in progress)
- [ ] Priority 2: Concreteness gate
- [ ] Priority 3: Discriminative evaluation
- [ ] Priority 3: MuseScorer-style novelty
- [ ] Priority 4: Affective alignment
- [ ] Priority 5: LRA relational retrieval
