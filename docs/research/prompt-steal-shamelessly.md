# Research Prompt: Steal Shamelessly

## Context — What We've Built (and Where We're Stuck)

Metaforge is a metaphor generation engine. Given "anger", it suggests metaphorical vehicles like "fire", "storm", "volcano". The pipeline:

- **Data**: 20k WordNet synsets enriched with LLM-extracted semantic properties (~11 properties/synset). Properties snapped to a 35k-entry curated vocabulary.
- **Matching**: Find synsets sharing properties with the query synset, filtered to different semantic domains (FastText cosine distance > threshold).
- **Scoring**: Composite of shared property count + IDF-weighted overlap + domain distance + antonym contrast.
- **Evaluation**: MRR against 274 known metaphor pairs. Current score: **0.034** (average rank ~29 for a known target).

### Where we're stuck

Our MRR is low. Recent experiment: clustering synonymous vocabulary entries (e.g. "heavy"/"weighty" → same cluster_id) to enable fuzzy property matching. **Result: MRR dropped from 0.034 to 0.025.** Clustering lost 18 previously-found pairs and gained zero new ones. The deduplication reduced unique property-synset links from ~217k to ~180k, killing signal.

We need fresh ideas. I want to find **any system, paper, or technique** that does metaphor generation, metaphor ranking, or metaphor quality scoring — and mine it for ideas we can adapt.

## What I Need

### 1. Metaphor Generation Systems

Find every system that generates metaphorical language or suggests metaphorical mappings. For each:
- What's the input? (word, sentence, concept pair, topic?)
- What's the output? (single metaphor, ranked list, generated text?)
- What's the core algorithm? (retrieval, generation, knowledge graph traversal, neural, hybrid?)
- How do they score/rank candidates?
- What evaluation did they use? What scores did they achieve?
- **What can we steal?** Specific techniques, scoring functions, data sources, evaluation methods.

### 2. Metaphor Quality / Aptness Scoring

Find work on quantifying how "good" a metaphor is. Terms to search: metaphor aptness, metaphor quality, metaphor conventionality, metaphor novelty, metaphor comprehensibility.
- What features predict metaphor quality?
- Are there any scoring functions we could adapt?
- How do they handle the tension between novelty (distant domains) and comprehensibility (some shared structure)?
- Do any of these map onto our composite scoring components?

### 3. Cross-Domain Semantic Similarity and Transfer

Find work on computing similarity or relatedness between concepts in *different* domains, especially:
- Analogical reasoning systems (A:B :: C:D) — metaphor is a form of analogy
- Structure Mapping Engine (SME) and its descendants
- Relational similarity (Turney's work)
- Word analogy methods that go beyond word2vec arithmetic
- Knowledge graph approaches to cross-domain mapping

### 4. Property/Feature Norms in NLP

Find computational work using semantic property norms or feature-based representations:
- McRae feature norms, CSLB norms, Binder et al. conceptual features
- LLM-extracted features/properties for downstream tasks
- Any comparison of hand-normed vs LLM-extracted properties
- Feature-based similarity metrics (Tversky's contrast model, etc.)
- **Critical**: Has anyone found that property overlap correlates with metaphor quality?

### 5. Evaluation Methods and Datasets

Find metaphor evaluation resources:
- Datasets of metaphor pairs with quality ratings
- Benchmarks for metaphor generation
- Evaluation metrics beyond MRR (human judgement, aptness ratings, creativity scores)
- How do other systems handle the long-tail problem? (Many valid metaphors aren't in any gold standard)

### 6. Alternative Scoring Signals

Our current signals are: property count, IDF-weighted overlap, domain distance, antonym contrast. What else could we add?
- Concreteness differential (abstract source → concrete target is more prototypically metaphorical)
- Imageability scores
- Emotional valence alignment/contrast
- Frequency of metaphorical usage in corpora
- Distributional features (do the words co-occur in metaphorical contexts?)
- Graph-based features from WordNet (path length, LCS depth)
- Selectional preference violation (Wilks 1978)

## Output Format

For each finding, provide:
- **Paper/system**: Name, authors, year, venue
- **Relevance**: How directly this applies to our system (high/medium/low)
- **Key idea**: The one technique or insight we should pay attention to
- **Steal potential**: What specifically we could adapt, and how it might plug into our pipeline
- **Link/DOI**: If available

Organise by section (1–6 above), then by relevance within each section.

## Search Guidance

Start broad, then narrow. Check:
- **ACL Anthology** (aclweb.org) — the motherlode for NLP metaphor work
- **Semantic Scholar** — for citation graphs and related work chains
- **Google Scholar** — for older cognitive science work
- **arXiv** — for recent preprints
- **ICCC** (International Conference on Computational Creativity) — metaphor as creative generation

Key search queries:
- "metaphor generation system"
- "computational metaphor" ranking OR scoring OR quality
- "cross-domain" metaphor mapping
- "property norms" metaphor
- "semantic features" metaphor aptness
- "analogical reasoning" NLP
- "structure mapping" computational
- "metaphor detection" (detection papers often contain generation insights)
- "conceptual blending" computational
- LLM metaphor generation OR extraction

Chase citation chains: when you find a relevant paper, check both its references and what cites it.

## Constraints

- Don't stop at 2020. Check 2021–2026 for LLM-era work that may have changed the landscape.
- Include negative results — papers that tried property-based approaches and found them insufficient are just as valuable.
- If a system has a public implementation or dataset, note that explicitly.
- Prioritise work with empirical evaluation over pure theory.
