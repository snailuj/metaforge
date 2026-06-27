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


def test_prompt_json_retries_on_unparseable_then_succeeds():
    calls = {"n": 0}

    def flaky(*a, **k):
        calls["n"] += 1
        return _resp("not json at all") if calls["n"] == 1 else _resp('{"ok": 1}')

    out = oc.prompt_json("hi", model="m", base_url="http://x", api_key="k",
                         max_retries=3, _post=flaky, _sleep=lambda s: None)
    assert out == {"ok": 1} and calls["n"] == 2
