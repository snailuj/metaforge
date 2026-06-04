"""Tests for metaphor_disambiguate — the one-time LLM sense-disambiguation pass.

The hard sense-accuracy gate: lexicon_v2.db has no sense-frequency data, so the
least-polysemous / lowest-synset-id heuristics mis-pick common-word senses
(house->'playing house', feel->genital). This pass presents ALL noun senses of
a head lemma to a cheap model and takes the dominant everyday sense, or abstains.

DB queries run against an in-memory fixture; LLM access is injected (prompt_fn).
"""
import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import metaphor_disambiguate as md


# --- in-memory fixture ------------------------------------------------------
def _db() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.executescript(
        """
        CREATE TABLE synsets (synset_id TEXT PRIMARY KEY, pos TEXT NOT NULL, definition TEXT NOT NULL);
        CREATE TABLE lemmas (lemma TEXT NOT NULL, synset_id TEXT NOT NULL, PRIMARY KEY (lemma, synset_id));
        CREATE TABLE frequencies (lemma TEXT PRIMARY KEY, zipf REAL);
        CREATE TABLE property_vocab_curated (vocab_id INTEGER PRIMARY KEY, synset_id TEXT NOT NULL,
            lemma TEXT NOT NULL, pos TEXT NOT NULL, polysemy INTEGER NOT NULL, UNIQUE(synset_id));
        CREATE TABLE synset_properties_curated (synset_id TEXT NOT NULL, vocab_id INTEGER NOT NULL,
            cluster_id INTEGER NOT NULL, PRIMARY KEY (synset_id, cluster_id));
        """
    )
    synsets = [
        ("51775", "n", "a dwelling that serves as living quarters"),
        ("9591", "n", "play in which children take the roles of parents"),
        ("30227", "n", "a strong emotion of displeasure"),
        ("100", "n", "the 8th letter of the alphabet"),   # a junk 'letter of the' sense
    ]
    conn.executemany("INSERT INTO synsets VALUES (?,?,?)", synsets)
    conn.executemany("INSERT INTO lemmas VALUES (?,?)", [
        ("house", "51775"), ("house", "9591"),   # two noun senses
        ("anger", "30227"),                        # single noun sense
        ("the", "100"),                            # stopword
    ])
    conn.executemany("INSERT INTO frequencies VALUES (?,?)", [
        ("house", 5.0), ("anger", 4.5), ("the", 7.0), ("ox", 4.9),
    ])
    # curated + enriched (one row per synset; enriched = has a synset_properties_curated row)
    pvc = [(1, "51775", "house", "n", 3), (2, "9591", "house", "n", 9),
           (3, "30227", "anger", "n", 2), (4, "100", "the", "n", 1)]
    conn.executemany("INSERT INTO property_vocab_curated VALUES (?,?,?,?,?)", pvc)
    conn.executemany("INSERT INTO synset_properties_curated VALUES (?,?,?)",
                     [("51775", 1, 0), ("9591", 2, 0), ("30227", 3, 0), ("100", 4, 0)])
    return conn


# --- head_lemmas (DB) -------------------------------------------------------
def test_head_lemmas_filters_stopwords_and_short_and_orders_by_zipf():
    conn = _db()
    rows = md.head_lemmas(conn, limit=10, min_zipf=2.5)
    lemmas = [r["lemma"] for r in rows]
    assert "the" not in lemmas            # stopword removed
    assert "ox" not in lemmas             # length < 3 (also not an enriched noun)
    assert lemmas == ["house", "anger"]   # zipf desc: 5.0 then 4.5


def test_candidate_senses_returns_all_noun_senses():
    conn = _db()
    senses = md.candidate_senses(conn, "house")
    ids = {s["synset_id"] for s in senses}
    assert ids == {"51775", "9591"}
    assert all("gloss" in s for s in senses)


def test_select_candidate_topics_groups_senses_per_lemma():
    conn = _db()
    cands = md.select_candidate_topics(conn, limit=10, min_zipf=2.5)
    by_lemma = {c["lemma"]: c for c in cands}
    assert len(by_lemma["house"]["senses"]) == 2
    assert len(by_lemma["anger"]["senses"]) == 1


# --- build_disambiguation_prompt (pure) ------------------------------------
def test_prompt_lists_each_lemma_with_its_glosses_and_allows_abstain():
    items = [{"lemma": "house", "zipf": 5.0, "senses": [
        {"synset_id": "51775", "gloss": "a dwelling"},
        {"synset_id": "9591", "gloss": "play in which children take roles"},
    ]}]
    p = md.build_disambiguation_prompt(items).lower()
    assert "house" in p and "a dwelling" in p and "children take roles" in p
    assert "everyday" in p or "common" in p or "dominant" in p
    assert "null" in p or "abstain" in p or "none" in p  # abstention allowed
    assert "sense_index" in p


# --- parse_disambiguation_batch (pure, conservative) -----------------------
def _items():
    return [{"lemma": "house", "zipf": 5.0, "senses": [
        {"synset_id": "51775", "gloss": "a dwelling"},
        {"synset_id": "9591", "gloss": "playing house"},
    ]}]


def test_parse_maps_one_based_index_to_sense():
    out = md.parse_disambiguation_batch({"picks": [{"lemma": "house", "sense_index": 1}]}, _items())
    assert out == [{"word": "house", "topic_synset_id": "51775", "gloss": "a dwelling"}]


def test_parse_abstain_is_dropped():
    out = md.parse_disambiguation_batch({"picks": [{"lemma": "house", "sense_index": None}]}, _items())
    assert out == []


def test_parse_out_of_range_index_is_dropped():
    out = md.parse_disambiguation_batch({"picks": [{"lemma": "house", "sense_index": 9}]}, _items())
    assert out == []


def test_parse_unknown_lemma_is_dropped():
    out = md.parse_disambiguation_batch({"picks": [{"lemma": "ghost", "sense_index": 1}]}, _items())
    assert out == []


# --- disambiguate (driver, injected client) --------------------------------
def test_disambiguate_autoaccepts_single_sense_without_llm():
    calls = []

    def fake(prompt, model="haiku"):
        calls.append(prompt)
        return {"picks": [{"lemma": "house", "sense_index": 1}]}

    cands = [
        {"lemma": "anger", "zipf": 4.5, "senses": [{"synset_id": "30227", "gloss": "displeasure"}]},
        {"lemma": "house", "zipf": 5.0, "senses": [
            {"synset_id": "51775", "gloss": "a dwelling"}, {"synset_id": "9591", "gloss": "playing house"}]},
    ]
    out = md.disambiguate(cands, prompt_fn=fake, model="haiku")
    by_word = {o["word"]: o for o in out}
    assert by_word["anger"]["topic_synset_id"] == "30227"  # auto, no LLM
    assert by_word["house"]["topic_synset_id"] == "51775"  # LLM picked everyday sense
    assert len(calls) == 1                                  # single-sense never hit the model
    assert "anger" not in calls[0]                          # ...and wasn't in the prompt


def test_disambiguate_chunk_error_abstains_chunk_without_crashing():
    def boom(prompt, model="haiku"):
        raise RuntimeError("api down")

    cands = [{"lemma": "house", "zipf": 5.0, "senses": [
        {"synset_id": "51775", "gloss": "a dwelling"}, {"synset_id": "9591", "gloss": "playing house"}]}]
    out = md.disambiguate(cands, prompt_fn=boom, model="haiku")
    assert out == []  # abstained, run survived


def test_vetted_from_glossed_exact_match_skips_llm():
    conn = _db()
    called = []

    def fake(prompt, model="haiku"):
        called.append(prompt)
        return {"picks": []}

    out = md.vetted_topics_from_glossed(
        conn, [{"word": "house", "gloss": "a dwelling that serves as living quarters"}],
        prompt_fn=fake,
    )
    assert out == [{"word": "house", "topic_synset_id": "51775",
                    "gloss": "a dwelling that serves as living quarters"}]
    assert called == []  # exact gloss->synset match needs no LLM


def test_vetted_from_glossed_single_sense_skips_llm():
    conn = _db()
    out = md.vetted_topics_from_glossed(
        conn, [{"word": "anger", "gloss": "rage"}], prompt_fn=lambda p, model="haiku": {"picks": []})
    assert out == [{"word": "anger", "topic_synset_id": "30227", "gloss": "rage"}]


def test_vetted_from_glossed_ambiguous_uses_llm_and_keeps_curated_gloss():
    conn = _db()

    def fake(prompt, model="haiku"):
        return {"picks": [{"lemma": "house", "sense_index": 1}]}  # 51775 = dwelling

    out = md.vetted_topics_from_glossed(
        conn, [{"word": "house", "gloss": "a place where people live"}], prompt_fn=fake)
    assert out == [{"word": "house", "topic_synset_id": "51775",
                    "gloss": "a place where people live"}]  # curated gloss preserved


def test_vetted_from_glossed_drops_word_with_no_noun_sense():
    conn = _db()
    out = md.vetted_topics_from_glossed(
        conn, [{"word": "zzznope", "gloss": "x"}], prompt_fn=lambda p, model="haiku": {"picks": []})
    assert out == []


def test_write_topics_file_roundtrips(tmp_path):
    topics = [{"word": "house", "topic_synset_id": "51775", "gloss": "a dwelling"}]
    p = tmp_path / "vetted.json"
    md.write_topics_file(topics, str(p))
    import generate_metaphor_edges as mge
    loaded = mge.load_vetted_topics(str(p))   # must be runner-ingestible
    assert loaded == topics
