"""Tests for judge_stage2 — the Stage-2 liveness/pairing judge (plan §5).

All offline: prompt_fn is always an injected stub via judge_llm's DI seam;
the claude CLI is never invoked.

THE load-bearing property: the unit judged is the (topic, vehicle) PAIRING —
intermediate chain steps import lazy-path noise, and tags/notes/the gold label
carry the operator's answer — so NONE of them may ever reach the prompt.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import judge_harness as jh  # noqa: E402
import judge_llm  # noqa: E402
import judge_stage2 as js2  # noqa: E402


# --- fixtures -----------------------------------------------------------------

def _gloss(definition: str, pos: str | None = "noun") -> dict:
    return {"pos": pos, "definition": definition}


def _row(sig: str, topic_id: str, y: int, **extra) -> dict:
    """A synthetic context-attached corpus ROW honouring the shared contract."""
    row = {
        "chain_signature": sig,
        "topic": f"topic-{sig}",
        "topic_synset_id": str(topic_id),
        "vehicle": f"vehicle-{sig}",
        "vehicle_synset_id": f"v-{sig}",
        "metaphor": "live" if y else "dead",
        "linkage_effective": "good",
        "tags": [],
        "notes": "",
        "ts": "2026-06-01T00:00:00+00:00",
        "chain": [],
        "topic_gloss": _gloss(f"definition of topic {sig}"),
        "vehicle_gloss": _gloss(f"definition of vehicle {sig}"),
        "chain_missing": False,
        "y_live": y,
    }
    row.update(extra)
    return row


_MARKERS = ("MARKER-PHRASE-ALPHA", "MARKER-HEAD-BRAVO", "MARKER-SYN-CHARLIE",
            "MARKER-NOTES-DELTA", "MARKER-TAG-ECHO")


def _marked(sig: str, topic_id: str, y: int) -> dict:
    """Row whose chain/notes/tags carry distinctive markers — every field a
    pairing-only prompt must NOT contain."""
    return _row(sig, topic_id, y,
                chain=[{"phrase": "MARKER-PHRASE-ALPHA",
                        "head": "MARKER-HEAD-BRAVO",
                        "synset_id": "MARKER-SYN-CHARLIE"}],
                notes="MARKER-NOTES-DELTA",
                tags=["MARKER-TAG-ECHO"])


class _SpyPromptFn:
    """Counting stub standing in for claude_client.prompt_json."""

    def __init__(self, respond=None):
        self.calls: list[tuple[str, str]] = []
        self.respond = respond or (lambda prompt: {"verdict": "live"})

    def __call__(self, prompt, model):
        self.calls.append((prompt, model))
        return self.respond(prompt)


# --- build_prompt: pairing-only (THE load-bearing test) --------------------------

def test_prompt_is_pairing_only_no_chain_steps_tags_or_notes():
    few = [_marked("fs0", "T1", 1), _marked("fs1", "T2", 0)]
    item = _marked("it0", "T0", 1)
    prompt = js2.build_prompt(few, item)
    for marker in _MARKERS:
        assert marker not in prompt
    # The endpoints + glosses ARE the unit, so they must be present.
    assert "topic-it0" in prompt and "vehicle-it0" in prompt
    assert "definition of topic it0" in prompt
    assert "definition of vehicle it0" in prompt


def test_prompt_invariant_to_item_gold_fields():
    # The judged item's own gold label (and every gold-adjacent field) must
    # not influence the prompt — otherwise the eval measures leakage, not skill.
    few = [_row("fs0", "T1", 1), _row("fs1", "T2", 0)]
    base = _row("it0", "T0", 1)
    flipped = {**base, "y_live": 0, "metaphor": "dead", "linkage_effective": "bad",
               "tags": ["strong"], "notes": "the operator's reasoning"}
    assert js2.build_prompt(few, base) == js2.build_prompt(few, flipped)


# --- build_prompt: persona + rendering --------------------------------------------

def test_persona_preamble_present():
    prompt = js2.build_prompt([], _row("it0", "T0", 1))
    assert "Forge Reader" in prompt
    assert "genre" in prompt
    assert "cross-domain" in prompt
    # The strict binary output contract is spelt out for the model.
    assert '{"verdict": "live"}' in prompt
    assert '{"verdict": "dead"}' in prompt


def test_persona_carries_operator_revision_2026_07():
    """Julian's preamble revision: wider span (surrealist, some realist
    fiction), reader engagement as the determining vector, beauty subordinate
    to momentum. The old 'never highbrow' framing is superseded."""
    prompt = js2.build_prompt([], _row("it0", "T0", 1))
    assert "surrealist" in prompt
    assert "reader engagement is the determining vector" in prompt
    assert "not at the expense of momentum" in prompt
    assert "never highbrow" not in prompt


def test_pairing_renders_topic_then_vehicle_with_glosses():
    item = _row("it0", "T0", 1, topic="grief", vehicle="anchor",
                topic_gloss=_gloss("intense sorrow"),
                vehicle_gloss=_gloss("a mooring device"))
    prompt = js2.build_prompt([], item)
    judged = prompt.split(js2.ITEM_HEADER)[1]
    assert judged.index("grief") < judged.index("anchor")
    assert "intense sorrow" in judged and "a mooring device" in judged


def test_glossless_rows_render_without_none():
    bare = _row("it0", "T0", 1, topic_gloss=None, vehicle_gloss=None)
    prompt = js2.build_prompt([], bare)
    assert "None" not in prompt
    assert "topic-it0" in prompt and "vehicle-it0" in prompt
    # A gloss dict whose parts are missing degrades the same way.
    empty = _row("it1", "T0", 1, topic_gloss={"pos": None, "definition": None},
                 vehicle_gloss=_gloss("a defined vehicle", pos=None))
    prompt = js2.build_prompt([], empty)
    assert "None" not in prompt
    assert "a defined vehicle" in prompt


def test_few_shot_examples_carry_verdicts_balanced_and_deterministic():
    train = [_row(f"s{i}", f"TR{i % 4}", i % 2) for i in range(12)]
    few = jh.select_few_shot(train, k=4, seed=3, balance_key="y_live")
    item = _row("it0", "HELD", 1)
    prompt = js2.build_prompt(few, item)
    examples = prompt.split(js2.ITEM_HEADER)[0]
    assert examples.count('{"verdict": "live"}') == 2
    assert examples.count('{"verdict": "dead"}') == 2
    redraw = jh.select_few_shot(train, k=4, seed=3, balance_key="y_live")
    assert js2.build_prompt(redraw, item) == prompt


def test_few_shot_without_y_live_fails_loudly():
    # An un-stamped row must not silently render an unlabelled example.
    unstamped = {k: v for k, v in _row("fs0", "T1", 1).items() if k != "y_live"}
    with pytest.raises(KeyError):
        js2.build_prompt([unstamped], _row("it0", "T0", 1))


# --- parse_verdict ----------------------------------------------------------------

def test_parse_verdict_polarity():
    assert js2.parse_verdict({"verdict": "live"}) == 1
    assert js2.parse_verdict({"verdict": "dead"}) == 0


def test_parse_verdict_normalises_case_and_whitespace_only():
    assert js2.parse_verdict({"verdict": " LIVE "}) == 1
    assert js2.parse_verdict({"verdict": "Dead"}) == 0


@pytest.mark.parametrize("raw", [
    {"verdict": "alive"}, {"verdict": "live or dead"}, {"verdict": 1},
    {"verdict": None}, {"verdict": ""}, {"score": 8}, {}, "live", ["live"], None,
])
def test_parse_verdict_abstains_on_everything_else(raw):
    with pytest.raises(judge_llm.JudgeAbstain):
        js2.parse_verdict(raw)


# --- make_judge wiring ------------------------------------------------------------

def test_make_judge_defaults_to_sonnet(tmp_path):
    spy = _SpyPromptFn()
    judge = js2.make_judge(prompt_fn=spy, cache_path=tmp_path / "cache.jsonl")
    assert judge([], _row("it0", "T0", 1)) == 1
    assert spy.calls[0][1] == "sonnet"


def test_make_judge_model_parameterised(tmp_path):
    # The harness runs a haiku baseline through this same seam (plan §5).
    spy = _SpyPromptFn(respond=lambda prompt: {"verdict": "dead"})
    judge = js2.make_judge(model="haiku", prompt_fn=spy,
                           cache_path=tmp_path / "cache.jsonl")
    assert judge([], _row("it0", "T0", 1)) == 0
    assert spy.calls[0][1] == "haiku"


# --- end-to-end through judge_harness.run_axis --------------------------------------

def _e2e_corpus() -> list[dict]:
    """Every topic group both-class; the topic WORD encodes the gold label
    (glow=live, dull=dead) so a prompt-reading stub can play a perfect judge.
    Chains carry markers so the e2e run also proves pairing-only prompts."""
    return [
        _row(f"e{t}-{i}", f"T{t}", i % 2,
             topic=("glow" if i % 2 else "dull") + f"-{t}-{i}",
             vehicle=f"vessel-{t}-{i}",
             chain=[{"phrase": f"MARKER-STEP-{t}-{i}", "head": "h", "synset_id": "s"}])
        for t in range(5)
        for i in range(4)
    ]


def _gold_echo(prompt: str) -> dict:
    judged = prompt.split(js2.ITEM_HEADER)[1]
    return {"verdict": "live"} if "glow" in judged else {"verdict": "dead"}


def test_end_to_end_run_axis_with_stubbed_prompt_fn(tmp_path):
    rows = _e2e_corpus()
    spy = _SpyPromptFn(respond=_gold_echo)
    judge = js2.make_judge(prompt_fn=spy, cache_path=tmp_path / "cache.jsonl")
    result = jh.run_axis(rows, judge, "y_live", k_shot=4, n_repeats=2, seed=0)
    assert result["kappa"] == pytest.approx(1.0)
    assert result["n_abstain"] == 0
    assert result["n_scored"] == len(rows) * 2
    assert all(model == "sonnet" for _, model in spy.calls)
    assert all("MARKER-STEP" not in prompt for prompt, _ in spy.calls)
    # Idempotent re-run: every prompt is a cache hit, zero new spend.
    n_calls = len(spy.calls)
    rerun = jh.run_axis(rows, judge, "y_live", k_shot=4, n_repeats=2, seed=0)
    assert rerun["kappa"] == pytest.approx(1.0)
    assert len(spy.calls) == n_calls


def test_end_to_end_abstention_counted_not_crashed(tmp_path):
    rows = _e2e_corpus()
    rows.append(_row("amb", "T0", 1, topic="glow-ambiguous", vehicle="vessel-amb"))

    def respond(prompt):
        judged = prompt.split(js2.ITEM_HEADER)[1]
        if "ambiguous" in judged:
            return {"verdict": "cannot say"}  # garbage -> JudgeAbstain in parse
        return _gold_echo(prompt)

    judge = js2.make_judge(prompt_fn=_SpyPromptFn(respond=respond),
                           cache_path=tmp_path / "cache.jsonl")
    result = jh.run_axis(rows, judge, "y_live", k_shot=4, n_repeats=2, seed=0)
    assert result["n_abstain"] == 2  # the ambiguous item, once per repeat
    assert result["n_scored"] == result["n_items"] - 2
    assert result["kappa"] == pytest.approx(1.0)  # abstentions excluded from kappa
