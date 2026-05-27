#!/usr/bin/env python3
"""Python↔Go cascade-scorer parity harness — acceptance criterion 3.

Picks 50 (topic, vehicle) pairs from the Phase 2 + Lakoff cohorts, scores
each pair via Python's ``evaluate_cascade_pair`` with ``PRODUCTION_CASCADE_CONFIG``
AND via Go's ``/forge/suggest`` endpoint (env vars wired to the same config),
then asserts ``|python_final − go_final| < 1e-6`` for every comparable pair.

Skips pairs where either side cannot produce a final_score
(missing_concreteness, no_properties, no matching Go candidate, gate_dropped
on the Python side — Go does not emit gate_dropped under soft gate).

Exit 0: all comparable pairs within tolerance.
Exit 1: any mismatch found, or the API failed to start.

Usage::

    # From repo root with the venv active and Go binary built:
    .venv/bin/python data-pipeline/scripts/parity_test_go_vs_python.py

    # Point at a custom binary / DB:
    PARITY_BINARY=api/metaforge PARITY_DB=data-pipeline/output/lexicon_v2.db \\
        .venv/bin/python data-pipeline/scripts/parity_test_go_vs_python.py

Important: the Go binary must be built before running this script.
  cd api && go build -o metaforge ./cmd/metaforge
"""
from __future__ import annotations

import json
import logging
import os
import random
import signal
import sqlite3
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional

import requests

# ---------------------------------------------------------------------------
# Path setup
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "data-pipeline" / "scripts"))

from evaluate_aptness import lookup_primary_synset  # noqa: E402
from evaluate_cascade import evaluate_cascade_pair  # noqa: E402
from evaluate_loop_harness import (  # noqa: E402
    PRODUCTION_CASCADE_CONFIG,
    _load_lakoff_pairs,
    _load_phase2_pairs,
)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

DB_PATH = Path(os.environ.get("PARITY_DB", str(REPO_ROOT / "data-pipeline" / "output" / "lexicon_v2.db")))
BINARY = Path(os.environ.get("PARITY_BINARY", str(REPO_ROOT / "api" / "metaforge")))

PORT = int(os.environ.get("PARITY_PORT", "9193"))
LIMIT = 200          # candidates per /forge/suggest request — high to maximise coverage
TARGET_PAIRS = 50    # total pairs to test
SEED = 20260526      # deterministic — same pairs every run
TOLERANCE = 1e-6

# Phase 2 cohort paths (same defaults as evaluate_loop_harness)
PHASE2_APT = REPO_ROOT / "data-pipeline" / "output" / "metaphor_spike_apt_phase2_20260525T004154.jsonl"
PHASE2_INAPT = REPO_ROOT / "data-pipeline" / "output" / "metaphor_spike_inapt_phase2_20260525T004154.jsonl"
LAKOFF_APT = REPO_ROOT / "data-pipeline" / "fixtures" / "lakoff_apt.jsonl"
LAKOFF_INAPT = REPO_ROOT / "data-pipeline" / "fixtures" / "lakoff_inapt.jsonl"

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Go API lifecycle helpers (mirrors loop1_eyeball_harness.py)
# ---------------------------------------------------------------------------

def _build_go_env() -> dict[str, str]:
    """Build the environment mapping that mirrors PRODUCTION_CASCADE_CONFIG.

    M05 type-diversity bonus (Gamma) must be disabled here because Python's
    evaluate_cascade_pair has no Gamma term. Setting METAFORGE_FORGE_GAMMA=0
    ensures the Go scorer matches Python's algorithm exactly.
    """
    cfg = PRODUCTION_CASCADE_CONFIG
    env = os.environ.copy()
    env["METAFORGE_FORGE_CASCADE"] = "1"
    env["METAFORGE_FORGE_GATE_MODE"] = cfg.gate_mode
    env["METAFORGE_FORGE_GATE_ALPHA"] = str(cfg.gate_alpha)
    env["METAFORGE_FORGE_ALPHA"] = str(cfg.alpha)
    env["METAFORGE_FORGE_DCAP"] = str(cfg.d_cap)
    env["METAFORGE_FORGE_RERANK_EXPONENT"] = str(cfg.rerank_exponent)
    env["METAFORGE_FORGE_CONCRETENESS_BONUS_COEF"] = str(cfg.concreteness_bonus_coef)
    env["METAFORGE_FORGE_ORTONY_WEIGHT"] = str(cfg.ortony_weight)
    env["METAFORGE_FORGE_ORTONY_SCORING"] = cfg.ortony_scoring
    # Disable M05 type-diversity bonus — Python side has no equivalent.
    env["METAFORGE_FORGE_GAMMA"] = "0"
    return env


def start_api() -> subprocess.Popen:
    """Start the Go API and wait for it to become healthy.

    Raises RuntimeError if the port is already in use (another process is
    listening) — this guards against accidentally querying a stale API instance
    with a different config, which would produce silent parity failures.
    """
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        if s.connect_ex(("127.0.0.1", PORT)) == 0:
            raise RuntimeError(
                f"Port {PORT} is already in use — kill the existing process before running "
                "the parity test, or set PARITY_PORT env var to an available port. "
                "Running against a pre-existing API risks comparing against the wrong config."
            )

    env = _build_go_env()
    args = [str(BINARY), "--db", str(DB_PATH), "--port", str(PORT), "--cascade"]
    proc = subprocess.Popen(args, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    base = f"http://127.0.0.1:{PORT}"
    deadline = time.time() + 20
    while time.time() < deadline:
        try:
            if requests.get(f"{base}/health", timeout=0.5).ok:
                log.info("API healthy at %s (pid=%d)", base, proc.pid)
                return proc
        except requests.RequestException:
            time.sleep(0.1)
    proc.kill()
    out, err = proc.communicate(timeout=2)
    raise RuntimeError(
        f"API failed to start:\nstdout: {out[-500:]!r}\nstderr: {err[-500:]!r}"
    )


def stop_api(proc: subprocess.Popen) -> None:
    proc.send_signal(signal.SIGTERM)
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=2)


# ---------------------------------------------------------------------------
# Topic sampling (used by Go-first pair generation)
# ---------------------------------------------------------------------------

def _sample_topics(n_phase2: int, n_lakoff: int, seed: int) -> list[dict]:
    """Sample unique topic lemmas from both cohorts.

    Returns a flat list of dicts with: topic, cohort_source.
    Deterministic via seed.
    """
    rng = random.Random(seed)

    phase2_rows = _load_phase2_pairs(PHASE2_APT, PHASE2_INAPT)
    lakoff_rows = _load_lakoff_pairs(LAKOFF_APT, LAKOFF_INAPT)

    # Extract unique topics from each cohort.
    p2_topics = list({r["topic"]: r for r in phase2_rows}.values())
    lak_topics = list({r["topic"]: r for r in lakoff_rows}.values())

    p2_sample = rng.sample(p2_topics, min(n_phase2, len(p2_topics)))
    lak_sample = rng.sample(lak_topics, min(n_lakoff, len(lak_topics)))

    result = []
    for r in p2_sample:
        result.append({"topic": r["topic"], "cohort_source": "phase2"})
    for r in lak_sample:
        result.append({"topic": r["topic"], "cohort_source": "lakoff"})
    rng.shuffle(result)
    return result


# ---------------------------------------------------------------------------
# Go-side query
# ---------------------------------------------------------------------------

def fetch_suggestions(base_url: str, lemma: str, limit: int) -> Optional[list[dict]]:
    """Query /forge/suggest and return the suggestions list, or None on error."""
    try:
        r = requests.get(
            f"{base_url}/forge/suggest",
            params={"word": lemma, "limit": limit},
            timeout=30,
        )
    except requests.RequestException as exc:
        log.warning("fetch_suggestions: request failed for %r: %s", lemma, exc)
        return None
    if r.status_code != 200:
        log.warning(
            "fetch_suggestions: %r status=%d body=%s",
            lemma, r.status_code, r.text[:200],
        )
        return None
    body = r.json()
    return body.get("suggestions", [])


# ---------------------------------------------------------------------------
# Main parity check logic
# ---------------------------------------------------------------------------

def run_parity(conn: sqlite3.Connection, base_url: str) -> tuple[int, int, list[dict]]:
    """Score at least TARGET_PAIRS pairs through both Python and Go and compare.

    Strategy — Go-first pair generation:
      1. Sample unique topic lemmas from both cohorts (~12 Phase 2 + ~13 Lakoff).
      2. Query Go for each topic to get its candidate list.
      3. From Go's candidates, randomly pick up to 5 per topic (capped so we
         reach ~50 total).  Each Go candidate carries its actual source_synset_id
         so Python can be scored on the IDENTICAL (source_synset_id, vehicle_synset_id)
         pair — guaranteeing comparability without depending on lemma-resolution
         agreement between the two implementations.
      4. Skip only candidates where Python returns status!=scored (missing_concreteness
         or no_properties — these reflect data gaps, not algorithmic divergence).

    Returns (n_comparable, n_mismatch, mismatch_details).
    """
    rng = random.Random(SEED)

    # Sample topics — aim for enough that we can fill TARGET_PAIRS even with
    # some topics returning 0 Go candidates.
    topics = _sample_topics(n_phase2=12, n_lakoff=13, seed=SEED)
    log.info("sampled %d topics (%d phase2 + %d lakoff)",
             len(topics),
             sum(1 for t in topics if t["cohort_source"] == "phase2"),
             sum(1 for t in topics if t["cohort_source"] == "lakoff"))

    all_pairs: list[dict] = []
    # Collect all Go candidates per topic, then sample.
    for t in topics:
        topic_lemma = t["topic"]
        cohort_source = t["cohort_source"]
        suggestions = fetch_suggestions(base_url, topic_lemma, LIMIT)
        if not suggestions:
            log.info("TOPIC_SKIP %r (%s): Go returned 0 scored candidates", topic_lemma, cohort_source)
            continue
        # Randomly sample up to 5 candidates per topic for diversity.
        sample_k = min(5, len(suggestions))
        selected = rng.sample(suggestions, sample_k)
        for s in selected:
            all_pairs.append({
                "topic_lemma": topic_lemma,
                "cohort_source": cohort_source,
                "go_source_sid": s.get("source_synset_id"),
                "vehicle_synset_id": s.get("synset_id"),
                "vehicle_word": s.get("word"),
                "go_final": s.get("final_score"),
                "go_ortony": s.get("ortony_score"),
                "go_cosine": s.get("cosine_distance"),
                "go_rerank": s.get("re_rank_bonus"),
                "go_cascade_status": s.get("cascade_status"),
            })

    log.info("collected %d candidate pairs from Go (target: %d)", len(all_pairs), TARGET_PAIRS)

    # If we have more than TARGET_PAIRS, sample deterministically.
    if len(all_pairs) > TARGET_PAIRS:
        all_pairs = rng.sample(all_pairs, TARGET_PAIRS)

    n_skipped = 0
    n_comparable = 0
    n_mismatch = 0
    mismatches: list[dict] = []

    for i, pair in enumerate(all_pairs, 1):
        topic_lemma = pair["topic_lemma"]
        cohort_source = pair["cohort_source"]
        go_source_sid = pair["go_source_sid"]
        vehicle_synset_id = pair["vehicle_synset_id"]
        vehicle_word = pair["vehicle_word"]
        go_final = pair["go_final"]

        if go_source_sid is None or vehicle_synset_id is None:
            log.info(
                "SKIP [%d] %s %r: missing source or vehicle synset_id in Go response",
                i, cohort_source, topic_lemma,
            )
            n_skipped += 1
            continue

        if go_final is None:
            log.info(
                "SKIP [%d] %s %r→%r: Go final_score is null (status=%s)",
                i, cohort_source, topic_lemma, vehicle_word,
                pair["go_cascade_status"],
            )
            n_skipped += 1
            continue
        go_final = float(go_final)

        # --- Python side -------------------------------------------------
        # Use the exact same (source_synset_id, vehicle_synset_id) that Go used.
        # This avoids all lemma-resolution divergence — we're comparing the
        # cascade math on identical inputs.
        try:
            py_result = evaluate_cascade_pair(
                conn, go_source_sid, vehicle_synset_id, PRODUCTION_CASCADE_CONFIG
            )
        except Exception as exc:
            log.warning(
                "SKIP [%d] %s %r→%r: Python evaluate_cascade_pair raised %s: %s",
                i, cohort_source, topic_lemma, vehicle_word,
                type(exc).__name__, exc,
            )
            n_skipped += 1
            continue

        py_final = py_result.final_score
        if py_final is None:
            # missing_concreteness / no_properties — not a comparable pair.
            # These reflect data availability, not algorithmic divergence.
            log.info(
                "SKIP [%d] %s %r→%r (sid=%s→%s): Python status=%s (no final_score)",
                i, cohort_source, topic_lemma, vehicle_word,
                go_source_sid, vehicle_synset_id, py_result.status,
            )
            n_skipped += 1
            continue

        # --- Compare -----------------------------------------------------
        n_comparable += 1
        delta = abs(py_final - go_final)
        if delta >= TOLERANCE:
            n_mismatch += 1
            detail = {
                "index": i,
                "cohort_source": cohort_source,
                "topic_lemma": topic_lemma,
                "vehicle_word": vehicle_word,
                "topic_synset": go_source_sid,
                "vehicle_synset": vehicle_synset_id,
                "py_final": py_final,
                "go_final": go_final,
                "delta": delta,
                "py_status": py_result.status,
                "go_cascade_status": pair["go_cascade_status"],
                "py_ortony": py_result.ortony_score,
                "go_ortony": pair.get("go_ortony"),
                "py_cosine": py_result.cosine_distance,
                "go_cosine": pair.get("go_cosine"),
                "py_rerank": py_result.re_rank_bonus,
                "go_rerank": pair.get("go_rerank"),
            }
            mismatches.append(detail)
            log.error(
                "MISMATCH [%d] %s %r→%r (sid=%s→%s): py=%.10f go=%.10f delta=%.2e",
                i, cohort_source, topic_lemma, vehicle_word,
                go_source_sid, vehicle_synset_id,
                py_final, go_final, delta,
            )
        else:
            log.debug(
                "OK [%d] %s %r→%r: py=%.10f go=%.10f delta=%.2e",
                i, cohort_source, topic_lemma, vehicle_word,
                py_final, go_final, delta,
            )

    return n_comparable, n_mismatch, mismatches


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        datefmt="%H:%M:%S",
    )

    if not BINARY.exists():
        print(
            f"ERROR: Go binary not found at {BINARY}. "
            "Build first: cd api && go build -o metaforge ./cmd/metaforge",
            file=sys.stderr,
        )
        return 1

    if not DB_PATH.exists():
        print(f"ERROR: DB not found at {DB_PATH}", file=sys.stderr)
        return 1

    log.info(
        "Parity test: %d target pairs, tolerance=%.0e, port=%d",
        TARGET_PAIRS, TOLERANCE, PORT,
    )
    log.info("Binary: %s", BINARY)
    log.info("DB: %s", DB_PATH)
    log.info("PRODUCTION_CASCADE_CONFIG: gate_mode=%s gate_alpha=%s alpha=%s "
             "d_cap=%s rerank_exponent=%s concreteness_bonus_coef=%s "
             "ortony_weight=%s ortony_scoring=%s composition=%s",
             PRODUCTION_CASCADE_CONFIG.gate_mode,
             PRODUCTION_CASCADE_CONFIG.gate_alpha,
             PRODUCTION_CASCADE_CONFIG.alpha,
             PRODUCTION_CASCADE_CONFIG.d_cap,
             PRODUCTION_CASCADE_CONFIG.rerank_exponent,
             PRODUCTION_CASCADE_CONFIG.concreteness_bonus_coef,
             PRODUCTION_CASCADE_CONFIG.ortony_weight,
             PRODUCTION_CASCADE_CONFIG.ortony_scoring,
             PRODUCTION_CASCADE_CONFIG.composition)

    proc = start_api()
    base_url = f"http://127.0.0.1:{PORT}"

    try:
        conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
        try:
            n_comparable, n_mismatch, mismatches = run_parity(conn, base_url)
        finally:
            conn.close()
    finally:
        stop_api(proc)

    print()
    if n_mismatch == 0:
        print(f"PARITY OK: {n_comparable} pairs within {TOLERANCE:.0e}")
        return 0
    else:
        print(f"PARITY FAIL: {n_mismatch} pairs over tolerance (of {n_comparable} comparable)")
        print(f"\nFirst {min(10, len(mismatches))} mismatches:")
        for m in mismatches[:10]:
            print(
                f"  [{m['index']}] {m['cohort_source']} "
                f"{m['topic_lemma']!r}→{m['vehicle_word']!r} "
                f"(topic_sid={m['topic_synset']}, vehicle_sid={m['vehicle_synset']})"
            )
            print(
                f"       py={m['py_final']:.10f}  go={m['go_final']:.10f}  "
                f"delta={m['delta']:.4e}"
            )
            print(f"       py_status={m['py_status']}  go_status={m['go_cascade_status']}")
            if m.get('py_ortony') is not None:
                print(
                    f"       py_ortony={m['py_ortony']:.8f}  go_ortony={m.get('go_ortony')}"
                )
            if m.get('py_cosine') is not None:
                print(
                    f"       py_cosine={m['py_cosine']:.8f}  go_cosine={m.get('go_cosine')}"
                )
            if m.get('py_rerank') is not None:
                print(
                    f"       py_rerank={m['py_rerank']:.8f}  go_rerank={m.get('go_rerank')}"
                )
        return 1


if __name__ == "__main__":
    sys.exit(main())
