# Gemini 3 Flash Preview
*2026-02-24T12:58:48.120Z*

The Council has reviewed your documentation and the current trajectory of your NLP app’s data curation redesign. There is a strong consensus that your move from a monolithic "Franken-score" to a **Cascade Architecture (Retrieve → Gate → Rank → Re-rank)** is a significant engineering upgrade. By isolating variables and utilizing cheap, high-signal filters early in the pipeline, you are aligning your technical implementation with cognitive reality.

However, the Council has identified several critical areas where your current roadmap requires refinement to avoid brittleness and silent failures.

### 1. Refining the Concreteness Gate (P2 Implementation)
The shift to using **Brysbaert concreteness norms** as a directional gate (Vehicle must be more concrete than Target) is theoretically sound, but the Council warns against a rigid SQL implementation.

- **The Margin Requirement:** A strict `>=` gate is too unforgiving and may cause significant false negatives. We recommend implementing a **soft margin**. Instead of `V >= T`, use `Vehicle_Concreteness + 0.5 >= Target_Concreteness`. This allows for horizontal conceptual mapping while still filtering out severe inversions (e.g., trying to explain "fire" using "anger").
- **Aggregation Strategy:** Currently, you are using the **mean** of lemma scores to represent a synset. The Council suggests experimenting with **Max Concreteness** for vehicles. Metaphors often rely on the most tangible sense of a word; using a mean may unfairly penalize a concrete vehicle because it has secondary abstract senses.
- **POS Sensitivity:** Concreteness norms are most reliable for nouns. Consider applying the hard gate primarily to **Noun-Noun** mappings and treating it as a "soft prior" for adjectives and verbs, where semantic boundaries are more fluid.

### 2. Solving the "Reporting Bias" in LLM Property Extraction
While your roadmap pushes back on the critique’s demand for strict physical typings, the Council agrees that **LLM Reporting Bias** is a legitimate threat. LLMs often omit "obvious" physical traits (e.g., that an apple is solid) in favor of more "interesting" abstract traits.

- **Dual-Prompt Strategy:** To ensure your **Ortony Salience** calculations are grounded, update your extraction pipeline to hit the LLM twice per synset. One prompt should focus exclusively on **Sensory/Physical/Taxonomic** properties (The Physics), and the second on **Abstract/Functional/Relational** properties (The Vibes).
- **The "is_physical" Flag:** Store these separately. A high-quality metaphor vehicle usually requires at least one overlapping physical trait and one relational trait to bridge the gap between "grounded reality" and "creative leap."

### 3. Transitioning Metrics: From MRR to Discriminative Aptness
The Council applauds your realization that **Mean Reciprocal Rank (MRR)** is a regressive metric for creativity. If you optimize for MRR against a static list of "classic" metaphors, you are effectively optimizing for clichés.

- **MRR as a Guardrail:** Continue tracking MRR on your 274-pair gold standard, but treat it as a **regression test** only. Its job is to ensure you haven't broken the system's ability to find "expected" results.
- **Aptness as the North Star:** Your primary KPI should shift to **Discriminative Aptness** (using MUNCH-style controls). Success should be measured by the system's ability to statistically distinguish an "apt" metaphor from a "munch/inapt" control. 
- **Novelty Buckets:** To prevent the system from recycling the same 50 vehicles, implement a **Novelty Proxy**. Track the "bucket rarity" of your generated metaphors. If the system starts generating highly apt but rare mappings, your "Quality" metric should increase even if MRR stays flat.

### 4. Technical Implementation and Scalability
From a systems architecture perspective, your "Steal Shamelessly" branch is moving in the right direction, but watch for the following:

- **Handling Data Gaps:** Your "fail-open" strategy (passing through if Brysbaert data is null) is correct for preserving recall. However, you must implement **telemetry** to track how often this happens. If more than 20% of your candidates are bypassing the gate, you should prioritize building the **FastText regression model** to fill those gaps.
- **Relational Impedance:** Integrating **Latent Relational Analysis (LRA)** later will be difficult if your current data structures only support flat properties. Ensure your Go structs or DB schema can handle **triples** (Source-Relation-Target) now, even if you don't populate them until P5 of the roadmap.
- **SQL Efficiency:** As you add joins for concreteness, salience, and domain distance, watch for N+1 query patterns. Use bulk operations and consider caching high-frequency synset scores in Redis to keep the "Gate" stage truly "cheap."

### Final Conclusion
The Council **approves** of your direction. You are successfully moving from distributional math to a pipeline that mimics human cognitive processing. By softening your gates, dual-prompting for physical properties, and decoupling "Aptness" from "Cliché-matching," you will build a much more resilient engine.

**Immediate Actions:** 
1. Implement the **+0.5 margin** on the concreteness gate. 
2. Add **POS-specific logic** to the gating stage. 
3. Split your **property extraction prompts** into "Physical" and "Relational" passes. 
4. Build the **Discriminative Evaluation harness** to replace MRR as your primary success metric.