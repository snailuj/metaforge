import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_next_round_prompt import (
    select_anti_examples, deterministic_topic_shuffle, filter_substantive_notes
)

def test_filter_excludes_short_notes():
    items = [
        {"notes": "merge: sideways step here clearly", "chain_signature": "a"},
        {"notes": "x", "chain_signature": "b"},
        {"notes": "", "chain_signature": "c"},
    ]
    out = filter_substantive_notes(items, min_chars=20)
    assert [x["chain_signature"] for x in out] == ["a"]

def test_select_uses_all_when_few():
    items = [{"notes": "merge: something quite long here indeed", "chain_signature": str(i)} for i in range(3)]
    result = select_anti_examples(items, target=10)
    assert len(result) == 3

def test_select_clusters_by_tag_prefix_proportionally():
    items = (
        [{"notes": "merge: " + "x"*30, "chain_signature": f"m{i}"} for i in range(8)]
        + [{"notes": "padding: " + "x"*30, "chain_signature": f"p{i}"} for i in range(8)]
    )
    result = select_anti_examples(items, target=10, cluster_max_per_tag=4)
    merge = sum(1 for r in result if r["notes"].startswith("merge:"))
    padding = sum(1 for r in result if r["notes"].startswith("padding:"))
    assert merge <= 4 and padding <= 4
    assert len(result) <= 10

def test_select_excludes_empty_or_short_notes_even_when_few():
    items = [
        {"notes": "x", "chain_signature": "a"},  # too short
        {"notes": "merge: substantive enough note here", "chain_signature": "b"},
    ]
    result = select_anti_examples(items, target=10)
    assert len(result) == 1
    assert result[0]["chain_signature"] == "b"

def test_deterministic_topic_shuffle_reproducible():
    topics = ["a", "b", "c", "d", "e"]
    s1 = deterministic_topic_shuffle(topics, seed_str="topics_v1")
    s2 = deterministic_topic_shuffle(topics, seed_str="topics_v1")
    assert s1 == s2

def test_deterministic_topic_shuffle_excludes_already_used():
    topics = ["a", "b", "c", "d", "e"]
    shuffled = deterministic_topic_shuffle(topics, seed_str="topics_v1", exclude={"b", "d"})
    assert "b" not in shuffled and "d" not in shuffled
    assert len(shuffled) == 3

def test_deterministic_topic_shuffle_different_seeds_differ():
    topics = list("abcdefghijklmnop")
    s1 = deterministic_topic_shuffle(topics, seed_str="seed_1")
    s2 = deterministic_topic_shuffle(topics, seed_str="seed_2")
    # Same set, different order (with very high probability for 16 items)
    assert set(s1) == set(s2)
    assert s1 != s2
