"""Reusable Claude CLI client for Metaforge.

Provides prompt_text, prompt_json, and prompt_batch for interacting
with the Claude CLI, with built-in retries and error handling.
"""
import json
import logging
import os
import re
import subprocess
import time
from pathlib import Path

log = logging.getLogger(__name__)


class ClaudeError(Exception):
    """Base error for Claude CLI operations."""


class RateLimitError(ClaudeError):
    """Usage/rate limit exhausted."""


class EmptyResponseError(ClaudeError):
    """Empty stdout or missing result field."""


class ParseError(ClaudeError):
    """Cannot parse the LLM response."""


# --- Internal layers ---------------------------------------------------------

def _strip_fences(text: str) -> str:
    """Extract the fenced code body from LLM output, tolerating surround prose.

    Sonnet occasionally prefixes/suffixes its fenced JSON with explanatory
    prose even when the system prompt says 'output ONLY the JSON' — e.g.
    'Here are the properties:\\n```json\\n[...]\\n```\\nLet me know if…'.
    The earlier `^```...$`-anchored regex left the surround prose intact,
    so downstream json.loads crashed with 'Expecting value: line 1 column 1
    (char 0)' on the leading 'H'. This was the failure mode that killed
    every batch of the 8k enrichment run on 2026-05-14.

    Robust strategy: if a fenced block exists anywhere in the text,
    return just its body. Otherwise return the stripped text as-is —
    callers without prose surround keep working unchanged.
    """
    # Accept any lowercase language tag (json, markdown, javascript, text,
    # python, ...). Models occasionally emit ```javascript or ```text even
    # when the system prompt asks for JSON. Restricting to json/markdown
    # caused the fallback extractor to run, which produced corrupt bodies
    # on prose-with-stray-brace inputs.
    match = re.search(
        r'```[a-z]*\s*\n(.*?)\n```', text, re.DOTALL,
    )
    if match:
        # Preserve internal whitespace — the pre-existing whitespace test
        # asserts that "```json\n  data  \n```" → "  data  ". We only
        # strip the fence markers themselves, never trim the body.
        return match.group(1)

    # No fence found. Sonnet sometimes emits unfenced JSON wrapped in prose
    # (e.g. 'Continuing with the remaining entries:\n\n[...]' — observed
    # live on the 8k enrichment run on 2026-05-14). Walk every opener `[`
    # or `{` and do a one-pass, string-aware bracket-balance scan to find
    # its matching closer; return the first balanced span that parses as
    # JSON. A naive rfind for the closer breaks in two ways:
    #   1) Prose-with-stray-brace: 'next batch uses {placeholder} IDs:
    #      [1,2,3]' — first `{` is the stray brace whose balanced match
    #      is `{placeholder}` (invalid JSON); we must skip it and find
    #      the real `[1,2,3]` further on.
    #   2) Strings containing `]` or `}` chars — naive rfind picks the
    #      one inside the string literal, truncating the body.
    # The first opener whose balanced span json.loads-parses successfully
    # wins. Residual risk: a refusal-with-example like
    # 'Brief example: [1,2,3]' would still return [1,2,3]; mitigation is
    # downstream (caller logs unknown IDs and raw_response diagnostics).
    candidate_openers = [
        i for i, ch in enumerate(text) if ch == '[' or ch == '{'
    ]
    if not candidate_openers:
        return text  # No JSON-like content at all; let the caller decide.

    for start in candidate_openers:
        opener = text[start]
        closer = ']' if opener == '[' else '}'
        depth = 0
        in_string = False
        escape = False
        end = -1
        for i in range(start, len(text)):
            ch = text[i]
            if in_string:
                # Inside a string literal — track escape state and the
                # closing quote. Brackets/braces here are opaque to
                # balance counting.
                if escape:
                    escape = False
                elif ch == '\\':
                    escape = True
                elif ch == '"':
                    in_string = False
                continue
            if ch == '"':
                in_string = True
                continue
            if ch == opener:
                depth += 1
            elif ch == closer:
                depth -= 1
                if depth == 0:
                    end = i
                    break
        if end <= start:
            continue  # Unbalanced from this opener — try the next one.
        candidate = text[start:end + 1]
        try:
            json.loads(candidate)
        except (ValueError, TypeError):
            continue
        return candidate

    # No opener yielded a parseable span — fall through to the original
    # text and let the caller surface the parse error.
    return text


_RATE_LIMIT_INDICATORS = ("rate limit", "usage limit", "quota", "overloaded", "429")


def _parse_events(stdout: str, returncode: int, stderr: str) -> str:
    """Parse Claude CLI JSON event output and return the result text."""
    if returncode != 0:
        raise ClaudeError(f"claude CLI failed (exit {returncode}): {stderr}")
    if not stdout or not stdout.strip():
        raise EmptyResponseError("claude CLI returned empty stdout")
    try:
        parsed = json.loads(stdout)
    except json.JSONDecodeError as e:
        raise EmptyResponseError(f"Failed to parse claude stdout as JSON: {e}") from e
    # The claude CLI's --output-format=json schema has evolved across versions:
    # earlier emissions were a JSON array of events (system init, then result);
    # current emissions are a bare result object. Normalise to a list so the
    # downstream "find last result event" logic works for both shapes —
    # otherwise the dict-keys-iteration path raises 'str' has no .get attr.
    if isinstance(parsed, dict):
        events = [parsed]
    elif isinstance(parsed, list):
        events = parsed
    else:
        raise EmptyResponseError(
            f"Unexpected claude stdout shape: {type(parsed).__name__}"
        )
    result_event = next(
        (e for e in reversed(events) if e.get("type") == "result"), None
    )
    if result_event is None:
        raise EmptyResponseError("No result event in claude output")
    if result_event.get("is_error"):
        error_text = result_event.get("result", "")
        if any(ind in error_text.lower() for ind in _RATE_LIMIT_INDICATORS):
            raise RateLimitError(error_text)
        raise ClaudeError(error_text)
    text = result_event.get("result")
    if not text:
        raise EmptyResponseError(
            f"Result event missing 'result' field "
            f"(keys: {sorted(result_event.keys())})"
        )
    return _strip_fences(text.strip())


_EMPTY_MCP = str(Path(__file__).parent / "empty_mcp.json")


def _invoke(prompt: str, model: str, verbose: bool = False) -> str:
    """Call claude CLI and return the parsed result text."""
    if verbose:
        log.debug("claude_client prompt (first 500 chars): %s", prompt[:500])
    # Strip CLAUDECODE env var so `claude -p` doesn't refuse to run
    # when invoked from within a Claude Code session.
    env = {k: v for k, v in os.environ.items() if k != "CLAUDECODE"}
    proc = subprocess.run(
        [
            "claude", "-p",
            "--output-format", "json",
            "--model", model,
            "--max-turns", "1",
            "--no-session-persistence",
            "--strict-mcp-config",
            "--mcp-config", _EMPTY_MCP,
        ],
        input=prompt,
        capture_output=True,
        text=True,
        # Sonnet output rate is roughly 100-150 tokens/sec; a v2 enrichment
        # batch of 20 synsets emits ~1800 tokens × 20 = 36k tokens which lands
        # at 240-360s — right on the old 300s edge. 900s gives clear headroom
        # without masking a genuine hang (anything past ~10 min is wrong).
        timeout=900,
        env=env,
    )
    if verbose:
        log.debug("claude_client raw stdout (last 2000 chars): %s",
                  proc.stdout[-2000:] if proc.stdout else "<empty>")
        if proc.stderr:
            log.debug("claude_client stderr: %s", proc.stderr[:500])
    return _parse_events(proc.stdout, proc.returncode, proc.stderr)


def _invoke_with_retries(
    prompt: str,
    model: str,
    max_retries: int = 5,
    verbose: bool = False,
) -> str:
    """Call _invoke with exponential backoff retries.

    Retries on EmptyResponseError, ParseError, and generic ClaudeError.
    Does NOT retry on RateLimitError (surfaces immediately).
    """
    last_error = None
    for attempt in range(max_retries):
        try:
            return _invoke(prompt, model=model, verbose=verbose)
        except RateLimitError:
            raise
        except ClaudeError as e:
            last_error = e
            if attempt < max_retries - 1:
                backoff = min(4 * 2 ** attempt, 120)
                log.warning("Retry %d/%d after error: %s", attempt + 1, max_retries, e)
                time.sleep(backoff)
    raise last_error


# --- Public API --------------------------------------------------------------

def prompt_text(
    prompt: str,
    model: str = "sonnet",
    max_retries: int = 5,
    verbose: bool = False,
) -> str:
    """Send a prompt, get text back."""
    return _invoke_with_retries(prompt, model=model, max_retries=max_retries, verbose=verbose)


def prompt_json(
    prompt: str,
    model: str = "sonnet",
    expect: type = None,
    max_retries: int = 5,
    verbose: bool = False,
) -> list | dict:
    """Send a prompt, get parsed JSON back."""
    raw = _invoke_with_retries(prompt, model=model, max_retries=max_retries, verbose=verbose)
    try:
        result = json.loads(raw)
    except json.JSONDecodeError as e:
        # Include first/last 500 chars of raw so we can diagnose without
        # re-running. The 8k enrichment kept hitting 'Expecting value: line 1
        # column 1 (char 0)' with no visibility into what came back — log
        # both ends so we see whether the response was empty, prose-only,
        # or truncated mid-stream.
        head = raw[:500] if raw else "<empty>"
        tail = raw[-500:] if raw and len(raw) > 1000 else ""
        raise ParseError(
            f"Failed to parse JSON ({e}); raw_len={len(raw)}; "
            f"head={head!r}; tail={tail!r}"
        ) from e
    if expect is not None and not isinstance(result, expect):
        raise ParseError(f"Expected {expect.__name__}, got {type(result).__name__}")
    return result


def prompt_batch(
    items: list,
    template: str,
    batch_size: int = 20,
    model: str = "sonnet",
    max_retries: int = 5,
    verbose: bool = False,
    render_fn: callable = None,
    on_batch: callable = None,
) -> list:
    """Chunk items, render into template, call per-batch, merge results."""
    if "{batch_items}" not in template:
        raise ValueError("template must contain {batch_items} placeholder")
    render = render_fn or (lambda batch: "\n".join(str(i) for i in batch))
    total_batches = (len(items) + batch_size - 1) // batch_size
    all_results = []
    for i in range(0, len(items), batch_size):
        chunk = items[i:i + batch_size]
        batch_text = render(chunk)
        prompt = template.format(batch_items=batch_text)
        raw = _invoke_with_retries(prompt, model=model, max_retries=max_retries, verbose=verbose)
        try:
            batch_results = json.loads(raw)
        except json.JSONDecodeError as e:
            raise ParseError(f"Failed to parse batch JSON: {e}") from e
        if not isinstance(batch_results, list):
            raise ParseError(f"Expected list from batch, got {type(batch_results).__name__}")
        all_results.extend(batch_results)
        if on_batch:
            batch_index = i // batch_size + 1
            on_batch(batch_index, total_batches, batch_results)
    return all_results
