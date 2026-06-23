# Grading UX Round 2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Head-primary grade-node labels with a `›` backlink tooltip, and a `strong/ironic/surprising` multi-select tier vocabulary.

**Architecture:** Two independent tracks over disjoint files. W2 (tiers) is a schema-shape change rippling through `models.py` → `grading.ts` → `mf-grade-panel.ts` → `mf-app.ts`. W1 (labels) extends `label-layer.ts` primitives + `mf-force-graph.ts` grade-graph builder. No file overlap; no semantic coupling (`mf-force-graph` reads only `linkage`/`metaphor` from `normaliseJudgement`, not tiers).

**Tech Stack:** Pydantic v2, FastAPI; Lit 3 + Vite 6 + TypeScript; Vitest (happy-dom); Playwright (real chromium); three `CSS2DRenderer`.

**Spec:** `docs/superpowers/specs/2026-06-01-grading-ux-round2-design.md`

**Standing constraints (every task):** TDD red→green→commit, atomic commits. UK English. **Data-safety: tests NEVER read/write the live grading JSONL (`data-pipeline/grading/judgements_provisional.jsonl`, `sonnet_chains_provisional_r1.jsonl`) — use tmp/scratch dirs only.** Run the relevant suite before each commit.

**Test commands:**
- Python: `cd /home/agent/projects/metaforge && source data-pipeline/.venv/bin/activate && python -m pytest data-pipeline/grading_sidecar/ -q`
- Web unit: `cd web && npm test`  ·  Types: `cd web && npx tsc --noEmit`
- e2e: `cd web && npx playwright test e2e/graph-labels.spec.ts`

---

## Track W2 — Tier vocabulary → multi-select

### Task W2.1: Pydantic model — `tiers` list + 3-value vocab

**Files:**
- Modify: `data-pipeline/grading_sidecar/models.py`
- Test: `data-pipeline/grading_sidecar/test_models.py` (or the existing models test file — locate with `grep -rl "JudgementRecord\|normalise_judgement" data-pipeline/grading_sidecar`)

- [ ] **Step 1: Failing tests.** Add/extend:

```python
def test_judgement_accepts_multiple_tiers():
    r = JudgementRecord(schema_version="judgement.v2", judged_by="op", round=1,
        topic="anger", topic_synset_id="1", vehicle="volcano", vehicle_synset_id="2",
        proposer="sonnet_v1", chain_signature="a"*64, linkage="good", metaphor="live",
        tiers=["strong", "surprising"])
    assert r.tiers == ["strong", "surprising"]

def test_judgement_tiers_default_empty():
    r = JudgementRecord(schema_version="judgement.v2", judged_by="op", round=1,
        topic="t", topic_synset_id="1", vehicle="v", vehicle_synset_id="2",
        proposer="p", chain_signature="a"*64, linkage="good", metaphor="dead")
    assert r.tiers == []

def test_judgement_rejects_unknown_tier():
    import pytest
    with pytest.raises(Exception):
        JudgementRecord(schema_version="judgement.v2", judged_by="op", round=1,
            topic="t", topic_synset_id="1", vehicle="v", vehicle_synset_id="2",
            proposer="p", chain_signature="a"*64, linkage="good", metaphor="live",
            tiers=["legendary"])

def test_normalise_judgement_v2_returns_tiers_list():
    assert normalise_judgement({"linkage": "good", "metaphor": "live", "tiers": ["ironic"]})["tiers"] == ["ironic"]
    assert normalise_judgement({"linkage": "good", "metaphor": "dead"})["tiers"] == []

def test_normalise_judgement_v1_returns_empty_tiers():
    assert normalise_judgement({"label": "live"})["tiers"] == []
```

- [ ] **Step 2: Run → fail.** `python -m pytest data-pipeline/grading_sidecar/ -q` — expect failures (unknown `tiers` kwarg / vocab).
- [ ] **Step 3: Implement.**
  - `Tier = Literal["strong", "ironic", "surprising"]`
  - In `JudgementRecord`: replace `tier: Optional[Tier] = None` with `tiers: list[Tier] = Field(default_factory=list)`. Update the class docstring (drop "single-select `tier`").
  - `normalise_judgement`: in the v2 branch return `{**raw, "tiers": raw.get("tiers", [])}`; in the v1 branch return `{..., "tiers": []}`. Remove the old `"tier"` key handling.
- [ ] **Step 4: Run → pass.**
- [ ] **Step 5: Update sidecar consumers.** `grep -rn "\.tier\b\|\"tier\"\|'tier'" data-pipeline/grading_sidecar` — update `/stats` / `/calibration-sample` / any reader to use `tiers` (counting membership across the list). Add/extend a test if a consumer changes behaviour. Run → pass.
- [ ] **Step 6: Commit.** `git commit -m "feat(grading): tiers list (strong/ironic/surprising) replaces single tier"`

### Task W2.2: TS types — `tiers` mirror

**Files:**
- Modify: `web/src/types/grading.ts`
- Test: locate the grading-types test (`grep -rl "normaliseJudgement" web/src`); if none, add `web/src/types/grading.test.ts`.

- [ ] **Step 1: Failing test.**

```ts
import { normaliseJudgement, type JudgementRecord } from './grading'
it('v2 normalises to a tiers array', () => {
  expect(normaliseJudgement({ linkage: 'good', metaphor: 'live', tiers: ['strong'] }).tiers).toEqual(['strong'])
  expect(normaliseJudgement({ linkage: 'good', metaphor: 'dead' }).tiers).toEqual([])
})
it('v1 label normalises to empty tiers', () => {
  expect(normaliseJudgement({ label: 'live' }).tiers).toEqual([])
})
```

- [ ] **Step 2: Run → fail.** `cd web && npm test` + `npx tsc --noEmit`.
- [ ] **Step 3: Implement.**
  - `export type Tier = 'strong' | 'ironic' | 'surprising'`
  - `JudgementRecord.tier: Tier | null` → `tiers: Tier[]`
  - `VerdictSubmitDetail.tier: Tier | null` → `tiers: Tier[]`
  - `NormalisedJudgement.tier: Tier | null` → `tiers: Tier[]`
  - `normaliseJudgement`: v2 branch `tiers: raw.tiers ?? []`; v1 branch `tiers: []`. Update the `raw` param type (`tiers?: Tier[]` replacing `tier?`).
- [ ] **Step 4: Run → pass** (test + tsc). (tsc will surface every downstream `.tier` use — those are fixed in W2.3/W2.4.)
- [ ] **Step 5: Commit.** `git commit -m "feat(grading-ui): tiers array types (strong/ironic/surprising)"`

### Task W2.3: Grade panel — multi-select chips

**Files:**
- Modify: `web/src/components/mf-grade-panel.ts`
- Test: the existing panel test (`grep -rl "mf-grade-panel\|selectedTier\|tier-" web/src web/test`)

- [ ] **Step 1: Failing tests.** Cover: clicking two tier chips selects both; clicking a selected chip deselects only it; a `verdict-submit` for a live metaphor carries `tiers` with both; tiers are gated to live (dead/irrelevant submit → `tiers: []`); banner renders multiple prior tiers. Use the existing panel test harness/fixtures; assert on the emitted `VerdictSubmitDetail.tiers` and `data-testid="tier-*"` `selected` class.
- [ ] **Step 2: Run → fail.**
- [ ] **Step 3: Implement.**
  - `const TIERS: readonly Tier[] = ['strong', 'ironic', 'surprising']`
  - `@state() private selectedTiers: Tier[] = []` (replace `selectedTier`)
  - `_selectTier(tier)`: `this.selectedTiers = this.selectedTiers.includes(tier) ? this.selectedTiers.filter(t => t !== tier) : [...this.selectedTiers, tier]`
  - submit: `const tiers = metaphor === 'live' ? this.selectedTiers : []` → emit `tiers` in the detail; reset `this.selectedTiers = []` after submit.
  - chips render: `class="tier ${this.selectedTiers.includes(tier) ? 'selected' : ''}"`
  - banner (`priorVerdict.tiers`): render joined, e.g. `${this.priorVerdict.tiers.length ? html\` (<strong>${this.priorVerdict.tiers.join(', ')}</strong>)\` : ''}`
  - Reconcile the local detail interface at line ~9 with `VerdictSubmitDetail` (`tiers`).
- [ ] **Step 4: Run → pass** (test + tsc).
- [ ] **Step 5: Commit.** `git commit -m "feat(grading-ui): multi-select tier chips"`

### Task W2.4: mf-app — submit + priorVerdict carry `tiers`

**Files:**
- Modify: `web/src/components/mf-app.ts`
- Test: the existing mf-app test (`grep -rl "handleVerdictSubmit\|priorVerdict" web/src web/test`)

- [ ] **Step 1: Failing test.** `handleVerdictSubmit` builds a `JudgementRecord` with `tiers` from `e.detail.tiers`; `priorVerdict` returns `tiers` from `normaliseJudgement`. (Mock the grading client; assert the posted judgement's `tiers`. Tmp/mocked only — never the live client.)
- [ ] **Step 2: Run → fail.**
- [ ] **Step 3: Implement.**
  - line ~628: `tier: e.detail.tier` → `tiers: e.detail.tiers`
  - `priorVerdict` return type + body: `tier` → `tiers` (from `normaliseJudgement(latest).tiers`).
- [ ] **Step 4: Run → pass** (test + tsc, full `npm test`).
- [ ] **Step 5: Commit.** `git commit -m "feat(grading-ui): mf-app emits/echoes tiers array"`

---

## Track W1 — Head-primary labels + backlink tooltip

### Task W1.1: label-layer — `›` affordance + backlink tooltip

**Files:**
- Modify: `web/src/graph/label-layer.ts`
- Test: `web/src/graph/label-layer.test.ts`

- [ ] **Step 1: Failing tests.**

```ts
it('with no backlinks renders just the head text, no arrow/tooltip', () => {
  const el = buildLabelEl({ text: 'anger', colour: '#fff', role: 'topic' }, CONST)
  expect(el.querySelector('.mf-graph-label__text')!.textContent).toBe('anger')
  expect(el.querySelector('.mf-graph-label__arrow')).toBeNull()
  expect(el.querySelector('.mf-graph-label__tooltip')).toBeNull()
})
it('with backlinks renders an interactive arrow and a tooltip row per deduped backlink', () => {
  const el = buildLabelEl({ text: 'heat', colour: '#fff', role: 'step', backlinks: [
    { source: 'pressure', phrase: 'subterranean heat' },
    { source: 'ember', phrase: 'the warmth below' },
    { source: 'pressure', phrase: 'subterranean heat' }, // dup — collapses
  ] }, CONST)
  const arrow = el.querySelector('.mf-graph-label__arrow') as HTMLElement
  expect(arrow).not.toBeNull()
  expect(arrow.style.pointerEvents).toBe('auto')
  const rows = el.querySelectorAll('.mf-graph-label__tooltip .mf-graph-label__backlink')
  expect(rows.length).toBe(2)
  expect(rows[0].textContent).toContain('pressure')
  expect(rows[0].textContent).toContain('subterranean heat')
})
```

- [ ] **Step 2: Run → fail.** `cd web && npm test`.
- [ ] **Step 3: Implement.**
  - `export interface BacklinkRow { source: string; phrase: string }`
  - `LabelStyle` gains `backlinks?: BacklinkRow[]`.
  - In `buildLabelEl`, after the text span, when `style.backlinks?.length`:
    - append `span.mf-graph-label__arrow` (textContent `›`), `style.pointerEvents = 'auto'`, plus cursor/padding for a clear target.
    - append `div.mf-graph-label__tooltip` (header = `style.text`; one `div.mf-graph-label__backlink` per **deduped** `(source, phrase)` row, text `← {source} · "{phrase}"`). Set tooltip `position:absolute; left:100%; top:0; pointer-events:none` inline; **do NOT set `display` inline** (the stylesheet `:hover` rule controls it).
  - Dedup with a `Set` keyed `${source} ${phrase}`, preserving first-seen order.
- [ ] **Step 4: Run → pass.**
- [ ] **Step 5: Commit.** `git commit -m "feat(grading-ui): backlink tooltip primitives in label layer"`

### Task W1.2: mf-force-graph — head label + backlinks + hover CSS

**Files:**
- Modify: `web/src/components/mf-force-graph.ts`
- Test: the force-graph unit test (`grep -rl "buildGradeGraph\|gradeNodes\|GradeNode" web/src web/test`)

- [ ] **Step 1: Failing tests.** `gradeNodes` carry `head` and deduped `backlinks` with correct `{source, phrase}` (target node accumulates from its inbound edges across chains); `labelStyleFor` (grade) returns `{ text: head, backlinks }`; the topic node has empty `backlinks`. Build a 2-chain fixture sharing an intermediate synset reached via two different phrases.
- [ ] **Step 2: Run → fail.**
- [ ] **Step 3: Implement.**
  - `interface GradeNode { id: string; head: string; role: ...; backlinks: BacklinkRow[] }` (drop `phrase`).
  - `buildGradeGraph`: on node creation store `head: step.head`, `backlinks: []`. While building links, push `{ source: <prev step head>, phrase: <current step phrase> }` onto the **target** node's `backlinks`; dedup per node (Set keyed source phrase). Keep the full-graph build (filter is render-time).
  - `labelStyleFor` (grade branch): `{ text: gn.head, colour: GRADE_NODE_COLOURS[gn.role], role: gn.role, backlinks: gn.backlinks }`.
  - Add to `static styles`:
    ```css
    .mf-graph-label__tooltip { display: none; }
    .mf-graph-label__arrow:hover ~ .mf-graph-label__tooltip { display: block; }
    ```
    plus tooltip box styling (background, padding, border-radius, font-size, white-space, z-index, max-width) consistent with the label palette.
- [ ] **Step 4: Run → pass** (test + tsc + full `npm test`).
- [ ] **Step 5: Commit.** `git commit -m "feat(grading-ui): head-primary labels with backlink affordance"`

### Task W1.3: e2e — head text, arrow, hover reveal, tracks under rotate

**Files:**
- Modify: `web/e2e/graph-labels.spec.ts` (+ `web/e2e/fixture.html` if the grade fixture needs backlink data)

- [ ] **Step 1: Add e2e assertions.** In a grade-mode fixture with a shared intermediate node: (a) a label's `.mf-graph-label__text` equals the head; (b) `.mf-graph-label__arrow` present on an inbound node, absent on the topic; (c) `hover` the arrow → `.mf-graph-label__tooltip` becomes visible (`getComputedStyle(...).display !== 'none'`) with the expected `← source · "phrase"` rows; (d) after `cameraPosition(...,0)` rotate + `__test_pauseAndRenderFrame`, the arrow's screen position still matches `graph2ScreenCoords` (reuse the existing two-independent-paths assertion).
- [ ] **Step 2: Run → pass.** `cd web && npx playwright test e2e/graph-labels.spec.ts` (chromium 1223). Pin node fx/fy/fz + poll-until-synced before freezing (existing determinism gotcha).
- [ ] **Step 3: Commit.** `git commit -m "test(grading-ui): e2e for head labels + backlink tooltip"`

---

## Final verification (controller, after both tracks)
- Full suites green: `python -m pytest data-pipeline/grading_sidecar/ -q`, `cd web && npm test`, `npx tsc --noEmit`, `npx playwright test e2e/graph-labels.spec.ts`.
- **Data-safety:** `grep -c '"tier"' data-pipeline/grading/judgements_provisional.jsonl` confirms 0 assigned tiers (validates the no-migration decision); confirm live JSONL md5 unchanged by the test run.
- Build dist (`cd web && npm run build`), stage into `.worktrees/next/web/dist`.
- Hand off the coordinated flip: operator `sudo systemctl restart metaforge-grading` + hard-refresh.

## Self-review notes
- Type consistency: `BacklinkRow` defined once in `label-layer.ts`, imported by `mf-force-graph.ts`. `tiers` is a `Tier[]` everywhere (no residual `tier` singular). `VerdictSubmitDetail`/`NormalisedJudgement`/`JudgementRecord` all carry `tiers`.
- Spec coverage: W1 label/arrow/tooltip/data/tests ✓; W2 vocab/multi-select/back-compat/surface/tests ✓; deploy ✓.
