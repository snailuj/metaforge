"""Tests for prompt_templates.py — exploration prompts and tweak generator."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))

from unittest.mock import patch
from prompt_templates import EXPLORATION_PROMPTS, generate_tweak


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
