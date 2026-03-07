"""Tests for audit_physical_coverage.py."""

import json
import sys
import pytest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from audit_physical_coverage import audit_physical_coverage, POS_THRESHOLDS


# --- Fixtures ---

def make_synset(sid, pos, physical_count, total=10):
    """Build a synset dict with N physical properties + padding."""
    props = [{"text": f"phys{i}", "salience": 0.8, "type": "physical",
              "relation": f"has phys{i}"} for i in range(physical_count)]
    props += [{"text": f"social{i}", "salience": 0.5, "type": "social",
               "relation": f"has social{i}"} for i in range(total - physical_count)]
    return {"id": sid, "lemma": "test", "definition": "test def",
            "pos": pos, "properties": props}


def make_checkpoint(synsets):
    """Build a checkpoint-format dict."""
    return {"completed_ids": [s["id"] for s in synsets], "results": synsets}


def make_enrichment(synsets):
    """Build an enrichment-format dict."""
    return {"synsets": synsets}


class TestPosThresholds:
    def test_noun_threshold_is_4(self):
        assert POS_THRESHOLDS["n"] == 4

    def test_verb_threshold_is_2(self):
        assert POS_THRESHOLDS["v"] == 2

    def test_adj_threshold_is_2(self):
        assert POS_THRESHOLDS["a"] == 2
        assert POS_THRESHOLDS["s"] == 2


class TestAuditPhysicalCoverage:
    def test_noun_below_threshold_flagged(self):
        synsets = [make_synset("s1", "n", 2)]
        result = audit_physical_coverage(make_enrichment(synsets))
        assert "s1" in result["flagged_ids"]

    def test_noun_at_threshold_not_flagged(self):
        synsets = [make_synset("s1", "n", 4)]
        result = audit_physical_coverage(make_enrichment(synsets))
        assert "s1" not in result["flagged_ids"]

    def test_verb_below_threshold_flagged(self):
        synsets = [make_synset("s1", "v", 1)]
        result = audit_physical_coverage(make_enrichment(synsets))
        assert "s1" in result["flagged_ids"]

    def test_verb_at_threshold_not_flagged(self):
        synsets = [make_synset("s1", "v", 2)]
        result = audit_physical_coverage(make_enrichment(synsets))
        assert "s1" not in result["flagged_ids"]

    def test_adj_below_threshold_flagged(self):
        synsets = [make_synset("s1", "s", 1)]
        result = audit_physical_coverage(make_enrichment(synsets))
        assert "s1" in result["flagged_ids"]

    def test_mixed_pos_flags_correctly(self):
        synsets = [
            make_synset("n1", "n", 2),  # flagged
            make_synset("n2", "n", 5),  # ok
            make_synset("v1", "v", 0),  # flagged
            make_synset("v2", "v", 3),  # ok
        ]
        result = audit_physical_coverage(make_enrichment(synsets))
        assert set(result["flagged_ids"]) == {"n1", "v1"}

    def test_summary_stats(self):
        synsets = [
            make_synset("n1", "n", 2),
            make_synset("n2", "n", 5),
            make_synset("v1", "v", 0),
        ]
        result = audit_physical_coverage(make_enrichment(synsets))
        assert result["total_synsets"] == 3
        assert result["flagged_count"] == 2

    def test_exclude_ids(self):
        synsets = [
            make_synset("n1", "n", 2),
            make_synset("n2", "n", 1),
        ]
        result = audit_physical_coverage(make_enrichment(synsets), exclude_ids={"n1"})
        assert result["flagged_ids"] == ["n2"]

    def test_checkpoint_format(self):
        """Audit reads checkpoint format (results key) as well as enrichment format."""
        synsets = [make_synset("s1", "n", 1)]
        result = audit_physical_coverage(make_checkpoint(synsets))
        assert "s1" in result["flagged_ids"]

    def test_empty_input(self):
        result = audit_physical_coverage({"synsets": []})
        assert result["flagged_ids"] == []
        assert result["total_synsets"] == 0

    def test_pos_breakdown(self):
        synsets = [
            make_synset("n1", "n", 1),
            make_synset("n2", "n", 2),
            make_synset("v1", "v", 0),
        ]
        result = audit_physical_coverage(make_enrichment(synsets))
        assert result["pos_breakdown"]["n"]["flagged"] == 2
        assert result["pos_breakdown"]["v"]["flagged"] == 1
