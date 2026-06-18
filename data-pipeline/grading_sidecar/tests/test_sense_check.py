"""Unit tests for the sense-check sampler + item builder."""
from __future__ import annotations
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from grading_sidecar import paths as paths_mod


def test_sense_labels_path_is_separate_from_judgements():
    # Safety invariant: a sense label must never share a file with gold verdicts.
    assert paths_mod.SENSE_LABELS_PATH != paths_mod.JUDGEMENTS_PATH
    assert paths_mod.SENSE_LABELS_PATH.name == "sense_labels_provisional.jsonl"
    assert paths_mod.SENSE_FLAGS_NAME == "sense_flags_provisional.jsonl"
    assert paths_mod.SENSE_CANDIDATES_NAME == "sense_candidates_provisional.jsonl"


def _chain(sig, topic, tsid, vehicle, vsid):
    return {"topic": topic, "topic_synset_id": tsid, "vehicle": vehicle,
            "vehicle_synset_id": vsid, "chain_signature": sig,
            "chain": [{"phrase": topic, "head": topic, "synset_id": tsid},
                      {"phrase": vehicle, "head": vehicle, "synset_id": vsid}]}


def test_distinct_endpoints_dedup_topic_and_vehicle():
    from grading_sidecar.sense_check import distinct_endpoints
    chains = [_chain("a", "longing", "72598", "drought", "104281"),
              _chain("b", "longing", "72598", "river", "9")]  # topic repeats
    eps = distinct_endpoints(chains)
    keys = {(e["role"], e["word"], e["snapped_synset_id"]) for e in eps}
    assert ("topic", "longing", "72598") in keys      # deduped to one
    assert ("vehicle", "drought", "104281") in keys
    assert ("vehicle", "river", "9") in keys
    assert sum(1 for e in eps if e["role"] == "topic") == 1


def test_sample_stratifies_flagged_and_random_excludes_labelled_and_is_seed_stable():
    from grading_sidecar.sense_check import sample_sense_check
    chains = [_chain(str(i), "longing", "72598", f"v{i}", str(100 + i)) for i in range(10)]
    flags = [{"role": "vehicle", "word": "v0", "synset_id": "100"},
             {"role": "vehicle", "word": "v1", "synset_id": "101"}]
    labels = [{"role": "vehicle", "word": "v0", "snapped_synset_id": "100"}]  # already done
    out = sample_sense_check(flags, chains, labels, n_flagged=5, n_random=3, seed=7)
    keys = {(e["role"], e["word"], e["snapped_synset_id"]) for e in out}
    assert ("vehicle", "v0", "100") not in keys           # labelled excluded
    assert ("vehicle", "v1", "101") in keys               # only un-labelled flag left
    flagged = [e for e in out if e["stratum"] == "flagged"]
    randoms = [e for e in out if e["stratum"] == "random"]
    assert len(flagged) == 1 and len(randoms) == 3        # caps honoured vs pool size
    assert all(("vehicle", e["word"], e["snapped_synset_id"]) not in
               {("vehicle", "v1", "101")} for e in randoms)  # random pool excludes flags
    # Determinism: same seed → identical draw.
    again = sample_sense_check(flags, chains, labels, n_flagged=5, n_random=3, seed=7)
    assert [e["snapped_synset_id"] for e in out] == [e["snapped_synset_id"] for e in again]


def test_build_items_attaches_gloss_candidates_and_all_context_chains():
    from grading_sidecar.sense_check import build_sample_items
    chains = [_chain("a", "longing", "72598", "drought", "104281"),
              _chain("b", "longing", "72598", "river", "9")]
    endpoints = [{"role": "topic", "word": "longing",
                  "snapped_synset_id": "72598", "stratum": "random"}]
    candidates = {"longing": [
        {"synset_id": "72598", "pos": "n", "gloss": "prolonged desire", "tagcount": 5},
        {"synset_id": "999", "pos": "n", "gloss": "a yearning", "tagcount": None},
    ]}
    glosses = {"72598": {"pos": "n", "definition": "prolonged desire"}}
    items = build_sample_items(endpoints, candidates, glosses, chains)
    it = items[0]
    assert it["snapped_gloss"] == "prolonged desire" and it["pos"] == "n"
    assert len(it["candidates"]) == 2
    # Context = ALL chains the endpoint appears in (the operator's addition).
    sigs = {c["chain_signature"] for c in it["context"]["chains"]}
    assert sigs == {"a", "b"}
    # Representative chain_signature for the label is one of them.
    assert it["chain_signature"] in sigs


def test_load_sense_candidates_returns_lemma_to_senses_map(tmp_path):
    """load_sense_candidates returns {lemma: senses} for a valid JSONL."""
    from grading_sidecar.persistence import read_jsonl_skip_malformed
    from grading_sidecar.sense_check import load_sense_candidates
    import json
    p = tmp_path / "candidates.jsonl"
    p.write_text(
        json.dumps({"lemma": "drought", "senses": [
            {"synset_id": "104281", "pos": "n", "gloss": "a dry spell", "tagcount": 3}
        ]}) + "\n" +
        json.dumps({"lemma": "river", "senses": [
            {"synset_id": "9", "pos": "n", "gloss": "a natural stream", "tagcount": 7}
        ]}) + "\n"
    )
    result = load_sense_candidates(read_jsonl_skip_malformed, p)
    assert list(result["drought"]) == [
        {"synset_id": "104281", "pos": "n", "gloss": "a dry spell", "tagcount": 3}
    ]
    assert result["river"][0]["synset_id"] == "9"


def test_load_sense_candidates_missing_path_returns_empty(tmp_path):
    from grading_sidecar.persistence import read_jsonl_skip_malformed
    from grading_sidecar.sense_check import load_sense_candidates
    result = load_sense_candidates(read_jsonl_skip_malformed, tmp_path / "nonexistent.jsonl")
    assert result == {}


def test_load_snapped_glosses_returns_synset_to_pos_and_definition(tmp_path):
    """load_snapped_glosses returns {synset_id: {pos, definition}} for a valid JSONL."""
    from grading_sidecar.persistence import read_jsonl_skip_malformed
    from grading_sidecar.sense_check import load_snapped_glosses
    import json
    p = tmp_path / "glosses.jsonl"
    p.write_text(
        json.dumps({"synset_id": "104281", "pos": "n", "definition": "a dry spell"}) + "\n" +
        json.dumps({"synset_id": "9", "pos": "n", "definition": "a natural stream"}) + "\n"
    )
    result = load_snapped_glosses(read_jsonl_skip_malformed, p)
    assert result["104281"] == {"pos": "n", "definition": "a dry spell"}
    assert result["9"] == {"pos": "n", "definition": "a natural stream"}


def test_load_snapped_glosses_missing_path_returns_empty(tmp_path):
    from grading_sidecar.persistence import read_jsonl_skip_malformed
    from grading_sidecar.sense_check import load_snapped_glosses
    result = load_snapped_glosses(read_jsonl_skip_malformed, tmp_path / "nonexistent.jsonl")
    assert result == {}


def test_build_items_degrades_when_candidates_absent():
    from grading_sidecar.sense_check import build_sample_items
    chains = [_chain("a", "longing", "72598", "drought", "104281")]
    endpoints = [{"role": "vehicle", "word": "drought",
                  "snapped_synset_id": "104281", "stratum": "flagged"}]
    items = build_sample_items(endpoints, {}, {}, chains)  # no candidates, no glosses
    assert items[0]["candidates"] == []
    assert items[0]["snapped_gloss"] is None


# ---------------------------------------------------------------------------
# Task 1: cohort-aware random stratum
# ---------------------------------------------------------------------------

def _chain_with_cohort(sig, topic, tsid, vehicle, vsid, cohort):
    """Chain dict including a cohort tag (as tagged by distinct_endpoints_by_cohort)."""
    return {"topic": topic, "topic_synset_id": tsid, "vehicle": vehicle,
            "vehicle_synset_id": vsid, "chain_signature": sig, "_cohort": cohort,
            "chain": [{"phrase": topic, "head": topic, "synset_id": tsid},
                      {"phrase": vehicle, "head": vehicle, "synset_id": vsid}]}


def test_random_stratum_excludes_curated_topics_and_keeps_spike_topics_and_vehicles():
    """Random pool keeps vehicles (any cohort) + spike topics; excludes curated/stock topics."""
    from grading_sidecar.sense_check import sample_sense_check
    # Arrange: two chains — one curated-topic vehicle, one spike-topic vehicle.
    chains_by_cohort = [
        # curated cohort: topic=harbour, vehicle=anchor
        {"topic": "harbour", "topic_synset_id": "1001", "vehicle": "anchor",
         "vehicle_synset_id": "2001", "chain_signature": "sig-curated", "_cohort": "curated",
         "chain": [{"phrase": "harbour", "head": "harbour", "synset_id": "1001"},
                   {"phrase": "anchor", "head": "anchor", "synset_id": "2001"}]},
        # spike cohort: topic=longing, vehicle=drought
        {"topic": "longing", "topic_synset_id": "1002", "vehicle": "drought",
         "vehicle_synset_id": "2002", "chain_signature": "sig-spike", "_cohort": "spike",
         "chain": [{"phrase": "longing", "head": "longing", "synset_id": "1002"},
                   {"phrase": "drought", "head": "drought", "synset_id": "2002"}]},
    ]
    # No flags, no labels → everything comes from random pool.
    out = sample_sense_check([], chains_by_cohort, [], n_flagged=10, n_random=20, seed=1)
    random_ep = {(e["role"], e["word"]) for e in out if e["stratum"] == "random"}
    # Vehicles from both cohorts must be in the random pool.
    assert ("vehicle", "anchor") in random_ep
    assert ("vehicle", "drought") in random_ep
    # Spike topic must be in the random pool.
    assert ("topic", "longing") in random_ep
    # Curated topic must NOT be in the random pool.
    assert ("topic", "harbour") not in random_ep


def test_flagged_stratum_still_includes_flagged_curated_topic():
    """Flagged stratum is cohort-agnostic — a flagged curated topic must still surface."""
    from grading_sidecar.sense_check import sample_sense_check
    chains_by_cohort = [
        {"topic": "harbour", "topic_synset_id": "1001", "vehicle": "anchor",
         "vehicle_synset_id": "2001", "chain_signature": "sig-curated", "_cohort": "curated",
         "chain": [{"phrase": "harbour", "head": "harbour", "synset_id": "1001"},
                   {"phrase": "anchor", "head": "anchor", "synset_id": "2001"}]},
    ]
    flags = [{"role": "topic", "word": "harbour", "synset_id": "1001"}]
    out = sample_sense_check(flags, chains_by_cohort, [], n_flagged=10, n_random=0, seed=1)
    flagged_ep = {(e["role"], e["word"]) for e in out if e["stratum"] == "flagged"}
    assert ("topic", "harbour") in flagged_ep


# ---------------------------------------------------------------------------
# Task 2: topic POS + gloss in each context chain
# ---------------------------------------------------------------------------

def test_context_chain_carries_topic_pos_and_gloss_for_vehicle_item():
    """context_for returns chains with topic_pos + topic_gloss resolved from glosses map."""
    from grading_sidecar.sense_check import build_sample_items
    chains = [_chain("a", "longing", "72598", "drought", "104281")]
    # Sense-checking a VEHICLE — context chains should show the paired topic's POS/gloss.
    endpoints = [{"role": "vehicle", "word": "drought",
                  "snapped_synset_id": "104281", "stratum": "random"}]
    glosses = {
        "104281": {"pos": "n", "definition": "a dry spell"},
        "72598":  {"pos": "n", "definition": "prolonged desire"},
    }
    items = build_sample_items(endpoints, {}, glosses, chains)
    ctx_chains = items[0]["context"]["chains"]
    assert len(ctx_chains) == 1
    chain = ctx_chains[0]
    assert chain["topic_pos"] == "n"
    assert chain["topic_gloss"] == "prolonged desire"


def test_context_chain_topic_pos_and_gloss_are_none_when_absent():
    """topic_pos and topic_gloss gracefully degrade to None when the gloss map lacks the topic."""
    from grading_sidecar.sense_check import build_sample_items
    chains = [_chain("a", "longing", "72598", "drought", "104281")]
    endpoints = [{"role": "vehicle", "word": "drought",
                  "snapped_synset_id": "104281", "stratum": "random"}]
    # Glosses map has the vehicle's synset but NOT the topic's synset_id.
    glosses = {"104281": {"pos": "n", "definition": "a dry spell"}}
    items = build_sample_items(endpoints, {}, glosses, chains)
    chain = items[0]["context"]["chains"][0]
    assert chain["topic_pos"] is None
    assert chain["topic_gloss"] is None
