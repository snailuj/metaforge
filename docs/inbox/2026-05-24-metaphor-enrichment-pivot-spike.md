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
3. **Polysemy at snap — vehicles.** Word "fire" maps to multiple synset_ids (noun: combustion / firearm / dismissal). Same sense-disambiguation problem property snap already solves — confirm the existing snap algorithm handles this without modification.
4. **Polysemy inside `shared_features` concepts.** Same problem one level deeper. "heat" inside `{"dimension":"sensorimotor","concept":"heat"}` is itself polysemous (temperature / pressure / sexual attraction / intensity-of-feeling). Per-concept inline gloss is impractical — token cost balloons and the LLM struggles with gloss-consistency across many concepts in one response.

   **Decision for this spike: Path A from Phase 1a.** The apt prompt explicitly constrains concepts to single common English words so they can be programmatically snapped to dictionary entries downstream via the same `lemmas → synset_id` path used for vehicles. Sense disambiguation falls out of snap (property-based tiebreaker; bridge nodes become synset_ids — queryable like vehicles).

   Phase 1a diagnostic shifts accordingly: not "what shapes does the LLM emit?" but "**does the LLM comply with the single-word constraint, and at what snap rate do those single words resolve against the `lemmas` table?**" Compliance failure here is a prompt-engineering bug we'd rather catch on 5 topics than 200.

   Rationale for promoting Path A: snappability is foundational, not a Phase 2 polish item. Past experience with the Haiku property-enrichment prompt confirmed the model defaults to multi-word phrases unless very explicitly steered away — the same drift would compound here if left to "learn from emission."
5. **Cost ceiling.** ~35k synsets × N output tokens × per-call cost. Need a real number before commit.

## Resolved during brainstorm 2026-05-24

- **Input granularity:** option (b) — `word + tight Claude-summarised gloss`. Disambiguates polysemy cheaply, matches existing enrich-properties prompt shape. Verbatim WordNet definition rejected as too long; tight Claude gloss preferred.
- **Storage:** the Claude-summarised gloss is **persisted in the DB alongside the WordNet definition** (new column on `synsets`, or sibling table). Future UI work may promote the gloss to user-facing whenever present.
- **Sense-gloss-only input variant (option c)** deferred to backlog — interesting research signal (does the LLM metaphor-map a concept vs pattern-match a word?) but not this week.
- **Inapt cohort generation:** option (b) — dedicated "plausible-but-wrong" prompt with structured JSON output. Closed-vocabulary `inapt_reason_type` tag + free-text `explanation` per vehicle. Cross-shuffle (option c) deferred to volume-scaling phase; same-prompt inapt (option a) rejected for triviality bias.
- **Phasing:** spike runs in three gated phases — 1a small validation (5 topics, 20 calls), 1b full 20-topic spike (80 calls), Phase 2 cohort scale-up (~400 calls). Each phase operator-gated against the next. Operator funds 1a first; 1b only on 1a pass; Phase 2 only on 1b pass.
- **Score-as-we-go:** every (topic, vehicle) pair is scored through the cascade in the same batch it's generated. First-look calibration signal builds live across phases. Diagnostic axis: per-`inapt_reason_type` discrimination breakdown reveals which failure modes the cascade catches vs misses — the calibration evidence M05 currently lacks.
- **Gloss in output rejected.** Topic gloss is sent in input but NOT echoed in output (wasted tokens). Runner attaches gloss locally at writeback for human inspection.
- **Concept disambiguation inside `shared_features`** flagged as a real polysemy concern one level deeper than vehicle disambiguation. Per-concept gloss rejected as token-prohibitive. **Spike adopts Path A from Phase 1a, not Phase 2:** concepts constrained to single common English words in the apt prompt so they're reliably snappable to dictionary entries downstream. Prior experience with the Haiku property-enrichment prompt showed the model defaults to multi-word phrases unless explicitly steered — same drift would compound here if left to "learn from emission." Phase 1a diagnostic now includes single-word compliance rate and snap-rate against `lemmas`. See open-questions item #4.

## Prompt — apt (current draft)

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
both topic and vehicle exhibit.

CONCEPT FORMAT (CRITICAL): Each "concept" value MUST be a SINGLE
common English word (noun, gerund, or adjective). NOT a phrase. NOT
a list. NOT a comma-separated string. NOT a sentence fragment.
These concepts are programmatically resolved to dictionary entries
downstream, so they MUST exist as standalone words.

GOOD: heat, spreading, destruction, intensity, taming, eruption
BAD:  "must be tamed", "spent saved wasted", "clears air after",
      "pressure builds invisibly then erupts"

If a single word cannot capture what you mean, split it into
multiple shared_feature entries.

If fewer than 3 strong metaphors exist, return only the strong ones.

OUTPUT (JSON only, no markdown, no preamble). DO NOT echo the input gloss in the output — runner attaches it locally:
{"topic":"<word>","metaphors":[{"vehicle":"<word>","shared_features":[{"dimension":"<dim>","concept":"<concept>"}],"confidence":<0.0-1.0>}]}

EXAMPLE
Input: anger (a strong feeling of displeasure)
Output: {"topic":"anger","metaphors":[
  {"vehicle":"fire","shared_features":[
    {"dimension":"sensorimotor","concept":"heat"},
    {"dimension":"behaviour","concept":"spreading"},
    {"dimension":"behaviour","concept":"consumption"},
    {"dimension":"effect","concept":"destruction"},
    {"dimension":"emotional","concept":"intensity"}],"confidence":0.95},
  {"vehicle":"storm","shared_features":[
    {"dimension":"behaviour","concept":"buildup"},
    {"dimension":"behaviour","concept":"release"},
    {"dimension":"sensorimotor","concept":"turbulence"},
    {"dimension":"effect","concept":"damage"}],"confidence":0.85},
  {"vehicle":"volcano","shared_features":[
    {"dimension":"behaviour","concept":"pressure"},
    {"dimension":"behaviour","concept":"eruption"},
    {"dimension":"sensorimotor","concept":"heat"},
    {"dimension":"emotional","concept":"release"}],"confidence":0.85},
  {"vehicle":"beast","shared_features":[
    {"dimension":"behaviour","concept":"taming"},
    {"dimension":"functional","concept":"agency"},
    {"dimension":"social","concept":"fear"}],"confidence":0.7}]}

EXAMPLE
Input: time (an indefinite period as a continuum)
Output: {"topic":"time","metaphors":[
  {"vehicle":"money","shared_features":[
    {"dimension":"functional","concept":"spending"},
    {"dimension":"functional","concept":"saving"},
    {"dimension":"social","concept":"budgeting"},
    {"dimension":"behaviour","concept":"tracking"}],"confidence":0.95},
  {"vehicle":"river","shared_features":[
    {"dimension":"behaviour","concept":"flowing"},
    {"dimension":"sensorimotor","concept":"motion"},
    {"dimension":"effect","concept":"erosion"}],"confidence":0.9},
  {"vehicle":"thief","shared_features":[
    {"dimension":"behaviour","concept":"taking"},
    {"dimension":"effect","concept":"loss"},
    {"dimension":"emotional","concept":"grief"}],"confidence":0.75}]}

Input: <TOPIC> (<GLOSS>)
Output:
```

## Prompt — inapt (current draft)

```
You generate plausible-but-INAPT metaphor mappings for a thesaurus
evaluation cohort. For each topic, return 2-3 vehicles that have
SURFACE resemblance to good metaphors but actually fail under
structural scrutiny.

The goal is to test whether a structural-similarity algorithm can
DISCRIMINATE apt cross-domain metaphors from plausible-looking
cross-domain noise. Therefore:

- DO NOT return obvious antonyms or random unrelated words. They
  test triviality, not discrimination.
- DO return vehicles that share a single surface feature, are
  paraphrastic, or sit in the same conceptual domain.
- Each vehicle must look "metaphor-eligible" at first glance —
  the inaptness should require analysis to detect.

FAILURE MODES (closed vocabulary — pick exactly one per vehicle):
- single_dimension: shares only one of {sensorimotor, behaviour,
  functional, effect, emotional, social}. Insufficient resonance.
- same_domain: actually a paraphrase / synonym / near-synonym in
  the same conceptual domain. anger→fury, time→duration.
- wrong_concreteness: vehicle is at the same abstraction level as
  topic, or more abstract. anger→fury, time→eternity.
- dead_metaphor: a once-living metaphor now literalised by usage
  ("leg of a table"). The mapping no longer feels figurative.
- synonym_or_hypernym: vehicle is a kind-of / part-of /
  contained-in the topic. anger→emotion, fire→combustion.

OUTPUT (JSON only, no markdown, no preamble). DO NOT echo the input gloss in the output — runner attaches it locally:
{"topic":"<word>","inapt_metaphors":[{"vehicle":"<word>","inapt_reason_type":"<tag>","explanation":"<text>"}]}

EXAMPLE
Input: anger (a strong feeling of displeasure)
Output: {"topic":"anger","inapt_metaphors":[
  {"vehicle":"calendar","inapt_reason_type":"single_dimension","explanation":"shares only the functional dimension of time-tracking; no sensorimotor, emotional, or behavioural resonance"},
  {"vehicle":"fury","inapt_reason_type":"same_domain","explanation":"near-synonym in the emotion domain; not a cross-domain mapping at all"},
  {"vehicle":"emotion","inapt_reason_type":"synonym_or_hypernym","explanation":"anger is a kind-of emotion; a taxonomic parent, not a metaphor"}]}

EXAMPLE
Input: time (an indefinite period as a continuum)
Output: {"topic":"time","inapt_metaphors":[
  {"vehicle":"clock","inapt_reason_type":"single_dimension","explanation":"shares only the functional dimension of measurement; clock is an instrument of time, not a structurally-different domain mapping onto it"},
  {"vehicle":"duration","inapt_reason_type":"same_domain","explanation":"near-synonym; same conceptual domain, no cross-domain leap"},
  {"vehicle":"eternity","inapt_reason_type":"wrong_concreteness","explanation":"more abstract than time itself; vehicle should be more concrete than topic"}]}

Input: <TOPIC> (<GLOSS>)
Output:
```

## Output schema — apt (per anchor synset)

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

`gloss` is sent in the input prompt but deliberately NOT echoed in output — wasted tokens. Runner attaches the gloss locally at writeback for human-inspection records.

## Output schema — inapt (per anchor synset)

```json
{
  "topic": "anger",
  "inapt_metaphors": [
    {
      "vehicle": "calendar",
      "inapt_reason_type": "single_dimension",
      "explanation": "shares only the functional dimension of time-tracking; no sensorimotor, emotional, or behavioural mapping"
    }
  ]
}
```

Closed-vocabulary `inapt_reason_type` tags (each maps to a violated apt criterion):

| Tag | Definition | Maps to apt criterion violated |
|-----|------------|--------------------------------|
| `single_dimension` | Shares only one of the six dimensions. Insufficient resonance. | #3 multi-dimensional |
| `same_domain` | Near-synonym / paraphrase in the same conceptual domain (anger→fury). | #2 cross-domain |
| `wrong_concreteness` | Vehicle at the same abstraction level as topic or more abstract (time→eternity). | #1 concrete vehicle |
| `dead_metaphor` | Once-living metaphor now literalised by usage; mapping no longer felt as figurative. | #5 living metaphor |
| `synonym_or_hypernym` | Vehicle is a kind-of / part-of / contained-in the topic (anger→emotion). | #4 not synonym/hyponym |

The closed vocabulary is the diagnostic axis: when we score apt-vs-inapt discrimination, we can ask *which failure modes the cascade discriminates against best*. γ may help with `single_dimension` (the multi-dimensional bonus literally targets this) but not necessarily with `same_domain` (the cosine band might mis-bin a same-domain pair as cross-domain). Per-failure-mode discrimination breakdown is exactly the calibration evidence M05 currently lacks.

## Test plan — phased rollout

The spike phases gate at each step so we never spend on a phase whose predecessor failed.

### Phase 1a — small validation sample (operator-funded, cheap)

- **5 anchor topics** spanning the four type-categories: `anger` (Lakoff classic), `heart` (concrete metaphor-rich), `deadline` (compound), `anxiety` (emotion).
- **Both models** (Haiku 4.5, Sonnet 4.6).
- **Both prompts** (apt + inapt). 5 topics × 2 models × 2 prompts = 20 LLM calls. Trivially cheap.
- **Score-as-we-go:** each (topic, vehicle) pair is scored through the Go cascade in the same batch (or via Python `evaluate_cascade.py` for the spike, since the Go path requires the API running). This gives first-look calibration signal *during* validation.
- **Gate to Phase 1b:**
  - JSON parseability ≥80% per model
  - Schema compliance ≥80% per model
  - **Single-word concept compliance ≥90% per model** (every `concept` value is a single dictionary word). Drift below this threshold means the apt prompt needs more steering before scaling.
  - **Concept snap-rate ≥80% per model** (concepts resolve to at least one `synset_id` via the `lemmas` table). Below this means the LLM is inventing concepts that aren't in our lexicon, and the bridge-node plumbing won't work.
  - Manual eyeball quality pass acceptable on at least the Sonnet output (Haiku failures here would re-shape the prompt before scaling)

### Phase 1b — full 20-topic spike (operator-gated promotion from 1a)

- **20 anchor topics** as originally planned:
  - 5 canonical Lakoff abstractions (anger, time, ideas, life, argument)
  - 5 concrete-but-metaphor-rich nouns (heart, light, road, anchor, mirror)
  - 5 compound / rare nouns (deadline, recursion, ambush, threshold, gridlock)
  - 5 emotion / state nouns (anxiety, hope, grief, courage, doubt)
- **Both models, both prompts.** 20 × 2 × 2 = 80 LLM calls.
- **Score-as-we-go** continues — each batch's (topic, vehicle) pairs land in the cohort scoring table as they're generated.
- **Aggregate metrics:**
  - Per-model format-compliance %
  - Per-model quality-pass % (apt and inapt evaluated separately)
  - Per-criterion violation counts (apt prompt criteria 1–5; inapt prompt failure-mode coverage)
  - **First-look calibration:** separation_score and aptness_rate against the cascade, computed live on the 20-topic cohort
- **Gate to Phase 2:** operator review against pass/fail criteria below.

### Phase 2 — cohort scale-up (operator-gated, paid)

- **~200 anchor topics** drawn from a mix of: high-frequency abstractions, Lakoff classics, emotion words, common compound nouns, and a representative sample from `synsets` by POS / concreteness band.
- **Winning model from Phase 1b** (Haiku if it passed; Sonnet otherwise; hybrid Haiku-draft → Sonnet-refine if neither passed alone).
- **Both prompts.** ~200 × 1 × 2 = ~400 LLM calls.
- **Output:** the eval cohort that unblocks M05 calibration.

### Phase 3 — full-enrichment pivot decision

Out of scope for this spike. Once Phase 2 lands and M05 calibration re-runs against the new cohort, operator decides whether to promote to a full 35k-synset enrichment milestone.

## Pass / fail criteria

**Haiku passes** if: ≥80% format-compliant AND ≥60% quality-pass on manual eyeball. → Pivot is cost-viable. Promote to milestone.

**Haiku fails on format, Sonnet passes** → Try Haiku-draft → Sonnet-refine on the failing subset. If hybrid lifts Haiku output to passing threshold, the pivot is still cost-viable (at ~2× Haiku cost, still under all-Sonnet).

**Both pass on format, only Sonnet passes on quality** → Either eat the Sonnet cost or use Sonnet only on the ~5k highest-frequency anchors and accept Haiku on the long tail.

**Both fail** → Pivot is not viable in current form. Either: improve prompt with more worked examples; or fall back to property-cascade as primary with hand-curated metaphor pairs as a small authoritative overlay.

## Cohort dividend (independent of pivot decision)

Even if we never promote the full pivot to a milestone, this prompt run on ~200 carefully-chosen topics gives us the **evaluation cohort** we don't currently have (the 5–10 vehicles-per-topic idea from the brainstorm). That solves the M05 verdict's separation-score caveat about n=1 inapt resolutions. Worth running the prompt at small scale regardless of full-pivot decision.

## M05 calibration follows from the spike — explicit sequencing

The M05 verdict left three caveats unresolved: (1) n=1 inapt magnitude sensitivity, (2) `aptness_rate=0` because γ moves ranks but not absolute scores past the `apt_mean > inapt_mean + σ` threshold, (3) ~24% apt resolution against the curator cohort. These look like calibration problems but they are **measurement-instrument problems** — the existing Lakoff cohort can't measure what M05 changes, regardless of how the threshold is tuned. More calibration work against the same broken cohort will not move the metric.

This spike is the unblock. At even small scale (200 topics × 5–10 apt vehicles + matched inapt controls), the cohort produced here has the n>>1 inapt mass that makes σ meaningful again. Once that lands:

1. Re-run M05 γ-sweep against the new cohort. `aptness_rate` becomes measurable for the first time.
2. Either γ=1.0 holds with absolute-score corroboration (calibration closed) or the new cohort reveals γ needs adjustment.
3. The cascade — repositioned, not retired — keeps its job as cold-start engine + ranking primitive + multi-hop derivation engine on top of the enriched substrate.

The spike doesn't defer M05 calibration. It **delivers the instrument calibration needs**. Sequencing recap:

| Step | Output | Unblocks |
|------|--------|----------|
| Spike runs prompt on 20 test topics, dual-model | Format/quality verdict | Cohort scale-up |
| Spike scales to ~200 topics + inapt controls | Eval cohort | M05 calibration measurement |
| M05 γ-sweep re-run against new cohort | `aptness_rate` measurable | Calibration close-out OR γ adjustment |
| Full enrichment pivot decision | Operator call | Programme direction |

If the spike fails at step 1, M05 calibration is still blocked on cohort — the failure means we need another cohort path (hand curation, public dataset, Claude-as-judge), not that we should retry M05 calibration directly.

## Files this spike will produce

- `data-pipeline/scripts/metaphor_enrichment_spike.py` — prompt runner over a fixed test-topic list, dual-model, dual-prompt, phased (1a → 1b → 2)
- `data-pipeline/scripts/glosses_summarise.py` — Claude-summarised gloss generator (input: synset_id + WordNet definition → tight gloss), idempotent, JSONL output
- `data-pipeline/output/glosses.jsonl` — synset_id → tight Claude gloss (persisted alongside WordNet definition; pending decision on DB column vs sibling table)
- `data-pipeline/output/metaphor_spike_apt_haiku.jsonl` — Haiku apt output
- `data-pipeline/output/metaphor_spike_apt_sonnet.jsonl` — Sonnet apt output
- `data-pipeline/output/metaphor_spike_inapt_haiku.jsonl` — Haiku inapt output
- `data-pipeline/output/metaphor_spike_inapt_sonnet.jsonl` — Sonnet inapt output
- `data-pipeline/output/metaphor_spike_scores.jsonl` — per (topic, vehicle) cascade score appended live as the spike runs
- `data-pipeline/output/metaphor_spike_scoring.md` — manual eyeball results, aggregate format/quality metrics, first-look separation_score / aptness_rate, per-failure-mode discrimination breakdown
- This doc updated with the verdict + decision after Phase 1b

## Cost estimate

- Spike itself: half-day. 20 topics × 2 models is small enough to run in minutes; the work is the scoring rubric and the manual quality pass.
- Full enrichment (if pivot promoted): ~same order as current sensorimotor enrichment. ~35k synsets, Haiku rate, ~24–48h elapsed depending on rate limits. Sonnet equivalent ~10× cost.

## Decision authority

This spike is **operator-decision** at the end. Two go/no-go gates:

1. **Spike-result gate** — does the prompt deliver on the test topics? Pass criteria above.
2. **Strategic gate** — does pivoting now (vs continuing M06+ on the existing roadmap) serve the project? Operator call.
