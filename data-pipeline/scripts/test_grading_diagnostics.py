import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from grading_diagnostics import wilson_ci, ci_overlap, convergence_verdict

def test_wilson_ci_known_values():
    # 6/20 → ~[0.146, 0.519]
    lo, hi = wilson_ci(6, 20, alpha=0.05)
    assert 0.13 < lo < 0.16
    assert 0.50 < hi < 0.53

def test_wilson_ci_edge_zero():
    lo, hi = wilson_ci(0, 20)
    assert lo == 0.0
    assert 0.0 < hi < 0.2

def test_wilson_ci_edge_n_equals_k():
    lo, hi = wilson_ci(20, 20)
    assert hi == 1.0
    assert lo > 0.8

def test_wilson_ci_n_zero():
    lo, hi = wilson_ci(0, 0)
    assert lo == 0.0 and hi == 0.0

def test_ci_overlap_overlapping():
    assert ci_overlap((0.15, 0.52), (0.08, 0.42)) is True

def test_ci_overlap_separate():
    # (0.30, 0.52) and (0.01, 0.24) — separate
    assert ci_overlap((0.30, 0.52), (0.01, 0.24)) is False

def test_convergence_verdict_down_when_ci_separates():
    # At n=20, Wilson CIs for 6→4→1 all overlap — not statistically separated.
    # Use 12→7→0 which produces non-overlapping CIs (last CI entirely below prev).
    rounds = [
        {"round": 1, "bad_path": 12, "total": 20},
        {"round": 2, "bad_path": 7, "total": 20},
        {"round": 3, "bad_path": 0, "total": 20},
    ]
    v = convergence_verdict(rounds)
    assert v["status"] == "DOWN"

def test_convergence_verdict_flat_when_cis_overlap():
    rounds = [{"round": i+1, "bad_path": 5, "total": 20} for i in range(3)]
    v = convergence_verdict(rounds)
    assert v["status"] == "FLAT"

def test_convergence_verdict_ceiling_at_8_rounds():
    rounds = [{"round": i+1, "bad_path": 5, "total": 20} for i in range(8)]
    v = convergence_verdict(rounds)
    assert v["status"] == "CEILING"

def test_convergence_verdict_insufficient_with_one_round():
    rounds = [{"round": 1, "bad_path": 5, "total": 20}]
    v = convergence_verdict(rounds)
    assert v["status"] == "INSUFFICIENT"
