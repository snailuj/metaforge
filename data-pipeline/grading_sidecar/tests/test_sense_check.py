"""Unit tests for the sense-check sampler + item builder."""
from __future__ import annotations
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from grading_sidecar import paths as paths_mod


def test_sense_labels_path_is_separate_from_judgements():
    # Safety invariant: a sense label must never share a file with gold verdicts.
    assert paths_mod.SENSE_LABELS_PATH != paths_mod.JUDGEMENTS_PATH
    assert paths_mod.SENSE_LABELS_PATH.name == "sense_labels_provisional.jsonl"
    assert paths_mod.SENSE_FLAGS_NAME == "sense_flags_provisional.jsonl"
    assert paths_mod.SENSE_CANDIDATES_NAME == "sense_candidates_provisional.jsonl"
