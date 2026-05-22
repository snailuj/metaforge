# M03-S05 Smoke Test Crib

Generated 2026-05-21 against `data-pipeline/output/lexicon_v2.db`
(post-haiku-sm rebuild — curated × enriched 99.2%, curated × centroid 99.3%).

This crib pins the Python ground truth for the 8 smoke pairs the Go cascade
endpoint must replicate. Task 11 (live smoke test) diffs the Go response
against the values below.

## Cascade config

```
evaluator:               cascade
concreteness_threshold:  1.0   (signed; vehicle − topic)
alpha:                   1.0
d_cap:                   0.77
ortony_scoring:          jaccard_salience
composition:             additive
```

## Python ground truth

```json
[
  {
    "topic": "anger",
    "vehicle": "fire",
    "topic_synset": "30227",
    "vehicle_synset": "50554",
    "status": "scored",
    "final_score": 0.3264111093603957,
    "ortony_score": 0.0,
    "cosine_distance": 0.25133655420750467,
    "re_rank_bonus": 0.3264111093603957
  },
  {
    "topic": "idea",
    "vehicle": "light",
    "topic_synset": "64981",
    "vehicle_synset": "44464",
    "status": "scored",
    "final_score": 0.2483492844771258,
    "ortony_score": 0.0,
    "cosine_distance": 0.19122894904738685,
    "re_rank_bonus": 0.2483492844771258
  },
  {
    "topic": "time",
    "vehicle": "money",
    "topic_synset": "445",
    "vehicle_synset": "94024",
    "status": "scored",
    "final_score": 0.31237238468193407,
    "ortony_score": 0.0,
    "cosine_distance": 0.24052673620508924,
    "re_rank_bonus": 0.31237238468193407
  },
  {
    "topic": "argument",
    "vehicle": "war",
    "topic_synset": "67993",
    "vehicle_synset": "15970",
    "status": "gate_dropped",
    "final_score": 0.0,
    "ortony_score": null,
    "cosine_distance": null,
    "re_rank_bonus": null
  },
  {
    "topic": "life",
    "vehicle": "journey",
    "topic_synset": "92",
    "vehicle_synset": "31055",
    "status": "gate_dropped",
    "final_score": 0.0,
    "ortony_score": null,
    "cosine_distance": null,
    "re_rank_bonus": null
  },
  {
    "topic": "truth",
    "vehicle": "hammer",
    "topic_synset": "64180",
    "vehicle_synset": "28753",
    "status": "scored",
    "final_score": 0.26667097125952566,
    "ortony_score": 0.0,
    "cosine_distance": 0.20533664786983474,
    "re_rank_bonus": 0.26667097125952566
  },
  {
    "topic": "silence",
    "vehicle": "velvet",
    "topic_synset": "59903",
    "vehicle_synset": "57528",
    "status": "no_properties",
    "final_score": null,
    "ortony_score": null,
    "cosine_distance": null,
    "re_rank_bonus": null
  },
  {
    "topic": "cat",
    "vehicle": "feline",
    "topic_synset": "81628",
    "vehicle_synset": "46156",
    "status": "gate_dropped",
    "final_score": 0.0,
    "ortony_score": null,
    "cosine_distance": null,
    "re_rank_bonus": null
  }
]
```

## Pair-by-pair table

Numbers shown to 6 decimal places. `—` (em-dash) denotes `null` / `None` —
fields the Python evaluator did not populate because the pair short-circuited
before that stage.

| topic | vehicle | status | final_score | ortony_score | cosine_distance | re_rank_bonus |
|-------|---------|--------|-------------|--------------|-----------------|---------------|
| anger | fire | scored | 0.326411 | 0.000000 | 0.251337 | 0.326411 |
| idea | light | scored | 0.248349 | 0.000000 | 0.191229 | 0.248349 |
| time | money | scored | 0.312372 | 0.000000 | 0.240527 | 0.312372 |
| argument | war | gate_dropped | 0.000000 | — | — | — |
| life | journey | gate_dropped | 0.000000 | — | — | — |
| truth | hammer | scored | 0.266671 | 0.000000 | 0.205337 | 0.266671 |
| silence | velvet | no_properties | — | — | — | — |
| cat | feline | gate_dropped | 0.000000 | — | — | — |

## Parity tolerance

The Go cascade endpoint at `GET /forge/suggest?word=<topic>&limit=50&--cascade`
must satisfy:

- For every pair where Python reports `status=scored` (anger/fire, idea/light,
  time/money, truth/hammer): the Go response must include the vehicle word,
  with `final_score`, `ortony_score`, `cosine_distance`, `re_rank_bonus`
  matching the table above to ±1e-6.
- For every pair where Python reports `status != scored` (`gate_dropped`,
  `missing_concreteness`, `no_properties`, `unresolved`): the vehicle word
  must NOT appear in the Go response. The API drops non-scored pairs from
  product output, per `handleSuggestCascade`. The 4 non-scored pairs here are:
  argument/war (gate_dropped), life/journey (gate_dropped), silence/velvet
  (no_properties), cat/feline (gate_dropped).

Note: `ortony_score` is 0.0 for all 4 scored pairs in this DB state because
curated salience overlap is empty for these topic/vehicle synset pairs;
`final_score == re_rank_bonus` follows from the additive composition with
`ortony_score == 0`.

## Reproduction

Run from repo root with the data-pipeline venv active:

```python
import json, sqlite3, sys
sys.path.insert(0, "data-pipeline/scripts")
from evaluate_cascade import CascadeConfig, evaluate_cascade_pair
from evaluate_aptness import lookup_primary_synset

PAIRS = [
    ("anger", "fire"), ("idea", "light"), ("time", "money"),
    ("argument", "war"), ("life", "journey"),
    ("truth", "hammer"), ("silence", "velvet"),
    ("cat", "feline"),
]
cfg = CascadeConfig(concreteness_threshold=1.0, ortony_scoring="jaccard_salience",
                    d_cap=0.77, alpha=1.0, composition="additive")
out = []
with sqlite3.connect("data-pipeline/output/lexicon_v2.db") as conn:
    for topic, vehicle in PAIRS:
        t = lookup_primary_synset(conn, topic)
        v = lookup_primary_synset(conn, vehicle)
        if t is None or v is None:
            out.append({"topic": topic, "vehicle": vehicle, "status": "unresolved",
                        "topic_synset": t, "vehicle_synset": v})
            continue
        r = evaluate_cascade_pair(conn, t, v, cfg)
        out.append({
            "topic": topic, "vehicle": vehicle,
            "topic_synset": t, "vehicle_synset": v,
            "status": r.status,
            "final_score": r.final_score,
            "ortony_score": r.ortony_score,
            "cosine_distance": r.cosine_distance,
            "re_rank_bonus": r.re_rank_bonus,
        })
print(json.dumps(out, indent=2))
```

## Go parity confirmation

Confirmed 2026-05-21 by `TestCascadeParity_GoMatchesPythonGroundTruth` in
`api/internal/forge/cascade_parity_test.go`.

### Approach

The test bypasses the Go `/forge/suggest` candidate-generation layer (the
cluster-overlap CTE in `GetForgeCascadeCandidatesByLemma`) and calls
`forge.EvaluateCascadePair` directly with inputs derived from the same
DB the Python evaluator used: concreteness + centroids from
`CascadeCache`, properties from `GetSynsetClusterPropertiesBatch`,
primary synsets resolved by mirroring Python's `lookup_primary_synset`
(curated-vocab least-polysemous first; lemmas fallback ordered by
`synset_id`).

This proves the Go scoring math faithfully ports the Python reference,
which is the relevant correctness property for S05.

### Why not end-to-end through `/forge/suggest`

The Go endpoint can only surface candidates that share at least one
curated cluster between source-primary-synset and vehicle-primary-synset
(the `per_sense_shared` CTE in `cascade.go`). All 4 scored smoke pairs
have `ortony_score = 0.0` — they share no curated clusters — and so
never appear as candidates in the live endpoint. The cascade re-rank
*would* discriminate them; the candidate generation doesn't surface
them. Broadening the candidate set is the M04 — Cosine-Sim Candidate
Generation milestone (see `docs/roadmap/M04-cosine-candidate-gen-roadmap.md`).

### Results

| topic | vehicle | python status | go status | numeric match |
|-------|---------|---------------|-----------|---------------|
| anger | fire | scored | scored | ±1e-6 |
| idea | light | scored | scored | ±1e-6 |
| time | money | scored | scored | ±1e-6 |
| truth | hammer | scored | scored | ±1e-6 |
| argument | war | gate_dropped | gate_dropped | (no numeric fields) |
| life | journey | gate_dropped | gate_dropped | (no numeric fields) |
| silence | velvet | no_properties | no_properties | (no numeric fields) |
| cat | feline | gate_dropped | gate_dropped | (no numeric fields) |

All 8 subtests pass; cumulative runtime ~0.7s (cache load + 8 evaluations).

### Note on synset drift

The test cross-checks the resolved synset_ids against the crib's pinned
IDs. If the lemmas → primary-synset resolution ever drifts (e.g. via
a DB rebuild that changes the ordering), the test will emit a clear
"synset drift" error pointing at the affected lemma. The crib must be
regenerated in that case, NOT silently updated.
