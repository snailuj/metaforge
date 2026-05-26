# Antonyms — proper import (WordNet lexical + ConceptNet augment)

**Status:** Queued. Needs `sqlunet_master.db` on disk (currently absent on this host). Operator at laptop required for the schema work.

**Pre-req for:** Iter 25's antonym-clash hypothesis follow-up + thesaurus product-side antonym display + a richer cohort-side signal for any future cascade work. Should land *before* the next LLM graph-enrichment pass so we don't waste tokens on antonyms.

## The gap (discovered 2026-05-26)

Our `relations` table is synset↔synset only. WordNet's `!` antonym is a **lexical** relation (word↔word), which the sqlunet import dropped entirely. `build_antonyms.py` worked around this by deriving antonym pairs via the `attribute` (relation_type 60) semantic relation — adjectives sharing an attribute noun are inferred antonyms. The derivation is structurally noisy and sparse: **576 pairs covering 365 of ~35,000 vocab entries (~1% coverage)**. Sample inspection finds noise like `ability ↔ ability` and `active ↔ active` — same-lemma "antonyms" from variant senses grouped under one attribute noun.

Iter 25 demonstrated the cohort signal that *should* be there: apt vehicles show 3-5× higher antonym-clash rates than inapt vehicles. But the absolute magnitude was too small to flip the metric because most pairs simply can't clash — the table doesn't have antonyms for most properties.

## Recommended path — two-stage, both free, both pre-LLM

### Stage 1: Re-import WordNet lexical pointers (high-precision baseline)

Modify `data-pipeline/import_raw.sh` + `SCHEMA.sql` to add a `lemma_relations` (or `lexical_relations`) table populated from sqlunet's lexical-link source. Antonym is one entry there; while we're at it we should also bring in `pertainym`, `derivationally_related_form`, and `participle_of_verb` — all useful for both the thesaurus product side and any future cohort enrichment.

Expected order-of-magnitude: WordNet has ~7-8k antonym pairs at the lemma level for English. Lemma→synset_id snap via `lookup_primary_synset` gives us synset-level coverage we can layer over the property vocab. Compared to the current 576 derived pairs, **roughly 12-15× expansion** at curated lexicographer quality.

**Schema sketch:**

```sql
CREATE TABLE lemma_relations (
    relation_type  TEXT NOT NULL,    -- 'antonym' | 'pertainym' | 'derivation' | ...
    source_lemma   TEXT NOT NULL,
    source_synset  TEXT NOT NULL,
    target_lemma   TEXT NOT NULL,
    target_synset  TEXT NOT NULL,
    PRIMARY KEY (relation_type, source_lemma, source_synset, target_lemma, target_synset)
);
CREATE INDEX idx_lemma_relations_source ON lemma_relations(source_synset, relation_type);
CREATE INDEX idx_lemma_relations_target ON lemma_relations(target_synset, relation_type);
```

Then derive a refreshed `property_antonyms` directly from these lexical pairs (filtered to vocab entries) — drop the `attribute`-relation hack from `build_antonyms.py` entirely.

### Stage 2: Augment with ConceptNet `/r/Antonym` (broader coverage)

[ConceptNet 5](https://conceptnet.io/) is CC BY-SA 4.0, distributes as gzipped TSV, has `/r/Antonym` edges sourced from Wiktionary. Tens of thousands of English antonym pairs at lower precision than WordNet but much wider coverage. Filter to `/c/en/...` start/end nodes, normalise via existing lemma resolution, dedup against WordNet-sourced pairs.

Probably **+10-20k pairs** beyond WordNet, especially for informal/derived antonyms (rich/broke, sleepy/awake) that WordNet's lexicographer-curated set misses.

**Practical considerations:**

- ConceptNet's edge weights are noisy. Filter by weight ≥ some threshold (1.0 is the conventional cutoff for "reasonably confident").
- Multiword expressions are common in ConceptNet but our property vocab is mostly single-word. Either skip multiword targets or split-and-resolve.
- License is CC BY-SA 4.0 — propagates to derived data. Need to track attribution if the antonym data leaves the DB into a redistributable output. For Metaforge's deploy-server use it's fine.

Alternative source: [Wiktextract](http://www.lrec-conf.org/proceedings/lrec2022/pdf/2022.lrec-1.140.pdf) goes directly to Wiktionary dumps and lets us do our own filtering. Same upstream as ConceptNet but with more control. Pick one — ConceptNet is faster to ingest.

## Combined output target

- `lemma_relations` populated from WordNet (~7-8k antonym lemma-pairs + pertainym + derivation)
- `property_antonyms` rebuilt: WordNet lexical + ConceptNet filtered + Wiktextract optional — dedup, vocab-filtered
- Estimated final size: **10-30k pairs**, ~10-20% vocab coverage (vs the current ~1%)

## Implications for the LLM graph-enrichment pass

**Antonyms come out of the LLM prompt entirely.** They're structural data we can pull for free from WordNet + ConceptNet. The LLM graph-enrichment should focus on what only an LLM can do well: structured metaphor vehicles + per-feature rationale per topic, using the property-dimension vocabulary as a controlled vocab.

This frees ~10-20% of the prompt token budget (depending on prompt design) for richer per-vehicle structure.

## Acceptance criteria

- `lemma_relations` table exists, populated from a re-run of `import_raw.sh` against `sqlunet_master.db`
- New `build_antonyms.py` (or replacement) reads from `lemma_relations` + optional ConceptNet ingest, writes `property_antonyms`
- `property_antonyms` row count ≥ 10,000
- Sample inspection: no same-lemma "antonyms" (e.g. `active ↔ active`)
- Thesaurus-side `/thesaurus/<word>` returns antonym list when available (separate API concern, but worth threading)

## Why not now

`sqlunet_master.db` isn't on this host, and the operator is on mobile (Termux) — schema iteration + the re-import workflow want a laptop. Defer.

## Related work this unblocks

- **Iter 25 follow-up** — antonym-clash signal becomes magnitude-able with denser antonym data. The hypothesis was correct but starved.
- **Thesaurus product side** — display antonyms alongside synonyms in the word card. UI affordance already designed (see Sprint Zero docs); blocked on having a usable antonyms data source.
- **Future LLM graph enrichment** — don't pay tokens for structural data. This work is a pre-req.
