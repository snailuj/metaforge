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
