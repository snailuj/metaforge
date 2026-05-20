# M02-S04 — Apt-cohort gap synset classification

Generated from `metaphor_pairs_v2.json` (274 pairs, 548 synset-sides analysed) against the live DB.

## Status totals (synset-sides)

| status | count | what fixes it |
|---|---|---|
| unenriched | 1 | surgical enrichment (this run) |
| snap-dropped | 40 | snap retuning (S04-D) |
| unresolved | 3 | lexicon scope expansion (not in M02) |
| has-properties | 504 | already scoring — no action needed |
| missing-lemma | 0 | data quality on apt pairs |

## Breakdown by role × status

| role | status | count |
|---|---|---|
| source | has-properties | 246 |
| source | snap-dropped | 27 |
| source | unenriched | 1 |
| target | has-properties | 258 |
| target | snap-dropped | 13 |
| target | unresolved | 3 |

## Unenriched targets (this surgical run will fix)

Distinct synset_ids: **1** (deduped across role and pair).

Domain breakdown:

| domain | count of side-instances |
|---|---|
| creativity | 1 |

Sample (first 30 side-instances):

```
  source comedy         domain=creativity tier=medium
```

## Snap-dropped — enrichment can't fix these (37 distinct synsets)

These synsets have LLM enrichment data in `synset_properties` but every property dropped at snap (most likely `below_threshold` embedding match against curated vocab). Surgical enrichment would just re-enrich the same data; the real fix is snap threshold retuning or curated vocab expansion (S04-D in the retro plan).

```
  source sorrow         domain=emotion tier=weak
  source anxiety        domain=emotion tier=strong
  source contentment    domain=emotion tier=weak
  source shame          domain=emotion tier=strong
  source elation        domain=emotion tier=medium
  source nostalgia      domain=emotion tier=weak
  target lightning      domain=emotion tier=medium
  target wildfire       domain=emotion tier=strong
  source frustration    domain=emotion tier=strong
  source humiliation    domain=emotion tier=weak
  source yearning       domain=emotion tier=weak
  source delight        domain=emotion tier=weak
  source longing        domain=emotion tier=medium
  source gratitude      domain=emotion tier=weak
  source awe            domain=emotion tier=weak
  source disgust        domain=emotion tier=medium
  target sunset         domain=time tier=strong
  source anticipation   domain=time tier=weak
  target avalanche      domain=time tier=medium
  target thunderbolt    domain=cognition tier=strong
  source hypothesis     domain=cognition tier=weak
  target wildfire       domain=society tier=medium
  target eruption       domain=society tier=strong
  source joint          domain=body tier=strong
  target drum           domain=body tier=medium
  source adversity      domain=nature tier=strong
  target landslide      domain=nature tier=weak
  source hardship       domain=nature tier=strong
  target thorn          domain=nature tier=strong
  source desolation     domain=nature tier=strong
```

## Unresolved — lexicon scope issue

Lemma doesn't resolve to any synset (not in `lemmas` or `property_vocab_curated` for any sense). Neither enrichment nor snap helps — the word is outside the current lexicon.

```
  target scales         domain=society tier=weak
  target rapids         domain=time tier=medium
  target funhouse       domain=creativity tier=medium
```

## Next steps

1. (caller) `--from-json` import the in-flight 8k partial so the surgical run's `--skip-enriched-required` flag can see what's already covered.
2. (caller) Run `enrich_properties.py --synset-ids apt_gap_synset_ids.json --strategy frequency --size <N> --skip-enriched-required` where N matches `len(unenriched_ids)`. The frequency padding phase will fetch zero extras since required_ids already fills the slate.
3. (downstream) Re-run M02-S04-A attrition audit to confirm the surgical lifted apt retention back toward the cognition stratum (currently 69.2% → 95.1% gap).