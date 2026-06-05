"""Reusable Claude CLI client for Metaforge.

Provides prompt_text, prompt_json, and prompt_batch for interacting
with the Claude CLI, with built-in retries and error handling.
"""
import datetime
import json
import logging
import os
import re
import subprocess
import time
import uuid
from pathlib import Path

log = logging.getLogger(__name__)

# When prompt_json hits an unparseable response, the canonical ParseError
# message only carries head + tail (500 chars each). The middle is where
# most JSON-decoder errors actually land — Haiku's missing-comma /
# truncated-string failures sit at char ~20k in a ~22k response. Without
# the full payload, diagnosing means re-running and hoping for repro.
# Dumping the byte-exact raw text per failure costs ~25KB/file at worst
# and is bounded by the failure rate (≈3-4% for batch=20 haiku in the
# M02-S04 retro). Operators can prune the dump dir periodically.
PARSE_FAILURE_DUMP_DIR = Path(__file__).resolve().parent.parent / "data-pipeline" / "logs" / "parse_failures"


class ClaudeError(Exception):
    """Base error for Claude CLI operations."""


class RateLimitError(ClaudeError):
    """Usage/rate limit exhausted."""


class SessionLimitError(RateLimitError):
    """A 429 usage/session limit that resets at a known wall-clock time.

    Subclasses RateLimitError so the retry loop surfaces it IMMEDIATELY (no
    backoff/retry) — a session limit resets in hours, not seconds, so retrying
    it in-process is pure churn. Carries the parsed reset time so the caller
    can pause and schedule a single, informed resume."""

    def __init__(self, msg, *, reset_text="", reset_hour=None, reset_minute=None):
        super().__init__(msg)
        self.reset_text = reset_text
        self.reset_hour = reset_hour
        self.reset_minute = reset_minute


class SessionLimitFormatError(RateLimitError):
    """A 429 usage/session limit whose reset-time format we could NOT parse.

    Raised LOUDLY (distinct class) when the server returns a confirmed 429 but
    the reset clause is missing or in an unrecognised shape — e.g. a server-side
    message change. Surfacing this rather than silently treating it as a generic
    retryable error stops a format drift from degrading into a blind retry
    grind. Also subclasses RateLimitError so it surfaces without retry."""

    def __init__(self, msg, *, raw=""):
        super().__init__(msg)
        self.raw = raw


# Matches 'resets 7:50am (UTC)', 'resets 3pm (UTC)', 'resets 10am UTC'.
# Deliberately strict: a 24h shape ('0750') or a date-stamped format won't
# match, so a server-side wording change trips parse_reset_time → ValueError →
# SessionLimitFormatError (loud) rather than a silent mis-parse.
_RESET_TIME_RE = re.compile(r"resets\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm)\b", re.IGNORECASE)


def parse_reset_time(text):
    """Parse a Claude session-limit reset clause -> (hour_24, minute).

    'You've hit your session limit · resets 7:50am (UTC)' -> (7, 50).
    Raises ValueError when no recognised 'resets <h[:mm]><am|pm>' clause is
    present, so the caller can fail loudly on an unexpected (changed) format
    instead of guessing a reset time."""
    m = _RESET_TIME_RE.search(text or "")
    if not m:
        raise ValueError(f"no parseable 'resets <time>' clause in: {text!r}")
    hour = int(m.group(1))
    minute = int(m.group(2) or 0)
    ampm = m.group(3).lower()
    if not (1 <= hour <= 12) or not (0 <= minute <= 59):
        raise ValueError(f"reset time out of range in: {text!r}")
    if ampm == "pm" and hour != 12:
        hour += 12
    if ampm == "am" and hour == 12:
        hour = 0
    return hour, minute


def _detect_session_limit(stdout):
    """Return the result text of a 429 usage/session-limit event in `stdout`,
    or None if stdout is not a 429 limit (or isn't parseable JSON).

    The session limit arrives as a CLI result object (single dict or event
    list) carrying `api_error_status == 429`; that status is the robust,
    wording-independent signal."""
    try:
        parsed = json.loads(stdout)
    except (ValueError, TypeError):
        return None
    events = parsed if isinstance(parsed, list) else [parsed]
    for e in events:
        if not isinstance(e, dict):
            continue
        status = e.get("api_error_status")
        if status == 429 or str(status) == "429":
            return e.get("result") or ""
    return None


def _raise_if_session_limit(stdout):
    """If `stdout` encodes a 429 session/usage limit, raise SessionLimitError
    (reset parsed) or SessionLimitFormatError (reset UNPARSEABLE -> loud).

    No-op (returns None) when stdout is not a 429 limit, so callers fall through
    to their normal error handling."""
    text = _detect_session_limit(stdout)
    if text is None:
        return
    try:
        hour, minute = parse_reset_time(text)
    except ValueError as e:
        raise SessionLimitFormatError(
            "429 session/usage limit detected but reset-time format "
            f"unrecognised (possible server change): {text!r}",
            raw=text,
        ) from e
    raise SessionLimitError(
        f"429 session/usage limit; {text!r}",
        reset_text=text.strip(), reset_hour=hour, reset_minute=minute,
    )


class _StdoutDiagnosticMixin:
    """Shared typed-diagnostic __init__ for ClaudeError subclasses that
    carry stdout head/tail/total_len fields.

    Lifted from the identical 12-line bodies on EmptyResponseError and
    ParseError. Inheritance order is `(_StdoutDiagnosticMixin, ClaudeError)`
    so this __init__ wins; it calls super().__init__(msg) which lands on
    ClaudeError → Exception with the message string preserved. Kept as a
    mixin (rather than a fourth ClaudeError subclass) so the existing
    public hierarchy is unchanged — issubclass(EmptyResponseError,
    ClaudeError) continues to hold, and tests asserting that hierarchy
    don't need updating.
    """

    def __init__(
        self,
        msg: str,
        *,
        stdout_head: str = "",
        stdout_tail: str = "",
        total_len: int = 0,
    ):
        super().__init__(msg)
        self.stdout_head = stdout_head
        self.stdout_tail = stdout_tail
        self.total_len = total_len


class EmptyResponseError(_StdoutDiagnosticMixin, ClaudeError):
    """Empty stdout or missing result field.

    Carries typed diagnostic fields so structured callers don't have to
    regex-parse the message string. The message still includes a
    human-readable head/tail snapshot for logs.
    """


class ParseError(_StdoutDiagnosticMixin, ClaudeError):
    """Cannot parse the LLM response.

    Same typed-diagnostic contract as EmptyResponseError.
    """


class ClaudeTimeoutError(ClaudeError):
    """Wraps subprocess.TimeoutExpired so upstream stalls remain inside the
    ClaudeError hierarchy. enrich_properties.run_enrichment narrowed its
    batch-failure handler to `except ClaudeError` (commit c5563cf6) — if a
    raw subprocess.TimeoutExpired escapes _invoke it bypasses that handler
    and abandons every remaining batch in the run. _invoke catches the
    subprocess timeout at the source and re-raises as this subclass so the
    existing retry/checkpoint logic still works.

    Carries typed diagnostic fields (mirroring EmptyResponseError / ParseError)
    so structured callers can inspect the partial stdout/stderr that
    subprocess captured before SIGKILL. The message still embeds a
    human-readable head/tail snapshot for log triage."""

    def __init__(
        self,
        msg: str,
        *,
        timeout_seconds: int = 0,
        cmd_prefix: list | None = None,
        stdout_head: str = "",
        stdout_tail: str = "",
        stderr_head: str = "",
        stderr_tail: str = "",
        total_stdout_len: int = 0,
        total_stderr_len: int = 0,
    ):
        super().__init__(msg)
        self.timeout_seconds = timeout_seconds
        self.cmd_prefix = cmd_prefix if cmd_prefix is not None else []
        self.stdout_head = stdout_head
        self.stdout_tail = stdout_tail
        self.stderr_head = stderr_head
        self.stderr_tail = stderr_tail
        self.total_stdout_len = total_stdout_len
        self.total_stderr_len = total_stderr_len


# --- Module configuration constants ------------------------------------------

_RATE_LIMIT_INDICATORS = ("rate limit", "usage limit", "quota", "overloaded", "429")

# List-result length at or below which _strip_fences emits a WARNING.
#
# Tuned for production batch_size≈20; an operator using batch_size=2 may
# want to lower this. Threshold balances false-positives (legitimate
# 2-3 item batches) against silent-mis-success (refusal-with-example
# patterns that produce 1-3 items).
_STRIP_FENCES_SUSPICIOUS_RESULT_THRESHOLD = 3

# Dict-result key-count at or below which _strip_fences emits a WARNING.
#
# Mirrors the list-side foot-gun: a refusal-with-example like
# `Brief example: {"id": "0001", "text": "soft"}` produces a 2-key dict
# that previously slipped through (Round 2's heuristic only flagged
# EMPTY dicts). No `prompt_json(expect=dict)` callers in-tree today, but
# closing the asymmetry pre-emptively.
_STRIP_FENCES_SUSPICIOUS_DICT_THRESHOLD = 2

# _MAX_TIMEOUT_ATTEMPTS caps the loop at exactly one attempt for
# ClaudeTimeoutError — i.e. zero retries. Timeouts are expensive (each
# attempt burns up to the full per-call timeout, default 900s); bounding
# the loop at 1 attempt total caps worst-case stall at 1× the per-call
# timeout (~15 min at defaults) rather than max_retries × timeout
# (~75 min). Cheap-to-retry errors (ParseError, EmptyResponseError)
# still use the full max_retries budget. Bumping this to N would allow
# N total attempts = (N-1) retries, with worst-case wall-clock = N × timeout;
# the retry branch below would also need to switch its backoff counter
# from `attempt` (outer, mixes all error types) to `timeout_attempts`.
_MAX_TIMEOUT_ATTEMPTS = 1


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

    Residual risk on the unfenced fallback: a refusal-with-example
    pattern ("Brief example: [1,2,3]") or thinking-aloud-with-fragment
    can return a JSON-valid but content-wrong short prefix. Mitigation:
    we emit a DEBUG log every time the unfenced path wins so operators
    investigating retro can tell which extraction branch fired, and a
    WARNING when the parsed result is suspiciously short (< 3 items in a
    list, or an empty object) — operators correlating that with
    downstream "unknown ID" warnings can spot mis-extractions before
    they corrupt aggregated results. The threshold isn't perfect (a
    legit 2-item batch is possible), but downstream extract_batch
    already logs unknown-ID warnings for items it can't map, so the
    correlation pattern is reliable.
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
            parsed = json.loads(candidate)
        except (ValueError, TypeError):
            continue
        log.debug(
            "_strip_fences: unfenced extraction (no fence found); "
            "span=%d:%d; parsed_type=%s",
            start, end + 1, type(parsed).__name__,
        )
        # Suspiciously-short heuristic: short list or empty dict from an
        # unfenced prose-prefixed extraction is the silent-mis-success
        # signature (refusal-with-example, thinking-aloud-with-fragment).
        # Surface as WARNING so operators correlating logs can spot it.
        # Threshold of <= 3 items catches the spec-example refusal pattern
        # "Brief example: [1,2,3]" while still letting most legitimate
        # batches (batch_size default = 20, so even a heavily-truncated
        # response with 4 items is unlikely to be a refusal-snippet).
        # False-positive cost is a single WARNING per genuine-short batch;
        # false-negative cost is silent corruption of downstream aggregates,
        # so erring towards louder is correct.
        suspicious = (
            (isinstance(parsed, list)
             and len(parsed) <= _STRIP_FENCES_SUSPICIOUS_RESULT_THRESHOLD)
            or (isinstance(parsed, dict)
                and len(parsed) <= _STRIP_FENCES_SUSPICIOUS_DICT_THRESHOLD)
        )
        if suspicious:
            head, tail, _total = _stdout_diagnostic_fields(text)
            # Cap parsed-value repr so a borderline-large dict doesn't
            # blow up the log line; 200 chars is enough to identify the
            # contents downstream "unknown ID" warnings will correlate to.
            log.warning(
                "_strip_fences: unfenced extraction returned suspiciously "
                "short result (type=%s, n=%s); parsed_value=%s; "
                "raw_head=%r; raw_tail=%r",
                type(parsed).__name__,
                len(parsed) if hasattr(parsed, "__len__") else "?",
                repr(parsed)[:200],
                head, tail,
            )
        return candidate

    # No opener yielded a parseable span — fall through to the original
    # text and let the caller surface the parse error.
    return text


def _stdout_diagnostic(stdout: str, head: int = 300, tail: int = 300) -> str:
    """Render a short head/tail snapshot of subprocess stdout for inclusion
    in error messages. Mirrors the diagnostic pattern that prompt_json
    already uses for JSON-decode failures so the retry-loop WARNING log
    surfaces enough context to diagnose without re-running.

    Returns a string like `head=<first 300>...; tail=<last 300>` or
    `head=(empty); tail=(empty)` for empty input. Capped at ~head + tail
    for long stdouts; short stdouts (≤ head + tail bytes) are dumped in
    full so the log shows the complete response when it would already fit.
    """
    if not stdout:
        return "head=(empty); tail=(empty)"
    if len(stdout) <= head + tail:
        return f"head={stdout!r}; tail=(none, len={len(stdout)})"
    return f"head={stdout[:head]!r}; tail={stdout[-tail:]!r}"


def _decode_stream(raw) -> str:
    """Coerce a subprocess stream (str | bytes | None) into a str safely.

    subprocess.TimeoutExpired carries `stdout` / `stderr` as whatever type
    was captured — typically str when `text=True`, bytes when `text=False`,
    None when capture was disabled or the process died before any output.
    The typed-diagnostic path needs a str either way; decode bytes with
    `errors='replace'` so a non-UTF-8 byte never blocks the wrap path."""
    if raw is None:
        return ""
    if isinstance(raw, bytes):
        return raw.decode("utf-8", errors="replace")
    return raw


def _stdout_diagnostic_fields(
    stdout: str, head: int = 300, tail: int = 300,
) -> tuple[str, str, int]:
    """Structured sibling of `_stdout_diagnostic` returning the head/tail/
    total_len components as typed fields. Lets exception classes carry
    machine-readable diagnostic context alongside the human-readable
    message. Symmetric byte-cap behaviour with `_stdout_diagnostic`."""
    if not stdout:
        return ("", "", 0)
    total = len(stdout)
    if total <= head + tail:
        return (stdout, "", total)
    return (stdout[:head], stdout[-tail:], total)


def _parse_events(stdout: str, returncode: int, stderr: str) -> str:
    """Parse Claude CLI JSON event output and return the result text."""
    if returncode != 0:
        # A 429 session/usage limit arrives here as exit!=0 with the error
        # JSON on stdout. Classify it before the generic raise so the retry
        # loop surfaces it immediately instead of grinding it 5× (the limit
        # resets in hours). Unparseable reset format -> loud SessionLimitFormatError.
        _raise_if_session_limit(stdout)
        # Include stdout head/tail too — stderr alone often loses partial
        # event output (e.g. a CLI segfault after a 3-event prefix). The
        # retry-loop WARNING logs the full exception message, so this
        # diagnostic flows through to operators without re-running.
        raise ClaudeError(
            f"claude CLI failed (exit {returncode}); stderr={stderr!r}; "
            f"{_stdout_diagnostic(stdout)}"
        )
    head, tail, total = _stdout_diagnostic_fields(stdout)
    if not stdout or not stdout.strip():
        raise EmptyResponseError(
            f"claude CLI returned empty stdout; {_stdout_diagnostic(stdout)}",
            stdout_head=head, stdout_tail=tail, total_len=total,
        )
    try:
        parsed = json.loads(stdout)
    except json.JSONDecodeError as e:
        raise EmptyResponseError(
            f"Failed to parse claude stdout as JSON: {e}; "
            f"{_stdout_diagnostic(stdout)}",
            stdout_head=head, stdout_tail=tail, total_len=total,
        ) from e
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
            f"Unexpected claude stdout shape: {type(parsed).__name__}; "
            f"{_stdout_diagnostic(stdout)}",
            stdout_head=head, stdout_tail=tail, total_len=total,
        )
    result_event = next(
        (e for e in reversed(events) if e.get("type") == "result"), None
    )
    if result_event is None:
        raise EmptyResponseError(
            f"No result event in claude output; {_stdout_diagnostic(stdout)}",
            stdout_head=head, stdout_tail=tail, total_len=total,
        )
    if result_event.get("is_error"):
        # Classify a 429 session/usage limit first (zero-exit is_error variant)
        # so it surfaces immediately with its parsed reset time.
        _raise_if_session_limit(stdout)
        error_text = result_event.get("result", "")
        if any(ind in error_text.lower() for ind in _RATE_LIMIT_INDICATORS):
            raise RateLimitError(error_text)
        raise ClaudeError(error_text)
    text = result_event.get("result")
    if not text:
        raise EmptyResponseError(
            f"Result event missing 'result' field "
            f"(keys: {sorted(result_event.keys())}); "
            f"{_stdout_diagnostic(stdout)}",
            stdout_head=head, stdout_tail=tail, total_len=total,
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
    cmd = [
        "claude", "-p",
        "--output-format", "json",
        "--model", model,
        "--max-turns", "1",
        "--no-session-persistence",
        "--strict-mcp-config",
        "--mcp-config", _EMPTY_MCP,
    ]
    # Sonnet output rate is roughly 100-150 tokens/sec; a v2 enrichment
    # batch of 20 synsets emits ~1800 tokens × 20 = 36k tokens which lands
    # at 240-360s — right on the old 300s edge. 900s gives clear headroom
    # without masking a genuine hang (anything past ~10 min is wrong).
    timeout = 900
    try:
        proc = subprocess.run(
            cmd,
            input=prompt,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=env,
        )
    except subprocess.TimeoutExpired as exc:
        # subprocess.TimeoutExpired inherits from subprocess.SubprocessError,
        # NOT from ClaudeError — without this wrap it escapes the narrow
        # `except ClaudeError` in enrich_properties.run_enrichment (commit
        # c5563cf6) and abandons every remaining batch in the run.
        #
        # Capture partial stdout/stderr that subprocess populates when
        # capture_output=True and the process is killed. With text=True
        # these are str; defensive-decode in case a future caller flips
        # text=False (bytes path). Pass through head/tail typed fields so
        # structured callers can inspect without re-running.
        stdout_str = _decode_stream(exc.stdout)
        stderr_str = _decode_stream(exc.stderr)
        out_head, out_tail, out_total = _stdout_diagnostic_fields(stdout_str)
        err_head, err_tail, err_total = _stdout_diagnostic_fields(stderr_str)
        raise ClaudeTimeoutError(
            f"Claude subprocess timed out after {timeout}s "
            f"(cmd_prefix={cmd[:6]}); "
            f"stdout:{_stdout_diagnostic(stdout_str)}; "
            f"stderr:{_stdout_diagnostic(stderr_str)}",
            timeout_seconds=timeout,
            cmd_prefix=cmd[:6],
            stdout_head=out_head,
            stdout_tail=out_tail,
            stderr_head=err_head,
            stderr_tail=err_tail,
            total_stdout_len=out_total,
            total_stderr_len=err_total,
        ) from exc
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
    # Foot-gun guard: max_retries < 1 means the loop body never executes,
    # last_error stays None, and `raise last_error` raises
    # `TypeError: exceptions must derive from BaseException`. Catch the
    # bad input early with a clean ValueError so callers see what they
    # actually did wrong.
    if max_retries < 1:
        raise ValueError(
            f"max_retries must be >= 1, got {max_retries}"
        )
    last_error = None
    timeout_attempts = 0
    for attempt in range(max_retries):
        try:
            return _invoke(prompt, model=model, verbose=verbose)
        except RateLimitError:
            raise
        except ClaudeTimeoutError as e:
            # Timeout retries are expensive (up to `timeout` seconds each).
            # Cap at _MAX_TIMEOUT_ATTEMPTS regardless of max_retries so a
            # stalled batch fails fast rather than burning ~75 min worst-
            # case at the default timeout=900s × max_retries=5.
            #
            # Under the current cap of 1 we always re-raise on the first
            # timeout — no backoff/sleep path is needed. If the cap is
            # bumped to N > 1, re-add a backoff branch here that uses
            # `timeout_attempts` (not the outer `attempt`, which mixes
            # all error types) so the wait grows with timeout retries
            # specifically.
            last_error = e
            timeout_attempts += 1
            if timeout_attempts >= _MAX_TIMEOUT_ATTEMPTS:
                log.warning(
                    "Claude subprocess timeout on attempt %d/%d; not "
                    "retrying further (max_timeout_attempts=%d, each retry "
                    "burns up to the per-call timeout)",
                    attempt + 1, max_retries, _MAX_TIMEOUT_ATTEMPTS,
                )
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


def _dump_parse_failure(raw: str, *, reason: str, error: str = "") -> None:
    """Write the full failing raw response to PARSE_FAILURE_DUMP_DIR.

    Best-effort: failures to write are logged at WARNING but never raised,
    so a disk-full / permission error never escalates a parse failure into
    a different exception class that bypasses callers' `except ClaudeError`
    handlers.
    """
    try:
        PARSE_FAILURE_DUMP_DIR.mkdir(parents=True, exist_ok=True)
        ts = datetime.datetime.now().strftime("%Y%m%d-%H%M%S-%f")
        # Suffix the filename with a short random tag so two failures
        # landing in the same microsecond can't clobber each other.
        path = PARSE_FAILURE_DUMP_DIR / f"raw-{ts}-{uuid.uuid4().hex[:6]}.txt"
        path.write_text(raw, encoding="utf-8")
        log.warning(
            "parse failure dumped: %s (%d bytes, reason=%s)%s",
            path, len(raw), reason,
            f", error={error!r}" if error else "",
        )
    except Exception:
        log.exception("could not dump failing raw response (reason=%s)", reason)


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
        # Surface raw response head/tail so we can diagnose without
        # re-running. The 8k enrichment kept hitting 'Expecting value: line 1
        # column 1 (char 0)' with no visibility into what came back. Use the
        # canonical _stdout_diagnostic helper at 500/500 — JSON payloads are
        # longer than CLI events so the larger window matters.
        head, tail, total = _stdout_diagnostic_fields(raw, head=500, tail=500)
        _dump_parse_failure(raw, reason="json_decode_error", error=str(e))
        raise ParseError(
            f"Failed to parse JSON ({e}); "
            f"{_stdout_diagnostic(raw, head=500, tail=500)}",
            stdout_head=head, stdout_tail=tail, total_len=total,
        ) from e
    if expect is not None and not isinstance(result, expect):
        head, tail, total = _stdout_diagnostic_fields(raw, head=500, tail=500)
        raise ParseError(
            f"Expected {expect.__name__}, got {type(result).__name__}; "
            f"{_stdout_diagnostic(raw, head=500, tail=500)}",
            stdout_head=head, stdout_tail=tail, total_len=total,
        )
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
            head, tail, total = _stdout_diagnostic_fields(raw, head=500, tail=500)
            raise ParseError(
                f"Failed to parse batch JSON: {e}; "
                f"{_stdout_diagnostic(raw, head=500, tail=500)}",
                stdout_head=head, stdout_tail=tail, total_len=total,
            ) from e
        if not isinstance(batch_results, list):
            head, tail, total = _stdout_diagnostic_fields(raw, head=500, tail=500)
            raise ParseError(
                f"Expected list from batch, got {type(batch_results).__name__}; "
                f"{_stdout_diagnostic(raw, head=500, tail=500)}",
                stdout_head=head, stdout_tail=tail, total_len=total,
            )
        all_results.extend(batch_results)
        if on_batch:
            batch_index = i // batch_size + 1
            on_batch(batch_index, total_batches, batch_results)
    return all_results
