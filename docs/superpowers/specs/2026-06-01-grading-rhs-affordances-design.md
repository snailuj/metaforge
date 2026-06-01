# Grading RHS form-affordances + head-extraction polarity — Design

**Date:** 2026-06-01
**Status:** Design (awaiting user review)
**Branch (suggested):** `metaphor-graph/grading-rhs-affordances` (stacked on current `metaphor-graph/enrich-stage-a` tip)
**Supersedes/extends:** `2026-06-01-grading-ux-round2-design.md` (W1 head-primary labels + W2 multi-select tiers shipped)

## Goal

Remove four sources of friction in the live grading tool's RHS panel, surfaced during Julian's Round-1 grading (a UAT report), plus fix the systematic data-prep error that produced them:

1. **No graph re-heat on verdict submit** — update only the just-graded path's visuals in place.
2. **Prefill the form with the last-saved verdict** (instead of a read-only "Re-Grading" banner) so re-grading is an *edit*, not a blank re-entry.
3. **Structured `tags[]`** (`merge · padding · leap · other`) replacing the free-text notes-prefix hack, for filterable analysis.
4. **Antonymic-head handling** — a `bad_head` tag to keep head-extraction errors out of the metaphor-quality signal, plus a polarity clause in both head-generation prompts.

## Why (grounded findings)

A parallel read of the codebase established the exact mechanisms (file:line refs below). These are facts the design depends on, not assumptions.

### Re-heat (W1)
- Submit flow: `mf-grade-panel.ts:148` emits `verdict-submit` → `mf-app` `handleVerdictSubmit` (~613) POSTs the record, refetches, and reassigns `this.gradeJudgements` (~637, Lit `@state`).
- That reassignment propagates to `mf-force-graph.updated()` (~567) → `changed.has('judgements')` → `feedGraph()` (~528) → **`this.graph.graphData(data)` at `mf-force-graph.ts:532`**, which resets the d3 force simulation. **This is the re-heat.**
- The graph is **accessor-based**: `linkColor`, `nodeColor`, `nodeVisibility`, `linkVisibility` are functions re-evaluated per frame — no re-feed needed to recolour. `refreshLinkStyles()` (~522) reassigns the `linkColor` accessor to force re-evaluation; `reapplyVisibility()` (~591) toggles visibility in place.
- Under the `Ungraded` filter, a graded path is hidden via `nodeVisibility`/`linkVisibility` (`reapplyVisibility`) — this already works *without* reheat; the reheat is purely the `graphData()` re-feed on submit.

### Prefill + last-saved (W2)
- The persisted timestamp is `ts` (ISO-8601 UTC) — `models.py:81` / `grading.ts:34`. Server-injected. **This is the "last saved" source.** No other timestamp field exists.
- `priorVerdict()` (`mf-app.ts:~688-704`) is bridge-keyed (latest record for the selected chain's `chain_signature`) and currently returns `{linkage, metaphor, tiers, ts, notes}` — **it omits `confidence`** (and tags, which don't exist yet).
- The "Re-Grading" banner is `mf-grade-panel.ts:186-197` (read-only summary).
- All form fields are `@state()` set only by user interaction and reset on submit: `pendingLinkage` (~95), `confidence` (~92), `selectedTiers` (~97), `notes` (~93). None bind from `priorVerdict`.
- `metaphor` is **transient** — not stored as form state; it is the submit trigger (clicking L/D/I in `_submit` ~138-156 emits the verdict immediately).
- `supersedes_ts` exists (`models.py:95`) but is **always set to null** on creation (`mf-app:~631`).

### Tags (W3)
- Spec vocabulary: `merge · padding · leap · other` (`docs/design-system/02_grade_mode/README.md`), multi-select pills, **always available** (not verdict-gated), placed between Confidence and Notes.
- Currently faked: `_addTag` (`mf-grade-panel.ts:~173-180`) prepends `"<tag>: "` to the notes string. There is **no** structured `tags` field on `VerdictSubmitDetail`, `JudgementRecord` (TS), or `JudgementRecord` (Python).
- Tiers (`strong|ironic|surprising`, gated to `metaphor==='live'`) and tags (`merge|padding|leap|other`) are **orthogonal axes**.

### Head extraction (W4)
- **Two independent generation paths:**
  - **Round-1 backfill** (`head_extraction_backfill.py`) — the cohort being graded now. Multi-word intermediate steps → **Haiku** batched call (`extract_heads_batch`, prompt lines 37-43): *"return the single-word concept that the phrase most centres on — typically a noun."* No polarity clause. Single-word phrases → `phrase.lower()`. Heads snapped via `lookup_primary_synset` (nullable on miss; falls back to first token). **No Sonnet pass in this path.**
  - **Stage-A Sonnet enrichment** (`metaphor_graph_enrich_sonnet.py`, `SONNET_EDIT_PROMPT` lines 27-51) — Sonnet emits one-word `path_concepts` **directly**. It is the *originator* of those heads, not a reviewer of Haiku's, and can flip polarity the same way. Corrected heads must still snap (`lookup_primary_synset` / `insert_bridge_with_raw_path`).
- **The bug:** `resists change` → head `change`. Haiku extracted the object noun and dropped the polarity-flipping modifier `resists`. Antonymic.

## Scope

Four workstreams. W1, W2, W3 are frontend + (W3) a small backend schema touch. W4 is a tag (folds into W3) + two prompt edits + a deferred-work capture. All cohere around the grading RHS panel + verdict model — one spec, one plan.

---

### W1 — No re-heat on verdict submit

**Behaviour:** Tapping L/D/I (or pressing the key) still submits and recolours the graded path, but the force layout does **not** restart. Under the `Ungraded` filter, the graded path disappears (as today) — also without reheat.

**Design:** In `mf-force-graph.updated()`, branch: when the change set indicates **only** judgements changed (not graph topology / mode / nodes), call a lightweight refresh — `refreshLinkStyles()` + `reapplyVisibility()` — **instead of** `feedGraph()`. Topology-affecting changes still go through `feedGraph()`.

- The verdict colour rides the `linkColor` accessor (reads `getEdgeColour()` dynamically), so `refreshLinkStyles()` re-applies it.
- Node colour is a per-frame accessor; if any node colour is verdict-dependent it auto-updates. Implementation must **verify under test** that the graded path's node *and* edge colours reflect the new verdict after the lightweight refresh; if node colour needs a nudge, add a `refreshNodeStyles()` sibling (same pattern as `refreshLinkStyles`).
- Guard precision: the branch must fire only when `changed.has('judgements')` and no topology key (`nodes`, `mode`, …) is present in the same update. Otherwise fall through to `feedGraph()`.

**Edge cases:**
- First load / topic switch / mode change → still `feedGraph()` (topology changed).
- Filter change (`pathFilter`) → existing `reapplyVisibility()` path (already no reheat).
- A verdict that changes visibility under `Ungraded` → `reapplyVisibility()` hides it in place.

**Testing (TDD):** Unit test against the existing happy-dom `3d-force-graph` Proxy mock: on `verdict-submit` while in grade mode, assert `graph.graphData` call-count does **not** increase, and `refreshLinkStyles` (+ `reapplyVisibility`) **is** called. A Playwright e2e (real chromium) asserts node screen positions are stable across a submit (no fly-around) and the graded edge colour changes.

---

### W2 — Prefill last-saved verdict; replace the banner

**Behaviour:** Selecting a previously-graded chain prefills every editable field from the last-saved verdict — linkage, confidence, tiers, notes, tags — and shows a small muted line: `last saved: <linkage>/<metaphor>[ · <tiers>][ · <tags>] · <ts>`. The previously-chosen metaphor button (L/D/I) carries a subtle "was-prior" marker so the grader sees their prior call without it auto-submitting. Tapping any L/D/I still submits, now carrying the (possibly edited) prefilled annotations — so re-grading never silently drops tags/notes.

**Design:**
- Extend `priorVerdict()` (`mf-app.ts`) to also return `confidence` and `tags` (defaulting to `'high'` / `[]` for legacy records via `normaliseJudgement`).
- Add a `willUpdate(changed)` hook in `mf-grade-panel` keyed on **`priorVerdict?.ts`** (the saved timestamp = stable record identity). When that key changes, sync `pendingLinkage`, `confidence`, `selectedTiers`, `notes`, `selectedTags` from `priorVerdict` (or to defaults when `priorVerdict` is null). Keying on `ts` prevents clobbering mid-edit re-renders (same record → no re-sync) while still re-syncing when a genuinely different verdict arrives (incl. the one just submitted).
- Add `@state() priorMetaphor: MetaphorVerdict | null` and `@state() priorTs: string | null`; render the matching L/D/I button with a `.was-prior` class and the muted last-saved line.
- Replace the `mf-grade-panel.ts:186-197` banner with the muted line.
- On re-grade submit, set `supersedes_ts = priorVerdict.ts` (instead of always-null) so the append-log is self-describing. (`mf-app` builds the record.)

**Edge cases:**
- First grade of a chain (`priorVerdict === null`) → fields at defaults, no last-saved line, no `.was-prior` marker, `supersedes_ts = null`.
- Re-grading the same chain twice in one session → after submit, the refetched `priorVerdict.ts` changes → fields re-sync to the just-saved values (consistent: form reflects what is persisted). The explicit reset-on-submit for tiers/linkage is removed in grade mode in favour of this prior-driven sync (TDD pins the ordering).
- `confidence` previously persisted across submits; under prefill it follows the prior verdict. Acceptable and more predictable.

**Testing (TDD):** Component tests: selecting a chain with a prior verdict prefills all five fields + renders the muted line + marks the prior metaphor button; selecting an ungraded chain clears to defaults; submitting a re-grade emits `supersedes_ts === priorVerdict.ts`; editing a field then re-rendering the same `priorVerdict` does **not** clobber the edit (ts-keyed guard).

---

### W3 — Structured `tags[]`

**Behaviour:** A "TAGS" pill row (matching tier styling) sits between Confidence and Notes: `merge · padding · leap · bad_head · other`, multi-select, always available, prefilled on re-grade, reset after submit. The notes-prefix hack is removed.

**Data model:**
- **Frontend (`grading.ts`):** add `export type Tag = 'merge' | 'padding' | 'leap' | 'bad_head' | 'other'` and `export const TAGS: readonly Tag[]`. Add `tags: Tag[]` to `VerdictSubmitDetail`, `JudgementRecord`, `NormalisedJudgement`. `normaliseJudgement` returns `tags: raw.tags ?? []` (v2) / `[]` (v1).
- **Backend (`models.py`):** `Tag = Literal['merge','padding','leap','bad_head','other']`; add `tags: list[Tag] = Field(default_factory=list)` to `JudgementRecord`; `normalise_judgement` returns `tags` (`raw.get('tags', [])` for v2, `[]` for v1). Pydantic drops stray legacy keys (as with the deprecated `tier`). Schema stays `judgement.v2` (additive, read-compatible).
- No `/stats` or `/calibration-sample` consumer currently reads tags; none required, but tags become available for future diagnostics.

**UI (`mf-grade-panel`):**
- `@state() selectedTags: Tag[] = []`; `_toggleTag(tag)` toggles membership (mirrors `_selectTier`).
- Render the TAGS row of toggle pills; `.selected` when included.
- Remove `_addTag`'s notes-prefix behaviour.
- Emit `tags: selectedTags` on submit; displayed state (incl. tags) follows the W2 ts-keyed prior-driven sync rather than an explicit per-field reset; prefill from `priorVerdict.tags`.
- Keyboard: click-only in this iteration (spec leaves keys as an open question; reserve, don't bind).

**Migration:** Historical notes carrying `merge:`/`padding:`/etc. prefixes are **left untouched** — no writes to live grading data. `tags[]` starts fresh; analysis can read prefixes for old records and `tags[]` for new. (A separate idempotent one-shot migration script is a future option, run by the operator, never auto-run.)

**Testing (TDD):** Backend — a `JudgementRecord` round-trips `tags`; invalid tag rejected by the `Literal`; v1 record normalises to `tags: []`; v2 without tags → `[]`. Frontend — pill toggle updates `selectedTags`; submit emits the array; reset after submit; prefill from prior; collision/dedup not applicable (fixed vocabulary).

---

### W4 — Antonymic head: `bad_head` tag + polarity clauses

**Grading decision (answers "should I mark it bad_path?" — No):** A mis-extracted head is a *data-prep* error, not a metaphor verdict. Marking it `bad_path` would poison the bootstrap signal. Instead: `linkage=good, metaphor=<your read>, tags=[bad_head]` records "the path is sound; this node's head label is broken." `bad_head` is bridge-scoped (the tag says *somewhere in this path* a head is wrong); the specific node goes in notes (e.g. `resists change → change`). Per-node head tagging is YAGNI for now.

**Prompt clauses (both paths, applied now, no re-extraction):**
- **Haiku backfill** (`head_extraction_backfill.py` `extract_heads_batch`) — add to the prompt: *"Preserve modifiers that flip or invert meaning: a negation, opposition, or relational modifier changes the head. 'resists change' → 'resistance' or 'stability', not 'change'; 'avoids risk' → 'caution', not 'risk'. Prefer a single word that still names a common concept (so it resolves to a synset)."*
- **Sonnet edit** (`metaphor_graph_enrich_sonnet.py` `SONNET_EDIT_PROMPT`) — add an equivalent line to the `path_concepts` instruction: each one-word path concept must preserve the source phrase's semantic polarity; don't reduce `resists change` to `change`.
- **No re-run now.** Editing the prompts is a code change only. `sonnet_chains_provisional_r1.jsonl` (the live Round-1 cohort being graded) is **not** regenerated — re-extraction would shift heads mid-round and disrupt active grading. Re-extraction happens at a round boundary the operator chooses.

**Testing (TDD):** The prompt edits are string-constant changes; assert the new constant contains the polarity clause (guards against accidental removal). No live data touched. (Re-extraction validation belongs to the future head milestone.)

## Decisions log (forks resolved with the user)

| Decision | Resolution |
|---|---|
| Flag mis-extracted heads | Add **`bad_head`** as a 5th structured tag (not `other`+notes). Keeps the training signal clean and filterable. |
| Head-prompt polarity fix timing | Edit **both** prompts (Haiku backfill + Sonnet edit) **now**. |
| Re-extraction of Round-1 cohort | **Deferred** to an operator-chosen round boundary — live data untouched. |
| Sonnet as head reviewer | Strengthen the **existing Sonnet edit prompt** (it originates heads in its path); do **not** build a new Sonnet-audits-Haiku stage (YAGNI). |
| Historical notes-prefixes | **Leave as-is** — no writes to live grading data. |
| Last-saved line content | Show prior verdict summary + `ts` + subtle `.was-prior` marker on the metaphor button (richer than ts alone; supports the "did my tags survive?" concern). |

## Out of scope / deferred

- **Re-extracting** Round-1 (or any) heads with the corrected prompts — operator-triggered at a round boundary.
- **Routing head extraction through Sonnet** (replacing Haiku) — the clean home for "Sonnet's judgement on heads"; a future head-extraction milestone.
- **Per-node head tagging** in the grading UI (bridge-scoped `bad_head` + notes suffices now).
- **One-shot notes-prefix → tags[] migration** script (optional, operator-run).
- **Design-system adoption** (token unification, Parchment skin) — already deferred to the Browse milestone.
- Keyboard shortcuts for tag pills.

## Risks

- **W1 node-colour assumption:** if node colour (not just edge colour) is verdict-dependent, `refreshLinkStyles()` alone may not recolour spheres. Mitigation: TDD asserts both node and edge colour post-refresh; add `refreshNodeStyles()` if needed.
- **W2 prefill clobber:** an over-eager sync could overwrite in-progress edits. Mitigation: key the sync on `priorVerdict?.ts` (stable record identity), not on every render.
- **W3 schema additivity:** `tags[]` must be read-compatible with existing `judgement.v2` records (default `[]`). No version bump. Verified by normalise tests.
- **Data safety:** all tests use tmp/scratch paths; no test writes to `judgements_provisional.jsonl` or `sonnet_chains_provisional_r1.jsonl`. Prompt edits are code-only; no re-extraction.

## TDD / commit plan (summary — full steps in the implementation plan)

Red→green→commit per unit, smallest atomic commits:
1. Backend `tags[]` (model + normalise) — Python tests.
2. Frontend types `Tag`/`tags[]` + `normaliseJudgement` — TS tests.
3. `mf-grade-panel` TAGS pill row + emit/reset; remove notes-prefix — component tests.
4. `priorVerdict()` returns `confidence`+`tags`; `mf-grade-panel` prefill via `ts`-keyed `willUpdate`; muted last-saved line + `.was-prior`; replace banner; `supersedes_ts` wiring — component tests.
5. W1 no-reheat branch in `mf-force-graph.updated()` (+ `refreshNodeStyles()` if needed) — unit (mock call-counts) + Playwright e2e.
6. Polarity clauses in both prompts — constant-content tests.
