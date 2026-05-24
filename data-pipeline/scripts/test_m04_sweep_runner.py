# test_m04_sweep_runner.py
"""Tests for m04_sweep_runner.py — verdict title parametrisation
and CellResult JSON serialisation of derived metrics.
"""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))

from m04_sweep_runner import (
    CellResult,
    _attribute_drop,
    fetch_suggestions,
    load_preflight,
    write_verdict,
)


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


# ---- fetch_suggestions: silent-failure pinning -----------------------------
#
# R4 standards finding: fetch_suggestions used to return None on
# RequestException, non-200 status, or JSON-decode error WITHOUT logging
# anything. Operator could not distinguish a real cohort gap from a
# network blip / 5xx / timeout. The fix emits a stderr WARN per failure
# path. These tests pin the warnings exist and the None-return contract
# is preserved (callers still rely on it).


class _FakeResp:
    def __init__(self, status_code: int, payload=None, text: str = "") -> None:
        self.status_code = status_code
        self._payload = payload
        self.text = text or (json.dumps(payload) if payload is not None else "")

    def json(self):
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload


def test_fetch_suggestions_request_exception_logs_and_returns_none(monkeypatch, capsys):
    import requests as _requests

    def boom(*_a, **_kw):
        raise _requests.ConnectionError("connection refused")

    monkeypatch.setattr("m04_sweep_runner.requests.get", boom)
    result = fetch_suggestions("http://localhost:0", topic="anger", limit=10)
    assert result is None
    err = capsys.readouterr().err
    assert "fetch_suggestions" in err
    assert "anger" in err
    assert "ConnectionError" in err


def test_fetch_suggestions_non_200_logs_status_and_body(monkeypatch, capsys):
    monkeypatch.setattr(
        "m04_sweep_runner.requests.get",
        lambda *a, **kw: _FakeResp(503, text="upstream busy"),
    )
    result = fetch_suggestions("http://localhost:0", topic="idea", limit=10)
    assert result is None
    err = capsys.readouterr().err
    assert "fetch_suggestions" in err
    assert "idea" in err
    assert "503" in err
    assert "upstream busy" in err


def test_fetch_suggestions_non_json_body_logs_and_returns_none(monkeypatch, capsys):
    monkeypatch.setattr(
        "m04_sweep_runner.requests.get",
        lambda *a, **kw: _FakeResp(200, payload=ValueError("not json"), text="<html/>"),
    )
    result = fetch_suggestions("http://localhost:0", topic="time", limit=10)
    assert result is None
    err = capsys.readouterr().err
    assert "fetch_suggestions" in err
    assert "time" in err
    assert "non-JSON" in err


def test_fetch_suggestions_happy_path_does_not_log(monkeypatch, capsys):
    """Sanity: success path stays quiet (no false-positive WARN spam)."""
    monkeypatch.setattr(
        "m04_sweep_runner.requests.get",
        lambda *a, **kw: _FakeResp(
            200,
            payload={"suggestions": [{"word": "fire", "final_score": 0.42, "candidate_source": "cluster"}]},
        ),
    )
    result = fetch_suggestions("http://localhost:0", topic="anger", limit=10)
    assert result == {"fire": (0.42, "cluster")}
    err = capsys.readouterr().err
    assert "WARN" not in err


# ---- Phase 2: pre-flight drop attribution ---------------------------------
#
# CellResult now carries apt_drop_buckets / inapt_drop_buckets. Each post-API
# drop is attributed to either a pre-flight bucket (from the diagnostics JSON)
# or to api_filtered_or_no_overlap (pre-flight clean but API still didn't
# return the vehicle — the real gate-level signal).


def test_attribute_drop_returns_api_filtered_when_no_preflight():
    """Without a pre-flight ledger every drop is attributed to the
    api_filtered bucket (legacy/no-diagnostics callers preserve the
    "all drops are unknown" interpretation)."""
    assert _attribute_drop("anger", "fire", None) == "api_filtered_or_no_overlap"


def test_attribute_drop_returns_api_filtered_for_preflight_clean():
    preflight = {("anger", "fire"): "preflight_clean"}
    assert _attribute_drop("anger", "fire", preflight) == "api_filtered_or_no_overlap"


def test_attribute_drop_returns_api_filtered_for_unknown_pair():
    """A pair not in the ledger is treated as preflight_clean — graceful
    degradation when the diagnostics file was generated against a different
    cohort revision than the sweep run."""
    preflight = {("anger", "fire"): "preflight_clean"}
    assert _attribute_drop("idea", "light", preflight) == "api_filtered_or_no_overlap"


def test_attribute_drop_returns_named_bucket_for_blocked_pair():
    preflight = {
        ("foo", "bar"): "pre_vehicle_no_concreteness",
        ("foo", "baz"): "pre_topic_no_lemma",
    }
    assert _attribute_drop("foo", "bar", preflight) == "pre_vehicle_no_concreteness"
    assert _attribute_drop("foo", "baz", preflight) == "pre_topic_no_lemma"


def test_load_preflight_round_trips_pair_diagnostics(tmp_path: Path):
    payload = {
        "db": "test.db",
        "apt": {
            "n_pairs": 2,
            "attribution_histogram": {"preflight_clean": 1, "pre_vehicle_no_lemma": 1},
            "pair_diagnostics": [
                {"topic": "anger", "vehicle": "fire", "topic_bucket": "clean", "vehicle_bucket": "clean", "attribution": "preflight_clean"},
                {"topic": "anger", "vehicle": "nonsense", "topic_bucket": "clean", "vehicle_bucket": "vehicle_no_lemma", "attribution": "pre_vehicle_no_lemma"},
            ],
        },
        "inapt": {
            "n_pairs": 1,
            "attribution_histogram": {"preflight_clean": 1},
            "pair_diagnostics": [
                {"topic": "anger", "vehicle": "doormat", "topic_bucket": "clean", "vehicle_bucket": "clean", "attribution": "preflight_clean"},
            ],
        },
    }
    p = tmp_path / "diag.json"
    p.write_text(json.dumps(payload))
    pre = load_preflight(p)
    assert pre["apt"][("anger", "fire")] == "preflight_clean"
    assert pre["apt"][("anger", "nonsense")] == "pre_vehicle_no_lemma"
    assert pre["inapt"][("anger", "doormat")] == "preflight_clean"


def test_write_verdict_emits_drop_attribution_when_buckets_present(tmp_path: Path):
    """When any cell has drop buckets, the verdict gains a Drop Attribution
    section with two tables (apt + inapt) and api_filtered_or_no_overlap
    pinned as the first bucket column."""
    out = tmp_path / "verdict.md"
    baseline = _make_cell("baseline", apt=[0.3], inapt=[0.1, 0.2])
    cell = _make_cell("gamma1.0", apt=[0.5], inapt=[0.1, 0.2], gamma=1.0)
    cell.apt_drop_buckets = {"api_filtered_or_no_overlap": 5, "pre_vehicle_no_lemma": 2}
    cell.inapt_drop_buckets = {"api_filtered_or_no_overlap": 88}

    write_verdict([cell], baseline, out, cfg={"name": "m05_test"})
    body = out.read_text()
    assert "## Drop Attribution (per-cause breakdown)" in body
    # api_filtered comes first in the column order
    assert body.index("apt:api_filtered_or_no_overlap") < body.index("apt:pre_vehicle_no_lemma")
    # Numbers surface verbatim
    assert "| 5 |" in body or "| 5 " in body
    assert "| 88 |" in body or "| 88 " in body


def test_write_verdict_omits_drop_attribution_when_no_buckets(tmp_path: Path):
    """Legacy/no-diagnostics callers must produce a verdict without the
    new section so cross-run diffs against pre-Phase-2 sweeps stay clean."""
    out = tmp_path / "verdict.md"
    baseline = _make_cell("baseline", apt=[0.3], inapt=[0.1, 0.2])
    cell = _make_cell("gamma1.0", apt=[0.5], inapt=[0.1, 0.2], gamma=1.0)
    write_verdict([cell], baseline, out, cfg={"name": "m05_test"})
    body = out.read_text()
    assert "## Drop Attribution" not in body
