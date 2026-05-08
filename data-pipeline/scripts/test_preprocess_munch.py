"""Tests for preprocess_munch — uses inline fixtures (no .gitignored paths)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from preprocess_munch import (
    extract_target,
    explode_apt,
    emit_inapt,
    load_generation,
    load_judgement,
    preprocess,
)


GENERATION_CSV = (
    "i0,idx,s0,novelty,sid,genre,human_ans\n"
    '0,1,"Latest <b>approach</b> to debt",0.03,a1e-1,NEWS,direction method plan\n'
    '1,2,"He <b>leading</b> a deal",-0.03,a1e-2,NEWS,winning fronting\n'
    '2,3,"Her <b>tones</b> were sharp",0.18,b2-1,FICTION,language voice\n'
)

JUDGEMENT_CSV = (
    "i0,s0_idx,s0,s1,s1_label,s2,s2_label\n"
    '0,1,"Latest <b>approach</b> to debt","Latest <b>method</b> to debt",apt,"Latest <b>coming</b> to debt",inapt\n'
    '1,2,"He <b>leading</b> a deal","He <b>winning</b> a deal",apt,"He <b>heading</b> a deal",inapt\n'
)


def test_extract_target_returns_bold_text():
    assert extract_target("a <b>foo</b> bar") == "foo"
    assert extract_target("no markup") is None


def test_explode_apt_yields_one_row_per_paraphrase_token():
    rows = [
        {"idx": "1", "s0": "Latest <b>approach</b> to debt",
         "genre": "NEWS", "human_ans": "direction method plan"},
    ]
    records, skipped = explode_apt(rows)
    assert len(records) == 3
    assert {r["paraphrase"] for r in records} == {"direction", "method", "plan"}
    assert all(r["label"] == "apt" for r in records)
    assert all(r["target"] == "approach" for r in records)
    assert all(r["genre"] == "NEWS" for r in records)
    assert skipped == 0


def test_explode_apt_skips_blank_human_ans():
    rows = [{"idx": "1", "s0": "x", "genre": "", "human_ans": ""}]
    records, skipped = explode_apt(rows)
    assert records == []
    assert skipped == 1


def test_explode_apt_counts_blank_rows_alongside_good_rows():
    """Blank human_ans rows are tallied for ETL observability."""
    rows = [
        {"idx": "1", "s0": "Latest <b>approach</b> to debt",
         "genre": "NEWS", "human_ans": "direction"},
        {"idx": "2", "s0": "He <b>x</b>", "genre": "NEWS", "human_ans": ""},
        {"idx": "3", "s0": "She <b>y</b>", "genre": "NEWS"},  # missing key
        {"idx": "4", "s0": "It <b>z</b> went", "genre": "NEWS",
         "human_ans": "method plan"},
    ]
    records, skipped = explode_apt(rows)
    assert len(records) == 3  # 1 + 2
    assert skipped == 2


def test_emit_inapt_uses_s2_word_and_joins_genre():
    judgement = [{
        "s0_idx": "1",
        "s0": "Latest <b>approach</b> to debt",
        "s1": "Latest <b>method</b> to debt", "s1_label": "apt",
        "s2": "Latest <b>coming</b> to debt", "s2_label": "inapt",
    }]
    genres = {"1": "NEWS"}
    out = list(emit_inapt(judgement, genres))
    assert len(out) == 1
    rec = out[0]
    assert rec["paraphrase"] == "coming"
    assert rec["target"] == "approach"
    assert rec["label"] == "inapt"
    assert rec["genre"] == "NEWS"
    assert rec["paraphrase_sentence"].startswith("Latest <b>coming</b>")


def test_emit_inapt_skips_rows_with_unexpected_label(caplog):
    judgement = [{
        "s0_idx": "9", "s0": "x", "s1": "y", "s1_label": "apt",
        "s2": "z", "s2_label": "apt",  # malformed
    }]
    out = list(emit_inapt(judgement, {}))
    assert out == []


def test_emit_inapt_handles_inapt_in_s1_column():
    """A subset of MUNCH judgement rows place the inapt option in s1, not s2."""
    judgement = [{
        "s0_idx": "9597",
        "s0": "Latest <b>approach</b> to debt",
        "s1": "Latest <b>coming</b> to debt", "s1_label": "inapt",
        "s2": "Latest <b>method</b> to debt", "s2_label": "apt",
    }]
    out = list(emit_inapt(judgement, {"9597": "NEWS"}))
    assert len(out) == 1
    assert out[0]["paraphrase"] == "coming"
    assert out[0]["label"] == "inapt"


def test_preprocess_end_to_end(tmp_path: Path):
    raw = tmp_path / "munch"
    (raw / "correct_answers").mkdir(parents=True)
    (raw / "correct_answers" / "for_generation.csv").write_text(GENERATION_CSV)
    (raw / "correct_answers" / "for_judgement.csv").write_text(JUDGEMENT_CSV)
    out_dir = tmp_path / "fixtures"

    apt_count, inapt_count = preprocess(raw, out_dir)
    # 3 rows × {3,2,2} paraphrases = 7 apt; 2 inapt judgement rows
    assert apt_count == 7
    assert inapt_count == 2

    apt_lines = (out_dir / "munch_apt.jsonl").read_text().splitlines()
    inapt_lines = (out_dir / "munch_inapt.jsonl").read_text().splitlines()
    assert len(apt_lines) == 7
    assert len(inapt_lines) == 2

    # Validate JSON shape on every line
    for line in apt_lines + inapt_lines:
        rec = json.loads(line)
        assert {"metaphor", "target", "paraphrase", "label", "genre", "s0_idx"} <= rec.keys()
        assert rec["label"] in {"apt", "inapt"}


def test_load_generation_includes_path_on_csv_error(tmp_path: Path):
    """Malformed CSV must surface the file path in the raised exception."""
    import csv as _csv
    bad = tmp_path / "bad_generation.csv"
    # Unterminated quoted field — csv.Error on read
    bad.write_text('i0,idx,s0,human_ans\n0,1,"unterminated quote,foo\n')
    try:
        load_generation(bad)
    except (_csv.Error, RuntimeError) as exc:
        assert str(bad) in str(exc)
    else:
        raise AssertionError("expected csv.Error/RuntimeError")


def test_load_judgement_includes_path_on_csv_error(tmp_path: Path):
    import csv as _csv
    bad = tmp_path / "bad_judgement.csv"
    bad.write_text('i0,s0_idx,s0\n0,1,"unterminated\n')
    try:
        load_judgement(bad)
    except (_csv.Error, RuntimeError) as exc:
        assert str(bad) in str(exc)
    else:
        raise AssertionError("expected csv.Error/RuntimeError")


def test_preprocess_raises_when_source_missing(tmp_path: Path):
    raw = tmp_path / "missing"
    out_dir = tmp_path / "out"
    try:
        preprocess(raw, out_dir)
    except FileNotFoundError as exc:
        assert "MUNCH source missing" in str(exc)
    else:
        raise AssertionError("expected FileNotFoundError")
