"""W4: both head-generation prompts must carry the polarity/modifier clause so a
phrase like 'resists change' is not reduced to its bare object noun 'change'."""
from __future__ import annotations
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from head_extraction_backfill import HEAD_PROMPT_INSTRUCTIONS
from metaphor_graph_enrich_sonnet import SONNET_EDIT_PROMPT


def test_haiku_head_prompt_has_polarity_clause():
    p = HEAD_PROMPT_INSTRUCTIONS.lower()
    assert "resists change" in p
    assert "resistance" in p or "stability" in p


def test_sonnet_edit_prompt_has_polarity_clause():
    p = SONNET_EDIT_PROMPT.lower()
    assert "resists change" in p
    assert "polarity" in p or "resistance" in p or "stability" in p
