"""Tests for judge_llm — the LLM call layer of the judge agreement harness.

All offline: prompt_fn is always an injected stub; the claude CLI is never
invoked. claude_client is imported ONLY to construct its real exception
classes (import-safe: pure stdlib, no subprocess at import time).

Properties under test (plan §3):
  * content-addressed cache — a repeated (model, prompt) pair costs zero
    prompt_fn calls, and the cache survives a fresh make_llm_judge instance
    (resume after a halt is free);
  * abstention boundary — garbage output and recoverable claude_client errors
    become JudgeAbstain, never a crash, and errors never poison the cache;
  * the session-limit classes pass through untouched so a run halts cleanly.
"""
from __future__ import annotations

import hashlib
import json
import logging
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))                         # sibling judge_llm
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "lib"))   # claude_client

import claude_client  # noqa: E402
import judge_llm  # noqa: E402


# --- fixtures -----------------------------------------------------------------

_FEW_SHOT = [{"chain_signature": "sig-a"}, {"chain_signature": "sig-b"}]
_ITEM = {"chain_signature": "sig-item", "topic": "anxiety"}


def _build_prompt(few_shot, item):
    shots = ";".join(ex["chain_signature"] for ex in few_shot)
    return f"shots={shots}|item={item['chain_signature']}"


def _parse_verdict(raw):
    verdict = raw.get("verdict") if isinstance(raw, dict) else None
    if verdict not in (0, 1):
        raise judge_llm.JudgeAbstain(f"unparseable verdict: {raw!r}")
    return verdict


class _StubPromptFn:
    """Counting stub standing in for claude_client.prompt_json."""

    def __init__(self, raw=None, error=None):
        self.calls = []
        self.raw = {"verdict": 1} if raw is None else raw
        self.error = error

    def __call__(self, prompt, model):
        self.calls.append((prompt, model))
        if self.error is not None:
            raise self.error
        return self.raw


def _make(tmp_path, stub, model="haiku"):
    return judge_llm.make_llm_judge(_build_prompt, _parse_verdict, model,
                                    prompt_fn=stub,
                                    cache_path=tmp_path / "judge_cache.jsonl")


# --- happy path + cache ---------------------------------------------------------

def test_judge_calls_prompt_fn_and_returns_parsed_verdict(tmp_path):
    stub = _StubPromptFn(raw={"verdict": 1})
    judge = _make(tmp_path, stub)
    assert judge(_FEW_SHOT, _ITEM) == 1
    assert len(stub.calls) == 1
    prompt, model = stub.calls[0]
    assert "sig-item" in prompt and "sig-a" in prompt
    assert model == "haiku"


def test_second_identical_call_is_cache_hit_with_zero_new_calls(tmp_path):
    stub = _StubPromptFn(raw={"verdict": 0})
    judge = _make(tmp_path, stub)
    assert judge(_FEW_SHOT, _ITEM) == 0
    assert judge(_FEW_SHOT, _ITEM) == 0
    assert len(stub.calls) == 1


def test_cache_survives_a_fresh_judge_instance(tmp_path):
    judge1 = _make(tmp_path, _StubPromptFn(raw={"verdict": 1}))
    assert judge1(_FEW_SHOT, _ITEM) == 1
    # A fresh instance re-reads the file; this stub would DISAGREE if called.
    disagreeing = _StubPromptFn(raw={"verdict": 0})
    judge2 = _make(tmp_path, disagreeing)
    assert judge2(_FEW_SHOT, _ITEM) == 1
    assert disagreeing.calls == []


def test_different_prompt_and_different_model_both_miss_cache(tmp_path):
    stub = _StubPromptFn(raw={"verdict": 1})
    judge = _make(tmp_path, stub)
    judge(_FEW_SHOT, _ITEM)
    judge(_FEW_SHOT, {"chain_signature": "sig-other"})   # new prompt
    other_model = _make(tmp_path, stub, model="sonnet")  # same prompt, new model
    other_model(_FEW_SHOT, _ITEM)
    assert len(stub.calls) == 3


def test_cache_file_lines_are_valid_json_with_contract_keys(tmp_path):
    stub = _StubPromptFn(raw={"verdict": 1})
    judge = _make(tmp_path, stub)
    judge(_FEW_SHOT, _ITEM)
    judge(_FEW_SHOT, {"chain_signature": "sig-other"})
    lines = [ln for ln in (tmp_path / "judge_cache.jsonl")
             .read_text(encoding="utf-8").splitlines() if ln.strip()]
    assert len(lines) == 2
    records = [json.loads(ln) for ln in lines]
    for rec in records:
        assert set(rec) == {"key", "model", "raw"}
        assert rec["model"] == "haiku"
        assert rec["raw"] == {"verdict": 1}
    expected = hashlib.sha256(
        ("haiku" + chr(0) + _build_prompt(_FEW_SHOT, _ITEM)).encode("utf-8")
    ).hexdigest()
    assert records[0]["key"] == expected


def test_malformed_cache_line_is_skipped_with_warning(tmp_path, caplog):
    path = tmp_path / "judge_cache.jsonl"
    path.write_text("this is not json\n", encoding="utf-8")
    stub = _StubPromptFn(raw={"verdict": 1})
    judge = judge_llm.make_llm_judge(_build_prompt, _parse_verdict, "haiku",
                                     prompt_fn=stub, cache_path=path)
    with caplog.at_level(logging.WARNING, logger="judge_llm"):
        assert judge(_FEW_SHOT, _ITEM) == 1
    assert any("malformed" in rec.message for rec in caplog.records)


def test_default_cache_path_is_gitignored_output_jsonl():
    # Documents the default; live runs land in data-pipeline/output/.
    assert judge_llm.DEFAULT_CACHE_PATH.name == "judge_cache.jsonl"
    assert judge_llm.DEFAULT_CACHE_PATH.parent.name == "output"
    assert judge_llm.DEFAULT_CACHE_PATH.parent.parent.name == "data-pipeline"


# --- abstention boundary --------------------------------------------------------

def test_unparseable_raw_raises_judge_abstain(tmp_path):
    stub = _StubPromptFn(raw={"note": "no verdict here"})
    judge = _make(tmp_path, stub)
    with pytest.raises(judge_llm.JudgeAbstain):
        judge(_FEW_SHOT, _ITEM)


def test_garbage_raw_is_cached_so_reabstaining_costs_nothing(tmp_path):
    stub = _StubPromptFn(raw="total garbage")
    judge = _make(tmp_path, stub)
    with pytest.raises(judge_llm.JudgeAbstain):
        judge(_FEW_SHOT, _ITEM)
    with pytest.raises(judge_llm.JudgeAbstain):
        judge(_FEW_SHOT, _ITEM)
    assert len(stub.calls) == 1  # known-garbage never re-spends


def test_claude_parse_error_maps_to_abstain(tmp_path):
    stub = _StubPromptFn(error=claude_client.ParseError("bad json"))
    with pytest.raises(judge_llm.JudgeAbstain):
        _make(tmp_path, stub)(_FEW_SHOT, _ITEM)


def test_generic_claude_error_maps_to_abstain(tmp_path):
    stub = _StubPromptFn(error=claude_client.ClaudeError("CLI exit 1"))
    with pytest.raises(judge_llm.JudgeAbstain):
        _make(tmp_path, stub)(_FEW_SHOT, _ITEM)


def test_claude_errors_are_never_cached(tmp_path):
    # A transient CLI failure must not poison the cache: a later run succeeds.
    failing = _StubPromptFn(error=claude_client.ClaudeError("transient"))
    with pytest.raises(judge_llm.JudgeAbstain):
        _make(tmp_path, failing)(_FEW_SHOT, _ITEM)
    ok = _StubPromptFn(raw={"verdict": 1})
    assert _make(tmp_path, ok)(_FEW_SHOT, _ITEM) == 1
    assert len(ok.calls) == 1


def test_unrelated_exceptions_propagate_not_abstain(tmp_path):
    # A programming error in build_prompt/prompt_fn must surface, not be
    # silently converted into an abstention.
    stub = _StubPromptFn(error=KeyError("bug"))
    with pytest.raises(KeyError):
        _make(tmp_path, stub)(_FEW_SHOT, _ITEM)


# --- session-limit pass-through --------------------------------------------------

def test_session_limit_error_propagates_untouched(tmp_path):
    err = claude_client.SessionLimitError(
        "429 session limit", reset_text="resets 7am (UTC)",
        reset_hour=7, reset_minute=0)
    judge = _make(tmp_path, _StubPromptFn(error=err))
    with pytest.raises(claude_client.SessionLimitError) as excinfo:
        judge(_FEW_SHOT, _ITEM)
    assert excinfo.value is err  # untouched — reset metadata intact for the caller
    assert excinfo.value.reset_hour == 7


def test_session_limit_format_error_also_propagates(tmp_path):
    # Same 429 hard-limit event, unparseable reset format — designed LOUD;
    # degrading it to abstention would grind one doomed call per remaining item.
    err = claude_client.SessionLimitFormatError("429 unparseable reset", raw="resets soon")
    judge = _make(tmp_path, _StubPromptFn(error=err))
    with pytest.raises(claude_client.SessionLimitFormatError):
        judge(_FEW_SHOT, _ITEM)
