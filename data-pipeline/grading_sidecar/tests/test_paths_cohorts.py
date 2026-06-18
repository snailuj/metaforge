"""Cohort config + env-indirected data location."""
from __future__ import annotations
import importlib
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))


def _reload_paths():
    from grading_sidecar import paths as p
    return importlib.reload(p)


def test_cohort_constants_and_membership():
    p = _reload_paths()
    assert p.GRADING_COHORTS == ["spike", "curated"]          # grading views: no stock
    assert p.SENSECHECK_COHORTS == ["spike", "curated", "stock"]
    # stock globs point under the stock/ subdir; spike/curated match new + legacy names
    assert any("stock/" in g for g in p.CHAIN_COHORTS["stock"])
    assert "chain-topics_spike*.jsonl" in p.CHAIN_COHORTS["spike"]
    assert any("sonnet_chains_provisional_r1" in g for g in p.CHAIN_COHORTS["spike"])  # legacy
    assert "chain-topics_curated*.jsonl" in p.CHAIN_COHORTS["curated"]


def test_data_dir_defaults_in_repo_but_is_env_overridable(monkeypatch, tmp_path):
    p = _reload_paths()
    assert p.GRADING_DIR == p.REPO_ROOT / "data-pipeline" / "grading"   # default unchanged
    assert p.GRADING_DATA_GIT_ROOT == str(p.REPO_ROOT)
    monkeypatch.setenv("GRADING_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("GRADING_DATA_GIT_ROOT", str(tmp_path / "gitroot"))
    p2 = _reload_paths()
    assert p2.GRADING_DIR == tmp_path / "data"
    assert p2.GRADING_DATA_GIT_ROOT == str(tmp_path / "gitroot")
    monkeypatch.delenv("GRADING_DATA_DIR"); monkeypatch.delenv("GRADING_DATA_GIT_ROOT")
    _reload_paths()  # restore module global for other tests
