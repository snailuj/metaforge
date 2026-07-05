"""Canonical filesystem paths for grading data.

Resolved relative to the repo root at import time so tests can monkey-patch
GRADING_DIR for isolation.
"""
from __future__ import annotations
import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
# Data location is env-overridable so the deploy can point it at a SEPARATE data
# worktree (code/data separation). Default = in-repo, so dev + every test is unchanged.
GRADING_DIR = Path(os.environ.get("GRADING_DATA_DIR", str(REPO_ROOT / "data-pipeline" / "grading")))
# Git root the autocommit targets: the data worktree in deploy, the main repo in dev.
GRADING_DATA_GIT_ROOT = os.environ.get("GRADING_DATA_GIT_ROOT", str(REPO_ROOT))
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

# Sense-check inputs/outputs. The subagent's wrong/rare flags (READ), the offline
# candidate-senses precompute (READ, lemma -> [senses]; DB-free sidecar), and the
# operator's sense labels. SENSE_LABELS_PATH is a SEPARATE file from the gold
# judgements on purpose: a sense label is not a liveness/linkage verdict and must
# never be resolved as one. Auto-committed like the rest of GRADING_DIR.
SENSE_FLAGS_NAME = "sense_flags_provisional.jsonl"
SENSE_CANDIDATES_NAME = "sense_candidates_provisional.jsonl"
SENSE_LABELS_PATH = GRADING_DIR / "sense_labels_provisional.jsonl"

# Operator-prefilled guided-walk candidate list (chain_signature, order, cohort,
# judge_verdict, batch) — an EXACT ordered subset teed up offline for a blind
# grading round. The stored judge_verdict + eval/train cohort are server-side
# only (never served to the client): showing them would anchor the blind grade.
GUIDED_WALK_NAME = "guided_walk_provisional.jsonl"

# --- Chain cohorts (source-by-location) ---
# Grading views (walk/topic/stats/chains/regrade) read GRADING_COHORTS. The
# sense-check context reads SENSECHECK_COHORTS (adds `stock`). `stock` lives under a
# stock/ subdir the top-level grading globs DON'T match, so it never surfaces in
# grading views. Globs are relative to GRADING_DIR. spike/curated match the new
# chain-topics_* names AND the legacy sonnet_chains_provisional_* names (transitional —
# drop the legacy entries once the data rename in Task 8 has propagated everywhere).
CHAIN_COHORTS: dict[str, list[str]] = {
    "spike":   ["chain-topics_spike*.jsonl",
                "sonnet_chains_provisional_r1*.jsonl",
                "sonnet_chains_provisional_r2.jsonl"],
    "curated": ["chain-topics_curated*.jsonl",
                "sonnet_chains_provisional_r2_handpicked*.jsonl"],
    "stock":   ["stock/chain-topics_stock*.jsonl"],
}
GRADING_COHORTS = ["spike", "curated"]
SENSECHECK_COHORTS = ["spike", "curated", "stock"]
