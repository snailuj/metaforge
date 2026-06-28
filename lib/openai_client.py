"""Provider-agnostic OpenAI-compatible chat client.

Mirrors the public shape of `claude_client` (`prompt_text` / `prompt_json`) so it
drops straight into the generation runner's injected LLM functions. Targets any
OpenAI-compatible `/chat/completions` endpoint — OpenRouter, DeepInfra, Together,
Z.AI/GLM, or a local vLLM/ollama server — selected by `base_url` + `api_key`.

The HTTP transport is injectable (`_post`) so it is unit-testable offline; the
default transport is stdlib urllib (no extra dependency).
"""
from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.request


class OpenAIClientError(Exception):
    """Base error for the OpenAI-compatible client."""


class RateLimitError(OpenAIClientError):
    """Transient throttling (HTTP 429 / 5xx) — retried with backoff."""


class ParseError(OpenAIClientError):
    """Model returned content that is not the expected JSON — retried."""


_FENCE = re.compile(r"^\s*```(?:json)?\s*|\s*```\s*$", re.IGNORECASE)


def _strip_fences(text: str) -> str:
    """Remove a leading ```json / ``` fence and trailing ``` if present."""
    text = _FENCE.sub("", text.strip())
    return _FENCE.sub("", text).strip()


def _http_post(url: str, body: dict, api_key: str, timeout: float) -> dict:
    """Default transport: POST JSON, return parsed JSON. 429/5xx -> RateLimitError."""
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST")
    req.add_header("Content-Type", "application/json")
    if api_key:
        req.add_header("Authorization", f"Bearer {api_key}")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        if exc.code == 429 or 500 <= exc.code < 600:
            raise RateLimitError(f"HTTP {exc.code}: {exc.reason}") from exc
        detail = ""
        try:
            detail = exc.read().decode("utf-8", "replace")[:300]
        except Exception:  # noqa: BLE001 — best-effort diagnostic only
            pass
        raise OpenAIClientError(f"HTTP {exc.code}: {exc.reason}; {detail}") from exc
    except urllib.error.URLError as exc:
        raise RateLimitError(f"network error: {exc.reason}") from exc


def _extract_content(resp: dict) -> str:
    try:
        return resp["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise OpenAIClientError(f"unexpected response shape: {resp!r}") from exc


def _with_retries(fn, max_retries, sleep, retry_on):
    last = None
    for i in range(max_retries):
        try:
            return fn()
        except retry_on as exc:
            last = exc
            if i < max_retries - 1:
                sleep(min(2 ** i, 30))
    raise last


def _resolve(base_url, api_key):
    base_url = base_url or os.environ.get("OPENAI_BASE_URL")
    api_key = api_key or os.environ.get("OPENAI_API_KEY")
    if not base_url:
        raise OpenAIClientError("no base_url (set OPENAI_BASE_URL or pass base_url=)")
    return base_url.rstrip("/"), api_key


def _call_once(prompt, model, base_url, api_key, temperature, timeout, post, reasoning=None):
    body = {"model": model, "messages": [{"role": "user", "content": prompt}]}
    if temperature is not None:
        body["temperature"] = temperature
    if reasoning is not None:
        # OpenRouter's unified reasoning control, e.g. {"enabled": False} to run a
        # reasoning model in fast mode (no hidden CoT) — halves latency + output cost.
        body["reasoning"] = reasoning
    resp = post(f"{base_url}/chat/completions", body, api_key, timeout)
    return _extract_content(resp)


def prompt_text(prompt, *, model, base_url=None, api_key=None, max_retries=5,
                temperature=None, timeout=120, verbose=False, reasoning=None,
                _post=None, _sleep=None):
    """Return the assistant message text; retries transient throttling."""
    base_url, api_key = _resolve(base_url, api_key)
    post = _post or _http_post
    sleep = _sleep or time.sleep
    if verbose:
        print(f"[openai_client] {model} <- {prompt[:200]}")
    return _with_retries(
        lambda: _call_once(prompt, model, base_url, api_key, temperature, timeout, post, reasoning),
        max_retries, sleep, retry_on=(RateLimitError,),
    )


def prompt_json(prompt, *, model, base_url=None, api_key=None, max_retries=5,
                temperature=None, timeout=120, verbose=False, reasoning=None,
                _post=None, _sleep=None):
    """Return parsed JSON (object or array); retries throttling AND unparseable output."""
    base_url, api_key = _resolve(base_url, api_key)
    post = _post or _http_post
    sleep = _sleep or time.sleep

    def attempt():
        text = _call_once(prompt, model, base_url, api_key, temperature, timeout, post, reasoning)
        try:
            return json.loads(_strip_fences(text))
        except (json.JSONDecodeError, TypeError) as exc:
            raise ParseError(f"non-JSON content: {str(text)[:200]!r}") from exc

    if verbose:
        print(f"[openai_client] {model} <- {prompt[:200]}")
    return _with_retries(attempt, max_retries, sleep, retry_on=(RateLimitError, ParseError))
