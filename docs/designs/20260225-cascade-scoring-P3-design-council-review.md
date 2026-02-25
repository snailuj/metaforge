# Gemini 3 Flash Preview
*2026-02-25T07:35:54.674Z*

The Council has completed its review of your Technical Design and Implementation Plan for the Discriminative Evals. We are pleased with the progression; incorporating the +0.5 margin and POS-specific logic addresses several immediate concerns regarding gate precision.

Our consensus is that the shift from pure MRR to a three-tier discriminative framework is the correct architectural move. This transition allows you to measure **structural quality** (how well the system separates metaphors from synonyms) independently of gold-standard matching.

To ensure this evaluation harness remains robust as you scale, the Council recommends the following synthesis of adjustments to your implementation plan:

### 1. Refinement of Tier 2 Metrics (Structural Discrimination)
While your current metrics are a good start, they risk becoming "circular" if the production API already uses domain distance as a gate.

- **Shift to Rank-Based Separation:** Instead of relying solely on `median_score_ratio` (which can be unstable if score scales shift), implement an **AUC-style rank separation**. This measures the probability that a random cross-domain candidate outranks a random same-domain candidate for the same source word. This is more stable across different embedding versions.
- **Symmetric Ambiguity:** Your current thresholds (same <0.3, cross >0.5) leave a narrow "don't know" zone. We recommend making this symmetric (e.g., same <0.3, cross >0.7) or utilizing word-dependent quantiles to ensure you are measuring a clean mechanism check rather than noise.
- **Expand Synonym Detection:** Relying strictly on WordNet synsets might under-count "contamination." Consider adding a basic normalization layer (lowercase, simple lemmatization) and including WordNet’s `similar_to` lemmas to ensure near-synonyms don't masquerade as valid cross-domain metaphors.

### 2. Source-Word Selection & Polysemy Logic
Your current SQL selection favors words with many properties, which unintentionally biases the evaluation toward highly polysemous words.

- **POS Stratification:** Ensure your selection includes a fixed quota (e.g., 20 Nouns, 15 Verbs, 15 Adjectives) to ensure Tier 2 remains stable across the lexicon.
- **Primary Synset Focus:** To avoid the "rock" problem (stone vs. music), modify `select_source_words` to focus on the **primary synset** (lowest synset index) for each lemma. This ensures the evaluation probes are distinct and not a muddy mix of multiple senses.

### 3. Implementation and Workflow Integration
To keep the codebase lean and the developer experience high, we suggest the following structural tweaks:

- **Unify the Harness:** Rather than a standalone script, fold the discriminative logic into `evaluate_mrr.py` via a `--discriminative` flag. This allows you to share DB connections and output a unified JSON result (`{"mrr": ..., "discrimination": ...}`).
- **Mechanism Regression Testing:** To ensure Tier 2 isn't just a "gate check," consider adding a temporary API parameter to toggle domain gating. This allows the eval to compare **Mode A (No Gate)** vs. **Mode B (Production)** to see the true delta your logic provides.
- **Handle Missing Distances:** Ensure `classify_by_domain` explicitly handles `None` or missing distance values by excluding them from the counts, rather than defaulting them to 0 (which would falsely inflate "same-domain" counts).

### 4. Tier 3 (LLM Judge) Guardrails
While implementation is deferred, prepare the ground now by ensuring the judge is **blinded**. When you implement the Claude/GPT calls, do not pass the internal composite scores or tier labels. The judge should only see the source, the vehicle, and the mapping to provide an unbiased aptness score.

### Actionable Next Steps
- **Task 1 & 2:** Proceed with the TDD approach but implement the **rank-based separation** as the primary Tier 2 metric.
- **Task 3:** Adjust the SQL query for source word selection to include **POS quotas** and **synset capping**.
- **Output:** Enhance the JSON output to include `git_commit`, `api_version`, and a **distance histogram**. This will make it easier to identify embedding drift over time.

**The Council approves the design subject to these refinements.** Your plan to prioritize tests and use a pure Python implementation is excellent for maintainability. We look forward to seeing the first batch run results once the "Physical" vs "Relational" property split is complete.