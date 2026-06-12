"""Tests for judge_stage1 — the Stage-1 construction (linkage) judge.

All offline: every LLM seam is an injected stub prompt_fn; the claude CLI is
never invoked. Properties under test (plan §4):

  * prompt content — ordered chain rendering (head per step, original phrase
    beside it only when it differs), endpoint glosses when present, a
    STRUCTURAL rubric (bad_head / leap / merge force "bad"; padding is
    "good"), and a strict-JSON response demand;
  * few-shot fidelity — exactly k worked examples, class-balanced when the
    train pool allows, each closed with its gold verdict;
  * leakage — the item-under-test's gold verdict never appears in its own
    section; the prompt is byte-identical whatever the item's label is;
  * parse strictness — good/bad polarity (bad -> 1, the y_link convention),
    prose-wrapped JSON tolerated, everything else abstains;
  * composition — make_judge + a stubbed prompt_fn scores kappa=1 through
    judge_harness.run_axis on a synthetic corpus.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))  # sibling judge modules

import judge_harness as jh  # noqa: E402
import judge_llm  # noqa: E402
import judge_stage1 as js1  # noqa: E402


# --- fixtures -----------------------------------------------------------------

_TOPIC_GLOSS = {"pos": "n", "definition": "a vague unpleasant emotion of dread"}
_VEHICLE_GLOSS = {"pos": "n", "definition": "a moving mass of insects"}


def _steps(*pairs: tuple[str, str]) -> list[dict]:
    return [{"phrase": phrase, "head": head, "synset_id": f"s{i}"}
            for i, (phrase, head) in enumerate(pairs)]


_CHAIN = _steps(("anxiety", "anxiety"),
                ("buzzing unease", "unease"),
                ("swarm", "swarm"))


def _row(sig: str, topic_id: str, y_link: int, *, vehicle: str = "swarm",
         chain: list[dict] | None = None, topic_gloss=_TOPIC_GLOSS,
         vehicle_gloss=_VEHICLE_GLOSS) -> dict:
    """A synthetic construction ROW honouring the shared interface contract."""
    return {
        "chain_signature": sig,
        "topic": "anxiety",
        "topic_synset_id": topic_id,
        "vehicle": vehicle,
        "vehicle_synset_id": f"v-{sig}",
        "metaphor": "live",
        "linkage_effective": "bad" if y_link else "good",
        "tags": ["leap"] if y_link else [],
        "notes": "",
        "ts": "2026-06-01T00:00:00+00:00",
        "y_link": y_link,
        "chain": _CHAIN if chain is None else chain,
        "topic_gloss": topic_gloss,
        "vehicle_gloss": vehicle_gloss,
        "chain_missing": False,
    }


def _train_corpus(n_topics: int = 4, per_topic: int = 6) -> list[dict]:
    """Every topic both-class (alternating labels) so balance is achievable."""
    return [_row(f"t{t}-{i}", f"T{t}", i % 2)
            for t in range(n_topics) for i in range(per_topic)]


def _item_section(prompt: str) -> str:
    sections = prompt.split(js1.ITEM_HEADER)
    assert len(sections) == 2, "item header must appear exactly once"
    return sections[1]


# --- build_prompt: chain + gloss rendering ---------------------------------------

def test_prompt_renders_chain_heads_in_order():
    # Scope to the chain block: the endpoint lines also name topic/vehicle.
    chain_block = js1.build_prompt([], _row("a", "T0", 0)).split("Chain:")[-1]
    positions = [chain_block.index(head) for head in ("anxiety", "unease", "swarm")]
    assert positions == sorted(positions)


def test_prompt_shows_phrase_beside_head_only_when_it_differs():
    prompt = js1.build_prompt([], _row("a", "T0", 0))
    assert '"buzzing unease"' in prompt           # phrase != head -> shown beside
    assert prompt.count("from “") + prompt.count('from "') == 1  # equal steps stay bare


def test_prompt_renders_endpoint_glosses_when_present():
    prompt = js1.build_prompt([], _row("a", "T0", 0))
    assert _TOPIC_GLOSS["definition"] in prompt
    assert _VEHICLE_GLOSS["definition"] in prompt


def test_prompt_omits_gloss_when_absent_without_crashing():
    prompt = js1.build_prompt(
        [], _row("a", "T0", 0, topic_gloss=None, vehicle_gloss=None))
    assert _TOPIC_GLOSS["definition"] not in prompt
    assert "anxiety" in prompt and "swarm" in prompt


@pytest.mark.parametrize("bare_row", [
    {k: v for k, v in _row("a", "T0", 0).items() if k != "chain"},  # context-free row
    _row("a", "T0", 0, chain=[]),                                    # joined, chain empty
])
def test_prompt_degrades_gracefully_without_a_chain(bare_row):
    prompt = js1.build_prompt([], bare_row)
    assert "(chain unavailable)" in prompt


def test_prompt_contains_structural_rubric_and_strict_json_demand():
    prompt = js1.build_prompt([], _row("a", "T0", 0))
    lowered = prompt.lower()
    for marker in ("mis-extracted", "leap", "merge", "padding"):
        assert marker in lowered
    assert '{"verdict": "good"}' in prompt
    assert '{"verdict": "bad"}' in prompt
    assert "STRICT JSON" in prompt


# --- build_prompt: few-shot fidelity ----------------------------------------------

def test_prompt_contains_exactly_k_class_balanced_examples():
    train = _train_corpus()
    few = jh.select_few_shot(train, k=4, seed=3, balance_key="y_link")
    prompt = js1.build_prompt(few, _row("item", "T-held-out", 0))
    assert prompt.count("Verdict: ") == 4
    assert prompt.count("Verdict: bad") == 2
    assert prompt.count("Verdict: good") == 2


def test_prompt_zero_shot_renders_without_examples_block():
    prompt = js1.build_prompt([], _row("item", "T0", 0))
    assert "Verdict: " not in prompt
    assert js1.ITEM_HEADER in prompt


# --- build_prompt: item-verdict leakage --------------------------------------------

def test_item_prompt_is_independent_of_its_gold_label():
    few = jh.select_few_shot(_train_corpus(), k=4, seed=0, balance_key="y_link")
    as_good = js1.build_prompt(few, _row("item", "T-held-out", 0))
    as_bad = js1.build_prompt(few, _row("item", "T-held-out", 1))
    assert as_good == as_bad


def test_item_section_contains_no_verdict_line():
    few = jh.select_few_shot(_train_corpus(), k=4, seed=0, balance_key="y_link")
    prompt = js1.build_prompt(few, _row("item", "T-held-out", 1))
    assert "Verdict:" not in _item_section(prompt)
    # the item is the LAST chain shown — every worked example precedes it
    assert prompt.index(js1.ITEM_HEADER) > prompt.rindex("Verdict:")


# --- parse_verdict ----------------------------------------------------------------

def test_parse_verdict_polarity_bad_is_one():
    assert js1.parse_verdict({"verdict": "bad"}) == 1
    assert js1.parse_verdict({"verdict": "good"}) == 0


def test_parse_verdict_accepts_a_json_string():
    assert js1.parse_verdict('{"verdict": "bad"}') == 1
    assert js1.parse_verdict('{"verdict": "good"}') == 0


@pytest.mark.parametrize("raw,expected", [
    ('Sure, here is my verdict: {"verdict": "good"}', 0),
    ('```json\n{"verdict": "bad"}\n```', 1),
    ({"verdict": " BAD "}, 1),  # case/whitespace slop from the model
])
def test_parse_verdict_tolerates_prose_wrapped_json_and_label_slop(raw, expected):
    assert js1.parse_verdict(raw) == expected


@pytest.mark.parametrize("raw", [
    "no idea",
    "",
    "good",                                       # bare word: no JSON anchor -> abstain
    '{"verdict": "maybe"}',
    {"verdict": "maybe"},
    {"verdict": 1},                               # numeric label rejected: contract is strings
    {"note": "missing verdict key"},
    None,
    42,
    ["good"],
    '{"verdict": "good"} or {"verdict": "bad"}',  # instruction echo: ambiguous -> abstain
])
def test_parse_verdict_garbage_abstains(raw):
    with pytest.raises(judge_llm.JudgeAbstain):
        js1.parse_verdict(raw)


# --- make_judge wiring -------------------------------------------------------------

def test_make_judge_defaults_to_haiku_and_maps_bad_to_one(tmp_path):
    seen = []

    def stub(prompt, model):
        seen.append(model)
        return {"verdict": "bad"}

    judge = js1.make_judge(prompt_fn=stub, cache_path=tmp_path / "cache.jsonl")
    assert judge([], _row("a", "T0", 1)) == 1
    assert seen == ["haiku"]


def test_make_judge_model_parameter_passes_through(tmp_path):
    seen = []

    def stub(prompt, model):
        seen.append(model)
        return {"verdict": "good"}

    judge = js1.make_judge(model="sonnet", prompt_fn=stub,
                           cache_path=tmp_path / "cache.jsonl")
    assert judge([], _row("a", "T0", 0)) == 0
    assert seen == ["sonnet"]


# --- end-to-end through the harness -------------------------------------------------

def test_run_axis_end_to_end_with_stubbed_prompt_fn(tmp_path):
    """A deterministic prompt_fn that reads the item's vehicle out of the
    rendered prompt and echoes the encoded gold verdict must score kappa=1
    through run_axis — proving prompt, parser, judge_llm and harness compose."""
    rows = [_row(f"t{t}-{i}", f"T{t}", i % 2,
                 vehicle=f"{'badveh' if i % 2 else 'goodveh'}-t{t}-{i}")
            for t in range(5) for i in range(4)]

    def stub(prompt, model):
        tail = prompt.split(js1.ITEM_HEADER)[-1]
        vehicle = re.search(r"Vehicle: (\S+)", tail).group(1)
        return {"verdict": "bad" if vehicle.startswith("badveh") else "good"}

    judge = js1.make_judge(prompt_fn=stub, cache_path=tmp_path / "cache.jsonl")
    result = jh.run_axis(rows, judge, "y_link", k_shot=4, n_repeats=2, seed=0)
    assert result["kappa"] == pytest.approx(1.0)
    assert result["n_abstain"] == 0
    assert result["n_scored"] == len(rows) * 2
