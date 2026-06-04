"""Proxy-judge + live-rate tripwire for the continuous metaphor-edge runner.

Two roles, deliberately separated:

  * **proxy judge** — a CONSERVATIVE, zero-false-positive liveness verdict
    (live / dead / irrelevant) from a cheap model (Haiku by default). It is a
    *monitor*, NOT the final admission gate: it is tuned to under-call `live`
    so that a `live` signal is trustworthy. Sampled, not run on every chain.

  * **tripwire** — a pure sliding-window state machine over recent verdicts.
    It pauses generation when the rolling live-rate drops below an absolute
    floor OR falls a relative fraction below a baseline frozen early in the
    run. Detecting a *cratering* prompt is the whole point — a sense-mangled
    topic tail or a prompt regression shows up as a live-rate collapse.

All LLM access is injected (`prompt_fn`) so the logic is unit-tested without
spending. The default client is `claude_client.prompt_json`.
"""
from __future__ import annotations

import logging
import sys
from dataclasses import dataclass, replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "lib"))  # claude_client

log = logging.getLogger(__name__)

DEFAULT_JUDGE_MODEL = "claude-haiku-4-5-20251001"
# The judge is a sampled MONITOR — a flaky response should fail fast and be
# skipped (ok=False, not counted), never trigger the client's full 5x retry
# storm (which cost ~10 min/batch in the smoke before this cap).
JUDGE_MAX_RETRIES = 2
_VALID_VERDICTS = ("live", "dead", "irrelevant")


class JudgeError(Exception):
    """Raised by an injected judge client when the call fails."""


# ---------------------------------------------------------------------------
# Verdict arithmetic (pure)
# ---------------------------------------------------------------------------

def live_rate(verdicts: list[str]) -> float:
    """Fraction of verdicts that are `live`. Empty -> 0.0.

    Denominator is ALL non-error verdicts (live + dead + irrelevant): an
    `irrelevant` chain is a generation failure, not a free pass.
    """
    if not verdicts:
        return 0.0
    return sum(1 for v in verdicts if v == "live") / len(verdicts)


def parse_verdict(raw: dict) -> str:
    """Normalise a judge response to one of live/dead/irrelevant.

    Conservative: anything unrecognised, missing, or null collapses to `dead`
    (NOT live) so a garbled judge response can never inflate the live-rate.
    """
    if not isinstance(raw, dict):
        return "dead"
    v = raw.get("verdict")
    if not isinstance(v, str):
        return "dead"
    v = v.strip().lower()
    return v if v in _VALID_VERDICTS else "dead"


# ---------------------------------------------------------------------------
# Judge prompt (pure) + judge call (injected client)
# ---------------------------------------------------------------------------

def _render_chain(record: dict) -> str:
    steps = record.get("chain", [])
    phrases = [s.get("phrase", "") for s in steps if isinstance(s, dict)]
    return " → ".join(phrases)


def build_judge_prompt(record: dict) -> str:
    """Conservative liveness judge prompt for a single chain.v1 record.

    Structured as an imperative ONE-SHOT task (instruction + the concrete
    metaphor first, JSON-only demand last). A role-preamble opener ('You are a
    judge…') made the model treat it as setup and reply 'provide the metaphor
    pairs and I'll respond' instead of classifying the metaphor already given.
    """
    topic = record.get("topic", "")
    vehicle = record.get("vehicle", "")
    chain_str = _render_chain(record)
    return f"""Classify this ONE metaphor as exactly "live", "dead", or "irrelevant".

THE METAPHOR TO CLASSIFY:
  {topic} → {vehicle}
  via the conceptual chain: {chain_str}

Definitions:
  - "live": an apt, vivid, cross-domain metaphor a careful writer would use —
    the vehicle illuminates the topic in a fresh, non-obvious way.
  - "dead": a cliché, a near-synonym, a conventional/dead metaphor, or a pairing
    whose connection is purely literal or definitional (no cross-domain leap).
  - "irrelevant": no genuine metaphorical connection between topic and vehicle.

Be a strict, conservative judge: if you are unsure, in any doubt, or the aptness
is only weak, do NOT call it "live". Reserve "live" for metaphors you are
confident a discerning editor would keep. Under-calling live is correct;
over-calling live is a serious error.

The metaphor is given above — classify it now. Output ONLY this JSON object and
nothing else (no preamble, no request for input):
{{"verdict": "live|dead|irrelevant", "confidence": <0.0-1.0>, "reason": "<short>"}}"""


def judge_chain(record: dict, *, prompt_fn=None, model: str = DEFAULT_JUDGE_MODEL) -> dict:
    """Judge one chain. Returns {verdict, ok, confidence, reason}.

    `prompt_fn(prompt, model=...) -> dict` is injected for tests; defaults to
    claude_client.prompt_json. A client failure returns ok=False with
    verdict=None — it is NOT counted as `dead`, so transient API errors cannot
    false-trip the tripwire. Every failure is logged (never silent).
    """
    if prompt_fn is None:
        from claude_client import prompt_json  # lazy: keeps unit tests import-light
        prompt_fn = lambda p, model: prompt_json(p, model=model, max_retries=JUDGE_MAX_RETRIES)
    prompt = build_judge_prompt(record)
    try:
        raw = prompt_fn(prompt, model=model)
    except Exception as exc:  # noqa: BLE001 — a monitor must never crash the run
        log.warning("judge_chain: client error (not counted): %s", exc)
        return {"verdict": None, "ok": False, "error": str(exc)}
    verdict = parse_verdict(raw if isinstance(raw, dict) else {})
    confidence = raw.get("confidence") if isinstance(raw, dict) else None
    reason = raw.get("reason") if isinstance(raw, dict) else None
    return {"verdict": verdict, "ok": True, "confidence": confidence, "reason": reason}


# ---------------------------------------------------------------------------
# Tripwire (pure sliding-window state machine)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class TripwireState:
    window: int
    min_judged: int
    abs_floor: float
    rel_drop: float
    baseline_n: int
    recent: tuple = ()          # last `window` verdicts (most recent last)
    total_judged: int = 0
    baseline: float | None = None  # frozen once total_judged reaches baseline_n


def new_tripwire(
    *,
    window: int = 30,
    min_judged: int = 15,
    abs_floor: float = 0.08,
    rel_drop: float = 0.4,
    baseline_n: int = 15,
) -> TripwireState:
    """A fresh tripwire. Defaults are a starting point — CALIBRATE per cohort.

    window      — verdicts in the rolling window the rate is computed over.
    min_judged  — no pause decision until this many verdicts seen (avoid noise).
    abs_floor   — pause if window live-rate drops below this absolute value. The
                  judge is tuned to UNDER-call `live`, so a HEALTHY run sits at a
                  low-ish rate; the floor must sit BELOW the measured healthy
                  live-rate (default 0.08 is a near-total-collapse line, not a
                  quality bar) or the brake fails CLOSED on good output. Measure
                  the healthy rate on a vetted cohort and set this accordingly.
    rel_drop    — pause if window rate falls this fraction below the baseline.
                  This is the PRIMARY degradation brake; the absolute floor is a
                  collapse backstop.
    baseline_n  — freeze the baseline live-rate after this many verdicts. Must be
                  <= window (else the baseline is sampled over a truncated window,
                  silently mis-anchoring the relative-drop arm).

    Arming cost: the runner contributes ~judge_sample verdicts per batch, so the
    brake arms after roughly (min_judged / judge_sample) batches of generation —
    keep min_judged small enough that arming happens within an acceptable spend.
    """
    if baseline_n > window:
        raise ValueError(f"baseline_n ({baseline_n}) must be <= window ({window})")
    return TripwireState(
        window=window, min_judged=min_judged, abs_floor=abs_floor,
        rel_drop=rel_drop, baseline_n=baseline_n,
    )


def record_verdict(state: TripwireState, verdict: str) -> TripwireState:
    """Append one verdict, returning a new state (immutable). Freezes the
    baseline live-rate the moment `total_judged` reaches `baseline_n`."""
    recent = (state.recent + (verdict,))[-state.window:]
    total = state.total_judged + 1
    baseline = state.baseline
    if baseline is None and total >= state.baseline_n:
        baseline = live_rate(list(recent))
    return replace(state, recent=recent, total_judged=total, baseline=baseline)


def should_pause(state: TripwireState) -> bool:
    """True when the rolling window indicates a cratered live-rate."""
    if state.total_judged < state.min_judged:
        return False
    rate = live_rate(list(state.recent))
    if rate < state.abs_floor:
        return True
    if state.baseline is not None and rate < state.baseline * (1.0 - state.rel_drop):
        return True
    return False
