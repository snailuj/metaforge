# Metaforge Data Pipeline Rebuild - Detailed Code Generation Prompt

## Table of Contents
1.  Project Overview
2.  Development Environment
3.  Phase 0: Project Archaeology - Detailed Instructions
4.  Phase 1: Assess - Detailed Instructions
5.  Phase 2: Remix - Detailed Instructions
6.  Phase 3: Scripts & Enrichment Prompt - Detailed Instructions
7.  General Coding and Testing Requirements
8.  Working Style
9.  Deliverables and File Structure

## 1. Project Overview
You will rebuild the data pipeline for **Metaforge**, an educational app (MIT licensed) that gamifies discovery of figurative language (metaphors, word hunt games, metonyms) for Middle Grades students (Grades 4-8). The current pipeline (sch.v1) combines OEWN, GloVe embeddings, and SUBTLEX-UK. The new pipeline (sch.v2) will use `sqlunet` as a foundation, GloVe embeddings (optional), SUBTLEX-UK (optional) plus additional dependencies recommended in the course of this rebuild (optional). This prompt provides detailed instructions for each phase of the rebuild, emphasizing thorough assessment, thoughtful design, and robust implementation. Remember that human-in-the-loop checkpoints are mandatory after each phase.

## 2. Development Environment

*   **Language**: Python 3.9+
*   **Database**: SQLite
*   **LLM**: Gemini Flash 2.5 Lite
*   **Environment**: Production
*   **Dependencies**: Use `pip` to manage dependencies. Specify required packages in a `requirements.txt` file. Use a dedicated `venv` for environment isolation.
*   **Existing Codebase**: Check the existing codebase for patterns, established libraries (e.g., for database interaction, data transformation, logging), and coding conventions. Follow these conventions.
*   **Error Handling**: Implement robust error handling using `try...except` blocks. Log all errors with detailed information, including timestamps and traceback.
*   **Logging**: Use a logging library to record all significant events during data processing, including data validation results, transformation steps, and API calls.
*   **Configuration**: Use environment variables for sensitive information like API keys and database paths. [Illustrative]

## 3. Phase 0: Project Archaeology - Detailed Instructions

**Objective**: Understand the existing data pipeline.

**Output**: `docs/archaeology-report.md` (Markdown format).

**Tasks**:

1.  **Locate Existing Pipeline Work**:
    *   Search for SQL schemas, Python scripts, data processing code.
    *   Identify any documentation about data model decisions.
    *   Find the current enrichment prompt(s) used for LLM calls.
    *   Locate any test data or validation scripts.
2.  **Document the Current State**:
    *   What data sources are currently integrated?
    *   What is the schema structure (sch.v1)? Include a diagram, if available.
    *   How are "surprise" calculations currently performed (semantic distance, ratio of frequencies, etc)
    *   What enrichment fields exist? Provide a detailed description of each field.
    *   What gaps or pain points have been noted? List any known issues or TODOs.
    *   Read git history for information about what was implemented, changed, or dropped. List any significant deviations from plan and outstanding issues.

**`docs/archaeology-report.md` Content Requirements**:

*   Inventory of existing pipeline components with descriptions and file paths.
*   Current schema diagram or detailed description, including table names, column names, data types, and relationships.
*   List of known issues or TODOs extracted from code comments and documentation.
*   Any design rationale found in documentation.

## 4. Phase 1: Assess - Detailed Instructions

**Objective**: Systematically examine each sibling dataset within `sqlunet` and evaluate its potential for Metaforge.

**Data Access**:

*   **Primary**: Query the pre-loaded SQLite database (`sqlunet_master`) at `[PATH_TO_SQLUNET_DB]` [Illustrative].
*   **Reference**: Consult SQL DDL files at `[PATH_TO_SQL_DUMPS]` [Illustrative] for design intent and comments.

**Research Questions for Each Dataset (OEWN, VerbNet, PropBank, FrameNet, SUMO, BNC, ILFwn, GlossLF, XWordNet)**:

**Schema Analysis**:

1.  What datatypes does this dataset contribute? List each table/entity with a brief description.
2.  Why did the creators include this datatype? What linguistic phenomenon does it capture?
3.  What shapes can this data take? (cardinality, optionality, valid values). Provide examples.
4.  Why is it structured this way? What design tradeoffs were made?
5.  How does it link to other tables within the same dataset? Illustrate with examples.
6.  How does `sqlunet` link it to entities in other datasets? Illustrate with examples.

**Data Quality**:

1.  Completeness: What percentage of expected entries are populated? Are there systematic gaps? Quantify where possible.
2.  Correctness: Sample 20 entries [Illustrative] - are they accurate? Document any errors found.
3.  Currency: When was this data last updated? Is the source actively maintained?
4.  Project fit: How directly useful is this data for Metaforge's figurative language goals?

**Metaforge-Specific Questions**:

1.  Does this dataset provide information that could replace or improve our current LLM enrichment? How?
2.  Does it offer semantic/relational data that could improve "surprise potential" calculations? How?
3.  Could it help filter age-inappropriate content for middle grades? How?
4.  Does it provide usage examples or contexts that could seed our LLM few-shot prompts? How?

**Provenance Questions**:

1.  What is the license? Compatible with MIT? Verify.
2.  What is the academic citation / original publication?
3.  Are there known errata or issues documented by the maintainers?
4.  What is the grain of the data: word-level, sense-level, phrase-level, sentence-level?

**Output Format (for each dataset)**:

```markdown
## [Dataset Name]

### Datatypes

#### [Datatype 1 Name]
**Summary** (3-4 sentences): [What this datatype represents, why it exists, its structure, its coverage]

**Key relationships** (2-3 sentences): [How it connects to other datatypes within this dataset and across sqlunet]

#### [Datatype 2 Name]
...

### Quality Assessment
- Completeness: [X%] - [notes]
- Correctness: [X/20 sampled entries accurate] - [notes]
- Currency: [Last updated YYYY] - [actively maintained? Y/N]
- Project fit: [High/Medium/Low] - [rationale]

### Metaforge Relevance
[2-3 sentences on specific value for figurative language discovery]

### Licensing & Provenance
- License: [X] - MIT compatible: [Y/N]
- Citation: [X]
- Known issues: [X]
```

**Self-Verification Loop**:

1.  Query `sqlunet_master` to extract complete list of tables.
2.  Compare against documented datatypes.
3.  For each missing table:
    *   Generate the required summary.
    *   Document why it was initially missed.
4.  Repeat until: `tables_documented == tables_in_database`.
5.  **Escape hatch**: If iteration exceeds 3 cycles, flag remaining gaps for human review rather than continuing indefinitely.

## 5. Phase 2: Remix - Detailed Instructions

**Objective**: Design `sch.v2` that extends `sch.v1` using findings from the Assess phase.

**Strategic Constraints**:

*   Maintain bird's-eye view of how sibling datasets relate.
*   Preserve ability to trace data provenance.
*   Optimise for Metaforge's core operations:
    *   Fast lookup: `lemma` → definition, sense, part of speech, semantic properties, connotations, register, usage example(s)
    *   Surprise calculations, combining
        *   Approach identified in Phase 0 (semantic distance, frequency [Illustrative])
        *   New approaches enabled by `sch.v2` enhancements
    *   Property intersection: `lemma` -> all lemmas sharing properties with `lemma`, sort by `count(shared), surprise_from_source`
    *   Age-appropriate filtering
    *   Metonym/metaphor relationship traversal if available

### Design Questions:

For each candidate data structure from Assess:

**Quality Tradeoffs**:

1.  What advantages would adopting this structure bring to Metaforge's feature-set vs `sch.v1`?
2.  What disadvantages or complications would it introduce?
3.  What quality upsides would the end user (student) notice?
4.  What quality upsides would the developer notice?
5.  What would future open-source maintainers appreciate or struggle with?

**Cost Tradeoffs**:

1.  What is the storage cost of this structure? Estimate based on data volumes.
2.  What is the query complexity cost for common operations?
3.  What is the build-time cost to populate?
4.  What is the expected enrichment cost? Estimate based on 100k synsets, $0.15/1M tokens in, $1.25/1M tokens out
4.  What is the maintenance cost (updates when source datasets change)?

**LLM Enrichment Implications**:

1.  If this structure were included in few-shot examples, how could it improve enrichment consistency?
2.  How could it improve enrichment accuracy?
3.  How could it reduce hallucination risk?
4.  How could it reduce API cost (fewer tokens, better first-attempt accuracy)?
5.  Should the LLM output directly into this schema, or into an intermediate format?

**Integration Questions**:

1.  Can this be populated entirely from `sqlunet` + GloVe + SUBTLEX-UK?
2.  What additional public domain datasets might fill gaps? (Must be actively maintained or demonstrably stable).
3.  What data requires LLM enrichment vs can be derived computationally?

### Output: Discussion Document (`docs/remix-discussion.md`)**:

1.  **Executive Summary**: 1-2 paragraphs on the proposed approach.
2.  **Question Responses**: Structured answers to all `### Design Questions` above.
3.  **Proposed Schema (`sch.v2`)**:
    *   Technical summary (paragraph form, covering design philosophy).
    *   For each datatype:
        *   Name and purpose (3-4 sentences).
        *   Key relationships (2-3 sentences).
        *   Source: which input dataset(s) populate this.
        *   Enrichment required: Y/N and what kind.
        *   Data type of each field.
        *   Constraints on each field (e.g., NOT NULL, UNIQUE).
4.  **Added Dependencies**: Complete list of all public domain datasets (if any)identified in answers to `### Design Questions > Integration Questions > 2.` above.
5.  **Migration Path**: How to move from `sch.v1` to `sch.v2`.
6.  **Open Questions**: Issues requiring human decision.

**Self-Verification Loop**:

1.  Re-read each question from the Design Questions section.
2.  Verify an answer exists in the document.
3.  Verify the answer is supported by findings from Assess phase.
4.  Verify solutions are technically feasible with identified data sources.
5.  Verify all added dependencies are in the public domain, and actively maintained or demonstrably stable.
6.  For each discrepancy, omission, or unsupported claim:
    *   Revise the relevant section.
    *   Document the correction.
7.  Repeat until: no corrections needed in a verification pass.
8.  **Escape hatch**: If iteration exceeds 3 cycles, flag remaining issues for human review.

## 6. Phase 3: Scripts & Enrichment Prompt - Detailed Instructions

**Objective**: Generate implementation artifacts for `sch.v2`.

**Script Requirements**:

1.  **Schema Creation (`scripts/create_schema.sql`)**:
    *   DDL for `sch.v2`.
    *   Include comments explaining design decisions.
    *   Include indexes for common query patterns.
    *   Use appropriate data types for each column.
    *   Enforce constraints (e.g., NOT NULL, UNIQUE, foreign keys).
2.  **Data Import (`scripts/import_data.py`)**:
    *   Ensure Added Dependencies from `## Phase 2: Remix > Output` (if any) are downloaded and the data is accessible to this script.
    *   Read from `sqlunet` SQLite database.
    *   Read from GloVe embeddings file [Illustrative].
    *   Read from SUBTLEX-UK [Illustrative].
    *   Read from Added Dependencies (if any).
    *   Transform and load into `sch.v2`.
    *   Include progress logging.
    *   Implement data validation checks to ensure data integrity during import. Log any discrepancies.
    *   Handle potential data type conversions and data cleaning.
    *   Use parameterized queries to prevent SQL injection vulnerabilities.
3.  **Enrichment Sampling (`scripts/sample_for_enrichment.py`)**:
    *   Select 1000 random lemmas [Illustrative] requiring enrichment.
    *   Stratify by: frequency band, part of speech, current coverage gaps.
    *   Output in format ready for enrichment script (e.g., JSON).
    *   Ensure that the sampling process is reproducible.
4.  **Enrichment Execution (`scripts/run_enrichment.py`)**:
    *   Submit samples to Gemini Flash 2.5 Lite.
    *   Handle rate limiting and retries.
    *   Parse structured responses (e.g., JSON).
    *   Load results into `sch.v2`.
    *   Log failures for human review, including the input lemma and the LLM's response.
    *   Implement error handling for API calls and data parsing.

**Enrichment Prompt Requirements (`prompts/enrichment_prompt.md`)**:

Create `prompts/enrichment_prompt.md` containing the prompt for Gemini Flash 2.5 Lite.

**Prompt Engineering Techniques to Apply**:

*   Clear role and task framing.
*   Explicit output schema with field descriptions (use JSON format).
*   3-5 few-shot examples demonstrating desired output quality.
*   Edge case handling instructions (unknown words, ambiguous cases).
*   Instruction to acknowledge uncertainty rather than hallucinate.
*   Chain-of-thought scaffolding if beneficial for accuracy.
*   Include instructions on how to handle age-inappropriate content.

**Prompt Structure**:

```
[System context: role, task, constraints]

[Output schema definition - use JSON format]

[Field-by-field instructions with examples of good/bad responses]

[Few-shot examples - diverse, covering edge cases]
- Example 1: Common noun
- Example 2: Abstract noun
- Example 3: Verb with multiple senses
- Example 4: Informal/slang term
- Example 5: Word with strong connotation

[Final instructions: format, handling uncertainty, age-appropriateness]
```

**Few-Shot Example Format**:

Each example should show:

*   Input: the lemma and any context from `sch.v2`.
*   Output: complete structured response (in JSON format).
*   (Optional) Brief annotation explaining why this output is correct.

## 7. General Coding and Testing Requirements

*   **Code Style**: Adhere to PEP 8 coding style guidelines. Use `flake8` to enforce code style consistency.
*   **Type Hints**: Use type hints extensively for improved code readability and maintainability.
*   **Docstrings**: Write clear and concise docstrings for all functions and classes, explaining the purpose, arguments, and return values. Focus on explaining "why" rather than "what."
*   **Testing**:
    *   Write comprehensive unit tests using `pytest` to ensure the correctness of all scripts. Aim for at least 80% test coverage.
    *   Test key functions and classes with a variety of inputs, including edge cases and invalid data.
    *   Use mocks and stubs to isolate units of code during testing.
    *   Implement integration tests to verify the interaction between different components of the pipeline.
    *   [Illustrative] Example test cases:
        *   `create_schema.sql`: Verify that the schema is created correctly with all tables, columns, data types, and constraints.
        *   `import_data.py`: Verify that data is imported correctly from all sources and that data validation checks are performed.
        *   `sample_for_enrichment.py`: Verify that the sampling process is stratified correctly and that the output is in the correct format.
        *   `run_enrichment.py`: Verify that API calls are made correctly and that responses are parsed and loaded into the database.
*   **Version Control**: Use Git for version control. Commit code frequently with clear and descriptive commit messages.

## 8. Working Style

- Think step by step
- When uncertain, state assumptions explicitly
- Prefer queries over assumptions about data
- Document your reasoning, not just conclusions
- If you hit a blocker, describe it clearly rather than guessing

## 9. Deliverables and File Structure

```
metaforge-pipeline/
├── docs/
│   ├── archaeology-report.md
│   └── remix-discussion.md
├── scripts/
│   ├── create_schema.sql
│   ├── import_data.py
│   ├── sample_for_enrichment.py
│   └── run_enrichment.py
├── prompts/
│   └── enrichment_prompt.md
├── data/
│   └── (working data files - e.g., sampled lemmas)
├── requirements.txt
└── README.md (with instructions on how to set up and run the pipeline)
```

**Critical Requirements (REITERATED)**:

1.  **Human-in-the-loop checkpoints are mandatory**. Do not proceed past a checkpoint without explicit human approval.
2.  **Self-verification loops must complete** or explicitly flag remaining issues.
3.  **All design decisions must trace to Assess findings** - no unsupported claims.
4.  **License compatibility must be verified** for all data sources.
```