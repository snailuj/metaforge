"""Validate all *.jsonl files in data-pipeline/grading/ against their Pydantic models.

Usage:
    python data-pipeline/scripts/validate_grading_jsonl.py [--dir PATH]

Callable as a library via ``validate_lines(lines)``, which accepts any iterable
of raw text lines and returns a summary dict without touching the filesystem.

Exit code:
    0 — all lines valid (or directory empty / no JSONL files found)
    1 — one or more parse, version, or validation errors
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Iterable

# Allow running directly or importing from tests without installing the package.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "grading_sidecar"))

from models import ChainRecord, JudgementRecord, JudgementRecordV1  # noqa: E402

MODEL_BY_VERSION: dict[str, type] = {
    "chain.v1": ChainRecord,
    "judgement.v1": JudgementRecordV1,  # legacy flat `label`
    "judgement.v2": JudgementRecord,    # two-axis linkage + metaphor (+ tier)
}


def validate_lines(lines: Iterable[str]) -> dict:
    """Validate an iterable of raw JSONL lines.

    Returns a dict with keys:
        parsed_ok     — count of lines that passed validation
        bad_json      — count of lines that could not be parsed as JSON
        bad_version   — count of lines with an unknown or missing schema_version
        bad_validation — count of lines whose data failed Pydantic validation
        errors        — list of human-readable error strings (one per bad line)
    """
    parsed_ok = 0
    bad_json = 0
    bad_version = 0
    bad_validation = 0
    errors: list[str] = []

    for i, raw in enumerate(lines, 1):
        raw = raw.strip()
        if not raw:
            continue

        # --- JSON parse ---
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            bad_json += 1
            errors.append(f"line {i}: JSON parse: {exc}")
            continue

        # --- Schema version lookup ---
        ver = data.get("schema_version")
        model = MODEL_BY_VERSION.get(ver)  # type: ignore[arg-type]
        if model is None:
            bad_version += 1
            errors.append(f"line {i}: unknown schema_version={ver!r}")
            continue

        # --- Pydantic validation ---
        try:
            model(**data)
            parsed_ok += 1
        except Exception as exc:
            bad_validation += 1
            errors.append(f"line {i}: validation: {exc}")

    return {
        "parsed_ok": parsed_ok,
        "bad_json": bad_json,
        "bad_version": bad_version,
        "bad_validation": bad_validation,
        "errors": errors,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate grading JSONL files against their Pydantic schemas."
    )
    parser.add_argument(
        "--dir",
        default="data-pipeline/grading/",
        help="Directory to scan for *.jsonl files (default: data-pipeline/grading/)",
    )
    args = parser.parse_args()

    target = Path(args.dir)
    if not target.exists():
        print(f"Directory not found: {target}", file=sys.stderr)
        return 1

    total_errors = 0
    files_checked = 0

    for fpath in sorted(target.glob("*.jsonl")):
        files_checked += 1
        result = validate_lines(fpath.read_text().splitlines())
        bad = result["bad_json"] + result["bad_version"] + result["bad_validation"]
        total_errors += bad
        status = "OK" if bad == 0 else f"FAIL ({bad} errors)"
        print(f"{fpath}: {result['parsed_ok']} valid, {status}")
        # Show at most 10 errors per file to keep output readable.
        for err in result["errors"][:10]:
            print(f"  - {err}")

    if files_checked == 0:
        print(f"No *.jsonl files found in {target}")

    return 0 if total_errors == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
