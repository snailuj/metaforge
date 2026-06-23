# Two-Axis Verdict Model + Optional Tiers — Design

**Date:** 2026-05-31
**Branch:** `metaphor-graph/grading-tool`
**Status:** Design (awaiting review) → implementation plan to follow
**Supersedes:** the flat 4-label grading verdict (`live`/`dead`/`bad_path`/`irrelevant`).

## Goal

Replace the single grading `label` with two orthogonal axes — **linkage** (is the path's edges accurate?) and **metaphor** (is the endpoint pairing apt?) — plus an **optional tier** describing the character of `live` metaphors. This lets us keep the reusable conceptual edges of a path even when its endpoint is a dull/dead vehicle, and bootstraps a human sample for the product's metaphor tiers without committing to tag the whole cohort.

## The invariant this rests on (non-negotiable)

**Verdicts are properties of the *bridge* — the `(topic, vehicle, path)` reading — never of a concept node.** A judgement is keyed by `chain_signature`. The same concept node (`stone`) can simultaneously be a dead vehicle for `anchor`, a live vehicle for `grief`, and a good intermediate hop in a third bridge; "dull vehicle" is a fact about *that pairing*, not about the node. Attaching quality to a node would poison every other reading that shares it. Concretely:
- `linkage` / `metaphor` / `tier` live on `metaphor_judgments` (bridge-scoped, keyed by `chain_signature`).
- The concept/synset nodes carry no verdict.
- This already holds in the live `JudgementRecord` (no node-level field) — the new axes ride the same bridge-scoped record.

## The two axes

| Axis | Values | Meaning |
|------|--------|---------|
| **linkage** | `good` / `bad` | Are the hops real, accurate associations? (`bad` = today's `bad_path`.) A positive assertion — "I vouch for these edges" — not merely "not broken". |
| **metaphor** | `live` / `dead` / `irrelevant` | Endpoint quality: apt & vivid / connected-but-clichéd / unconnected. |

Both axes are **required** for a new grade (two taps). The quadrant that today is unrecordable — `linkage:good` + `metaphor:dead|irrelevant` — is the one that *keeps the edges* while flagging the endpoint as a poor vehicle for this topic.

## Optional tier (supplement, not replace)

A nullable, single-select **tier** on `live`(-ish) metaphors, drawn from the OG product taxonomy: `legendary · complex · interesting · ironic · strong · obvious · unlikely`. Decisions (per review):

- **Supplements** the `metaphor` axis; does not replace it. `live/dead/irrelevant` stays the crisp core signal; tier is a richer descriptive overlay. The overlap (e.g. `obvious` ≈ `dead`, `strong/interesting/legendary` ≈ gradations of `live`; `ironic`/`complex` are character; `unlikely` is ambiguous) is resolved **empirically at the calibration gate**, not pre-judged here.
- **Optional and non-blocking** — never required to submit a grade. Tagged when the grader has a clear gut read.
- **Stored as remappable metadata** — a judgement field, not graph structure — so refining/pruning the taxonomy later is cheap (re-interpret the column; no structural migration).
- **Scaling model:** the durable mechanism is **Sonnet assigns the tier; the human sample validates it** — not human-tagging everything. The optional toggle accumulates that validation sample for free. Human-tag-all-200 is explicitly *not* the plan.

### Calibration gate (~25 grades)
After ~25 two-axis grades with optional tiers, check: (a) are tiers applied consistently? (b) do they collapse onto `live/dead` (→ reconsider as a finer-grained replacement) or add real signal (→ keep as supplement)? (c) prune ambiguous tiers (`unlikely`) and confirm the character ones (`ironic`/`complex`) earn their place; (d) early read on whether a Sonnet pass agrees with the human sample. Only after this do we decide whether Sonnet drives tiers wholesale.

## Schema change — `JudgementRecord` v2 (`judgement.v2`)

`data-pipeline/grading_sidecar/models.py` + `web/src/types/grading.ts`. Replace the single `label` with the two axes + tier; everything else (ts, judged_by, round, topic/vehicle/synset ids, proposer, chain_signature, confidence, notes, supersedes_ts) is unchanged.

```python
Linkage         = Literal["good", "bad"]
MetaphorVerdict = Literal["live", "dead", "irrelevant"]
Tier            = Literal["legendary","complex","interesting","ironic","strong","obvious","unlikely"]

class JudgementRecord(BaseModel):
    schema_version: JudgementSchemaVersion   # add "judgement.v2"
    # ...unchanged identity/bridge fields...
    chain_signature: str
    linkage: Linkage
    metaphor: MetaphorVerdict
    tier: Optional[Tier] = None              # optional, remappable
    confidence: Confidence = "high"
    notes: str = ""
    supersedes_ts: Optional[str] = None
```

**Back-compat:** v1 records (with `label`) remain readable; the reader maps them to the two axes on the fly (no destructive rewrite). Migration mapping:

| v1 `label` | → `linkage` | → `metaphor` | note |
|-----------|------------|-------------|------|
| `live` | `good` | `live` | |
| `dead` | `good` | `dead` | assumes a coherent path; flag for re-grade if doubtful |
| `bad_path` | `bad` | `null`* | old label only asserted the route was broken |
| `irrelevant` | `null`* | `irrelevant` | linkage moot when unconnected |

\* For the handful of existing real judgements (≈5, all `anxiety`), the cleanest path is a quick **re-grade** under the two-axis model rather than carrying nulls — cheap and removes ambiguity. The `anxiety→debt` mis-fire (logged earlier) gets corrected here too.

## Downstream: edge admission (bridge/SQLite side — future Stage A ingestion)

When bridges are ingested to SQLite (`metaphor_bridges` / `metaphor_bridge_steps` / `metaphor_judgments` / `graph_edges` view — the bridge-centric schema on `metaphor-graph/schema-base`, not yet merged), the verdict axes drive two *separate* uses:
- **`graph_edges` admission** keys off the bridge's latest **`linkage = good`**. The same hop `(from_synset → to_synset)` may be vouched by many bridges → edge weight = accumulated count of good-linkage bridges traversing it. This is the reusable graph asset.
- The **`metaphor`** verdict + **`tier`** stay bridge-scoped, feeding metaphor-pair eval/ranking and (eventually) the product tier display. They never gate edge admission and never touch a node.

This decoupling is the whole point: a `linkage:good, metaphor:dead` bridge contributes edges (reusable for future *live* metaphors) while recording that *this* pairing was dull.

## UI changes (grade panel + graph)

- **Grade panel** (`mf-grade-panel`): two control groups — **metaphor** `Live/Dead/Irrelevant` and **linkage** `good/bad` — plus an optional **tier** selector (single-select chips, only meaningful/enabled for `live`). Keep grading fast: the common case is `linkage:good`, so **linkage defaults to `good`** and a single modifier marks it `bad`; a metaphor tap submits with current linkage + optional tier + confidence. Exact keybindings (today `L/D/B/I` + `1/2/3`) are re-derived in the plan — principle: common path stays ~one-tap, tier never blocks.
- **Edge colouring** (`mf-force-graph` `GRADE_EDGE_COLOURS`): currently keyed on the flat label. Re-map to the two axes — colour edges by `metaphor` (live=green, dead=red, irrelevant=grey), with `linkage:bad` shown distinctly (e.g. amber/dashed) so a broken route reads differently from a dull endpoint. `ungraded` unchanged.
- Re-grade banner (C3, just shipped) shows prior `linkage`+`metaphor`(+tier) + notes.

## Out of scope (deferred)

- **Per-hop / "degrades after hop k" truncation** — vouching a *prefix* of a path rather than all-or-nothing `linkage`. Needs per-hop interaction (click the degrade point on the step-node) + schema for partial-path edge admission. Revisit only if the bridge-level `linkage` signal proves too coarse.
- **Sonnet auto-assignment of tiers** — designed after the calibration gate validates the taxonomy against the human sample.

## Migration / build order (for the plan)

1. `JudgementRecord` v2 (Pydantic + TS type) with v1 read-compat + mapping. TDD on the model + reader.
2. Sidecar `/judgements` accept v2; `latestVerdicts` / stats read both versions.
3. Grade-panel two-axis controls + optional tier + keybindings (fast-path preserved).
4. `mf-force-graph` edge colouring re-mapped to the two axes.
5. Re-grade the ≈5 legacy judgements under v2 (incl. the `anxiety→debt` fix).
6. (Calibration gate after ~25 — operator step, not code.)
