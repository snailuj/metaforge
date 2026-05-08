---
task: T03
verdict: APPROVE
reviewer: agent
reviewed_at: 2026-05-02T13:21:00Z
scope: task-level (critical/high only)
---

# T03 Code Review — APPROVE

## Scope

Task-level review of T03 changes: `preprocess_munch.py`, `test_preprocess_munch.py`, and the two committed JSONL fixtures. Focused on critical/high-severity issues only — bugs causing crashes/data loss, security vulnerabilities, missing boundary error handling, and broken contracts. Style/cosmetic findings deferred to slice-level review.

## Critical / High Findings

**None.**

## Verification

- `pytest data-pipeline/scripts/test_preprocess_munch.py -q` → 8/8 passed (0.06s)
- File-system boundary handled: `preprocess()` raises `FileNotFoundError` with actionable remediation message if either source CSV is missing.
- I/O encoding is explicit (`utf-8`), `newline=""` is correctly passed to `csv.DictReader` (avoids platform line-ending corruption).
- Idempotent: `write_jsonl` opens output paths with `"w"` and recreates the parent directory each run.
- `(row.get("human_ans") or "").split()` correctly tolerates missing/None values without crashing.
- `extract_target()` returns `None` when bold markers absent; downstream consumers receive an explicit `null` rather than a malformed string — acceptable contract.
- Inapt label dispatch reads `s1_label` / `s2_label` (not column position) and logs a warning + skips on unexpected labels — matches the documented MUNCH quirk and is exercised by `test_emit_inapt_skips_rows_with_unexpected_label` and `test_emit_inapt_handles_inapt_in_s1_column`.
- No secrets, no SQL, no network I/O, no shell — narrow attack surface.

## Notes (non-blocking, deferred to slice review)

- `load_generation` / `load_judgement` are duplicate function bodies — small DRY tidy possible at slice level.
- Redundant `paraphrase.strip()` after `split()` is harmless.
- `caplog` fixture is captured but unused in `test_emit_inapt_skips_rows_with_unexpected_label`.

These are cosmetic and do not block the task.

## Verdict

**APPROVE** — proceed to task completion.
