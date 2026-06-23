# Grading UX Round 2 — Head-Primary Labels + Backlink Tooltip + Multi-Tier

**Date:** 2026-06-01
**Branch:** `metaphor-graph/grading-tool`
**Status:** Design approved (inline) → plan to follow
**Builds on:** [verdict-model v2](2026-05-31-verdict-model-design.md), [DOM label layer](2026-05-31-dom-label-layer-design.md)

## Goal

Two independent, diagnostically-motivated grading-UX changes, surfaced while grading Round 1 in earnest:

- **W1 — Head-primary labels + backlink tooltip.** Make the node label the *head* (the stable concept that is snapped to a synset and drives dedup/edge identity) rather than the *phrase* (the incidental surface wording of whichever chain first created the deduped node). Surface the per-connection phrases — which a deduped node has *many* of, one per inbound chain — in a hover tooltip behind a `›` affordance.
- **W2 — Tier vocabulary → multi-select.** Collapse the outdated 7-tier taxonomy to `strong · ironic · surprising`, and allow a reading to belong to more than one. `legendary` is derived in a later milestone, not human-assigned.

The two workstreams touch disjoint files and have no semantic coupling.

## W1 — Head-primary labels + backlink tooltip

### What changes
- The visible grade-node label text becomes the node's **`head`** (e.g. `heat`), replacing the current `phrase` (e.g. `subterranean heat`).
- The phrase is **not** shown as a static sub-line. A deduped node is reached by many phrases (one per inbound chain) — there is no single phrase to show. The phrases live in the tooltip, per inbound connection.
- When a grade node has **≥1 inbound edge**, a `›` affordance renders at the right-hand end of the label. Topic nodes (no inbound) get no affordance.
- Hovering `›` reveals a tooltip listing the node's inbound connections. Each row: `← {source head} · "{phrase this node carried in that chain}"`, deduplicated. Header = this node's head.

```
        ┌──────────────┐
        │  heat      ›  │
        └──────────────┘
                  └─ hover › ─┐
            ╭─────────────────────────────────╮
            │ heat                             │
            │ ← pressure · "subterranean heat" │
            │ ← ember    · "the warmth below"  │
            ╰─────────────────────────────────╯
```

### Interaction mechanism (the constraints this rests on)
- Labels are `pointer-events:none` so the WebGL sphere stays the sole raycast target. The `›` affordance is the **one** element set to `pointer-events:auto` — re-enabling hit-testing for that element only. This makes it an **exact DOM hit-target**, sidestepping the long-standing raycaster hover-offset bug (that bug is WebGL-sphere-only) and not stealing canvas orbit/rotate events elsewhere.
- The tooltip is a **child of the label element**, so `CSS2DRenderer` carries it with the node under rotate/pan/zoom automatically — no manual projection.
- Reveal is **pure CSS** `:hover` (`.mf-graph-label__arrow:hover ~ .mf-graph-label__tooltip { display: block }`), rule declared in `mf-force-graph` static styles. Zero per-label listeners (matters at fog-of-war scale). Default-hidden is set **via the stylesheet, not inline** — an inline `display:none` would out-specify the `:hover` rule and never reveal.
- **Known v1 limit:** tooltips near the viewport edge clip (the `CSS2DRenderer` container is `overflow:hidden`). Accepted for v1; edge-flip positioning is a later refinement.

### Data
- `GradeNode` gains `head: string` and `backlinks: BacklinkRow[]` (`{ source: string; phrase: string }`), and drops the now-unused `phrase`.
- `buildGradeGraph` accumulates backlinks on each **target** node as it walks chain edges: for edge `stepIds[i-1] → stepIds[i]`, the target node gains `{ source: <head of step i-1>, phrase: <phrase of step i> }`. Deduped across chains (identical `(source, phrase)` rows collapse).
- Cost is O(total edges) — trivial now, linear at fog-of-war scale (labels/backlinks only built for visible nodes there).

### Label-layer API
- `LabelStyle` gains optional `backlinks?: BacklinkRow[]`. `buildLabelEl` renders the `›` span + tooltip child **only** when `backlinks` is non-empty. Browse-mode labels never set it — unchanged.
- `labelStyleFor` (grade branch) returns `{ text: gn.head, colour, role, backlinks: gn.backlinks }`.

### Testing
- **Unit (happy-dom):** `buildLabelEl` renders head as `.mf-graph-label__text`; with backlinks → `.mf-graph-label__arrow` present + `pointer-events:auto`, `.mf-graph-label__tooltip` present with one row per deduped backlink and correct text; without backlinks → neither element. `buildGradeGraph` populates `head` + deduped `backlinks` with correct source/phrase. (`:hover` reveal is **not** unit-testable — no real pointer in happy-dom.)
- **e2e (real chromium):** label text is the head; `›` present on a node with inbound edges and absent on the topic; hovering `›` reveals the tooltip with the expected rows; tooltip tracks under rotate.

## W2 — Tier vocabulary → multi-select

### What changes
- `Tier` vocabulary → **`strong | ironic | surprising`**. Drop `legendary, complex, interesting, obvious, unlikely`.
- The judgement field `tier: Tier | null` (single) → **`tiers: Tier[]`** (multi-select, default `[]`). A reading can be e.g. both `strong` and `surprising`.
- Tier chips remain enabled **only when `metaphor = live`** (existing constraint); on submit, tiers ride only a live metaphor, else `[]`.
- Schema stays **`judgement.v2`** — tier was always "remappable metadata", so no version bump.

### Back-compat (simplified — no tiers assigned yet)
The operator confirmed **zero tiers have been assigned**, so no value-migration is needed:
- `normalise_judgement` / `normaliseJudgement` output `tiers = raw.tiers ?? []`. A record with no `tiers` key (every record to date) normalises to `[]`.
- Pydantic ignores extra keys by default, so a stray legacy `tier` key (none exist) would be silently ignored — no crash, no resurrection of dead vocabulary.

### Surface
- `models.py`: `Tier` literal → 3 values; `JudgementRecord.tier` → `tiers: list[Tier] = Field(default_factory=list)`; `normalise_judgement` returns `tiers`. Update any `/stats` or `/calibration-sample` consumer of `tier`.
- `grading.ts`: `Tier` → 3 values; `JudgementRecord.tier` → `tiers: Tier[]`; `VerdictSubmitDetail.tier` → `tiers`; `NormalisedJudgement.tier` → `tiers`; `normaliseJudgement` returns `tiers`.
- `mf-grade-panel.ts`: `TIERS` const → 3 values; `selectedTier: Tier | null` → `selectedTiers: Tier[]`; `_selectTier` toggles membership (multi); submit emits `tiers` (live → selected, else `[]`); reset clears; chips `selected` when included; banner shows joined `tiers`.
- `mf-app.ts`: `handleVerdictSubmit` builds `tiers: e.detail.tiers`; `priorVerdict` returns `tiers`.

### Testing
- **Python:** `JudgementRecord` accepts `tiers: ["strong","surprising"]`; rejects out-of-vocab; defaults `[]`; `normalise_judgement` returns `tiers` for v2 (present + absent) and v1 (`[]`). Data-safety: tests use tmp dirs only.
- **Frontend:** `normaliseJudgement` returns `tiers`; panel multi-selects/deselects and emits the array; live-only gating preserved; banner renders multiple tiers.

## Deploy
One combined dist (W1 frontend-only; W2 frontend + sidecar model). W2's `tiers` POST schema requires the coordinated **sidecar restart** (operator `sudo systemctl restart metaforge-grading` + hard-refresh), same flip as the verdict-model deploy. Stage dist into `.worktrees/next/web/dist`.

## Out of scope
- Per-hop path truncation (deferred from verdict-model spec).
- Sonnet auto-assignment of tiers / `legendary` derivation (later milestone).
- Tooltip edge-flip positioning.
