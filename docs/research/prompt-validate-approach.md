# Research Prompt: Validate Our Approach

## Context — What We've Built

Metaforge is a metaphor generation engine. Given a source concept (e.g. "anger"), it suggests cross-domain metaphorical vehicles (e.g. "fire", "storm", "volcano"). The core mechanism:

1. **Property extraction**: An LLM (Claude) extracts 10–15 semantic properties per WordNet synset (e.g. for "fire": destructive, consuming, hot, spreading, luminous, transformative).
2. **Vocabulary normalisation**: ~15k raw LLM-extracted properties are snapped to a curated vocabulary of ~35k canonical terms (built from WordNet's least-polysemous lemmas) via a 3-stage cascade: exact match → morphological normalisation → embedding cosine similarity → drop.
3. **Cross-domain matching**: For a query word, we find its synset(s), retrieve their snapped properties, then find other synsets sharing properties — filtering to ensure source and target are in *different* semantic domains (measured by FastText cosine distance between synset centroids).
4. **Composite scoring**: Matches are ranked by a weighted composite of (a) shared property count, (b) IDF-weighted property overlap, (c) FastText domain distance, and (d) antonym contrast bonus.
5. **Evaluation**: We measure Mean Reciprocal Rank (MRR) against a hand-curated set of 274 known metaphor pairs (e.g. anger→fire, time→river, hope→light) across 10 thematic categories.

Current MRR: **0.034** (i.e. on average, a known metaphorical target appears around rank 29). We have 20k synsets enriched with properties from ~220k synset-property links.

## What I Need Researched

### Primary question: Is property-based cross-domain metaphor generation an established approach, a novel approach, or a known dead end?

Specifically:

1. **Conceptual Metaphor Theory (CMT) in computation**: Lakoff & Johnson (1980) proposed that metaphors are systematic mappings between conceptual domains. Has anyone *computationally implemented* CMT-style cross-domain property mapping for metaphor generation or detection? Not just cited CMT as motivation — actually built a working system that maps properties/features between domains.

2. **Property/feature-based metaphor models**: Has anyone used semantic property norms (like McRae et al. 2005, CSLB, or Binder et al. 2016) or LLM-extracted properties to compute metaphor quality or generate metaphors? Our approach extracts properties via LLM rather than using hand-normed datasets — is that novel, or has it been done?

3. **Cross-domain transfer as a metaphor signal**: We use embedding distance between source and target as a *positive* signal (more distant domains = more metaphorical). Is this established in the literature? What's the theoretical and empirical support for "domain distance correlates with metaphor quality"?

4. **Vocabulary-based property matching**: We normalise free-text properties to a controlled vocabulary before matching. Has anyone done this for metaphor computation specifically? How does it compare to embedding-based soft matching of raw properties?

5. **The "shared property overlap" mechanism**: Our core signal is literally "count how many properties two concepts share, weighted by IDF". Is this mechanism used anywhere in computational metaphor work? How does it relate to similarity-based models of metaphor (Gentner's Structure Mapping Theory, Turney's SuperSIM, etc.)?

### Secondary questions:

6. What are the known **failure modes** of property-based approaches to metaphor? What do critics say?
7. Are there **hybrid approaches** that combine property overlap with other signals (distributional semantics, knowledge graphs, neural generation)?
8. What **evaluation benchmarks** exist for metaphor generation quality? Is MRR against known pairs standard, or is there something better?

## Output Format

For each finding, provide:
- **Paper/system name** and year
- **How it relates to our approach** (validates, contradicts, extends, or is orthogonal)
- **Key technique** that's relevant
- **What we could learn from it** (if anything)

Group findings by how closely they match our approach:
- **Ring 0**: Direct matches — property-based cross-domain metaphor generation
- **Ring 1**: Close parallels — computational metaphor systems using features, properties, or structured knowledge
- **Ring 2**: Adjacent work — metaphor detection/generation using other methods that could inform our approach
- **Ring 3**: Theoretical foundations — CMT, structure mapping, conceptual blending that ground our approach

## Search Guidance

Key authors to check: Lakoff, Gentner, Turney, Shutova, Veale, Barnden, Fass, Martin, Kintsch, Bowdle & Gentner, Glucksberg, Wilks.

Key venues: ACL, EMNLP, NAACL, COLING, Cognitive Science, Metaphor and Symbol, computational creativity conferences (ICCC).

Key terms: "computational metaphor", "metaphor generation", "conceptual metaphor theory NLP", "cross-domain mapping", "property norms metaphor", "feature-based metaphor", "metaphor quality", "semantic property overlap", "structure mapping engine".

Don't limit to NLP — check cognitive science, computational creativity, and AI/knowledge representation venues too.
