# Curated Pipeline Integration & Targeted MRR Evaluation

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Integrate the curated vocabulary pipeline (build_vocab, snap_properties, build_antonyms) into `enrich_pipeline.py`'s `run_pipeline()`, then run a targeted MRR evaluation enriching only the ~500 synsets needed by the 274 test pairs.

**Architecture:** The curated pipeline steps are already implemented as standalone scripts. We add three function calls to `run_pipeline()` so that every enrichment run automatically builds the curated tables. Then `evaluate_mrr.py` (which calls `run_pipeline()`) will produce a DB with curated tables, and the Go API will auto-detect them and use the curated forge path.

**Tech Stack:** Python 3, SQLite, FastText embeddings, Go API server, Claude CLI (for LLM enrichment)

---

## Pre-flight

Before starting any task, ensure a working Python environment:

```bash
cd /home/msi/projects/metaforge/.worktrees/feat-curated-vocab
# Check for existing venv
ls -la .venv/bin/python 2>/dev/null || ls -la data-pipeline/.venv/bin/python 2>/dev/null

# If no venv found, create one:
python3 -m venv .venv
source .venv/bin/activate
pip install -r data-pipeline/requirements.txt 2>/dev/null || pip install numpy nltk requests

# Verify key imports work
python -c "import numpy, nltk, sqlite3; print('OK')"
```

---

### Task 1: Make the failing test pass — import curated functions into enrich_pipeline.py

**Files:**
- Modify: `data-pipeline/scripts/enrich_pipeline.py:17-30` (imports)

**Step 1: Add imports at top of enrich_pipeline.py**

After the existing `from utils import ...` line (line 30), add:

```python
from build_vocab import build_and_store
from snap_properties import snap_properties
from build_antonyms import build_antonym_table
```

**Step 2: Verify test still fails (imports alone don't fix it)**

```bash
cd /home/msi/projects/metaforge/.worktrees/feat-curated-vocab
python -m pytest data-pipeline/scripts/test_enrich_pipeline.py::test_run_pipeline_creates_curated_tables -v
```

Expected: FAIL — `run_pipeline()` still doesn't call the new functions.

---

### Task 2: Call curated pipeline steps in run_pipeline()

**Files:**
- Modify: `data-pipeline/scripts/enrich_pipeline.py:417-455` (run_pipeline function)

**Step 1: Add curated pipeline calls after existing steps**

In `run_pipeline()`, after the line `centroids = compute_synset_centroids(conn)` (inside the `try` block), add:

```python
        # --- Curated vocabulary pipeline ---
        print("  Building curated vocabulary...")
        vocab_entries = build_and_store(conn)
        print("  Snapping properties to curated vocabulary...")
        snap_stats = snap_properties(conn)
        print("  Building antonym pairs...")
        antonym_pairs = build_antonym_table(conn)
```

**Step 2: Add curated stats to the return dict**

Replace the `stats = { ... }` block with:

```python
    stats = {
        "properties_curated": props,
        "synset_links": links,
        "similarity_pairs": sim_pairs,
        "centroids": centroids,
        "vocab_entries": vocab_entries,
        "snapped_properties": sum(snap_stats.values()) - snap_stats.get("dropped", 0),
        "antonym_pairs": antonym_pairs,
    }
```

**Step 3: Run the failing test**

```bash
cd /home/msi/projects/metaforge/.worktrees/feat-curated-vocab
python -m pytest data-pipeline/scripts/test_enrich_pipeline.py::test_run_pipeline_creates_curated_tables -v
```

Expected: PASS

**Step 4: Run full test suite to check for regressions**

```bash
cd /home/msi/projects/metaforge/.worktrees/feat-curated-vocab
python -m pytest data-pipeline/scripts/test_enrich_pipeline.py -v
```

Expected: All tests PASS. Note: the existing `test_run_pipeline_end_to_end` test will now also call the curated steps. It should still pass because `build_and_store` will find zero synsets in the base schema (no `frequencies` or `lemmas` data beyond what's in enrichment) and produce an empty vocabulary — `snap_properties` and `build_antonym_table` will produce empty tables but not error.

**Step 5: Commit**

```bash
cd /home/msi/projects/metaforge/.worktrees/feat-curated-vocab
git add data-pipeline/scripts/enrich_pipeline.py
git commit -m "feat: integrate curated vocabulary pipeline into run_pipeline()

build_and_store, snap_properties, build_antonym_table now called
automatically after legacy enrichment steps. Curated tables are
always populated — Go API auto-detects and uses curated forge path."
```

---

### Task 3: Verify existing end-to-end test still passes with curated steps

**Files:**
- Read: `data-pipeline/scripts/test_enrich_pipeline.py` (test_run_pipeline_end_to_end, around line 351)

**Step 1: Run it explicitly**

```bash
cd /home/msi/projects/metaforge/.worktrees/feat-curated-vocab
python -m pytest data-pipeline/scripts/test_enrich_pipeline.py::test_run_pipeline_end_to_end -v
```

Expected: PASS — curated steps run but produce empty/minimal tables since test data lacks frequencies table rows. If it fails, investigate and fix. Do NOT skip.

---

### Task 4: Run targeted MRR evaluation — curated path

This is the payoff. We enrich ONLY the synsets needed for the 274 test pairs (~500 synsets), then run the full curated pipeline and measure MRR.

**Step 1: Run the evaluation with live enrichment**

```bash
cd /home/msi/projects/metaforge/.worktrees/feat-curated-vocab
source .venv/bin/activate

python data-pipeline/scripts/evaluate_mrr.py \
    --enrich \
    --size 700 \
    --model haiku \
    --batch-size 20 \
    --delay 1.0 \
    --threshold 0.7 \
    --limit 200 \
    --port 9091 \
    --output data-pipeline/output/eval_curated_targeted.json
```

**Important notes:**
- `--size 700` provides enough padding beyond the ~500 required synsets
- `--port 9091` avoids conflicts with any running server
- The `--enrich` mode guarantees the metaphor pair synsets are included
- `run_pipeline()` now includes curated steps, so the Go API will detect curated tables
- This will make ~35 Claude Haiku API calls (700 synsets ÷ 20 batch size)

**Step 2: Check the results**

```bash
cat data-pipeline/output/eval_curated_targeted.json | python -m json.tool | head -30
```

Look for:
- `mrr` value (the headline number)
- `enrichment_coverage` (should be near 1.0)
- `testable_pairs` count
- `valid` should be `true`

**Step 3: Save the results and commit**

```bash
cd /home/msi/projects/metaforge/.worktrees/feat-curated-vocab
git add data-pipeline/output/eval_curated_targeted.json
git commit -m "data: targeted MRR evaluation — curated pipeline, 700 synsets

Enriched ~700 synsets covering all 274 metaphor test pairs.
Full curated pipeline (vocab, snap, antonyms) active.
MRR: <INSERT_VALUE_HERE>"
```

Update the commit message with the actual MRR value from the output.

---

### Task 5: Run baseline comparison — legacy path with same enrichment

To compare fairly, we need legacy MRR on the same enrichment data.

**Step 1: Check what enrichment file was produced**

The enrichment JSON from Task 4 is saved at `data-pipeline/output/eval_enrichment.json` (this is where `evaluate_mrr.py` saves it when using `--enrich` mode).

**Step 2: Temporarily revert curated steps to get legacy-only MRR**

Rather than reverting code, we can evaluate with the pre-computed enrichment file on a fresh baseline. The curated pipeline will still run but if the Go API falls back to legacy (which it won't since curated tables exist), we need a different approach.

**Alternative: just record the curated MRR and compare to the known legacy baseline.**

The legacy MRR from sprint-zero with 700 synsets was previously measured. If you need a fresh comparison:

```bash
cd /home/msi/projects/metaforge/.worktrees/feat-curated-vocab
# Note: This comparison is informational — the curated MRR is the primary metric
echo "Legacy baseline MRR (from sprint-zero): check docs/reviews/20260214-curated-forge-mrr-investigation.md"
```

**Step 3: Document the comparison**

Create a brief note in the investigation doc or as a commit message with both numbers.

---

## Summary of expected outcomes

| Metric | Expected |
|--------|----------|
| All Python tests | PASS |
| Enrichment coverage | ~95-100% (700 synsets covers ~500 required) |
| Curated tables populated | Yes — property_vocab_curated, synset_properties_curated, property_antonyms |
| Go API path | Curated (auto-detected) |
| MRR | Unknown — this is what we're measuring! |
| API cost | ~35 Haiku calls (~$1-5) |
