# Claude Client Abstraction Layer

**Date:** 2026-02-14
**Status:** Approved
**Scope:** Reusable module for all Claude CLI interactions across Metaforge

## Problem

Four call sites (`enrich_properties`, `prompt_templates.generate_tweak`, `prompt_templates.improve_prompt`, `generate_evolution_report._llm_prose`) each duplicate the same pattern:

1. Call `invoke_claude()` via subprocess
2. Parse JSON event array from stdout
3. Find the result event, check for errors
4. Strip markdown fences
5. Optionally parse the result text as JSON

Each site has different levels of robustness — the enrichment path has full guards and retries, while `generate_tweak` was crashing on missing `result` fields. ~60-70 lines of duplicated parsing and error handling across the 4 callers.

## Design

### Single module: `lib/claude_client.py`

One file, layered internally. FP style (no classes). CLI-only transport (no API SDK).

### Public API

```python
def prompt_text(
    prompt: str,
    model: str = "sonnet",
    max_retries: int = 5,
    verbose: bool = False,
) -> str:
    """Send a prompt, get text back."""

def prompt_json(
    prompt: str,
    model: str = "sonnet",
    expect: type = list,       # list or dict — validates shape
    max_retries: int = 5,
    verbose: bool = False,
) -> list | dict:
    """Send a prompt, get parsed JSON back."""

def prompt_batch(
    items: list[dict],
    template: str,              # must contain {batch_items}
    batch_size: int = 20,
    model: str = "sonnet",
    max_retries: int = 5,       # per-batch retries
    verbose: bool = False,
    render_fn: Callable | None = None,  # custom item->text renderer
    on_batch: Callable[[int, int, list[dict]], None] | None = None,  # progress callback
) -> list[dict]:
    """Chunk items, render into template, call per-batch, merge results."""
```

`prompt_batch` renders each batch into the template, calls `prompt_json(expect=list)`, and concatenates results. `render_fn` controls how items become text (default: `ID: {id}\nWord: {word}\nDefinition: {defn}` format). `on_batch(batch_index, total_batches, batch_results)` fires after each successful batch for progress reporting.

### Error Hierarchy

```python
class ClaudeError(Exception):
    """Base for all Claude CLI errors."""

class RateLimitError(ClaudeError):
    """Usage/rate limit exhausted. Caller may want to wait and retry."""

class EmptyResponseError(ClaudeError):
    """CLI returned empty stdout or missing result field."""

class ParseError(ClaudeError):
    """Response text couldn't be parsed as expected format."""
```

Replaces the current grab-bag of `RuntimeError`, `ValueError`, `KeyError`. `UsageExhaustedError` from `enrich_properties` becomes `RateLimitError`.

### Internal Layers

```
+-------------------------------------+
|  prompt_text / prompt_json          |  Public API
|  prompt_batch                       |
+-------------------------------------+
|  _invoke_with_retries(prompt, ...)  |  Retry loop + rate-limit polling
+-------------------------------------+
|  _invoke(prompt, model, verbose)    |  subprocess.run, logging
+-------------------------------------+
|  _parse_events(stdout, returncode,  |  JSON event parsing, error
|                stderr)              |  detection, result extraction
+-------------------------------------+
|  _strip_fences(text)                |  Remove ```json / ```markdown
+-------------------------------------+
```

**`_invoke`** — wraps `subprocess.run` with `claude -p --output-format json --model X --max-turns 1 --no-session-persistence` flags. Returns `CompletedProcess`. Handles verbose logging (prompt preview, last 2000 chars of stdout, stderr).

**`_parse_events`** — takes raw stdout/stderr/returncode. Validates non-empty, parses JSON event array, finds result event, detects rate-limit indicators, raises typed errors. Returns the result text string.

**`_strip_fences`** — regex strip of ```json, ```markdown, trailing ``` fences.

**`_invoke_with_retries`** — orchestrates `_invoke -> _parse_events -> _strip_fences` in a retry loop. Catches `EmptyResponseError` and `ParseError` for retry. On `RateLimitError`, polls with backoff until usage renews. Returns clean text after max attempts or raises.

### Logging and Output

Uses Python's `logging` module. Debug-level for verbose output (prompt previews, raw stdout). Warning-level for retries and parse failures. No file I/O or log routing inside the module — callers/environment configure handlers.

Progress reporting (e.g. "Batch 54/74...") stays in callers via the `on_batch` callback, not in the module.

## Migration

| Caller | Before | After |
|--------|--------|-------|
| `enrich_properties._extract_batch_inner` | `invoke_claude` + `parse_response` + tenacity retry (~40 lines) | `prompt_batch()` |
| `prompt_templates.generate_tweak` | `invoke_claude` + manual JSON parse + guards | `prompt_json(expect=dict)` |
| `prompt_templates.improve_prompt` | `invoke_claude` + manual text extract + guards | `prompt_text()` |
| `generate_evolution_report._llm_prose` | `invoke_claude` + manual text extract (no guards) | `prompt_text()` |

### Deleted from existing modules

- `enrich_properties.invoke_claude` — replaced entirely
- `enrich_properties.parse_response` — absorbed into `_parse_events`
- `enrich_properties.UsageExhaustedError` — becomes `RateLimitError`
- `enrich_properties._retry_unless_usage_exhausted` — absorbed into `_invoke_with_retries`
- All duplicated fence-stripping and event-parsing across 4 files
- ~60-70 lines of duplicated parsing and error handling

### Stays in callers

- Template rendering for `generate_tweak` (the `_TWEAK_META_PROMPT.format(...)` logic)
- Fixture vocabulary guard in `generate_tweak`
- Batch progress printing via `on_batch` callback
- Domain-specific validation (e.g. checking for `{batch_items}` in improved prompts)

### Test impact

- Existing tests mock `invoke_claude` — they swap to mocking `prompt_text`/`prompt_json`/`prompt_batch`
- New unit tests for `lib/claude_client.py` covering each internal layer
- Existing caller tests mostly unchanged, just swap mock target
