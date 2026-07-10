# Phrase-as-Node — SQL DDL Design (Block 3)

*Status: designed 2026-07-10; NOT built. Implementation deferred to Block 3 (First Completion).*

## Purpose

This is the node-first DDL replacement for the synset-keyed
`metaphor_bridges` / `metaphor_bridge_steps` tables currently defined on branch
`metaphor-graph/schema-base` at `data-pipeline/SCHEMA.sql:404-437`. Those tables
carry NOT-NULL foreign-key constraints on `synset_id` columns that vec: nodes
and multi-sense occurrence records structurally violate.

The DDL below is to be applied when Block 3 (First Completion) materialises.
**The sidecar remains file-based throughout** — no sidecar-to-DB dependency is
introduced.

## Invariants

Two invariants govern both the JSONL record schema (chain.v2) and this SQL layer;
any migration or Block-3 materialiser MUST enforce them:

1. **`chain_signature` is the occurrence key.** It is computed as
   `sha256(proposer + normalised_phrases)` — phrase-based and snap-stable. Every
   row in `chain_steps` and `step_apt_senses` is keyed by `chain_signature`. A
   schema or migration change that would alter any existing signature is a defect.

2. **`step_apt_senses.source IN ('intended','operator')` mirrors `AptSense.source`.**
   The snapper never asserts co-aptness it cannot validate; only the emit-the-sense
   gloss-match (`'intended'`) and explicit operator ticks (`'operator'`) are valid
   sources. No other value is permitted at either layer.

## DDL

```sql
CREATE TABLE nodes (
    node_id   INTEGER PRIMARY KEY,
    phrase    TEXT NOT NULL,               -- canonical form, never impoverished
    head      TEXT,                        -- display/search only
    kind      TEXT NOT NULL CHECK (kind IN ('syn','vec')),
    UNIQUE (phrase)
);
CREATE TABLE node_senses (                 -- context-free sense inventory
    node_id   INTEGER NOT NULL REFERENCES nodes(node_id),
    synset_id TEXT NOT NULL REFERENCES synsets(synset_id),
    PRIMARY KEY (node_id, synset_id)
);
CREATE TABLE chain_steps (                 -- occurrence layer
    chain_signature TEXT NOT NULL,
    step_idx        INTEGER NOT NULL,
    node_id         INTEGER NOT NULL REFERENCES nodes(node_id),
    intended_synset_id TEXT,               -- NULL for vec:
    PRIMARY KEY (chain_signature, step_idx)
);
CREATE TABLE step_apt_senses (             -- per-occurrence co-aptness
    chain_signature TEXT NOT NULL,
    step_idx        INTEGER NOT NULL,
    synset_id       TEXT NOT NULL,
    source          TEXT NOT NULL CHECK (source IN ('intended','operator')),
    PRIMARY KEY (chain_signature, step_idx, synset_id),
    FOREIGN KEY (chain_signature, step_idx)
        REFERENCES chain_steps(chain_signature, step_idx)
);
-- metaphor_bridges / bridge_steps become node-referencing; the sense-grain
-- edge view for completion derives (judged vs derived provenance) at read
-- time. Deliverable here: updated SCHEMA.sql on schema-base + design note —
-- NO data build, NO sidecar DB dependency (it stays file-based).
```
