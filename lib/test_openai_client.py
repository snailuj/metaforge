"""Tests for the provider-agnostic OpenAI-compatible client (bake-off + farm-out).

The HTTP transport is injected (`_post`) so tests exercise real client behaviour
(parsing, fence-stripping, retry, request shaping) without network access.
"""
import pytest

import openai_client as oc


def _resp(content):
    return {"choices": [{"message": {"content": content}}]}


def test_prompt_text_extracts_message_content():
    out = oc.prompt_text("hi", model="m", base_url="http://x", api_key="k",
                         _post=lambda *a, **k: _resp("hello world"))
    assert out == "hello world"


def test_prompt_json_parses_fenced_object():
    out = oc.prompt_json("hi", model="m", base_url="http://x", api_key="k",
                         _post=lambda *a, **k: _resp("```json\n{\"a\": 1}\n```"))
    assert out == {"a": 1}


def test_prompt_json_parses_bare_array():
    out = oc.prompt_json("hi", model="m", base_url="http://x", api_key="k",
                         _post=lambda *a, **k: _resp('[{"word": "x", "keep": true}]'))
    assert out == [{"word": "x", "keep": True}]


def test_prompt_json_sends_max_tokens_when_set():
    # Capping max_tokens matters for OpenRouter: it RESERVES credit for the full
    # max_tokens up front, so an uncapped judge call (model default 65536) 402s
    # when the balance is low even though the verdict is only ~50 tokens.
    captured = {}

    def capture(url, body, api_key, timeout):
        captured.update(body)
        return _resp("{}")

    oc.prompt_json("hi", model="m", base_url="http://x", api_key="k",
                   max_tokens=256, _post=capture)
    assert captured["max_tokens"] == 256


def test_prompt_json_omits_max_tokens_by_default():
    captured = {}

    def capture(url, body, api_key, timeout):
        captured.update(body)
        return _resp("{}")

    # default (None) must NOT send the field — generation calls need the model's full budget
    oc.prompt_json("hi", model="m", base_url="http://x", api_key="k", _post=capture)
    assert "max_tokens" not in captured


def test_prompt_json_retries_transient_then_succeeds():
    calls = {"n": 0}

    def flaky(*a, **k):
        calls["n"] += 1
        if calls["n"] < 3:
            raise oc.RateLimitError("429 slow down")
        return _resp("{}")

    out = oc.prompt_json("hi", model="m", base_url="http://x", api_key="k",
                         max_retries=5, _post=flaky, _sleep=lambda s: None)
    assert out == {} and calls["n"] == 3


def test_prompt_json_raises_after_exhausting_retries():
    def always_429(*a, **k):
        raise oc.RateLimitError("429")

    with pytest.raises(oc.OpenAIClientError):
        oc.prompt_json("hi", model="m", base_url="http://x", api_key="k",
                       max_retries=2, _post=always_429, _sleep=lambda s: None)


def test_request_shape_and_auth_and_url_join():
    seen = {}

    def capture(url, body, api_key, timeout):
        seen.update(url=url, body=body, api_key=api_key)
        return _resp("ok")

    oc.prompt_text("hello", model="qwen-72b", base_url="http://h/v1/", api_key="KEY",
                   _post=capture)
    assert seen["url"] == "http://h/v1/chat/completions"
    assert seen["body"]["model"] == "qwen-72b"
    assert seen["body"]["messages"] == [{"role": "user", "content": "hello"}]
    assert seen["api_key"] == "KEY"


def test_prompt_json_tolerates_trailing_prose_after_json():
    # Some models (e.g. Haiku via OpenRouter) append commentary after the JSON.
    # Extract the first JSON value rather than failing the whole call.
    out = oc.prompt_json("hi", model="m", base_url="http://x", api_key="k",
                         _post=lambda *a, **k: _resp('{"accurate": false}\n\nIn the phrase "x", the word...'))
    assert out == {"accurate": False}


def test_prompt_json_tolerates_fenced_json_with_trailing_prose():
    out = oc.prompt_json("hi", model="m", base_url="http://x", api_key="k",
                         _post=lambda *a, **k: _resp('```json\n{"accurate": true}\n```\n\nThis gloss is accurate because...'))
    assert out == {"accurate": True}


def test_prompt_json_passes_reasoning_into_body():
    seen = {}

    def capture(url, body, api_key, timeout):
        seen.update(body=body)
        return _resp("{}")

    oc.prompt_json("hi", model="m", base_url="http://x", api_key="k",
                   reasoning={"enabled": False}, _post=capture)
    assert seen["body"]["reasoning"] == {"enabled": False}


def test_prompt_json_omits_reasoning_when_none():
    seen = {}

    def capture(url, body, api_key, timeout):
        seen.update(body=body)
        return _resp("{}")

    oc.prompt_json("hi", model="m", base_url="http://x", api_key="k", _post=capture)
    assert "reasoning" not in seen["body"]


def test_prompt_json_retries_on_unparseable_then_succeeds():
    calls = {"n": 0}

    def flaky(*a, **k):
        calls["n"] += 1
        return _resp("not json at all") if calls["n"] == 1 else _resp('{"ok": 1}')

    out = oc.prompt_json("hi", model="m", base_url="http://x", api_key="k",
                         max_retries=3, _post=flaky, _sleep=lambda s: None)
    assert out == {"ok": 1} and calls["n"] == 2
