# Grading-app Reconciliation — Round 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give the grading sidecar a source-composing ChainStore (per-reader cohort lists so sense-check sees `stock` context without cluttering grading views), a sense-checker skip button, and a code/data deploy split (env-indirected data location + retargeted autocommit) — landing in one cutover.

**Architecture:** Chain files are grouped into cohorts (`spike`, `curated`, `stock`) by a glob config in `paths.py`; `chain_store` composes the files for a given cohort list. Grading-view readers pass `[spike, curated]`; the sense-check route passes `[spike, curated, stock]`. `stock` lives under a `stock/` subdir the top-level grading globs don't match. The data location (`GRADING_DIR`) and the autocommit git root become env-overridable so the deploy can point them at a separate **data worktree**, leaving the code worktree clean (FF-only). Cohort globs match both new `chain-topics_*` and legacy `sonnet_chains_provisional_*` names, so existing tests pass unchanged and the file rename is a clean isolated step.

**Tech Stack:** Python 3 / FastAPI / pytest (sidecar); Lit + TypeScript + Vitest (web); git worktrees + systemd (deploy).

---

## File structure

**Modify:**
- `data-pipeline/grading_sidecar/paths.py` — cohort config + `GRADING_DATA_DIR` / `GRADING_DATA_GIT_ROOT` env indirection.
- `data-pipeline/grading_sidecar/chain_store.py` — `cohort_files(cohorts)` + `load_chains(cohorts)`.
- `data-pipeline/grading_sidecar/routes/chains.py`, `topics.py`, `stats.py` — direct glob → `cohort_files(GRADING_COHORTS)`.
- `data-pipeline/grading_sidecar/routes/sense_check.py` — `load_chains()` → `load_chains(SENSECHECK_COHORTS)`.
- `data-pipeline/grading_sidecar/app.py` — autocommit targets the data git root.
- `data-pipeline/scripts/export_chain_glosses.py`, `build_sense_candidates.py` — chain globs cover `chain-topics_*` (+ `stock/`).
- `web/src/components/mf-grade-sensecheck.ts` (+ test) — Skip control.

**Rename (git mv, Task 8):** `sonnet_chains_provisional_r1.jsonl` → `chain-topics_spike_r1.jsonl`, `…_r2.jsonl` → `chain-topics_spike_r2.jsonl`, `…_r2_handpicked.jsonl` → `chain-topics_curated.jsonl`. (`chain-topics_stock` enters via the data worktree at cutover.)

**No change (verified):** `routes/walk.py`, `routes/regrade.py` already call `load_chains()` with no args → the new default (`GRADING_COHORTS`) is correct for them.

**Test commands:**
- Sidecar: `cd /home/agent/projects/metaforge/data-pipeline && .venv/bin/python -m pytest <path> -v`
- Scripts: `cd /home/agent/projects/metaforge/data-pipeline/scripts && ../.venv/bin/python -m pytest <file> -v`
- Web: `cd /home/agent/projects/metaforge/web && npx vitest run <path>`

**Guardrail (all tasks):** targeted `git add <paths>` only — the working tree holds unrelated untracked Phase-B-era files that must never be swept in.

---

## Task 1: Cohort config + data-location env indirection (paths.py)

**Files:**
- Modify: `data-pipeline/grading_sidecar/paths.py`
- Test: `data-pipeline/grading_sidecar/tests/test_paths_cohorts.py` (new)

- [ ] **Step 1: Write the failing test**

Create `data-pipeline/grading_sidecar/tests/test_paths_cohorts.py`:

```python
"""Cohort config + env-indirected data location."""
from __future__ import annotations
import importlib
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))


def _reload_paths():
    from grading_sidecar import paths as p
    return importlib.reload(p)


def test_cohort_constants_and_membership():
    p = _reload_paths()
    assert p.GRADING_COHORTS == ["spike", "curated"]          # grading views: no stock
    assert p.SENSECHECK_COHORTS == ["spike", "curated", "stock"]
    # stock globs point under the stock/ subdir; spike/curated match new + legacy names
    assert any("stock/" in g for g in p.CHAIN_COHORTS["stock"])
    assert "chain-topics_spike*.jsonl" in p.CHAIN_COHORTS["spike"]
    assert any("sonnet_chains_provisional_r1" in g for g in p.CHAIN_COHORTS["spike"])  # legacy
    assert "chain-topics_curated*.jsonl" in p.CHAIN_COHORTS["curated"]


def test_data_dir_defaults_in_repo_but_is_env_overridable(monkeypatch, tmp_path):
    p = _reload_paths()
    assert p.GRADING_DIR == p.REPO_ROOT / "data-pipeline" / "grading"   # default unchanged
    assert p.GRADING_DATA_GIT_ROOT == str(p.REPO_ROOT)
    monkeypatch.setenv("GRADING_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("GRADING_DATA_GIT_ROOT", str(tmp_path / "gitroot"))
    p2 = _reload_paths()
    assert p2.GRADING_DIR == tmp_path / "data"
    assert p2.GRADING_DATA_GIT_ROOT == str(tmp_path / "gitroot")
    monkeypatch.delenv("GRADING_DATA_DIR"); monkeypatch.delenv("GRADING_DATA_GIT_ROOT")
    _reload_paths()  # restore module global for other tests
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/agent/projects/metaforge/data-pipeline && .venv/bin/python -m pytest grading_sidecar/tests/test_paths_cohorts.py -v`
Expected: FAIL — `AttributeError: module 'grading_sidecar.paths' has no attribute 'GRADING_COHORTS'`.

- [ ] **Step 3: Edit paths.py**

At the top of `data-pipeline/grading_sidecar/paths.py`, add `import os` (after `from __future__ import annotations`). Change the `GRADING_DIR` line and append the cohort + git-root config:

```python
import os
# ...
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
# Data location is env-overridable so the deploy can point it at a SEPARATE data
# worktree (code/data separation). Default = in-repo, so dev + every test is unchanged.
GRADING_DIR = Path(os.environ.get("GRADING_DATA_DIR", str(REPO_ROOT / "data-pipeline" / "grading")))
# Git root the autocommit targets: the data worktree in deploy, the main repo in dev.
GRADING_DATA_GIT_ROOT = os.environ.get("GRADING_DATA_GIT_ROOT", str(REPO_ROOT))
```

Then append (after the existing `CHAIN_GLOSSES_NAME` block):

```python
# --- Chain cohorts (source-by-location) ---
# Grading views (walk/topic/stats/chains/regrade) read GRADING_COHORTS. The
# sense-check context reads SENSECHECK_COHORTS (adds `stock`). `stock` lives under a
# stock/ subdir the top-level grading globs DON'T match, so it never surfaces in
# grading views. Globs are relative to GRADING_DIR. spike/curated match the new
# chain-topics_* names AND the legacy sonnet_chains_provisional_* names (transitional —
# drop the legacy entries once the data rename in Task 8 has propagated everywhere).
CHAIN_COHORTS: dict[str, list[str]] = {
    "spike":   ["chain-topics_spike*.jsonl",
                "sonnet_chains_provisional_r1*.jsonl",
                "sonnet_chains_provisional_r2.jsonl"],
    "curated": ["chain-topics_curated*.jsonl",
                "sonnet_chains_provisional_r2_handpicked*.jsonl"],
    "stock":   ["stock/chain-topics_stock*.jsonl"],
}
GRADING_COHORTS = ["spike", "curated"]
SENSECHECK_COHORTS = ["spike", "curated", "stock"]
```

(Leave `CHAINS_GLOB` in place — still referenced until Task 3 converts the direct-glob routes; it becomes unused after.)

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /home/agent/projects/metaforge/data-pipeline && .venv/bin/python -m pytest grading_sidecar/tests/test_paths_cohorts.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add data-pipeline/grading_sidecar/paths.py data-pipeline/grading_sidecar/tests/test_paths_cohorts.py
git commit -m "feat(grading): chain-cohort config + env-indirected data location"
```

---

## Task 2: ChainStore — cohort_files + load_chains(cohorts)

**Files:**
- Modify: `data-pipeline/grading_sidecar/chain_store.py`
- Test: `data-pipeline/grading_sidecar/tests/test_chain_store.py`

- [ ] **Step 1: Write the failing test**

Append to `data-pipeline/grading_sidecar/tests/test_chain_store.py`:

```python
def _chain(sig, topic="t", vehicle="v"):
    return {"chain_signature": sig, "topic": topic, "vehicle": vehicle,
            "topic_synset_id": "1", "vehicle_synset_id": "2", "chain": []}


def test_load_chains_cohort_selection_excludes_stock_for_grading(tmp_path, monkeypatch):
    import json
    from grading_sidecar import paths as paths_mod
    from grading_sidecar import chain_store
    monkeypatch.setattr(paths_mod, "GRADING_DIR", tmp_path)
    (tmp_path / "stock").mkdir()
    (tmp_path / "chain-topics_curated.jsonl").write_text(json.dumps(_chain("c1")) + "\n")
    (tmp_path / "sonnet_chains_provisional_r1.jsonl").write_text(json.dumps(_chain("s1")) + "\n")  # legacy spike
    (tmp_path / "stock" / "chain-topics_stock.jsonl").write_text(json.dumps(_chain("k1")) + "\n")

    grading = {c["chain_signature"] for c in chain_store.load_chains(paths_mod.GRADING_COHORTS)}
    assert grading == {"c1", "s1"}                       # stock excluded from grading views
    full = {c["chain_signature"] for c in chain_store.load_chains(paths_mod.SENSECHECK_COHORTS)}
    assert full == {"c1", "s1", "k1"}                    # sense-check sees stock
    # default (no args) == grading cohorts
    assert {c["chain_signature"] for c in chain_store.load_chains()} == {"c1", "s1"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/agent/projects/metaforge/data-pipeline && .venv/bin/python -m pytest grading_sidecar/tests/test_chain_store.py::test_load_chains_cohort_selection_excludes_stock_for_grading -v`
Expected: FAIL — `load_chains()` takes no positional arg / stock leaks in.

- [ ] **Step 3: Rewrite chain_store.py**

Replace the body of `data-pipeline/grading_sidecar/chain_store.py` (keep the module docstring + imports + `_REQUIRED_CHAIN_KEYS`):

```python
def cohort_files(cohorts: list[str]):
    """Yield the chain files for `cohorts`, in cohort-then-filename order.

    The fall-through composition: each reader picks which cohorts it sees by passing
    a cohort list. Patterns are resolved relative to paths.GRADING_DIR."""
    for cohort in cohorts:
        for pattern in paths_mod.CHAIN_COHORTS.get(cohort, []):
            yield from sorted(paths_mod.GRADING_DIR.glob(pattern))


def load_chains(cohorts: list[str] | None = None) -> list[dict]:
    """Union the cohort files; drop records missing required keys; dedup by signature
    (last file wins). Defaults to the grading-view cohorts (no stock)."""
    if cohorts is None:
        cohorts = paths_mod.GRADING_COHORTS
    by_sig: dict[str, dict] = {}
    dropped = 0
    for p in cohort_files(cohorts):
        recs, _ = read_jsonl_skip_malformed(p)
        for r in recs:
            if not all(r.get(k) for k in _REQUIRED_CHAIN_KEYS):
                dropped += 1
                continue
            by_sig[r["chain_signature"]] = r
    if dropped:
        log.warning("load_chains: dropped %d chain record(s) missing required keys", dropped)
    return list(by_sig.values())
```

- [ ] **Step 4: Run tests to verify pass (incl. existing chain_store tests)**

Run: `cd /home/agent/projects/metaforge/data-pipeline && .venv/bin/python -m pytest grading_sidecar/tests/test_chain_store.py -v`
Expected: PASS. (Existing tests write legacy `sonnet_chains_provisional_r*` names — still matched via the legacy globs, so they pass unchanged.)

- [ ] **Step 5: Commit**

```bash
git add data-pipeline/grading_sidecar/chain_store.py data-pipeline/grading_sidecar/tests/test_chain_store.py
git commit -m "feat(grading): cohort-composing ChainStore (cohort_files + load_chains(cohorts))"
```

---

## Task 3: Convert the direct-glob grading routes to cohort_files

**Files:**
- Modify: `data-pipeline/grading_sidecar/routes/chains.py`, `routes/topics.py`, `routes/stats.py`
- Test: `data-pipeline/grading_sidecar/tests/test_chains_endpoint.py` (add a stock-exclusion case)

- [ ] **Step 1: Write the failing test**

Append to `data-pipeline/grading_sidecar/tests/test_chains_endpoint.py` (mirror the file's existing fixture/harness for writing chain files + the monkeypatched GRADING_DIR client):

```python
def test_chains_endpoint_excludes_stock(client, tmp_path, monkeypatch):
    import json
    from grading_sidecar import paths as paths_mod
    monkeypatch.setattr(paths_mod, "GRADING_DIR", tmp_path)
    (tmp_path / "stock").mkdir()
    rec = {"schema_version": "chain.v1", "topic": "t", "topic_synset_id": "1",
           "vehicle": "v", "vehicle_synset_id": "2", "proposer": "p", "round": 1,
           "chain_signature": "a" * 64, "generated_at": "2026-06-01T00:00:00+00:00",
           "chain": [{"phrase": "t", "head": "t", "synset_id": "1"},
                     {"phrase": "v", "head": "v", "synset_id": "2"}]}
    (tmp_path / "chain-topics_curated.jsonl").write_text(json.dumps(rec) + "\n")
    stock = {**rec, "chain_signature": "b" * 64}
    (tmp_path / "stock" / "chain-topics_stock.jsonl").write_text(json.dumps(stock) + "\n")
    body = client.get("/api/grading/chains").json()
    sigs = {r["chain_signature"] for r in body["records"]}
    assert "a" * 64 in sigs and "b" * 64 not in sigs   # stock not in the grading view
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/agent/projects/metaforge/data-pipeline && .venv/bin/python -m pytest grading_sidecar/tests/test_chains_endpoint.py::test_chains_endpoint_excludes_stock -v`
Expected: FAIL — the `chains` route globs `CHAINS_GLOB` which doesn't match `chain-topics_*`, so `a*64` is absent (and/or stock logic missing).

- [ ] **Step 3: Convert the three routes**

In each of `chains.py`, `topics.py`, `stats.py`, add the import `from ..chain_store import cohort_files` and replace the loop header `for p in sorted(paths_mod.GRADING_DIR.glob(paths_mod.CHAINS_GLOB)):` (and the non-sorted variant in `stats.py`) with:

```python
    for p in cohort_files(paths_mod.GRADING_COHORTS):
```

(`cohort_files` already yields in a stable order; drop the now-redundant `sorted(...)`.) No other logic changes — each route keeps its own per-file processing (skipped-count, distinct-topic, count).

- [ ] **Step 4: Run tests to verify pass**

Run: `cd /home/agent/projects/metaforge/data-pipeline && .venv/bin/python -m pytest grading_sidecar/tests/test_chains_endpoint.py grading_sidecar/tests/test_topics_stats_calibration.py -v`
Expected: PASS (existing legacy-named fixtures still load via the legacy globs).

- [ ] **Step 5: Commit**

```bash
git add data-pipeline/grading_sidecar/routes/chains.py data-pipeline/grading_sidecar/routes/topics.py data-pipeline/grading_sidecar/routes/stats.py data-pipeline/grading_sidecar/tests/test_chains_endpoint.py
git commit -m "feat(grading): grading-view routes read [spike,curated] via cohort_files (stock excluded)"
```

---

## Task 4: Sense-check reads stock for context

**Files:**
- Modify: `data-pipeline/grading_sidecar/routes/sense_check.py:34`
- Test: `data-pipeline/grading_sidecar/tests/test_sense_check_endpoint.py`

- [ ] **Step 1: Write the failing test**

Append to `data-pipeline/grading_sidecar/tests/test_sense_check_endpoint.py` (reuse the file's `sc_client` fixture + `_chain` helper):

```python
def test_sense_check_context_includes_stock_chain(sc_client, tmp_path):
    # A flagged endpoint whose only chain lives in the stock cohort must still get context.
    (tmp_path / "stock").mkdir()
    _write(tmp_path / "stock" / "chain-topics_stock.jsonl",
           _chain("c" * 64, "longing", "72598", "drought", "104281"))
    _write(tmp_path / paths_mod.SENSE_FLAGS_NAME,
           {"role": "vehicle", "word": "drought", "synset_id": "104281", "verdict": "WRONG_SENSE"})
    body = sc_client.get("/api/grading/sense-check/sample?n_flagged=5&n_random=0&seed=1").json()
    it = next(i for i in body["items"] if i["word"] == "drought")
    assert it["context"]["chains"][0]["chain_signature"] == "c" * 64   # stock context resolved
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/agent/projects/metaforge/data-pipeline && .venv/bin/python -m pytest grading_sidecar/tests/test_sense_check_endpoint.py::test_sense_check_context_includes_stock_chain -v`
Expected: FAIL — `load_chains()` defaults to grading cohorts (no stock), so the stock chain isn't found and `context.chains` is empty.

- [ ] **Step 3: Pass the sense-check cohort list**

In `data-pipeline/grading_sidecar/routes/sense_check.py`, change line 34 from `chains = load_chains()` to:

```python
    chains = load_chains(paths_mod.SENSECHECK_COHORTS)
```

(`paths_mod` is already imported as `from .. import paths as paths_mod`.)

- [ ] **Step 4: Run tests to verify pass**

Run: `cd /home/agent/projects/metaforge/data-pipeline && .venv/bin/python -m pytest grading_sidecar/tests/test_sense_check_endpoint.py grading_sidecar/tests/test_sense_check.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add data-pipeline/grading_sidecar/routes/sense_check.py data-pipeline/grading_sidecar/tests/test_sense_check_endpoint.py
git commit -m "feat(grading): sense-check composes [spike,curated,stock] so flagged stock items get context"
```

---

## Task 5: Precompute generators cover chain-topics_* (+ stock/)

**Files:**
- Modify: `data-pipeline/scripts/export_chain_glosses.py:22`, `build_sense_candidates.py:22`
- Test: `data-pipeline/scripts/test_export_chain_glosses.py`, `test_build_sense_candidates.py`

- [ ] **Step 1: Write the failing test**

Append to `data-pipeline/scripts/test_build_sense_candidates.py`:

```python
def test_collect_lemmas_matches_new_and_stock_names(tmp_path):
    import json, build_sense_candidates as bsc
    top = tmp_path / "chain-topics_curated.jsonl"
    top.write_text(json.dumps({"topic": "longing", "vehicle": "drought"}) + "\n")
    (tmp_path / "stock").mkdir()
    (tmp_path / "stock" / "chain-topics_stock.jsonl").write_text(
        json.dumps({"topic": "dread", "vehicle": "avalanche"}) + "\n")
    import glob
    paths = sorted(glob.glob(str(tmp_path / "**" / "chain-topics_*.jsonl"), recursive=True))
    lemmas = bsc.collect_lemmas(paths)
    assert {"longing", "drought", "dread", "avalanche"} <= lemmas
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/agent/projects/metaforge/data-pipeline/scripts && ../.venv/bin/python -m pytest test_build_sense_candidates.py::test_collect_lemmas_matches_new_and_stock_names -v`
Expected: PASS or FAIL — `collect_lemmas` already accepts an explicit path list, so this confirms it works on the new names; the change is the DEFAULT glob. If it passes, proceed to Step 3 to fix the defaults (the real gap is the default `*chains*.jsonl` not matching `chain-topics_*`).

- [ ] **Step 3: Update the default globs**

In BOTH `export_chain_glosses.py` and `build_sense_candidates.py`, the `DEFAULT_CHAINS` line currently globs `*chains*.jsonl` (which does NOT match `chain-topics_*`, since that has no "chains"). Replace it with a recursive glob covering new names (top-level + `stock/`) and legacy:

```python
DEFAULT_CHAINS = sorted(
    glob.glob(str(_HERE.parents[1] / "grading" / "**" / "chain-topics_*.jsonl"), recursive=True)
    + glob.glob(str(_HERE.parents[1] / "grading" / "*chains*.jsonl"))
)
```

- [ ] **Step 4: Run tests to verify pass**

Run: `cd /home/agent/projects/metaforge/data-pipeline/scripts && ../.venv/bin/python -m pytest test_build_sense_candidates.py test_export_chain_glosses.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add data-pipeline/scripts/export_chain_glosses.py data-pipeline/scripts/build_sense_candidates.py data-pipeline/scripts/test_build_sense_candidates.py
git commit -m "feat(grading): precompute generators cover chain-topics_* + stock/ (and legacy names)"
```

---

## Task 6: Autocommit targets the data git root

**Files:**
- Modify: `data-pipeline/grading_sidecar/app.py:27`
- Test: `data-pipeline/grading_sidecar/tests/test_app.py`

- [ ] **Step 1: Write the failing test**

Add a small testable helper and assert it reads the env-indirected git root. Append to `data-pipeline/grading_sidecar/tests/test_app.py`:

```python
def test_autocommit_target_uses_data_git_root(monkeypatch):
    from grading_sidecar import app as app_mod
    from grading_sidecar import paths as paths_mod
    monkeypatch.setattr(paths_mod, "GRADING_DATA_GIT_ROOT", "/srv/grading-data")
    root, subdir = app_mod.autocommit_target()
    assert root == "/srv/grading-data"
    assert subdir == "data-pipeline/grading/"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/agent/projects/metaforge/data-pipeline && .venv/bin/python -m pytest grading_sidecar/tests/test_app.py::test_autocommit_target_uses_data_git_root -v`
Expected: FAIL — `app` has no `autocommit_target`.

- [ ] **Step 3: Add the helper + use it in lifespan**

In `data-pipeline/grading_sidecar/app.py`, add the helper (near the top, after imports):

```python
def autocommit_target() -> tuple[str, str]:
    """(git_root, subdir) the autocommit writes to. In deploy these resolve to the
    SEPARATE data worktree via GRADING_DATA_GIT_ROOT; in dev they default to the
    main repo, preserving today's behaviour."""
    return paths_mod.GRADING_DATA_GIT_ROOT, "data-pipeline/grading/"
```

In `lifespan`, replace the `autocommit_loop(str(paths_mod.REPO_ROOT), "data-pipeline/grading/")` call with:

```python
    git_root, subdir = autocommit_target()
    task = asyncio.create_task(autocommit_loop(git_root, subdir))
```

- [ ] **Step 4: Run tests to verify pass**

Run: `cd /home/agent/projects/metaforge/data-pipeline && .venv/bin/python -m pytest grading_sidecar/tests/test_app.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add data-pipeline/grading_sidecar/app.py data-pipeline/grading_sidecar/tests/test_app.py
git commit -m "feat(grading): autocommit targets the env-indirected data git root (code/data split)"
```

---

## Task 7: Sense-checker Skip button

**Files:**
- Modify: `web/src/components/mf-grade-sensecheck.ts`
- Test: `web/src/components/mf-grade-sensecheck.test.ts`

- [ ] **Step 1: Write the failing test**

Append inside the `describe` in `web/src/components/mf-grade-sensecheck.test.ts`:

```typescript
    it('Skip advances without POSTing a label', async () => {
        await start();
        expect(el.shadowRoot!.querySelector('[data-testid="sensecheck-progress"]')!.textContent).toContain('1 / 2');
        (el.shadowRoot!.querySelector('[data-testid="verdict-skip"]') as HTMLElement).click();
        await el.updateComplete; await tick(); await el.updateComplete;
        expect(postSenseLabel).not.toHaveBeenCalled();                 // no label recorded
        expect(el.shadowRoot!.querySelector('[data-testid="sensecheck-progress"]')!.textContent).toContain('2 / 2');
    });
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/agent/projects/metaforge/web && npx vitest run src/components/mf-grade-sensecheck.test.ts -t "Skip advances"`
Expected: FAIL — no `verdict-skip` element.

- [ ] **Step 3: Add the Skip control + handler**

In `web/src/components/mf-grade-sensecheck.ts`, add a `_skip()` method:

```typescript
    private _skip(): void {
        // Advance without recording a verdict; the item may resurface in a later sample.
        if (this._posting) return;
        this.index += 1;
        this.pendingVerdict = null;
        this.showContext = false;
        if (this.index >= this.sample.length) this.phase = 'done';
    }
```

And add the Skip button to the verdicts row in `_renderItem()` (after the Unsure button):

```typescript
                    <button class="verdict" data-testid="verdict-skip" @click=${() => this._skip()}>Skip</button>
```

- [ ] **Step 4: Run tests to verify pass**

Run: `cd /home/agent/projects/metaforge/web && npx vitest run src/components/mf-grade-sensecheck.test.ts`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add web/src/components/mf-grade-sensecheck.ts web/src/components/mf-grade-sensecheck.test.ts
git commit -m "feat(grading): sense-checker Skip button (advance without a verdict)"
```

---

## Task 8: Rename the committed chain files to chain-topics_*

**Files:** data only (committed `sonnet_chains_provisional_*` chain files on this branch).

- [ ] **Step 1: git mv the files**

```bash
cd /home/agent/projects/metaforge
git mv data-pipeline/grading/sonnet_chains_provisional_r1.jsonl          data-pipeline/grading/chain-topics_spike_r1.jsonl
git mv data-pipeline/grading/sonnet_chains_provisional_r2.jsonl          data-pipeline/grading/chain-topics_spike_r2.jsonl
git mv data-pipeline/grading/sonnet_chains_provisional_r2_handpicked.jsonl data-pipeline/grading/chain-topics_curated.jsonl
```

- [ ] **Step 2: Run the FULL sidecar suite (cohort globs match the new names; legacy globs now match nothing — both fine)**

Run: `cd /home/agent/projects/metaforge/data-pipeline && .venv/bin/python -m pytest grading_sidecar/tests/ -q`
Expected: PASS (test fixtures still write their own legacy-named files into tmp dirs, matched by the legacy globs; the renamed real files are matched by the new globs).

- [ ] **Step 3: Commit**

```bash
git add -- data-pipeline/grading/chain-topics_spike_r1.jsonl data-pipeline/grading/chain-topics_spike_r2.jsonl data-pipeline/grading/chain-topics_curated.jsonl data-pipeline/grading/sonnet_chains_provisional_r1.jsonl data-pipeline/grading/sonnet_chains_provisional_r2.jsonl data-pipeline/grading/sonnet_chains_provisional_r2_handpicked.jsonl
git commit -m "data(grading): rename chain cohorts to chain-topics_* (spike/curated)"
```

(The `git add` lists both new and old paths so the rename is staged exactly; no `-A`.)

- [ ] **Step 4: Full regression — web + sidecar**

Run: `cd /home/agent/projects/metaforge/web && npx vitest run`
Run: `cd /home/agent/projects/metaforge/data-pipeline && .venv/bin/python -m pytest grading_sidecar/tests/ -q`
Expected: web 403+ pass, sidecar 170+ pass.

---

## Task 9 (OPS — cutover runbook, operator's single sudo)

Not TDD — the deploy-topology change. The operator runs this once. Build everything above first; the controller stages what's non-privileged and hands the operator the privileged steps.

**Create the data worktree (data-only branch) — non-privileged, controller can stage:**
```bash
cd /home/agent/projects/metaforge
# data-only branch seeded from the current grading-live data state
git worktree add -b grading-data .worktrees/grading-data grading-live
mkdir -p .worktrees/grading-data/data-pipeline/grading/stock
# bring stock (rescued at a23b0107 on grading/ux-tag-notes-signal) into the stock/ subdir, renamed
git show a23b0107:data-pipeline/grading/sonnet_chains_provisional_r3_phaseb.jsonl \
  > .worktrees/grading-data/data-pipeline/grading/stock/chain-topics_stock.jsonl
# rename curated/spike in the data worktree to match the new globs
cd .worktrees/grading-data/data-pipeline/grading
[ -f sonnet_chains_provisional_r1.jsonl ]          && git mv sonnet_chains_provisional_r1.jsonl chain-topics_spike_r1.jsonl
[ -f sonnet_chains_provisional_r2.jsonl ]          && git mv sonnet_chains_provisional_r2.jsonl chain-topics_spike_r2.jsonl
[ -f sonnet_chains_provisional_r2_handpicked.jsonl ] && git mv sonnet_chains_provisional_r2_handpicked.jsonl chain-topics_curated.jsonl
cd /home/agent/projects/metaforge && git -C .worktrees/grading-data add -A && git -C .worktrees/grading-data commit -m "data(grading): seed data worktree (cohorts + stock/)"
```

**Point the code worktree at the round-1 code (clean FF) — non-privileged:**
```bash
git worktree add -b grading-code-stage /tmp/gc-stage grading-live 2>&1 | tail -1 || true
git -C /tmp/gc-stage cherry-pick grading/sense-check-mode..grading/reconciliation-round1   # round-1 code on top of the deployed line
# (verify clean; then the live FF below)
```
> If the deployed `grading-live` already carries the sense-check code (from the held sense-check cutover staging), cherry-pick only `grading/reconciliation-round1`'s own commits instead. The controller verifies the exact range against `.worktrees/next` HEAD before handing over.

**Edit the systemd unit** `deploy/grading/metaforge-grading.service` to add the data env + RW path:
```ini
Environment=GRADING_DATA_DIR=/home/agent/projects/metaforge/.worktrees/grading-data/data-pipeline/grading
Environment=GRADING_DATA_GIT_ROOT=/home/agent/projects/metaforge/.worktrees/grading-data
ReadWritePaths=/home/agent/projects/metaforge/.worktrees/grading-data
```
(Keep the existing `PYTHONPATH=.../.worktrees/next/data-pipeline/` — code still runs from the code worktree.)

**Regenerate precomputes against the data worktree, build the SPA — non-privileged:**
```bash
GRADING_DATA_DIR=.../.worktrees/grading-data/data-pipeline/grading \
  .worktrees/next/data-pipeline/.venv/bin/python .worktrees/next/data-pipeline/scripts/build_sense_candidates.py -o .worktrees/grading-data/data-pipeline/grading/sense_candidates_provisional.jsonl
# (and export_chain_glosses.py the same way, -o into the data worktree)
(cd .worktrees/next/web && npm run build)
```

**[sudo] operator's single cutover:**
```bash
sudo systemctl stop metaforge-grading                     # (if running)
git -C /home/agent/projects/metaforge/.worktrees/next merge --ff-only grading-code-stage   # code worktree → round-1 code
sudo /home/agent/projects/metaforge/deploy/grading/deploy.sh                                 # installs unit (with data env), restart, healthz smoke, PYTHONPATH verify
curl -fsS https://metaforge-next.julianit.me/api/grading/healthz
```

**Verify:** hard-refresh metaforge-next → Grade mode → Sense-check → flagged stock items now show context; Skip advances; walk/topic still show only spike+curated (no stock clutter).

**Rollback:** revert the unit's three Environment/ReadWritePaths lines, `git -C .worktrees/next reset --hard <pre-cutover-sha>`, `npm run build`, `sudo systemctl restart metaforge-grading`.

---

## Self-review

**Spec coverage:** ChainStore + per-reader cohorts (T1–T4) ✓; stock-by-location separation (T1 stock/ glob, T3 exclusion test, T4 inclusion test) ✓; precompute generators (T5) ✓; code/data env split + autocommit retarget (T1, T6) ✓; skip button (T7) ✓; file rename (T8) ✓; cutover (T9) ✓. walk/regrade need no change (default cohorts) — verified by their existing suites staying green.

**Placeholder scan:** none — every code step has concrete code/commands.

**Type/name consistency:** `CHAIN_COHORTS` / `GRADING_COHORTS` / `SENSECHECK_COHORTS` used identically across paths/chain_store/routes; `cohort_files` + `load_chains(cohorts)` signatures consistent T2→T3→T4; `GRADING_DATA_DIR` / `GRADING_DATA_GIT_ROOT` consistent T1→T6→T9; `autocommit_target()` defined T6 and used in lifespan.

**Note:** legacy `sonnet_chains_provisional_*` globs are intentionally retained in `CHAIN_COHORTS` through this round so tests + any un-migrated data keep loading; drop them in a trivial follow-up once all data is on the `chain-topics_*` scheme.
