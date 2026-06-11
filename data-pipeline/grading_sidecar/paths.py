"""Canonical filesystem paths for grading data.

Resolved relative to the repo root at import time so tests can monkey-patch
GRADING_DIR for isolation.
"""
from __future__ import annotations
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
GRADING_DIR = REPO_ROOT / "data-pipeline" / "grading"
CHAINS_GLOB = "sonnet_chains_provisional_r*.jsonl"
JUDGEMENTS_PATH = GRADING_DIR / "judgements_provisional.jsonl"
# Blind re-grade verdicts — a SEPARATE file from the gold judgements on purpose.
# The gold resolver is latest-wins per chain_signature, so a blind regrade written
# into JUDGEMENTS_PATH would silently overwrite the very verdict it is meant to be
# compared against. Kept here, auto-committed like the rest of GRADING_DIR, but
# never read by the gold-verdict path — only by the self-agreement report.
REGRADES_PATH = GRADING_DIR / "regrades_blind_provisional.jsonl"
DESIGN_NOTES_PATH = GRADING_DIR / "design_notes_provisional.md"
# Triage sidecar data feeding the signal-prioritised walk (see walk.py). Liveness
# is split across snapshot files (handpicked + r2 rounds) so it is globbed; the
# structural flags are a single file. Joined to GRADING_DIR dynamically by the
# walk route so tests can monkey-patch GRADING_DIR for isolation.
TRIAGE_SCORES_GLOB = "triage_scores*.jsonl"
TRIAGE_STRUCTURAL_NAME = "triage_structural.jsonl"
# Precomputed per-chain path geometry (max_hop_cos etc.), keyed by chain_signature,
# served by the /signal report. Generated offline against the typed lexicon
# (the sidecar has no DB/numpy); absence degrades the report to coverage-only.
CHAIN_GEOMETRY_NAME = "chain_geometry_provisional.jsonl"
# Precomputed synset gloss + POS (synset_id -> {pos, definition}) for the chain
# synsets, served by /glosses so the grader can disambiguate a topic's sense.
# Generated offline from the lexicon's synsets table (the sidecar has no DB).
CHAIN_GLOSSES_NAME = "chain_glosses_provisional.jsonl"
