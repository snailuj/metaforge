# test_m04_sweep_runner.py
"""Tests for m04_sweep_runner.py — verdict title parametrisation
and CellResult JSON serialisation of derived metrics.
"""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))

from m04_sweep_runner import CellResult, write_verdict


def _make_cell(name: str, apt: list[float], inapt: list[float], **kw) -> CellResult:
    """Helper — build a CellResult with synthetic apt/inapt score lists."""
    return CellResult(
        name=name,
        candidate_sources=kw.get("candidate_sources", "union"),
        d_min=kw.get("d_min"),
        d_max=kw.get("d_max"),
        top_k=kw.get("top_k"),
        gamma=kw.get("gamma"),
        apt_scores=apt,
        inapt_scores=inapt,
    )


def test_write_verdict_title_parametrised(tmp_path: Path) -> None:
    """Verdict title must be derived from the sweep config's name, not a
    hardcoded "M04 Embedding-Band" string. This protects the M05 (γ-sweep)
    and other future sweeps from inheriting M04-specific labels."""
    out = tmp_path / "verdict.md"
    baseline = _make_cell("baseline_cluster_only", apt=[0.3, 0.4], inapt=[0.1, 0.2])
    cells = [_make_cell("gamma1.00_dmax0.85", apt=[0.5, 0.6], inapt=[0.1, 0.2], gamma=1.0)]

    write_verdict(cells, baseline, out, cfg={"name": "m99_test"})

    body = out.read_text()
    assert body.startswith("# m99_test"), f"verdict title not parametrised: {body[:80]!r}"
    assert "M04 Embedding-Band" not in body, "M04-specific title leaked into m99 verdict"


def test_write_verdict_omits_m04_specific_sections_for_non_m04(tmp_path: Path) -> None:
    """The "ratify SourcesUnion" recommendation and the "Two-Path Correlation"
    block are M04-specific. For a γ-axis sweep (no d_min/d_max variation in
    the conceptual axis) they must be replaced with neutral wording."""
    out = tmp_path / "verdict.md"
    baseline = _make_cell("baseline", apt=[0.3], inapt=[0.1, 0.2])
    cells = [_make_cell("gamma1.00", apt=[0.5, 0.6], inapt=[0.1, 0.2], gamma=1.0)]

    write_verdict(cells, baseline, out, cfg={"name": "m05_lakoff_gamma", "axis": "gamma"})

    body = out.read_text()
    assert "ratify" not in body.lower(), "M04 ratify recommendation leaked into γ-sweep verdict"
    assert "Two-Path Correlation" not in body, "M04 two-path section leaked into γ-sweep verdict"


def test_write_verdict_preserves_m04_sections_when_axis_is_embedding_band(tmp_path: Path) -> None:
    """M04 sweeps explicitly tagged as the embedding-band axis must keep
    the original ratify / two-path wording for backwards compatibility."""
    out = tmp_path / "verdict.md"
    baseline = _make_cell("baseline", apt=[0.3], inapt=[0.1, 0.2])
    cells = [_make_cell("dmin0.4_dmax0.85", apt=[0.5, 0.6], inapt=[0.1, 0.2],
                        d_min=0.4, d_max=0.85)]

    write_verdict(cells, baseline, out,
                  cfg={"name": "m04_embedding_band", "axis": "embedding-band"})

    body = out.read_text()
    assert "Two-Path Correlation" in body
    assert "ratify" in body.lower() or "regression" in body.lower()


def test_cell_result_serialises_aptness_rate_and_separation_score() -> None:
    """asdict() must include aptness_rate and separation_score so the JSON
    output is auditable without recomputing from the raw score lists."""
    import dataclasses

    cell = _make_cell("test", apt=[0.5, 0.6, 0.7], inapt=[0.1, 0.2, 0.3, 0.4])
    # Mimic the runner's finalisation step.
    cell.finalise_metrics()

    dumped = dataclasses.asdict(cell)
    assert "aptness_rate" in dumped, "aptness_rate missing from JSON dump"
    assert "separation_score" in dumped, "separation_score missing from JSON dump"
    assert isinstance(dumped["aptness_rate"], float)
    assert isinstance(dumped["separation_score"], float)
    # Sanity — separation = mean(apt) - mean(inapt) = 0.6 - 0.25 = 0.35
    assert dumped["separation_score"] == pytest.approx(0.35, abs=1e-9)


def test_cell_result_property_accessors_still_work() -> None:
    """@property accessors should remain available as a convenience layer,
    delegating to stored field when present (or recomputing if not)."""
    cell = _make_cell("test", apt=[0.5, 0.6], inapt=[0.1, 0.2])
    # Before finalise — properties recompute on the fly.
    assert cell.separation_score == pytest.approx(0.4, abs=1e-9)
    cell.finalise_metrics()
    # After finalise — same value (idempotent).
    assert cell.separation_score == pytest.approx(0.4, abs=1e-9)
