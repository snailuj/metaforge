"""Preprocess the MUNCH dataset into evaluator-ready JSONL fixtures.

MUNCH (Metaphor Understanding Challenge, github.com/xiaoyuisrain/metaphor-understanding-challenge)
is licensed CC BY 4.0. We materialise two committed fixtures:

- ``munch_apt.jsonl``   — apt human paraphrases exploded from ``correct_answers/for_generation.csv``.
  Each row in ``human_ans`` holds 1+ space-separated paraphrase tokens; we emit one record per
  (s0, paraphrase) pair, yielding ~10,261 rows.
- ``munch_inapt.jsonl`` — inapt control paraphrases from ``correct_answers/for_judgement.csv``
  (one row per s0_idx, the ``s2``/``s2_label="inapt"`` column), yielding 1,492 rows.

Both files share the schema: ``{metaphor, target, paraphrase, label, genre, s0_idx, source_file}``.
Genre comes from ``for_generation.csv`` and is joined onto judgement rows via ``s0_idx``.

Idempotent — overwrites the two output files on every run.

Usage::

    python data-pipeline/scripts/preprocess_munch.py \\
        --raw data-pipeline/raw/munch \\
        --out data-pipeline/fixtures
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
import re
import sys
from pathlib import Path
from typing import Iterator

log = logging.getLogger(__name__)

BOLD_RE = re.compile(r"<b>(.*?)</b>", re.DOTALL)


def extract_target(sentence: str) -> str | None:
    """Pull the ``<b>...</b>``-marked target word from an MUNCH sentence."""
    match = BOLD_RE.search(sentence)
    return match.group(1) if match else None


def load_generation(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    log.info("loaded %d rows from %s", len(rows), path.name)
    return rows


def load_judgement(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    log.info("loaded %d rows from %s", len(rows), path.name)
    return rows


def explode_apt(
    generation_rows: list[dict[str, str]],
) -> tuple[list[dict[str, object]], int]:
    """Explode generation rows into one record per paraphrase token.

    Returns ``(records, skipped)`` where ``skipped`` is the count of input
    rows whose ``human_ans`` was missing or blank (no paraphrase tokens were
    yielded). The dataset is small (~10k rows) so materialising the list is
    fine and lets us tally skips for ETL observability.
    """
    records: list[dict[str, object]] = []
    skipped = 0
    for row in generation_rows:
        s0 = row.get("s0", "")
        target = extract_target(s0)
        genre = row.get("genre", "")
        s0_idx = row.get("idx", "")
        emitted_for_row = 0
        for paraphrase in (row.get("human_ans") or "").split():
            paraphrase = paraphrase.strip()
            if not paraphrase:
                continue
            records.append({
                "metaphor": s0,
                "target": target,
                "paraphrase": paraphrase,
                "label": "apt",
                "genre": genre,
                "s0_idx": s0_idx,
                "source_file": "correct_answers/for_generation.csv",
            })
            emitted_for_row += 1
        if emitted_for_row == 0:
            skipped += 1
    return records, skipped


def emit_inapt(
    judgement_rows: list[dict[str, str]],
    genre_by_idx: dict[str, str],
) -> Iterator[dict[str, object]]:
    """Emit one inapt record per judgement row.

    MUNCH places the inapt option in either ``s2`` (overwhelmingly) or ``s1`` —
    we read the labels rather than assume column order so all 1,492 controls
    are emitted.
    """
    for row in judgement_rows:
        s1_label = row.get("s1_label", "").strip().lower()
        s2_label = row.get("s2_label", "").strip().lower()
        if s2_label == "inapt":
            inapt_sentence = row.get("s2", "")
        elif s1_label == "inapt":
            inapt_sentence = row.get("s1", "")
        else:
            log.warning(
                "skipping judgement row %s — neither s1_label nor s2_label is 'inapt' (got %r/%r)",
                row.get("s0_idx"), row.get("s1_label"), row.get("s2_label"),
            )
            continue
        s0 = row.get("s0", "")
        s0_idx = row.get("s0_idx", "")
        yield {
            "metaphor": s0,
            "target": extract_target(s0),
            "paraphrase": extract_target(inapt_sentence),
            "paraphrase_sentence": inapt_sentence,
            "label": "inapt",
            "genre": genre_by_idx.get(s0_idx, ""),
            "s0_idx": s0_idx,
            "source_file": "correct_answers/for_judgement.csv",
        }


def write_jsonl(records: Iterator[dict[str, object]], path: Path) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with path.open("w", encoding="utf-8") as fh:
        for rec in records:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
            count += 1
    log.info("wrote %d records to %s", count, path)
    return count


def preprocess(raw_dir: Path, out_dir: Path) -> tuple[int, int]:
    """Return ``(apt_count, inapt_count)``."""
    generation_csv = raw_dir / "correct_answers" / "for_generation.csv"
    judgement_csv = raw_dir / "correct_answers" / "for_judgement.csv"
    for required in (generation_csv, judgement_csv):
        if not required.exists():
            raise FileNotFoundError(
                f"MUNCH source missing: {required}. "
                f"Clone github.com/xiaoyuisrain/metaphor-understanding-challenge into {raw_dir}."
            )

    generation_rows = load_generation(generation_csv)
    judgement_rows = load_judgement(judgement_csv)
    genre_by_idx = {row["idx"]: row.get("genre", "") for row in generation_rows}

    apt_records, blank_human_ans = explode_apt(generation_rows)
    log.info("explode_apt: %d rows had blank human_ans", blank_human_ans)
    apt_count = write_jsonl(iter(apt_records), out_dir / "munch_apt.jsonl")
    inapt_count = write_jsonl(
        emit_inapt(judgement_rows, genre_by_idx), out_dir / "munch_inapt.jsonl"
    )
    return apt_count, inapt_count


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--raw",
        type=Path,
        default=Path("data-pipeline/raw/munch"),
        help="Path to the cloned metaphor-understanding-challenge repo.",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("data-pipeline/fixtures"),
        help="Output directory for munch_apt.jsonl / munch_inapt.jsonl.",
    )
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    apt, inapt = preprocess(args.raw, args.out)
    print(f"munch_apt.jsonl   {apt} records")
    print(f"munch_inapt.jsonl {inapt} records")
    return 0


if __name__ == "__main__":
    sys.exit(main())
