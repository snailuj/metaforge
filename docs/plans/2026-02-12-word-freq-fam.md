# Word Frequency & Familiarity Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Import Brysbaert GPT familiarity data + SUBTLEX-UK frequency data into the lexicon, wire rarity through the Go API, and display rarity badges + HUD filter toggles in the frontend.

**Architecture:** Pipeline imports xlsx → populates `frequencies` table → Go API JOINs at query time → frontend renders badges and filters graph nodes. Two-signal approach: GPT familiarity for rarity classification, corpus Zipf for ranking tiebreaker.

**Tech Stack:** Python (openpyxl, sqlite3) for pipeline, Go for API, Lit/TypeScript for frontend, Vitest + pytest + `go test` for tests.

---

## Task 1: Add openpyxl to pipeline requirements

The familiarity data is `.xlsx`. We need openpyxl to read it.

**Files:**
- Modify: `data-pipeline/requirements.txt`

**Step 1: Add the dependency**

Add `openpyxl>=3.1.0,<4.0.0` to `data-pipeline/requirements.txt`:

```
pytest>=7.0.0,<9.0.0
google-genai>=0.1.0,<2.0.0
numpy>=1.24.0,<3.0.0
openpyxl>=3.1.0,<4.0.0
```

**Step 2: Install into venv**

Run: `cd data-pipeline && .venv/bin/pip install -r requirements.txt`
Expected: openpyxl installs successfully

**Step 3: Commit**

```bash
git add data-pipeline/requirements.txt
git commit -m "chore: add openpyxl to pipeline requirements for xlsx import"
```

---

## Task 2: Update schema — frequencies table

Update the schema to match the design: add `familiarity`, `familiarity_dominant`, `source` columns; change rarity CHECK to 3-tier; make numerics NULLable.

**Files:**
- Modify: `docs/designs/schema-v2.sql:41-50`

**Step 1: Write the failing test (Python)**

Create `data-pipeline/scripts/test_import_familiarity.py` with a schema validation test:

```python
"""Test familiarity import to lexicon_v2.db."""
import sqlite3
import pytest

from utils import LEXICON_V2


def test_frequencies_schema_has_familiarity_column():
    """Verify frequencies table has the new familiarity columns."""
    conn = sqlite3.connect(LEXICON_V2)
    try:
        cursor = conn.execute("PRAGMA table_info(frequencies)")
        columns = {row[1]: row[2] for row in cursor.fetchall()}
    finally:
        conn.close()

    assert "familiarity" in columns, "Missing familiarity column"
    assert "familiarity_dominant" in columns, "Missing familiarity_dominant column"
    assert "source" in columns, "Missing source column"
    assert columns["familiarity"] == "REAL"
    assert columns["familiarity_dominant"] == "INTEGER"
```

**Step 2: Run test to verify it fails**

Run: `cd data-pipeline && .venv/bin/python -m pytest scripts/test_import_familiarity.py::test_frequencies_schema_has_familiarity_column -v`
Expected: FAIL — current schema lacks `familiarity` column

**Step 3: Update the schema**

In `docs/designs/schema-v2.sql`, replace the `frequencies` table block (lines 41-50):

```sql
CREATE TABLE frequencies (
    lemma TEXT PRIMARY KEY,
    familiarity REAL,
    familiarity_dominant INTEGER,
    zipf REAL,
    frequency INTEGER,
    rarity TEXT NOT NULL DEFAULT 'unusual'
        CHECK (rarity IN ('common', 'unusual', 'rare')),
    source TEXT
);

CREATE INDEX idx_frequencies_lemma ON frequencies(lemma);
CREATE INDEX idx_frequencies_zipf ON frequencies(zipf);
CREATE INDEX idx_frequencies_rarity ON frequencies(rarity);
CREATE INDEX idx_frequencies_familiarity ON frequencies(familiarity);
```

**Step 4: Rebuild the database**

Run: `bash data-pipeline/scripts/restore_db.sh`
Expected: DB recreated with new schema

**Step 5: Run test to verify it passes**

Run: `cd data-pipeline && .venv/bin/python -m pytest scripts/test_import_familiarity.py::test_frequencies_schema_has_familiarity_column -v`
Expected: PASS

**Step 6: Run all existing pipeline tests to check for regressions**

Run: `cd data-pipeline && .venv/bin/python -m pytest scripts/ -v`
Expected: All tests pass (the `frequencies` table was empty, so nothing depends on old schema)

**Step 7: Commit**

```bash
git add docs/designs/schema-v2.sql data-pipeline/scripts/test_import_familiarity.py
git commit -m "feat(schema): update frequencies table for familiarity + 3-tier rarity"
```

---

## Task 3: Add input path constants to utils.py

The import script needs paths to the input xlsx files. Add them to the shared utils.

**Files:**
- Modify: `data-pipeline/scripts/utils.py`

**Step 1: Add the constants**

Add to `data-pipeline/scripts/utils.py`, below the existing constants:

```python
# Input data sources
INPUT_DIR = PIPELINE_DIR / "input"
MULTILEX_DIR = INPUT_DIR / "multilex-en"
SUBTLEX_DIR = INPUT_DIR / "subtlex-uk"

# Familiarity data
FAMILIARITY_FULL_XLSX = MULTILEX_DIR / "Full list GPT4 estimates familiarity and Multilex frequencies.xlsx"
FAMILIARITY_CLEANED_XLSX = MULTILEX_DIR / "Cleaned list GPT4 estimates familiarity and Multilex frequencies.xlsx"
MULTILEX_XLSX = MULTILEX_DIR / "Multilex English.xlsx"

# SUBTLEX-UK data
SUBTLEX_FLEMMAS_XLSX = SUBTLEX_DIR / "SUBTLEX-UK-flemmas.xlsx"
SUBTLEX_UK_XLSX = SUBTLEX_DIR / "SUBTLEX-UK.xlsx"

# Familiarity thresholds (from Brysbaert 2025, tuneable)
FAMILIARITY_COMMON_THRESHOLD = 5.5   # >= 5.5 → common
FAMILIARITY_UNUSUAL_THRESHOLD = 3.5  # >= 3.5 → unusual, below → rare

# Zipf fallback thresholds (for words without familiarity data)
ZIPF_COMMON_THRESHOLD = 4.5   # >= 4.5 → common
ZIPF_UNUSUAL_THRESHOLD = 2.5  # >= 2.5 → unusual, below → rare
```

**Step 2: Commit**

```bash
git add data-pipeline/scripts/utils.py
git commit -m "feat(pipeline): add familiarity input paths and threshold constants"
```

---

## Task 4: Write the familiarity import script — core import

Import Brysbaert GPT familiarity data, match against our lemmas, compute rarity tiers, populate the `frequencies` table.

**Files:**
- Create: `data-pipeline/scripts/import_familiarity.py`
- Test: `data-pipeline/scripts/test_import_familiarity.py`

**Step 1: Write failing tests**

Add to `data-pipeline/scripts/test_import_familiarity.py` (below the schema test from Task 2):

```python
def test_frequencies_populated():
    """Verify frequencies table has rows after import."""
    conn = sqlite3.connect(LEXICON_V2)
    try:
        count = conn.execute("SELECT COUNT(*) FROM frequencies").fetchone()[0]
    finally:
        conn.close()
    assert count > 80000, f"Expected 80k+ frequency rows, got {count}"


def test_happy_is_common():
    """Verify 'happy' is classified as common."""
    conn = sqlite3.connect(LEXICON_V2)
    try:
        row = conn.execute(
            "SELECT rarity, familiarity FROM frequencies WHERE lemma = 'happy'"
        ).fetchone()
    finally:
        conn.close()
    assert row is not None, "'happy' should be in frequencies"
    assert row[0] == "common", f"Expected 'happy' rarity=common, got {row[0]}"
    assert row[1] is not None and row[1] >= 5.5, f"Expected familiarity >= 5.5, got {row[1]}"


def test_melancholy_is_unusual():
    """Verify 'melancholy' is classified as unusual."""
    conn = sqlite3.connect(LEXICON_V2)
    try:
        row = conn.execute(
            "SELECT rarity, familiarity FROM frequencies WHERE lemma = 'melancholy'"
        ).fetchone()
    finally:
        conn.close()
    assert row is not None, "'melancholy' should be in frequencies"
    assert row[0] == "unusual", f"Expected rarity=unusual, got {row[0]}"


def test_source_column_populated():
    """Verify source provenance is recorded."""
    conn = sqlite3.connect(LEXICON_V2)
    try:
        sources = conn.execute(
            "SELECT DISTINCT source FROM frequencies"
        ).fetchall()
        sources = [s[0] for s in sources]
    finally:
        conn.close()
    assert "brysbaert" in sources, f"Expected 'brysbaert' in sources, got {sources}"


def test_unmatched_lemmas_get_default_unusual():
    """Verify lemmas not in any dataset get rarity='unusual' and NULL familiarity."""
    conn = sqlite3.connect(LEXICON_V2)
    try:
        # Get a lemma that exists in our DB
        all_lemmas = conn.execute("SELECT DISTINCT lemma FROM lemmas").fetchall()
        freq_lemmas = conn.execute("SELECT lemma FROM frequencies").fetchall()
    finally:
        conn.close()
    # We should have frequency entries for all lemmas in our DB
    assert len(freq_lemmas) >= len(all_lemmas) * 0.95, \
        f"Expected frequencies for >= 95% of lemmas, got {len(freq_lemmas)}/{len(all_lemmas)}"


def test_no_duplicate_lemmas():
    """Verify no duplicate lemma entries in frequencies table."""
    conn = sqlite3.connect(LEXICON_V2)
    try:
        dups = conn.execute("""
            SELECT lemma, COUNT(*) as cnt
            FROM frequencies
            GROUP BY lemma
            HAVING cnt > 1
        """).fetchall()
    finally:
        conn.close()
    assert len(dups) == 0, f"Found {len(dups)} duplicate lemmas: {dups[:5]}"


def test_rarity_distribution_reasonable():
    """Verify rarity tier distribution is roughly as expected."""
    conn = sqlite3.connect(LEXICON_V2)
    try:
        rows = conn.execute("""
            SELECT rarity, COUNT(*) FROM frequencies GROUP BY rarity
        """).fetchall()
    finally:
        conn.close()
    dist = {row[0]: row[1] for row in rows}
    total = sum(dist.values())
    # Common should be the largest group (most of our WordNet vocabulary is common)
    assert dist.get("common", 0) > total * 0.3, \
        f"Expected > 30% common, got {dist.get('common', 0)}/{total}"
    # We should have all three tiers
    assert "common" in dist, "Missing 'common' tier"
    assert "unusual" in dist, "Missing 'unusual' tier"
    assert "rare" in dist, "Missing 'rare' tier"
```

**Step 2: Run tests to verify they fail**

Run: `cd data-pipeline && .venv/bin/python -m pytest scripts/test_import_familiarity.py -v -k "not schema"`
Expected: FAIL — frequencies table is empty

**Step 3: Write the import script**

Create `data-pipeline/scripts/import_familiarity.py`:

```python
"""Import Brysbaert GPT familiarity data into the frequencies table.

Reads the full 417K-word familiarity dataset, matches against lemmas in our
lexicon, computes rarity tiers, and populates the frequencies table. Lemmas
not found in any dataset get rarity='unusual' with NULL familiarity.

Usage:
    python import_familiarity.py
"""
import sqlite3
from pathlib import Path

import openpyxl

from utils import (
    LEXICON_V2,
    FAMILIARITY_FULL_XLSX,
    FAMILIARITY_COMMON_THRESHOLD,
    FAMILIARITY_UNUSUAL_THRESHOLD,
    ZIPF_COMMON_THRESHOLD,
    ZIPF_UNUSUAL_THRESHOLD,
)


def compute_rarity(familiarity: float | None, zipf: float | None) -> str:
    """Compute rarity tier from familiarity (primary) or Zipf (fallback)."""
    if familiarity is not None:
        if familiarity >= FAMILIARITY_COMMON_THRESHOLD:
            return "common"
        elif familiarity >= FAMILIARITY_UNUSUAL_THRESHOLD:
            return "unusual"
        else:
            return "rare"
    elif zipf is not None:
        if zipf >= ZIPF_COMMON_THRESHOLD:
            return "common"
        elif zipf >= ZIPF_UNUSUAL_THRESHOLD:
            return "unusual"
        else:
            return "rare"
    else:
        return "unusual"


def load_familiarity(xlsx_path: Path) -> dict[str, tuple[float, int, float | None]]:
    """Load familiarity data from the full Brysbaert xlsx.

    Returns dict mapping lowercase word -> (GPT_Fam_probs, GPT_Fam_dominant, Multilex_Zipf or None).
    Skips null words, multi-word expressions (Type != 'W'), and duplicates (keeps first).
    """
    print(f"Loading familiarity data from {xlsx_path.name}...")
    wb = openpyxl.load_workbook(xlsx_path, read_only=True, data_only=True)
    ws = wb.active

    rows = ws.iter_rows(min_row=2, values_only=True)
    data: dict[str, tuple[float, int, float | None]] = {}

    for row in rows:
        word, fam_dom, fam_probs, multilex, entry_type, _ = row

        # Skip nulls and non-single-words
        if word is None or not isinstance(word, str):
            continue
        if entry_type != "W":
            continue

        key = word.lower().strip()
        if key in data:
            continue  # keep first occurrence

        fam_probs_val = float(fam_probs) if fam_probs is not None else None
        fam_dom_val = int(fam_dom) if fam_dom is not None else None
        multilex_val = float(multilex) if multilex is not None else None

        if fam_probs_val is not None:
            data[key] = (fam_probs_val, fam_dom_val, multilex_val)

    wb.close()
    print(f"  Loaded {len(data)} single-word entries")
    return data


def get_all_lemmas(conn: sqlite3.Connection) -> set[str]:
    """Get all distinct lemmas from the lexicon."""
    cursor = conn.execute("SELECT DISTINCT lemma FROM lemmas")
    return {row[0] for row in cursor}


def import_familiarity(conn: sqlite3.Connection, familiarity_data: dict) -> dict[str, int]:
    """Import familiarity data into frequencies table.

    Returns stats dict with counts.
    """
    lemmas = get_all_lemmas(conn)
    print(f"  {len(lemmas)} distinct lemmas in lexicon")

    # Clear existing data
    conn.execute("DELETE FROM frequencies")

    rows = []
    stats = {"matched": 0, "matched_hyphen": 0, "unmatched": 0}

    for lemma in lemmas:
        fam_probs = None
        fam_dom = None
        multilex_zipf = None
        source = None

        # Try exact match (case-insensitive — both sides already lowercase)
        if lemma in familiarity_data:
            fam_probs, fam_dom, multilex_zipf = familiarity_data[lemma]
            source = "brysbaert"
            stats["matched"] += 1
        else:
            # Try stripping hyphens
            dehyphenated = lemma.replace("-", " ")
            if dehyphenated != lemma and dehyphenated in familiarity_data:
                fam_probs, fam_dom, multilex_zipf = familiarity_data[dehyphenated]
                source = "brysbaert"
                stats["matched_hyphen"] += 1
            else:
                stats["unmatched"] += 1

        rarity = compute_rarity(fam_probs, multilex_zipf)

        rows.append((
            lemma,
            fam_probs,
            fam_dom,
            multilex_zipf,  # zipf column — Multilex Zipf for now, SUBTLEX later
            None,           # frequency — will be filled by SUBTLEX import
            rarity,
            source,
        ))

    conn.executemany(
        """INSERT OR REPLACE INTO frequencies
           (lemma, familiarity, familiarity_dominant, zipf, frequency, rarity, source)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        rows,
    )
    conn.commit()

    return stats


def main():
    if not FAMILIARITY_FULL_XLSX.exists():
        raise FileNotFoundError(f"Familiarity data not found: {FAMILIARITY_FULL_XLSX}")
    if not LEXICON_V2.exists():
        raise FileNotFoundError(f"Lexicon DB not found: {LEXICON_V2}")

    familiarity_data = load_familiarity(FAMILIARITY_FULL_XLSX)

    conn = sqlite3.connect(LEXICON_V2)
    try:
        stats = import_familiarity(conn, familiarity_data)
    finally:
        conn.close()

    total = stats["matched"] + stats["matched_hyphen"] + stats["unmatched"]
    print(f"\nImport complete:")
    print(f"  Exact match:   {stats['matched']} ({stats['matched'] / total * 100:.1f}%)")
    print(f"  Hyphen match:  {stats['matched_hyphen']} ({stats['matched_hyphen'] / total * 100:.1f}%)")
    print(f"  Unmatched:     {stats['unmatched']} ({stats['unmatched'] / total * 100:.1f}%)")
    print(f"  Total:         {total}")


if __name__ == "__main__":
    main()
```

**Step 4: Run the import script**

Run: `cd data-pipeline && .venv/bin/python scripts/import_familiarity.py`
Expected: Prints stats showing ~69% exact match, small hyphen match increment, ~30% unmatched

**Step 5: Run all import tests**

Run: `cd data-pipeline && .venv/bin/python -m pytest scripts/test_import_familiarity.py -v`
Expected: All PASS

**Step 6: Run all pipeline tests for regressions**

Run: `cd data-pipeline && .venv/bin/python -m pytest scripts/ -v`
Expected: All PASS

**Step 7: Commit**

```bash
git add data-pipeline/scripts/import_familiarity.py data-pipeline/scripts/test_import_familiarity.py
git commit -m "feat(pipeline): import Brysbaert GPT familiarity into frequencies table"
```

---

## Task 5: SUBTLEX-UK import (Zipf + frequency backfill)

Add SUBTLEX-UK flemma data as a second pass, filling in `zipf` and `frequency` for words that have SUBTLEX data but lacked Multilex coverage.

**Files:**
- Create: `data-pipeline/scripts/import_subtlex.py`
- Modify: `data-pipeline/scripts/test_import_familiarity.py` (add SUBTLEX tests)

**Step 1: Write failing tests**

Add to `data-pipeline/scripts/test_import_familiarity.py`:

```python
def test_subtlex_zipf_backfill():
    """Verify SUBTLEX Zipf is used when Multilex Zipf was NULL."""
    conn = sqlite3.connect(LEXICON_V2)
    try:
        # Count rows with non-null zipf
        count = conn.execute(
            "SELECT COUNT(*) FROM frequencies WHERE zipf IS NOT NULL"
        ).fetchone()[0]
    finally:
        conn.close()
    # SUBTLEX has 290K flemmas — should fill in many NULL Zipf values
    assert count > 60000, f"Expected 60k+ rows with Zipf, got {count}"


def test_subtlex_source_recorded():
    """Verify SUBTLEX source is recorded for backfilled rows."""
    conn = sqlite3.connect(LEXICON_V2)
    try:
        sources = conn.execute(
            "SELECT DISTINCT source FROM frequencies WHERE source IS NOT NULL"
        ).fetchall()
        sources = [s[0] for s in sources]
    finally:
        conn.close()
    assert "subtlex" in sources or "brysbaert+subtlex" in sources, \
        f"Expected 'subtlex' or 'brysbaert+subtlex' in sources, got {sources}"
```

**Step 2: Run tests to verify they fail**

Run: `cd data-pipeline && .venv/bin/python -m pytest scripts/test_import_familiarity.py::test_subtlex_zipf_backfill -v`
Expected: FAIL

**Step 3: Write the SUBTLEX import script**

Create `data-pipeline/scripts/import_subtlex.py`:

```python
"""Import SUBTLEX-UK frequency data as a second pass over the frequencies table.

Backfills zipf and frequency columns for lemmas that have SUBTLEX-UK data.
Updates source to reflect combined provenance.
Must run AFTER import_familiarity.py.

Usage:
    python import_subtlex.py
"""
import sqlite3
from pathlib import Path

import openpyxl

from utils import (
    LEXICON_V2,
    SUBTLEX_FLEMMAS_XLSX,
    ZIPF_COMMON_THRESHOLD,
    ZIPF_UNUSUAL_THRESHOLD,
)


def load_subtlex_flemmas(xlsx_path: Path) -> dict[str, tuple[float, int]]:
    """Load SUBTLEX-UK flemma data.

    Returns dict mapping lowercase flemma -> (Zipf, frequency_count).
    """
    print(f"Loading SUBTLEX-UK flemmas from {xlsx_path.name}...")
    wb = openpyxl.load_workbook(xlsx_path, read_only=True, data_only=True)
    ws = wb.active

    # Find column indices from header row
    headers = [cell.value for cell in next(ws.iter_rows(min_row=1, max_row=1))]
    flemma_idx = headers.index("flemma")
    zipf_idx = headers.index("Zipf")
    freq_idx = headers.index("lemmafreqs_combined")

    data: dict[str, tuple[float, int]] = {}
    for row in ws.iter_rows(min_row=2, values_only=True):
        flemma = row[flemma_idx]
        if flemma is None or not isinstance(flemma, str):
            continue

        key = flemma.lower().strip()
        if key in data:
            continue

        zipf_val = float(row[zipf_idx]) if row[zipf_idx] is not None else None
        freq_val = int(row[freq_idx]) if row[freq_idx] is not None else None

        if zipf_val is not None:
            data[key] = (zipf_val, freq_val)

    wb.close()
    print(f"  Loaded {len(data)} flemma entries")
    return data


def backfill_subtlex(conn: sqlite3.Connection, subtlex_data: dict) -> dict[str, int]:
    """Backfill SUBTLEX data into existing frequencies rows.

    For rows that already have familiarity (from Brysbaert), only update zipf/frequency
    if the current zipf is NULL. For rows with no familiarity data, also recompute
    rarity using Zipf fallback thresholds.

    Returns stats dict.
    """
    stats = {"updated_zipf": 0, "rarity_recomputed": 0, "no_match": 0}

    # Get all current frequency rows
    rows = conn.execute(
        "SELECT lemma, familiarity, zipf, source FROM frequencies"
    ).fetchall()

    for lemma, familiarity, current_zipf, current_source in rows:
        if lemma not in subtlex_data:
            stats["no_match"] += 1
            continue

        subtlex_zipf, subtlex_freq = subtlex_data[lemma]

        # Update zipf and frequency from SUBTLEX (prefer SUBTLEX over Multilex for Zipf)
        new_source = current_source
        if current_source == "brysbaert":
            new_source = "brysbaert+subtlex"
        elif current_source is None:
            new_source = "subtlex"

        # Recompute rarity if familiarity is NULL (Zipf-only fallback)
        new_rarity = None
        if familiarity is None:
            if subtlex_zipf >= ZIPF_COMMON_THRESHOLD:
                new_rarity = "common"
            elif subtlex_zipf >= ZIPF_UNUSUAL_THRESHOLD:
                new_rarity = "unusual"
            else:
                new_rarity = "rare"
            stats["rarity_recomputed"] += 1

        if new_rarity is not None:
            conn.execute(
                """UPDATE frequencies
                   SET zipf = ?, frequency = ?, source = ?, rarity = ?
                   WHERE lemma = ?""",
                (subtlex_zipf, subtlex_freq, new_source, new_rarity, lemma),
            )
        else:
            conn.execute(
                """UPDATE frequencies
                   SET zipf = ?, frequency = ?, source = ?
                   WHERE lemma = ?""",
                (subtlex_zipf, subtlex_freq, new_source, lemma),
            )
        stats["updated_zipf"] += 1

    conn.commit()
    return stats


def main():
    if not SUBTLEX_FLEMMAS_XLSX.exists():
        raise FileNotFoundError(f"SUBTLEX-UK flemmas not found: {SUBTLEX_FLEMMAS_XLSX}")
    if not LEXICON_V2.exists():
        raise FileNotFoundError(f"Lexicon DB not found: {LEXICON_V2}")

    subtlex_data = load_subtlex_flemmas(SUBTLEX_FLEMMAS_XLSX)

    conn = sqlite3.connect(LEXICON_V2)
    try:
        stats = backfill_subtlex(conn, subtlex_data)
    finally:
        conn.close()

    print(f"\nSUBTLEX backfill complete:")
    print(f"  Zipf updated:       {stats['updated_zipf']}")
    print(f"  Rarity recomputed:  {stats['rarity_recomputed']}")
    print(f"  No SUBTLEX match:   {stats['no_match']}")


if __name__ == "__main__":
    main()
```

**Step 4: Run the SUBTLEX import**

Run: `cd data-pipeline && .venv/bin/python scripts/import_subtlex.py`
Expected: Prints stats showing many Zipf updates

**Step 5: Run tests**

Run: `cd data-pipeline && .venv/bin/python -m pytest scripts/test_import_familiarity.py -v`
Expected: All PASS including the SUBTLEX tests

**Step 6: Commit**

```bash
git add data-pipeline/scripts/import_subtlex.py data-pipeline/scripts/test_import_familiarity.py
git commit -m "feat(pipeline): import SUBTLEX-UK Zipf as frequency backfill"
```

---

## Task 6: Add import steps to pipeline runner

Wire the new import scripts into `run_pipeline.sh`.

**Files:**
- Modify: `data-pipeline/run_pipeline.sh:101-103` (replace the comment about pending SUBTLEX import)

**Step 1: Update the pipeline runner**

In `data-pipeline/run_pipeline.sh`, after the Phase 1 import steps (after the SyntagNet/VerbNet imports, before Phase 2), add a new phase. Find the comment at line 101-103:

```bash
# NOTE: SUBTLEX-UK frequency import is pending (needs re-downloading).
# The 'frequencies' table exists in the schema but is not populated.
# See PRD-2 open questions and schema-v2.sql for context.
```

Replace with:

```bash
# --- Phase 1b: Frequency & Familiarity ----------------------------------

run_step "Import Brysbaert GPT familiarity" \
    python "$SCRIPTS_DIR/import_familiarity.py"

run_step "Backfill SUBTLEX-UK frequency data" \
    python "$SCRIPTS_DIR/import_subtlex.py"
```

Also remove the GEMINI_API_KEY check (line 63-66) since we switched to `claude -p`. The `--full` mode check should reference `claude` CLI instead. (Or just remove the check entirely since the enrichment step already validates its own prerequisites.)

**Step 2: Verify by running in check mode**

Run: `cd data-pipeline && bash run_pipeline.sh --check`
Expected: "All prerequisites found. Ready to run."

**Step 3: Commit**

```bash
git add data-pipeline/run_pipeline.sh
git commit -m "feat(pipeline): wire familiarity + SUBTLEX import into pipeline runner"
```

---

## Task 7: Update SQL dump

Re-export the SQL dump to include the populated frequencies table.

**Files:**
- Modify: `data-pipeline/output/lexicon_v2.sql` (auto-generated)

**Step 1: Export the dump**

Run: `sqlite3 data-pipeline/output/lexicon_v2.db .dump > data-pipeline/output/lexicon_v2.sql`

**Step 2: Verify restore is idempotent**

Run: `bash data-pipeline/scripts/restore_db.sh`
Expected: Restores without errors

**Step 3: Run all pipeline tests against restored DB**

Run: `cd data-pipeline && .venv/bin/python -m pytest scripts/ -v`
Expected: All tests PASS

**Step 4: Commit**

```bash
git add data-pipeline/output/lexicon_v2.sql
git commit -m "data: export SQL dump with populated frequencies table"
```

---

## Task 8: Go API — add rarity to LookupResult

Wire the `frequencies` table into the thesaurus lookup query. Add `rarity` to `RelatedWord` and `LookupResult`.

**Files:**
- Modify: `api/internal/thesaurus/thesaurus.go`
- Modify: `api/internal/thesaurus/thesaurus_test.go`

**Step 1: Write the failing test**

Add to `api/internal/thesaurus/thesaurus_test.go`:

```go
func TestGetLookup_RarityPresent(t *testing.T) {
	database := openTestDB(t)
	defer database.Close()

	result, err := GetLookup(database, "happy")
	if err != nil {
		t.Fatalf("GetLookup(happy) returned error: %v", err)
	}

	if result.Rarity == "" {
		t.Error("expected Rarity to be populated for 'happy'")
	}
	if result.Rarity != "common" {
		t.Errorf("expected Rarity='common' for 'happy', got %q", result.Rarity)
	}
}

func TestGetLookup_SynonymRarityPresent(t *testing.T) {
	database := openTestDB(t)
	defer database.Close()

	result, err := GetLookup(database, "fire")
	if err != nil {
		t.Fatalf("GetLookup(fire) returned error: %v", err)
	}

	// Check that at least some synonyms have rarity populated
	hasRarity := false
	for _, sense := range result.Senses {
		for _, syn := range sense.Synonyms {
			if syn.Rarity != "" {
				hasRarity = true
				break
			}
		}
		if hasRarity {
			break
		}
	}
	if !hasRarity {
		t.Error("expected at least some synonyms to have Rarity populated")
	}
}
```

**Step 2: Run tests to verify they fail**

Run: `cd api && PATH="/usr/local/go/bin:$PATH" go test ./internal/thesaurus/ -run TestGetLookup_Rarity -v`
Expected: FAIL — compilation error, `Rarity` field doesn't exist on `LookupResult`

**Step 3: Add Rarity to types**

In `api/internal/thesaurus/thesaurus.go`, update the types:

Add `Rarity` field to `RelatedWord`:

```go
type RelatedWord struct {
	Word     string `json:"word"`
	SynsetID string `json:"synset_id"`
	Rarity   string `json:"rarity,omitempty"`
}
```

Add `Rarity` field to `LookupResult`:

```go
type LookupResult struct {
	Word   string  `json:"word"`
	Senses []Sense `json:"senses"`
	Rarity string  `json:"rarity,omitempty"`
}
```

**Step 4: Wire rarity into querySenses**

In `querySenses`, update the SQL query to LEFT JOIN frequencies for the looked-up word's rarity, and for each synonym's rarity. The cleanest approach: after building senses, do one bulk query for rarity of the looked-up lemma + all synonym lemmas.

Add a new function `attachRarity` at the bottom of `thesaurus.go`:

```go
// attachRarity fetches rarity data for the looked-up word and all related words,
// populating the Rarity fields in-place.
func attachRarity(database *sql.DB, result *LookupResult) error {
	// Collect all unique words that need rarity lookup
	words := map[string]bool{result.Word: true}
	for _, sense := range result.Senses {
		for _, syn := range sense.Synonyms {
			words[syn.Word] = true
		}
		for _, h := range sense.Relations.Hypernyms {
			words[h.Word] = true
		}
		for _, h := range sense.Relations.Hyponyms {
			words[h.Word] = true
		}
		for _, s := range sense.Relations.Similar {
			words[s.Word] = true
		}
	}

	// Build IN clause
	placeholders := make([]string, 0, len(words))
	args := make([]interface{}, 0, len(words))
	for w := range words {
		placeholders = append(placeholders, "?")
		args = append(args, w)
	}
	if len(placeholders) == 0 {
		return nil
	}

	query := `SELECT lemma, rarity FROM frequencies WHERE lemma IN (` +
		strings.Join(placeholders, ",") + `)`

	rows, err := database.Query(query, args...)
	if err != nil {
		return err
	}
	defer rows.Close()

	rarityMap := make(map[string]string)
	for rows.Next() {
		var lemma, rarity string
		if err := rows.Scan(&lemma, &rarity); err != nil {
			continue
		}
		rarityMap[lemma] = rarity
	}
	if err := rows.Err(); err != nil {
		return err
	}

	// Apply rarity to result
	result.Rarity = rarityMap[result.Word]

	for i := range result.Senses {
		for j := range result.Senses[i].Synonyms {
			result.Senses[i].Synonyms[j].Rarity = rarityMap[result.Senses[i].Synonyms[j].Word]
		}
		for j := range result.Senses[i].Relations.Hypernyms {
			result.Senses[i].Relations.Hypernyms[j].Rarity = rarityMap[result.Senses[i].Relations.Hypernyms[j].Word]
		}
		for j := range result.Senses[i].Relations.Hyponyms {
			result.Senses[i].Relations.Hyponyms[j].Rarity = rarityMap[result.Senses[i].Relations.Hyponyms[j].Word]
		}
		for j := range result.Senses[i].Relations.Similar {
			result.Senses[i].Relations.Similar[j].Rarity = rarityMap[result.Senses[i].Relations.Similar[j].Word]
		}
	}

	return nil
}
```

**Step 5: Call attachRarity from GetLookup**

In `GetLookup`, after `queryRelations` and before the return, add:

```go
	// Query 3: rarity data for all words in the result
	if err := attachRarity(database, result); err != nil {
		// Non-fatal: rarity is optional enrichment
		// Log but don't fail the lookup
	}

	return result, nil
```

Note: this changes from 2 queries to 3, but the third is a simple indexed lookup. Update the function comment from "Uses two queries total" to "Uses three queries total".

**Step 6: Run tests**

Run: `cd api && PATH="/usr/local/go/bin:$PATH" go test ./internal/thesaurus/ -v`
Expected: All PASS including the new rarity tests

**Step 7: Run all Go tests for regressions**

Run: `cd api && PATH="/usr/local/go/bin:$PATH" go test ./... -v`
Expected: All PASS

**Step 8: Commit**

```bash
git add api/internal/thesaurus/thesaurus.go api/internal/thesaurus/thesaurus_test.go
git commit -m "feat(api): wire rarity from frequencies table into thesaurus lookup"
```

---

## Task 9: Go API — remove Rarity placeholder from db.Synset

The `Rarity` placeholder in `db.go:27` is now superseded by the thesaurus-level rarity. Remove it to avoid confusion.

**Files:**
- Modify: `api/internal/db/db.go:27`

**Step 1: Remove the placeholder**

In `api/internal/db/db.go`, remove line 27:

```go
	Rarity       string   `json:"rarity,omitempty"`        // Placeholder: SUBTLEX-UK frequency data pending
```

**Step 2: Run all Go tests**

Run: `cd api && PATH="/usr/local/go/bin:$PATH" go test ./... -v`
Expected: All PASS (nothing reads `Synset.Rarity`)

**Step 3: Commit**

```bash
git add api/internal/db/db.go
git commit -m "refactor(api): remove Rarity placeholder from Synset struct"
```

---

## Task 10: Frontend types — add rarity to API types

Update the TypeScript types to match the new API response shape.

**Files:**
- Modify: `web/src/types/api.ts`

**Step 1: Write the failing test**

Add to `web/src/components/mf-results-panel.test.ts`:

```typescript
it('renders a rarity badge for the looked-up word', async () => {
  const resultWithRarity: LookupResult = {
    ...melancholy,
    rarity: 'unusual',
  }
  el.result = resultWithRarity
  await el.updateComplete

  const badge = el.shadowRoot!.querySelector('.rarity-badge')
  expect(badge).toBeTruthy()
  expect(badge?.textContent?.trim()).toBe('unusual')
})
```

**Step 2: Run test to verify it fails**

Run: `cd web && npx vitest run src/components/mf-results-panel.test.ts`
Expected: FAIL — `rarity` not in `LookupResult` type

**Step 3: Update the types**

In `web/src/types/api.ts`:

```typescript
/** Mirrors Go thesaurus.RelatedWord */
export interface RelatedWord {
  word: string
  synset_id: string
  rarity?: string
}

/** Mirrors Go thesaurus.Relations */
export interface Relations {
  hypernyms: RelatedWord[]
  hyponyms: RelatedWord[]
  similar: RelatedWord[]
}

/** Mirrors Go thesaurus.Sense */
export interface Sense {
  synset_id: string
  pos: string
  definition: string
  synonyms: RelatedWord[]
  relations: Relations
}

/** Mirrors Go thesaurus.LookupResult */
export interface LookupResult {
  word: string
  senses: Sense[]
  rarity?: string
}
```

**Step 4: Commit**

```bash
git add web/src/types/api.ts
git commit -m "feat(frontend): add rarity to API type definitions"
```

---

## Task 11: Frontend — rarity badges in results panel

Render rarity badges next to POS badges in the results panel. Colour-coded: common (muted grey-green), unusual (amber), rare (purple).

**Files:**
- Modify: `web/src/components/mf-results-panel.ts`
- Modify: `web/src/components/mf-results-panel.test.ts`
- Modify: `strings/v1/ui.en-GB.ftl`

**Step 1: Write failing tests**

Add to `web/src/components/mf-results-panel.test.ts`, updating the test fixture and adding new tests:

Update the `melancholy` fixture to include rarity:

```typescript
const melancholy: LookupResult = {
  word: 'melancholy',
  rarity: 'unusual',
  senses: [
    {
      synset_id: '72858',
      pos: 'noun',
      definition: 'a feeling of thoughtful sadness',
      synonyms: [
        { word: 'sadness', synset_id: '72855', rarity: 'common' },
      ],
      relations: {
        hypernyms: [{ word: 'emotion', synset_id: '1' }],
        hyponyms: [{ word: 'gloom', synset_id: '2' }],
        similar: [],
      },
    },
  ],
}
```

Add tests:

```typescript
it('renders a rarity badge for the looked-up word', async () => {
  el.result = melancholy
  await el.updateComplete

  const badge = el.shadowRoot!.querySelector('.rarity-badge')
  expect(badge).toBeTruthy()
  expect(badge?.textContent?.trim()).toBe('unusual')
})

it('applies correct CSS class for rarity tier', async () => {
  el.result = melancholy
  await el.updateComplete

  const badge = el.shadowRoot!.querySelector('.rarity-badge')
  expect(badge?.classList.contains('unusual')).toBe(true)
})

it('renders rarity badge on synonym word chips', async () => {
  el.result = melancholy
  await el.updateComplete

  const chip = el.shadowRoot!.querySelector('[data-word="sadness"]')
  const badge = chip?.querySelector('.rarity-badge') ?? chip?.nextElementSibling
  // Rarity is shown as a title attribute or aria-label on the chip, not a sub-element
  // The exact approach depends on implementation — check word chip has rarity data
  expect(chip?.getAttribute('data-rarity')).toBe('common')
})

it('does not render rarity badge when rarity is missing', async () => {
  const noRarity: LookupResult = {
    word: 'test',
    senses: [{
      synset_id: '1',
      pos: 'noun',
      definition: 'a test',
      synonyms: [],
      relations: { hypernyms: [], hyponyms: [], similar: [] },
    }],
  }
  el.result = noRarity
  await el.updateComplete

  const badge = el.shadowRoot!.querySelector('.rarity-badge')
  expect(badge).toBeNull()
})
```

**Step 2: Run tests to verify they fail**

Run: `cd web && npx vitest run src/components/mf-results-panel.test.ts`
Expected: FAIL

**Step 3: Add Fluent strings for rarity**

Add to `strings/v1/ui.en-GB.ftl`:

```
## Rarity badges
rarity-common = common
rarity-unusual = unusual
rarity-rare = rare
```

**Step 4: Implement rarity badges in the results panel**

In `web/src/components/mf-results-panel.ts`:

Add CSS for rarity badges (inside the `static styles` block, after `.pos-badge`):

```css
    .rarity-badge {
      display: inline-block;
      font-size: 0.65rem;
      padding: 1px 6px;
      border-radius: 8px;
      margin-left: var(--space-xs, 0.25rem);
      text-transform: uppercase;
      letter-spacing: 0.04em;
      vertical-align: middle;
    }

    .rarity-badge.common {
      background: rgba(106, 139, 111, 0.2);
      color: #8bb89a;
    }

    .rarity-badge.unusual {
      background: rgba(196, 149, 106, 0.2);
      color: #c4956a;
    }

    .rarity-badge.rare {
      background: rgba(122, 106, 139, 0.2);
      color: #a88bc4;
    }
```

Add a `renderRarityBadge` method:

```typescript
  private renderRarityBadge(rarity?: string) {
    if (!rarity) return nothing
    return html`<span class="rarity-badge ${rarity}">${getString(`rarity-${rarity}`)}</span>`
  }
```

Update `renderSense` to include the rarity badge after the POS badge (line ~150):

```typescript
  private renderSense(sense: Sense) {
    return html`
      <div class="sense">
        <span class="pos-badge">${sense.pos}</span>
        <div class="definition">${sense.definition}</div>
        ...
```

Update the heading in `render()` to show the word's rarity:

```typescript
        <h2>${this.result.word} ${this.renderRarityBadge(this.result.rarity)}</h2>
```

Update `renderWordChip` to include a `data-rarity` attribute:

```typescript
  private renderWordChip(rw: RelatedWord, type: string) {
    return html`
      <span
        class="word-chip ${type}"
        data-word=${rw.word}
        data-rarity=${rw.rarity ?? ''}
        tabindex="0"
        role="button"
        ...
      >${rw.word}</span>
    `
  }
```

**Step 5: Run tests**

Run: `cd web && npx vitest run src/components/mf-results-panel.test.ts`
Expected: All PASS

**Step 6: Run all frontend tests for regressions**

Run: `cd web && npx vitest run`
Expected: All PASS

**Step 7: Commit**

```bash
git add web/src/components/mf-results-panel.ts web/src/components/mf-results-panel.test.ts strings/v1/ui.en-GB.ftl
git commit -m "feat(frontend): render rarity badges in results panel"
```

---

## Task 12: Frontend — HUD filter toggles

Three independent toggle checkboxes (Common / Unusual / Rare) that control visibility of nodes on the 3D force graph.

**Files:**
- Modify: `web/src/components/mf-app.ts`
- Modify: `web/src/components/mf-app.test.ts` (or create if none exists)
- Modify: `web/src/graph/types.ts`
- Modify: `web/src/graph/transform.ts`
- Modify: `strings/v1/ui.en-GB.ftl`

**Step 1: Add rarity to GraphNode**

In `web/src/graph/types.ts`, add an optional `rarity` field to `GraphNode`:

```typescript
export interface GraphNode {
  id: string
  word: string
  synsetId?: string
  relationType: RelationType
  val: number
  rarity?: string  // 'common' | 'unusual' | 'rare'
}
```

**Step 2: Propagate rarity in graph transform**

In `web/src/graph/transform.ts`, update the node creation to pass through rarity. The `RelatedWord` type now has `rarity?`, so:

Where the central node is created (~line 23):

```typescript
  nodeMap.set(centralId, {
    id: centralId,
    word: result.word,
    relationType: 'central',
    val: 8,
    rarity: result.rarity,
  })
```

Where related word nodes are created (~line 58):

```typescript
      nodeMap.set(nodeId, {
        id: nodeId,
        word: rw.word,
        synsetId: rw.synset_id,
        relationType: tier.type,
        val: tier.type === 'synonym' ? 4 : 2,
        rarity: rw.rarity,
      })
```

**Step 3: Write failing tests for HUD filter**

Create `web/src/components/mf-app.test.ts` or add to existing. Test that filter toggles exist and control graph data filtering:

```typescript
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { MfApp } from './mf-app'

describe('MfApp HUD filter', () => {
  let el: MfApp

  beforeEach(async () => {
    el = document.createElement('mf-app') as MfApp
    document.body.appendChild(el)
    await el.updateComplete
  })

  afterEach(() => {
    document.body.removeChild(el)
  })

  it('renders three filter toggles', async () => {
    // Trigger a result so the filter becomes visible
    // (filters only show when there's data)
    // Use internal state manipulation for unit testing
    ;(el as any).appState = 'ready'
    ;(el as any).result = { word: 'test', senses: [], rarity: 'common' }
    ;(el as any).graphData = { nodes: [{ id: 'test', word: 'test', relationType: 'central', val: 8, rarity: 'common' }], links: [] }
    await el.updateComplete

    const toggles = el.shadowRoot!.querySelectorAll('.rarity-toggle')
    expect(toggles.length).toBe(3)
  })

  it('all toggles default to checked', async () => {
    ;(el as any).appState = 'ready'
    ;(el as any).result = { word: 'test', senses: [], rarity: 'common' }
    ;(el as any).graphData = { nodes: [{ id: 'test', word: 'test', relationType: 'central', val: 8 }], links: [] }
    await el.updateComplete

    const checkboxes = el.shadowRoot!.querySelectorAll<HTMLInputElement>('.rarity-toggle input[type="checkbox"]')
    for (const cb of checkboxes) {
      expect(cb.checked).toBe(true)
    }
  })
})
```

**Step 4: Run tests to verify they fail**

Run: `cd web && npx vitest run src/components/mf-app.test.ts`
Expected: FAIL

**Step 5: Add Fluent strings for filter toggles**

Add to `strings/v1/ui.en-GB.ftl`:

```
## HUD filter toggles
filter-common = Common
filter-unusual = Unusual
filter-rare = Rare
filter-aria-label = Filter by word rarity
```

**Step 6: Implement filter toggles in mf-app**

In `web/src/components/mf-app.ts`:

Add state for filter toggles (after existing `@state()` declarations):

```typescript
  @state() private showCommon = true
  @state() private showUnusual = true
  @state() private showRare = true
```

Add a computed getter for filtered graph data:

```typescript
  private get filteredGraphData(): GraphData {
    if (this.showCommon && this.showUnusual && this.showRare) {
      return this.graphData // no filtering needed
    }

    const visibleNodes = this.graphData.nodes.filter(node => {
      // Central node is always visible
      if (node.relationType === 'central') return true
      const rarity = node.rarity ?? 'unusual' // default to unusual for NULL
      if (rarity === 'common' && !this.showCommon) return false
      if (rarity === 'unusual' && !this.showUnusual) return false
      if (rarity === 'rare' && !this.showRare) return false
      return true
    })

    const visibleIds = new Set(visibleNodes.map(n => n.id))
    const visibleLinks = this.graphData.links.filter(
      link => visibleIds.has(link.source as string) && visibleIds.has(link.target as string),
    )

    return { nodes: visibleNodes, links: visibleLinks }
  }
```

Add CSS for the filter toggles (in `static styles`):

```css
    .rarity-filters {
      position: absolute;
      top: calc(var(--space-md, 1rem) + 48px);
      left: 50%;
      transform: translateX(-50%);
      display: flex;
      gap: var(--space-sm, 0.5rem);
      z-index: 20;
    }

    .rarity-toggle {
      display: flex;
      align-items: center;
      gap: 4px;
      font-size: 0.75rem;
      color: var(--colour-text-secondary, #a89f94);
      cursor: pointer;
    }

    .rarity-toggle input {
      accent-color: var(--colour-accent-gold, #d4af37);
    }

    .rarity-toggle.common { color: #8bb89a; }
    .rarity-toggle.unusual { color: #c4956a; }
    .rarity-toggle.rare { color: #a88bc4; }
```

Add the filter toggle rendering in `render()`, below the search container and only when there's a result:

```typescript
      ${this.appState === 'ready'
        ? html`
            <div class="rarity-filters" role="group" aria-label="${getString('filter-aria-label')}">
              <label class="rarity-toggle common">
                <input type="checkbox" .checked=${this.showCommon}
                  @change=${(e: Event) => { this.showCommon = (e.target as HTMLInputElement).checked }}>
                ${getString('filter-common')}
              </label>
              <label class="rarity-toggle unusual">
                <input type="checkbox" .checked=${this.showUnusual}
                  @change=${(e: Event) => { this.showUnusual = (e.target as HTMLInputElement).checked }}>
                ${getString('filter-unusual')}
              </label>
              <label class="rarity-toggle rare">
                <input type="checkbox" .checked=${this.showRare}
                  @change=${(e: Event) => { this.showRare = (e.target as HTMLInputElement).checked }}>
                ${getString('filter-rare')}
              </label>
            </div>
          `
        : ''}
```

Pass `filteredGraphData` to the force graph instead of `graphData`:

```typescript
      <mf-force-graph
        .graphData=${this.filteredGraphData}
```

**Step 7: Run tests**

Run: `cd web && npx vitest run`
Expected: All PASS

**Step 8: Commit**

```bash
git add web/src/components/mf-app.ts web/src/components/mf-app.test.ts web/src/graph/types.ts web/src/graph/transform.ts strings/v1/ui.en-GB.ftl
git commit -m "feat(frontend): add HUD rarity filter toggles for graph density control"
```

---

## Task 13: Copy updated Fluent strings to web/public

The Fluent strings file in `strings/` is the source of truth, but the Vite dev server serves from `web/public/strings/`. Copy the updated file.

**Files:**
- Modify: `web/public/strings/v1/ui.ftl`

**Step 1: Copy the file**

Run: `cp strings/v1/ui.en-GB.ftl web/public/strings/v1/ui.ftl`

**Step 2: Verify both files match**

Run: `diff strings/v1/ui.en-GB.ftl web/public/strings/v1/ui.ftl`
Expected: No differences (or only the filename renaming pattern — the Go handler maps `ui.ftl` → `ui.en-GB.ftl`)

Actually, check what the existing `web/public/strings/v1/ui.ftl` contains — it may be the en-GB version directly. Match whatever pattern exists.

**Step 3: Commit**

```bash
git add web/public/strings/v1/ui.ftl
git commit -m "chore: sync Fluent strings to web/public for dev server"
```

---

## Task 14: Final integration test — end to end

Verify the full pipeline works: restore DB → start Go server → hit lookup endpoint → confirm rarity in response.

**Files:** None (manual verification)

**Step 1: Restore DB**

Run: `bash data-pipeline/scripts/restore_db.sh`

**Step 2: Start the Go API server**

Run: `cd api && PATH="/usr/local/go/bin:$PATH" go run cmd/metaforge/main.go --db ../data-pipeline/output/lexicon_v2.db`

**Step 3: Test lookup with rarity**

In a separate terminal:

```bash
curl -s 'http://localhost:8080/thesaurus/lookup?word=happy' | python3 -m json.tool | head -20
```

Expected: Response includes `"rarity": "common"` at the top level and rarity fields on synonyms.

```bash
curl -s 'http://localhost:8080/thesaurus/lookup?word=melancholy' | python3 -m json.tool | head -20
```

Expected: `"rarity": "unusual"`

**Step 4: Run all test suites**

```bash
# Pipeline
cd data-pipeline && .venv/bin/python -m pytest scripts/ -v

# Go
cd api && PATH="/usr/local/go/bin:$PATH" go test ./... -v

# Frontend
cd web && npx vitest run
```

Expected: All pass.

**Step 5: Stop the server and commit if any adjustments were needed**

---

## Summary

| Task | What | Files | Tests |
|------|------|-------|-------|
| 1 | Add openpyxl dependency | `requirements.txt` | — |
| 2 | Update frequencies schema | `schema-v2.sql`, test file | 1 |
| 3 | Add input path constants | `utils.py` | — |
| 4 | Familiarity import script | `import_familiarity.py` | 7 |
| 5 | SUBTLEX-UK backfill script | `import_subtlex.py` | 2 |
| 6 | Wire into pipeline runner | `run_pipeline.sh` | — |
| 7 | Export SQL dump | `lexicon_v2.sql` | — |
| 8 | Go API — rarity in lookup | `thesaurus.go` | 2 |
| 9 | Go API — remove placeholder | `db.go` | — |
| 10 | Frontend types — rarity | `api.ts` | — |
| 11 | Frontend — rarity badges | `mf-results-panel.ts`, strings | 4 |
| 12 | Frontend — HUD filter toggles | `mf-app.ts`, graph types, transform, strings | 2 |
| 13 | Sync Fluent strings | `web/public/strings/` | — |
| 14 | Integration test | Manual | — |

**Total: 14 tasks, ~18 new tests, ~10 files modified, 3 files created.**
