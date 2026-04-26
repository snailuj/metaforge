# Decisions Register

<!-- Append-only. Never edit or remove existing rows.
     To reverse a decision, add a new row that supersedes it.
     Read this file at the start of any planning or research phase. -->

| # | When | Scope | Decision | Choice | Rationale | Revisable? | Made By |
|---|------|-------|----------|--------|-----------|------------|---------|
| D001 |  | architecture | Backend language and framework | Go with chi router — stateless headless API, single binary | Self-hostable requirement demands minimal dependencies. Go compiles to a single binary with no runtime. Chi is lightweight and idiomatic. Stateless design means horizontal scaling is trivial. | Yes | human |
| D002 |  | architecture | Frontend framework | Lit + Vite + TypeScript with Shadow DOM web components | Browser-first, no React/Vue overhead. Lit web components are standards-based and lightweight. Shadow DOM provides style encapsulation. Vite for fast dev iteration. | Yes | human |
| D003 |  | architecture | Data storage | SQLite embedded database — no external DB services | Self-hostable requirement. SQLite is zero-config, ships with the binary. Read-heavy workload is ideal for SQLite. DB binary is gitignored; SQL text dumps committed for reproducibility. | Yes | human |
| D004 |  | library | Word embeddings model | FastText wiki-news-300d-1M for word vector similarity | Pre-trained, well-understood, handles out-of-vocabulary words via subword information. 300 dimensions is a good balance of quality and storage. Used for property snapping and semantic similarity. | Yes | human |
| D005 |  | architecture | Semantic property extraction | Claude (Sonnet) for LLM-extracted properties — 10-15 per synset | Properties are the backbone of the Metaphor Forge. LLM extraction captures nuanced semantic dimensions (physical, emotional, functional) that static databases lack. Claude chosen for quality and cost balance. | Yes | human |
| D006 |  | library | 3D graph visualisation library | 3d-force-graph (Three.js-based) for WebGL force-directed graph rendering | Mature library with good performance. Handles large node counts. Physics simulation feels right for the Visual Thesaurus successor experience. Ships inaccurate .d.ts — needs local module declaration override. | Yes | human |
| D007 |  | convention | Language convention | UK English spelling throughout (optimise, colour, etc.) | Project owner preference. Consistency across code, docs, and UI copy. | Yes | human |
