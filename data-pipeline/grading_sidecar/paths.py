"""Canonical filesystem paths for grading data."""
from __future__ import annotations
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
GRADING_DIR = REPO_ROOT / "data-pipeline" / "grading"
CHAINS_GLOB = "sonnet_chains_provisional_r*.jsonl"
JUDGEMENTS_PATH = GRADING_DIR / "judgements_provisional.jsonl"
DESIGN_NOTES_PATH = GRADING_DIR / "design_notes_provisional.md"
