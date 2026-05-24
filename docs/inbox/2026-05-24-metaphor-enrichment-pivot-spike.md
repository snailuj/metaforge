# Metaphor Enrichment Pivot — Spike

**Status:** Exploratory spike. Not a milestone yet. Outcome of this spike decides whether to promote to M07 (or wherever it slots).

**Captured:** 2026-05-24

**Context:** Brainstorming session 2026-05-24 (post-M05 merge). Triggered by operator's "traitorous feeling" — should we have been enriching synsets with *metaphors* (with structured rationale) rather than *properties*? Discussion conclusion: property enrichment isn't wasted (it stays as the explainability substrate and the cascade engine for arbitrary-pair scoring), but a parallel LLM-generated metaphor graph could solve the cohort-and-recalibration problems M05 surfaced AND deliver authoritative fast-path edges for known pairs.

## The pivot, in one sentence

Generate, per synset, a small JSON graph of metaphor vehicles + structured shared-feature rationale, using an LLM. Use the existing snap infrastructure to curate. Keep the cascade scorer as the cold-start engine; the LLM graph becomes the authoritative fast-path layer.

## Why this preserves rather than betrays existing work

- The bridge thesis (anger → [heat, spreading, destruction] → fire) is *enhanced*, not lost — shared-feature concepts become first-class bridge nodes in the data.
- The property taxonomy (sensorimotor, behaviour, functional, effect, emotional, social) becomes the dimension vocabulary inside each rationale entry — direct reuse, no translation.
- The cascade scorer keeps its job: novel topics, user-typed compounds, anything the LLM didn't enumerate. Two layers, one UI.
- M05's γ bonus reads `len({f.dimension for f in features})` directly — no prose parsing.

## Open questions resolved in the brainstorm

| Question | Resolution |
|----------|------------|
| Bidirectional or asymmetric edges? | Asymmetric. Canonical lemma-sense storage means dedup is automatic. |
| Use OEWN canonical IDs in LLM output? | No. LLM emits *words*. Snap maps word → synset_id via `lemmas` join (same as property snap). Verified 2026-05-24: our `synsets.synset_id` is `TEXT PRIMARY KEY` holding numeric-string IDs like `102023`, NOT OEWN. |
| Rationale: prose or structured? | Structured. Each entry pairs `(dimension, concept)`. The concept *is* the bridge waypoint. |
| Per-anchor metaphor count? | 3–7. "Return fewer if you can't find strong ones" — permission to under-deliver rather than confabulate. |
| Replace or complement cascade? | Complement. Cascade handles arbitrary pairs; LLM graph handles known pairs with rationale fast-path. |

## Open questions to resolve in the spike

1. **Haiku vs Sonnet.** Can Haiku 4.5 hold the JSON schema *and* maintain quality? Cost difference is roughly an order of magnitude — pivots-worth depends on this answer.
2. **Concept normalisation.** LLM will emit "heat", "hot", "heated" interchangeably across runs. Light stemming + a controlled vocab pass post-snap? Or accept the noise on v1?
3. **Polysemy at snap.** Word "fire" maps to multiple synset_ids (noun: combustion / firearm / dismissal). Same sense-disambiguation problem property snap already solves — confirm the existing snap algorithm handles this without modification.
4. **Cost ceiling.** ~35k synsets × N output tokens × per-call cost. Need a real number before commit.

## Prompt (current draft)

```
You generate metaphor mappings for a thesaurus. For each topic word,
return 3-7 concrete vehicles that map onto it via cross-domain
structural similarity.

QUALITY CRITERIA (every entry must satisfy):
1. CONCRETE vehicle. Physically perceivable. Vehicle must be more
   concrete than topic.
2. CROSS-DOMAIN. Vehicle from a clearly different conceptual domain.
   anger→fire (emotion→physical) GOOD.
   anger→rage (emotion→emotion, synonym) BAD.
3. MULTI-DIMENSIONAL. Metaphor should resonate across 2+ of these:
   sensorimotor, behaviour, functional, effect, emotional, social.
   Single-dimension matches are weak.
4. NOT a synonym, hypernym, hyponym, meronym, or paraphrase.
5. Living metaphor preferred. Lakoff classics (life→journey) are
   fine if structurally rich; avoid dead metaphors literalised by
   usage (e.g. "leg of a table").

Each shared_feature pairs a dimension with a specific concept that
both topic and vehicle exhibit. Keep concepts as short noun phrases.

If fewer than 3 strong metaphors exist, return only the strong ones.

OUTPUT (JSON only, no markdown, no preamble):
{"topic":"<word>","metaphors":[{"vehicle":"<word>","shared_features":[{"dimension":"<dim>","concept":"<concept>"}],"confidence":<0.0-1.0>}]}

EXAMPLE
Input: anger
Output: {"topic":"anger","metaphors":[
  {"vehicle":"fire","shared_features":[
    {"dimension":"sensorimotor","concept":"heat"},
    {"dimension":"behaviour","concept":"spreading"},
    {"dimension":"behaviour","concept":"consuming"},
    {"dimension":"effect","concept":"destruction"},
    {"dimension":"emotional","concept":"intensity"}],"confidence":0.95},
  {"vehicle":"storm","shared_features":[
    {"dimension":"behaviour","concept":"builds then breaks"},
    {"dimension":"sensorimotor","concept":"turbulence"},
    {"dimension":"effect","concept":"damage"},
    {"dimension":"social","concept":"clears air after"}],"confidence":0.85},
  {"vehicle":"volcano","shared_features":[
    {"dimension":"behaviour","concept":"pressure builds invisibly then erupts"},
    {"dimension":"sensorimotor","concept":"heat"},
    {"dimension":"emotional","concept":"explosive release"}],"confidence":0.85},
  {"vehicle":"beast","shared_features":[
    {"dimension":"behaviour","concept":"must be tamed"},
    {"dimension":"functional","concept":"external agent within self"},
    {"dimension":"social","concept":"feared, primal"}],"confidence":0.7}]}

EXAMPLE
Input: time
Output: {"topic":"time","metaphors":[
  {"vehicle":"money","shared_features":[
    {"dimension":"functional","concept":"spent, saved, wasted"},
    {"dimension":"social","concept":"budgeted, owed"},
    {"dimension":"behaviour","concept":"tracked carefully"}],"confidence":0.95},
  {"vehicle":"river","shared_features":[
    {"dimension":"behaviour","concept":"flows one direction"},
    {"dimension":"sensorimotor","concept":"continuous motion"},
    {"dimension":"effect","concept":"carries things away"}],"confidence":0.9},
  {"vehicle":"thief","shared_features":[
    {"dimension":"behaviour","concept":"takes without consent"},
    {"dimension":"effect","concept":"loss noticed late"},
    {"dimension":"emotional","concept":"lamented"}],"confidence":0.75}]}

Input: <TOPIC>
Output:
```

## Output schema (per anchor synset)

```json
{
  "topic": "anger",
  "metaphors": [
    {
      "vehicle": "fire",
      "shared_features": [
        {"dimension": "sensorimotor", "concept": "heat"},
        {"dimension": "behaviour", "concept": "spreading"}
      ],
      "confidence": 0.95
    }
  ]
}
```

Dimensions: `sensorimotor | behaviour | functional | effect | emotional | social` (mirrors property taxonomy; `other` deliberately excluded — if the LLM can't name a dimension, the feature is too vague to keep).

## Test plan

1. **Pick 20 anchor topics** mixing:
   - 5 canonical Lakoff abstractions (anger, time, ideas, life, argument)
   - 5 concrete-but-metaphor-rich nouns (heart, light, road, anchor, mirror)
   - 5 compound / rare nouns (deadline, recursion, ambush, threshold, gridlock)
   - 5 emotion / state nouns (anxiety, hope, grief, courage, doubt)
2. **Run prompt on both Haiku 4.5 and Sonnet 4.6**, same 20 topics. Independent runs.
3. **Score per output:**
   - JSON parseability (binary)
   - Schema compliance (all required fields, dimension in canonical set, confidence in [0,1])
   - Quality pass: for each (topic, vehicle, shared_features) tuple — does it satisfy criteria 1–5? Operator manual eyeball.
4. **Aggregate:** per-model format-compliance %, per-model quality-pass %, per-criterion violation counts.

## Pass / fail criteria

**Haiku passes** if: ≥80% format-compliant AND ≥60% quality-pass on manual eyeball. → Pivot is cost-viable. Promote to milestone.

**Haiku fails on format, Sonnet passes** → Try Haiku-draft → Sonnet-refine on the failing subset. If hybrid lifts Haiku output to passing threshold, the pivot is still cost-viable (at ~2× Haiku cost, still under all-Sonnet).

**Both pass on format, only Sonnet passes on quality** → Either eat the Sonnet cost or use Sonnet only on the ~5k highest-frequency anchors and accept Haiku on the long tail.

**Both fail** → Pivot is not viable in current form. Either: improve prompt with more worked examples; or fall back to property-cascade as primary with hand-curated metaphor pairs as a small authoritative overlay.

## Cohort dividend (independent of pivot decision)

Even if we never promote the full pivot to a milestone, this prompt run on ~200 carefully-chosen topics gives us the **evaluation cohort** we don't currently have (the 5–10 vehicles-per-topic idea from the brainstorm). That solves the M05 verdict's separation-score caveat about n=1 inapt resolutions. Worth running the prompt at small scale regardless of full-pivot decision.

## Files this spike will produce

- `data-pipeline/scripts/metaphor_enrichment_spike.py` — prompt runner over a fixed test-topic list, dual-model
- `data-pipeline/output/metaphor_spike_haiku.jsonl` — Haiku output
- `data-pipeline/output/metaphor_spike_sonnet.jsonl` — Sonnet output
- `data-pipeline/output/metaphor_spike_scoring.md` — manual eyeball results + aggregate stats
- This doc updated with the verdict + decision

## Cost estimate

- Spike itself: half-day. 20 topics × 2 models is small enough to run in minutes; the work is the scoring rubric and the manual quality pass.
- Full enrichment (if pivot promoted): ~same order as current sensorimotor enrichment. ~35k synsets, Haiku rate, ~24–48h elapsed depending on rate limits. Sonnet equivalent ~10× cost.

## Decision authority

This spike is **operator-decision** at the end. Two go/no-go gates:

1. **Spike-result gate** — does the prompt deliver on the test topics? Pass criteria above.
2. **Strategic gate** — does pivoting now (vs continuing M06+ on the existing roadmap) serve the project? Operator call.
