"""Reusable Claude CLI client for Metaforge.

Provides prompt_text, prompt_json, and prompt_batch for interacting
with the Claude CLI, with built-in retries and error handling.
"""
import json
import logging
import re
import subprocess

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
    )
    if verbose:
        log.debug("claude_client raw stdout (last 2000 chars): %s",
                  proc.stdout[-2000:] if proc.stdout else "<empty>")
        if proc.stderr:
            log.debug("claude_client stderr: %s", proc.stderr[:500])
    return _parse_events(proc.stdout, proc.returncode, proc.stderr)
