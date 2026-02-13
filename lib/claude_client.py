"""Reusable Claude CLI client for Metaforge.

Provides prompt_text, prompt_json, and prompt_batch for interacting
with the Claude CLI, with built-in retries and error handling.
"""


class ClaudeError(Exception):
    """Base error for Claude CLI operations."""


class RateLimitError(ClaudeError):
    """Usage/rate limit exhausted."""


class EmptyResponseError(ClaudeError):
    """Empty stdout or missing result field."""


class ParseError(ClaudeError):
    """Cannot parse the LLM response."""
