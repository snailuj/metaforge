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
    """asdict() must include the derived metrics so the JSON output is
    auditable without recomputing from the raw score lists.

    The dataclass fields are underscore-prefixed (`_aptness_rate`,
    `_separation_score`) because the public attributes are @property
    accessors. ``dataclasses.asdict`` serialises the stored fields, so the
    JSON keys carry the underscore prefix — finalise_metrics() must run
    first to snapshot the values.
    """
    import dataclasses

    cell = _make_cell("test", apt=[0.5, 0.6, 0.7], inapt=[0.1, 0.2, 0.3, 0.4])
    # Mimic the runner's finalisation step.
    cell.finalise_metrics()

    dumped = dataclasses.asdict(cell)
    assert "_aptness_rate" in dumped, "_aptness_rate missing from JSON dump"
    assert "_separation_score" in dumped, "_separation_score missing from JSON dump"
    assert isinstance(dumped["_aptness_rate"], float)
    assert isinstance(dumped["_separation_score"], float)
    # Sanity — separation = mean(apt) - mean(inapt) = 0.6 - 0.25 = 0.35
    assert dumped["_separation_score"] == pytest.approx(0.35, abs=1e-9)


def test_cell_result_property_accessors_still_work() -> None:
    """@property accessors should remain available as a convenience layer,
    delegating to stored field when present (or recomputing if not)."""
    cell = _make_cell("test", apt=[0.5, 0.6], inapt=[0.1, 0.2])
    # Before finalise — properties recompute on the fly.
    assert cell.separation_score == pytest.approx(0.4, abs=1e-9)
    cell.finalise_metrics()
    # After finalise — same value (idempotent).
    assert cell.separation_score == pytest.approx(0.4, abs=1e-9)


def test_cell_result_to_dict_uses_public_key_names() -> None:
    """to_dict() must emit the historical public JSON keys (aptness_rate,
    separation_score) rather than the underscore-prefixed dataclass fields.

    The R2 refactor (commit 16692031) replaced a __getattribute__ override
    with @property accessors and underscore-prefixed backing fields. As a
    side-effect, dataclasses.asdict() began serialising the underscore
    names — silently breaking wire compat with historical sweep-result
    JSONs. to_dict() restores the public-name contract and finalises
    metrics so callers don't have to remember.
    """
    cell = _make_cell("test", apt=[0.5, 0.6, 0.7], inapt=[0.1, 0.2, 0.3, 0.4])

    d = cell.to_dict()

    assert "aptness_rate" in d, "public key 'aptness_rate' missing from to_dict()"
    assert "separation_score" in d, "public key 'separation_score' missing from to_dict()"
    assert "_aptness_rate" not in d, "underscore-prefixed key leaked into to_dict()"
    assert "_separation_score" not in d, "underscore-prefixed key leaked into to_dict()"
    # Sanity — separation = mean(apt) - mean(inapt) = 0.6 - 0.25 = 0.35
    assert d["separation_score"] == pytest.approx(0.35, abs=1e-9)
    assert isinstance(d["aptness_rate"], float)


def test_cell_result_property_accessor_recomputes_when_unfinalised() -> None:
    """The @property accessor for aptness_rate / separation_score must
    recompute on the fly when the backing stored field is None — this
    guarantees ergonomic ad-hoc use (tests, REPL) without forcing
    callers to remember finalise_metrics. After finalise_metrics() runs,
    the stored field must be populated (no longer None) and the property
    must return the stored value verbatim.

    This pins the @property-based implementation that replaces the old
    __getattribute__ override: a CellResult must NOT have __getattribute__
    intercepting attribute reads — that's heavyweight and non-idiomatic.
    """
    cell = _make_cell("test", apt=[0.5, 0.6, 0.7], inapt=[0.1, 0.2, 0.3, 0.4])

    # Pre-finalise: the dataclass field is None, but the property recomputes.
    assert cell._aptness_rate is None
    assert cell._separation_score is None
    # mean(apt) - mean(inapt) = 0.6 - 0.25 = 0.35
    assert cell.separation_score == pytest.approx(0.35, abs=1e-9)
    # 95th percentile of inapt has insufficient data (n=4 < required) so
    # _compute_aptness_rate hits the n<2 guard? Actually n=4 is fine for
    # quantiles(n=20) but only when there are >=2 points. Just assert it
    # returns a float without crashing.
    rate = cell.aptness_rate
    assert isinstance(rate, float)

    # Post-finalise: stored fields populated and property returns stored value.
    cell.finalise_metrics()
    assert cell._aptness_rate is not None
    assert cell._separation_score is not None
    assert cell.separation_score == pytest.approx(0.35, abs=1e-9)

    # Regression guard: the old __getattribute__ override must be gone.
    # A @property-based implementation leaves CellResult with object's
    # default __getattribute__ (not overridden on the class itself).
    assert "__getattribute__" not in CellResult.__dict__, (
        "CellResult should not override __getattribute__ — use @property instead"
    )
