#!/usr/bin/env python3
"""M04 calibration-sweep driver.

For each variation in an M04 sweep YAML, spawns the Go API with the
matching env vars, queries /forge/suggest for every MUNCH apt+inapt
pair, computes per-cell separation_score / aptness_rate, then writes
a JSON results file and a human-readable verdict markdown.

Unlike the generic run_sweep.py harness (which drives the Python
aptness evaluator in-process), this driver tests the integrated Go
candidate-generation path end-to-end — the only fair test for M04's
generation-broadening claim.

Usage:
    python data-pipeline/scripts/m04_sweep_runner.py \\
        --config data-pipeline/sweeps/m04_embedding_band.yaml \\
        --output data-pipeline/output/m04_embedding_band_results.json \\
        --verdict data-pipeline/sweeps/m04_embedding_band_verdict.md
"""

from __future__ import annotations

import argparse
import json
import os
import random
import shutil
import signal
import statistics
import subprocess
import sys
import time
import dataclasses
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

import requests
import yaml


@dataclass
class CellResult:
    name: str
    candidate_sources: str
    d_min: float | None
    d_max: float | None
    top_k: int | None
    gamma: float | None = None
    apt_scores: list[float] = field(default_factory=list)
    inapt_scores: list[float] = field(default_factory=list)
    apt_missing: int = 0
    inapt_missing: int = 0
    source_mix: dict[str, int] = field(default_factory=lambda: {"cluster": 0, "embedding": 0, "both": 0})
    # Derived metrics — populated by ``finalise_metrics`` before serialisation
    # so that ``dataclasses.asdict`` exposes them in the JSON output.
    # ``None`` means "not yet computed"; the @property accessors below treat
    # ``None`` as a signal to recompute on the fly, which keeps ad-hoc use
    # (e.g. tests, REPL) ergonomic without forcing callers to remember
    # ``finalise_metrics()``. Note: ``dataclasses.asdict`` serialises the
    # underscore-prefixed *fields*, not the @property values, so
    # ``finalise_metrics()`` is still required before serialising.
    _aptness_rate: float | None = None
    _separation_score: float | None = None

    def _compute_aptness_rate(self) -> float:
        if not self.apt_scores:
            return 0.0
        # statistics.quantiles requires >=2 data points; Lakoff cohort
        # often has many inapt pairs unresolved by the API (cross-domain
        # implausible vehicles fall outside the cosine band), so guard
        # explicitly rather than crashing on the percentile call.
        if len(self.inapt_scores) < 2:
            return 0.0
        threshold = statistics.quantiles(self.inapt_scores, n=20)[18]  # 95th percentile
        return sum(1 for s in self.apt_scores if s > threshold) / len(self.apt_scores)

    def _compute_separation_score(self) -> float:
        if not self.apt_scores or not self.inapt_scores:
            return 0.0
        return statistics.mean(self.apt_scores) - statistics.mean(self.inapt_scores)

    @property
    def aptness_rate(self) -> float:
        """Return the stored aptness_rate, or recompute on the fly if unset.

        After ``finalise_metrics()`` runs, this returns the snapshot verbatim.
        Before then, it recomputes from ``apt_scores`` / ``inapt_scores`` so
        ad-hoc access (tests, REPL) works without needing to finalise first.
        """
        if self._aptness_rate is None:
            return self._compute_aptness_rate()
        return self._aptness_rate

    @property
    def separation_score(self) -> float:
        """Return the stored separation_score, or recompute on the fly if unset.

        After ``finalise_metrics()`` runs, this returns the snapshot verbatim.
        """
        if self._separation_score is None:
            return self._compute_separation_score()
        return self._separation_score

    def finalise_metrics(self) -> None:
        """Snapshot derived-metric fields from raw score lists.

        Idempotent — safe to call multiple times. Must be invoked before
        ``dataclasses.asdict`` if the JSON output is expected to carry
        aptness_rate and separation_score (asdict serialises the stored
        fields, not the @property accessors).
        """
        self._aptness_rate = self._compute_aptness_rate()
        self._separation_score = self._compute_separation_score()

    def to_dict(self) -> dict:
        """Serialise to JSON-friendly dict with public key names.

        Calls finalise_metrics() to snapshot computed metrics before
        serialisation. Keys are the public names (``aptness_rate``,
        ``separation_score``) not the internal underscore-prefixed fields —
        preserves wire compat with historical sweep result JSONs that
        predate the R2 @property refactor.
        """
        self.finalise_metrics()
        d = dataclasses.asdict(self)
        # Rewrite underscore-prefixed keys to their public names.
        if "_aptness_rate" in d:
            d["aptness_rate"] = d.pop("_aptness_rate")
        if "_separation_score" in d:
            d["separation_score"] = d.pop("_separation_score")
        return d


def load_pairs(path: Path) -> list[tuple[str, str]]:
    """Load MUNCH-shaped JSONL: one object per line.

    MUNCH fixtures use ``target`` (the metaphor target word — the topic being
    described) and ``paraphrase`` (the candidate substitute — the vehicle the
    forge is ranking). We also accept generic ``topic``/``vehicle`` and other
    synonyms so the runner works against non-MUNCH fixtures.
    """
    pairs: list[tuple[str, str]] = []
    with path.open() as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            obj = json.loads(line)
            topic = obj.get("topic") or obj.get("target") or obj.get("source") or obj.get("subject")
            vehicle = obj.get("vehicle") or obj.get("paraphrase") or obj.get("object")
            if topic and vehicle:
                pairs.append((str(topic), str(vehicle)))
    return pairs


def start_api(binary: str, db: Path, port: int, env_overrides: dict[str, str]) -> subprocess.Popen:
    env = os.environ.copy()
    env["METAFORGE_FORGE_CASCADE"] = "1"
    env.update(env_overrides)
    args = [binary, "--db", str(db), "--port", str(port), "--cascade"]
    proc = subprocess.Popen(args, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    # Poll /health for up to 10s.
    base = f"http://127.0.0.1:{port}"
    deadline = time.time() + 10
    while time.time() < deadline:
        try:
            r = requests.get(f"{base}/health", timeout=0.5)
            if r.ok:
                return proc
        except requests.RequestException:
            time.sleep(0.1)
    proc.kill()
    out, err = proc.communicate(timeout=2)
    raise RuntimeError(f"API failed to start on port {port}:\nstdout: {out!r}\nstderr: {err!r}")


def stop_api(proc: subprocess.Popen) -> None:
    proc.send_signal(signal.SIGTERM)
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=2)


def fetch_suggestions(base_url: str, topic: str, limit: int) -> dict[str, tuple[float | None, str | None]] | None:
    """Fetch /forge/suggest for a topic and return a {vehicle_word: (final_score, source)} map.

    Returns ``None`` if the API call failed (so callers can distinguish a missing topic
    from a missing vehicle within a topic's suggestion list).
    """
    try:
        r = requests.get(f"{base_url}/forge/suggest", params={"word": topic, "limit": limit}, timeout=10)
    except requests.RequestException as e:
        print(f"  WARN fetch_suggestions: topic={topic!r} request failed: {type(e).__name__}: {e}", file=sys.stderr, flush=True)
        return None
    if r.status_code != 200:
        print(f"  WARN fetch_suggestions: topic={topic!r} status={r.status_code} body={r.text[:200]!r}", file=sys.stderr, flush=True)
        return None
    try:
        body = r.json()
    except ValueError as e:
        print(f"  WARN fetch_suggestions: topic={topic!r} non-JSON response: {e}; body={r.text[:200]!r}", file=sys.stderr, flush=True)
        return None
    out: dict[str, tuple[float | None, str | None]] = {}
    for s in body.get("suggestions", []):
        word = s.get("word")
        if not word:
            continue
        fs = s.get("final_score")
        out[word] = ((float(fs) if fs is not None else None), s.get("candidate_source", ""))
    return out


def score_pair_cached(
    cache: dict[str, dict[str, tuple[float | None, str | None]] | None],
    base_url: str,
    topic: str,
    vehicle: str,
    limit: int,
) -> tuple[float | None, str | None]:
    """Returns (final_score, source_tag) — (None, None) if vehicle absent.

    Caches per-topic suggestion lookups within a cell evaluation so repeated topics
    cost a single HTTP round-trip. MUNCH apt has ~10k pairs over ~1.7k unique topics,
    so this is a ~6x reduction in API requests per cell.
    """
    if topic not in cache:
        cache[topic] = fetch_suggestions(base_url, topic, limit)
    suggestions = cache[topic]
    if suggestions is None:
        return None, None
    if vehicle in suggestions:
        return suggestions[vehicle]
    return None, None


def evaluate_cell(
    name: str,
    candidate_sources: str,
    d_min: float | None,
    d_max: float | None,
    top_k: int | None,
    gamma: float | None,
    binary: str,
    db: Path,
    port: int,
    apt_pairs: list[tuple[str, str]],
    inapt_pairs: list[tuple[str, str]],
    limit: int,
) -> CellResult:
    env = {"METAFORGE_FORGE_CANDIDATES": candidate_sources}
    if d_min is not None:
        env["METAFORGE_FORGE_EMB_DMIN"] = str(d_min)
    if d_max is not None:
        env["METAFORGE_FORGE_EMB_DMAX"] = str(d_max)
    if top_k is not None:
        env["METAFORGE_FORGE_EMB_TOPK"] = str(top_k)
    if gamma is not None:
        env["METAFORGE_FORGE_GAMMA"] = str(gamma)

    result = CellResult(name=name, candidate_sources=candidate_sources,
                        d_min=d_min, d_max=d_max, top_k=top_k, gamma=gamma)
    proc = start_api(binary, db, port, env)
    try:
        base_url = f"http://127.0.0.1:{port}"
        # Per-topic cache: /forge/suggest output depends only on topic+env, so
        # we hit the API once per unique topic per cell (env is fixed for the
        # cell's lifetime).
        cache: dict[str, dict[str, tuple[float | None, str | None]] | None] = {}
        for topic, vehicle in apt_pairs:
            fs, src = score_pair_cached(cache, base_url, topic, vehicle, limit)
            if fs is None:
                result.apt_missing += 1
                continue
            result.apt_scores.append(fs)
            if src in result.source_mix:
                result.source_mix[src] += 1
        for topic, vehicle in inapt_pairs:
            fs, _ = score_pair_cached(cache, base_url, topic, vehicle, limit)
            if fs is None:
                result.inapt_missing += 1
                continue
            result.inapt_scores.append(fs)
    finally:
        stop_api(proc)
    # Snapshot derived metrics onto the dataclass fields so downstream
    # asdict() serialisation includes them in the JSON output.
    result.finalise_metrics()
    return result


def write_verdict(
    results: list[CellResult],
    baseline: CellResult,
    verdict_path: Path,
    cfg: dict | None = None,
) -> None:
    """Emit the verdict markdown for a sweep run.

    Title and tail-section content are parametrised by the sweep config so the
    runner can be reused across milestones. ``cfg`` keys honoured:

    * ``name`` — sweep identifier (used as default title prefix)
    * ``verdict_title`` — optional explicit title (overrides ``name``)
    * ``axis`` — when ``"embedding-band"`` the original M04 "ratify SourcesUnion"
      recommendation and "Two-Path Correlation" section are emitted. Any other
      value (or omission) yields a neutral best-cell summary suitable for
      gamma sweeps and similar axis-agnostic studies.

    Backwards-compatible: omitting ``cfg`` falls back to the legacy M04
    Embedding-Band title and tail sections.
    """
    cfg = cfg or {}
    name = cfg.get("name")
    verdict_title = cfg.get("verdict_title")
    axis = cfg.get("axis")

    if verdict_title:
        title = f"# {verdict_title} Verdict"
    elif name:
        title = f"# {name} Verdict"
    else:
        # Legacy fallback — preserves behaviour for any caller that hasn't
        # been migrated to pass cfg through. New callers should always pass cfg.
        title = "# M04 Embedding-Band Calibration Verdict"
        axis = axis or "embedding-band"

    best = max(results, key=lambda r: r.separation_score)
    lines = [
        title,
        "",
        f"_Baseline ({baseline.candidate_sources}): separation_score = {baseline.separation_score:.4f}, "
        f"aptness_rate = {baseline.aptness_rate:.4f}_",
        "",
        "## Results Grid",
        "",
        "| Cell | d_min | d_max | gamma | separation_score | aptness_rate | cluster | embedding | both | apt_miss | inapt_miss |",
        "|------|------:|------:|------:|-----------------:|-------------:|--------:|----------:|-----:|---------:|-----------:|",
    ]
    for r in sorted(results, key=lambda r: -r.separation_score):
        lines.append(
            f"| {r.name} | {r.d_min} | {r.d_max} | {r.gamma} | {r.separation_score:.4f} | "
            f"{r.aptness_rate:.4f} | {r.source_mix['cluster']} | "
            f"{r.source_mix['embedding']} | {r.source_mix['both']} | "
            f"{r.apt_missing} | {r.inapt_missing} |"
        )

    lines += [
        "",
        f"## Best Cell: `{best.name}`",
        f"- d_min = {best.d_min}, d_max = {best.d_max}, gamma = {best.gamma}",
        f"- separation_score = **{best.separation_score:.4f}**",
        f"- aptness_rate = {best.aptness_rate:.4f}",
    ]

    if axis == "embedding-band":
        # M04-specific framing: the sweep's purpose is to ratify the
        # SourcesUnion default with a non-regressive embedding band.
        lines.append(
            f"- vs baseline ({baseline.separation_score:.4f}): "
            + ("**non-regressive — ratify** `SourcesUnion` as default with this band"
               if best.separation_score >= baseline.separation_score
               else "**regression — keep `SourcesCluster` default**, document follow-up sweep")
        )
        lines += [
            "",
            "## Two-Path Correlation (v2 β-bonus signal)",
            "",
            "Per cell, the `both` column counts apt pairs that were generated by BOTH the cluster",
            "and embedding paths. A high both-count under high aptness suggests two-path agreement",
            "correlates with aptness — i.e. a co-generation bonus β·1{both} may be worth adding in",
            "M04 v2. A low both-count under high aptness means the embedding path is the marginal",
            "contributor and a β-bonus would not help.",
        ]
    else:
        # Axis-agnostic framing: report best cell's delta vs baseline neutrally,
        # without naming any code default. Suitable for γ-sweeps and any future
        # sweep whose axis doesn't map to a SourcesUnion ratification decision.
        delta = best.separation_score - baseline.separation_score
        verdict_word = "non-regressive" if delta >= 0 else "regression"
        lines.append(
            f"- vs baseline ({baseline.separation_score:.4f}): "
            f"Δ separation_score = {delta:+.4f} ({verdict_word})"
        )

    verdict_path.write_text("\n".join(lines) + "\n")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--config", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--verdict", type=Path, required=True)
    args = p.parse_args(argv)

    cfg = yaml.safe_load(args.config.read_text())
    db = Path(cfg["db"])
    binary = cfg["api_binary"]
    if not Path(binary).exists():
        print(f"API binary not found at {binary} — build with:\n"
              f"  cd api && go build -o ../{binary} ./cmd/metaforge", file=sys.stderr)
        return 2

    apt_pairs = load_pairs(Path(cfg["pairs"]))
    inapt_pairs = load_pairs(Path(cfg["controls"]))
    limit = int(cfg.get("limit", 50))
    port_base = int(cfg.get("api_port_base", 9100))

    # Optional deterministic subsample — keeps each cell's wall-clock
    # under the calibration budget. Subsampling preserves per-topic
    # variance because we sample full topic→vehicle pairs (not topics);
    # the verdict markdown records the effective n.
    sample_apt = cfg.get("sample_apt")
    sample_inapt = cfg.get("sample_inapt")
    seed = int(cfg.get("sample_seed", 17))
    if sample_apt is not None and sample_apt < len(apt_pairs):
        rng = random.Random(seed)
        apt_pairs = rng.sample(apt_pairs, int(sample_apt))
    if sample_inapt is not None and sample_inapt < len(inapt_pairs):
        rng = random.Random(seed + 1)
        inapt_pairs = rng.sample(inapt_pairs, int(sample_inapt))
    print(f"Cohort: apt={len(apt_pairs)} pairs, inapt={len(inapt_pairs)} pairs", flush=True)

    baseline_cfg = cfg["baseline"]
    baseline = evaluate_cell(
        "baseline_cluster_only",
        candidate_sources=baseline_cfg["candidate_sources"],
        d_min=None, d_max=None, top_k=None, gamma=None,
        binary=binary, db=db, port=port_base,
        apt_pairs=apt_pairs, inapt_pairs=inapt_pairs, limit=limit,
    )

    results: list[CellResult] = []
    for i, var in enumerate(cfg["variations"], start=1):
        port = port_base + i
        r = evaluate_cell(
            name=var["name"],
            candidate_sources=var["candidate_sources"],
            d_min=var.get("d_min"),
            d_max=var.get("d_max"),
            top_k=var.get("top_k"),
            gamma=var.get("gamma"),
            binary=binary, db=db, port=port,
            apt_pairs=apt_pairs, inapt_pairs=inapt_pairs, limit=limit,
        )
        results.append(r)
        print(f"  {r.name}: sep={r.separation_score:.4f} apt_rate={r.aptness_rate:.4f}")

    args.output.write_text(json.dumps({
        "baseline": baseline.to_dict(),
        "results": [r.to_dict() for r in results],
    }, indent=2))
    write_verdict(results, baseline, args.verdict, cfg=cfg)
    print(f"\nWrote {args.output} and {args.verdict}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
