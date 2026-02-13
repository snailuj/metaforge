# Metaphor Vehicles (Source Concepts)

Extracted from the LCC Metaphor Dataset (Mohler et al. 2016, CC-BY-NC-SA 4.0).

## What This Is

108 source concept categories that represent **generic metaphor vehicles** — the
concrete domains humans map abstract concepts onto. Examples: FIRE, DISEASE,
JOURNEY, MACHINE, ABYSS, PLANT, ANIMAL, BODY_OF_WATER.

These are domain-independent. While the LCC dataset pairs them with political/
economic targets (POVERTY, DEMOCRACY, TAXATION), the vehicles themselves appear
across all metaphorical reasoning: emotions, cognition, time, body, society.

## Why They Might Be Useful

1. **Intermediate stepping-stones for metaphor discovery.** Given a source word
   like "anger", an enrichment prompt could first identify which vehicle category
   applies (FIRE, NATURAL_PHYSICAL_FORCE) and then use that to guide property
   extraction. This could improve the metaphor bridge between abstract source
   and concrete target.

2. **Structured exploration of the metaphor space.** Instead of hoping prompts
   stumble onto the right sensory terrain, we could explicitly enumerate which
   vehicle categories a concept maps to, then extract properties from those
   vehicles. This turns implicit metaphorical reasoning into explicit two-hop
   inference: concept → vehicle category → sensory properties.

3. **Validation and tier assignment.** If a metaphor pair's source concept maps
   to a well-attested vehicle category (high frequency in LCC), that suggests
   it's a culturally robust metaphor (strong tier). Low-frequency or absent
   mappings suggest novel/weak metaphors.

4. **Prompt engineering.** Vehicle categories could be injected into enrichment
   prompts as hints: "Consider whether this concept maps to any of these
   metaphorical domains: FIRE, JOURNEY, MACHINE, PLANT..."

## Source

- Repository: https://github.com/lcc-api/metaphor
- Paper: Mohler et al. (2016), "Introducing the LCC Metaphor Datasets", LREC
- Licence: CC-BY-NC-SA 4.0
- Extracted from: `en_large.xml` (167,479 instances, 51,324 CM annotations)
- Filter: CM score >= 2.0 (annotator-confirmed metaphorical mapping)
