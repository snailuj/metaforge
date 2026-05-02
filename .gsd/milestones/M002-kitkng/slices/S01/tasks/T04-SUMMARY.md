---
id: T04
parent: S01
milestone: M002-kitkng
key_files:
  - data-pipeline/scripts/test_utils.py
key_decisions:
  - Asserted byte-identical equality between the float64-tuple and float32-numpy struct.pack paths — `struct.pack` with the 'f' format performs the same float64→float32 downcast that numpy.astype(float32) does, so any divergence would be a real bug, not a tolerance issue. The redundant `assert_allclose(rtol=1e-7)` is kept as defence-in-depth in case a future Python/numpy release changes downcast rounding semantics.
  - Resolved the gate-1 failure by provisioning the worktree environment (.venv + populated lexicon_v2.db copied from the canonical worktree) rather than skipping the DB-dependent tests — preserves the slice plan's '24 test files pass' bar instead of silently narrowing it.
duration: 
verification_result: passed
completed_at: 2026-05-02T07:38:10.533Z
blocker_discovered: false
---

# T04: test: add float32 precision regression test confirming numpy/tuple struct.pack parity

**test: add float32 precision regression test confirming numpy/tuple struct.pack parity**

## What Happened

Added `test_float32_precision_matches_tuple_pack` to `data-pipeline/scripts/test_utils.py`. The test seeds a deterministic float64 vector with `np.random.default_rng(42)`, packs it via the legacy `tuple(float, ...)` path and via the new `FastTextVectors` numpy float32 row, and asserts the two `struct.pack(f'{EMBEDDING_DIM}f', *...)` blobs are byte-identical. It also unpacks both blobs and re-checks via `np.testing.assert_allclose(rtol=1e-7)` to guard against silent precision drift that could shift downstream similarity thresholds.

The first verification gate (auto-fix attempt 1) failed because the worktree was missing `.venv` (created with `python3 -m venv .venv` and `pip install -r data-pipeline/requirements.txt`) and the worktree's `data-pipeline/output/lexicon_v2.db` was a 0-byte placeholder so 28 DB-dependent tests in `test_validation.py`, `test_import_familiarity.py`, `test_import_oewn.py`, `test_import_syntagnet.py`, and `test_import_verbnet.py` failed to find tables. Restored the populated DB by copying from the canonical worktree at `/home/agent/projects/metaforge/data-pipeline/output/lexicon_v2.db` (the project convention — see worktree memory note). With venv and DB in place, the full slice-level suite runs clean: **388 passed, 0 failed in 48s** across all 24 test files.

Slice S01 verification is now complete: peak FastText memory dropped from ~11 GB to ~1.2 GB (T01), all consumers migrated to `FastTextVectors` + `numpy.tobytes()` (T02–T03), and float32 packing parity is now under regression test (T04).

## Verification

- Targeted test: `cd data-pipeline && ../.venv/bin/python -m pytest scripts/test_utils.py::test_float32_precision_matches_tuple_pack -v` → 1 passed in 0.24s.
- Slice-level: `cd data-pipeline && ../.venv/bin/python -m pytest scripts/ -v --tb=short` → **388 passed in 48.08s** (all 24 test files green, including the previously-failing predict_concreteness suite).
- Byte-equality assertion holds: tuple-of-Python-float and numpy-float32 paths produce identical `struct.pack` output.

## Verification Evidence

| # | Command | Exit Code | Verdict | Duration |
|---|---------|-----------|---------|----------|
| 1 | `cd data-pipeline && ../.venv/bin/python -m pytest scripts/test_utils.py::test_float32_precision_matches_tuple_pack -v` | 0 | pass | 240ms |
| 2 | `cd data-pipeline && ../.venv/bin/python -m pytest scripts/test_predict_concreteness.py -v` | 0 | pass | 37460ms |
| 3 | `cd data-pipeline && ../.venv/bin/python -m pytest scripts/ -v --tb=short` | 0 | pass | 48080ms |

## Deviations

Slice plan called for a single-file change to `test_utils.py`. That held. The only off-plan work was environment setup (creating `.venv`, restoring `data-pipeline/output/lexicon_v2.db` from the canonical worktree) needed to run the slice-level verification command at all — these are local environment fixes for this worktree, not changes to the shipped code.

## Known Issues

The worktree's `data-pipeline/output/lexicon_v2.db` was 0 bytes on entry; restored it for verification, but the restore is local-only (gitignored). Future executors entering a fresh worktree will need to run `data-pipeline/scripts/restore_db.sh` or copy from a sibling worktree before the validation/import_* test files will pass — this is pre-existing project setup behaviour, documented in `data-pipeline/CLAUDE.md`.

## Files Created/Modified

- `data-pipeline/scripts/test_utils.py`
