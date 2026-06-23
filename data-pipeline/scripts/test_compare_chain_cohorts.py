"""Tests for compare_chain_cohorts — pure-function coverage.

Compares an OLD chain cohort against a NEW one (same topics, same Haiku
candidates, different generation prompt) so the editor can eyeball whether a
prompt change actually shifted path structure. No LLM calls here.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from compare_chain_cohorts import (
    extract_phrases,
    index_chains,
    compare,
    render_markdown,
)


def test_extract_phrases_from_dict_steps():
    chain = [{"phrase": "anger", "head": "anger"}, {"phrase": "burning rage", "head": "rage"}]
    assert extract_phrases(chain) == ["anger", "burning rage"]


def test_extract_phrases_passes_through_bare_strings():
    assert extract_phrases(["anger", "fire"]) == ["anger", "fire"]


def test_index_chains_grouped_format():
    # New Sonnet output: one record per topic, with a "vehicles" list.
    records = [{
        "topic": "anger",
        "vehicles": [
            {"vehicle": "fire", "chain": [{"phrase": "anger"}, {"phrase": "heat"}, {"phrase": "fire"}]},
            {"vehicle": "storm", "chain": [{"phrase": "anger"}, {"phrase": "storm"}]},
        ],
    }]
    idx = index_chains(records)
    assert idx[("anger", "fire")] == ["anger", "heat", "fire"]
    assert idx[("anger", "storm")] == ["anger", "storm"]


def test_index_chains_flattened_format():
    # Committed round-1 cohort: one record per (topic, vehicle).
    records = [
        {"topic": "anger", "vehicle": "fire",
         "chain": [{"phrase": "anger"}, {"phrase": "spark"}, {"phrase": "fire"}]},
        {"topic": "anger", "vehicle": "volcano",
         "chain": [{"phrase": "anger"}, {"phrase": "pressure"}, {"phrase": "volcano"}]},
    ]
    idx = index_chains(records)
    assert idx[("anger", "fire")] == ["anger", "spark", "fire"]
    assert idx[("anger", "volcano")] == ["anger", "pressure", "volcano"]


def test_compare_partitions_common_and_only():
    old = {("anger", "fire"): ["anger", "spark", "fire"],
           ("anger", "ice"): ["anger", "ice"]}
    new = {("anger", "fire"): ["anger", "heat", "blaze", "fire"],
           ("anger", "storm"): ["anger", "storm"]}
    c = compare(old, new)
    common_keys = {(r["topic"], r["vehicle"]) for r in c["common"]}
    assert common_keys == {("anger", "fire")}
    row = c["common"][0]
    assert row["old_path"] == ["anger", "spark", "fire"]
    assert row["new_path"] == ["anger", "heat", "blaze", "fire"]
    assert [(r["topic"], r["vehicle"]) for r in c["old_only"]] == [("anger", "ice")]
    assert [(r["topic"], r["vehicle"]) for r in c["new_only"]] == [("anger", "storm")]


def test_render_markdown_shows_both_paths_with_arrows():
    old = {("anger", "fire"): ["anger", "spark", "fire"]}
    new = {("anger", "fire"): ["anger", "heat", "blaze", "fire"]}
    md = render_markdown(compare(old, new), old_label="OLD", new_label="NEW")
    assert "anger" in md  # topic header
    assert "anger → spark → fire" in md
    assert "anger → heat → blaze → fire" in md
    assert "OLD" in md and "NEW" in md
