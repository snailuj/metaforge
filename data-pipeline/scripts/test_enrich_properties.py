"""Tests for enrich_properties.py — claude -p enrichment script."""
import json
import sqlite3
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

# Ensure scripts/ is importable when running from data-pipeline/
sys.path.insert(0, str(Path(__file__).parent))

from enrich_properties import (
    format_batch_items,
    extract_batch,
    get_pilot_synsets,
    get_frequency_ranked_synsets,
    load_checkpoint,
    save_checkpoint,
    run_enrichment,
    EnrichmentResult,
    UsageExhaustedError,
)


# --- Test data ---------------------------------------------------------------

SAMPLE_SYNSETS = [
    {"id": "100001", "lemma": "candle", "definition": "stick of wax with a wick", "pos": "n"},
    {"id": "100002", "lemma": "whisper", "definition": "speak softly", "pos": "v"},
]

CANNED_RESULT = [
    {"id": "100001", "properties": ["warm", "flickering", "luminous"]},
    {"id": "100002", "properties": ["quiet", "intimate", "breathy"]},
]


# --- 1. format_batch_items ---------------------------------------------------

def test_format_batch_items():
    text = format_batch_items(SAMPLE_SYNSETS)
    assert "ID: 100001" in text
    assert "Word: candle" in text
    assert "Definition: stick of wax with a wick" in text
    assert "ID: 100002" in text
    assert "Word: whisper" in text
    assert "Definition: speak softly" in text


# --- 2. extract_batch merges local data ---------------------------------------

@patch("enrich_properties.prompt_json")
def test_extract_batch_merges_local_data(mock_prompt_json):
    mock_prompt_json.return_value = CANNED_RESULT
    results = extract_batch(SAMPLE_SYNSETS, model="haiku")

    assert len(results) == 2
    r0 = results[0]
    assert r0["id"] == "100001"
    assert r0["lemma"] == "candle"
    assert r0["definition"] == "stick of wax with a wick"
    assert r0["pos"] == "n"
    assert "warm" in r0["properties"]


# --- 3. extract_batch warns on unknown IDs ------------------------------------

@patch("enrich_properties.prompt_json")
def test_extract_batch_warns_unknown_ids(mock_prompt_json, caplog):
    import logging
    bad_result = [{"id": "999999", "properties": ["unknown"]}]
    mock_prompt_json.return_value = bad_result
    with caplog.at_level(logging.WARNING):
        results = extract_batch(SAMPLE_SYNSETS, model="haiku")

    assert len(results) == 0
    assert any("999999" in r.message for r in caplog.records)


# --- 4. checkpoint round-trip -------------------------------------------------

def test_checkpoint_round_trip(tmp_path):
    cp_file = tmp_path / "checkpoint.json"
    state = {"completed_ids": ["100001", "100002"], "results": CANNED_RESULT}
    save_checkpoint(cp_file, state)
    loaded = load_checkpoint(cp_file)
    assert loaded["completed_ids"] == ["100001", "100002"]
    assert len(loaded["results"]) == 2


# --- 5. checkpoint resume filters completed ----------------------------------

def test_checkpoint_resume_filters_completed(tmp_path):
    cp_file = tmp_path / "checkpoint.json"
    state = {"completed_ids": ["100001"], "results": [CANNED_RESULT[0]]}
    save_checkpoint(cp_file, state)
    loaded = load_checkpoint(cp_file)
    completed = set(loaded["completed_ids"])

    remaining = [s for s in SAMPLE_SYNSETS if s["id"] not in completed]
    assert len(remaining) == 1
    assert remaining[0]["id"] == "100002"


# --- 6. UsageExhaustedError is RateLimitError alias --------------------------

def test_usage_exhausted_error_is_rate_limit_alias():
    """UsageExhaustedError is an alias for claude_client.RateLimitError."""
    from claude_client import RateLimitError
    assert UsageExhaustedError is RateLimitError


# --- 7. extract_batch surfaces RateLimitError immediately --------------------

@patch("enrich_properties.prompt_json")
def test_extract_batch_no_retry_on_usage_exhausted(mock_prompt_json):
    """RateLimitError surfaces immediately from prompt_json."""
    mock_prompt_json.side_effect = UsageExhaustedError("rate limit exceeded")
    with pytest.raises(UsageExhaustedError):
        extract_batch(SAMPLE_SYNSETS, model="haiku")
    assert mock_prompt_json.call_count == 1


# --- 8. extract_batch uses custom prompt_template ----------------------------

@patch("enrich_properties.prompt_json")
def test_extract_batch_custom_prompt_template(mock_prompt_json):
    """extract_batch uses prompt_template when provided."""
    mock_prompt_json.return_value = CANNED_RESULT
    custom = "Custom prompt: {batch_items}\nJSON only: [{{}}]"
    extract_batch(SAMPLE_SYNSETS, model="haiku", prompt_template=custom)

    # Verify the prompt passed to prompt_json contains our custom text
    sent_prompt = mock_prompt_json.call_args[0][0]
    assert "Custom prompt:" in sent_prompt
    assert "ID: 100001" in sent_prompt  # batch_items still interpolated


# --- 9. extract_batch uses BATCH_PROMPT by default --------------------------

@patch("enrich_properties.prompt_json")
def test_extract_batch_default_prompt_unchanged(mock_prompt_json):
    """extract_batch uses BATCH_PROMPT when no prompt_template given."""
    mock_prompt_json.return_value = CANNED_RESULT
    extract_batch(SAMPLE_SYNSETS, model="haiku")

    sent_prompt = mock_prompt_json.call_args[0][0]
    # BATCH_PROMPT contains "sensory and behavioural properties"
    assert "sensory and behavioural properties" in sent_prompt


# --- 10. extract_batch rejects invalid template -------------------------------

def test_extract_batch_invalid_template():
    """extract_batch raises ValueError if template lacks {batch_items}."""
    with pytest.raises(ValueError, match="batch_items"):
        extract_batch(SAMPLE_SYNSETS, model="haiku", prompt_template="No placeholder here")


# --- Helpers for run_enrichment tests ----------------------------------------

def _make_test_db(tmp_path) -> str:
    """Create a temporary lexicon_v2-schema DB for run_enrichment tests."""
    db_file = tmp_path / "test_lexicon.db"
    conn = sqlite3.connect(str(db_file))
    conn.executescript(LEXICON_SCHEMA)
    conn.executemany(
        "INSERT INTO synsets VALUES (?, ?, ?)",
        [
            ("100001", "n", "stick of wax with a wick"),
            ("100002", "v", "speak softly"),
            ("100003", "n", "loud noise"),
        ],
    )
    conn.executemany(
        "INSERT INTO lemmas VALUES (?, ?)",
        [("candle", "100001"), ("whisper", "100002"), ("thunder", "100003")],
    )
    conn.commit()
    conn.close()
    return str(db_file)


# --- 11. run_enrichment returns EnrichmentResult dataclass --------------------

@patch("enrich_properties.extract_batch")
@patch("enrich_properties.get_pilot_synsets")
def test_run_enrichment_returns_enrichment_result(
    mock_get_synsets, mock_extract, tmp_path,
):
    """run_enrichment returns an EnrichmentResult dataclass with expected fields."""
    db_path = _make_test_db(tmp_path)

    mock_get_synsets.return_value = SAMPLE_SYNSETS
    mock_extract.return_value = [
        {"id": "100001", "lemma": "candle", "definition": "stick of wax", "pos": "n",
         "properties": ["warm", "flickering"]},
        {"id": "100002", "lemma": "whisper", "definition": "speak softly", "pos": "v",
         "properties": ["quiet", "intimate"]},
    ]

    with patch("enrich_properties.OUTPUT_DIR", tmp_path):
        result = run_enrichment(
            size=2,
            batch_size=20,
            delay=0,
            output_file=tmp_path / "out.json",
            db_path=db_path,
        )

    assert isinstance(result, EnrichmentResult)
    assert result.requested == 2
    assert result.succeeded == 2
    assert result.failed == 0
    assert result.failed_ids == []
    assert result.coverage == 1.0
    assert (tmp_path / "out.json").exists()
    assert result.output_file == str(tmp_path / "out.json")


# --- 12. run_enrichment tracks failed synset IDs ----------------------------

@patch("enrich_properties.extract_batch")
@patch("enrich_properties.get_pilot_synsets")
def test_run_enrichment_tracks_failed_synset_ids(
    mock_get_synsets, mock_extract, tmp_path,
):
    """When a batch fails, run_enrichment captures the failed synset IDs."""
    db_path = _make_test_db(tmp_path)

    synsets = [
        {"id": "100001", "lemma": "candle", "definition": "stick of wax", "pos": "n"},
        {"id": "100002", "lemma": "whisper", "definition": "speak softly", "pos": "v"},
        {"id": "100003", "lemma": "thunder", "definition": "loud noise", "pos": "n"},
    ]
    mock_get_synsets.return_value = synsets

    # First batch succeeds (first 2), second batch fails (third synset)
    mock_extract.side_effect = [
        [
            {"id": "100001", "lemma": "candle", "definition": "stick of wax", "pos": "n",
             "properties": ["warm"]},
            {"id": "100002", "lemma": "whisper", "definition": "speak softly", "pos": "v",
             "properties": ["quiet"]},
        ],
        RuntimeError("API failure"),
    ]

    with patch("enrich_properties.OUTPUT_DIR", tmp_path):
        result = run_enrichment(
            size=3,
            batch_size=2,
            delay=0,
            output_file=tmp_path / "out.json",
            db_path=db_path,
        )

    assert isinstance(result, EnrichmentResult)
    assert result.succeeded == 2
    assert result.failed == 1
    assert result.failed_ids == ["100003"]
    assert result.coverage == pytest.approx(2 / 3)


# --- 13. enrichment output JSON includes failed_synset_ids -------------------

@patch("enrich_properties.extract_batch")
@patch("enrich_properties.get_pilot_synsets")
def test_enrichment_output_json_includes_failed_ids(
    mock_get_synsets, mock_extract, tmp_path,
):
    """Output JSON file includes failed_synset_ids in stats."""
    db_path = _make_test_db(tmp_path)

    synsets = [
        {"id": "100001", "lemma": "candle", "definition": "stick of wax", "pos": "n"},
        {"id": "100002", "lemma": "whisper", "definition": "speak softly", "pos": "v"},
    ]
    mock_get_synsets.return_value = synsets

    # First synset succeeds, second batch fails
    mock_extract.side_effect = [
        [{"id": "100001", "lemma": "candle", "definition": "stick of wax", "pos": "n",
          "properties": ["warm"]}],
        RuntimeError("Timeout"),
    ]

    with patch("enrich_properties.OUTPUT_DIR", tmp_path):
        result = run_enrichment(
            size=2,
            batch_size=1,
            delay=0,
            output_file=tmp_path / "out.json",
            db_path=db_path,
        )

    output = json.loads((tmp_path / "out.json").read_text())
    assert "failed_synset_ids" in output["stats"]
    assert output["stats"]["failed_synset_ids"] == ["100002"]


# --- 14. get_pilot_synsets queries lexicon_v2 schema -------------------------

LEXICON_SCHEMA = """
CREATE TABLE synsets (
    synset_id TEXT PRIMARY KEY,
    pos TEXT NOT NULL,
    definition TEXT NOT NULL
);
CREATE TABLE lemmas (
    lemma TEXT NOT NULL,
    synset_id TEXT NOT NULL,
    PRIMARY KEY (lemma, synset_id)
);
"""


def _make_lexicon_db():
    """Create in-memory DB with lexicon_v2 schema and sample data."""
    conn = sqlite3.connect(":memory:")
    conn.executescript(LEXICON_SCHEMA)
    conn.executemany(
        "INSERT INTO synsets VALUES (?, ?, ?)",
        [
            ("100001", "n", "stick of wax with a wick"),
            ("100002", "v", "speak softly"),
            ("100003", "a", "having a high temperature"),
        ],
    )
    conn.executemany(
        "INSERT INTO lemmas VALUES (?, ?)",
        [
            ("candle", "100001"),
            ("taper", "100001"),
            ("whisper", "100002"),
            ("hot", "100003"),
        ],
    )
    conn.commit()
    return conn


def test_get_pilot_synsets_lexicon_schema():
    """get_pilot_synsets returns synsets from lexicon_v2 schema."""
    conn = _make_lexicon_db()
    synsets = get_pilot_synsets(conn, limit=10)

    assert len(synsets) == 3
    ids = {s["id"] for s in synsets}
    assert "100001" in ids
    assert "100002" in ids
    assert "100003" in ids

    # Check fields populated correctly
    candle = next(s for s in synsets if s["id"] == "100001")
    assert candle["definition"] == "stick of wax with a wick"
    assert candle["pos"] == "n"
    assert candle["lemma"] in ("candle", "taper")


def test_get_pilot_synsets_required_ids():
    """get_pilot_synsets prioritises required_ids."""
    conn = _make_lexicon_db()
    synsets = get_pilot_synsets(conn, limit=1, required_ids=["100002"])

    ids = {s["id"] for s in synsets}
    assert "100002" in ids


def test_run_enrichment_accepts_db_path(tmp_path):
    """run_enrichment accepts db_path parameter instead of using SQLUNET_DB."""
    db_path = tmp_path / "test_lexicon.db"
    conn = sqlite3.connect(str(db_path))
    conn.executescript(LEXICON_SCHEMA)
    conn.executemany(
        "INSERT INTO synsets VALUES (?, ?, ?)",
        [("100001", "n", "stick of wax with a wick")],
    )
    conn.executemany(
        "INSERT INTO lemmas VALUES (?, ?)",
        [("candle", "100001")],
    )
    conn.commit()
    conn.close()

    with patch("enrich_properties.extract_batch") as mock_extract, \
         patch("enrich_properties.OUTPUT_DIR", tmp_path):
        mock_extract.return_value = [
            {"id": "100001", "lemma": "candle", "definition": "stick of wax with a wick",
             "pos": "n", "properties": ["warm"]},
        ]
        result = run_enrichment(
            size=1,
            batch_size=20,
            delay=0,
            output_file=tmp_path / "out.json",
            db_path=str(db_path),
            required_synset_ids={"100001"},
        )

    assert isinstance(result, EnrichmentResult)
    assert result.succeeded == 1


# --- 15. get_frequency_ranked_synsets -----------------------------------------

LEXICON_SCHEMA_WITH_FREQ = """
CREATE TABLE synsets (
    synset_id TEXT PRIMARY KEY,
    pos TEXT NOT NULL,
    definition TEXT NOT NULL
);
CREATE TABLE lemmas (
    lemma TEXT NOT NULL,
    synset_id TEXT NOT NULL,
    PRIMARY KEY (lemma, synset_id)
);
CREATE TABLE frequencies (
    lemma TEXT PRIMARY KEY,
    familiarity REAL,
    rarity TEXT
);
CREATE TABLE enrichment (
    synset_id TEXT PRIMARY KEY,
    model_used TEXT
);
"""


def _make_freq_db():
    """Create in-memory DB with frequency + enrichment tables.

    Synsets ranked by max lemma familiarity:
      1. 200001 "happy" (fam=7.0) — already enriched, should be excluded
      2. 200002 "walk" (fam=6.5)
      3. 200003 "candle" (fam=5.0, "taper" fam=2.0)
      4. 200004 "melancholy" (fam=3.0)
      5. 200005 "petrichor" (no frequency data → fam=0)
    """
    conn = sqlite3.connect(":memory:")
    conn.executescript(LEXICON_SCHEMA_WITH_FREQ)
    conn.executemany(
        "INSERT INTO synsets VALUES (?, ?, ?)",
        [
            ("200001", "a", "feeling pleasure"),
            ("200002", "v", "move on foot"),
            ("200003", "n", "stick of wax with a wick"),
            ("200004", "n", "a feeling of pensive sadness"),
            ("200005", "n", "pleasant earthy smell after rain"),
        ],
    )
    conn.executemany(
        "INSERT INTO lemmas VALUES (?, ?)",
        [
            ("happy", "200001"),
            ("walk", "200002"),
            ("candle", "200003"),
            ("taper", "200003"),
            ("melancholy", "200004"),
            ("petrichor", "200005"),
        ],
    )
    conn.executemany(
        "INSERT INTO frequencies VALUES (?, ?, ?)",
        [
            ("happy", 7.0, "common"),
            ("walk", 6.5, "common"),
            ("candle", 5.0, "unusual"),
            ("taper", 2.0, "rare"),
            ("melancholy", 3.0, "rare"),
            # petrichor deliberately absent — no frequency data
        ],
    )
    # Mark "happy" as already enriched
    conn.execute(
        "INSERT INTO enrichment VALUES (?, ?)",
        ("200001", "haiku"),
    )
    conn.commit()
    return conn


def test_frequency_ranked_excludes_enriched():
    """Already-enriched synsets are excluded from frequency-ranked selection."""
    conn = _make_freq_db()
    synsets = get_frequency_ranked_synsets(conn, limit=10)

    ids = [s["id"] for s in synsets]
    assert "200001" not in ids, "already-enriched synset should be excluded"


def test_frequency_ranked_returns_familiarity_order():
    """Synsets are returned in descending max-lemma-familiarity order."""
    conn = _make_freq_db()
    synsets = get_frequency_ranked_synsets(conn, limit=10)

    ids = [s["id"] for s in synsets]
    # walk (6.5), candle (5.0), melancholy (3.0), petrichor (0)
    assert ids == ["200002", "200003", "200004", "200005"]


def test_frequency_ranked_picks_most_familiar_lemma():
    """For multi-lemma synsets, the most familiar lemma is selected."""
    conn = _make_freq_db()
    synsets = get_frequency_ranked_synsets(conn, limit=10)

    candle_entry = next(s for s in synsets if s["id"] == "200003")
    assert candle_entry["lemma"] == "candle", (
        "should pick 'candle' (fam=5.0) over 'taper' (fam=2.0)"
    )


def test_frequency_ranked_respects_limit():
    """Limit parameter caps the number of results."""
    conn = _make_freq_db()
    synsets = get_frequency_ranked_synsets(conn, limit=2)

    assert len(synsets) == 2
    ids = [s["id"] for s in synsets]
    assert ids == ["200002", "200003"]


def test_frequency_ranked_populates_all_fields():
    """Each result has id, lemma, definition, and pos."""
    conn = _make_freq_db()
    synsets = get_frequency_ranked_synsets(conn, limit=1)

    s = synsets[0]
    assert s["id"] == "200002"
    assert s["lemma"] == "walk"
    assert s["definition"] == "move on foot"
    assert s["pos"] == "v"


@patch("enrich_properties.extract_batch")
@patch("enrich_properties.get_pilot_synsets")
def test_run_enrichment_v2_property_stats(mock_get_synsets, mock_extract, tmp_path):
    """run_enrichment with v2 structured properties computes stats without crashing."""
    db_path = _make_test_db(tmp_path)

    mock_get_synsets.return_value = SAMPLE_SYNSETS
    mock_extract.return_value = [
        {"id": "100001", "lemma": "candle", "definition": "stick of wax", "pos": "n",
         "properties": [
             {"text": "warm", "salience": 0.9, "type": "physical", "relation": "emits warmth"},
             {"text": "flickering", "salience": 0.8, "type": "behaviour", "relation": "flame flickers"},
         ]},
        {"id": "100002", "lemma": "whisper", "definition": "speak softly", "pos": "v",
         "properties": [
             {"text": "quiet", "salience": 0.9, "type": "physical", "relation": "low volume"},
             {"text": "warm", "salience": 0.5, "type": "emotional", "relation": "feels warm"},
         ]},
    ]

    with patch("enrich_properties.OUTPUT_DIR", tmp_path):
        result = run_enrichment(
            size=2,
            batch_size=20,
            delay=0,
            output_file=tmp_path / "out.json",
            db_path=db_path,
            schema_version="v2",
        )

    assert result.succeeded == 2

    output = json.loads((tmp_path / "out.json").read_text())
    assert output["stats"]["total_properties"] == 4
    assert output["stats"]["unique_properties"] == 3  # warm appears twice
    assert "warm" in output["property_frequency"]


def test_frequency_ranked_offset_skips_top_n():
    """Offset skips the top N synsets by frequency."""
    conn = _make_freq_db()
    # Without offset: walk, candle, melancholy, petrichor
    # With offset=2: melancholy, petrichor
    synsets = get_frequency_ranked_synsets(conn, limit=10, offset=2)

    ids = [s["id"] for s in synsets]
    assert ids == ["200004", "200005"]


def test_frequency_ranked_offset_with_limit():
    """Offset + limit together select a window."""
    conn = _make_freq_db()
    # offset=1, limit=2: skip walk → candle, melancholy
    synsets = get_frequency_ranked_synsets(conn, limit=2, offset=1)

    ids = [s["id"] for s in synsets]
    assert ids == ["200003", "200004"]


def test_frequency_ranked_no_enrichment_table():
    """Works when enrichment table doesn't exist (fresh DB)."""
    conn = sqlite3.connect(":memory:")
    conn.executescript(LEXICON_SCHEMA)
    conn.executemany(
        "INSERT INTO synsets VALUES (?, ?, ?)",
        [("300001", "n", "a thing")],
    )
    conn.executemany(
        "INSERT INTO lemmas VALUES (?, ?)",
        [("thing", "300001")],
    )
    # No frequencies table either — should still work, just 0 familiarity
    conn.execute("""
        CREATE TABLE frequencies (
            lemma TEXT PRIMARY KEY,
            familiarity REAL,
            rarity TEXT
        )
    """)
    conn.commit()

    synsets = get_frequency_ranked_synsets(conn, limit=10)
    assert len(synsets) == 1
    assert synsets[0]["id"] == "300001"
