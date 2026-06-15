# Sense-Check Mode Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a self-contained "sense-check" mode to the Metaphor Grading UI where the operator labels a stratified sample of chain endpoints (right / wrong / rare-but-better / unsure + the intended sense), persisting to a separate provisional file that anchors sense-correctness to human gold.

**Architecture:** Mirrors the blind re-grade feature end-to-end — a self-contained Lit component (`mf-grade-sensecheck`) mounted by `mf-app` as a 4th grade view, a thin FastAPI route trio delegating to a pure sampler module, a DB-free sidecar fed by an offline precompute (`sense_candidates_provisional.jsonl`), and a separate-file persistence invariant (`sense_labels_provisional.jsonl`, never the gold judgements). Spec: `docs/superpowers/specs/2026-06-15-sense-check-mode-design.md`.

**Tech Stack:** Python 3 / FastAPI / Pydantic (sidecar), SQLite (offline precompute), Lit + TypeScript + Vitest/happy-dom (web), pytest.

---

## File structure

**Create:**
- `data-pipeline/grading_sidecar/sense_check.py` — pure sampler + item builder (no IO).
- `data-pipeline/grading_sidecar/routes/sense_check.py` — thin GET sample / POST label routes.
- `data-pipeline/grading_sidecar/tests/test_sense_check.py` — sampler/item-builder unit tests.
- `data-pipeline/grading_sidecar/tests/test_sense_check_endpoint.py` — route tests.
- `data-pipeline/scripts/build_sense_candidates.py` — offline candidate-senses precompute generator.
- `data-pipeline/scripts/test_build_sense_candidates.py` — generator test.
- `web/src/components/mf-grade-sensecheck.ts` — self-contained sense-check view.
- `web/src/components/mf-grade-sensecheck.test.ts` — component tests.

**Modify:**
- `data-pipeline/grading_sidecar/paths.py` — add `SENSE_FLAGS_NAME`, `SENSE_CANDIDATES_NAME`, `SENSE_LABELS_PATH`.
- `data-pipeline/grading_sidecar/models.py` — add `SenseVerdict`, `SenseLabel`.
- `data-pipeline/grading_sidecar/app.py` — register the new router.
- `web/src/types/grading.ts` — add sense-check types.
- `web/src/api/grading-client.ts` — add `getSenseCheckSample`, `postSenseLabel`.
- `web/src/components/mf-app.ts` — add the 4th grade view.

**Data files produced (gitignored DB → committed JSONL, like chain_glosses):**
- `data-pipeline/grading/sense_candidates_provisional.jsonl` (generated).
- `data-pipeline/grading/sense_labels_provisional.jsonl` (written at runtime).
- `data-pipeline/grading/sense_flags_provisional.jsonl` (already exists — the subagent's flags).

**Test commands:**
- Sidecar/scripts: `cd /home/agent/projects/metaforge/data-pipeline && .venv/bin/python -m pytest <path> -v`
- Web: `cd /home/agent/projects/metaforge/web && npx vitest run <path>`

---

## Task 1: Paths constants

**Files:**
- Modify: `data-pipeline/grading_sidecar/paths.py`
- Test: `data-pipeline/grading_sidecar/tests/test_sense_check.py`

- [ ] **Step 1: Write the failing test**

Create `data-pipeline/grading_sidecar/tests/test_sense_check.py`:

```python
"""Unit tests for the sense-check sampler + item builder."""
from __future__ import annotations
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from grading_sidecar import paths as paths_mod


def test_sense_labels_path_is_separate_from_judgements():
    # Safety invariant: a sense label must never share a file with gold verdicts.
    assert paths_mod.SENSE_LABELS_PATH != paths_mod.JUDGEMENTS_PATH
    assert paths_mod.SENSE_LABELS_PATH.name == "sense_labels_provisional.jsonl"
    assert paths_mod.SENSE_FLAGS_NAME == "sense_flags_provisional.jsonl"
    assert paths_mod.SENSE_CANDIDATES_NAME == "sense_candidates_provisional.jsonl"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/agent/projects/metaforge/data-pipeline && .venv/bin/python -m pytest grading_sidecar/tests/test_sense_check.py::test_sense_labels_path_is_separate_from_judgements -v`
Expected: FAIL with `AttributeError: module 'grading_sidecar.paths' has no attribute 'SENSE_LABELS_PATH'`

- [ ] **Step 3: Add the constants**

Append to `data-pipeline/grading_sidecar/paths.py`:

```python
# Sense-check inputs/outputs. The subagent's wrong/rare flags (READ), the offline
# candidate-senses precompute (READ, lemma -> [senses]; DB-free sidecar), and the
# operator's sense labels. SENSE_LABELS_PATH is a SEPARATE file from the gold
# judgements on purpose: a sense label is not a liveness/linkage verdict and must
# never be resolved as one. Auto-committed like the rest of GRADING_DIR.
SENSE_FLAGS_NAME = "sense_flags_provisional.jsonl"
SENSE_CANDIDATES_NAME = "sense_candidates_provisional.jsonl"
SENSE_LABELS_PATH = GRADING_DIR / "sense_labels_provisional.jsonl"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /home/agent/projects/metaforge/data-pipeline && .venv/bin/python -m pytest grading_sidecar/tests/test_sense_check.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add data-pipeline/grading_sidecar/paths.py data-pipeline/grading_sidecar/tests/test_sense_check.py
git commit -m "feat(grading): sense-check paths constants (separate labels file)"
```

---

## Task 2: SenseLabel model

**Files:**
- Modify: `data-pipeline/grading_sidecar/models.py`
- Test: `data-pipeline/grading_sidecar/tests/test_models.py`

- [ ] **Step 1: Write the failing test**

Append to `data-pipeline/grading_sidecar/tests/test_models.py`:

```python
def test_sense_label_defaults_and_optional_intended():
    from grading_sidecar.models import SenseLabel
    # Minimal valid label: schema_version + ts default; intended/chain_signature optional.
    lbl = SenseLabel(role="topic", word="apprehension",
                     snapped_synset_id="1760", verdict="wrong",
                     intended_synset_id="72797")
    assert lbl.schema_version == "sense_label.v1"
    assert lbl.ts  # server-injected default
    assert lbl.intended_synset_id == "72797"

    ok = SenseLabel(role="vehicle", word="river",
                    snapped_synset_id="9", verdict="right")
    assert ok.intended_synset_id is None
    assert ok.chain_signature is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/agent/projects/metaforge/data-pipeline && .venv/bin/python -m pytest grading_sidecar/tests/test_models.py::test_sense_label_defaults_and_optional_intended -v`
Expected: FAIL with `ImportError: cannot import name 'SenseLabel'`

- [ ] **Step 3: Add the model**

Append to `data-pipeline/grading_sidecar/models.py` (after `DesignNotePost`):

```python
# Sense-check label — the operator's verdict on whether an endpoint's snapped
# synset is the intended sense. Keyed on the endpoint (role, word,
# snapped_synset_id), NOT a chain; chain_signature stores one representative chain
# for traceability back to context. Written to SENSE_LABELS_PATH only.
SenseLabelSchemaVersion = Literal["sense_label.v1"]
SenseRole = Literal["topic", "vehicle"]
SenseVerdict = Literal["right", "wrong", "rare_ok", "unsure"]


class SenseLabel(BaseModel):
    schema_version: SenseLabelSchemaVersion = "sense_label.v1"
    # Server injects ts when the client omits it (mirrors JudgementRecord).
    ts: str = Field(default_factory=lambda: dt.datetime.now(dt.timezone.utc).isoformat())
    role: SenseRole
    word: str
    snapped_synset_id: str
    verdict: SenseVerdict
    # Set only for wrong / rare_ok (the sense the operator intended); else None.
    intended_synset_id: Optional[str] = None
    # One representative chain the endpoint appeared in (traceability, not a key).
    chain_signature: Optional[str] = None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /home/agent/projects/metaforge/data-pipeline && .venv/bin/python -m pytest grading_sidecar/tests/test_models.py -v`
Expected: PASS (all existing model tests still green)

- [ ] **Step 5: Commit**

```bash
git add data-pipeline/grading_sidecar/models.py data-pipeline/grading_sidecar/tests/test_models.py
git commit -m "feat(grading): SenseLabel model (endpoint-keyed sense verdict)"
```

---

## Task 3: Sampler — distinct endpoints + stratified draw

**Files:**
- Create: `data-pipeline/grading_sidecar/sense_check.py`
- Test: `data-pipeline/grading_sidecar/tests/test_sense_check.py`

- [ ] **Step 1: Write the failing test**

Append to `data-pipeline/grading_sidecar/tests/test_sense_check.py`:

```python
def _chain(sig, topic, tsid, vehicle, vsid):
    return {"topic": topic, "topic_synset_id": tsid, "vehicle": vehicle,
            "vehicle_synset_id": vsid, "chain_signature": sig,
            "chain": [{"phrase": topic, "head": topic, "synset_id": tsid},
                      {"phrase": vehicle, "head": vehicle, "synset_id": vsid}]}


def test_distinct_endpoints_dedup_topic_and_vehicle():
    from grading_sidecar.sense_check import distinct_endpoints
    chains = [_chain("a", "longing", "72598", "drought", "104281"),
              _chain("b", "longing", "72598", "river", "9")]  # topic repeats
    eps = distinct_endpoints(chains)
    keys = {(e["role"], e["word"], e["snapped_synset_id"]) for e in eps}
    assert ("topic", "longing", "72598") in keys      # deduped to one
    assert ("vehicle", "drought", "104281") in keys
    assert ("vehicle", "river", "9") in keys
    assert sum(1 for e in eps if e["role"] == "topic") == 1


def test_sample_stratifies_flagged_and_random_excludes_labelled_and_is_seed_stable():
    from grading_sidecar.sense_check import sample_sense_check
    chains = [_chain(str(i), "longing", "72598", f"v{i}", str(100 + i)) for i in range(10)]
    flags = [{"role": "vehicle", "word": "v0", "synset_id": "100"},
             {"role": "vehicle", "word": "v1", "synset_id": "101"}]
    labels = [{"role": "vehicle", "word": "v0", "snapped_synset_id": "100"}]  # already done
    out = sample_sense_check(flags, chains, labels, n_flagged=5, n_random=3, seed=7)
    keys = {(e["role"], e["word"], e["snapped_synset_id"]) for e in out}
    assert ("vehicle", "v0", "100") not in keys           # labelled excluded
    assert ("vehicle", "v1", "101") in keys               # only un-labelled flag left
    flagged = [e for e in out if e["stratum"] == "flagged"]
    randoms = [e for e in out if e["stratum"] == "random"]
    assert len(flagged) == 1 and len(randoms) == 3        # caps honoured vs pool size
    assert all(("vehicle", e["word"], e["snapped_synset_id"]) not in
               {("vehicle", "v1", "101")} for e in randoms)  # random pool excludes flags
    # Determinism: same seed → identical draw.
    again = sample_sense_check(flags, chains, labels, n_flagged=5, n_random=3, seed=7)
    assert [e["snapped_synset_id"] for e in out] == [e["snapped_synset_id"] for e in again]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/agent/projects/metaforge/data-pipeline && .venv/bin/python -m pytest grading_sidecar/tests/test_sense_check.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'grading_sidecar.sense_check'`

- [ ] **Step 3: Create the sampler module**

Create `data-pipeline/grading_sidecar/sense_check.py`:

```python
"""Sense-check sampling + item building — anchors snap-correctness to human gold.

Pure functions (no IO): the route loads the flags / chains / labels / precomputes
and passes them in. Mirrors regrade.py: a deterministic, stratified, seed-stable
draw. The two strata — `flagged` (the subagent's wrong/rare endpoints) and
`random` (UNFLAGGED endpoints) — are both labelled by the operator so the analysis
can estimate the subagent's precision AND its silent false-negative rate.
"""
from __future__ import annotations

import random


def distinct_endpoints(chains: list[dict]) -> list[dict]:
    """Distinct (role, word, snapped_synset_id) endpoints across all chains.

    Topic and vehicle of every chain; deduped. Endpoints missing a word or synset
    are skipped (a chain.v1 record always has both, but stay defensive)."""
    seen: set[tuple] = set()
    out: list[dict] = []
    for c in chains:
        for role, word, sid in (
            ("topic", c.get("topic"), c.get("topic_synset_id")),
            ("vehicle", c.get("vehicle"), c.get("vehicle_synset_id")),
        ):
            if not word or not sid:
                continue
            key = (role, word, str(sid))
            if key in seen:
                continue
            seen.add(key)
            out.append({"role": role, "word": word,
                        "snapped_synset_id": str(sid), "stratum": "random"})
    return out


def _take(pool: list[dict], k: int, rng: random.Random) -> list[dict]:
    """Deterministic sample of up to k from pool (sorted first for stability)."""
    ordered = sorted(pool, key=lambda e: (e["role"], e["word"], e["snapped_synset_id"]))
    return ordered if k >= len(ordered) else rng.sample(ordered, k)


def sample_sense_check(flags: list[dict], chains: list[dict], labels: list[dict],
                       *, n_flagged: int, n_random: int, seed: int) -> list[dict]:
    """Draw a deterministic, stratified sense-check sample.

    `flagged` stratum = up to n_flagged distinct endpoints present in `flags`;
    `random` stratum = up to n_random distinct endpoints NOT in flags. Endpoints
    already present in `labels` are excluded from both so successive sessions
    broaden coverage."""
    labelled = {(l.get("role"), l.get("word"), l.get("snapped_synset_id"))
                for l in labels}

    flagged: list[dict] = []
    seen: set[tuple] = set()
    for f in flags:
        key = (f.get("role"), f.get("word"),
               str(f["synset_id"]) if f.get("synset_id") is not None else None)
        if None in key or key in seen:
            continue
        seen.add(key)
        flagged.append({"role": key[0], "word": key[1],
                        "snapped_synset_id": key[2], "stratum": "flagged"})
    flagged_keys = {(e["role"], e["word"], e["snapped_synset_id"]) for e in flagged}

    flagged_pool = [e for e in flagged
                    if (e["role"], e["word"], e["snapped_synset_id"]) not in labelled]
    random_pool = [
        e for e in distinct_endpoints(chains)
        if (e["role"], e["word"], e["snapped_synset_id"]) not in flagged_keys
        and (e["role"], e["word"], e["snapped_synset_id"]) not in labelled
    ]

    rng = random.Random(seed)
    return _take(flagged_pool, n_flagged, rng) + _take(random_pool, n_random, rng)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /home/agent/projects/metaforge/data-pipeline && .venv/bin/python -m pytest grading_sidecar/tests/test_sense_check.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add data-pipeline/grading_sidecar/sense_check.py data-pipeline/grading_sidecar/tests/test_sense_check.py
git commit -m "feat(grading): sense-check stratified sampler (flagged + random)"
```

---

## Task 4: Item builder — context + candidates + snapped gloss

**Files:**
- Modify: `data-pipeline/grading_sidecar/sense_check.py`
- Test: `data-pipeline/grading_sidecar/tests/test_sense_check.py`

- [ ] **Step 1: Write the failing test**

Append to `data-pipeline/grading_sidecar/tests/test_sense_check.py`:

```python
def test_build_items_attaches_gloss_candidates_and_all_context_chains():
    from grading_sidecar.sense_check import build_sample_items
    chains = [_chain("a", "longing", "72598", "drought", "104281"),
              _chain("b", "longing", "72598", "river", "9")]
    endpoints = [{"role": "topic", "word": "longing",
                  "snapped_synset_id": "72598", "stratum": "random"}]
    candidates = {"longing": [
        {"synset_id": "72598", "pos": "n", "gloss": "prolonged desire", "tagcount": 5},
        {"synset_id": "999", "pos": "n", "gloss": "a yearning", "tagcount": None},
    ]}
    glosses = {"72598": {"pos": "n", "definition": "prolonged desire"}}
    items = build_sample_items(endpoints, candidates, glosses, chains)
    it = items[0]
    assert it["snapped_gloss"] == "prolonged desire" and it["pos"] == "n"
    assert len(it["candidates"]) == 2
    # Context = ALL chains the endpoint appears in (the operator's addition).
    sigs = {c["chain_signature"] for c in it["context"]["chains"]}
    assert sigs == {"a", "b"}
    # Representative chain_signature for the label is one of them.
    assert it["chain_signature"] in sigs


def test_build_items_degrades_when_candidates_absent():
    from grading_sidecar.sense_check import build_sample_items
    chains = [_chain("a", "longing", "72598", "drought", "104281")]
    endpoints = [{"role": "vehicle", "word": "drought",
                  "snapped_synset_id": "104281", "stratum": "flagged"}]
    items = build_sample_items(endpoints, {}, {}, chains)  # no candidates, no glosses
    assert items[0]["candidates"] == []
    assert items[0]["snapped_gloss"] is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/agent/projects/metaforge/data-pipeline && .venv/bin/python -m pytest grading_sidecar/tests/test_sense_check.py -k build_items -v`
Expected: FAIL with `ImportError: cannot import name 'build_sample_items'`

- [ ] **Step 3: Add context + builder**

Append to `data-pipeline/grading_sidecar/sense_check.py`:

```python
def context_for(role: str, word: str, synset_id: str, chains: list[dict]) -> list[dict]:
    """Every chain the endpoint appears in (pairing + steps), for the context panel.

    Matched on role's synset_id AND word, so the same synset under a different
    surface word isn't conflated."""
    sfield = "topic_synset_id" if role == "topic" else "vehicle_synset_id"
    wfield = "topic" if role == "topic" else "vehicle"
    out: list[dict] = []
    for c in chains:
        if str(c.get(sfield)) == str(synset_id) and c.get(wfield) == word:
            out.append({"topic": c.get("topic"), "vehicle": c.get("vehicle"),
                        "chain": c.get("chain", []),
                        "chain_signature": c.get("chain_signature")})
    return out


def build_sample_items(endpoints: list[dict], candidates: dict[str, list[dict]],
                       glosses: dict[str, dict], chains: list[dict]) -> list[dict]:
    """Enrich sampled endpoints with snapped gloss/POS, candidate senses, context.

    `glosses` = synset_id -> {pos, definition} (the chain_glosses precompute, reused
    for the SNAPPED gloss). `candidates` = lemma -> [senses] (the new precompute, the
    picker list). Both degrade gracefully to None / [] when absent."""
    items: list[dict] = []
    for e in endpoints:
        sid, word, role = e["snapped_synset_id"], e["word"], e["role"]
        g = glosses.get(sid, {})
        ctx = context_for(role, word, sid, chains)
        items.append({
            "role": role, "word": word, "snapped_synset_id": sid,
            "stratum": e.get("stratum", "random"),
            "snapped_gloss": g.get("definition"), "pos": g.get("pos"),
            "candidates": candidates.get(word, []),
            "context": {"chains": ctx},
            "chain_signature": ctx[0]["chain_signature"] if ctx else None,
        })
    return items


def load_sense_candidates(read_jsonl, candidates_path) -> dict[str, list[dict]]:
    """lemma -> [senses] from the precompute (DB-free). Missing file -> {}."""
    rows, _ = read_jsonl(candidates_path)
    return {r["lemma"]: r.get("senses", []) for r in rows if r.get("lemma")}


def load_snapped_glosses(read_jsonl, glosses_path) -> dict[str, dict]:
    """synset_id -> {pos, definition} from chain_glosses. Missing file -> {}."""
    rows, _ = read_jsonl(glosses_path)
    return {r["synset_id"]: {"pos": r.get("pos"), "definition": r.get("definition")}
            for r in rows if r.get("synset_id")}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /home/agent/projects/metaforge/data-pipeline && .venv/bin/python -m pytest grading_sidecar/tests/test_sense_check.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add data-pipeline/grading_sidecar/sense_check.py data-pipeline/grading_sidecar/tests/test_sense_check.py
git commit -m "feat(grading): sense-check item builder (gloss + candidates + all-chain context)"
```

---

## Task 5: Routes — GET sample / POST label + registration

**Files:**
- Create: `data-pipeline/grading_sidecar/routes/sense_check.py`
- Modify: `data-pipeline/grading_sidecar/app.py:21,91`
- Test: `data-pipeline/grading_sidecar/tests/test_sense_check_endpoint.py`

- [ ] **Step 1: Write the failing test**

Create `data-pipeline/grading_sidecar/tests/test_sense_check_endpoint.py`:

```python
"""Tests for the sense-check routes."""
from __future__ import annotations
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import json
import pytest
from grading_sidecar import paths as paths_mod


def _write(path, *records):
    path.write_text("\n".join(json.dumps(r) for r in records) + "\n")


@pytest.fixture
def sc_client(client, tmp_path, monkeypatch):
    monkeypatch.setattr(paths_mod, "GRADING_DIR", tmp_path)
    monkeypatch.setattr(paths_mod, "SENSE_LABELS_PATH",
                        tmp_path / "sense_labels_provisional.jsonl")
    monkeypatch.setattr(paths_mod, "JUDGEMENTS_PATH",
                        tmp_path / "judgements_provisional.jsonl")
    return client


def _chain(sig, topic, tsid, vehicle, vsid):
    return {"schema_version": "chain.v1", "topic": topic, "topic_synset_id": tsid,
            "vehicle": vehicle, "vehicle_synset_id": vsid, "proposer": "sonnet",
            "round": 1, "chain_signature": sig, "generated_at": "2026-06-01T00:00:00+00:00",
            "chain": [{"phrase": topic, "head": topic, "synset_id": tsid},
                      {"phrase": vehicle, "head": vehicle, "synset_id": vsid}]}


def test_sample_returns_enriched_items(sc_client, tmp_path):
    _write(tmp_path / "sonnet_chains_provisional_r1.jsonl",
           _chain("a", "longing", "72598", "drought", "104281"))
    _write(tmp_path / paths_mod.SENSE_FLAGS_NAME,
           {"role": "vehicle", "word": "drought", "synset_id": "104281",
            "verdict": "WRONG_SENSE"})
    _write(tmp_path / paths_mod.CHAIN_GLOSSES_NAME,
           {"synset_id": "104281", "pos": "n", "definition": "a dry spell"})
    _write(tmp_path / paths_mod.SENSE_CANDIDATES_NAME,
           {"lemma": "drought", "senses": [
               {"synset_id": "104281", "pos": "n", "gloss": "a dry spell", "tagcount": 3}]})
    body = sc_client.get("/api/grading/sense-check/sample?n_flagged=5&n_random=0&seed=1").json()
    assert body["count"] == 1
    it = body["items"][0]
    assert it["word"] == "drought" and it["snapped_gloss"] == "a dry spell"
    assert it["candidates"][0]["synset_id"] == "104281"
    assert it["context"]["chains"][0]["chain_signature"] == "a"


def test_post_label_lands_in_separate_file_not_judgements(sc_client, tmp_path):
    payload = {"role": "topic", "word": "apprehension", "snapped_synset_id": "1760",
               "verdict": "wrong", "intended_synset_id": "72797", "chain_signature": "a"}
    r = sc_client.post("/api/grading/sense-check", json=payload)
    assert r.status_code == 200
    assert (tmp_path / "sense_labels_provisional.jsonl").exists()
    assert not (tmp_path / "judgements_provisional.jsonl").exists()
    saved = json.loads((tmp_path / "sense_labels_provisional.jsonl").read_text().strip())
    assert saved["verdict"] == "wrong" and saved["schema_version"] == "sense_label.v1"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/agent/projects/metaforge/data-pipeline && .venv/bin/python -m pytest grading_sidecar/tests/test_sense_check_endpoint.py -v`
Expected: FAIL with 404s (router not registered)

- [ ] **Step 3: Create the routes**

Create `data-pipeline/grading_sidecar/routes/sense_check.py`:

```python
"""Sense-check routes — anchor snap-correctness to human gold.

  GET  /api/grading/sense-check/sample → a stratified sample of endpoints, each
       enriched with the snapped gloss, candidate senses, and all context chains.
  POST /api/grading/sense-check        → append one label to the SEPARATE labels
       file (never the gold judgements — see paths.SENSE_LABELS_PATH).

Sampler + item maths live in grading_sidecar.sense_check; these routes are thin IO.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Query

from ..auth import verify_secret
from ..chain_store import load_chains
from ..models import SenseLabel
from ..persistence import append_jsonl, read_jsonl_skip_malformed
from ..sense_check import (build_sample_items, load_sense_candidates,
                           load_snapped_glosses, sample_sense_check)
from .. import paths as paths_mod

log = logging.getLogger(__name__)
router = APIRouter(dependencies=[Depends(verify_secret)])


@router.get("/api/grading/sense-check/sample")
def get_sense_check_sample(n_flagged: int = Query(default=40, ge=0, le=200),
                           n_random: int = Query(default=40, ge=0, le=200),
                           seed: int = Query(default=1)) -> dict:
    """Draw a stratified sense-check sample and enrich it for the UI."""
    flags, _ = read_jsonl_skip_malformed(paths_mod.GRADING_DIR / paths_mod.SENSE_FLAGS_NAME)
    chains = load_chains()
    labels, _ = read_jsonl_skip_malformed(paths_mod.SENSE_LABELS_PATH)
    endpoints = sample_sense_check(flags, chains, labels,
                                   n_flagged=n_flagged, n_random=n_random, seed=seed)
    candidates = load_sense_candidates(
        read_jsonl_skip_malformed, paths_mod.GRADING_DIR / paths_mod.SENSE_CANDIDATES_NAME)
    glosses = load_snapped_glosses(
        read_jsonl_skip_malformed, paths_mod.GRADING_DIR / paths_mod.CHAIN_GLOSSES_NAME)
    items = build_sample_items(endpoints, candidates, glosses, chains)
    return {"count": len(items), "items": items}


@router.post("/api/grading/sense-check")
def post_sense_label(label: SenseLabel) -> dict:
    """Append a sense label to the SEPARATE labels file. Never JUDGEMENTS_PATH."""
    append_jsonl(paths_mod.SENSE_LABELS_PATH, label.model_dump(mode="json"))
    return label.model_dump(mode="json")
```

- [ ] **Step 4: Register the router**

In `data-pipeline/grading_sidecar/app.py`, line 21, add `sense_check` to the import:

```python
from .routes import healthz, judgements, chains, topics, stats, calibration, design_notes, walk, signal_report, glosses, regrade, sense_check
```

And after line 91 (`app.include_router(regrade.router)`), add:

```python
    app.include_router(sense_check.router)
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd /home/agent/projects/metaforge/data-pipeline && .venv/bin/python -m pytest grading_sidecar/tests/test_sense_check_endpoint.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add data-pipeline/grading_sidecar/routes/sense_check.py data-pipeline/grading_sidecar/app.py data-pipeline/grading_sidecar/tests/test_sense_check_endpoint.py
git commit -m "feat(grading): sense-check routes (GET sample, POST label to separate file)"
```

---

## Task 6: Candidate-senses precompute generator

**Files:**
- Create: `data-pipeline/scripts/build_sense_candidates.py`
- Test: `data-pipeline/scripts/test_build_sense_candidates.py`

- [ ] **Step 1: Write the failing test**

Create `data-pipeline/scripts/test_build_sense_candidates.py`:

```python
"""Test the candidate-senses precompute generator against a tiny in-memory lexicon."""
import json
import sqlite3
from pathlib import Path

import build_sense_candidates as bsc


def _db():
    conn = sqlite3.connect(":memory:")
    conn.executescript(
        """
        CREATE TABLE synsets (synset_id TEXT PRIMARY KEY, pos TEXT, definition TEXT);
        CREATE TABLE lemmas (lemma TEXT, synset_id TEXT);
        CREATE TABLE sense_attributes (sensekey TEXT, lemma TEXT, synset_id TEXT, tagcount INTEGER);
        INSERT INTO synsets VALUES ('1','n','the felt emotion of dread'),
                                   ('2','n','the act of arresting a criminal');
        INSERT INTO lemmas VALUES ('apprehension','1'), ('apprehension','2');
        INSERT INTO sense_attributes VALUES ('k1','apprehension','2', 7);
        """
    )
    conn.commit()
    return conn


def test_emits_all_senses_with_tagcount_ordered(tmp_path):
    out = tmp_path / "sense_candidates_provisional.jsonl"
    chains = tmp_path / "chains.jsonl"
    chains.write_text(json.dumps({
        "topic": "apprehension", "topic_synset_id": "1",
        "vehicle": "apprehension", "vehicle_synset_id": "2",
        "chain": [{"synset_id": "1"}, {"synset_id": "2"}]}) + "\n")
    n = bsc.export(_db(), [str(chains)], str(out))
    assert n == 1  # one lemma
    row = json.loads(out.read_text().strip())
    assert row["lemma"] == "apprehension"
    sids = [s["synset_id"] for s in row["senses"]]
    assert set(sids) == {"1", "2"}
    # Tagged sense (tagcount 7) sorts before the untagged (NULL) one.
    assert sids[0] == "2"
    tagged = next(s for s in row["senses"] if s["synset_id"] == "2")
    assert tagged["tagcount"] == 7 and tagged["pos"] == "n"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/agent/projects/metaforge/data-pipeline && .venv/bin/python -m pytest scripts/test_build_sense_candidates.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'build_sense_candidates'`

- [ ] **Step 3: Create the generator (mirrors export_chain_glosses.py)**

Create `data-pipeline/scripts/build_sense_candidates.py`:

```python
"""Precompute candidate senses per endpoint lemma for the sense-check UI.

The grading sidecar is DB-free, so the candidate-sense list the operator picks the
intended sense from is precomputed here and served as
data-pipeline/grading/sense_candidates_provisional.jsonl (one row per lemma:
{lemma, senses:[{synset_id, pos, gloss, tagcount}]}). Senses come from the lexicon's
lemmas⋈synsets; tagcount is the SemCor dominant-sense prior (NULL where untagged),
used only to ORDER the list (most-frequent first) — the rare sense is often the
better metaphor, so this is a hint, not an auto-fix. Re-run after generating chains.
"""

import argparse
import glob
import json
import logging
import sqlite3
from pathlib import Path

log = logging.getLogger(__name__)

_HERE = Path(__file__).resolve()
DEFAULT_DB = str(_HERE.parents[1] / "output" / "lexicon_v2.db")
DEFAULT_CHAINS = sorted(glob.glob(str(_HERE.parents[1] / "grading" / "*chains*.jsonl")))
DEFAULT_OUTPUT = str(_HERE.parents[1] / "grading" / "sense_candidates_provisional.jsonl")

# All senses of a lemma + the SemCor tagcount (NULL where untagged), most-frequent
# first. MAX() collapses any duplicate sense_attributes rows for one lemma+synset.
_SENSES_SQL = """
SELECT l.synset_id, s.pos, s.definition,
       (SELECT MAX(sa.tagcount) FROM sense_attributes sa
        WHERE sa.synset_id = l.synset_id AND sa.lemma = l.lemma) AS tagcount
FROM lemmas l
JOIN synsets s ON s.synset_id = l.synset_id
WHERE l.lemma = ?
ORDER BY (tagcount IS NULL), tagcount DESC, l.synset_id
"""


def collect_lemmas(chain_paths: list[str]) -> set[str]:
    """Endpoint lemmas (topic + vehicle) referenced by the chains."""
    lemmas: set[str] = set()
    for path in chain_paths:
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    chain = json.loads(line)
                except json.JSONDecodeError:
                    continue
                for key in ("topic", "vehicle"):
                    if chain.get(key):
                        lemmas.add(chain[key])
    return lemmas


def export(conn: sqlite3.Connection, chain_paths: list[str], output: str) -> int:
    """Write {lemma, senses:[...]} for each endpoint lemma with >=1 sense."""
    lemmas = collect_lemmas(chain_paths)
    n = 0
    with open(output, "w", encoding="utf-8") as fh:
        for lemma in sorted(lemmas):
            rows = conn.execute(_SENSES_SQL, (lemma,)).fetchall()
            if not rows:
                continue
            senses = [{"synset_id": r[0], "pos": r[1], "gloss": r[2], "tagcount": r[3]}
                      for r in rows]
            fh.write(json.dumps({"lemma": lemma, "senses": senses}) + "\n")
            n += 1
    return n


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Precompute candidate senses for sense-check.")
    p.add_argument("--db", default=DEFAULT_DB)
    p.add_argument("--chains", nargs="*", default=DEFAULT_CHAINS)
    p.add_argument("-o", "--output", default=DEFAULT_OUTPUT)
    args = p.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    conn = sqlite3.connect(args.db)
    try:
        n = export(conn, args.chains, args.output)
    finally:
        conn.close()
    log.info("wrote %d lemma candidate rows -> %s", n, args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /home/agent/projects/metaforge/data-pipeline && .venv/bin/python -m pytest scripts/test_build_sense_candidates.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add data-pipeline/scripts/build_sense_candidates.py data-pipeline/scripts/test_build_sense_candidates.py
git commit -m "feat(grading): candidate-senses precompute generator (lemma -> senses + tagcount)"
```

---

## Task 7: Frontend types + client methods

**Files:**
- Modify: `web/src/types/grading.ts`
- Modify: `web/src/api/grading-client.ts`
- Test: `web/src/api/grading-client.test.ts`

- [ ] **Step 1: Write the failing test**

Append to `web/src/api/grading-client.test.ts` (inside the existing top-level `describe`, mirroring the `getGlosses`/`postRegrade` tests):

```typescript
    it('getSenseCheckSample requests the stratified sample endpoint', async () => {
        fetchMock.mockResolvedValue({ ok: true, status: 200, json: async () => ({ count: 0, items: [] }) });
        const client = new GradingClient();
        await client.getSenseCheckSample({ nFlagged: 40, nRandom: 40, seed: 3 });
        expect(fetchMock).toHaveBeenCalledWith('/api/grading/sense-check/sample?n_flagged=40&n_random=40&seed=3');
    });

    it('postSenseLabel POSTs to the sense-check endpoint', async () => {
        fetchMock.mockResolvedValue({ ok: true, status: 200, json: async () => ({}) });
        const client = new GradingClient();
        await client.postSenseLabel({
            schema_version: 'sense_label.v1', role: 'topic', word: 'apprehension',
            snapped_synset_id: '1760', verdict: 'wrong', intended_synset_id: '72797',
            chain_signature: 'a',
        });
        expect(fetchMock).toHaveBeenCalledWith('/api/grading/sense-check', expect.objectContaining({ method: 'POST' }));
    });
```

> If the existing test file references `fetchMock`/`GradingClient` differently, match that file's setup; the assertions above are what matter.

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/agent/projects/metaforge/web && npx vitest run src/api/grading-client.test.ts`
Expected: FAIL — `getSenseCheckSample`/`postSenseLabel` not a function.

- [ ] **Step 3: Add the types**

Append to `web/src/types/grading.ts`:

```typescript
// --- Sense-check (anchors snap-correctness to human gold) ---
export type SenseVerdict = 'right' | 'wrong' | 'rare_ok' | 'unsure';

export interface SenseCandidate {
    synset_id: string;
    pos: string | null;
    gloss: string | null;
    tagcount: number | null;
}

export interface SenseContextChain {
    topic: string;
    vehicle: string;
    chain: ChainStep[];
    chain_signature: string;
}

export interface SenseCheckItem {
    role: 'topic' | 'vehicle';
    word: string;
    snapped_synset_id: string;
    stratum: string;
    snapped_gloss: string | null;
    pos: string | null;
    candidates: SenseCandidate[];
    context: { chains: SenseContextChain[] };
    chain_signature: string | null;
}

export interface SenseCheckSample {
    count: number;
    items: SenseCheckItem[];
}

// Posted on each verdict. ts is server-injected (omit on construction).
export interface SenseLabel {
    schema_version: 'sense_label.v1';
    ts?: string;
    role: 'topic' | 'vehicle';
    word: string;
    snapped_synset_id: string;
    verdict: SenseVerdict;
    intended_synset_id: string | null;
    chain_signature: string | null;
}
```

- [ ] **Step 4: Add the client methods**

In `web/src/api/grading-client.ts`, extend the import on line 1 to include the new types:

```typescript
import type { ChainRecord, GlossMap, JudgementRecord, RegradeAgreement, SenseCheckSample, SenseLabel, SignalReport, TopicSummary, WalkResponse } from '../types/grading';
```

Add these methods inside the `GradingClient` class (after `getRegradeAgreement`):

```typescript
    /** Draw a stratified sense-check sample (endpoints + candidates + context). */
    async getSenseCheckSample(opts: { nFlagged: number; nRandom: number; seed: number }): Promise<SenseCheckSample> {
        const q = `n_flagged=${opts.nFlagged}&n_random=${opts.nRandom}&seed=${opts.seed}`;
        const r = await fetch(`${BASE}/sense-check/sample?${q}`);
        if (!r.ok) throw new Error(`getSenseCheckSample: ${r.status}`);
        return r.json();
    }

    /** Sense label → the SEPARATE sense-labels file (never the gold judgements). */
    async postSenseLabel(l: SenseLabel): Promise<SenseLabel> {
        return this._postWithRetry(`${BASE}/sense-check`, l, 'postSenseLabel');
    }
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd /home/agent/projects/metaforge/web && npx vitest run src/api/grading-client.test.ts`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add web/src/types/grading.ts web/src/api/grading-client.ts web/src/api/grading-client.test.ts
git commit -m "feat(grading): sense-check types + client (getSenseCheckSample, postSenseLabel)"
```

---

## Task 8: Component — phases, item render, verdict POST/advance

**Files:**
- Create: `web/src/components/mf-grade-sensecheck.ts`
- Test: `web/src/components/mf-grade-sensecheck.test.ts`

- [ ] **Step 1: Write the failing test**

Create `web/src/components/mf-grade-sensecheck.test.ts`:

```typescript
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import './mf-grade-sensecheck';
import { MfGradeSensecheck } from './mf-grade-sensecheck';
import type { SenseCheckItem } from '../types/grading';

const tick = () => new Promise(r => setTimeout(r, 0));

function item(word = 'apprehension', role: 'topic' | 'vehicle' = 'topic'): SenseCheckItem {
    return {
        role, word, snapped_synset_id: '1760', stratum: 'flagged',
        snapped_gloss: 'the act of arresting a criminal', pos: 'n',
        candidates: [
            { synset_id: '1760', pos: 'n', gloss: 'the act of arresting a criminal', tagcount: 2 },
            { synset_id: '72797', pos: 'n', gloss: 'fearful expectation', tagcount: null },
        ],
        context: { chains: [
            { topic: 'apprehension', vehicle: 'avalanche', chain_signature: 'a',
              chain: [{ phrase: 'apprehension', head: 'apprehension', synset_id: '1760' },
                      { phrase: 'avalanche', head: 'avalanche', synset_id: '9' }] },
        ] },
        chain_signature: 'a',
    };
}

describe('mf-grade-sensecheck', () => {
    let el: MfGradeSensecheck;
    let getSenseCheckSample: ReturnType<typeof vi.fn>;
    let postSenseLabel: ReturnType<typeof vi.fn>;

    beforeEach(async () => {
        getSenseCheckSample = vi.fn().mockResolvedValue({ count: 2, items: [item(), item('river', 'vehicle')] });
        postSenseLabel = vi.fn().mockResolvedValue({});
        el = document.createElement('mf-grade-sensecheck') as MfGradeSensecheck;
        el.client = { getSenseCheckSample, postSenseLabel } as any;
        document.body.appendChild(el);
        await el.updateComplete;
    });
    afterEach(() => el.remove());

    const start = async () => {
        (el.shadowRoot!.querySelector('[data-testid="sensecheck-start"]') as HTMLElement).click();
        await el.updateComplete; await tick(); await el.updateComplete;
    };
    const click = async (sel: string) => {
        (el.shadowRoot!.querySelector(sel) as HTMLElement).click();
        await el.updateComplete; await tick(); await el.updateComplete;
    };

    it('shows only a start button before a batch is drawn', () => {
        expect(el.shadowRoot!.querySelector('[data-testid="sensecheck-start"]')).toBeTruthy();
        expect(el.shadowRoot!.querySelector('[data-testid="sensecheck-item"]')).toBeNull();
    });

    it('draws a sample and renders the first item word/role/gloss', async () => {
        await start();
        expect(getSenseCheckSample).toHaveBeenCalledOnce();
        const txt = el.shadowRoot!.querySelector('[data-testid="sensecheck-item"]')!.textContent!;
        expect(txt).toContain('apprehension');
        expect(txt).toContain('topic');
        expect(txt).toContain('the act of arresting a criminal');
        expect(el.shadowRoot!.querySelector('[data-testid="sensecheck-progress"]')!.textContent).toContain('1 / 2');
    });

    it('posts a "right" verdict (no intended) and advances', async () => {
        await start();
        await click('[data-testid="verdict-right"]');
        expect(postSenseLabel).toHaveBeenCalledOnce();
        const posted = postSenseLabel.mock.calls[0][0];
        expect(posted.verdict).toBe('right');
        expect(posted.intended_synset_id).toBeNull();
        expect(posted.snapped_synset_id).toBe('1760');
        expect(el.shadowRoot!.querySelector('[data-testid="sensecheck-progress"]')!.textContent).toContain('2 / 2');
    });

    it('does not advance when a POST fails (no lost label)', async () => {
        await start();
        postSenseLabel.mockRejectedValue(new Error('postSenseLabel: 500'));
        await click('[data-testid="verdict-right"]');
        expect(el.shadowRoot!.querySelector('[data-testid="sensecheck-progress"]')!.textContent).toContain('1 / 2');
        expect((el.shadowRoot!.textContent || '').toLowerCase()).toContain('error');
    });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/agent/projects/metaforge/web && npx vitest run src/components/mf-grade-sensecheck.test.ts`
Expected: FAIL — element/module not defined.

- [ ] **Step 3: Create the component**

Create `web/src/components/mf-grade-sensecheck.ts`:

```typescript
import { LitElement, html, css } from 'lit';
import { customElement, property, state } from 'lit/decorators.js';
import type { GradingClient } from '../api/grading-client';
import type { SenseCandidate, SenseCheckItem, SenseLabel, SenseVerdict } from '../types/grading';

// Self-contained sense-check session. Owns its own sample, cursor and POSTs —
// like mf-grade-regrade — because its labels go to the SEPARATE sense-labels file,
// never the gold judgements. mf-app only mounts it and hands down the client.
type Phase = 'idle' | 'loading' | 'labelling' | 'done' | 'error';

const BATCH_FLAGGED = 40;
const BATCH_RANDOM = 40;

type SenseCheckClient = Pick<GradingClient, 'getSenseCheckSample' | 'postSenseLabel'>;

@customElement('mf-grade-sensecheck')
export class MfGradeSensecheck extends LitElement {
    static styles = css`
        :host { display: block; }
        .intro { padding: 0.5rem; color: #c8c8c8; font-size: 0.9rem; max-width: 34rem; }
        .intro .muted { color: #8a93a2; font-size: 0.82rem; display: block; margin-top: 0.3rem; }
        button.primary {
            margin: 0.4rem 0.5rem; padding: 0.45rem 0.9rem; cursor: pointer; font-size: 0.88rem;
            background: #181b22; color: #e6e6e6; border: 1px solid #2a3140; border-radius: 4px;
        }
        button.primary:hover { border-color: #6db86d; }
        .bar { display: flex; align-items: center; gap: 0.7rem; flex-wrap: wrap;
            padding: 0.5rem; border-bottom: 1px solid #2a3140; margin-bottom: 0.5rem; }
        .badge { color: #d6a560; font-size: 0.72rem; text-transform: uppercase; letter-spacing: 0.06em; }
        .pos { font-variant-numeric: tabular-nums; color: #c8c8c8; min-width: 4.5em; }
        .err { color: #e09a9a; padding: 0.5rem; font-size: 0.85rem; }
        .item { margin: 0.5rem; padding: 0.7rem 0.8rem; background: #14171d;
            border: 1px solid #2a3140; border-radius: 6px; max-width: 34rem; }
        .role { font-size: 0.68rem; text-transform: uppercase; letter-spacing: 0.05em; color: #8a93a2; }
        .word { font-size: 1.15rem; color: #e6e6e6; margin: 0 0.4rem; }
        .gloss { color: #97a0ae; font-size: 0.9rem; display: block; margin: 0.3rem 0 0.6rem; }
        .verdicts { display: flex; gap: 0.5rem; flex-wrap: wrap; }
        button.verdict { padding: 0.5rem 0.9rem; font-size: 0.9rem; cursor: pointer;
            background: #181b22; color: #e6e6e6; border: 1px solid #2a3140; border-radius: 4px; }
        button.verdict.right { border-color: #6db86d; }
        button.verdict.wrong { border-color: #c47a7a; }
        button.verdict.rare { border-color: #d6a560; }
        button.verdict.pending { box-shadow: inset 0 0 0 2px #4d5566; }
        .candidates { margin: 0.6rem 0; display: flex; flex-direction: column; gap: 0.3rem; }
        button.cand { text-align: left; padding: 0.4rem 0.6rem; cursor: pointer;
            background: #181b22; color: #d6dae2; border: 1px solid #2a3140; border-radius: 4px; font-size: 0.84rem; }
        button.cand:hover { border-color: #6db86d; }
        button.cand .cpos { color: #9ec4ff; margin-right: 0.4rem; }
        button.cand .ctag { color: #8a93a2; margin-left: 0.4rem; font-size: 0.78rem; }
        .ctx-toggle { margin-top: 0.6rem; background: none; border: none; color: #9ec4ff;
            cursor: pointer; font-size: 0.8rem; padding: 0; }
        .ctx { margin-top: 0.4rem; border-top: 1px solid #2a3140; padding-top: 0.4rem; }
        .ctx-chain { font-size: 0.82rem; color: #b8bfca; margin: 0.2rem 0; }
        .ctx-arrow { color: #4d5260; margin: 0 0.25rem; }
        .done { padding: 0.7rem; color: #c8c8c8; }
    `;

    @property({ attribute: false }) client!: SenseCheckClient;

    @state() private phase: Phase = 'idle';
    @state() private sample: SenseCheckItem[] = [];
    @state() private index = 0;
    @state() private pendingVerdict: SenseVerdict | null = null;
    @state() private showContext = false;
    @state() private error: string | null = null;

    private get current(): SenseCheckItem | null {
        return this.sample[this.index] ?? null;
    }

    private _seed(): number {
        return Math.floor(Math.random() * 1_000_000);
    }

    private async _start(): Promise<void> {
        this.phase = 'loading';
        this.error = null;
        try {
            const res = await this.client.getSenseCheckSample(
                { nFlagged: BATCH_FLAGGED, nRandom: BATCH_RANDOM, seed: this._seed() });
            this.sample = res.items;
            this.index = 0;
            this.pendingVerdict = null;
            this.showContext = false;
            this.phase = this.sample.length ? 'labelling' : 'done';
        } catch (e) {
            this.error = e instanceof Error ? e.message : 'failed to draw a sense-check batch';
            this.phase = 'error';
        }
    }

    // right / unsure POST immediately (no intended sense). wrong / rare_ok reveal the
    // candidate picker; the chosen candidate's synset_id rides as intended_synset_id.
    private _onVerdict(verdict: SenseVerdict): void {
        if (verdict === 'wrong' || verdict === 'rare_ok') {
            this.pendingVerdict = verdict;
            return;
        }
        void this._post(verdict, null);
    }

    private _onCandidate(c: SenseCandidate): void {
        if (!this.pendingVerdict) return;
        void this._post(this.pendingVerdict, c.synset_id);
    }

    private async _post(verdict: SenseVerdict, intended: string | null): Promise<void> {
        const it = this.current;
        if (!it) return;
        const label: SenseLabel = {
            schema_version: 'sense_label.v1',
            role: it.role,
            word: it.word,
            snapped_synset_id: it.snapped_synset_id,
            verdict,
            intended_synset_id: intended,
            chain_signature: it.chain_signature,
        };
        try {
            await this.client.postSenseLabel(label);
            this.error = null;
            this.index += 1;
            this.pendingVerdict = null;
            this.showContext = false;
            if (this.index >= this.sample.length) this.phase = 'done';
        } catch (err) {
            // Keep the item so the operator can retry — no lost label.
            this.error = err instanceof Error ? err.message : 'failed to record sense label';
        }
    }

    render() {
        if (this.phase === 'idle') return this._renderIntro();
        if (this.phase === 'error') return html`
            <div class="err" data-testid="sensecheck-error">error: ${this.error}</div>
            <button class="primary" data-testid="sensecheck-start" @click=${this._start}>Try again</button>`;
        if (this.phase === 'loading') return html`<div class="intro">drawing a sense-check batch…</div>`;
        if (this.phase === 'labelling') return this._renderItem();
        return html`
            <div class="done" data-testid="sensecheck-done">Batch complete — your sense labels are saved.</div>
            <button class="primary" data-testid="sensecheck-start" @click=${this._start}>Label another batch</button>`;
    }

    private _renderIntro() {
        return html`
            <div class="intro">
                Sense-check — confirm whether each endpoint's snapped sense is the one the metaphor intends.
                Anchors the auto-flags and the planned re-snapper to your judgement.
                <span class="muted">Labels go to a separate file; your grades are never touched.</span>
            </div>
            <button class="primary" data-testid="sensecheck-start" @click=${this._start}>Start sense-check</button>`;
    }

    private _renderItem() {
        const it = this.current!;
        return html`
            <div class="bar" role="toolbar" aria-label="Sense-check">
                <span class="badge">sense-check</span>
                <span class="pos" data-testid="sensecheck-progress" aria-live="polite">${this.index + 1} / ${this.sample.length}</span>
            </div>
            ${this.error ? html`<div class="err" data-testid="sensecheck-error">error: ${this.error}</div>` : ''}
            <div class="item" data-testid="sensecheck-item">
                <span class="role">${it.role}</span><span class="word">${it.word}</span>
                ${it.pos ? html`<span class="role">${it.pos}</span>` : ''}
                <span class="gloss">${it.snapped_gloss ?? '(no gloss available)'}</span>
                <div class="verdicts">
                    <button class="verdict right" data-testid="verdict-right" @click=${() => this._onVerdict('right')}>Right</button>
                    <button class="verdict wrong ${this.pendingVerdict === 'wrong' ? 'pending' : ''}" data-testid="verdict-wrong" @click=${() => this._onVerdict('wrong')}>Wrong</button>
                    <button class="verdict rare ${this.pendingVerdict === 'rare_ok' ? 'pending' : ''}" data-testid="verdict-rare" @click=${() => this._onVerdict('rare_ok')}>Rare-but-better</button>
                    <button class="verdict" data-testid="verdict-unsure" @click=${() => this._onVerdict('unsure')}>Unsure</button>
                </div>
                ${this.pendingVerdict ? this._renderCandidates(it) : ''}
                ${this._renderContext(it)}
            </div>`;
    }

    private _renderCandidates(it: SenseCheckItem) {
        if (!it.candidates.length) return html`<div class="err">no candidate senses available — pick "Unsure" or fix the precompute</div>`;
        return html`
            <div class="candidates" data-testid="sensecheck-candidates">
                <span class="role">intended sense?</span>
                ${it.candidates.map(c => html`
                    <button class="cand" data-testid="cand-${c.synset_id}" @click=${() => this._onCandidate(c)}>
                        ${c.pos ? html`<span class="cpos">${c.pos}</span>` : ''}${c.gloss}
                        ${c.tagcount != null ? html`<span class="ctag">tagcount ${c.tagcount}</span>` : ''}
                    </button>`)}
            </div>`;
    }

    private _renderContext(it: SenseCheckItem) {
        return html`
            <button class="ctx-toggle" data-testid="ctx-toggle"
                    @click=${() => { this.showContext = !this.showContext; }}>
                ${this.showContext ? 'hide context' : `show context (${it.context.chains.length} chain${it.context.chains.length === 1 ? '' : 's'})`}
            </button>
            ${this.showContext ? html`
                <div class="ctx" data-testid="sensecheck-context">
                    ${it.context.chains.map(c => html`
                        <div class="ctx-chain">
                            ${c.chain.map((s, i) => html`${s.head}${i < c.chain.length - 1 ? html`<span class="ctx-arrow">→</span>` : ''}`)}
                        </div>`)}
                </div>` : ''}`;
    }
}

declare global {
    interface HTMLElementTagNameMap {
        'mf-grade-sensecheck': MfGradeSensecheck;
    }
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /home/agent/projects/metaforge/web && npx vitest run src/components/mf-grade-sensecheck.test.ts`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add web/src/components/mf-grade-sensecheck.ts web/src/components/mf-grade-sensecheck.test.ts
git commit -m "feat(grading): mf-grade-sensecheck component (phases, verdict POST/advance)"
```

---

## Task 9: Component — candidate picker on wrong/rare sets intended_synset_id

**Files:**
- Modify: `web/src/components/mf-grade-sensecheck.test.ts`
- (implementation already written in Task 8 — this task adds the proving test)

- [ ] **Step 1: Write the failing test**

Append inside the `describe` in `web/src/components/mf-grade-sensecheck.test.ts`:

```typescript
    it('Wrong reveals candidates; picking one posts that intended_synset_id', async () => {
        await start();
        // No candidate list until a Wrong/Rare verdict.
        expect(el.shadowRoot!.querySelector('[data-testid="sensecheck-candidates"]')).toBeNull();
        await click('[data-testid="verdict-wrong"]');
        expect(el.shadowRoot!.querySelector('[data-testid="sensecheck-candidates"]')).toBeTruthy();
        // No POST yet — we still need the intended sense.
        expect(postSenseLabel).not.toHaveBeenCalled();
        await click('[data-testid="cand-72797"]');
        const posted = postSenseLabel.mock.calls[0][0];
        expect(posted.verdict).toBe('wrong');
        expect(posted.intended_synset_id).toBe('72797');
        expect(el.shadowRoot!.querySelector('[data-testid="sensecheck-progress"]')!.textContent).toContain('2 / 2');
    });
```

- [ ] **Step 2: Run test to verify it passes (implementation already exists)**

Run: `cd /home/agent/projects/metaforge/web && npx vitest run src/components/mf-grade-sensecheck.test.ts`
Expected: PASS — confirms the Task 8 implementation satisfies the picker contract.

> If it fails, fix `mf-grade-sensecheck.ts` (the `_onVerdict`/`_onCandidate`/`_renderCandidates` path), not the test.

- [ ] **Step 3: Commit**

```bash
git add web/src/components/mf-grade-sensecheck.test.ts
git commit -m "test(grading): sense-check candidate picker sets intended_synset_id"
```

---

## Task 10: Component — context expander shows all chains

**Files:**
- Modify: `web/src/components/mf-grade-sensecheck.test.ts`
- (implementation already written in Task 8)

- [ ] **Step 1: Write the failing test**

Append inside the `describe`:

```typescript
    it('context expander reveals the endpoint\'s chains on demand', async () => {
        getSenseCheckSample.mockResolvedValue({
            count: 1, items: [{
                ...item(),
                context: { chains: [
                    { topic: 'apprehension', vehicle: 'avalanche', chain_signature: 'a',
                      chain: [{ phrase: 'apprehension', head: 'apprehension', synset_id: '1760' },
                              { phrase: 'avalanche', head: 'avalanche', synset_id: '9' }] },
                    { topic: 'apprehension', vehicle: 'trapdoor', chain_signature: 'b',
                      chain: [{ phrase: 'apprehension', head: 'apprehension', synset_id: '1760' },
                              { phrase: 'trapdoor', head: 'trapdoor', synset_id: '8' }] },
                ] },
            }],
        });
        await start();
        // Collapsed by default.
        expect(el.shadowRoot!.querySelector('[data-testid="sensecheck-context"]')).toBeNull();
        expect(el.shadowRoot!.querySelector('[data-testid="ctx-toggle"]')!.textContent).toContain('2 chains');
        await click('[data-testid="ctx-toggle"]');
        const ctx = el.shadowRoot!.querySelector('[data-testid="sensecheck-context"]')!.textContent!;
        expect(ctx).toContain('avalanche');   // both chains shown
        expect(ctx).toContain('trapdoor');
    });
```

- [ ] **Step 2: Run test to verify it passes**

Run: `cd /home/agent/projects/metaforge/web && npx vitest run src/components/mf-grade-sensecheck.test.ts`
Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add web/src/components/mf-grade-sensecheck.test.ts
git commit -m "test(grading): sense-check context expander shows all endpoint chains"
```

---

## Task 11: mf-app — mount the 4th grade view

**Files:**
- Modify: `web/src/components/mf-app.ts:35,408,589-590,633,800,808-812,1257-1263` + add `renderGradeSenseCheck`
- Test: `web/src/components/mf-app.test.ts`

- [ ] **Step 1: Write the failing test**

Append a test to `web/src/components/mf-app.test.ts` (mirror the existing regrade-mount test near line 1599; adapt selectors to that file's harness for constructing `mf-app` in grade mode):

```typescript
    it('mounts mf-grade-sensecheck with the client when the sense-check view is selected', async () => {
        // el is an mf-app already in grade mode (see the regrade-mount test for setup).
        (el as any).gradeView = 'sensecheck';
        await el.updateComplete;
        const shell = el.shadowRoot!.querySelector('[data-testid="grade-sensecheck"]') as any;
        expect(shell).toBeTruthy();
        expect(shell.client).toBe((el as any).gradingClient);
    });
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/agent/projects/metaforge/web && npx vitest run src/components/mf-app.test.ts -t "sense-check view"`
Expected: FAIL — no `grade-sensecheck` element.

- [ ] **Step 3: Wire the view into mf-app**

In `web/src/components/mf-app.ts`:

(a) After line 35 (`import './mf-grade-regrade'`), add:

```typescript
import './mf-grade-sensecheck'
```

(b) Widen the `gradeView` union everywhere it appears. Line 408:

```typescript
  @state() private gradeView: 'topic' | 'walk' | 'regrade' | 'sensecheck' = 'topic'
```

Lines 589-590:

```typescript
    const storedView = localStorage.getItem('mf-grade-view')
    if (storedView === 'walk' || storedView === 'topic' || storedView === 'regrade' || storedView === 'sensecheck') this.gradeView = storedView
```

Line 633 (`setGradeView` signature):

```typescript
  private setGradeView(view: 'topic' | 'walk' | 'regrade' | 'sensecheck'): void {
```

Line 800 (`opt` signature inside `renderGradeViewToggle`):

```typescript
    const opt = (view: 'topic' | 'walk' | 'regrade' | 'sensecheck', label: string) => html`
```

(c) Add the toggle button. After line 811 (`${opt('regrade', 'Blind re-grade')}`):

```typescript
        ${opt('sensecheck', 'Sense-check')}
```

(d) Add the render method. After `renderGradeRegrade()` (ends ~line 1238), add:

```typescript
  /** Sense-check view — its own toggle row + the self-contained sense-check shell
   *  (owns sample/cursor/POSTs to the separate sense-labels file). */
  private renderGradeSenseCheck() {
    return html`
      <div class="grade-layout" data-testid="grade-sensecheck-layout">
        <div class="grade-top">
          ${this.renderGradeViewToggle()}
        </div>
        <div class="grade-walk-scroll">
          <mf-grade-sensecheck
            data-testid="grade-sensecheck"
            .client=${this.gradingClient}
          ></mf-grade-sensecheck>
        </div>
      </div>
    `
  }
```

(e) Extend the render switch (lines ~1257-1263) to route the sense-check view:

```typescript
      ${this.mode === 'grade'
        ? (this.gradeView === 'walk'
            ? this.renderGradeWalk()
            : this.gradeView === 'regrade'
              ? this.renderGradeRegrade()
              : this.gradeView === 'sensecheck'
                ? this.renderGradeSenseCheck()
                : (this.viewportWidth >= 900 ? this.renderGradeModeDesktop() : this.renderGradeModeMobile()))
        : this.renderBrowseMode()}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /home/agent/projects/metaforge/web && npx vitest run src/components/mf-app.test.ts -t "sense-check view"`
Expected: PASS

- [ ] **Step 5: Run the full web + sidecar suites (no regressions)**

Run: `cd /home/agent/projects/metaforge/web && npx vitest run`
Run: `cd /home/agent/projects/metaforge/data-pipeline && .venv/bin/python -m pytest grading_sidecar/tests/ scripts/test_build_sense_candidates.py -q`
Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add web/src/components/mf-app.ts web/src/components/mf-app.test.ts
git commit -m "feat(grading): mount sense-check as the 4th grade view"
```

---

## Task 12: Generate the candidate precompute + manual smoke

**Files:** none (operational step; run against the real lexicon).

- [ ] **Step 1: Generate the candidate-senses precompute**

Run: `cd /home/agent/projects/metaforge/data-pipeline && .venv/bin/python scripts/build_sense_candidates.py`
Expected: `INFO: wrote N lemma candidate rows -> .../grading/sense_candidates_provisional.jsonl` (N ≈ the distinct endpoint lemmas).

- [ ] **Step 2: Sanity-check a known mis-snap is covered**

Run: `cd /home/agent/projects/metaforge/data-pipeline && .venv/bin/python -c "import json; rows={r['lemma']:r for r in map(json.loads, open('grading/sense_candidates_provisional.jsonl'))}; print('apprehension' in rows, len(rows.get('apprehension',{}).get('senses',[])))"`
Expected: `True` and ≥2 senses (the arrest sense + the dread sense).

- [ ] **Step 3: Commit the generated precompute**

```bash
git add data-pipeline/grading/sense_candidates_provisional.jsonl
git commit -m "data(grading): candidate-senses precompute for sense-check"
```

---

## Self-review

**Spec coverage:**
- Self-contained 4th view mirroring regrade → Tasks 8–11. ✓
- Verdict set Right/Wrong/Rare-but-better/Unsure + candidate picker on wrong/rare → Tasks 8–9. ✓
- Context expander (pairing + all chains) → Tasks 4, 10. ✓
- Stratified sampler (flagged + random-OK, seeded, dedup, exclude labelled) → Task 3. ✓
- Candidate precompute, DB-free → Tasks 4, 6, 12. ✓
- Separate-file persistence invariant → Tasks 1, 5 (route test asserts label never lands in judgements). ✓
- Thin routes + registration → Task 5. ✓
- Endpoints only (steps deferred) → sampler/context operate on topic+vehicle only. ✓

**Placeholder scan:** none — every step carries real code/commands.

**Type consistency:** `SenseLabel`/`SenseVerdict`/`SenseCandidate`/`SenseCheckItem` identical across Python (`models.py`) and TS (`types/grading.ts`); the candidate precompute key is `gloss` in both the generator (Task 6) and the TS type (Task 7); the route returns `{count, items}` consumed by the component's `res.items` (Tasks 5, 8); `chain_signature` flows builder → item → label unchanged.

**Note on field naming:** the candidate precompute uses `gloss` for a sense's definition, whereas the pre-existing `chain_glosses` precompute uses `definition`. This is intentional (separate files) and the route maps `chain_glosses.definition → item.snapped_gloss` while `sense_candidates.gloss → candidate.gloss`. No collision.
