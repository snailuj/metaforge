"""Tests for prompt_templates.py — exploration prompts and tweak generator."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))

from unittest.mock import patch
from prompt_templates import EXPLORATION_PROMPTS, generate_tweak, improve_prompt


# --- 1. All exploration prompts have {batch_items} placeholder ----------------

def test_all_prompts_have_batch_items_placeholder():
    """Every exploration prompt must contain {batch_items}."""
    assert len(EXPLORATION_PROMPTS) == 5
    for name, prompt in EXPLORATION_PROMPTS.items():
        assert "{batch_items}" in prompt, f"{name} missing {{batch_items}}"


# --- 2. All exploration prompts request JSON output ---------------------------

def test_all_prompts_request_json():
    """Every prompt must instruct the model to return JSON."""
    for name, prompt in EXPLORATION_PROMPTS.items():
        assert "JSON" in prompt or "json" in prompt, (
            f"{name} does not mention JSON output format"
        )


# --- 3. All exploration prompts request 10-15 properties ----------------------

def test_all_prompts_request_property_count():
    """Every prompt must mention 10-15 properties."""
    for name, prompt in EXPLORATION_PROMPTS.items():
        assert "10" in prompt and "15" in prompt, (
            f"{name} does not specify 10-15 property count"
        )


# --- 4. Each prompt has a distinct name ---------------------------------------

def test_prompt_names():
    """Expected prompt names are present."""
    expected = {"persona_poet", "contrastive", "narrative", "taxonomic", "embodied"}
    assert set(EXPLORATION_PROMPTS.keys()) == expected


# --- 5. Prompts can be formatted with batch_items ----------------------------

def test_prompts_format_with_batch_items():
    """Each prompt can .format(batch_items=...) without error."""
    sample = "ID: 100001\nWord: candle\nDefinition: stick of wax\n"
    for name, prompt in EXPLORATION_PROMPTS.items():
        formatted = prompt.format(batch_items=sample)
        assert "candle" in formatted, f"{name} did not interpolate batch_items"


# --- 6. Tweak generator returns modified prompt with {batch_items} -----------

@patch("prompt_templates.invoke_claude")
def test_generate_tweak_returns_modified_prompt(mock_invoke):
    """generate_tweak returns a dict with modified prompt containing {batch_items}."""
    import json
    import subprocess

    # The LLM returns a JSON object with the tweaked prompt and description
    tweak_response = {
        "modified_prompt": "Tweaked version: {batch_items}\nJSON: [{{}}]",
        "description": "Added emphasis on tactile properties",
    }
    events = [
        {"type": "system", "subtype": "init", "session_id": "test"},
        {"type": "result", "subtype": "success", "is_error": False,
         "result": json.dumps(tweak_response)},
    ]
    mock_invoke.return_value = subprocess.CompletedProcess(
        args=["claude"], returncode=0, stdout=json.dumps(events), stderr="",
    )

    per_pair = [
        {"source": "anger", "target": "fire", "rank": 1, "reciprocal_rank": 1.0},
        {"source": "grief", "target": "anchor", "rank": None, "reciprocal_rank": 0.0},
    ]

    result = generate_tweak(
        current_prompt="Original: {batch_items}\nJSON: [{{}}]",
        per_pair=per_pair,
        mrr=0.5,
        model="haiku",
    )

    assert "{batch_items}" in result["modified_prompt"]
    assert result["description"]  # non-empty
    mock_invoke.assert_called_once()


# --- 7. Tweak generator falls back if LLM returns invalid JSON ---------------

@patch("prompt_templates.invoke_claude")
def test_generate_tweak_raises_on_invalid_response(mock_invoke):
    """generate_tweak raises ValueError if LLM returns unparseable response."""
    import json
    import subprocess

    events = [
        {"type": "system", "subtype": "init", "session_id": "test"},
        {"type": "result", "subtype": "success", "is_error": False,
         "result": "This is not valid JSON at all"},
    ]
    mock_invoke.return_value = subprocess.CompletedProcess(
        args=["claude"], returncode=0, stdout=json.dumps(events), stderr="",
    )

    with pytest.raises(ValueError, match="tweak"):
        generate_tweak(
            current_prompt="Prompt: {batch_items}\n[{{}}]",
            per_pair=[],
            mrr=0.5,
            model="haiku",
        )


# --- 8. Tweak generator rejects response missing {batch_items} ---------------

@patch("prompt_templates.invoke_claude")
def test_generate_tweak_rejects_missing_placeholder(mock_invoke):
    """generate_tweak raises ValueError if tweaked prompt lacks {batch_items}."""
    import json
    import subprocess

    tweak_response = {
        "modified_prompt": "No placeholder here",
        "description": "Removed the placeholder accidentally",
    }
    events = [
        {"type": "system", "subtype": "init", "session_id": "test"},
        {"type": "result", "subtype": "success", "is_error": False,
         "result": json.dumps(tweak_response)},
    ]
    mock_invoke.return_value = subprocess.CompletedProcess(
        args=["claude"], returncode=0, stdout=json.dumps(events), stderr="",
    )

    with pytest.raises(ValueError, match="batch_items"):
        generate_tweak(
            current_prompt="Prompt: {batch_items}\n[{{}}]",
            per_pair=[],
            mrr=0.5,
            model="haiku",
        )


# --- 9. improve_prompt preserves {batch_items} placeholder --------------------

@patch("prompt_templates.invoke_claude")
def test_improve_prompt_preserves_batch_items_placeholder(mock_invoke):
    """improve_prompt returns a prompt that still contains {batch_items}."""
    import json
    import subprocess

    improved_text = "Improved prompt with {batch_items} placeholder."
    events = [
        {"type": "result", "subtype": "success", "is_error": False,
         "result": improved_text},
    ]
    mock_invoke.return_value = subprocess.CompletedProcess(
        args=["claude"], returncode=0, stdout=json.dumps(events), stderr="",
    )

    result = improve_prompt("Raw prompt: {batch_items}", model="sonnet")
    assert "{batch_items}" in result


# --- 10. improve_prompt uses the specified model ------------------------------

@patch("prompt_templates.invoke_claude")
def test_improve_prompt_called_with_stronger_model(mock_invoke):
    """improve_prompt calls invoke_claude with the specified model."""
    import json
    import subprocess

    events = [
        {"type": "result", "subtype": "success", "is_error": False,
         "result": "Improved: {batch_items}"},
    ]
    mock_invoke.return_value = subprocess.CompletedProcess(
        args=["claude"], returncode=0, stdout=json.dumps(events), stderr="",
    )

    improve_prompt("Raw: {batch_items}", model="sonnet")
    call_kwargs = mock_invoke.call_args[1] if mock_invoke.call_args[1] else {}
    call_args = mock_invoke.call_args[0] if mock_invoke.call_args[0] else []
    # model should be "sonnet"
    if "model" in call_kwargs:
        assert call_kwargs["model"] == "sonnet"
    else:
        assert call_args[1] == "sonnet"


# --- 11. improve_prompt rejects response without {batch_items} ----------------

@patch("prompt_templates.invoke_claude")
def test_improve_prompt_rejects_response_without_placeholder(mock_invoke):
    """improve_prompt raises ValueError if LLM drops the {batch_items} placeholder."""
    import json
    import subprocess

    events = [
        {"type": "result", "subtype": "success", "is_error": False,
         "result": "Improved prompt without placeholder"},
    ]
    mock_invoke.return_value = subprocess.CompletedProcess(
        args=["claude"], returncode=0, stdout=json.dumps(events), stderr="",
    )

    with pytest.raises(ValueError, match="batch_items"):
        improve_prompt("Raw: {batch_items}", model="sonnet")


# --- 12. Tweak meta-prompt contains no fixture words -------------------------

@patch("prompt_templates.invoke_claude")
def test_tweak_meta_prompt_no_fixture_words(mock_invoke):
    """The tweak meta-prompt sent to the LLM contains no concrete fixture words."""
    import json
    import subprocess

    tweak_response = {
        "modified_prompt": "Tweaked: {batch_items}\nJSON: [{{}}]",
        "description": "some change",
    }
    events = [
        {"type": "result", "subtype": "success", "is_error": False,
         "result": json.dumps(tweak_response)},
    ]
    mock_invoke.return_value = subprocess.CompletedProcess(
        args=["claude"], returncode=0, stdout=json.dumps(events), stderr="",
    )

    per_pair = [
        {"source": "anger", "target": "fire", "rank": 1, "reciprocal_rank": 1.0,
         "tier": "strong"},
        {"source": "grief", "target": "anchor", "rank": None, "reciprocal_rank": 0.0,
         "tier": "medium"},
    ]

    generate_tweak(
        current_prompt="Original: {batch_items}\n[{{}}]",
        per_pair=per_pair,
        mrr=0.5,
        model="haiku",
    )

    # Inspect the prompt that was sent to invoke_claude
    sent_prompt = mock_invoke.call_args[0][0]
    # Should NOT contain concrete source/target words
    assert "anger" not in sent_prompt
    assert "fire" not in sent_prompt
    assert "grief" not in sent_prompt
    assert "anchor" not in sent_prompt


# --- 13. Tweak meta-prompt has aggregate stats --------------------------------

@patch("prompt_templates.invoke_claude")
def test_tweak_meta_prompt_has_aggregate_stats(mock_invoke):
    """The tweak meta-prompt includes aggregate stats instead of concrete pairs."""
    import json
    import subprocess

    tweak_response = {
        "modified_prompt": "Tweaked: {batch_items}\nJSON: [{{}}]",
        "description": "some change",
    }
    events = [
        {"type": "result", "subtype": "success", "is_error": False,
         "result": json.dumps(tweak_response)},
    ]
    mock_invoke.return_value = subprocess.CompletedProcess(
        args=["claude"], returncode=0, stdout=json.dumps(events), stderr="",
    )

    per_pair = [
        {"source": "anger", "target": "fire", "rank": 1, "reciprocal_rank": 1.0,
         "tier": "strong"},
        {"source": "joy", "target": "fountain", "rank": 5, "reciprocal_rank": 0.2,
         "tier": "medium"},
        {"source": "grief", "target": "anchor", "rank": None, "reciprocal_rank": 0.0,
         "tier": "strong"},
    ]

    generate_tweak(
        current_prompt="Original: {batch_items}\n[{{}}]",
        per_pair=per_pair,
        mrr=0.4,
        model="haiku",
    )

    sent_prompt = mock_invoke.call_args[0][0]
    # Should contain aggregate stats
    assert "MRR" in sent_prompt
    assert "0.4" in sent_prompt
    # Should mention hit count or pair count
    assert "3" in sent_prompt or "pair" in sent_prompt.lower()
