import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from calibration_drift_check import compute_flip_rate, drift_verdict

def test_flip_rate_zero_when_all_match():
    originals = [
        {"chain_signature": "a", "label": "live"},
        {"chain_signature": "b", "label": "bad_path"},
    ]
    regrades = [
        {"chain_signature": "a", "label": "live"},
        {"chain_signature": "b", "label": "bad_path"},
    ]
    r = compute_flip_rate(originals, regrades)
    assert r["n"] == 2
    assert r["flips"] == 0
    assert r["rate"] == 0.0

def test_flip_rate_one_third_when_one_of_three_flips():
    originals = [{"chain_signature": s, "label": "live"} for s in "abc"]
    regrades = [
        {"chain_signature": "a", "label": "live"},
        {"chain_signature": "b", "label": "live"},
        {"chain_signature": "c", "label": "dead"},  # flipped
    ]
    r = compute_flip_rate(originals, regrades)
    assert r["n"] == 3
    assert r["flips"] == 1
    assert abs(r["rate"] - 1/3) < 0.001

def test_flip_rate_ignores_regrades_with_no_original():
    originals = [{"chain_signature": "a", "label": "live"}]
    regrades = [{"chain_signature": "b", "label": "dead"}]  # not in originals
    r = compute_flip_rate(originals, regrades)
    assert r["n"] == 0

def test_flip_rate_empty_returns_zero_rate():
    r = compute_flip_rate([], [])
    assert r["rate"] == 0.0

def test_drift_verdict_below_threshold_ok():
    v = drift_verdict({"n": 10, "flips": 2, "rate": 0.2}, threshold=0.30)
    assert v["status"] == "OK"

def test_drift_verdict_at_threshold_flags():
    v = drift_verdict({"n": 10, "flips": 3, "rate": 0.3}, threshold=0.30)
    assert v["status"] == "DRIFT"

def test_drift_verdict_above_threshold_flags():
    v = drift_verdict({"n": 10, "flips": 5, "rate": 0.5}, threshold=0.30)
    assert v["status"] == "DRIFT"

def test_drift_verdict_insufficient_when_n_lt_5():
    v = drift_verdict({"n": 3, "flips": 1, "rate": 0.333}, threshold=0.30)
    assert v["status"] == "INSUFFICIENT"
