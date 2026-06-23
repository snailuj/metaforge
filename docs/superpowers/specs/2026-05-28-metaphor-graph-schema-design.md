# Metaphor Graph Schema — Design Spec

**Date:** 2026-05-28
**Status:** Design approved in conversation; ready for plan.
**Related memory:**
- `metaphor_graph_vs_property_graph.md` — architectural reframe
- `eval_as_preference_tracking_instrument.md` — eval bootstrap context
- `product_goal_live_vs_dead_metaphors.md` — live vs dead distinction
- `karpathy_loop_purpose_framing.md` — cascade as cold-start

## Goal

Introduce a metaphor graph layer that is **structurally different** from today's implicit property graph: explicit metaphor edges with attributes (label, proposer, judge, bridge path) that are populated by both LLM proposers (Haiku) and the existing cascade, judged by Julian via the instrumented eyeballer, and consumed by the eventual graph-completion model.

The schema must:

1. Treat the bridge — the multi-hop path from topic to vehicle through shared concepts — as first-class. Endpoints alone are not enough.
2. Support multiple proposers (`cascade_v1`, `haiku_v1`, `eyeballer_freeform`, future) writing to one pool.
3. Support multiple judges (currently `julian`, eventually `llm_judge_v1`) with one verdict per (bridge, judge).
4. Support multiple parallel paths between the same `(topic, vehicle)` pair naturally — different bridges through different shared concepts are different rows.
5. Reuse the existing synset namespace — every node in the metaphor graph is a synset.
6. Enforce referential integrity via foreign keys.
7. Stay idempotent against re-runs of any proposer.
8. Leave the existing enrichment pipeline untouched (no migration of `synset_properties_curated`, `synset_metonyms`, etc.).

## Architecture

A unified `graph_edges` **view** sits on top of the existing relation tables plus two new physical tables (`metaphor_bridges`, `metaphor_judgments`) and one supporting child table (`metaphor_bridge_steps`). Nodes are synsets — no separate `graph_nodes` table is needed because `synset_properties_curated` is `UNIQUE(synset_id)`, so all curated property concepts are already synsets.

The metaphor graph is a **bridge-centric** layer: a "proposal" is `(topic, vehicle, path)` not `(topic, vehicle)`. A judgment is attached to a bridge, not a pair — this is what gives graph-completion direct supervision on which intermediate concepts carry the metaphor.

## Schema

### New physical tables

```sql
CREATE TABLE metaphor_bridges (
    bridge_id          INTEGER PRIMARY KEY AUTOINCREMENT,
    topic_synset_id    TEXT NOT NULL REFERENCES synsets(synset_id),
    vehicle_synset_id  TEXT NOT NULL REFERENCES synsets(synset_id),
    proposer           TEXT NOT NULL,            -- 'cascade_v1' | 'haiku_v1' | 'eyeballer_freeform' | ...
    proposed_at        TEXT NOT NULL,            -- ISO 8601
    path_hash          TEXT NOT NULL,            -- sha256 of "step0_id|step1_id|..." (order-preserving)
    rationale          TEXT,                     -- LLM's natural-language explanation, nullable
    -- cached cascade features (so completion training doesn't recompute)
    cosine_distance    REAL,
    ortony_score       REAL,
    cascade_score      REAL,
    signed_delta       REAL,
    UNIQUE (topic_synset_id, vehicle_synset_id, proposer, path_hash)
);

CREATE INDEX idx_metaphor_bridges_topic   ON metaphor_bridges(topic_synset_id);
CREATE INDEX idx_metaphor_bridges_vehicle ON metaphor_bridges(vehicle_synset_id);
CREATE INDEX idx_metaphor_bridges_proposer ON metaphor_bridges(proposer);

CREATE TABLE metaphor_bridge_steps (
    bridge_id          INTEGER NOT NULL REFERENCES metaphor_bridges(bridge_id) ON DELETE CASCADE,
    step_index         INTEGER NOT NULL,         -- 0 = first intermediate AFTER topic; endpoints not stored
    via_synset_id      TEXT NOT NULL REFERENCES synsets(synset_id),
    PRIMARY KEY (bridge_id, step_index)
);

CREATE INDEX idx_metaphor_bridge_steps_via ON metaphor_bridge_steps(via_synset_id);

CREATE TABLE metaphor_judgments (
    judgment_id        INTEGER PRIMARY KEY AUTOINCREMENT,
    bridge_id          INTEGER NOT NULL REFERENCES metaphor_bridges(bridge_id) ON DELETE CASCADE,
    label              TEXT NOT NULL CHECK (label IN
                         ('live','dead_synonym','dead_lakoff','irrelevant','edge_case')),
    judged_by          TEXT NOT NULL,
    judged_at          TEXT NOT NULL,
    confidence         REAL,
    notes              TEXT,
    UNIQUE (bridge_id, judged_by)
);

CREATE INDEX idx_metaphor_judgments_label ON metaphor_judgments(label);
CREATE INDEX idx_metaphor_judgments_judged_by ON metaphor_judgments(judged_by);
```

### Unified graph view

```sql
CREATE VIEW graph_edges AS
SELECT
    synset_id        AS src_synset_id,
    -- curated vocab is 1:1 with synset_id; expose via JOIN to property_vocab_curated
    pvc.synset_id    AS dst_synset_id,
    'has_property'   AS relation,
    spc.salience_sum AS weight,
    NULL             AS bridge_id
FROM synset_properties_curated spc
JOIN property_vocab_curated pvc ON pvc.vocab_id = spc.vocab_id

UNION ALL

SELECT
    src_synset_id,
    dst_synset_id,
    'metonym_of'     AS relation,
    NULL             AS weight,
    NULL             AS bridge_id
FROM synset_metonyms

UNION ALL

-- TODO at impl time: confirm shape of antonym source (cluster_antonyms / property_antonyms)
-- and project to synset level. Placeholder shape:
SELECT
    src_synset_id,
    dst_synset_id,
    'antonym_of'     AS relation,
    NULL             AS weight,
    NULL             AS bridge_id
FROM cluster_antonyms

UNION ALL

SELECT
    mb.topic_synset_id   AS src_synset_id,
    mb.vehicle_synset_id AS dst_synset_id,
    'metaphor_link'      AS relation,
    mj.confidence        AS weight,
    mb.bridge_id         AS bridge_id
FROM metaphor_bridges mb
JOIN metaphor_judgments mj ON mj.bridge_id = mb.bridge_id
WHERE mj.label = 'live';
```

Notes on the view:

- Only `label='live'` bridges become `metaphor_link` rows. Dead / irrelevant / edge-case judgments and unjudged proposals are NOT graph structure; they are addressable directly via the underlying tables (for ML training).
- The `bridge_id` column on `graph_edges` is nullable except for `metaphor_link` rows. Consumers that want the path JOIN through to `metaphor_bridge_steps`.
- No FK on a view — referential integrity is enforced by the underlying tables.
- Performance is acceptable for current scale; revisit with denormalisation if/when the completion model is being trained over the full graph.
- Multi-judge note: when more than one judge endorses the same bridge as `live`, the view emits one `metaphor_link` row per judge for that bridge. With only `julian` judging in v1 this is moot. When `llm_judge_v1` is added, consumers either `DISTINCT` over `(src, dst, bridge_id)` or the view evolves to aggregate. Deliberately not aggregated now to keep raw judgments visible.

## Worked Examples

### Cascade proposes `anger → fire`

Cascade finds three shared curated properties: `heat-n-1`, `destruction-n-1`, `intensity-n-1`. It inserts three rows in `metaphor_bridges` (proposer=`cascade_v1`), each with one row in `metaphor_bridge_steps`. Each bridge is independently scored (cached `cosine_distance`, `ortony_score`, `cascade_score`, `signed_delta`) and independently judgeable.

```
metaphor_bridges:
  bridge_id=101  topic=anger-n-1  vehicle=fire-n-1  proposer=cascade_v1  path_hash=H(heat-n-1)
  bridge_id=102  topic=anger-n-1  vehicle=fire-n-1  proposer=cascade_v1  path_hash=H(destruction-n-1)
  bridge_id=103  topic=anger-n-1  vehicle=fire-n-1  proposer=cascade_v1  path_hash=H(intensity-n-1)

metaphor_bridge_steps:
  (101, 0, heat-n-1)
  (102, 0, destruction-n-1)
  (103, 0, intensity-n-1)
```

### Haiku proposes `anger → fire`

Haiku emits `(vehicle="fire", bridge=["heat"], rationale="both consume and transform what they touch")`. The proposal layer takes the one-word concept string `"heat"`, runs it through the existing snap cascade (exact → morphological → embedding) to resolve it to `heat-n-1`. One row in `metaphor_bridges` (proposer=`haiku_v1`), one row in `metaphor_bridge_steps`. The cascade's bridge_id=101 and Haiku's new bridge share the same `path_hash` but different `proposer`, so the UNIQUE constraint allows both.

```
metaphor_bridges:
  bridge_id=204  topic=anger-n-1  vehicle=fire-n-1  proposer=haiku_v1  path_hash=H(heat-n-1)
                 rationale="both consume and transform what they touch"
```

### Julian judges

Eyeballer UI groups bridges by `(topic, vehicle, path_hash)` so the cascade's heat-bridge (101) and Haiku's heat-bridge (204) display as one card annotated "two proposers concur". One keystroke writes two `metaphor_judgments` rows (one per bridge_id), both with `label='live'`, `judged_by='julian'`. The destruction-bridge (102) and intensity-bridge (103) are separate cards and judged separately.

Possible verdicts on the example:

```
metaphor_judgments:
  bridge_id=101 (cascade/heat)        label=live           judged_by=julian
  bridge_id=204 (haiku/heat)          label=live           judged_by=julian
  bridge_id=102 (cascade/destruction) label=dead_lakoff    judged_by=julian
  bridge_id=103 (cascade/intensity)   label=live           judged_by=julian
```

Graph completion training then has:
- 3 positive examples (heat ×2, intensity ×1) — `heat-n-1` and `intensity-n-1` are load-bearing nodes for `(anger, fire)`
- 1 hard negative — `destruction-n-1` overlaps but doesn't carry a live metaphor here
- Haiku's rationale text is available as auxiliary supervision

### 3-hop bridge

Haiku emits `(anger, rumour, bridge=["heat", "spreading"])`. The proposal layer snaps both intermediates. Result: one bridge row with two step rows.

```
metaphor_bridges:
  bridge_id=305  topic=anger-n-1  vehicle=rumour-n-1  proposer=haiku_v1
                 path_hash=H(heat-n-1|spreading-n-1)

metaphor_bridge_steps:
  (305, 0, heat-n-1)
  (305, 1, spreading-n-1)
```

Order matters in the path (different `path_hash` if the order were reversed), so semantically different traversals through the same node-set are different bridges.

## Settled Decisions

| Decision | Choice | Why |
|---|---|---|
| Single vs multi-typed nodes | Single (all synsets) | `property_vocab_curated` is 1:1 with synsets — no need for separate node kinds. |
| Migrate vs view | View | Existing enrichment pipeline stays untouched; defer perf work until completion-model load is real. |
| Judgments + proposals layout | Bridge-centric (proposal IS bridge) | Path is first-class; cascade and LLM use the same representation. |
| Cascade bridge articulation | Per shared property | Each shared curated property is a 2-hop bridge; cascade emits N bridges per pair, individually judgeable. |
| LLM concept strings | One-word, snap on insert | Snap cascade already exists and works well; lets the LLM stay natural. |
| Verdict grain | One per (bridge, judge) | No versioning of judgments; if Julian changes his mind, that's an UPDATE not a new row. |
| Multiple paths per pair | Native, multiple bridge rows | Falls out of `UNIQUE (topic, vehicle, proposer, path_hash)`. |
| Idempotency | `path_hash` over ordered step IDs | Re-running a proposer doesn't double-insert. |
| Live edges only in graph view | Yes | Dead/irrelevant/unjudged stay in physical tables for ML; graph itself is gold-only. |

## Out of Scope

- The completion algorithm itself (TransE / GraphSAGE / LLM-link-predictor). Schema must NOT block any of them; concrete choice deferred until the graph has accumulated enough judged edges to test on.
- The eyeballer UI design (separate spec, will reference this schema).
- Migration of antonym source to a proper synset-level table (parked per `antonym_import_deprioritised.md`); current view uses the existing `cluster_antonyms` shape as best-effort.
- `graph_edges` view performance optimisation (UNION over UNION ALL, denormalisation, materialised views) — revisit when completion-model training pressure exists.
- Triggers / write paths for the existing enrichment pipeline. No changes proposed; the view reads what's already there.
- Backfill of the cascade's existing in-memory proposals into `metaphor_bridges`. Separate effort; the schema supports it but the spec only commits to the schema.

## Implementation Sketch

A future plan will need to:

1. Add the three new tables with their indexes (forward-only migration; SQLite + `PRAGMA foreign_keys=ON`).
2. Add a `path_hash` helper (Python + Go parity, hashing the ordered list of step `via_synset_id`s with `|` delimiter).
3. Add a `graph_edges` VIEW per the SQL above; settle the antonym source at impl time.
4. Add an inserter helper that:
   - Takes `(topic, vehicle, proposer, path: list[str], rationale, cascade_features)` where `path` is either pre-snapped synset_ids or raw concept strings.
   - Snaps any raw strings via the existing snap cascade.
   - Computes `path_hash`.
   - Inserts the `metaphor_bridges` row, then the ordered `metaphor_bridge_steps` rows, in a transaction.
   - Idempotent — `INSERT OR IGNORE` on the UNIQUE constraint; returns existing `bridge_id` if hit.
5. Write tests:
   - Cascade-style insert with one intermediate.
   - Haiku-style insert with raw string + snap.
   - Multi-hop bridge insert (ordered intermediates).
   - Idempotency: re-running same proposer doesn't duplicate.
   - Two proposers, same path: two rows.
   - View round-trip: judged-live bridge appears as `metaphor_link` in `graph_edges`; judged-dead does not.

Eyeballer integration and the cascade's bridge-emitting modification are downstream, addressed in their own plans.
