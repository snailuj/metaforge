"""Reusable Claude CLI client for Metaforge.

Provides prompt_text, prompt_json, and prompt_batch for interacting
with the Claude CLI, with built-in retries and error handling.
"""
import re


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
