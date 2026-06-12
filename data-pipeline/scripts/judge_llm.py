"""LLM call layer for the judge agreement harness — cache + abstention boundary.

Wraps lib/claude_client.prompt_json behind a JudgeFn `(few_shot, item) -> 0/1`
with a content-addressed JSONL cache, so re-running a harness config costs
nothing and only NEW (model, prompt) pairs spend. claude_client is imported
LAZILY inside the default prompt_fn factory: unit tests inject a stub
prompt_fn and never import the CLI path.

Error contract (plan §3):
  * parse_verdict raises JudgeAbstain on garbage output — the harness counts
    abstentions and excludes them from κ, never crashes;
  * recoverable claude_client errors (ParseError, EmptyResponseError,
    ClaudeTimeoutError, generic ClaudeError/RateLimitError) map to
    JudgeAbstain, and are NEVER cached — a transient failure must not poison
    the cache;
  * SessionLimitError AND SessionLimitFormatError re-raise untouched so the
    run halts cleanly (both are hard 429 session limits; the format variant is
    designed LOUD — degrading it to abstention would grind one doomed CLI call
    per remaining item). The cache makes resume free.

Cache: one {"key", "model", "raw"} JSON object per line, by default at
data-pipeline/output/judge_cache.jsonl (a regenerated LLM transcript, not
source — must stay gitignored). key = sha256(model + NUL + prompt); raw is
whatever prompt_fn returned (prompt_json yields parsed JSON, so dict/list
values round-trip through the JSONL). A successful raw is appended+flushed
BEFORE parsing, so a response parse_verdict rejects re-abstains for free on
every later run instead of re-spending on known garbage.
"""
from __future__ import annotations

import hashlib
import json
import logging
import sys
from pathlib import Path

log = logging.getLogger(__name__)

DEFAULT_CACHE_PATH = (Path(__file__).resolve().parent.parent
                      / "output" / "judge_cache.jsonl")

# Hard-halt claude_client classes, matched by MRO class name (duck-typed, like
# judge_harness._is_session_limit) so this module stays importable — and the
# abstention boundary testable — without ever importing the CLI path.
_HALT_ERROR_NAMES = frozenset({"SessionLimitError", "SessionLimitFormatError"})


class JudgeAbstain(Exception):
    """The judge declines a verdict for ONE item (garbage output or a
    recoverable CLI error). The harness counts + excludes it; never fatal."""


def cache_key(model: str, prompt: str) -> str:
    """Content address for one judge call. NUL separator so (model, prompt)
    pairs cannot collide by concatenation ('a'+'bc' vs 'ab'+'c')."""
    return hashlib.sha256((model + chr(0) + prompt).encode("utf-8")).hexdigest()


def _mro_names(exc: BaseException) -> frozenset[str]:
    return frozenset(c.__name__ for c in type(exc).__mro__)


def _is_session_limit(exc: BaseException) -> bool:
    return bool(_mro_names(exc) & _HALT_ERROR_NAMES)


def _is_claude_error(exc: BaseException) -> bool:
    return "ClaudeError" in _mro_names(exc)


def _load_cache(path: Path) -> dict:
    """Read the JSONL cache into {key: raw}. Latest-wins on duplicate keys
    (append-only file: a concurrent or repeated run re-appending is harmless).
    Malformed lines are skipped with a WARNING — a torn final line from a
    crash must not invalidate the rest of the cache."""
    cache: dict = {}
    if not path.exists():
        log.debug("no judge cache at %s (cold start)", path)
        return cache
    with open(path, encoding="utf-8") as fh:
        for lineno, line in enumerate(fh, start=1):
            if not line.strip():
                continue
            try:
                rec = json.loads(line)
                cache[rec["key"]] = rec["raw"]
            except (ValueError, KeyError, TypeError) as exc:
                log.warning("skipping malformed cache line %s:%d (%s)",
                            path, lineno, exc)
    log.info("loaded %d cached judge responses from %s", len(cache), path)
    return cache


def _append_cache_line(path: Path, key: str, model: str, raw) -> None:
    """Append+flush one cache record. A non-JSON-serialisable raw (only
    possible from a custom prompt_fn) is logged and NOT cached — costing a
    re-call next run is better than crashing this one."""
    try:
        line = json.dumps({"key": key, "model": model, "raw": raw})
    except (TypeError, ValueError) as exc:
        log.warning("raw response not JSON-serialisable, not cached "
                    "(key=%s): %s", key[:12], exc)
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(line + "\n")
        fh.flush()


def _default_prompt_fn():
    """Real CLI-backed prompt_fn. claude_client is imported HERE, not at
    module top, so the offline path (stub prompt_fn) never touches it."""
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "lib"))
    from claude_client import prompt_json
    return lambda prompt, model: prompt_json(prompt, model=model)


def make_llm_judge(build_prompt, parse_verdict, model,
                   prompt_fn=None, cache_path=None):
    """JudgeFn factory: returns judge(few_shot, item) -> 0/1.

    build_prompt(few_shot, item) -> str; parse_verdict(raw) -> 0/1, raising
    JudgeAbstain on garbage. prompt_fn(prompt, model) -> raw, defaulting to
    claude_client.prompt_json. Cache file and default prompt_fn are both
    resolved lazily on the first call, so constructing a judge is free and
    import-safe offline.
    """
    path = Path(cache_path) if cache_path is not None else DEFAULT_CACHE_PATH
    cache: dict | None = None
    call_fn = prompt_fn

    def judge(few_shot, item):
        nonlocal cache, call_fn
        if call_fn is None:
            call_fn = _default_prompt_fn()
        if cache is None:
            cache = _load_cache(path)
        prompt = build_prompt(few_shot, item)
        key = cache_key(model, prompt)
        if key in cache:
            log.debug("cache hit %s (model=%s)", key[:12], model)
            return parse_verdict(cache[key])
        try:
            raw = call_fn(prompt, model)
        except Exception as exc:
            if _is_session_limit(exc):
                raise  # halt cleanly; the cache makes resume free
            if _is_claude_error(exc):
                log.warning("claude error -> abstain (model=%s, key=%s): %s",
                            model, key[:12], exc)
                raise JudgeAbstain(f"claude error: {exc}") from exc
            raise  # a programming error must surface, not become an abstention
        _append_cache_line(path, key, model, raw)
        cache[key] = raw
        return parse_verdict(raw)

    return judge
