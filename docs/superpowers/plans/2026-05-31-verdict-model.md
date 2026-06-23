# Two-Axis Verdict Model Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Replace the flat grading `label` with two orthogonal axes — `linkage` (good/bad) + `metaphor` (live/dead/irrelevant) — plus an optional single-select `tier`, across the Python sidecar and the Lit frontend, keeping v1 records readable.

**Architecture:** `JudgementRecord` v2 (`judgement.v2`) carries `linkage` + `metaphor` + nullable `tier` instead of `label`. A normaliser maps v1 `label` → the two axes on read, so old data and new data coexist. The grade panel becomes two-tap (linkage defaults `good`; a modifier marks `bad`; a metaphor key submits), tier optional. Edge colour is derived from `(linkage, metaphor)`. Verdicts stay bridge-scoped (`chain_signature`) — never on a node.

**Tech Stack:** Python 3.12 + Pydantic v2 (`data-pipeline/grading_sidecar/`), Lit 3 + TS + Vitest (`web/`). Spec: `docs/superpowers/specs/2026-05-31-verdict-model-design.md` (read it). TDD throughout; commit on green. UK English.

**Test commands:** Python — `cd data-pipeline && .venv/bin/python -m pytest grading_sidecar/ scripts/ -q` (or the repo's venv). Frontend — `cd web && npx vitest run` (targeted: `-t "..."`), `npx tsc --noEmit`. Tasks 3–6 are a transitional cluster (the TS type change in T3 breaks consumers until T4–T6 land); the FULL frontend suite is green only at T7 — run targeted tests within the cluster.

---

## Task 1: Backend — `JudgementRecord` v2 + v1 read-compat normaliser

**Files:** Modify `data-pipeline/grading_sidecar/models.py`; Test `data-pipeline/grading_sidecar/test_models.py` (or the existing model test file).

- [ ] **Step 1: Write failing tests**

```python
def test_v2_record_roundtrips_two_axes_and_optional_tier():
    rec = JudgementRecord(
        schema_version="judgement.v2", judged_by="julian", round=1,
        topic="anchor", topic_synset_id="syn-anchor", vehicle="stone",
        vehicle_synset_id="syn-stone", proposer="sonnet_v1",
        chain_signature="a"*64, linkage="good", metaphor="dead", tier="obvious",
    )
    assert rec.linkage == "good" and rec.metaphor == "dead" and rec.tier == "obvious"

def test_v2_tier_optional_defaults_none():
    rec = JudgementRecord(schema_version="judgement.v2", judged_by="j", round=1,
        topic="t", topic_synset_id="s", vehicle="v", vehicle_synset_id="s2",
        proposer="p", chain_signature="b"*64, linkage="good", metaphor="live")
    assert rec.tier is None

def test_normalise_v1_label_maps_to_axes():
    # v1 record (has `label`, no axes) → normalised dict with linkage+metaphor
    assert normalise_judgement({"schema_version":"judgement.v1","label":"live", **_ID}) \
        |gets| ("good","live", None)
    assert normalise_judgement({"label":"bad_path", **_ID})  |gets| ("bad", None, None)
    assert normalise_judgement({"label":"irrelevant", **_ID}) |gets| (None,"irrelevant",None)
    assert normalise_judgement({"label":"dead", **_ID})       |gets| ("good","dead", None)
```
(Express the `|gets|` checks as plain asserts on the returned `(linkage, metaphor, tier)`. `_ID` = the required identity fields. Adjust to the actual test style in the repo.)

- [ ] **Step 2: Run — verify fail** — `pytest grading_sidecar/test_models.py -q` → FAIL (no `linkage`/`metaphor`/`normalise_judgement`).

- [ ] **Step 3: Implement**

In `models.py`:
```python
Linkage         = Literal["good", "bad"]
MetaphorVerdict = Literal["live", "dead", "irrelevant"]
Tier            = Literal["legendary","complex","interesting","ironic","strong","obvious","unlikely"]
# add "judgement.v2" to JudgementSchemaVersion

class JudgementRecord(BaseModel):
    schema_version: JudgementSchemaVersion
    ts: str = Field(default_factory=lambda: dt.datetime.now(dt.timezone.utc).isoformat())
    judged_by: str
    round: int = Field(ge=1)
    topic: str; topic_synset_id: str; vehicle: str; vehicle_synset_id: str
    proposer: str
    chain_signature: str = Field(pattern=r"^[0-9a-f]{64}$")
    linkage: Linkage
    metaphor: MetaphorVerdict
    tier: Optional[Tier] = None
    confidence: Confidence = "high"
    notes: str = Field(default="", max_length=1000)
    supersedes_ts: Optional[str] = None

_V1_MAP = {  # (linkage, metaphor)
    "live": ("good", "live"), "dead": ("good", "dead"),
    "bad_path": ("bad", None), "irrelevant": (None, "irrelevant"),
}

def normalise_judgement(raw: dict) -> dict:
    """Return a dict carrying linkage/metaphor/tier regardless of v1/v2 source.
    Non-destructive — used on read so old `label` records and new axis records
    are uniform to consumers (latest-verdict, stats, edge colour)."""
    if "linkage" in raw or "metaphor" in raw:
        return {**raw, "tier": raw.get("tier")}
    link, met = _V1_MAP.get(raw.get("label"), (None, None))
    return {**raw, "linkage": link, "metaphor": met, "tier": None}
```
Keep `Label` defined (for reading v1) but new records use the axes.

- [ ] **Step 4: Run — verify pass.** **Step 5: Commit** — `git commit -m "feat(grading): JudgementRecord v2 (linkage+metaphor+tier) with v1 read-compat"`.

---

## Task 2: Backend — routes + validators accept v2, read both

**Files:** Modify `data-pipeline/grading_sidecar/routes/judgements.py` (+ any stats/calibration route reading `label`); `data-pipeline/scripts/validate_grading_jsonl.py`. Test alongside.

- [ ] **Step 1: Write failing tests** — POST a v2 judgement returns 200 and persists `linkage`/`metaphor`/`tier`; GET returns records with axes present for BOTH a seeded v1 line and a v2 line (via `normalise_judgement`); stats/calibration that previously bucketed by `label` now bucket by `metaphor` (and don't crash on v1). `validate_grading_jsonl.py` accepts a v2 line and a v1 line.

- [ ] **Step 2: Run — verify fail.**

- [ ] **Step 3: Implement** — POST validates as `JudgementRecord` (v2); GET maps each stored line through `normalise_judgement` before returning; any aggregation keyed on `label` switches to the normalised `metaphor`/`linkage`. `validate_grading_jsonl.py` validates v2 and still passes v1 lines (via normaliser or dual-schema).

- [ ] **Step 4: Run — verify pass.** **Step 5: Commit** — `git commit -m "feat(grading): sidecar accepts v2 judgements, reads v1+v2 uniformly"`.

---

## Task 3: Frontend types — `grading.ts`

**Files:** Modify `web/src/types/grading.ts`. (Type-only; consumers updated in T4–T6 — targeted tests only.)

- [ ] **Step 1: Implement** (no separate test — `tsc` is the check)

```ts
export type Linkage = 'good' | 'bad'
export type MetaphorVerdict = 'live' | 'dead' | 'irrelevant'
export type Tier =
  | 'legendary' | 'complex' | 'interesting' | 'ironic' | 'strong' | 'obvious' | 'unlikely'

// JudgementRecord: replace `label: Label` with the two axes + optional tier.
// Keep a readonly `Label` alias + a `normaliseJudgement()` mirror of the Python
// normaliser if any TS code reads stored v1 records directly (else omit).
export interface VerdictSubmitDetail {
  linkage: Linkage
  metaphor: MetaphorVerdict
  tier: Tier | null
  confidence: Confidence
  notes: string
}
```
Update `JudgementRecord` to carry `linkage`/`metaphor`/`tier?` instead of `label`.

- [ ] **Step 2: Verify** — `npx tsc --noEmit` will now report errors in `mf-grade-panel`/`mf-app`/`mf-force-graph` (expected — fixed in T4–T6). Confirm the errors are ONLY in those consumers. **Step 3: Commit** — `git commit -m "feat(grading-ui): two-axis verdict types (linkage/metaphor/tier)"`.

---

## Task 4: `mf-grade-panel` — two-axis controls + tier + keybindings + banner

**Files:** Modify `web/src/components/mf-grade-panel.ts`; `web/src/components/mf-grade-panel.test.ts`.

**Keybinding contract (fast-path preserved):** `linkage` defaults `good`. `B` toggles a *pending* `linkage:bad` state (visual, does not submit). A metaphor key **submits**: `L`=live, `D`=dead, `I`=irrelevant — emitting `verdict-submit` with `{ linkage (good unless B toggled), metaphor, tier (selected chip or null), confidence }`. `1/2/3` set confidence (unchanged). Tier chips (single-select, only enabled when the pending metaphor would be `live` — i.e. always selectable but cleared/ignored unless `metaphor==='live'`; simplest: tier selectable always, but only sent when metaphor is live). Hotkey trap inside editable fields stays (composedPath check — do not regress).

- [ ] **Step 1: Write failing tests**

```ts
it('L submits linkage:good + metaphor:live by default', async () => {
  let d:any=null; el.addEventListener('verdict-submit',(e:any)=>d=e.detail)
  document.dispatchEvent(new KeyboardEvent('keydown',{key:'l'}))
  await tick(); expect(d).toMatchObject({linkage:'good',metaphor:'live'})
})
it('B then D submits linkage:bad + metaphor:dead', async () => {
  let d:any=null; el.addEventListener('verdict-submit',(e:any)=>d=e.detail)
  document.dispatchEvent(new KeyboardEvent('keydown',{key:'b'})); await tick()
  document.dispatchEvent(new KeyboardEvent('keydown',{key:'d'})); await tick()
  expect(d).toMatchObject({linkage:'bad',metaphor:'dead'})
})
it('selecting a tier chip then L includes the tier', async () => {
  let d:any=null; el.addEventListener('verdict-submit',(e:any)=>d=e.detail)
  ;(el.shadowRoot!.querySelector('[data-testid="tier-legendary"]') as HTMLElement).click()
  await el.updateComplete
  document.dispatchEvent(new KeyboardEvent('keydown',{key:'l'})); await tick()
  expect(d).toMatchObject({metaphor:'live', tier:'legendary'})
})
it('re-grade banner shows prior linkage, metaphor, tier and notes', async () => {
  el.priorVerdict = { linkage:'good', metaphor:'dead', tier:'obvious', notes:'cliché', ts:'2026-05-31T00:00:00Z' }
  await el.updateComplete
  const b = el.shadowRoot!.querySelector('[data-testid="re-grade-banner"]')!.textContent!
  expect(b).toContain('dead'); expect(b).toContain('obvious'); expect(b).toContain('cliché')
})
it('does not fire while typing in an editable field (composedPath trap retained)', async () => {
  let d:any=null; el.addEventListener('verdict-submit',(e:any)=>d=e.detail)
  const ta=document.createElement('textarea'); document.body.appendChild(ta)
  ta.dispatchEvent(new KeyboardEvent('keydown',{key:'l',bubbles:true,composed:true})); await tick()
  expect(d).toBeNull(); ta.remove()
})
```
(`tick = () => new Promise(r=>setTimeout(r,0))`.)

- [ ] **Step 2: Run targeted — verify fail.**
- [ ] **Step 3: Implement** — render a **metaphor** group (Live/Dead/Irrelevant), a **linkage** indicator/toggle (good default; `B` flips bad), optional **tier** chips (`data-testid="tier-<name>"`), confidence `1/2/3`. `_onKeydown`: keep the composedPath editable-field trap; `b` toggles `this.pendingLinkage`; `l/d/i` emit `verdict-submit` with `{linkage:this.pendingLinkage??'good', metaphor, tier:this.selectedTier, confidence}` then reset pending state; `1/2/3` set confidence. Update `priorVerdict` prop type to `{linkage, metaphor, tier, notes, ts}` and render all in the banner.
- [ ] **Step 4: Run targeted — verify pass.** **Step 5: Commit** — `git commit -m "feat(grading-ui): two-axis grade panel (linkage toggle + metaphor submit + tier)"`.

---

## Task 5: `mf-app` — submit payload + priorVerdict v2

**Files:** Modify `web/src/components/mf-app.ts`; its test file.

- [ ] **Step 1: Write failing tests** — `handleVerdictSubmit` builds a v2 `JudgementRecord` (`linkage`/`metaphor`/`tier`, `judged_by:'julian'`, `schema_version:'judgement.v2'`) and enqueues it (pending_judgements); `priorVerdict` passed to the panel is the LATEST judgement for the selected chain mapped to `{linkage, metaphor, tier, notes, ts}`.

- [ ] **Step 2: Run — verify fail.**
- [ ] **Step 3: Implement** — update `handleVerdictSubmit(detail: VerdictSubmitDetail)` to assemble the v2 record (drop `label`); update the pending-queue payload; compute `priorVerdict` from the latest judgement (using `normaliseJudgement` if reading stored v1) → the v2 shape the panel now expects.
- [ ] **Step 4: Run — verify pass.** **Step 5: Commit** — `git commit -m "feat(grading-ui): mf-app emits v2 judgements + v2 priorVerdict"`.

---

## Task 6: `mf-force-graph` — edge colour from `(linkage, metaphor)`

**Files:** Modify `web/src/components/mf-force-graph.ts`; its test file.

**Colour key derivation** (preserves the existing `GRADE_EDGE_COLOURS` palette):
- `ungraded` → `#e8e8e8`
- `linkage==='bad'` → `bad_path` colour `#d6a560` (amber — broken route dominates)
- else by metaphor: `live`→`#6db86d`, `dead`→`#c47a7a`, `irrelevant`→`#5a5f6a`

- [ ] **Step 1: Write failing test**

```ts
it('edge colour: linkage bad → amber; good+dead → red; good+live → green; none → ungraded', () => {
  const sig='a'.repeat(64)
  gradeEl.judgements = [{ ...ID(sig), linkage:'bad', metaphor:'live' }]
  expect(gradeEl.getEdgeColour(sig)).toBe('bad_path')      // or the amber hex, per impl
  gradeEl.judgements = [{ ...ID(sig), linkage:'good', metaphor:'dead' }]
  expect(gradeEl.getEdgeColour(sig)).toBe('dead')
  expect(gradeEl.getEdgeColour('missing')).toBe(null)       // ungraded
})
```
(Match the assertion to whether `getEdgeColour` returns the colour KEY or the hex — keep it returning the key, mapped via `GRADE_EDGE_COLOURS` at the call site, as today.)

- [ ] **Step 2: Run — verify fail.**
- [ ] **Step 3: Implement** — `latestVerdicts` already maps `chain_signature → JudgementRecord`; change `getEdgeColour` to derive the key from `(linkage, metaphor)` per the table (return `null` when no verdict, as today so `ungraded` applies). `GRADE_EDGE_COLOURS` keys (`live/dead/bad_path/irrelevant/ungraded`) are unchanged — only the key-derivation changes. `hideGraded` (keys on "has any verdict") is unaffected.
- [ ] **Step 4: Run — verify pass.** **Step 5: Commit** — `git commit -m "feat(grading-ui): edge colour derived from linkage+metaphor"`.

---

## Task 7: Full green + build

**Files:** none new — close-out.

- [ ] **Step 1:** `cd data-pipeline && .venv/bin/python -m pytest grading_sidecar/ scripts/ -q` → all pass.
- [ ] **Step 2:** `cd web && npx vitest run` → all pass (full suite green now). Fix any straggler consumers of the old `label` (grep `web/src` for `\blabel\b` in grading context, `bad_path`, `Label`).
- [ ] **Step 3:** `npx tsc --noEmit` clean; `npm run build` succeeds.
- [ ] **Step 4: Commit** any straggler fixes — `git commit -m "chore(grading): green full suite on two-axis verdict"`.

> **Operator step (not code):** re-grade the ≈5 legacy `anxiety` judgements under v2 (incl. the `anxiety→debt` mis-fire → its correct verdict) once deployed. Calibration gate (~25 grades) is also operator-driven.

---

## Self-Review

**Spec coverage:** two axes (T1,T3,T4); optional tier supplement (T1,T3,T4); bridge-scoped (unchanged — chain_signature keyed); v2 + v1 read-compat + migration map (T1,T2); edge admission keyed on linkage = future SQLite (noted in spec, not this frontend/JSONL plan); UI two-tap fast-path + tier + banner (T4,T5); edge colour two-axis (T6); legacy re-grade = operator step. ✓

**Placeholder scan:** keybinding contract + colour table are concrete; the `|gets|` shorthand in T1 tests is explicitly flagged to be written as plain asserts. No TBDs.

**Type consistency:** `Linkage`/`MetaphorVerdict`/`Tier`/`VerdictSubmitDetail`/`normalise_judgement`/`priorVerdict {linkage,metaphor,tier,notes,ts}`/`getEdgeColour`→key consistent across T1–T6.
