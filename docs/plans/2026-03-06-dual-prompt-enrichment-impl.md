# Dual-Prompt Enrichment Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Improve property quality by switching to a modified v2 prompt with single-word constraints, physical property minimum, post-hoc physical coverage audit, and targeted gap-fill for under-covered synsets.

**Architecture:** Three-phase pipeline: (1) modify v2 prompt and add property validation, (2) new audit script classifies physical coverage per synset, (3) new gap-fill script runs targeted second pass on flagged synsets. All phases use TDD.

**Tech Stack:** Python 3.12, pytest, sqlite3, existing `claude_client.py` for LLM calls, existing `enrich_pipeline.py` for import.

**Design doc:** `docs/plans/2026-03-06-dual-prompt-enrichment-design.md`

---

### Task 1: Add post-import property validation to reject multi-word and hyphenated properties

The existing `filter_mwe()` in `enrich_pipeline.py` handles multi-word expressions by trying to salvage them (POS-tag, strip adjectives). With single-word-only properties, we want a stricter approach: reject anything with a space or hyphen outright, and log what was rejected.

**Files:**
- Modify: `data-pipeline/scripts/enrich_pipeline.py:72-85` (`filter_mwe` function)
- Test: `data-pipeline/scripts/test_enrich_pipeline.py`

**Step 1: Write failing tests**

Add to `data-pipeline/scripts/test_enrich_pipeline.py`:

```python
def test_filter_mwe_rejects_hyphenated():
    """Hyphenated words are rejected (single-word policy)."""
    assert filter_mwe("dormant-active") is None

def test_filter_mwe_rejects_hyphenated_simple():
    """Even two-part hyphenated words are rejected."""
    assert filter_mwe("lava-formed") is None

def test_filter_mwe_single_word_passes():
    """Plain single words still pass through."""
    assert filter_mwe("molten") == "molten"
```

**Step 2: Run tests to verify they fail**

Run: `cd data-pipeline && ../.venv/bin/python -m pytest scripts/test_enrich_pipeline.py::test_filter_mwe_rejects_hyphenated scripts/test_enrich_pipeline.py::test_filter_mwe_rejects_hyphenated_simple -v`
Expected: FAIL — `filter_mwe("dormant-active")` currently returns `"dormant-active"` (single token, passes through)

**Step 3: Modify `filter_mwe` to reject hyphens**

In `data-pipeline/scripts/enrich_pipeline.py`, modify `filter_mwe()`:

```python
def filter_mwe(text: str) -> str | None:
    """Filter multi-word and hyphenated expressions.

    Single unhyphenated tokens pass through unchanged. Hyphenated words
    and multi-word expressions are rejected (returns None). This enforces
    single-word-only properties for clean vocabulary snapping.
    """
    # Reject multi-word
    tokens = text.split()
    if len(tokens) > 1:
        return None
    # Reject hyphenated compounds
    if "-" in text:
        return None
    return text
```

Note: this removes the old POS-tagging salvage logic. With single-word properties, there's nothing to salvage — it's either a single unhyphenated word or it's rejected.

**Step 4: Run tests to verify they pass**

Run: `cd data-pipeline && ../.venv/bin/python -m pytest scripts/test_enrich_pipeline.py -v`
Expected: ALL PASS (including existing tests — check that no existing tests relied on hyphenated pass-through)

**Step 5: Add logging for rejected properties**

In `curate_properties()` at `data-pipeline/scripts/enrich_pipeline.py:132`, add a counter for rejected properties and log a summary:

```python
import logging
log = logging.getLogger(__name__)

def curate_properties(conn, enrichment_data, vectors):
    all_props = set()
    rejected_count = 0
    for synset in enrichment_data.get("synsets", []):
        for prop in synset.get("properties", [])[:MAX_PROPERTIES_PER_SYNSET]:
            raw_text = _extract_property_text(prop)
            if raw_text is None:
                continue
            filtered = filter_mwe(normalise(raw_text))
            if filtered is not None:
                all_props.add(filtered)
            else:
                rejected_count += 1

    if rejected_count > 0:
        log.warning("rejected %d multi-word/hyphenated properties", rejected_count)
    # ... rest unchanged
```

**Step 6: Run full test suite**

Run: `cd data-pipeline && ../.venv/bin/python -m pytest scripts/ -v`
Expected: ALL PASS

**Step 7: Commit**

```bash
git add data-pipeline/scripts/enrich_pipeline.py data-pipeline/scripts/test_enrich_pipeline.py
git commit -m "feat: reject hyphenated/multi-word properties in pipeline validation"
```

---

### Task 2: Modify BATCH_PROMPT_V2 with single-word constraint, physical minimum, and examples

**Files:**
- Modify: `data-pipeline/scripts/enrich_properties.py:97-141` (`BATCH_PROMPT_V2`)

**Step 1: Replace BATCH_PROMPT_V2**

In `data-pipeline/scripts/enrich_properties.py`, replace the existing `BATCH_PROMPT_V2` string (lines 97-141) with the modified version. Key changes:

1. Replace `"text": 1-2 word property (short, evocative)` with:
```
   - "text": exactly ONE word (no hyphens, no compounds, no spaces)
     GOOD: flickering, frigid, shrill, dense, molten, conical, pungent
     BAD: cold metal (two words), high-pitched (hyphenated), lava-formed (compound)
     If you need "cold metal", choose ONE word: frigid, metallic, or icy
```

2. Add after the property types list:
```
   IMPORTANT: At least 4 of your properties must have type "physical" (texture, weight,
   temperature, luminosity, sound, colour, shape, size, material). Most concrete nouns
   have at least 4 physical qualities. If the concept genuinely has fewer, include as many
   as truly apply.
```

3. Add after the existing `physical:` type description, expand it:
```
   - physical: texture, weight, temperature, luminosity, sound, colour, shape, size, material, smell, taste
```

4. Add a second example after the candle example that demonstrates good physical property extraction:
```
Word: volcano
Lemmas: volcano
Definition: a mountain formed by volcanic material

{{"id": "oewn-volcano-n", "usage_example": "The volcano erupted, sending a plume of ash into the sky.", "properties": [{{"text": "hot", "salience": 0.95, "type": "physical", "relation": "volcano radiates extreme heat"}}, {{"text": "conical", "salience": 0.8, "type": "physical", "relation": "volcano has cone shape"}}, {{"text": "towering", "salience": 0.85, "type": "physical", "relation": "volcano is very tall"}}, {{"text": "molten", "salience": 0.9, "type": "physical", "relation": "contains molten lava"}}, {{"text": "ashy", "salience": 0.7, "type": "physical", "relation": "produces ash"}}, {{"text": "eruptive", "salience": 0.85, "type": "behaviour", "relation": "volcano erupts violently"}}, {{"text": "destructive", "salience": 0.75, "type": "effect", "relation": "eruptions destroy surroundings"}}, {{"text": "dormant", "salience": 0.5, "type": "behaviour", "relation": "may be inactive for years"}}, {{"text": "rumbling", "salience": 0.65, "type": "physical", "relation": "produces low sounds"}}, {{"text": "ancient", "salience": 0.4, "type": "social", "relation": "geological timescale"}}], "lemma_metadata": [{{"lemma": "volcano", "register": "neutral", "connotation": "negative"}}]}}
(NOT: magmatic, pyroclastic, geological — these are taxonomic labels, not experiential properties)
```

5. Update the candle example to use single-word properties only (the existing example is already single-word, so no change needed).

**Step 2: Verify the prompt compiles**

Run: `cd data-pipeline && ../.venv/bin/python -c "from scripts.enrich_properties import BATCH_PROMPT_V2; print('OK:', len(BATCH_PROMPT_V2), 'chars')"`
Expected: OK with character count

**Step 3: Verify {batch_items} placeholder present**

Run: `cd data-pipeline && ../.venv/bin/python -c "from scripts.enrich_properties import BATCH_PROMPT_V2; assert '{batch_items}' in BATCH_PROMPT_V2; print('placeholder OK')"`
Expected: `placeholder OK`

**Step 4: Commit**

```bash
git add data-pipeline/scripts/enrich_properties.py
git commit -m "feat: modify v2 prompt — single-word, physical minimum, volcano example"
```

---

### Task 3: Create audit_physical_coverage.py

New script that audits physical property coverage per synset using the v2 `type` field.

**Files:**
- Create: `data-pipeline/scripts/audit_physical_coverage.py`
- Create: `data-pipeline/scripts/test_audit_physical_coverage.py`

**Step 1: Write failing tests**

Create `data-pipeline/scripts/test_audit_physical_coverage.py`:

```python
"""Tests for audit_physical_coverage.py."""
import json
import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))

from audit_physical_coverage import audit_physical_coverage, POS_THRESHOLDS


def _make_test_db():
    """Create in-memory DB with synsets, synset_properties, property_vocabulary."""
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE synsets (synset_id TEXT PRIMARY KEY, pos TEXT, definition TEXT)")
    conn.execute("CREATE TABLE property_vocabulary (property_id INTEGER PRIMARY KEY, text TEXT)")
    conn.execute("""CREATE TABLE synset_properties (
        synset_id TEXT, property_id INTEGER, salience REAL DEFAULT 1.0,
        property_type TEXT, relation TEXT,
        PRIMARY KEY (synset_id, property_id)
    )""")
    return conn


def _add_synset(conn, synset_id, pos, props):
    """Helper: add a synset with properties (list of (text, type) tuples)."""
    conn.execute("INSERT INTO synsets VALUES (?, ?, 'test')", (synset_id, pos))
    for i, (text, ptype) in enumerate(props):
        pid = abs(hash(f"{synset_id}_{text}")) % 1000000
        conn.execute("INSERT OR IGNORE INTO property_vocabulary VALUES (?, ?)", (pid, text))
        conn.execute("INSERT INTO synset_properties VALUES (?, ?, 1.0, ?, NULL)",
                     (synset_id, pid, ptype))


def test_noun_with_enough_physical_not_flagged():
    """Noun with >= 4 physical properties passes audit."""
    conn = _make_test_db()
    _add_synset(conn, "syn-rock", "n", [
        ("hard", "physical"), ("heavy", "physical"),
        ("solid", "physical"), ("rough", "physical"),
        ("ancient", "social"),
    ])
    result = audit_physical_coverage(conn)
    assert len(result["flagged"]) == 0


def test_noun_with_few_physical_flagged():
    """Noun with < 4 physical properties is flagged."""
    conn = _make_test_db()
    _add_synset(conn, "syn-justice", "n", [
        ("abstract", "emotional"), ("balanced", "behaviour"),
        ("impartial", "social"), ("cold", "physical"),
    ])
    result = audit_physical_coverage(conn)
    assert len(result["flagged"]) == 1
    assert result["flagged"][0]["synset_id"] == "syn-justice"
    assert result["flagged"][0]["physical_count"] == 1


def test_verb_threshold_is_two():
    """Verb with < 2 physical properties is flagged."""
    conn = _make_test_db()
    _add_synset(conn, "syn-run", "v", [
        ("fast", "behaviour"), ("rhythmic", "behaviour"),
        ("sweaty", "physical"),
    ])
    result = audit_physical_coverage(conn)
    assert len(result["flagged"]) == 1
    assert result["flagged"][0]["physical_count"] == 1


def test_verb_with_enough_physical_not_flagged():
    """Verb with >= 2 physical properties passes."""
    conn = _make_test_db()
    _add_synset(conn, "syn-run", "v", [
        ("fast", "behaviour"), ("sweaty", "physical"), ("loud", "physical"),
    ])
    result = audit_physical_coverage(conn)
    assert len(result["flagged"]) == 0


def test_adjective_threshold_is_two():
    """Adjective with < 2 physical properties is flagged."""
    conn = _make_test_db()
    _add_synset(conn, "syn-bright", "a", [
        ("cheerful", "emotional"), ("optimistic", "emotional"),
    ])
    result = audit_physical_coverage(conn)
    assert len(result["flagged"]) == 1


def test_audit_returns_summary_stats():
    """Audit result includes total, flagged count, and per-POS breakdown."""
    conn = _make_test_db()
    _add_synset(conn, "syn-rock", "n", [
        ("hard", "physical"), ("heavy", "physical"),
        ("solid", "physical"), ("rough", "physical"),
    ])
    _add_synset(conn, "syn-justice", "n", [("fair", "social")])
    result = audit_physical_coverage(conn)
    assert result["total_audited"] == 2
    assert result["total_flagged"] == 1
    assert result["by_pos"]["n"]["flagged"] == 1


def test_synsets_without_type_annotation_flagged():
    """Synsets with NULL property_type (v1 data) are flagged — no type = 0 physical."""
    conn = _make_test_db()
    conn.execute("INSERT INTO synsets VALUES ('syn-old', 'n', 'test')")
    conn.execute("INSERT INTO property_vocabulary VALUES (1, 'hot')")
    conn.execute("INSERT INTO synset_properties VALUES ('syn-old', 1, 1.0, NULL, NULL)")
    result = audit_physical_coverage(conn)
    assert len(result["flagged"]) == 1
```

**Step 2: Run tests to verify they fail**

Run: `cd data-pipeline && ../.venv/bin/python -m pytest scripts/test_audit_physical_coverage.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'audit_physical_coverage'`

**Step 3: Implement audit_physical_coverage.py**

Create `data-pipeline/scripts/audit_physical_coverage.py`:

```python
"""Audit physical property coverage per synset.

Reads v2 enrichment data from the DB (synset_properties.property_type)
and flags synsets below POS-dependent physical property thresholds.

Usage:
    python audit_physical_coverage.py --db PATH [-o report.json]
"""
import argparse
import json
import logging
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from utils import LEXICON_V2

log = logging.getLogger(__name__)

# Minimum physical properties per POS before flagging
POS_THRESHOLDS = {
    "n": 4,  # nouns are primary metaphor vehicles
    "v": 2,  # verbs have physical dimensions but fewer
    "a": 2,  # adjectives — sensory ones are valuable
    "r": 0,  # adverbs — no physical requirement
}


def audit_physical_coverage(conn: sqlite3.Connection) -> dict:
    """Audit physical property coverage per enriched synset.

    Returns dict with:
        total_audited: int
        total_flagged: int
        by_pos: {pos: {total, flagged, threshold}}
        flagged: [{synset_id, pos, physical_count, total_count, properties}]
    """
    # Get all enriched synsets with their property type counts
    rows = conn.execute("""
        SELECT s.synset_id, s.pos,
               COUNT(sp.property_id) as total_props,
               COUNT(CASE WHEN sp.property_type = 'physical' THEN 1 END) as physical_count
        FROM synsets s
        JOIN synset_properties sp ON sp.synset_id = s.synset_id
        GROUP BY s.synset_id, s.pos
    """).fetchall()

    flagged = []
    by_pos: dict[str, dict] = {}

    for synset_id, pos, total_props, physical_count in rows:
        threshold = POS_THRESHOLDS.get(pos, 0)

        if pos not in by_pos:
            by_pos[pos] = {"total": 0, "flagged": 0, "threshold": threshold}
        by_pos[pos]["total"] += 1

        if physical_count < threshold:
            # Fetch existing property texts for the report
            prop_rows = conn.execute("""
                SELECT pv.text, sp.property_type
                FROM synset_properties sp
                JOIN property_vocabulary pv ON pv.property_id = sp.property_id
                WHERE sp.synset_id = ?
            """, (synset_id,)).fetchall()

            existing_props = [{"text": r[0], "type": r[1]} for r in prop_rows]

            flagged.append({
                "synset_id": synset_id,
                "pos": pos,
                "physical_count": physical_count,
                "total_count": total_props,
                "threshold": threshold,
                "properties": existing_props,
            })
            by_pos[pos]["flagged"] += 1

    return {
        "total_audited": len(rows),
        "total_flagged": len(flagged),
        "by_pos": by_pos,
        "flagged": flagged,
    }


def main():
    parser = argparse.ArgumentParser(
        description="Audit physical property coverage per synset.",
    )
    parser.add_argument("--db", default=str(LEXICON_V2), help="lexicon database path")
    parser.add_argument("-o", "--output", help="output JSON report path")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s: %(message)s",
    )

    conn = sqlite3.connect(args.db)
    try:
        result = audit_physical_coverage(conn)
    finally:
        conn.close()

    print(f"\n=== Physical Coverage Audit ===")
    print(f"  Audited: {result['total_audited']} synsets")
    print(f"  Flagged: {result['total_flagged']} ({result['total_flagged']/result['total_audited']*100:.1f}%)" if result['total_audited'] else "  Flagged: 0")
    for pos, stats in sorted(result["by_pos"].items()):
        pct = stats["flagged"] / stats["total"] * 100 if stats["total"] else 0
        print(f"  POS={pos}: {stats['flagged']}/{stats['total']} flagged ({pct:.0f}%), threshold={stats['threshold']}")

    if args.output:
        with open(args.output, "w") as f:
            json.dump(result, f, indent=2)
        print(f"\n  Report: {args.output}")


if __name__ == "__main__":
    main()
```

**Step 4: Run tests to verify they pass**

Run: `cd data-pipeline && ../.venv/bin/python -m pytest scripts/test_audit_physical_coverage.py -v`
Expected: ALL PASS

**Step 5: Commit**

```bash
git add data-pipeline/scripts/audit_physical_coverage.py data-pipeline/scripts/test_audit_physical_coverage.py
git commit -m "feat: add physical coverage audit script with POS-dependent thresholds"
```

---

### Task 4: Create gap_fill_physical.py

New script that runs a targeted gap-fill prompt on flagged synsets.

**Files:**
- Create: `data-pipeline/scripts/gap_fill_physical.py`
- Create: `data-pipeline/scripts/test_gap_fill_physical.py`

**Step 1: Write failing tests**

Create `data-pipeline/scripts/test_gap_fill_physical.py`:

```python
"""Tests for gap_fill_physical.py."""
import json
import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))

from gap_fill_physical import build_gap_fill_prompt, format_gap_fill_items, merge_gap_fill


GAP_FILL_PROMPT = None  # imported below after module exists


def test_format_gap_fill_items_includes_existing_props():
    """Batch item text includes existing properties for dedup."""
    items = [{
        "synset_id": "syn-justice",
        "lemma": "justice",
        "definition": "the quality of being just or fair",
        "pos": "n",
        "existing_properties": ["fair", "balanced", "impartial"],
    }]
    text = format_gap_fill_items(items)
    assert "justice" in text
    assert "fair, balanced, impartial" in text


def test_format_gap_fill_items_multiple():
    """Multiple items are separated."""
    items = [
        {"synset_id": "s1", "lemma": "a", "definition": "d1", "pos": "n",
         "existing_properties": ["x"]},
        {"synset_id": "s2", "lemma": "b", "definition": "d2", "pos": "n",
         "existing_properties": ["y"]},
    ]
    text = format_gap_fill_items(items)
    assert "s1" in text
    assert "s2" in text


def test_merge_gap_fill_appends_properties():
    """Gap-fill properties are appended to existing enrichment data."""
    existing = {
        "synsets": [
            {"id": "syn-justice", "properties": [
                {"text": "fair", "salience": 0.8, "type": "social", "relation": "justice is fair"},
            ]},
        ],
    }
    gap_fill = [
        {"id": "syn-justice", "properties": [
            {"text": "cold", "salience": 0.6, "type": "physical", "relation": "justice feels cold"},
        ]},
    ]
    merged = merge_gap_fill(existing, gap_fill)
    props = merged["synsets"][0]["properties"]
    assert len(props) == 2
    assert props[1]["text"] == "cold"


def test_merge_gap_fill_skips_duplicates():
    """Gap-fill properties that duplicate existing text are skipped."""
    existing = {
        "synsets": [
            {"id": "syn-rock", "properties": [
                {"text": "hard", "salience": 0.9, "type": "physical", "relation": "rock is hard"},
            ]},
        ],
    }
    gap_fill = [
        {"id": "syn-rock", "properties": [
            {"text": "hard", "salience": 0.8, "type": "physical", "relation": "dup"},
            {"text": "heavy", "salience": 0.7, "type": "physical", "relation": "rock is heavy"},
        ]},
    ]
    merged = merge_gap_fill(existing, gap_fill)
    props = merged["synsets"][0]["properties"]
    texts = [p["text"] for p in props]
    assert texts.count("hard") == 1
    assert "heavy" in texts


def test_merge_gap_fill_ignores_unknown_synset():
    """Gap-fill for synsets not in existing data is ignored."""
    existing = {"synsets": [{"id": "syn-rock", "properties": []}]}
    gap_fill = [{"id": "syn-unknown", "properties": [{"text": "x", "salience": 0.5, "type": "physical", "relation": ""}]}]
    merged = merge_gap_fill(existing, gap_fill)
    assert len(merged["synsets"]) == 1
```

**Step 2: Run tests to verify they fail**

Run: `cd data-pipeline && ../.venv/bin/python -m pytest scripts/test_gap_fill_physical.py -v`
Expected: FAIL with `ModuleNotFoundError`

**Step 3: Implement gap_fill_physical.py**

Create `data-pipeline/scripts/gap_fill_physical.py`:

```python
"""Gap-fill physical properties for synsets flagged by coverage audit.

Takes an audit report JSON (from audit_physical_coverage.py) and runs
a targeted prompt asking the LLM to add missing physical/sensory
properties. Existing properties are shown to avoid duplication.

Usage:
    python gap_fill_physical.py --db PATH --audit report.json -o gap_fill.json [--model sonnet]
"""
import argparse
import json
import logging
import sqlite3
import sys
from pathlib import Path
from typing import List, Dict

sys.path.insert(0, str(Path(__file__).parent))
from utils import LEXICON_V2

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "lib"))
from claude_client import prompt_json, RateLimitError

log = logging.getLogger(__name__)

GAP_FILL_PROMPT = """You are adding missing physical and sensory properties to word senses that lack them.

Below are word senses with their EXISTING properties. Your job is to add ONLY physical/sensory
properties that are missing. Do NOT duplicate any existing property.

Physical/sensory properties describe: texture, weight, temperature, luminosity, sound, colour,
shape, size, material, smell, taste, motion.

CONSTRAINTS:
- Every property MUST be exactly one word. No hyphens, no compounds, no spaces.
- Only add properties with type "physical".
- Do NOT repeat or rephrase any existing property.
- Add 3-6 physical properties per synset — enough to ground it, not more.
- Use the same JSON format: {{"text": "...", "salience": 0.0-1.0, "type": "physical", "relation": "..."}}
- "relation" is a short phrase linking the word to the property (e.g. "rock is heavy").

{batch_items}

Output ONLY a valid JSON array (no markdown, no explanation):
[{{"id": "...", "properties": [...]}}, ...]
"""


def build_gap_fill_prompt(batch_items_text: str) -> str:
    """Build the gap-fill prompt with batch items inserted."""
    return GAP_FILL_PROMPT.replace("{batch_items}", batch_items_text)


def format_gap_fill_items(items: List[Dict]) -> str:
    """Format flagged synsets for the gap-fill prompt.

    Each item includes existing properties so the LLM avoids duplicates.
    """
    lines = []
    for item in items:
        lines.append(f"ID: {item['synset_id']}")
        lines.append(f"Word: {item['lemma']}")
        lines.append(f"Definition: {item['definition']}")
        existing = ", ".join(item.get("existing_properties", []))
        lines.append(f"Existing properties: {existing}")
        lines.append("")
    return "\n".join(lines)


def merge_gap_fill(existing_data: dict, gap_fill_results: list[dict]) -> dict:
    """Merge gap-fill properties into existing enrichment data.

    Appends new properties, skipping any whose text matches an existing property.
    Returns a new dict (does not mutate existing_data).
    """
    import copy
    merged = copy.deepcopy(existing_data)

    synset_map = {s["id"]: s for s in merged.get("synsets", [])}

    for entry in gap_fill_results:
        sid = entry["id"]
        if sid not in synset_map:
            log.warning("gap-fill synset %s not in existing data, skipping", sid)
            continue

        existing_texts = {p["text"] for p in synset_map[sid].get("properties", [])
                         if isinstance(p, dict)}

        for prop in entry.get("properties", []):
            if isinstance(prop, dict) and prop.get("text") not in existing_texts:
                synset_map[sid]["properties"].append(prop)
                existing_texts.add(prop["text"])

    return merged


def main():
    parser = argparse.ArgumentParser(
        description="Gap-fill physical properties for flagged synsets.",
    )
    parser.add_argument("--db", default=str(LEXICON_V2), help="lexicon database path")
    parser.add_argument("--audit", required=True, help="path to audit report JSON")
    parser.add_argument("-o", "--output", required=True, help="output gap-fill JSON path")
    parser.add_argument("--model", default="sonnet", help="LLM model (default: sonnet)")
    parser.add_argument("--batch-size", type=int, default=20, help="synsets per LLM call")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s: %(message)s",
    )

    with open(args.audit) as f:
        audit = json.load(f)

    flagged = audit.get("flagged", [])
    if not flagged:
        print("No synsets flagged — nothing to gap-fill.")
        return

    # Look up lemma and definition for each flagged synset
    conn = sqlite3.connect(args.db)
    try:
        items = []
        for entry in flagged:
            sid = entry["synset_id"]
            row = conn.execute(
                "SELECT s.definition FROM synsets s WHERE s.synset_id = ?", (sid,)
            ).fetchone()
            lemma_row = conn.execute(
                "SELECT lemma FROM lemmas WHERE synset_id = ? LIMIT 1", (sid,)
            ).fetchone()
            if row and lemma_row:
                existing_texts = [p["text"] for p in entry.get("properties", [])
                                  if isinstance(p, dict)]
                items.append({
                    "synset_id": sid,
                    "lemma": lemma_row[0],
                    "definition": row[0],
                    "pos": entry["pos"],
                    "existing_properties": existing_texts,
                })
    finally:
        conn.close()

    print(f"Gap-filling {len(items)} synsets in batches of {args.batch_size}...")

    all_results = []
    for i in range(0, len(items), args.batch_size):
        batch = items[i:i + args.batch_size]
        batch_text = format_gap_fill_items(batch)
        prompt = build_gap_fill_prompt(batch_text)

        log.info("[%d/%d] Processing batch of %d synsets...",
                 i // args.batch_size + 1,
                 (len(items) + args.batch_size - 1) // args.batch_size,
                 len(batch))

        try:
            results = prompt_json(prompt, model=args.model, expect=list)
            all_results.extend(results)
        except (RateLimitError, Exception) as exc:
            log.error("Batch %d failed: %s", i // args.batch_size + 1, exc)
            continue

    output = {"synsets": all_results, "source": "gap_fill", "model": args.model}
    with open(args.output, "w") as f:
        json.dump(output, f, indent=2)

    print(f"\nGap-fill complete: {len(all_results)} synsets → {args.output}")


if __name__ == "__main__":
    main()
```

**Step 4: Run tests to verify they pass**

Run: `cd data-pipeline && ../.venv/bin/python -m pytest scripts/test_gap_fill_physical.py -v`
Expected: ALL PASS

**Step 5: Commit**

```bash
git add data-pipeline/scripts/gap_fill_physical.py data-pipeline/scripts/test_gap_fill_physical.py
git commit -m "feat: add gap-fill script for physical property enrichment"
```

---

### Task 5: Update documentation

**Files:**
- Modify: `data-pipeline/CLAUDE.md`
- Modify: `docs/designs/cascade-scoring-roadmap.md`

**Step 1: Add Operation 6 to data-pipeline/CLAUDE.md**

After the Operation 5 (Concreteness Regression) section, add:

```markdown
### 6. Physical Coverage Audit & Gap-fill

Audit physical property coverage per synset and gap-fill flagged synsets with a targeted prompt.

```bash
# Audit — writes JSON report with flagged synsets
source .venv/bin/activate
python data-pipeline/scripts/audit_physical_coverage.py \
  --db data-pipeline/output/lexicon_v2.db -o data-pipeline/output/audit_physical.json

# Gap-fill flagged synsets — runs LLM on flagged synsets only
python data-pipeline/scripts/gap_fill_physical.py \
  --db data-pipeline/output/lexicon_v2.db \
  --audit data-pipeline/output/audit_physical.json \
  -o data-pipeline/output/gap_fill_physical.json --model sonnet

# Import gap-fill into DB (use enrich.sh --from-json with both files)
./data-pipeline/enrich.sh --db data-pipeline/output/lexicon_v2.db \
  --from-json data-pipeline/output/enrichment_*.json data-pipeline/output/gap_fill_physical.json
```

POS-dependent thresholds: nouns >= 4, verbs >= 2, adjectives >= 2 physical properties.
```

**Step 2: Add audit + gap-fill to shell scripts table**

Add row: `| audit_physical_coverage.py | Audit physical property coverage, flag under-covered synsets |`
Add row: `| gap_fill_physical.py | Targeted LLM gap-fill for synsets lacking physical properties |`

**Step 3: Update cascade-scoring-roadmap.md**

Mark the dual-prompt strategy as designed, note the v2 prompt modifications.

**Step 4: Commit**

```bash
git add data-pipeline/CLAUDE.md docs/designs/cascade-scoring-roadmap.md
git commit -m "docs: add physical coverage audit and gap-fill operations"
```

---

### Task 6: Run full test suite and verify

**Step 1: Run all Python tests**

Run: `cd data-pipeline && ../.venv/bin/python -m pytest scripts/ -v`
Expected: ALL PASS

**Step 2: Run all Go tests**

Run: `export PATH="/usr/local/go/bin:$PATH" && cd api && go test ./...`
Expected: ALL PASS

**Step 3: Commit any final fixes if needed**
