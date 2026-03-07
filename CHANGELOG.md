# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Added
- Physical coverage audit script with POS-dependent thresholds (nouns >= 4, verbs >= 2, adjectives >= 2)
- Gap-fill pipeline — targeted second-pass LLM enrichment for flagged synsets (4,496 synsets across 3 rounds)
- Purpose-framed v2 enrichment prompt (+43% physical properties, A/B tested)
- `--retry` and `--retry-window` flags for unattended overnight enrichment runs
- `--offset` flag for frequency-ranked enrichment (continue from where you left off)
- Multi-word/hyphenated property rejection in pipeline validation (96.3% single-word compliance)
- 7k synsets enriched with purpose-framed prompt, nouns avg 5.0 physical props
- Concreteness regression with 4-model shootout (k-NN r=0.91, 68.8% coverage)
- SVR subsampling for large training sets (svr_max_samples param)
- Discrimination eval with rank AUC metric (AUC 0.5994 at 6.5% coverage)
- P2 concreteness gate with soft margin +0.5 and noun-noun POS gate
- Brysbaert concreteness ratings import (max aggregation per synset)
- Concreteness telemetry — startup coverage + POS bypass logging
- Cross-domain metaphor scoring with cascade pipeline
- P1 salience imbalance scoring in forge cascade
- Curated property vocabulary with WordNet-derived canonical entries
- Property snapping — 3-stage cascade (exact, morphological, cosine similarity)
- Enrichment schema v2 — structured properties with domain and salience
- Enrichment pipeline with Claude LLM extraction (3,530 synsets enriched)
- FastText 300d embedding similarity in forge scoring
- VerbNet classes, roles, and examples import
- SyntagNet collocation pairs import
- OEWN core data import (synsets, lemmas, relations)
- SUBTLEX-UK frequency data with rarity tier classification
- Forge tier classification and HTTP handler with threshold/limit
- Thesaurus data layer with GetLookup function
- Core thesaurus search endpoint (HandleLookup)
- Fluent strings endpoint for localisation
- CORS middleware and route wiring
- 3d-force-graph wrapper with fly controls and click navigation
- Vite + Lit + TypeScript frontend scaffold
- API client with lookupWord fetch wrapper
- Graph data transform with dedup, priority tiers, and node cap
- Staging deployment at metaforge.julianit.me
- evals.sh wrapper for concreteness regression CLI
- Changelog and backlog tracking system (GitHub Issues + Keep a Changelog)

### Changed
- Unified checkpoint and enrichment JSON formats (single `{"synsets": [...]}` shape)
- `enrich.sh --from-json` now produces API-ready DB (imports Brysbaert + runs concreteness fill)
- Enrichment schema v2 replaces flat property text with structured domain/salience
- GetForgeMatches mega-query replaces N+1 handler loop
- Normalised distances for tier classification

### Fixed
- RateLimitError now breaks enrichment batch loop instead of continuing
- Cosine distance clamping to [0,1] in CompositeScore
- Deterministic lemma SQL ordering
- Input normalisation for forge queries
- argparse --verbose flag rejected after subcommand
- FastText dimension validation on load
- Streaming lemma query in store_lemma_embeddings (OOM prevention)
- Structured logging for GetLemmaEmbedding graceful degradation paths
- Missing table validation and 404 vs 500 distinction in HandleSuggest

### Removed
- Stale `.planning/` directory (auto-generated, superseded by CLAUDE.md)
- Dead IDF, similarity, and centroid computation code
- Dead property_similarity, synset_centroids tables and idf column
