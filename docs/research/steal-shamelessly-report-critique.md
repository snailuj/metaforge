
## Critique Introduction
"Stealing Shamelessly for Metaphor Generation" is a technical analysis proposing a complete architectural overhaul of the Metaforge pipeline by integrating techniques from over a dozen state-of-the-art papers.

### 1. Key Structural Issue Finding
The proposal "Stealing Shamelessly for Metaphor Generation" attempts to merge two fundamentally opposing mathematical models of semantics: Ortony Salience Imbalance and Latent Relational Analysis, without actually resolving their structural conflict.

The weakness here is that the document treats these distinct theories as additive features, essentially throwing them into the same weighted sum equation. Whereas they actually require completely different data structures.

- Ortony is looking at physical traits. It looks for properties and inherent to the object itself. Like the classic volcano example, is it hot? Is it explosive? It's very noun-centric.
- Turney's LRA, which the author explicitly wants to steal to boost performance, relies exclusively on *relational similarity*, meaning it cares about the analogies between word pairs, not the words themselves.

#### 1A: Impedance Mismatch
Metaforge cannot simply sum a property salience score and a relational vector score. High quality relational mappings *rely on suppressing* specific attributional properties to work. The two cancel each other out. Optimizing for Ortony's Salience Imbalance, which demands highly salient vehicle properties, inherently penalizes the relational similarity if that mapping requires abstracting away from those physical traits.

**Mismatch:** *Mixing salience and relational signals breaks pipeline.*

#### 1B: Architectural Guidance
**Suggestion:** hierarchically subordinate one model to the other. Do not use a flat weighted composite score. The pipeline must choose a primary driver for the logic of the metaphor.

##### Option 1B.1
Implement a switching mechanism based on the concept of a Schema Grammar from the Visual Metaphor Transfer section. If the grammar detects a strong relational invariant like a clear causal structure, the system should just bypass the Ortony scoring entirely. Effectively, we then let the relation drive and leave the attributes behind.

##### Option 1B.2
Just do not calculate them simultaneously:
1. Apply LRA *first* to generate a candidate set based purely on analogy.
2. Use Ortony Salience Imbalance strictly as a post-ranking filter to ensure the vehicle is concrete enough.

### 2. Franken-Scoring
The proposed scoring function creates a brittle Frankenstein metric by linearly combining disparate signal types.

#### 2A: Fragility
The Appendix section suggests multiplying or summing scores from affective alignment, concreteness differentials, Selectional Preference Violation (SPV), and domain distance. This assumes perfect data availability across all those databases.

**Fragility:** A single noisy signal like a missing entry in the NRC lexicon or an SPV parser error can return zero and unfairly penalize a brilliant metaphor. Legacy lexicons have massive gaps.

#### 2B: Architectural Guidance
Move from a single composite score to a cascading filter architecture like a gate and rank system. Instead of a massive equation, use the signals as binary gates at the retrieval stage.

##### Option 2B.1: Example Scoring
Take the concreteness differential and affective alignment:
- If the concreteness of the target is greater than the concreteness of the vehicle (assessing whether to explain something simple with something abstract, ie, the opposite of how a good metaphor works), you discard it immediately.
    - Don't score it. Don't weigh it. It's a hard fail.
    - **General rule:** *Thin the herd before the expensive calculations.*
- For fragile metrics like SPV:
    - Use SPV only for the final ranking of the top 10 candidates.
    - **General rule:** *Apply the most fragile metrics last, only on the survivors.*
- For manual formulas: tuning coefficients like multiplying sentiment by 0.5 is  arbitrary. Instead of a manual formula, train a small regression model using the human ratings from **Automatic Scoring of Metaphor Creativity with LLMs** (Beaty et al., 2024, Psychology of Aesthetics, Creativity, and the Arts). Let the model learn the optimal weights of these features dynamically.

### 3. Evals for Longtail Creativity
There's a critical misalignment between the goal of longtail creativity and the continued reliance on MRR as a primary KPI.

The document correctly identifies that MRR against a static 274 pair gold standard suppresses creativity, but the proposal still frames success as rescuing the MRR.

#### 3A: MRR Should Decrease
Successfully implementing dynamic buckets to reward unique *non-cliche* metaphors means that MRR against a fixed list will **actually decrease**.

**Falling MRR:** If the system generates novel metaphors -- not present in the ground truth -- the MRR metric sees that as a miss. Metaforge cannot optimize for novelty and matching the answer key at the same time.

#### 3B: Architectural Guidance
Explicitly decouple the engineering optimization from the creative evaluation. Do not eval for MRR and start optimizing for *discriminative aptness*.

##### Option 3B.1: Discriminative Aptness
Adopt discriminative evaluation referenced in MUNCH as the primary metric.
- Train a discriminator specifically on the **inapt negative controls** from the MUNCH data set.
- Define success not as matching the gold standard, but as statistically significant separation from inapt controls.
- Use the LLM-as-a-judge framework:
    1. Measure the distance between the generated metaphor and the nearest cliche bucket.
    2. Maximise the distance from 1. while *maintaining high Ortony Salience*.

### 4. LLM-Generated Properties
The reliance on LLM-generated properties for the Salience Imbalance would be the single biggest failure point in the new architecture.

Calibration is completely insufficient to fix it. The weak thing here is **LLM reporting bias**.

#### 4A: LLM Reporting Bias
LLMs omit obvious physical norms. The proposal suggests calibrating prompts against McCrae norms, but if the LLM fails to output the word "solid" for "apple", no amount of downstream weighting will fix that.

**Bias:** *Calibration assumes the LLM knows a property* P *and just needs a nudge. Often though,* P *is not known in the discrete sense that we need for autonomy.*

#### 4B: Architectural Guidance
Do not just use LLM extraction. Inject an external knowledge graph before property matching.

##### Option 4B.1: Enforced Taxonomy
- Require the LLM to map *every extracted property* to a specific McCrae style attribute type, like "has surface" or "requires tool" -- a property typing constraint as suggested by **Structure Mapping Engine (SME)** (Section 3) (Falkenhainer, Forbus, & Gentner, 1989)
- If the LLM generates a vague associate (say, "freedom" for "bird")
    - If pipeline cannot retrieve a McCrae type for "freedom", discard property immediately
- **General rule:** filter out the vibes and keep only the physics.
- **General rule (restated):** Only allow properties that fit the psycho linguistic taxonomy to enter the calculation.

This solves the garbage in garbage out problem that the current strategy overlooks.

### 5. Recap
1. Decide between relational and attributional models. Don't mix them blindly. Use a switching mechanism or a sequence.
2. Replace the linear scoring composite with a cascade filter. Use Concreteness and Affect as strict gates early on.
3. Abandon MRR in favor of discriminative aptness using MUNCH inapt controls.
4. Enforce strict McCrae typing on LLM properties to ground hallucinations.

### 6. Final Words
- The instinct to grapple with these specific papers to fix the Metaforge pipeline is solid.
- The combination of Visual Transfer Schemas with text is highly original.

The integration just needs to be surgical, not additive. Building a precision instrument, not a smoothie.

Please submit the revised architectural diagram for a follow-up critique.