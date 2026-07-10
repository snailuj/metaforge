# Phrase-as-Node Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Land the Phrase-as-Node contract (spec: `docs/superpowers/specs/2026-07-10-phrase-as-node-design.md`) — chain.v2 records (phrase-first nodes, per-occurrence sense-sets, vec: fallback), a per-hop noun-prior snapper + $0 migration, grading-tool consumption, and a judge-harness v2 reader.

**Architecture:** Three build surfaces in three git worktrees, each on its home branch. The JSONL record schema is the contract; SQL is design-only. `chain_signature` is phrase-based and MUST NOT change for any existing record.

**Tech Stack:** Python 3 + Pydantic v2 + pytest (pipeline, sidecar) · Lit + TypeScript + Vitest + Playwright (web) · SQLite read-only lexicon.

## Global Constraints

- **Worktrees (never work outside your assigned one):**
  - W1 pipeline: `/home/agent/projects/metaforge/.worktrees/phrase-as-node` (branch `metaphor-graph/phrase-as-node`)
  - W2 grading: `/home/agent/projects/metaforge/.worktrees/pan-grading` (branch `grading/phrase-as-node`)
  - W3 harness: `/home/agent/projects/metaforge/.worktrees/judge-harness` (branch `metaphor-graph/judge-harness`)
- **Python for W1 + W3 tests:** `/home/agent/projects/metaforge/data-pipeline/.venv/bin/python` (has numpy/sklearn/pydantic). **W2 sidecar tests:** `/home/agent/projects/metaforge/.worktrees/pan-grading/data-pipeline/.venv/bin/python` (created in setup). **W2 web:** `cd web && npx vitest run` / `npm run build`.
- **TDD non-negotiable:** failing test FIRST, watch it fail, minimal code, watch it pass, commit. One commit per green test cycle.
- **NEVER `git add -A` or `git add .`** — stage explicit paths only (repo has large untracked artifacts).
- **`chain_signature` invariant:** `compute_chain_signature(proposer, phrases)` inputs are untouched by every task. Any diff that changes signature computation or the `phrase` values feeding it is a defect.
- **Additive-only schemas:** every existing chain.v1 record and every judgement.v1/v2 record must still validate/read after your change. Test this explicitly.
- **UK English** in comments/docs (optimise, colour). Comments explain intent/constraints, never restate code.
- **No DB writes** — `lexicon_v2.db` is read-only everywhere. **No LLM/API calls** in any task.
- **Do not touch** deploy branches (`grading-code`), `main`, live data under `.worktrees/grading-data/`, or any worktree not assigned to your task.
- **Logging:** vec: admissions, low-confidence snaps, migration skips — log with phrase + position. No silent drops anywhere.

---

## Task 1 (W1): chain.v2 record schema — `grading_sidecar/models.py`

**Files:**
- Modify: `data-pipeline/grading_sidecar/models.py` (ChainSchemaVersion ~line 13, ChainStep ~line 41, ChainRecord ~line 52)
- Test: `data-pipeline/grading_sidecar/tests/test_models_chain_v2.py` (create)

**Interfaces:**
- Consumes: existing `ChainStep`, `ChainRecord`, `normalise_phrase`.
- Produces (later tasks rely on these exact names):
  - `ChainSchemaVersion = Literal["chain.v1", "chain.v2"]`
  - `AptSense(BaseModel)`: `synset_id: str`, `source: Literal["intended", "operator"]`
  - `ChainStep` new optional fields: `node_ref: Optional[str] = None`, `apt_senses: list[AptSense] = Field(default_factory=list)`
  - `ChainStep.resolved_node_ref() -> str` — returns `node_ref` if set, else `f"syn:{self.synset_id}"` if `synset_id`, else `f"vec:{vec_ref(self.phrase)}"`
  - module function `vec_ref(phrase: str) -> str` — `"vec:" + normalise_phrase(phrase).replace(" ", "_")` **without** the `vec:` prefix duplicated: returns only the canonical suffix, i.e. `vec_ref("Pressed  Flower") == "pressed_flower"`; callers prepend `vec:`.
  - `ChainRecord`: `topic_synset_id: Optional[str] = None`, `vehicle_synset_id: Optional[str] = None`, new `topic_node_ref: Optional[str] = None`, `vehicle_node_ref: Optional[str] = None`.
  - Endpoint-canonicalisation validator: for each endpoint, if the synset id is present, behave exactly as today; if absent, require the matching `*_node_ref` to be present and equal to the step's `resolved_node_ref()`.

- [ ] **Step 1: Write the failing tests**

```python
"""chain.v2 — additive over chain.v1; every v1 record must still validate."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import pytest
from models import (AptSense, ChainRecord, ChainStep, ChainSchemaVersion,
                    compute_chain_signature, vec_ref)


def _sig(proposer, phrases):
    return compute_chain_signature(proposer, phrases)


def _v1_record():
    phrases = ["grief", "pain", "scar"]
    return {
        "schema_version": "chain.v1", "topic": "grief", "topic_synset_id": "1",
        "vehicle": "scar", "vehicle_synset_id": "3", "proposer": "sonnet_v1",
        "round": 1, "generated_at": "2026-07-10T00:00:00+00:00",
        "chain_signature": _sig("sonnet_v1", phrases),
        "chain": [
            {"phrase": "grief", "head": "grief", "synset_id": "1"},
            {"phrase": "pain", "head": "pain", "synset_id": "2"},
            {"phrase": "scar", "head": "scar", "synset_id": "3"},
        ],
    }


def test_v1_record_still_validates():
    rec = ChainRecord(**_v1_record())
    assert rec.schema_version == "chain.v1"
    assert rec.chain[0].node_ref is None
    assert rec.chain[0].apt_senses == []


def test_vec_ref_canonicalises_via_normalise_phrase():
    assert vec_ref("Pressed  Flower ") == "pressed__flower"  # NFC+strip+lower; spaces->underscores
    assert vec_ref("glance") == "glance"


def test_resolved_node_ref_derivation():
    syn = ChainStep(phrase="wound", head="wound", synset_id="82241")
    assert syn.resolved_node_ref() == "syn:82241"
    explicit = ChainStep(phrase="wound", head="wound", synset_id="82241",
                         node_ref="syn:82241")
    assert explicit.resolved_node_ref() == "syn:82241"
    vec = ChainStep(phrase="pressed flower", head="flower", synset_id=None)
    assert vec.resolved_node_ref() == "vec:pressed_flower"


def test_v2_vec_vehicle_endpoint_validates():
    phrases = ["nostalgia", "keepsake", "pressed flower"]
    rec = ChainRecord(
        schema_version="chain.v2", topic="nostalgia", topic_synset_id="10",
        vehicle="pressed flower", vehicle_synset_id=None,
        vehicle_node_ref="vec:pressed_flower", proposer="sonnet_v1", round=1,
        generated_at="2026-07-10T00:00:00+00:00",
        chain_signature=_sig("sonnet_v1", phrases),
        chain=[
            {"phrase": "nostalgia", "head": "nostalgia", "synset_id": "10"},
            {"phrase": "keepsake", "head": "keepsake", "synset_id": "11"},
            {"phrase": "pressed flower", "head": "flower", "synset_id": None,
             "node_ref": "vec:pressed_flower"},
        ],
    )
    assert rec.chain[-1].resolved_node_ref() == "vec:pressed_flower"


def test_v2_vec_vehicle_requires_matching_node_ref():
    bad = _v1_record()
    bad["schema_version"] = "chain.v2"
    bad["vehicle_synset_id"] = None
    bad["chain"][-1]["synset_id"] = None
    # no vehicle_node_ref supplied -> must fail
    with pytest.raises(ValueError):
        ChainRecord(**bad)


def test_apt_senses_roundtrip():
    step = ChainStep(phrase="glance", head="glance", synset_id="70001",
                     apt_senses=[{"synset_id": "70001", "source": "intended"},
                                 {"synset_id": "70002", "source": "operator"}])
    assert [a.synset_id for a in step.apt_senses] == ["70001", "70002"]
    with pytest.raises(ValueError):
        AptSense(synset_id="x", source="snapper")  # not a valid source
```

Note on `test_vec_ref_canonicalises_via_normalise_phrase`: `normalise_phrase` collapses nothing — it only NFC-normalises, strips, and lowers. `"Pressed  Flower "` therefore normalises to `"pressed  flower"` and space→underscore gives `"pressed__flower"`. Keep the double underscore in the assertion — the canonicaliser must stay byte-consistent with `chain_signature`'s.

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /home/agent/projects/metaforge/.worktrees/phrase-as-node && /home/agent/projects/metaforge/data-pipeline/.venv/bin/python -m pytest data-pipeline/grading_sidecar/tests/test_models_chain_v2.py -v`
Expected: FAIL — `ImportError: cannot import name 'AptSense'`.

- [ ] **Step 3: Minimal implementation in `models.py`**

```python
ChainSchemaVersion = Literal["chain.v1", "chain.v2"]

def vec_ref(phrase: str) -> str:
    """Canonical vec-node suffix: the SAME canonicaliser that keys
    chain_signature (one canonicaliser, never two), spaces to underscores."""
    return normalise_phrase(phrase).replace(" ", "_")


class AptSense(BaseModel):
    """A locally co-apt sense at one chain position. `intended` = the
    emit-the-sense gloss-match; `operator` = a grading tick. The snapper never
    writes here — co-aptness it can't validate stays out of the record."""
    synset_id: str = Field(min_length=1)
    source: Literal["intended", "operator"]


class ChainStep(BaseModel):
    phrase: str = Field(min_length=1)
    head: str = Field(min_length=1)
    synset_id: Optional[str] = None
    gloss: Optional[str] = None          # (existing emit-the-sense field)
    # Phrase-as-Node: explicit node kind. Absent -> derived from synset_id, so
    # every chain.v1 record reads as v2 without rewrite.
    node_ref: Optional[str] = None
    # Per-OCCURRENCE apt sense-set (spec §2.2/§2.4). Optional: an empty list is
    # a fully valid step that simply yields no derived siblings.
    apt_senses: list[AptSense] = Field(default_factory=list)

    def resolved_node_ref(self) -> str:
        if self.node_ref:
            return self.node_ref
        if self.synset_id:
            return f"syn:{self.synset_id}"
        return f"vec:{vec_ref(self.phrase)}"
```

`ChainRecord`: make `topic_synset_id`/`vehicle_synset_id` `Optional[str] = None`, add `topic_node_ref: Optional[str] = None` / `vehicle_node_ref: Optional[str] = None`, and extend `_endpoint_canonicalisation`: keep the existing equality checks whenever the synset id is not None; when an endpoint synset id IS None, require the corresponding `*_node_ref` to be non-empty and `== self.chain[0/-1].resolved_node_ref()`, else `raise ValueError("endpoint canonicalisation: vec endpoint requires matching node_ref")`.

- [ ] **Step 4: Run the new tests AND the whole existing sidecar suite**

Run: `/home/agent/projects/metaforge/data-pipeline/.venv/bin/python -m pytest data-pipeline/grading_sidecar/tests/ -v`
Expected: all PASS (regressions here = your validator broke v1 reads).

- [ ] **Step 5: Commit**

```bash
git add data-pipeline/grading_sidecar/models.py data-pipeline/grading_sidecar/tests/test_models_chain_v2.py
git commit -m "feat(schema): chain.v2 — node_ref + per-occurrence apt_senses, vec: endpoints (additive over v1)"
```

---

## Task 2 (W1): sense inventory + vec: gate + fan ranking — new module

**Files:**
- Create: `data-pipeline/scripts/sense_inventory.py`
- Create: `data-pipeline/scripts/build_sense_inventories.py` (CLI)
- Test: `data-pipeline/scripts/test_sense_inventory.py`

**Interfaces:**
- Consumes: `metaphor_disambiguate.candidate_senses(conn, lemma) -> list[dict]` (each dict has `synset_id`, `sensenum`, `tagcount`, `definition`, `pos` — check the actual keys at `data-pipeline/scripts/metaphor_disambiguate.py:110` and use what it returns; if `pos`/`definition` are missing there, query them in this module instead — do NOT modify `metaphor_disambiguate.py`). `dominant_sense_prior.choose_sense` exists at `data-pipeline/scripts/dominant_sense_prior.py` (cherry-picked into this branch during setup) — reuse its tagcount logic as a RANKING primitive only; its single-pick override mode is not used.
- Produces:
  - `noun_inventory(conn, phrase: str, head: str) -> list[dict]` — noun-POS candidate senses for the full phrase first, else the head lemma; each `{synset_id, sensenum, tagcount, definition, pos}`; ranked by `(tagcount DESC, sensenum ASC)`.
  - `vec_gate(conn, phrase: str, head: str) -> bool` — True ⇔ vec: admission allowed ⇔ `noun_inventory` is empty for BOTH the full phrase and the head lemma (spec §2.3).
  - `rank_fan(senses: list[dict], intended_synset_id: str | None) -> list[dict]` — the grading display fan: intended sense first (if present), remainder by `(tagcount DESC, sensenum ASC)`.
  - CLI `build_sense_inventories.py --db PATH --chains GLOB... --out PATH` — one JSONL row per distinct `(lemma_or_phrase)` appearing at any chain step: `{"key": <normalise_phrase(phrase)>, "senses": [...ranked...]}`. Idempotent: `--out` is rewritten atomically (tmp file + rename); re-running with identical inputs produces byte-identical output.

- [ ] **Step 1: Write the failing tests** (fixture DB pattern: copy the in-memory fixture-building helper from `data-pipeline/scripts/test_metaphor_disambiguate.py` — same `lemmas`/`synsets`/`sense_attributes` tables; do not invent a new fixture shape)

```python
import sqlite3
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import sense_inventory as si


def _db():
    conn = sqlite3.connect(":memory:")
    conn.executescript("""
        CREATE TABLE synsets (synset_id TEXT PRIMARY KEY, pos TEXT, definition TEXT);
        CREATE TABLE lemmas (lemma TEXT, synset_id TEXT);
        CREATE TABLE sense_attributes (lemma TEXT, synset_id TEXT,
                                       sensenum INTEGER, tagcount INTEGER);
    """)
    rows = [
        ("100", "n", "a brief look"), ("101", "v", "look quickly"),
        ("102", "n", "a deflection"), ("200", "n", "an open sore"),
    ]
    conn.executemany("INSERT INTO synsets VALUES (?,?,?)", rows)
    conn.executemany("INSERT INTO lemmas VALUES (?,?)",
                     [("glance", "100"), ("glance", "101"), ("glance", "102"),
                      ("wound", "200")])
    conn.executemany("INSERT INTO sense_attributes VALUES (?,?,?,?)",
                     [("glance", "100", 1, 9), ("glance", "101", 2, 4),
                      ("glance", "102", 3, 0), ("wound", "200", 1, 2)])
    return conn


def test_noun_inventory_filters_to_nouns_and_ranks_by_tagcount():
    inv = si.noun_inventory(_db(), "glance", "glance")
    assert [s["synset_id"] for s in inv] == ["100", "102"]  # verb 101 excluded
    assert inv[0]["tagcount"] == 9


def test_noun_inventory_falls_back_to_head_for_multiword():
    inv = si.noun_inventory(_db(), "buried wound", "wound")
    assert [s["synset_id"] for s in inv] == ["200"]


def test_vec_gate_true_only_when_no_noun_candidates_anywhere():
    conn = _db()
    assert si.vec_gate(conn, "pressed flower", "flower") is True   # neither known
    assert si.vec_gate(conn, "buried wound", "wound") is False     # head has a noun sense
    assert si.vec_gate(conn, "glance", "glance") is False


def test_rank_fan_puts_intended_first_then_tagcount():
    inv = si.noun_inventory(_db(), "glance", "glance")
    fan = si.rank_fan(inv, intended_synset_id="102")
    assert [s["synset_id"] for s in fan] == ["102", "100"]
    assert si.rank_fan(inv, None)[0]["synset_id"] == "100"


def test_build_inventories_idempotent(tmp_path):
    import json, build_sense_inventories as bsi
    chains = tmp_path / "chains.jsonl"
    chains.write_text(json.dumps({
        "schema_version": "chain.v1", "chain_signature": "0" * 64,
        "topic": "grief", "vehicle": "scar",
        "chain": [{"phrase": "glance", "head": "glance", "synset_id": "100"}],
    }) + "\n")
    out = tmp_path / "inv.jsonl"
    db = tmp_path / "d.db"
    _dump_fixture_to(db)  # helper: persist the _db() fixture to a file
    r1 = bsi.build(str(db), [str(chains)], str(out))
    text1 = out.read_text()
    r2 = bsi.build(str(db), [str(chains)], str(out))
    assert out.read_text() == text1 and r1 == r2
```

(Write `_dump_fixture_to` in the test module: open a file-backed connection, run the same executescript/executemany as `_db()`.)

- [ ] **Step 2: Run to verify failure** — `.../python -m pytest data-pipeline/scripts/test_sense_inventory.py -v` → `ModuleNotFoundError: sense_inventory`.

- [ ] **Step 3: Implement `sense_inventory.py` + `build_sense_inventories.py`** — SQL joins `lemmas`→`synsets` (+ LEFT JOIN `sense_attributes` for tagcount/sensenum, `COALESCE(tagcount,0)`) with `WHERE s.pos='n' AND LOWER(l.lemma)=?`; try full phrase, fall back to head. `vec_gate` = both inventories empty; log every True at INFO with the phrase ("vec: admission"). `rank_fan` is pure. `build` streams chains, collects distinct step phrases (+heads as fallback keys), writes sorted-by-key JSONL via `tmp = out + '.tmp'` then `os.replace` (atomic; idempotent by construction).

- [ ] **Step 4: Run tests to verify pass** — same command, all PASS.

- [ ] **Step 5: Commit**

```bash
git add data-pipeline/scripts/sense_inventory.py data-pipeline/scripts/build_sense_inventories.py data-pipeline/scripts/test_sense_inventory.py
git commit -m "feat(snapper): sense inventory (noun-POS), vec: admission gate, fan ranking + inventory precompute CLI"
```

---

## Task 3 (W1): per-hop noun-prior snapper + chain.v2 migration

**Files:**
- Create: `data-pipeline/scripts/migrate_chain_v2.py`
- Test: `data-pipeline/scripts/test_migrate_chain_v2.py`
- Read-only reference: `data-pipeline/scripts/resnap_glossed_corpus.py` (the flow to imitate), `data-pipeline/scripts/gloss_backfill.py` (`resnap_chain_record`), `data-pipeline/scripts/metaphor_graph.py:526-` (`snap_by_gloss_embed`, `snap_by_gloss`).

**Interfaces:**
- Consumes: Task 1 (`ChainRecord`, `ChainStep`, `vec_ref`), Task 2 (`noun_inventory`, `vec_gate`), existing `snap_by_gloss`, `snap_by_gloss_embed`.
- Produces:
  - `noun_prior_snap(conn, vectors, phrase: str, head: str, gloss: str | None) -> dict` — returns `{"synset_id": str | None, "node_ref": str, "confidence": "ok" | "low" | "vec"}`. Logic (spec §4): (1) if `gloss`, snap via `snap_by_gloss_embed` falling back to `snap_by_gloss` **restricted to the noun inventory** (filter the returned synset: if it is not in `noun_inventory`, retry the snap over noun candidates only by passing the head; if the snapper's answer is cross-POS but gloss evidence chose it, KEEP it — the prior yields to decisive gloss evidence: concretely, accept the unrestricted snap result when it is non-None, and only fall back to the top noun-inventory sense when the snap returns None); (2) no snap result: if `vec_gate` → `synset_id=None, node_ref="vec:"+vec_ref(phrase), confidence="vec"` (log admission); (3) else top noun-inventory sense with `confidence="low"` (log) — never drop, never fall through to vec.
  - `migrate_record(rec: dict, snap_fn) -> dict` — chain.v1 dict in, chain.v2 dict out: per step set `synset_id` (intended), `node_ref`, `apt_senses=[{synset_id, source:"intended"}]` when a synset resolved; endpoints mirrored to `topic_synset_id`/`vehicle_synset_id`/`*_node_ref` from steps 0/-1; `schema_version="chain.v2"`; **every other field byte-identical** — assert `out["chain_signature"] == rec["chain_signature"]` inside and raise on mismatch. Records already `chain.v2` are returned unchanged (idempotency).
  - CLI `main(argv)` — `--db --vectors --in GLOB... --out-suffix _v2` : for each input file write `<stem>_v2.jsonl` next to it (originals untouched), skip outputs that already exist unless `--force`, print a summary dict per file (`records`, `resnapped_steps`, `vec_admissions`, `low_confidence`).

- [ ] **Step 1: failing tests** — cover: (a) `migrate_record` on a 3-step v1 fixture (reuse Task 1's `_v1_record()` shape) with a stub `snap_fn` returning a changed interior sense → v2 out, signature preserved, interior `synset_id` updated, `apt_senses=[{...,"intended"}]`; (b) already-v2 record returned unchanged; (c) `noun_prior_snap` unit tests on the Task-2 fixture DB with a stub embed (pass `vectors={}` so embed yields None and token-overlap `snap_by_gloss` drives): gloss matching the verb sense of `glance` still returns the verb (decisive gloss evidence wins); gloss `None` + known noun → top-noun with `confidence="low"`; unknown phrase+head → `confidence="vec"`, `node_ref=="vec:pressed_flower"`; (d) signature-mismatch guard raises if a mutated `phrase` sneaks through (feed a malicious snap_fn that edits phrases — expect `RuntimeError`); (e) CLI writes `_v2` file, second run without `--force` skips it (assert file mtime unchanged and summary says skipped).

Write each as a real pytest function with real asserts (follow the style of `test_resnap_glossed_corpus.py`).

- [ ] **Step 2: verify red** → `ModuleNotFoundError: migrate_chain_v2`.
- [ ] **Step 3: implement** (compose, don't copy: import from `gloss_backfill`/`metaphor_graph`/`sense_inventory`).
- [ ] **Step 4: verify green** — new tests + `test_resnap_glossed_corpus.py` + `test_gloss_backfill.py` still pass.
- [ ] **Step 5: Commit** — `feat(migration): per-hop noun-prior snapper + chain.v2 migration ($0, idempotent, signature-preserving)`.

---

## Task 4 (W1): generation emits chain.v2 (vec: vehicles stop being dropped)

**Files:**
- Modify: `data-pipeline/scripts/generate_metaphor_edges.py` (the ingest path that builds `ChainRecord`s — find `chain_records_from_sonnet` / the resolver wiring; the "no synset" vehicle drop lives where a vehicle fails to resolve a synset)
- Test: extend `data-pipeline/scripts/test_generate_metaphor_edges.py` (new test functions only — do not rewrite existing ones)

**Interfaces:**
- Consumes: Task 1 models, Task 2 `vec_gate` + `noun_inventory`, Task 3 `noun_prior_snap` if importable cleanly (else inline the same three-outcome logic through the existing resolver hooks).
- Produces: generated records with `schema_version="chain.v2"`, per-step `node_ref` + intended `apt_senses`, and vehicles that fail synset resolution but pass `vec_gate` admitted as `vehicle_synset_id=None` + `vehicle_node_ref="vec:…"` instead of skipped. The skip counter / log line that today records the drop must now record the admission.

- [ ] **Step 1: failing tests** — (a) a model proposal with an OOV multi-word vehicle (stub resolver returns None; fixture DB lacks the lemma) produces a valid v2 `ChainRecord` with a vec: vehicle (assert no skip); (b) a resolvable vehicle still produces `syn:` exactly as before (regression); (c) emitted records validate through `ChainRecord(**rec)` and steps carry `apt_senses == [{"synset_id": <intended>, "source": "intended"}]` for resolved steps and `[]` for vec steps.
- [ ] **Step 2: verify red.**
- [ ] **Step 3: implement minimally** — thread the fixture-DB conn that the module already receives for gloss snapping into the vec-gate call; keep the tripwire/money-brake code paths untouched.
- [ ] **Step 4: verify green** — the FULL `test_generate_metaphor_edges.py` (+ provider tests) must pass.
- [ ] **Step 5: Commit** — `feat(generation): emit chain.v2 — node_ref + intended apt_senses; vec:-gated vehicles admitted, not dropped`.

---

## Task 5 (W1): SQL DDL design note (no data build)

**Files:**
- Create: `docs/designs/2026-07-10-phrase-as-node-ddl.md`

Copy the DDL block from spec §8 **verbatim** into the doc with a short preamble: it is the node-first replacement for the synset-keyed `metaphor_bridges`/`metaphor_bridge_steps` on branch `metaphor-graph/schema-base` (`data-pipeline/SCHEMA.sql:327-361`), to be applied when Block 3 (First Completion) materialises; the sidecar stays file-based. State the two invariants: `chain_signature` remains the occurrence key; `step_apt_senses.source IN ('intended','operator')` mirrors `AptSense.source`.

- [ ] **Step 1: write the doc** (no test — documentation task).
- [ ] **Step 2: Commit** — `docs(ddl): node-first DDL design for Block 3 (nodes/node_senses/chain_steps/step_apt_senses)`.

---

## Task 6 (W2): sidecar models — chain.v2 mirror + verdict `step_apt_senses`

**Files:**
- Modify: `data-pipeline/grading_sidecar/models.py`
- Test: `data-pipeline/grading_sidecar/tests/test_models_chain_v2.py` (create — same file name as W1's, this is a different worktree/branch)

**Interfaces:**
- Produces: the SAME `ChainSchemaVersion`/`AptSense`/`ChainStep`/`vec_ref`/`ChainRecord` change as Task 1 — apply the exact code blocks from Task 1 Step 3 (the two branches' `models.py` have diverged around Tags; touch ONLY the chain classes + add `vec_ref`/`AptSense`; leave `Tag`/`LINKAGE_FORCING_TAGS` etc. exactly as they are on this branch). PLUS the verdict extension:
  - `StepAptSense(BaseModel)`: `step_idx: int = Field(ge=0)`, `synset_id: str = Field(min_length=1)`
  - `JudgementRecord` (models.py:79): `topic_synset_id: Optional[str] = None`, `vehicle_synset_id: Optional[str] = None`, new `topic_node_ref: Optional[str] = None`, `vehicle_node_ref: Optional[str] = None`, new `step_apt_senses: list[StepAptSense] = Field(default_factory=list)`.

- [ ] **Step 1: failing tests** — reuse Task 1's chain tests verbatim PLUS: (a) a stored v2 judgement line WITHOUT `step_apt_senses` still validates (read-compat — copy a real-shaped dict from the `JudgementRecord` fields with `topic_synset_id` present); (b) a verdict WITH `step_apt_senses=[{"step_idx":2,"synset_id":"70002"}]` round-trips; (c) a vec-vehicle verdict (`vehicle_synset_id=None`, `vehicle_node_ref="vec:pressed_flower"`) validates.
- [ ] **Step 2: red** → import errors.
- [ ] **Step 3: implement** (exact Task 1 blocks + the verdict fields).
- [ ] **Step 4: green** — new tests + `python -m pytest data-pipeline/grading_sidecar/tests/ -v` all pass (v1 verdict POST fixtures in existing route tests are the regression canary).
- [ ] **Step 5: Commit** — `feat(sidecar): chain.v2 models + verdict step_apt_senses / vec: endpoints (additive)`.

---

## Task 7 (W2): TS types + phrase-first chain labels

**Files:**
- Modify: `web/src/types/grading.ts` (ChainStep at ~line 19)
- Modify: `web/src/components/mf-grade-panel.ts` (line ~242 `<strong>${step.head}</strong>`, line ~368 step-node button label)
- Modify: any other component rendering chain-step text via `.head` — run `grep -rn "\.head" web/src/components/ web/src/` and flip every *chain-step display label* (not head-comparison logic) to phrase-primary
- Test: `web/src/components/mf-grade-panel.test.ts` (extend)

**Interfaces:**
- Produces TS types (later tasks import these exact names):

```ts
export interface AptSense { synset_id: string; source: 'intended' | 'operator'; }
export interface StepAptSense { step_idx: number; synset_id: string; }
// ChainStep gains: node_ref?: string | null; apt_senses?: AptSense[];
// (synset_id already string | null — verify, make nullable if not)
```

- Display rule: the step label is **`step.phrase`**; when `phrase !== head`, `head` moves to the subscript (`phrase-sub` span) — the exact inversion of today's line 368. Line ~242 becomes `<strong>${step.phrase}</strong>`.

- [ ] **Step 1: failing test** — render the panel with a chain containing `{phrase: "buried wound", head: "wound", ...}`; assert the step button's primary text content includes `buried wound` and the subscript shows `wound`; assert a single-word step renders no subscript.
- [ ] **Step 2: red** — `cd web && npx vitest run src/components/mf-grade-panel.test.ts`.
- [ ] **Step 3: implement** (types + label flips).
- [ ] **Step 4: green** — full `npx vitest run` + `npx tsc --noEmit` both clean.
- [ ] **Step 5: Commit** — `feat(grading-ui): phrase-first chain labels (bad_head display-loss dissolves) + chain.v2 TS types`.

---

## Task 8 (W2): sense fan + operator ticks

**Files:**
- Create: `data-pipeline/grading_sidecar/routes/senses.py` + register in `app.py` (follow `routes/glosses.py` as the template — file-serving, DB-free)
- Modify: `data-pipeline/grading_sidecar/paths.py` (add `sense_inventories_path()` beside the existing data-file helpers)
- Modify: `web/src/components/mf-grade-panel.ts` (extend the existing gloss tap: fan list + tick)
- Modify: `web/src/types/grading.ts` (fan payload type)
- Test: `data-pipeline/grading_sidecar/tests/test_senses_route.py` (create), `web/src/components/mf-grade-panel.test.ts` (extend)

**Interfaces:**
- Consumes: the precomputed inventory JSONL from Task 2's CLI (`{"key": <canonical phrase>, "senses": [{synset_id, sensenum, tagcount, definition, pos}]}`), landed at the grading data dir as `sense_inventories_provisional.jsonl` (integration step runs the build; the route must degrade to `{}` with a warning when the file is missing — same pattern as `load_glosses`).
- Produces:
  - `GET /api/grading/senses?key=<normalised phrase>` → `{"key": ..., "senses": [...]}` or `{"key": ..., "senses": []}` when unknown/missing file.
  - Panel behaviour: the existing per-step gloss popover gains a "senses" fan listing the inventory (definition + `n·sensenum`, tagcount badge), **intended sense pre-lit** (`step.synset_id`), tap to toggle others → maintained in a private field `_stepTicks: Map<number, Set<string>>`; on verdict submit the map serialises to `step_apt_senses: [{step_idx, synset_id}]` merged into the existing POST body (only OPERATOR ticks — the intended sense is NOT duplicated into the payload); ticks reset on chain change (same `willUpdate` hook that resets `_pinnedStepIdx`).
- vec: steps (`synset_id == null`): fan shows the phrase + "vector node — no synset"; no tickable senses.

- [ ] **Step 1: failing sidecar test** — write the inventory fixture file, `TestClient` GET known key → senses; unknown key → empty; missing file → empty + no 500.
- [ ] **Step 2: red** (route 404).
- [ ] **Step 3: implement route + paths helper; register router.**
- [ ] **Step 4: green (sidecar suite).**
- [ ] **Step 5: Commit** — `feat(sidecar): /senses route serving precomputed sense inventories (file-based, DB-free)`.
- [ ] **Step 6: failing web test** — fan renders inventory with intended pre-lit; tick toggles; submit payload contains `step_apt_senses` with only operator ticks; ticks reset on chain switch; vec: step shows the no-synset affordance.
- [ ] **Step 7: red.**
- [ ] **Step 8: implement panel fan + tick + payload merge.**
- [ ] **Step 9: green** — full `npx vitest run` + `npx tsc --noEmit`.
- [ ] **Step 10: Commit** — `feat(grading-ui): per-step sense fan with operator ticks -> step_apt_senses on the verdict`.

---

## Task 9 (W2): real-bundle Playwright verification

**Files:**
- Create/extend: the e2e spec beside the existing ones (`ls web/e2e/` and follow the established harness — the repo has real-bundle Playwright e2e from prior grading rounds)
- No production-code changes; if e2e exposes a defect, fix it in the owning file with a unit test first.

- [ ] **Step 1: `cd web && npm run build`** (must succeed).
- [ ] **Step 2: e2e spec** asserting on the BUILT bundle (desktop 1280 + mobile 390): (a) a multi-word step renders phrase-first; (b) the sense fan opens on a step and a tick toggles; (c) a vec: step shows "vector node — no synset"; (d) zero console errors. Use the existing e2e fixture/server pattern — do not invent a new harness.
- [ ] **Step 3: run e2e headless, all green.**
- [ ] **Step 4: Commit** — `test(e2e): real-bundle verification — phrase-first labels, sense fan, vec: affordance`.

---

## Task 10 (W3): judge-harness chain.v2 projection

**Files:**
- Modify: `data-pipeline/scripts/judge_corpus.py` (`attach_chain_context` ~line 288 — the step projection)
- Test: `data-pipeline/scripts/test_judge_corpus.py` (extend; find the existing `attach_chain_context` tests and add beside them)

**Interfaces:**
- Produces: the projected step dicts gain `"gloss"` and `"node_ref"` (pass-through from the chain record, `None` when absent): `{"phrase":…, "head":…, "synset_id":…, "gloss":…, "node_ref":…}`. Downstream prompt rendering already tolerates extra keys; a vec: step (synset_id None) then renders its own emitted gloss instead of a synset gloss. `_REQUIRED_CHAIN_KEYS` stays `("chain_signature", "topic", "vehicle")` — chain.v2 records already load; add a test proving a v2 record with a vec: vehicle attaches without warnings and `vehicle_gloss is None`.

- [ ] **Step 1: failing test** — v2 chain fixture with a vec: step: projection carries `gloss`/`node_ref`; v1 fixture: both keys present as None (shape-stable).
- [ ] **Step 2: red.** Run with `/home/agent/projects/metaforge/data-pipeline/.venv/bin/python -m pytest data-pipeline/scripts/test_judge_corpus.py -v` from W3.
- [ ] **Step 3: implement (2-line projection change).**
- [ ] **Step 4: green** — full harness suite (`python -m pytest data-pipeline/scripts/ -v` from W3) passes.
- [ ] **Step 5: Commit** — `feat(harness): project gloss + node_ref through attach_chain_context (chain.v2 / vec: steps)`.

---

## Integration (orchestrator-only; NOT worker tasks)

1. Run `migrate_chain_v2.py` over the real corpus (real DB + FastText vectors), verify summary + spot-check; back up live grading chain files before any promotion; promote to `.worktrees/grading-data` (atomic swap, same playbook as 2026-06-20).
2. Run `build_sense_inventories.py` over the migrated corpus → `sense_inventories_provisional.jsonl` into grading-data.
3. Surface the 25 bad_sense-quarantined gold rows as re-grade candidates (list, not auto-unquarantine).
4. Cherry-pick W2 commits → `grading-code`, rebuild dist (sidecar restart = operator sudo, deferred note).
5. Judge κ re-baseline sanity (`no worse than 0.524`), PIPELINE.md + memory updates.
