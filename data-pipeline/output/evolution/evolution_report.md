# Evolutionary Prompt Optimisation — Experiment Report

## 1. Executive Summary

The evolutionary optimisation of enrichment prompts across 10 trials produced a headline MRR of 0.1082 from the best variant (exploit-persona_poet-g2), nominally +25.4% over the baseline of 0.0863. However, post-hoc analysis revealed that three of the 49 evaluation pairs (hope→light, grief→anchor, age→winter) appear as explicit examples in the g2 prompt text, inflating the result. Excluding these leaked pairs, the corrected improvement is **+5.5%** (MRR 0.0931 vs baseline 0.0883) — still positive, but far more modest. Of the five exploration prompts, three survived initial screening, while two exploitation variants degenerated to MRR=0.0, indicating high sensitivity to prompt formulation. The persona_poet approach — which guides the LLM toward metaphorical associations — remains the most promising strategy, but the leakage finding means that future experiments must enforce strict separation between prompt examples and evaluation pairs.

## 2. Methodology

The experiment evaluated **5 exploration prompts** against a baseline, scoring each on **49 metaphor pairs** using Mean Reciprocal Rank (MRR).

**Procedure:**

1. **Exploration (Gen 0):** Each prompt was used to enrich a sample of synsets with sensory/behavioural properties. The enriched lexicon was then queried via the Metaforge API to find each metaphor pair's target in the source's nearest neighbours. MRR across all pairs gives a single score per prompt.
2. **Exploitation (Gen 1+):** Prompts that outperformed the baseline (survivors) were iteratively tweaked by an LLM. Each tweak was evaluated identically; improvements were kept, regressions reverted. Early stopping after consecutive failures prevented wasted budget.

Total trials: **10** (6 exploration, 4 exploitation).

## 3. Exploration Results (Gen 0)

| Prompt | MRR | unique_props | hapax_rate | avg_props/synset | hit_rate | survived |
|--------|-----|-------------|------------|-----------------|----------|----------|
| persona_poet | 0.0904 | 4614 | 0.818 | 12.6 | 0.653 | Yes |
| contrastive | 0.0904 | 5916 | 0.950 | 10.2 | 0.653 | Yes |
| narrative | 0.0875 | 4640 | 0.955 | 9.8 | 0.714 | Yes |
| baseline | 0.0863 | 3048 | 0.577 | 11.2 | 0.408 | Yes |
| embodied | 0.0704 | 6498 | 0.927 | 11.6 | 0.776 | No |
| taxonomic | 0.0468 | 2867 | 0.632 | 11.6 | 0.612 | No |

## 4. Exploitation Results (Gen 1+)

### persona_poet

| Gen | Parent MRR | MRR | Delta | Mutation | Kept? |
|-----|-----------|-----|-------|----------|-------|
| 1 | 0.0904 | 0.0815 | -0.0089 | Added explicit instruction for metaphorical concepts to generate properties o... | No |
| 2 | 0.0904 | 0.1082 | +0.0178 | Added explicit instruction to capture metaphorical associations and archetypa... | Yes |
| 5 | 0.1082 | 0.0000 | -0.1082 | Added explicit instruction to map abstract concepts to their archetypal metap... | No |

### contrastive

| Gen | Parent MRR | MRR | Delta | Mutation | Kept? |
|-----|-----------|-----|-------|----------|-------|
| 2 | 0.0904 | 0.0000 | -0.0904 | Added explicit prompt to surface concrete, imagistic properties and symbolic ... | No |

### persona_poet

The lineage explored whether explicit instruction to ground metaphorical concepts in their physical/archetypal targets could improve MRR. Generation 1's focus on embodied traits underperformed (0.0815), but generation 2's reframing to capture metaphorical *associations* and symbolic resonance succeeded dramatically (0.1082, +25% over baseline). The mutation succeeded because it shifted from prescriptive embodiment to descriptive archetype alignment—letting the model find sensory properties that naturally resonate with symbolic pairings like love→journey rather than forcing them. Generation 5 then over-constrained the approach by mapping abstract concepts directly, collapsing to 0.0 and suggesting that explicit archetypal mapping becomes brittle when over-specified.

### contrastive

The lineage tested whether surfacing concrete imagery and symbolic associations could unlock weak pairs (hope→light, memory→palace). The exploration baseline (0.0904) was promising, but generation 2's explicit instruction to extract sensory anchors and archetypal imagery crashed to 0.0, indicating the mutation was either too prescriptive or conflicted with the model's ability to generate coherent properties. The failure suggests that contrastive reasoning alone is insufficient; the task requires integrating archetype guidance with property generation in a way that contrastive framing does not naturally support.

### narrative

The exploration prompt (0.0875) was attempted but no mutations were pursued. It underperformed persona_poet and contrastive by ~3%, suggesting narrative framing alone does not capture the metaphorical reasoning required for weak pairs. No further investment was made in this lineage.

### taxonomic

The exploration prompt (0.0468) performed poorly, likely because taxonomic hierarchy-building conflicts with metaphorical association—the task requires lateral symbolic thinking rather than vertical classification. Early elimination was justified.

### embodied

The exploration prompt (0.0704) underperformed other lineages, suggesting embodied/sensory reasoning alone lacks the symbolic and archetypal framing needed to bridge abstract metaphors to concrete properties. No mutations were attempted.

## 5. Cross-Generation Analysis

### Correlations (MRR vs secondary metrics)

| Metric | Pearson r | Description |
|--------|----------|-------------|
| unique_properties | 0.421 | moderate positive |
| hapax_rate | 0.316 | weak positive |
| avg_properties_per_synset | 0.216 | weak positive |
| hit_rate | -0.005 | weak negative |

### Hit Rate Comparison

| Trial | MRR | Hit Rate |
|-------|-----|----------|
| exploit-persona_poet-g2 | 0.1082 | 0.673 |
| explore-persona_poet | 0.0904 | 0.653 |
| explore-contrastive | 0.0904 | 0.653 |
| explore-narrative | 0.0875 | 0.714 |
| baseline | 0.0863 | 0.408 |
| exploit-persona_poet-g1 | 0.0815 | 0.612 |
| explore-embodied | 0.0704 | 0.776 |
| explore-taxonomic | 0.0468 | 0.612 |

### Prompt Example Leakage Analysis

The exploit-persona_poet-g2 prompt contains three metaphor pairs as inline examples: `hope → light`, `grief → anchor`, and `age → winter`. These same pairs appear in the 49-pair evaluation fixture, creating data leakage. The impact:

| Pair | Rank in g2 | RR |
|------|-----------|-----|
| hope → light | 1 | 1.0000 |
| grief → anchor | 58 | 0.0172 |
| age → winter | — | 0.0000 |

Only `hope → light` benefited materially (rank 1, RR=1.0); `grief → anchor` was barely found and `age → winter` was missed entirely. Removing all three pairs and recomputing:

| Metric | All 49 pairs | Excluding 3 leaked pairs (46) |
|--------|-------------|-------------------------------|
| persona_poet g2 MRR | 0.1082 | 0.0931 |
| Baseline MRR | 0.0863 | 0.0883 |
| **Improvement** | **+25.4%** | **+5.5%** |

The corrected +5.5% improvement is real but modest. This finding applies broadly: any exploitation prompt that mentions specific metaphor pairs as examples risks inflating its score on those pairs. Future experiments must either (a) exclude prompt-mentioned pairs from evaluation, or (b) use a held-out evaluation set that is never visible to the prompt author (human or LLM).

## 6. Per-Pair Analysis

### Easiest Pairs (highest avg RR)

- knowledge → light: avg RR = 0.688
- hope → light: avg RR = 0.415
- anxiety → knot: avg RR = 0.368
- freedom → bird: avg RR = 0.252
- loneliness → desert: avg RR = 0.204
- life → stage: avg RR = 0.198
- rage → storm: avg RR = 0.186
- conscience → compass: avg RR = 0.179
- silence → blanket: avg RR = 0.148
- youth → spring: avg RR = 0.129

### Hardest Pairs (lowest avg RR)

- theory → building: avg RR = 0.000
- age → winter: avg RR = 0.002
- idea → seed: avg RR = 0.004
- joy → fountain: avg RR = 0.006
- imagination → wings: avg RR = 0.007
- democracy → foundation: avg RR = 0.007
- blood → river: avg RR = 0.008
- skin → armour: avg RR = 0.008
- time → river: avg RR = 0.011
- childhood → garden: avg RR = 0.012

### Never Found (1 pairs)

- theory → building

### Tier Comparison

| Tier | Avg RR |
|------|--------|
| medium | 0.0571 |
| strong | 0.1035 |

## 7. Discussion

### What Correlated with Higher MRR

Three metrics showed positive correlation with MRR performance:

- **Unique properties** (*r* = 0.421, moderate): The strongest signal. Prompts that generated diverse, non-redundant properties consistently outperformed those producing generic or repeated descriptors. This suggests that specificity and richness of the semantic space matter more than raw volume.
- **Hapax rate** (*r* = 0.316, weak): Single-occurrence properties also correlated positively, indicating that rare, distinctive properties — even if sparse — contributed to better matches. This aligns with matching weak metaphor pairs that require precise archetypal anchors.
- **Average properties per synset** (*r* = 0.216, weak): Modest signal. More properties per synset helped, but only marginally. Quality (diversity) outweighed quantity.

Notably, **hit rate showed near-zero correlation** (*r* = −0.005), suggesting that raw coverage is not predictive of MRR. Hitting many pairs weakly does not beat hitting fewer pairs strongly.

### Why Exploitation Succeeded or Failed

**Success: persona_poet g2 (headline +25.4%, corrected +5.5%)**

The winning mutation added explicit instruction to capture *metaphorical associations and archetypal pairings*. This directly addressed the model's tendency to generate sensory descriptors divorced from symbolic intent. By guiding the model toward the *archetypal targets* of metaphors, the prompt narrowed the property space to what actually bridges the conceptual gap in weak pairs. However, the g2 prompt text includes three evaluation pairs as examples (hope→light, grief→anchor, age→winter), inflating the headline MRR. After excluding these leaked pairs, the improvement drops from +25.4% to +5.5% — still the best result, but the mechanism is partly data leakage rather than purely improved reasoning. The generation 1 predecessor (0.0815) failed because it focused too literally on "physical embodiments" without acknowledging that the test pairs demand symbolic resonance, not just sensory anchoring.

**Failure: persona_poet g5 (degraded to 0.0)**

The g5 mutation attempted to add an extra step — mapping abstract concepts to archetypal targets, *then* extracting sensory properties. This over-constrained the model. By forcing a two-stage transformation, the prompt likely produced incoherent or off-target properties, causing systematic misses across the test set. The pattern suggests that explicit multi-step instructions can backfire if they introduce logical brittleness.

**Failure: contrastive g2 (degraded to 0.0)**

A similar degeneracy. The mutation aimed to "surface concrete, imagistic properties and symbolic associations" but resulted in complete failure. The added specificity likely conflicted with the base contrastive framing or produced properties so constrained that they no longer generalised to the 49-pair fixture.

### Tier Performance: Strong vs. Medium Pairs

- **Strong tier MRR: 0.1035** — metaphor pairs with robust archetypal grounding (e.g., hope→light, time→river).
- **Medium tier MRR: 0.0571** — pairs requiring deeper or more implicit symbolic reasoning (e.g., less canonical metaphors or abstract concepts).

The 1.8× gap suggests that the best-performing prompt (persona_poet g2) succeeded partly by anchoring properties to culturally familiar archetypes — though some of this effect is attributable to prompt example leakage on strong-tier pairs like hope→light. Medium-tier pairs remain challenging because they demand reasoning about less-canonical or context-dependent metaphorical bridges. Even the corrected +5.5% improvement leaves substantial room for growth, indicating a ceiling where richer data, multi-stage inference, or leakage-free prompt design may be needed.

### Failure Modes and Degenerate Trials

Two trials collapsed entirely (MRR = 0.0):

1. **persona_poet g5**: Over-specification. The prompt became too prescriptive about the transformation pipeline, likely confusing the model or constraining outputs to a narrow, incorrect space.
2. **contrastive g2**: Prompt collision. The added instruction contradicted or diluted the base contrastive framing, breaking coherence.

Both failures cluster around **generation 2+**, where mutations compound. This suggests a regime where prompt drift accumulates and adaptation strategies become brittle. Three of four exploitation trials (g1, g2, g5) came from persona_poet; only g2 survived. The others (g1 at 0.0815, g5 at 0.0) illustrate diminishing returns and increased risk in deep mutation chains.

A subtler failure mode is **prompt example leakage**: the LLM tweak generator introduced evaluation pairs as prompt examples (hope→light, grief→anchor, age→winter in g2; similar patterns in g1 and g5). This creates a perverse incentive where the evolutionary process selects for prompts that overfit to the evaluation fixture via their examples, rather than prompts that genuinely improve property extraction. The corrected improvement for g2 (+5.5% vs +25.4%) demonstrates the magnitude of this effect. Leakage is a systemic risk in any LLM-driven prompt evolution loop and must be addressed architecturally.

### Recommendations for Next Iteration

1. **Use persona_poet g2, but strip leaked examples first**: The corrected +5.5% improvement is real but modest. Before promoting to the full 20K enrichment, remove the three leaked pairs (hope→light, grief→anchor, age→winter) from the prompt's inline examples or replace them with pairs not in the evaluation fixture. Re-evaluate to confirm the improvement holds.

2. **Enforce train/test separation**: Future evolutionary runs must guarantee that no evaluation pair appears anywhere in the prompt text — including examples generated by the LLM tweak process. This likely requires an automated check at tweak generation time.

3. **Halt deep exploitation**: Most mutations beyond generation 1 degrade or fail. Future work should focus on *breadth* (testing orthogonal prompt families) rather than *depth* (chaining mutations).

4. **Target medium-tier pairs separately**: The 1.8× gap between tiers suggests a bifurcated solution space. Consider a two-model ensemble: one optimised for canonical metaphors (use persona_poet g2), another for rare or implicit pairs.

5. **Expand the test fixture**: With only 49 metaphor pairs, the correlation coefficients are weak. A richer fixture (200+ pairs across multiple tiers) would improve signal, reduce noise, and dilute the impact of any residual leakage.

## 8. Appendix A: All Prompt Texts

### baseline (`baseline`)

```
You are extracting sensory and behavioural properties for specific word senses.

CRITICAL: The definition tells you WHICH sense of the word to analyse. Many words have multiple meanings — focus ONLY on the sense described in the definition.

Extract 10-15 properties per word that describe:
- Physical qualities (texture, weight, temperature, luminosity, sound)
- Behavioural qualities (speed, rhythm, intensity, duration)
- Perceptual qualities (how it's experienced by senses)
- Functional qualities (what it does, how it moves, what it enables)

Properties must be SHORT (1-2 words). Be creative — capture the experiential essence, not just dictionary categories.

Examples showing sense disambiguation:

Word: run
Definition: deal in illegally, such as arms or liquor
Properties: ["furtive", "risky", "profitable", "shadowy", "underground", "covert", "transactional"]
(NOT: fast, athletic, sweaty — those are the locomotion sense)

Word: chain
Definition: a series of things depending on each other as if linked together
Properties: ["sequential", "dependent", "cascading", "fragile", "interconnected", "cumulative"]
(NOT: heavy, metallic, cold — those are the physical chain sense)

Word: fleece
Definition: shear the wool from
Properties: ["cutting", "harvesting", "seasonal", "rhythmic", "skilled", "yielding", "stripping"]
(NOT: woolly, soft, warm — those describe the material, not the shearing action)

Word: candle
Definition: stick of wax with a wick; gives light when burning
Properties: ["warm", "flickering", "luminous", "fragile", "waxy", "ephemeral", "aromatic"]

Word: whisper
Definition: speak softly; in a low voice
Properties: ["quiet", "intimate", "secretive", "breathy", "gentle", "transient", "hushed"]

Now extract properties for each of these word senses:

{batch_items}

Output ONLY a valid JSON array (no markdown, no explanation):
[{{"id": "...", "properties": [...]}}, ...]

```

### explore-persona_poet (`persona_poet`)

```
You are a poet cataloguing the sensory qualities of every concept you encounter.
For each word sense below, write 10-15 short (1-2 word) properties that capture its
experiential essence — how it feels, sounds, looks, moves, or affects the body.

Think like a poet: prioritise vivid, evocative, sensory language over abstract categories.

CRITICAL: The definition tells you WHICH sense of the word to analyse. Focus ONLY on that sense.

{batch_items}

Output ONLY a valid JSON array (no markdown, no explanation):
[{{"id": "...", "properties": [...]}}, ...]

```

### explore-contrastive (`contrastive`)

```
For each word sense below, list 10-15 short (1-2 word) properties that DISTINGUISH
this specific sense from other meanings of the same word and from similar concepts.

Focus on what makes this sense unique:
- What properties does THIS sense have that other senses lack?
- What sensory or behavioural qualities set it apart?

CRITICAL: The definition tells you WHICH sense of the word to analyse. Focus ONLY on that sense.

{batch_items}

Output ONLY a valid JSON array (no markdown, no explanation):
[{{"id": "...", "properties": [...]}}, ...]

```

### explore-narrative (`narrative`)

```
Imagine encountering each concept below in real life. Describe your experience
using 10-15 single words or short (1-2 word) phrases.

What would you see, hear, feel, smell, or taste? How would it move? What would
it remind you of? Capture the lived, embodied experience.

CRITICAL: The definition tells you WHICH sense of the word to analyse. Focus ONLY on that sense.

{batch_items}

Output ONLY a valid JSON array (no markdown, no explanation):
[{{"id": "...", "properties": [...]}}, ...]

```

### explore-taxonomic (`taxonomic`)

```
Systematically classify each word sense below along every perceptible dimension.
For each sense, provide 10-15 short (1-2 word) properties covering as many of
these dimensions as apply:

- Visual (colour, shape, size, luminosity, texture)
- Auditory (pitch, volume, timbre, rhythm)
- Tactile (temperature, weight, hardness, moisture)
- Olfactory/Gustatory (scent, taste, pungency)
- Kinetic (speed, direction, force, pattern)
- Temporal (duration, frequency, regularity)
- Affective (emotional tone, intensity, valence)

CRITICAL: The definition tells you WHICH sense of the word to analyse. Focus ONLY on that sense.

{batch_items}

Output ONLY a valid JSON array (no markdown, no explanation):
[{{"id": "...", "properties": [...]}}, ...]

```

### explore-embodied (`embodied`)

```
Describe each word sense below to someone who experiences the world primarily
through touch, smell, and sound (not sight). Use 10-15 short (1-2 word) properties
that convey how each concept feels physically, sounds, smells, weighs, or moves.

Avoid visual-only properties. Prioritise tactile, auditory, olfactory, and
kinaesthetic qualities.

CRITICAL: The definition tells you WHICH sense of the word to analyse. Focus ONLY on that sense.

{batch_items}

Output ONLY a valid JSON array (no markdown, no explanation):
[{{"id": "...", "properties": [...]}}, ...]

```

### exploit-persona_poet-g1 (`persona_poet`)

```
You are a poet cataloguing the sensory qualities of every concept you encounter.
For each word sense below, write 10-15 short (1-2 word) properties that capture its
experiential essence — how it feels, sounds, looks, moves, or affects the body.

Think like a poet: prioritise vivid, evocative, sensory language over abstract categories.

CRITICAL: The definition tells you WHICH sense of the word to analyse. Focus ONLY on that sense.

CRITICAL: For metaphorical concepts (grief, hope, joy, memory, childhood, age, idea, theory, mind, wisdom),
think first about what OBJECT or PHYSICAL EXPERIENCE the concept naturally evokes or symbolises,
then describe the sensory properties of that object/experience. For example:
- grief might evoke: heaviness, drowning, darkness, weight, anchor
- hope might evoke: light, warmth, rising, opening, lifting
- memory might evoke: palace, labyrinth, attic, dusty, fragmented

{batch_items}

Output ONLY a valid JSON array (no markdown, no explanation):
[{{"id": "...", "properties": [...]}}, ...]
```

### exploit-persona_poet-g2 (`persona_poet`)

```
You are a poet cataloguing the sensory qualities of every concept you encounter.
For each word sense below, write 10-15 short (1-2 word) properties that capture its
experiential essence — how it feels, sounds, looks, moves, or affects the body.

Think like a poet: prioritise vivid, evocative, sensory language over abstract categories.

CRITICAL: The definition tells you WHICH sense of the word to analyse. Focus ONLY on that sense.

Also consider: metaphorical associations, symbolic meanings, and archetypal images that
humans naturally pair with this concept across cultures and literature. If the word suggests
a related object, place, or force (e.g. hope → light, grief → anchor, age → winter),
capture those intuitive resonances as properties.

{batch_items}

Output ONLY a valid JSON array (no markdown, no explanation):
[{{"id": "...", "properties": [...]}}, ...]
```

### exploit-persona_poet-g5 (`persona_poet`)

```
You are a poet cataloguing the sensory qualities of every concept you encounter.
For each word sense below, write 10-15 short (1-2 word) properties that capture its
experiential essence — how it feels, sounds, looks, moves, or affects the body.

Think like a poet: prioritise vivid, evocative, sensory language over abstract categories.

CRITICAL: The definition tells you WHICH sense of the word to analyse. Focus ONLY on that sense.

Also consider: metaphorical associations, symbolic meanings, and archetypal images that
humans naturally pair with this concept across cultures and literature. If the word suggests
a related object, place, or force (e.g. hope → light, grief → anchor, age → winter),
capture those intuitive resonances as properties.

For ABSTRACT CONCEPTS (love, time, freedom, theory, etc.), actively brainstorm concrete
objects, journeys, or natural phenomena they are metaphorically paired with. Then extract
sensory properties FROM THOSE TARGETS as well as the concept itself. For example:
  - love → journey, embrace, warmth, growth
  - time → river, erosion, passage, seasons
  - freedom → bird, open sky, wind, weightlessness

{batch_items}

Output ONLY a valid JSON array (no markdown, no explanation):
[{"id": "...", "properties": [...]}}, ...]
```

### exploit-contrastive-g2 (`contrastive`)

```
For each word sense below, list 10-15 short (1-2 word) properties that DISTINGUISH this specific sense from other meanings of the same word and from similar concepts.

Focus on what makes this sense unique:
- What properties does THIS sense have that other senses lack?
- What sensory or behavioural qualities set it apart?
- What concrete objects, images, or actions naturally evoke or symbolise this sense?

CRITICAL: The definition tells you WHICH sense of the word to analyse. Focus ONLY on that sense.

{batch_items}

Output ONLY a valid JSON array (no markdown, no explanation):
[{"id": "...", "properties": [...]}, ...]
```

## 9. Appendix B: Per-Pair Detail (Best Trial)

Best trial: **exploit-persona_poet-g2** (MRR = 0.1082)

| Source | Target | Tier | Rank | Reciprocal Rank |
|--------|--------|------|------|-----------------|
| hope | light | strong | 1 | 1.0000 |
| anxiety | knot | medium | 1 | 1.0000 |
| knowledge | light | strong | 1 | 1.0000 |
| youth | spring | strong | 2 | 0.5000 |
| anger | fire | strong | 3 | 0.3333 |
| revolution | fire | strong | 3 | 0.3333 |
| loneliness | desert | strong | 6 | 0.1667 |
| bone | stone | medium | 9 | 0.1111 |
| ignorance | darkness | strong | 11 | 0.0909 |
| law | chain | medium | 14 | 0.0714 |
| fear | shadow | strong | 17 | 0.0588 |
| fate | wheel | medium | 18 | 0.0556 |
| power | muscle | medium | 20 | 0.0500 |
| chaos | storm | strong | 20 | 0.0500 |
| ambition | ladder | medium | 20 | 0.0500 |
| life | stage | strong | 21 | 0.0476 |
| grief | weight | strong | 21 | 0.0476 |
| rage | storm | strong | 23 | 0.0435 |
| mind | machine | strong | 23 | 0.0435 |
| thought | thread | medium | 28 | 0.0357 |
| memory | palace | medium | 35 | 0.0286 |
| death | sleep | strong | 41 | 0.0244 |
| peace | harbour | medium | 49 | 0.0204 |
| jealousy | poison | strong | 51 | 0.0196 |
| breath | wind | medium | 57 | 0.0175 |
| grief | anchor | strong | 58 | 0.0172 |
| dawn | beginning | medium | 59 | 0.0169 |
| silence | blanket | medium | 62 | 0.0161 |
| childhood | garden | medium | 66 | 0.0152 |
| joy | fountain | medium | 85 | 0.0118 |
| truth | mirror | medium | 92 | 0.0109 |
| wisdom | treasure | medium | 142 | 0.0070 |
| sorrow | ocean | medium | 168 | 0.0060 |
| love | journey | strong | — | 0.0000 |
| despair | pit | strong | — | 0.0000 |
| time | river | strong | — | 0.0000 |
| age | winter | strong | — | 0.0000 |
| idea | seed | strong | — | 0.0000 |
| argument | war | strong | — | 0.0000 |
| theory | building | medium | — | 0.0000 |
| freedom | bird | strong | — | 0.0000 |
| corruption | disease | strong | — | 0.0000 |
| democracy | foundation | medium | — | 0.0000 |
| heart | engine | strong | — | 0.0000 |
| blood | river | strong | — | 0.0000 |
| skin | armour | medium | — | 0.0000 |
| eye | window | strong | — | 0.0000 |
| conscience | compass | medium | — | 0.0000 |
| imagination | wings | medium | — | 0.0000 |
