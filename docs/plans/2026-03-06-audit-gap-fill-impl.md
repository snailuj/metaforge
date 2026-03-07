# Audit + Gap-Fill Physical Properties Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Two new scripts — `audit_physical_coverage.py` (flags synsets with insufficient physical properties) and `gap_fill_physical.py` (targeted second-pass enrichment for flagged synsets) — that run in parallel with the main enrichment.

**Architecture:** Both scripts live in `data-pipeline/scripts/`. The audit reads enrichment JSON (or live checkpoint) and outputs flagged synset IDs. The gap-fill calls the LLM with a physical-only prompt for those synsets, producing an enrichment-format JSON importable via `enrich.sh --from-json`. No changes to existing pipeline code.

**Tech Stack:** Python 3, sqlite3, argparse, json. Gap-fill reuses `claude_client.prompt_json` and `enrich_properties.extract_batch` for LLM calls.

**Design doc:** `docs/plans/2026-03-06-audit-gap-fill-design.md`

---

### Task 1: audit_physical_coverage.py — Tests

**Files:**
- Create: `data-pipeline/scripts/test_audit_physical_coverage.py`

**Step 1: Write the failing tests**

```python
"""Tests for audit_physical_coverage.py."""

import json
import pytest
from pathlib import Path
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
```

**Step 2: Run tests to verify they fail**

Run: `cd data-pipeline/scripts && python -m pytest test_audit_physical_coverage.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'audit_physical_coverage'`

**Step 3: Commit**

```bash
git add data-pipeline/scripts/test_audit_physical_coverage.py
git commit -m "test: add audit_physical_coverage tests (red)"
```

---

### Task 2: audit_physical_coverage.py — Implementation

**Files:**
- Create: `data-pipeline/scripts/audit_physical_coverage.py`

**Step 1: Implement to pass the tests**

```python
"""Audit enrichment data for physical property coverage.

Reads enrichment JSON (or live checkpoint) and flags synsets with
insufficient physical properties based on POS-dependent thresholds.

Usage:
    python audit_physical_coverage.py --input checkpoint_enrich.json --output flagged.json
    python audit_physical_coverage.py --input enrichment_8000.json --exclude gap_fill.json -o flagged.json
"""

import argparse
import json
import sys
import time
from pathlib import Path


POS_THRESHOLDS = {
    "n": 4,
    "v": 2,
    "a": 2,
    "s": 2,  # satellite adjective — same threshold as adjective
}

DEFAULT_THRESHOLD = 2  # fallback for unknown POS (adverbs, etc.)


def audit_physical_coverage(
    data: dict,
    exclude_ids: set[str] | None = None,
) -> dict:
    """Audit enrichment data for physical property coverage.

    Args:
        data: Enrichment JSON ({"synsets": [...]}) or checkpoint ({"results": [...]}).
        exclude_ids: Synset IDs to skip (already gap-filled).

    Returns:
        Dict with flagged_ids, total_synsets, flagged_count, pos_breakdown.
    """
    # Handle both enrichment format and checkpoint format
    synsets = data.get("synsets") or data.get("results") or []
    exclude = exclude_ids or set()

    flagged_ids = []
    pos_breakdown = {}

    for synset in synsets:
        sid = synset["id"]
        if sid in exclude:
            continue

        pos = synset.get("pos", "n")
        threshold = POS_THRESHOLDS.get(pos, DEFAULT_THRESHOLD)

        physical_count = sum(
            1 for p in synset.get("properties", [])
            if isinstance(p, dict) and p.get("type") == "physical"
        )

        # Track POS stats
        if pos not in pos_breakdown:
            pos_breakdown[pos] = {"total": 0, "flagged": 0, "avg_physical": 0, "physical_sum": 0}
        pos_breakdown[pos]["total"] += 1
        pos_breakdown[pos]["physical_sum"] += physical_count

        if physical_count < threshold:
            flagged_ids.append(sid)
            pos_breakdown[pos]["flagged"] += 1

    # Compute averages
    for stats in pos_breakdown.values():
        if stats["total"] > 0:
            stats["avg_physical"] = round(stats["physical_sum"] / stats["total"], 2)
        del stats["physical_sum"]

    total = len([s for s in synsets if s["id"] not in exclude])

    return {
        "flagged_ids": flagged_ids,
        "total_synsets": total,
        "flagged_count": len(flagged_ids),
        "flagged_pct": round(len(flagged_ids) / total * 100, 1) if total else 0,
        "pos_breakdown": pos_breakdown,
    }


def load_json_with_retry(path: Path, retries: int = 1) -> dict:
    """Load JSON, retrying once on decode error (concurrent write tolerance)."""
    for attempt in range(retries + 1):
        try:
            with open(path) as f:
                return json.load(f)
        except json.JSONDecodeError:
            if attempt < retries:
                print(f"  JSON decode error, retrying in 1s...", file=sys.stderr)
                time.sleep(1)
            else:
                raise


def main():
    parser = argparse.ArgumentParser(
        description="Audit enrichment data for physical property coverage"
    )
    parser.add_argument(
        "--input", "-i", type=str, required=True,
        help="Enrichment JSON or checkpoint file to audit",
    )
    parser.add_argument(
        "--output", "-o", type=str, required=True,
        help="Output JSON with flagged synset IDs",
    )
    parser.add_argument(
        "--exclude", "-x", type=str, default=None,
        help="JSON file with synset IDs to exclude (already gap-filled)",
    )
    args = parser.parse_args()

    data = load_json_with_retry(Path(args.input))

    exclude_ids = set()
    if args.exclude:
        exclude_data = json.loads(Path(args.exclude).read_text())
        # Accept either a plain list or an enrichment-format dict
        if isinstance(exclude_data, list):
            exclude_ids = set(str(i) for i in exclude_data)
        elif isinstance(exclude_data, dict) and "synsets" in exclude_data:
            exclude_ids = {s["id"] for s in exclude_data["synsets"]}

    result = audit_physical_coverage(data, exclude_ids=exclude_ids)

    # Write output
    Path(args.output).write_text(json.dumps(result, indent=2))

    # Print summary to stdout
    print(f"\n=== Physical Coverage Audit ===")
    print(f"Total synsets: {result['total_synsets']}")
    print(f"Flagged: {result['flagged_count']} ({result['flagged_pct']}%)")
    print(f"\nBreakdown by POS:")
    for pos, stats in sorted(result["pos_breakdown"].items()):
        print(f"  {pos}: {stats['flagged']}/{stats['total']} flagged "
              f"(avg {stats['avg_physical']} physical)")


if __name__ == "__main__":
    main()
```

**Step 2: Run tests to verify they pass**

Run: `cd data-pipeline/scripts && python -m pytest test_audit_physical_coverage.py -v`
Expected: All PASS

**Step 3: Commit**

```bash
git add data-pipeline/scripts/audit_physical_coverage.py
git commit -m "feat: add audit_physical_coverage.py — flags synsets with insufficient physical properties"
```

---

### Task 3: gap_fill_physical.py — Tests

**Files:**
- Create: `data-pipeline/scripts/test_gap_fill_physical.py`

**Step 1: Write the failing tests**

Tests should cover:
- Prompt construction (physical-only, single-word constraint)
- Output format matches enrichment JSON schema (`{"synsets": [...]}`)
- Checkpoint save/load for resume
- Synset ID lookup from DB (definition, lemma, pos)
- CLI argument parsing
- `--exclude` for already-gap-filled IDs

Key tests (not full code — implementation will determine exact shape):

```python
"""Tests for gap_fill_physical.py."""

import json
import sqlite3
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
from gap_fill_physical import (
    build_physical_prompt,
    format_gap_fill_batch,
    load_synsets_from_db,
    build_output,
    GAP_FILL_PROMPT,
)


# --- Prompt tests ---

class TestGapFillPrompt:
    def test_prompt_mentions_physical(self):
        assert "physical" in GAP_FILL_PROMPT.lower()

    def test_prompt_requires_single_word(self):
        assert "single" in GAP_FILL_PROMPT.lower() or "one word" in GAP_FILL_PROMPT.lower()

    def test_prompt_has_batch_items_placeholder(self):
        assert "{batch_items}" in GAP_FILL_PROMPT


class TestFormatGapFillBatch:
    def test_includes_id_and_definition(self):
        synsets = [{"id": "s1", "lemma": "rock", "definition": "a hard mineral", "pos": "n"}]
        result = format_gap_fill_batch(synsets)
        assert "s1" in result
        assert "rock" in result
        assert "a hard mineral" in result


# --- DB lookup tests ---

class TestLoadSynsetsFromDb:
    def test_loads_synset_by_id(self, tmp_path):
        db_path = tmp_path / "test.db"
        conn = sqlite3.connect(db_path)
        conn.executescript("""
            CREATE TABLE synsets (synset_id TEXT PRIMARY KEY, definition TEXT, pos TEXT);
            CREATE TABLE lemmas (lemma TEXT, synset_id TEXT);
            CREATE TABLE frequencies (lemma TEXT, familiarity REAL);
            INSERT INTO synsets VALUES ('s1', 'a large rock', 'n');
            INSERT INTO lemmas VALUES ('boulder', 's1');
            INSERT INTO frequencies VALUES ('boulder', 5.5);
        """)
        conn.close()

        result = load_synsets_from_db(str(db_path), ["s1"])
        assert len(result) == 1
        assert result[0]["id"] == "s1"
        assert result[0]["lemma"] == "boulder"
        assert result[0]["definition"] == "a large rock"

    def test_missing_synset_skipped(self, tmp_path):
        db_path = tmp_path / "test.db"
        conn = sqlite3.connect(db_path)
        conn.executescript("""
            CREATE TABLE synsets (synset_id TEXT PRIMARY KEY, definition TEXT, pos TEXT);
            CREATE TABLE lemmas (lemma TEXT, synset_id TEXT);
            CREATE TABLE frequencies (lemma TEXT, familiarity REAL);
        """)
        conn.close()

        result = load_synsets_from_db(str(db_path), ["nonexistent"])
        assert len(result) == 0


# --- Output format tests ---

class TestBuildOutput:
    def test_output_has_synsets_key(self):
        results = [{"id": "s1", "properties": [{"text": "hard", "type": "physical"}]}]
        output = build_output(results, model="sonnet", batch_size=20)
        assert "synsets" in output

    def test_output_has_stats(self):
        results = [{"id": "s1", "properties": [{"text": "hard", "type": "physical"}]}]
        output = build_output(results, model="sonnet", batch_size=20)
        assert output["stats"]["total_synsets"] == 1

    def test_output_has_config(self):
        output = build_output([], model="sonnet", batch_size=20)
        assert output["config"]["model"] == "sonnet"
```

**Step 2: Run tests to verify they fail**

Run: `cd data-pipeline/scripts && python -m pytest test_gap_fill_physical.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'gap_fill_physical'`

**Step 3: Commit**

```bash
git add data-pipeline/scripts/test_gap_fill_physical.py
git commit -m "test: add gap_fill_physical tests (red)"
```

---

### Task 4: gap_fill_physical.py — Implementation

**Files:**
- Create: `data-pipeline/scripts/gap_fill_physical.py`

**Step 1: Implement to pass the tests**

```python
"""Gap-fill physical properties for flagged synsets.

Targeted second-pass enrichment: calls the LLM with a physical-only prompt
for synsets that have insufficient physical properties (as identified by
audit_physical_coverage.py).

Output is enrichment-format JSON compatible with enrich.sh --from-json.

Usage:
    python gap_fill_physical.py --synset-ids flagged.json --db lexicon_v2.db \
      --model sonnet --output gap_fill_physical.json
"""

import argparse
import json
import logging
import sqlite3
import time
from collections import Counter
from pathlib import Path
from typing import List, Dict

from claude_client import prompt_json, RateLimitError

OUTPUT_DIR = Path(__file__).parent.parent / "output"

GAP_FILL_PROMPT = """You are extracting PHYSICAL and SENSORY properties for specific word senses.

For each word sense below, provide 4-6 properties that describe its physical, tangible, or sensory qualities.

RULES:
- Each property must be a SINGLE WORD (no hyphens, no compounds, no phrases)
- Focus ONLY on physical/sensory properties: texture, weight, temperature, shape, colour, sound, smell, taste, luminosity, size
- The definition tells you WHICH sense — focus only on that sense
- Every property gets salience 0.0-1.0 and a short relation phrase

Output format per word:
{{"id": "...", "properties": [{{"text": "word", "salience": 0.8, "type": "physical", "relation": "short phrase"}}]}}

Example:

Word: anvil
Definition: a heavy block of iron or steel on which hot metals are hammered into shape
Properties: heavy, metallic, dense, dark, resonant, rigid

{batch_items}

Output ONLY a valid JSON array (no markdown, no explanation):
[{{"id": "...", "properties": [...]}}, ...]
"""


def format_gap_fill_batch(synsets: List[Dict]) -> str:
    """Format synsets for the gap-fill prompt."""
    lines = []
    for s in synsets:
        lines.append(f"ID: {s['id']}")
        lines.append(f"Word: {s['lemma']}")
        lines.append(f"Definition: {s['definition']}")
        lines.append("")
    return "\n".join(lines)


def load_synsets_from_db(db_path: str, synset_ids: list[str]) -> List[Dict]:
    """Look up synset details from the DB for gap-fill."""
    conn = sqlite3.connect(db_path)
    try:
        placeholders = ",".join("?" for _ in synset_ids)
        cursor = conn.execute(f"""
            WITH ranked_lemmas AS (
                SELECT
                    s.synset_id,
                    s.definition,
                    s.pos,
                    l.lemma,
                    ROW_NUMBER() OVER (
                        PARTITION BY s.synset_id
                        ORDER BY COALESCE(f.familiarity, 0) DESC, l.lemma
                    ) AS rn
                FROM synsets s
                JOIN lemmas l ON l.synset_id = s.synset_id
                LEFT JOIN frequencies f ON f.lemma = l.lemma
                WHERE s.synset_id IN ({placeholders})
            )
            SELECT synset_id, definition, lemma, pos
            FROM ranked_lemmas
            WHERE rn = 1
        """, synset_ids)
        return [
            {"id": str(row[0]), "definition": row[1], "lemma": row[2], "pos": row[3]}
            for row in cursor.fetchall()
        ]
    finally:
        conn.close()


def build_output(results: List[Dict], model: str, batch_size: int) -> dict:
    """Build enrichment-format output JSON."""
    all_properties = []
    for r in results:
        all_properties.extend(r.get("properties", []))

    property_texts = [
        p["text"] if isinstance(p, dict) else p
        for p in all_properties
    ]
    property_freq = Counter(property_texts)

    return {
        "synsets": results,
        "all_properties": list(set(property_texts)),
        "property_frequency": dict(property_freq.most_common(100)),
        "stats": {
            "total_synsets": len(results),
            "total_properties": len(property_texts),
            "unique_properties": len(set(property_texts)),
            "avg_properties_per_synset": round(
                len(all_properties) / len(results), 2
            ) if results else 0,
        },
        "config": {
            "model": model,
            "batch_size": batch_size,
            "purpose": "gap_fill_physical",
        },
    }


def load_checkpoint(checkpoint_path: Path) -> dict:
    """Load checkpoint state, or return empty state."""
    if checkpoint_path.exists():
        with open(checkpoint_path) as f:
            return json.load(f)
    return {"completed_ids": [], "results": []}


def save_checkpoint(checkpoint_path: Path, state: dict):
    """Save checkpoint state to disk."""
    with open(checkpoint_path, "w") as f:
        json.dump(state, f, indent=2)


def run_gap_fill(
    synsets: List[Dict],
    model: str = "sonnet",
    batch_size: int = 20,
    delay: float = 1.0,
    output_file: Path = None,
    resume: bool = False,
    verbose: bool = False,
) -> dict:
    """Run physical gap-fill enrichment on synsets."""
    checkpoint_path = OUTPUT_DIR / "checkpoint_gap_fill.json"

    if resume:
        state = load_checkpoint(checkpoint_path)
        completed_ids = set(state["completed_ids"])
        results = state["results"]
        print(f"  Resuming from checkpoint: {len(completed_ids)} already done")
    else:
        completed_ids = set()
        results = []
        if checkpoint_path.exists():
            checkpoint_path.unlink()

    remaining = [s for s in synsets if s["id"] not in completed_ids]
    failed_batches = 0

    num_batches = (len(remaining) + batch_size - 1) // batch_size
    print(f"Gap-fill: {len(remaining)} synsets in {num_batches} batches")

    for batch_idx in range(num_batches):
        start = batch_idx * batch_size
        end = min(start + batch_size, len(remaining))
        batch = remaining[start:end]

        print(f"\n  Batch {batch_idx + 1}/{num_batches} ({len(batch)} synsets)...")

        try:
            batch_items = format_gap_fill_batch(batch)
            prompt = GAP_FILL_PROMPT.format(batch_items=batch_items)
            batch_results = prompt_json(prompt, model=model, expect=list, verbose=verbose)

            local_data = {s["id"]: s for s in batch}
            for r in batch_results:
                rid = str(r.get("id", ""))
                if rid in local_data:
                    # Merge local data (lemma, definition, pos) into result
                    r["lemma"] = local_data[rid]["lemma"]
                    r["definition"] = local_data[rid]["definition"]
                    r["pos"] = local_data[rid]["pos"]
                    # Force all properties to physical type
                    for p in r.get("properties", []):
                        p["type"] = "physical"
                    results.append(r)
                    completed_ids.add(rid)
                    print(f"    {r.get('lemma', '?')}: {len(r.get('properties', []))} physical properties")

            save_checkpoint(checkpoint_path, {
                "completed_ids": list(completed_ids),
                "results": results,
            })

        except RateLimitError as e:
            print(f"  RATE LIMITED — stopping: {e}")
            break
        except Exception as e:
            print(f"  BATCH FAILED: {e}")
            failed_batches += 1

        if delay > 0:
            time.sleep(delay)

    output = build_output(results, model=model, batch_size=batch_size)

    if output_file:
        output_file.parent.mkdir(exist_ok=True)
        with open(output_file, "w") as f:
            json.dump(output, f, indent=2)

    # Clean up checkpoint on success
    if failed_batches == 0 and checkpoint_path.exists():
        checkpoint_path.unlink()

    print(f"\nGap-fill complete!")
    print(f"  Synsets: {output['stats']['total_synsets']}")
    print(f"  Properties: {output['stats']['total_properties']}")
    print(f"  Failed batches: {failed_batches}")

    return output


def main():
    parser = argparse.ArgumentParser(
        description="Gap-fill physical properties for flagged synsets"
    )
    parser.add_argument(
        "--synset-ids", "-s", type=str, required=True,
        help="JSON file with audit output (must contain 'flagged_ids' key)",
    )
    parser.add_argument(
        "--db", type=str, required=True,
        help="Path to lexicon_v2.db",
    )
    parser.add_argument(
        "--output", "-o", type=str, required=True,
        help="Output JSON path",
    )
    parser.add_argument(
        "--model", "-m", type=str, default="sonnet",
        help="Claude model alias (default: sonnet)",
    )
    parser.add_argument(
        "--batch-size", "-b", type=int, default=20,
        help="Synsets per LLM call (default: 20)",
    )
    parser.add_argument(
        "--delay", type=float, default=1.0,
        help="Seconds between batches (default: 1.0)",
    )
    parser.add_argument(
        "--resume", "-r", action="store_true",
        help="Resume from checkpoint",
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true",
        help="Enable DEBUG logging",
    )
    args = parser.parse_args()

    if args.verbose:
        logging.basicConfig(level=logging.DEBUG, format="%(levelname)s: %(message)s")

    # Load flagged IDs from audit output
    audit_data = json.loads(Path(args.synset_ids).read_text())
    flagged_ids = audit_data.get("flagged_ids", audit_data)  # accept list or audit dict
    print(f"Flagged synsets: {len(flagged_ids)}")

    # Look up synset details from DB
    synsets = load_synsets_from_db(args.db, flagged_ids)
    print(f"Found in DB: {len(synsets)}")

    run_gap_fill(
        synsets,
        model=args.model,
        batch_size=args.batch_size,
        delay=args.delay,
        output_file=Path(args.output),
        resume=args.resume,
        verbose=args.verbose,
    )


if __name__ == "__main__":
    main()
```

**Step 2: Run tests to verify they pass**

Run: `cd data-pipeline/scripts && python -m pytest test_gap_fill_physical.py -v`
Expected: All PASS

**Step 3: Commit**

```bash
git add data-pipeline/scripts/gap_fill_physical.py
git commit -m "feat: add gap_fill_physical.py — targeted second-pass enrichment for physical properties"
```

---

### Task 5: Integration test — audit reads checkpoint, gap-fill produces importable JSON

**Files:**
- Modify: `data-pipeline/scripts/test_audit_physical_coverage.py`
- Modify: `data-pipeline/scripts/test_gap_fill_physical.py`

**Step 1: Add integration-style tests**

In `test_audit_physical_coverage.py`, add a test that writes a checkpoint file to disk, reads it via CLI args simulation, and verifies the output file.

In `test_gap_fill_physical.py`, add a test that verifies the output JSON is importable by checking it matches the expected enrichment schema (has `synsets` key, each synset has `id`, `properties` array, each property has `text`, `type`, `salience`, `relation`).

**Step 2: Run full test suite**

Run: `cd data-pipeline/scripts && python -m pytest test_audit_physical_coverage.py test_gap_fill_physical.py -v`
Expected: All PASS

**Step 3: Commit**

```bash
git add data-pipeline/scripts/test_audit_physical_coverage.py data-pipeline/scripts/test_gap_fill_physical.py
git commit -m "test: add integration tests for audit + gap-fill pipeline"
```

---

### Task 6: Run audit on live checkpoint + start gap-fill

**Step 1: Run audit against current checkpoint**

```bash
source .venv/bin/activate
python data-pipeline/scripts/audit_physical_coverage.py \
  --input data-pipeline/output/checkpoint_enrich.json \
  --output data-pipeline/output/flagged_physical.json
```

**Step 2: Start gap-fill in background**

```bash
source .venv/bin/activate
python data-pipeline/scripts/gap_fill_physical.py \
  --synset-ids data-pipeline/output/flagged_physical.json \
  --db data-pipeline/output/lexicon_v2.db \
  --model sonnet \
  --output data-pipeline/output/gap_fill_physical.json \
  --verbose
```

**Step 3: Verify gap-fill output looks correct**

Check the first few results in the output JSON to confirm physical-only properties.

---

### Task 7: Update data-pipeline/CLAUDE.md

**Files:**
- Modify: `data-pipeline/CLAUDE.md`

**Step 1: Add audit + gap-fill to operations section**

Add section documenting the two new scripts, their CLI args, and the parallel workflow.

**Step 2: Commit**

```bash
git add data-pipeline/CLAUDE.md
git commit -m "docs: add audit + gap-fill to data pipeline CLAUDE.md"
```
