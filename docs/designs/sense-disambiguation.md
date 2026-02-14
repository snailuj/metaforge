# Sense Disambiguation — Design Note

> Captured from conversation 2026-02-14, after deploying curated property vocabulary.

## The Problem: Sense Collapse

The current architecture resolves a word to a single synset and returns matches based on that one sense's properties. Example: querying "fire" resolves to synset 21097 — "go off or discharge" (the firearms sense). Properties are all about gunshots (percussive, recoiling, explosive), and matches are predictably in the same domain — "burst" as in firearms discharge, "bang" as in violent closing.

None of the poetic/metaphorical senses of fire come through — heat, light, passion, destruction, flickering, consuming. Those live on different synsets.

This isn't just a metaphor-generator problem. The thesaurus IS the product — people come for the thesaurus and the force graph. If "fire" shows up with the wrong sense's frequency ranking, that's the core lookup being wrong, not an edge case. A thesaurus that doesn't know combustion-fire is more common than firearms-fire isn't shiny, it's broken.

## SUBTLEX Limitation

SUBTLEX is surface-form frequency — "fire" gets one count regardless of whether it meant combustion or gunfire or termination. Even with perfect sense disambiguation everywhere else, you can't frequency-rank *senses* from SUBTLEX alone.

## Architectural Approaches (No Hand-Curation)

The sense structure is already in WordNet — you don't need to curate it, you need to *use* it.

### 1. Multi-sense fan-out at query time

Instead of resolving "fire" to one synset, query ALL synsets for the lemma, collect their property bags, and return grouped results. The frontend shows sense clusters: "fire (combustion)", "fire (discharge)", "fire (terminate)". User picks, or browses all. Zero curation — it's just a different query shape.

### 2. Property union with provenance

Merge properties across all senses into one fat bag, but tag each with which sense(s) contributed it. "Dangerous" comes from 3 senses, "flickering" from 1. Shared-across-senses properties are the *core* of the word; sense-specific ones are the interesting metaphor fuel. Again, algorithmic — no hand-curation.

### 3. Context-driven auto-disambiguation

In forge mode you have TWO words. Use the target's properties to pick which sense of the source is most relevant — the sense whose property bag overlaps most with the target. "Fire" + "passion" -> combustion sense. "Fire" + "gun" -> discharge sense. The data does the work.

### 4. Frequency-weighted default sense

Use familiarity data to rank senses, so the most common sense surfaces as default. Combustion-fire would beat firearms-fire for most users.

## Sense-Level Familiarity Sources

Since SUBTLEX can't give sense-level familiarity directly, these alternatives exist:

- **WordNet's own sense ordering.** Synsets are already ordered by frequency (SemCor corpus annotations). Sense 1 of "fire" is combustion, not firearms. Coarse and dated, but free and already in the data.
- **SemCor sense-tagged frequencies.** ~234k manually sense-tagged tokens from Brown corpus. Small, but gives per-sense frequency directly. NLTK bundles it — cross-reference in the pipeline without any new curation.
- **Word Sense Disambiguation models.** Run a pretrained WSD model (e.g. EWISER, or BERT-based) over a large corpus, count sense occurrences in the output. Automated sense-level frequency at scale.
- **Distributional proxy.** Use FastText embedding distance between a lemma and its synset's definition/gloss as a rough proxy for "how central is this sense." The sense whose definition is closest to the bare word embedding is probably the dominant sense. Hacky, but cheap and automatic.

## Status

Parked. Worth a deliberate pass post-MVP. The data sources exist, the pipeline architecture can accommodate it, and it doesn't require hand-curation.
