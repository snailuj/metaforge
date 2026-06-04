"""Tests for metaphor_live_rate — the proxy-judge + live-rate tripwire.

The judge is a CONSERVATIVE, zero-false-positive monitor (Haiku/Sonnet) used
only to detect a cratering prompt mid-run — NOT the final admission gate. The
tripwire pauses generation when the rolling live-rate drops below an absolute
floor OR falls a relative fraction below an established baseline.

LLM calls are injected (prompt_fn) so these tests make no API calls.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import metaphor_live_rate as mlr


# --- a minimal chain.v1 record fixture -------------------------------------
def _record(topic="anger", vehicle="volcano", phrases=("anger", "pressure", "volcano")):
    return {
        "schema_version": "chain.v1",
        "topic": topic,
        "topic_synset_id": "1",
        "vehicle": vehicle,
        "vehicle_synset_id": "2",
        "proposer": "sonnet_v1",
        "round": 2,
        "chain": [{"phrase": p, "head": p, "synset_id": None} for p in phrases],
        "chain_signature": "0" * 64,
        "generated_at": "2026-06-04T00:00:00+00:00",
    }


# --- live_rate --------------------------------------------------------------
def test_live_rate_is_fraction_live_over_all_verdicts():
    assert mlr.live_rate(["live", "dead", "live", "irrelevant"]) == 0.5


def test_live_rate_empty_is_zero():
    assert mlr.live_rate([]) == 0.0


# --- build_judge_prompt (pure) ---------------------------------------------
def test_judge_prompt_contains_the_chain_endpoints_and_steps():
    p = mlr.build_judge_prompt(_record(phrases=("anger", "pressure", "volcano")))
    assert "anger" in p and "volcano" in p and "pressure" in p


def test_judge_prompt_asks_for_the_three_verdicts():
    p = mlr.build_judge_prompt(_record()).lower()
    assert "live" in p and "dead" in p and "irrelevant" in p


def test_judge_prompt_is_conservative_zero_false_positive():
    """When unsure the judge must NOT call live — the monitor under-calls live
    by design so a 'live' signal is trustworthy."""
    p = mlr.build_judge_prompt(_record()).lower()
    assert "unsure" in p or "uncertain" in p or "doubt" in p
    # it must instruct the model to avoid false 'live' calls
    assert "not" in p and "live" in p


# --- parse_verdict (pure, conservative) ------------------------------------
def test_parse_verdict_reads_clean_response():
    assert mlr.parse_verdict({"verdict": "live"}) == "live"
    assert mlr.parse_verdict({"verdict": "DEAD"}) == "dead"
    assert mlr.parse_verdict({"verdict": "irrelevant"}) == "irrelevant"


def test_parse_verdict_defaults_to_dead_on_garbage():
    """Conservative: an unrecognised/garbled verdict is treated as NOT live."""
    assert mlr.parse_verdict({"verdict": "maybe"}) == "dead"
    assert mlr.parse_verdict({}) == "dead"
    assert mlr.parse_verdict({"verdict": None}) == "dead"


# --- judge_chain (injected client) -----------------------------------------
def test_judge_chain_uses_injected_prompt_fn():
    calls = []

    def fake_prompt(prompt, model="haiku"):
        calls.append((prompt, model))
        return {"verdict": "live", "confidence": 0.9}

    out = mlr.judge_chain(_record(), prompt_fn=fake_prompt, model="haiku")
    assert out["verdict"] == "live"
    assert out["ok"] is True
    assert len(calls) == 1
    assert calls[0][1] == "haiku"


def test_judge_chain_on_client_error_is_not_counted():
    """An API error must NOT be counted as 'dead' — that would false-trip the
    tripwire on transient outages. ok=False so the caller skips it."""
    def boom(prompt, model="haiku"):
        raise mlr.JudgeError("api down")

    out = mlr.judge_chain(_record(), prompt_fn=boom, model="haiku")
    assert out["ok"] is False
    assert out["verdict"] is None


# --- tripwire (pure state machine) -----------------------------------------
def _feed(state, verdicts):
    for v in verdicts:
        state = mlr.record_verdict(state, v)
    return state


def test_tripwire_does_not_pause_before_min_judged():
    st = mlr.new_tripwire(window=10, min_judged=10, abs_floor=0.3, rel_drop=0.4, baseline_n=10)
    st = _feed(st, ["dead"] * 5)  # only 5 < min_judged
    assert mlr.should_pause(st) is False


def test_tripwire_pauses_below_absolute_floor():
    st = mlr.new_tripwire(window=10, min_judged=10, abs_floor=0.3, rel_drop=0.9, baseline_n=10)
    st = _feed(st, ["dead"] * 10)  # rate 0.0 < floor 0.3
    assert mlr.should_pause(st) is True


def test_tripwire_does_not_pause_when_rate_healthy():
    st = mlr.new_tripwire(window=10, min_judged=10, abs_floor=0.3, rel_drop=0.4, baseline_n=10)
    st = _feed(st, ["live"] * 7 + ["dead"] * 3)  # rate 0.7
    assert mlr.should_pause(st) is False


def test_tripwire_pauses_on_relative_drop_from_baseline():
    """Baseline frozen at 0.7 over first 10; a later window at 0.35 is a 50%
    relative drop (> rel_drop 0.4) even though it's above the absolute floor."""
    st = mlr.new_tripwire(window=10, min_judged=10, abs_floor=0.2, rel_drop=0.4, baseline_n=10)
    st = _feed(st, ["live"] * 7 + ["dead"] * 3)        # baseline window: 0.7
    assert mlr.should_pause(st) is False
    st = _feed(st, ["live"] * 3 + ["dead"] * 7)        # newest 10: rate 0.3
    assert mlr.should_pause(st) is True


def test_tripwire_window_only_considers_recent_verdicts():
    """A long-ago bad streak must not keep the tripwire latched once recent
    quality recovers (window slides)."""
    st = mlr.new_tripwire(window=5, min_judged=5, abs_floor=0.3, rel_drop=0.9, baseline_n=5)
    st = _feed(st, ["dead"] * 5)      # window all dead -> would pause
    assert mlr.should_pause(st) is True
    st = _feed(st, ["live"] * 5)      # window now all live -> recovered
    assert mlr.should_pause(st) is False
