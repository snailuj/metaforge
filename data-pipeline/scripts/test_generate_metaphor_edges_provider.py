"""Provider-agnostic LLM-fn factories: the bulk calls (haiku apt + sonnet chains)
must be drivable by an injected `prompt_json`, so generation can be farmed out to
any OpenAI-compatible provider instead of the Claude CLI.
"""
import generate_metaphor_edges as gme


def test_sonnet_factory_uses_injected_prompt_json():
    seen = []

    def pj(prompt, model):
        seen.append((prompt, model))
        return {"vehicles": [{"chain": []}]}

    fn = gme.make_live_sonnet_fn("glm-5.2", prompt_json=pj)
    out = fn("the sonnet prompt")
    assert out == {"vehicles": [{"chain": []}]}
    assert seen == [("the sonnet prompt", "glm-5.2")]


def test_haiku_factory_uses_injected_prompt_json():
    seen = []

    def pj(prompt, model):
        seen.append(model)
        return {"metaphors": []}

    fn = gme.make_live_haiku_fn("qwen-72b", avoid_vehicles=["river"], prompt_json=pj)
    out = fn("hope", "a feeling of expectation")
    assert out == {"metaphors": []}
    assert seen == ["qwen-72b"]


def test_factory_default_is_claude_backward_compatible():
    # No prompt_json injected -> the factory still constructs (lazy-imports the
    # Claude client); we only assert it builds a callable, not that it calls out.
    assert callable(gme.make_live_sonnet_fn("claude-sonnet-4-6"))
    assert callable(gme.make_live_haiku_fn("claude-haiku-4-5-20251001"))
