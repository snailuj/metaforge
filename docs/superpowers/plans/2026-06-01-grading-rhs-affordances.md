# Grading RHS form-affordances + head-extraction polarity — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove four Round-1 grading-friction items in the RHS panel — graph re-heat on submit, no prefill of the last verdict, free-text tag prefixes, and antonymic head labels — via in-place graph updates, ts-keyed form prefill, a structured `tags[]` field (incl. `bad_head`), and a polarity clause in both head-generation prompts.

**Architecture:** Frontend is Lit 3 + TypeScript + `3d-force-graph` (`web/`); the verdict model is shared between a Pydantic sidecar (`data-pipeline/grading_sidecar/`) and TS types (`web/src/types/grading.ts`). The grade graph is accessor-based (link/node colour + visibility are per-frame functions), so verdict changes need no `graphData()` re-feed. Form prefill rides Lit's `willUpdate`, keyed on the prior record's `ts` so it can't clobber edits.

**Tech Stack:** Lit 3, Vite 6, TypeScript, Vitest (happy-dom), Playwright (chromium); Python 3.12 + Pydantic; pytest.

**Spec:** `docs/superpowers/specs/2026-06-01-grading-rhs-affordances-design.md`

---

## Pre-flight

- Branch `metaphor-graph/grading-rhs-affordances` already exists (spec committed there). Work on it.
- Frontend deps: `cd web && npm install` (own `node_modules`).
- Python venv: `data-pipeline/.venv` (memory: `python3 -m venv data-pipeline/.venv && data-pipeline/.venv/bin/pip install -r data-pipeline/requirements.txt` if absent).
- **Data-safety (NON-NEGOTIABLE):** no test may write to live grading data (`data-pipeline/grading/judgements_provisional.jsonl`, `sonnet_chains_provisional_r1.jsonl`). All Python tests construct in-memory models only. **No re-extraction** is run in this plan — W4 edits prompt strings only.

**Command shorthands (run from repo root unless noted):**
- PY: `source data-pipeline/.venv/bin/activate && python -m pytest <paths> -v`
- FE-TEST: `cd web && npx vitest run <path>`
- FE-TYPES: `cd web && npx tsc --noEmit`

## File Structure

| File | Responsibility | Tasks |
|---|---|---|
| `data-pipeline/grading_sidecar/models.py` | `Tag` literal + `tags[]` on `JudgementRecord` + `normalise_judgement` | 1 |
| `data-pipeline/grading_sidecar/tests/test_models.py` | tags model + normalise tests | 1 |
| `web/src/types/grading.ts` | `Tag`/`TAGS` + `tags[]` on the 3 interfaces + `normaliseJudgement` | 2 |
| `web/src/types/grading.test.ts` | normalise tags tests | 2 |
| `web/src/components/mf-grade-panel.ts` | `selectedTags` state + emit (T2); pills UI (T3); prefill + last-saved + was-prior (T5) | 2,3,5 |
| `web/src/components/mf-grade-panel.test.ts` | tags + prefill component tests | 2,3,5 |
| `web/src/components/mf-app.ts` | `handleVerdictSubmit` tags (T2); `priorVerdict()` confidence+tags + `supersedes_ts` (T4) | 2,4 |
| `web/src/components/mf-app.test.ts` | prior threading + supersedes_ts tests | 4 |
| `web/src/components/mf-force-graph.ts` | `updated()` no-reheat branch | 6 |
| `web/src/components/mf-force-graph.test.ts` | no-reheat-on-judgements-change test | 6 |
| `data-pipeline/scripts/head_extraction_backfill.py` | Haiku prompt → module constant + polarity clause | 7 |
| `data-pipeline/scripts/metaphor_graph_enrich_sonnet.py` | `SONNET_EDIT_PROMPT` polarity clause | 7 |
| `data-pipeline/scripts/test_head_polarity_prompts.py` | both prompts carry the clause | 7 |

---

### Task 1: Backend — `tags[]` + `bad_head` on `JudgementRecord`

**Files:**
- Modify: `data-pipeline/grading_sidecar/models.py` (after line 22 `Tier`; in `JudgementRecord` after `tiers` ~line 92; in `normalise_judgement` ~lines 141-144)
- Test: `data-pipeline/grading_sidecar/tests/test_models.py` (append)

- [ ] **Step 1: Write the failing tests** — append to `test_models.py`:

```python
# --- W3: structured tags[] (merge/padding/leap/bad_head/other), multi-select ---

def test_judgement_accepts_multiple_tags():
    r = JudgementRecord(schema_version="judgement.v2", judged_by="op", round=1,
        topic="anger", topic_synset_id="1", vehicle="volcano", vehicle_synset_id="2",
        proposer="sonnet_v1", chain_signature="a"*64, linkage="good", metaphor="live",
        tags=["padding", "bad_head"])
    assert r.tags == ["padding", "bad_head"]

def test_judgement_tags_default_empty():
    r = JudgementRecord(schema_version="judgement.v2", judged_by="op", round=1,
        topic="t", topic_synset_id="1", vehicle="v", vehicle_synset_id="2",
        proposer="p", chain_signature="a"*64, linkage="good", metaphor="dead")
    assert r.tags == []

def test_judgement_rejects_unknown_tag():
    with pytest.raises(Exception):
        JudgementRecord(schema_version="judgement.v2", judged_by="op", round=1,
            topic="t", topic_synset_id="1", vehicle="v", vehicle_synset_id="2",
            proposer="p", chain_signature="a"*64, linkage="good", metaphor="live",
            tags=["bogus"])

def test_normalise_judgement_v2_returns_tags_list():
    assert normalise_judgement({"linkage": "good", "metaphor": "live", "tags": ["bad_head"]})["tags"] == ["bad_head"]
    assert normalise_judgement({"linkage": "good", "metaphor": "dead"})["tags"] == []

def test_normalise_judgement_v1_returns_empty_tags():
    assert normalise_judgement({"label": "live"})["tags"] == []
```

- [ ] **Step 2: Run to verify failure**

Run: `PY data-pipeline/grading_sidecar/tests/test_models.py`
Expected: FAIL — `JudgementRecord` has no `tags` field / `normalise_judgement` output lacks `tags`.

- [ ] **Step 3: Implement** — in `models.py`, after the `Tier` line (22):

```python
# Structured issue tags — orthogonal to the verdict axes. `bad_head` flags a
# mis-extracted head concept (a data-prep error), kept distinct from a `bad`
# linkage verdict so head-extraction noise stays out of the metaphor signal.
Tag = Literal["merge", "padding", "leap", "bad_head", "other"]
```

In `JudgementRecord`, add immediately after the `tiers` field (line 92):

```python
    tags: list[Tag] = Field(default_factory=list)
```

Replace the body of `normalise_judgement` (lines 141-144):

```python
    if "linkage" in raw or "metaphor" in raw:
        return {**raw, "tiers": raw.get("tiers", []), "tags": raw.get("tags", [])}
    linkage, metaphor = _V1_LABEL_MAP.get(raw.get("label"), (None, None))
    return {**raw, "linkage": linkage, "metaphor": metaphor, "tiers": [], "tags": []}
```

- [ ] **Step 4: Run to verify pass**

Run: `PY data-pipeline/grading_sidecar/tests/test_models.py`
Expected: PASS (all, including pre-existing).

- [ ] **Step 5: Commit**

```bash
git add data-pipeline/grading_sidecar/models.py data-pipeline/grading_sidecar/tests/test_models.py
git commit -m "feat(grading): structured tags[] (+bad_head) on JudgementRecord"
```

---

### Task 2: Frontend types + end-to-end `tags` plumbing

Adds `tags` to the TS contract and threads it panel→app, with no UI yet (keeps `tsc` green). The old notes-prefix chip UI stays until Task 3.

**Files:**
- Modify: `web/src/types/grading.ts`
- Modify: `web/src/components/mf-grade-panel.ts` (state + `_submit` only)
- Modify: `web/src/components/mf-app.ts` (`handleVerdictSubmit` line 628 area)
- Test: `web/src/types/grading.test.ts` (append); `web/src/components/mf-grade-panel.test.ts` (append one emit test)

- [ ] **Step 1: Write failing type tests** — append to `web/src/types/grading.test.ts`:

```typescript
import { normaliseJudgement, TAGS } from './grading';

describe('normaliseJudgement tags (W3)', () => {
  it('v2 record returns its tags', () => {
    expect(normaliseJudgement({ linkage: 'good', metaphor: 'live', tags: ['bad_head'] }).tags).toEqual(['bad_head']);
  });
  it('v2 record without tags defaults to empty', () => {
    expect(normaliseJudgement({ linkage: 'good', metaphor: 'dead' }).tags).toEqual([]);
  });
  it('v1 label record returns empty tags', () => {
    expect(normaliseJudgement({ label: 'live' }).tags).toEqual([]);
  });
  it('TAGS vocabulary includes bad_head', () => {
    expect(TAGS).toContain('bad_head');
  });
});
```

(If `grading.test.ts` already imports `describe/it/expect` from vitest at top, do not duplicate the import; reuse it.)

- [ ] **Step 2: Run to verify failure**

Run: `FE-TEST src/types/grading.test.ts`
Expected: FAIL — `TAGS` not exported; `.tags` undefined on result.

- [ ] **Step 3: Implement types** — in `web/src/types/grading.ts`, after the `Tier` line (8):

```typescript
// Structured issue tags — orthogonal to the verdict axes. `bad_head` flags a
// mis-extracted head concept (a data-prep error), kept distinct from a `bad`
// linkage verdict so head-extraction noise stays out of the metaphor signal.
export type Tag = 'merge' | 'padding' | 'leap' | 'bad_head' | 'other';
export const TAGS: readonly Tag[] = ['merge', 'padding', 'leap', 'bad_head', 'other'] as const;
```

Add `tags: Tag[];` immediately after `tiers: Tier[];` in **all three** interfaces — `JudgementRecord` (after line 46), `VerdictSubmitDetail` (after line 57), `NormalisedJudgement` (after line 72).

Replace `normaliseJudgement` (lines 87-101):

```typescript
export function normaliseJudgement(
    raw: { linkage?: Linkage; metaphor?: MetaphorVerdict; tiers?: Tier[]; tags?: Tag[]; label?: Label },
): NormalisedJudgement {
    if (raw.linkage !== undefined || raw.metaphor !== undefined) {
        return {
            linkage: raw.linkage ?? null,
            metaphor: raw.metaphor ?? null,
            tiers: raw.tiers ?? [],
            tags: raw.tags ?? [],
        };
    }
    const [linkage, metaphor] = raw.label
        ? V1_LABEL_MAP[raw.label]
        : [null, null];
    return { linkage, metaphor, tiers: [], tags: [] };
}
```

- [ ] **Step 4: Plumb panel emit** — in `web/src/components/mf-grade-panel.ts`:

Add `Tag` to the type import (line 3): `...Tier, Tag, Confidence, VerdictSubmitDetail }`.

Add state after `selectedTiers` (line 97):

```typescript
    // Multi-select issue tags — orthogonal to verdict axes, always available.
    @state() private selectedTags: Tag[] = [];
```

In `_submit` (lines 141-147), add `tags` to the detail:

```typescript
        const detail: VerdictSubmitDetail = {
            linkage: this.pendingLinkage,
            metaphor,
            tiers,
            tags: this.selectedTags,
            confidence: this.confidence,
            notes: this.notes,
        };
```

Add a reset alongside the existing ones (after line 155 `this.selectedTiers = [];`):

```typescript
        this.selectedTags = [];
```

- [ ] **Step 5: Plumb app persist** — in `web/src/components/mf-app.ts` `handleVerdictSubmit`, add `tags` to the judgement literal (after `tiers: e.detail.tiers,` line 628):

```typescript
      tags: e.detail.tags,
```

- [ ] **Step 6: Add a panel emit test** — append to `mf-grade-panel.test.ts` (inside the `describe`):

```typescript
    it('a submit carries a tags array (empty by default)', async () => {
        let d: any = null;
        el.addEventListener('verdict-submit', (e: any) => d = e.detail);
        document.dispatchEvent(new KeyboardEvent('keydown', { key: 'l' })); await tick();
        expect(d.tags).toEqual([]);
    });
```

- [ ] **Step 7: Fix any fixture type errors, then run tests + types**

Run: `FE-TYPES`
If `tsc` reports `tags` missing on a `JudgementRecord` object literal (only where a variable/property is *typed* as `JudgementRecord`, not `as any`), add `tags: []` to that literal. Candidate spots to check: `mf-force-graph.test.ts` `GRADED_JUDGEMENT` (~741) and `base` (~601) if assigned to the typed `.judgements` prop. (`mf-app.test.ts` fixtures use `(el as any)` and won't error.)

Run: `FE-TEST src/types/grading.test.ts` and `FE-TEST src/components/mf-grade-panel.test.ts`
Expected: PASS. `FE-TYPES`: clean.

- [ ] **Step 8: Commit**

```bash
git add web/src/types/grading.ts web/src/types/grading.test.ts web/src/components/mf-grade-panel.ts web/src/components/mf-app.ts web/src/components/mf-grade-panel.test.ts
# plus any *.test.ts fixtures touched in Step 7
git commit -m "feat(grading): thread tags[] through TS types, panel emit, app persist"
```

---

### Task 3: `mf-grade-panel` — tags pill row (replace notes-prefix)

**Files:**
- Modify: `web/src/components/mf-grade-panel.ts`
- Test: `web/src/components/mf-grade-panel.test.ts`

- [ ] **Step 1: Write failing tests** — in `mf-grade-panel.test.ts`, **remove** the test `'tag chip prepends tag prefix to notes'` (lines 159-165) and add:

```typescript
    const clickTag = async (tag: string) => {
        (el.shadowRoot!.querySelector(`[data-testid="chip-${tag}"]`) as HTMLElement).click();
        await el.updateComplete;
    };
    const tagSelected = (tag: string) =>
        (el.shadowRoot!.querySelector(`[data-testid="chip-${tag}"]`) as HTMLElement)
            .classList.contains('selected');

    it('exposes bad_head as a tag chip', () => {
        expect(el.shadowRoot!.querySelector('[data-testid="chip-bad_head"]')).toBeTruthy();
    });

    it('clicking tag chips multi-selects (toggle on/off)', async () => {
        await clickTag('padding');
        await clickTag('bad_head');
        expect(tagSelected('padding')).toBe(true);
        expect(tagSelected('bad_head')).toBe(true);
        expect(tagSelected('merge')).toBe(false);
        await clickTag('padding'); // toggle off
        expect(tagSelected('padding')).toBe(false);
        expect(tagSelected('bad_head')).toBe(true);
    });

    it('a submit carries the selected tags as an array', async () => {
        let d: any = null;
        el.addEventListener('verdict-submit', (e: any) => d = e.detail);
        await clickTag('leap');
        await clickTag('bad_head');
        document.dispatchEvent(new KeyboardEvent('keydown', { key: 'd' })); await tick();
        expect(d.tags).toEqual(['leap', 'bad_head']);
    });

    it('selected tags reset after a submit', async () => {
        const captures: any[] = [];
        el.addEventListener('verdict-submit', (e: any) => captures.push(e.detail));
        await clickTag('merge');
        document.dispatchEvent(new KeyboardEvent('keydown', { key: 'l' })); await tick();
        document.dispatchEvent(new KeyboardEvent('keydown', { key: 'l' })); await tick();
        expect(captures.map(c => c.tags)).toEqual([['merge'], []]);
    });
```

- [ ] **Step 2: Run to verify failure**

Run: `FE-TEST src/components/mf-grade-panel.test.ts`
Expected: FAIL — chips have no `selected` class / no `chip-bad_head`.

- [ ] **Step 3: Implement** — in `mf-grade-panel.ts`:

Add a value import below the existing imports (line 3 region):

```typescript
import { TAGS } from '../types/grading';
```

Remove the `const TAG_CHIPS = [...] as const;` line (26). Remove the `_addTag` method (lines 173-180). Add `_toggleTag`:

```typescript
    private _toggleTag(tag: Tag) {
        // Multi-select toggle: clicking a selected chip removes only it.
        this.selectedTags = this.selectedTags.includes(tag)
            ? this.selectedTags.filter(t => t !== tag)
            : [...this.selectedTags, tag];
    }
```

Add a `.chip.selected` rule to `static styles` (after the `button.chip {...}` block, line 69):

```css
        button.chip.selected { background: #2a3140; color: #fff; border-color: #6db86d; }
```

Replace the `.chips` render block (lines 237-241):

```html
            <div class="chips">
                <span class="group-label">Tags:</span>
                ${TAGS.map(tag => html`
                    <button class="chip ${this.selectedTags.includes(tag) ? 'selected' : ''}"
                            data-testid="chip-${tag}"
                            @click=${() => this._toggleTag(tag)}>${tag}</button>
                `)}
            </div>
```

- [ ] **Step 4: Run to verify pass**

Run: `FE-TEST src/components/mf-grade-panel.test.ts` and `FE-TYPES`
Expected: PASS / clean.

- [ ] **Step 5: Commit**

```bash
git add web/src/components/mf-grade-panel.ts web/src/components/mf-grade-panel.test.ts
git commit -m "feat(grading): structured tag pills (multi-select) replace notes-prefix"
```

---

### Task 4: `mf-app` — `priorVerdict()` confidence+tags + `supersedes_ts` wiring

**Files:**
- Modify: `web/src/components/mf-app.ts` (`priorVerdict` lines 688-704; `handleVerdictSubmit` line 616-632)
- Test: `web/src/components/mf-app.test.ts`

- [ ] **Step 1: Write failing tests** — in `mf-app.test.ts`, inside the `describe('prior notes in re-grade banner (C3)', ...)` block (the `judgement` factory at line 1173 already defaults `tiers: []`), add:

```typescript
    it('threads confidence and tags into the priorVerdict prop', async () => {
      ;(el as any).mode = 'grade'
      ;(el as any).viewportWidth = 1200
      ;(el as any).gradeChains = [chain]
      ;(el as any).gradeJudgements = [
        judgement({ confidence: 'med', tags: ['leap', 'bad_head'], ts: '2026-05-31T00:00:00Z' }),
      ]
      ;(el as any).selectedChain = chain
      await el.updateComplete
      const panel = el.shadowRoot!.querySelector('mf-grade-panel') as any
      expect(panel.priorVerdict.confidence).toBe('med')
      expect(panel.priorVerdict.tags).toEqual(['leap', 'bad_head'])
    })

    it('a re-grade sets supersedes_ts to the prior verdict ts', async () => {
      ;(el as any).mode = 'grade'
      ;(el as any).gradeChains = [chain]
      ;(el as any).gradeJudgements = [judgement({ ts: '2026-05-30T00:00:00Z' })]
      ;(el as any).selectedChain = chain
      await el.updateComplete
      const postSpy = vi.spyOn((el as any).gradingClient, 'postJudgement').mockResolvedValue({} as any)
      vi.spyOn((el as any).gradingClient, 'getJudgements').mockResolvedValue({ count: 0, records: [] })
      await (el as any).handleVerdictSubmit(new CustomEvent('verdict-submit', {
        detail: { linkage: 'good', metaphor: 'dead', tiers: [], tags: [], confidence: 'high', notes: '' },
      }))
      expect(postSpy.mock.calls[0][0].supersedes_ts).toBe('2026-05-30T00:00:00Z')
      postSpy.mockRestore()
    })

    it('a first grade (no prior) sets supersedes_ts null', async () => {
      ;(el as any).mode = 'grade'
      ;(el as any).gradeChains = [chain]
      ;(el as any).gradeJudgements = []
      ;(el as any).selectedChain = chain
      await el.updateComplete
      const postSpy = vi.spyOn((el as any).gradingClient, 'postJudgement').mockResolvedValue({} as any)
      vi.spyOn((el as any).gradingClient, 'getJudgements').mockResolvedValue({ count: 0, records: [] })
      await (el as any).handleVerdictSubmit(new CustomEvent('verdict-submit', {
        detail: { linkage: 'good', metaphor: 'live', tiers: [], tags: [], confidence: 'high', notes: '' },
      }))
      expect(postSpy.mock.calls[0][0].supersedes_ts).toBeNull()
      postSpy.mockRestore()
    })
```

- [ ] **Step 2: Run to verify failure**

Run: `FE-TEST src/components/mf-app.test.ts`
Expected: FAIL — `priorVerdict` lacks `confidence`/`tags`; `supersedes_ts` is hardcoded `null`.

- [ ] **Step 3: Implement** — in `mf-app.ts`:

Add `Tag, Confidence` to the grading type import (the line importing `Linkage, MetaphorVerdict, Tier, ...`).

Replace `priorVerdict` (lines 688-704):

```typescript
  private priorVerdict(
    chain: ChainRecord,
  ): { linkage: Linkage; metaphor: MetaphorVerdict; tiers: Tier[]; tags: Tag[]; confidence: Confidence; ts: string; notes: string } | null {
    let latest: JudgementRecord | null = null
    for (const j of this.gradeJudgements) {
      if (j.chain_signature === chain.chain_signature) latest = j
    }
    if (!latest) return null
    const { linkage, metaphor, tiers, tags } = normaliseJudgement(latest)
    return {
      linkage: linkage ?? 'bad',
      metaphor: metaphor ?? 'irrelevant',
      tiers,
      tags,
      confidence: latest.confidence ?? 'high',
      ts: latest.ts ?? '',
      notes: latest.notes ?? '',
    }
  }
```

In `handleVerdictSubmit`, compute the prior before building the judgement (insert after line 615 `const chain = this.selectedChain`):

```typescript
    const prior = this.priorVerdict(chain)
```

and change `supersedes_ts: null,` (line 631) to:

```typescript
      supersedes_ts: prior?.ts ?? null,
```

- [ ] **Step 4: Run to verify pass**

Run: `FE-TEST src/components/mf-app.test.ts` and `FE-TYPES`
Expected: PASS / clean.

- [ ] **Step 5: Commit**

```bash
git add web/src/components/mf-app.ts web/src/components/mf-app.test.ts
git commit -m "feat(grading): priorVerdict carries confidence+tags; wire supersedes_ts on re-grade"
```

---

### Task 5: `mf-grade-panel` — prefill + last-saved line + was-prior marker

**Files:**
- Modify: `web/src/components/mf-grade-panel.ts`
- Test: `web/src/components/mf-grade-panel.test.ts`

- [ ] **Step 1: Write failing tests** — in `mf-grade-panel.test.ts`, **remove** the two banner tests (`'re-grade banner shows prior ...'` and `'renders no prior-notes line ...'`, lines 141-157) and add (place after the `tagSelected` helper from Task 3 so it's in scope):

```typescript
    const PRIOR = {
        linkage: 'bad' as const, metaphor: 'dead' as const,
        tiers: ['strong', 'surprising'], tags: ['leap', 'bad_head'],
        confidence: 'med' as const, notes: 'cliché', ts: '2026-05-31T14:22:00Z',
    };
    const setPrior = async (over: Record<string, unknown> = {}) => {
        el.priorVerdict = { ...PRIOR, tiers: [...PRIOR.tiers], tags: [...PRIOR.tags], ...over } as any;
        await el.updateComplete;
    };

    it('prefills all editable fields from the prior verdict', async () => {
        await setPrior();
        expect((el.shadowRoot!.querySelector('[data-testid="linkage-toggle"]') as HTMLElement).classList.contains('bad')).toBe(true);
        expect(tierSelected('strong')).toBe(true);
        expect(tierSelected('surprising')).toBe(true);
        expect(tagSelected('leap')).toBe(true);
        expect(tagSelected('bad_head')).toBe(true);
        const medBtn = [...el.shadowRoot!.querySelectorAll('button.conf')].find(b => b.textContent!.includes('Med'))!;
        expect(medBtn.classList.contains('active')).toBe(true);
        expect((el.shadowRoot!.querySelector('textarea') as HTMLTextAreaElement).value).toBe('cliché');
    });

    it('shows a muted last-saved line with summary + timestamp', async () => {
        await setPrior();
        const line = el.shadowRoot!.querySelector('[data-testid="last-saved"]')!.textContent!;
        expect(line).toContain('bad');
        expect(line).toContain('dead');
        expect(line).toContain('strong');
        expect(line).toContain('leap');
        expect(line).toContain('2026-05-31 14:22');
    });

    it('marks the previously-chosen metaphor button as was-prior', async () => {
        await setPrior();
        expect((el.shadowRoot!.querySelector('[data-testid="metaphor-dead"]') as HTMLElement).classList.contains('was-prior')).toBe(true);
        expect((el.shadowRoot!.querySelector('[data-testid="metaphor-live"]') as HTMLElement).classList.contains('was-prior')).toBe(false);
    });

    it('a re-grade submit retains the prefilled tiers/tags/notes/linkage/confidence', async () => {
        let d: any = null;
        el.addEventListener('verdict-submit', (e: any) => d = e.detail);
        await setPrior({ metaphor: 'live', tiers: ['strong'], tags: ['bad_head'] });
        document.dispatchEvent(new KeyboardEvent('keydown', { key: 'l' })); await tick();
        expect(d.tiers).toEqual(['strong']);
        expect(d.tags).toEqual(['bad_head']);
        expect(d.notes).toBe('cliché');
        expect(d.linkage).toBe('bad');
        expect(d.confidence).toBe('med');
    });

    it('does not clobber in-progress edits when priorVerdict identity changes but ts is unchanged', async () => {
        await setPrior({ notes: 'original' });
        const ta = el.shadowRoot!.querySelector('textarea') as HTMLTextAreaElement;
        ta.value = 'my edit'; ta.dispatchEvent(new Event('input'));
        await el.updateComplete;
        await setPrior({ notes: 'original' }); // new object, same ts
        expect((el.shadowRoot!.querySelector('textarea') as HTMLTextAreaElement).value).toBe('my edit');
    });

    it('clears the form when switching to an ungraded chain (priorVerdict null)', async () => {
        await setPrior();
        el.priorVerdict = null;
        await el.updateComplete;
        expect(tierSelected('strong')).toBe(false);
        expect(tagSelected('leap')).toBe(false);
        expect((el.shadowRoot!.querySelector('textarea') as HTMLTextAreaElement).value).toBe('');
    });
```

- [ ] **Step 2: Run to verify failure**

Run: `FE-TEST src/components/mf-grade-panel.test.ts`
Expected: FAIL — no prefill; no `last-saved` testid; no `was-prior` class.

- [ ] **Step 3: Implement** — in `mf-grade-panel.ts`:

Import `PropertyValues` from lit (line 1): `import { LitElement, html, css, type PropertyValues } from 'lit';`

Extend the `PriorVerdict` interface (lines 6-12):

```typescript
interface PriorVerdict {
    linkage: Linkage;
    metaphor: MetaphorVerdict;
    tiers: Tier[];
    tags: Tag[];
    confidence: Confidence;
    ts: string;
    notes: string;
}
```

Add a private guard field (after `selectedTags`):

```typescript
    // Stable identity of the prior record we last prefilled from. Keyed on `ts`
    // so an mf-app re-render handing us a fresh-but-equal priorVerdict object
    // never re-syncs over in-progress edits — only a genuinely new record does.
    private _prefilledForTs: string | null = null;
```

Add `willUpdate` and a ts formatter (place near the other private methods):

```typescript
    protected willUpdate(changed: PropertyValues<this>): void {
        if (!changed.has('priorVerdict')) return;
        const pv = this.priorVerdict;
        const key = pv?.ts ?? null;
        if (key === this._prefilledForTs) return;
        this._prefilledForTs = key;
        if (pv) {
            this.pendingLinkage = pv.linkage;
            this.confidence = pv.confidence;
            this.selectedTiers = [...pv.tiers];
            this.selectedTags = [...pv.tags];
            this.notes = pv.notes;
        } else {
            this.pendingLinkage = 'good';
            this.confidence = 'high';
            this.selectedTiers = [];
            this.selectedTags = [];
            this.notes = '';
        }
    }

    // ISO-8601 → "YYYY-MM-DD HH:MM" by slice (deterministic; no Date/locale).
    private _fmtTs(ts: string): string {
        return ts.slice(0, 16).replace('T', ' ');
    }
```

Replace the banner styles — remove `.banner {...}` (75-78) and `.banner .prior-notes {...}` (79-82); add:

```css
        .last-saved { color: #8a93a2; font-size: 0.78rem; margin-bottom: 0.5rem; }
        .last-saved strong { color: #b8bfca; font-weight: 600; }
        button.verdict.was-prior { box-shadow: inset 0 0 0 2px #4d5566; }
```

Replace the banner render block (lines 186-197) with the muted last-saved line:

```html
            ${this.priorVerdict ? html`
                <div class="last-saved" data-testid="last-saved">
                    last saved:
                    <strong>${this.priorVerdict.linkage}</strong>/<strong>${this.priorVerdict.metaphor}</strong>${this.priorVerdict.tiers.length
                        ? html` · ${this.priorVerdict.tiers.join(', ')}` : ''}${this.priorVerdict.tags.length
                        ? html` · ${this.priorVerdict.tags.join(', ')}` : ''}
                    · ${this._fmtTs(this.priorVerdict.ts)}
                </div>
            ` : ''}
```

Add the `was-prior` class to each metaphor button (lines 205-210):

```html
                <button class="verdict live ${this.priorVerdict?.metaphor === 'live' ? 'was-prior' : ''}" data-testid="metaphor-live"
                        @click=${() => this._submit('live')}>Live<kbd>L</kbd></button>
                <button class="verdict dead ${this.priorVerdict?.metaphor === 'dead' ? 'was-prior' : ''}" data-testid="metaphor-dead"
                        @click=${() => this._submit('dead')}>Dead<kbd>D</kbd></button>
                <button class="verdict irrelevant ${this.priorVerdict?.metaphor === 'irrelevant' ? 'was-prior' : ''}" data-testid="metaphor-irrelevant"
                        @click=${() => this._submit('irrelevant')}>Irrelevant<kbd>I</kbd></button>
```

> **Implementation note (spec reconciliation):** `_submit`'s existing resets (`pendingLinkage='good'`, `selectedTiers=[]`, `selectedTags=[]`) are **retained**. They don't conflict with the ts-keyed prefill: prefill drives displayed state on every *selection* (the spec's single-source-of-truth intent), while the resets only matter for the rare same-instance double-submit (which in real use unmounts the panel via `selectedChain=null`). Keeping them keeps the Task-2/3 reset tests green.

- [ ] **Step 4: Run to verify pass**

Run: `FE-TEST src/components/mf-grade-panel.test.ts` and `FE-TYPES`
Expected: PASS / clean. (The Task-2/3 reset tests still pass — they set no `priorVerdict`, so `willUpdate` skips prefill and `_submit` resets apply.)

- [ ] **Step 5: Commit**

```bash
git add web/src/components/mf-grade-panel.ts web/src/components/mf-grade-panel.test.ts
git commit -m "feat(grading): prefill form from prior verdict (ts-keyed) + muted last-saved line + was-prior marker"
```

---

### Task 6: `mf-force-graph` — no re-heat on verdict submit

**Files:**
- Modify: `web/src/components/mf-force-graph.ts` (`updated()` lines 567-583)
- Test: `web/src/components/mf-force-graph.test.ts`

- [ ] **Step 1: Write the failing test** — in `mf-force-graph.test.ts`, mirror the existing no-bounce test (line 774). Add inside the same `describe` that defines `GRADED_JUDGEMENT` (line 741) and uses `gradeEl`:

```typescript
    it('a new verdict re-applies styles + visibility WITHOUT a graphData re-feed (no re-heat)', async () => {
      gradeEl.judgements = []
      await gradeEl.updateComplete
      const feedsBefore = graphDataSetCount
      // A verdict arrives (mf-app refetch reassigns the judgements array).
      gradeEl.judgements = [GRADED_JUDGEMENT]
      await gradeEl.updateComplete
      // No graphData(data) setter call → the d3 force sim is not restarted.
      expect(graphDataSetCount).toBe(feedsBefore)
      // The edge colour map reflects the new verdict (read through the getter).
      expect((gradeEl as any).getEdgeColour(GRADED_JUDGEMENT.chain_signature)).not.toBeNull()
    })
```

- [ ] **Step 2: Run to verify failure**

Run: `FE-TEST src/components/mf-force-graph.test.ts`
Expected: FAIL — current `updated()` calls `feedGraph()` on `judgements` change, so `graphDataSetCount` increments.

- [ ] **Step 3: Implement** — replace the `updated()` body (lines 567-583):

```typescript
  updated(changed: PropertyValues<this>): void {
    // Topology-affecting changes need a full re-feed (which restarts the sim).
    const topologyChanged =
      changed.has('graphData') || changed.has('mode') || changed.has('gradeChains')
    if (this.graph && topologyChanged) {
      this.feedGraph()
    } else if (this.graph && changed.has('judgements')) {
      // A verdict changed but the node/link set did not. Edge colour rides the
      // linkColor accessor (getEdgeColour reads the latestVerdicts getter) and
      // the path filter reads the same getter — so re-evaluating styles +
      // visibility in place reflects the new verdict WITHOUT graphData(), and
      // the force sim never re-heats. Under the 'ungraded' filter this also
      // hides the now-graded path.
      this.refreshLinkStyles()
      this.reapplyVisibility()
    }
    // Visibility filters toggle already-fed objects in place (no re-feed).
    if ((changed.has('pathFilter') || changed.has('hiddenRarities')) && this.graph) {
      this.reapplyVisibility()
    }
  }
```

- [ ] **Step 4: Run to verify pass**

Run: `FE-TEST src/components/mf-force-graph.test.ts` and `FE-TYPES`
Expected: PASS / clean. **Also run the full FE suite** (`cd web && npx vitest run`) to confirm no regression in tests that set `judgements` (e.g. the edge-colour-map test at line 571 reads `getEdgeColour`, independent of feed — should stay green).

- [ ] **Step 5: Commit**

```bash
git add web/src/components/mf-force-graph.ts web/src/components/mf-force-graph.test.ts
git commit -m "fix(grading): update graded path in place on verdict submit (no force-sim re-heat)"
```

---

### Task 7: Head-extraction polarity clauses (Haiku + Sonnet)

Prompt-string edits only. **No re-extraction is run** — the live Round-1 cohort is untouched.

**Files:**
- Modify: `data-pipeline/scripts/head_extraction_backfill.py` (`extract_heads_batch` lines 35-45)
- Modify: `data-pipeline/scripts/metaphor_graph_enrich_sonnet.py` (`SONNET_EDIT_PROMPT` lines 27-51)
- Test: `data-pipeline/scripts/test_head_polarity_prompts.py` (create)

- [ ] **Step 1: Write the failing test** — create `data-pipeline/scripts/test_head_polarity_prompts.py`:

```python
"""W4: both head-generation prompts must carry the polarity/modifier clause so a
phrase like 'resists change' is not reduced to its bare object noun 'change'."""
from __future__ import annotations
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from head_extraction_backfill import HEAD_PROMPT_INSTRUCTIONS
from metaphor_graph_enrich_sonnet import SONNET_EDIT_PROMPT


def test_haiku_head_prompt_has_polarity_clause():
    p = HEAD_PROMPT_INSTRUCTIONS.lower()
    assert "resists change" in p
    assert "resistance" in p or "stability" in p


def test_sonnet_edit_prompt_has_polarity_clause():
    p = SONNET_EDIT_PROMPT.lower()
    assert "resists change" in p
    assert "polarity" in p or "resistance" in p or "stability" in p
```

- [ ] **Step 2: Run to verify failure**

Run: `PY data-pipeline/scripts/test_head_polarity_prompts.py`
Expected: FAIL — `HEAD_PROMPT_INSTRUCTIONS` does not exist yet (ImportError); clause absent.

- [ ] **Step 3: Implement Haiku** — in `head_extraction_backfill.py`, add a module-level constant above `extract_heads_batch` (after line 28 `HAIKU_MODEL = ...`):

```python
HEAD_PROMPT_INSTRUCTIONS = (
    "For each phrase below, return the single-word concept that the phrase "
    "most centres on — typically a noun. Prefer a head likely to be re-used "
    "across other metaphor traversals over a hyper-specific one. "
    "Preserve modifiers that flip or invert meaning: a negation, opposition, or "
    "relational modifier changes the head — 'resists change' -> 'resistance' or "
    "'stability', not 'change'; 'avoids risk' -> 'caution', not 'risk'. Prefer a "
    "single word that still names a common concept so it resolves to a synset.\n\n"
)
```

Rewrite the prompt assembly inside `extract_heads_batch` (lines 37-43) to use it:

```python
    prompt = (
        HEAD_PROMPT_INSTRUCTIONS
        + "Output strict JSON: {\"phrases\": [{\"phrase\": \"...\", \"head\": \"...\"}, ...]}\n\n"
        + "Phrases:\n" + "\n".join(f"- {p}" for p in phrases)
    )
```

- [ ] **Step 4: Implement Sonnet** — in `metaphor_graph_enrich_sonnet.py`, add a clause to `SONNET_EDIT_PROMPT` immediately after the "Return 10 vehicles, each with 3-6 one-word path concepts ..." paragraph (after line 42):

```
Each path concept must preserve the source phrase's semantic polarity: never
reduce a phrase to a bare object noun when a negation or opposing modifier flips
its meaning (e.g. "resists change" -> "resistance"/"stability", not "change").
```

(Insert as a new paragraph in the triple-quoted string; keep the existing JSON block below it.)

- [ ] **Step 5: Run to verify pass**

Run: `PY data-pipeline/scripts/test_head_polarity_prompts.py`
Expected: PASS.
(If importing `head_extraction_backfill` fails on an unrelated heavy dependency, that is a pre-existing env issue — the sibling `data-pipeline/scripts/test_build_next_round_prompt.py` imports comparable modules, so the env supports it; restore the venv per Pre-flight.)

- [ ] **Step 6: Commit**

```bash
git add data-pipeline/scripts/head_extraction_backfill.py data-pipeline/scripts/metaphor_graph_enrich_sonnet.py data-pipeline/scripts/test_head_polarity_prompts.py
git commit -m "feat(pipeline): polarity/modifier clause in Haiku + Sonnet head prompts (no re-extraction)"
```

---

## Final verification (after all tasks)

- [ ] Full Python: `PY data-pipeline/grading_sidecar/tests/ data-pipeline/scripts/test_head_polarity_prompts.py`
- [ ] Full frontend: `cd web && npx vitest run` (all green) + `npx tsc --noEmit` (clean)
- [ ] (Optional) e2e sanity: `cd web && npx playwright test` — the unit test in Task 6 is the primary no-reheat guard; the e2e suite must still pass.
- [ ] Update memory `grading_ux_round2_landed.md` → note round-3 affordances (no-reheat, prefill, tags[], bad_head, polarity prompts) and that no re-extraction was run.
- [ ] Capture deferred items in `docs/roadmap/PIPELINE.md` inbox: head re-extraction at a round boundary; route head extraction through Sonnet (next head milestone); optional notes-prefix→tags[] migration script.
- [ ] Use `superpowers:finishing-a-development-branch` to land (PR to base, per git discipline — no direct merge to main).

## Notes / gotchas (from the grounded read)

- **happy-dom mock:** `mf-force-graph.test.ts` already provides a chainable Proxy mock and `graphDataSetCount` (setter-call counter). Reuse it — do not re-mock.
- **Lit templates aren't tsc-checked:** changing `PriorVerdict` (panel) doesn't error at mf-app's `.priorVerdict=${...}` binding. Runtime shape is supplied by Task 4's `priorVerdict()`.
- **`latestVerdicts` is a getter** (mf-force-graph:242) — derived from the `judgements` prop on access, so Task 6's in-place refresh sees fresh verdicts with no rebuild step.
- **Data safety:** no test or step writes live grading JSONL; W4 changes prompt strings only and runs no extraction.
