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
    """Remove markdown code fences from LLM output."""
    text = re.sub(r'^```(?:json|markdown)?\n', '', text)
    text = re.sub(r'\n```$', '', text)
    return text


_RATE_LIMIT_INDICATORS = ("rate limit", "usage limit", "quota", "overloaded", "429")


def _parse_events(stdout: str, returncode: int, stderr: str) -> str:
    """Parse Claude CLI JSON event output and return the result text."""
    if returncode != 0:
        raise ClaudeError(f"claude CLI failed (exit {returncode}): {stderr}")
    if not stdout or not stdout.strip():
        raise EmptyResponseError("claude CLI returned empty stdout")
    try:
        events = json.loads(stdout)
    except json.JSONDecodeError as e:
        raise EmptyResponseError(f"Failed to parse claude stdout as JSON: {e}") from e
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
        ],
        input=prompt,
        capture_output=True,
        text=True,
        timeout=120,
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
        raise ParseError(f"Failed to parse JSON: {e}") from e
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
