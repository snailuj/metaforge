# Concreteness Gate Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a hard concreteness gate to the forge query that discards metaphor candidates where the target is more concrete than the vehicle.

**Architecture:** Import Brysbaert et al. (2014) concreteness ratings into a new `synset_concreteness` table (mean of lemma scores per synset). Add a SQL-level gate (`WHERE candidate_concreteness >= source_concreteness`) to both forge queries. Missing scores on either side pass through.

**Tech Stack:** Python (data import), Go (SQL queries, tests), SQLite

**Design doc:** `docs/plans/2026-02-25-concreteness-gate-design.md`

---

### Task 1: Download Brysbaert data and add to gitignore

**Files:**
- Create: `data-pipeline/input/brysbaert-concreteness/` (directory)
- Modify: `data-pipeline/.gitignore` (if exists, else project root `.gitignore`)

**Step 1: Download the Brysbaert data file**

```bash
mkdir -p data-pipeline/input/brysbaert-concreteness
# Download from GitHub mirror
curl -L -o data-pipeline/input/brysbaert-concreteness/Concreteness_ratings_Brysbaert_et_al_BRM.txt \
  https://raw.githubusercontent.com/ArtsEngine/concreteness/master/Concreteness_ratings_Brysbaert_et_al_BRM.txt
```

**Step 2: Verify the file**

```bash
head -3 data-pipeline/input/brysbaert-concreteness/Concreteness_ratings_Brysbaert_et_al_BRM.txt
wc -l data-pipeline/input/brysbaert-concreteness/Concreteness_ratings_Brysbaert_et_al_BRM.txt
```

Expected: tab-separated file with header row, ~40k lines. Columns likely include `Word`, `Conc.M` (mean concreteness), `Conc.SD`, etc.

**Step 3: Ensure the input directory is gitignored**

Check whether `data-pipeline/input/` is already in `.gitignore`. If not, add the brysbaert directory specifically. We don't commit raw third-party data files.

**Step 4: Commit**

```bash
git add .gitignore  # or data-pipeline/.gitignore
git commit -m "chore: add brysbaert concreteness input directory"
```

---

### Task 2: Add CONCRETENESS_TSV to utils.py

**Files:**
- Modify: `data-pipeline/scripts/utils.py`

**Step 1: Add the path constant**

Add after the SUBTLEX constants (around line 29):

```python
# Brysbaert concreteness ratings
BRYSBAERT_CONCRETENESS_DIR = INPUT_DIR / "brysbaert-concreteness"
BRYSBAERT_CONCRETENESS_TSV = BRYSBAERT_CONCRETENESS_DIR / "Concreteness_ratings_Brysbaert_et_al_BRM.txt"
```

**Step 2: Run existing tests to confirm nothing breaks**

```bash
source .venv/bin/activate && python -m pytest data-pipeline/scripts/test_utils.py -v
```

Expected: all pass.

**Step 3: Commit**

```bash
git add data-pipeline/scripts/utils.py
git commit -m "chore: add Brysbaert concreteness path constant to utils"
```

---

### Task 3: Write failing tests for import_concreteness.py

**Files:**
- Create: `data-pipeline/scripts/test_import_concreteness.py`

The test file follows the pattern from `test_import_familiarity.py`: pure unit tests with in-memory SQLite, no dependency on real data files.

**Step 1: Write the test file**

```python
"""Tests for import_concreteness.py — Brysbaert concreteness import."""
import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))

from import_concreteness import load_concreteness, import_concreteness


def _make_test_db():
    """Create an in-memory SQLite with synsets, lemmas, and synset_concreteness tables."""
    conn = sqlite3.connect(":memory:")
    conn.execute("""CREATE TABLE synsets (
        synset_id TEXT PRIMARY KEY, pos TEXT, definition TEXT
    )""")
    conn.execute("""CREATE TABLE lemmas (
        lemma TEXT, synset_id TEXT, PRIMARY KEY (lemma, synset_id)
    )""")
    conn.execute("""CREATE TABLE synset_concreteness (
        synset_id TEXT PRIMARY KEY,
        score REAL NOT NULL,
        source TEXT NOT NULL,
        FOREIGN KEY (synset_id) REFERENCES synsets(synset_id)
    )""")
    return conn


# --- load_concreteness ---

def test_load_concreteness_parses_tsv(tmp_path):
    """load_concreteness reads tab-separated Brysbaert file."""
    tsv = tmp_path / "concreteness.txt"
    tsv.write_text(
        "Word\tBigram\tConc.M\tConc.SD\tUnknown\tTotal\tPercent_known\tSUBTLEX\tDom_Pos\n"
        "apple\t0\t4.82\t0.39\t0\t25\t100\t12345\tNoun\n"
        "justice\t0\t1.78\t1.22\t2\t25\t92\t5678\tNoun\n"
    )
    data = load_concreteness(tsv)
    assert "apple" in data
    assert abs(data["apple"] - 4.82) < 0.01
    assert "justice" in data
    assert abs(data["justice"] - 1.78) < 0.01


def test_load_concreteness_lowercases_words(tmp_path):
    """Words are lowercased for matching."""
    tsv = tmp_path / "concreteness.txt"
    tsv.write_text(
        "Word\tBigram\tConc.M\tConc.SD\tUnknown\tTotal\tPercent_known\tSUBTLEX\tDom_Pos\n"
        "Apple\t0\t4.82\t0.39\t0\t25\t100\t12345\tNoun\n"
    )
    data = load_concreteness(tsv)
    assert "apple" in data


def test_load_concreteness_skips_bigrams(tmp_path):
    """Bigrams (Bigram=1) are skipped — we only want single words."""
    tsv = tmp_path / "concreteness.txt"
    tsv.write_text(
        "Word\tBigram\tConc.M\tConc.SD\tUnknown\tTotal\tPercent_known\tSUBTLEX\tDom_Pos\n"
        "apple\t0\t4.82\t0.39\t0\t25\t100\t12345\tNoun\n"
        "ice cream\t1\t4.50\t0.50\t0\t25\t100\t2345\tNoun\n"
    )
    data = load_concreteness(tsv)
    assert "apple" in data
    assert "ice cream" not in data


# --- import_concreteness ---

def test_import_concreteness_single_lemma_synset():
    """Synset with one lemma gets that lemma's concreteness score."""
    conn = _make_test_db()
    conn.execute("INSERT INTO synsets VALUES ('syn-apple', 'n', 'fruit')")
    conn.execute("INSERT INTO lemmas VALUES ('apple', 'syn-apple')")

    stats = import_concreteness(conn, {"apple": 4.82})

    row = conn.execute(
        "SELECT score, source FROM synset_concreteness WHERE synset_id = 'syn-apple'"
    ).fetchone()
    assert row is not None
    assert abs(row[0] - 4.82) < 0.01
    assert row[1] == "brysbaert"
    assert stats["scored"] == 1
    conn.close()


def test_import_concreteness_multi_lemma_synset_uses_mean():
    """Synset with multiple lemmas gets the mean of available scores."""
    conn = _make_test_db()
    conn.execute("INSERT INTO synsets VALUES ('syn-rock', 'n', 'a stone')")
    conn.execute("INSERT INTO lemmas VALUES ('rock', 'syn-rock')")
    conn.execute("INSERT INTO lemmas VALUES ('stone', 'syn-rock')")

    # rock=4.8, stone=4.6 → mean=4.7
    stats = import_concreteness(conn, {"rock": 4.8, "stone": 4.6})

    row = conn.execute(
        "SELECT score FROM synset_concreteness WHERE synset_id = 'syn-rock'"
    ).fetchone()
    assert abs(row[0] - 4.7) < 0.01
    assert stats["scored"] == 1
    conn.close()


def test_import_concreteness_partial_lemma_coverage():
    """Synset scores use only lemmas with data; ignores missing ones."""
    conn = _make_test_db()
    conn.execute("INSERT INTO synsets VALUES ('syn-rock', 'n', 'a stone')")
    conn.execute("INSERT INTO lemmas VALUES ('rock', 'syn-rock')")
    conn.execute("INSERT INTO lemmas VALUES ('boulder', 'syn-rock')")

    # Only 'rock' has a score; 'boulder' missing → score = rock's alone
    stats = import_concreteness(conn, {"rock": 4.8})

    row = conn.execute(
        "SELECT score FROM synset_concreteness WHERE synset_id = 'syn-rock'"
    ).fetchone()
    assert abs(row[0] - 4.8) < 0.01
    conn.close()


def test_import_concreteness_no_coverage_no_row():
    """Synset where no lemmas have Brysbaert data gets no row."""
    conn = _make_test_db()
    conn.execute("INSERT INTO synsets VALUES ('syn-xyzzy', 'n', 'unknown')")
    conn.execute("INSERT INTO lemmas VALUES ('xyzzy', 'syn-xyzzy')")

    stats = import_concreteness(conn, {})

    row = conn.execute(
        "SELECT * FROM synset_concreteness WHERE synset_id = 'syn-xyzzy'"
    ).fetchone()
    assert row is None
    assert stats["unscored"] == 1
    conn.close()


def test_import_concreteness_idempotent():
    """Running import twice produces same result (INSERT OR REPLACE)."""
    conn = _make_test_db()
    conn.execute("INSERT INTO synsets VALUES ('syn-apple', 'n', 'fruit')")
    conn.execute("INSERT INTO lemmas VALUES ('apple', 'syn-apple')")

    import_concreteness(conn, {"apple": 4.82})
    import_concreteness(conn, {"apple": 4.82})

    count = conn.execute("SELECT COUNT(*) FROM synset_concreteness").fetchone()[0]
    assert count == 1
    conn.close()


def test_import_concreteness_returns_stats():
    """Stats dict has scored and unscored counts."""
    conn = _make_test_db()
    conn.execute("INSERT INTO synsets VALUES ('syn-a', 'n', 'a')")
    conn.execute("INSERT INTO synsets VALUES ('syn-b', 'n', 'b')")
    conn.execute("INSERT INTO lemmas VALUES ('apple', 'syn-a')")
    conn.execute("INSERT INTO lemmas VALUES ('xyzzy', 'syn-b')")

    stats = import_concreteness(conn, {"apple": 4.82})

    assert stats["scored"] == 1
    assert stats["unscored"] == 1
    assert stats["total_synsets"] == 2
    conn.close()
```

**Step 2: Run tests to verify they fail**

```bash
source .venv/bin/activate && python -m pytest data-pipeline/scripts/test_import_concreteness.py -v
```

Expected: `ModuleNotFoundError: No module named 'import_concreteness'` — the module doesn't exist yet.

**Step 3: Commit the failing tests**

```bash
git add data-pipeline/scripts/test_import_concreteness.py
git commit -m "test: add failing tests for concreteness import"
```

---

### Task 4: Implement import_concreteness.py

**Files:**
- Create: `data-pipeline/scripts/import_concreteness.py`

**Step 1: Write the implementation**

```python
"""Import Brysbaert et al. (2014) concreteness ratings into synset_concreteness.

Reads the tab-separated concreteness ratings file, matches lemmas against our
lexicon, computes mean concreteness per synset, and populates the
synset_concreteness table.

Usage:
    python import_concreteness.py
"""
import sqlite3
from pathlib import Path

from utils import LEXICON_V2, BRYSBAERT_CONCRETENESS_TSV


def load_concreteness(tsv_path: Path) -> dict[str, float]:
    """Load concreteness ratings from the Brysbaert TSV.

    Returns dict mapping lowercase word -> concreteness mean (1.0-5.0).
    Skips bigrams (Bigram column = 1).
    """
    print(f"Loading concreteness data from {tsv_path.name}...")
    data: dict[str, float] = {}

    with open(tsv_path, "r", encoding="utf-8") as f:
        header = f.readline().strip().split("\t")
        word_idx = header.index("Word")
        conc_m_idx = header.index("Conc.M")
        bigram_idx = header.index("Bigram")

        for line in f:
            fields = line.strip().split("\t")
            if len(fields) <= max(word_idx, conc_m_idx, bigram_idx):
                continue

            # Skip bigrams
            if fields[bigram_idx].strip() == "1":
                continue

            word = fields[word_idx].strip().lower()
            if not word:
                continue

            try:
                score = float(fields[conc_m_idx])
            except (ValueError, IndexError):
                continue

            if word not in data:  # keep first occurrence
                data[word] = score

    print(f"  Loaded {len(data)} single-word entries")
    return data


def import_concreteness(
    conn: sqlite3.Connection,
    concreteness_data: dict[str, float],
) -> dict[str, int]:
    """Import concreteness ratings into synset_concreteness table.

    For each synset, collects all its lemmas, looks up each in
    concreteness_data, and stores the mean score. Synsets with zero
    matching lemmas get no row.

    Returns stats dict with counts.
    """
    # Get all synset → lemmas mappings
    cursor = conn.execute("SELECT synset_id, lemma FROM lemmas")
    synset_lemmas: dict[str, list[str]] = {}
    for synset_id, lemma in cursor:
        synset_lemmas.setdefault(synset_id, []).append(lemma)

    print(f"  {len(synset_lemmas)} synsets in lexicon")

    # Clear existing data
    conn.execute("DELETE FROM synset_concreteness")

    rows = []
    stats = {"scored": 0, "unscored": 0, "total_synsets": len(synset_lemmas)}

    for synset_id, lemmas in synset_lemmas.items():
        scores = []
        for lemma in lemmas:
            if lemma in concreteness_data:
                scores.append(concreteness_data[lemma])

        if scores:
            mean_score = sum(scores) / len(scores)
            rows.append((synset_id, mean_score, "brysbaert"))
            stats["scored"] += 1
        else:
            stats["unscored"] += 1

    conn.executemany(
        "INSERT OR REPLACE INTO synset_concreteness (synset_id, score, source) VALUES (?, ?, ?)",
        rows,
    )
    conn.commit()

    return stats


def main():
    if not BRYSBAERT_CONCRETENESS_TSV.exists():
        raise FileNotFoundError(
            f"Concreteness data not found: {BRYSBAERT_CONCRETENESS_TSV}"
        )
    if not LEXICON_V2.exists():
        raise FileNotFoundError(f"Lexicon DB not found: {LEXICON_V2}")

    concreteness_data = load_concreteness(BRYSBAERT_CONCRETENESS_TSV)

    conn = sqlite3.connect(LEXICON_V2)
    try:
        # Ensure table exists
        conn.execute("""CREATE TABLE IF NOT EXISTS synset_concreteness (
            synset_id TEXT PRIMARY KEY,
            score REAL NOT NULL,
            source TEXT NOT NULL,
            FOREIGN KEY (synset_id) REFERENCES synsets(synset_id)
        )""")
        stats = import_concreteness(conn, concreteness_data)
    finally:
        conn.close()

    coverage = stats["scored"] / stats["total_synsets"] * 100 if stats["total_synsets"] else 0
    print(f"\nImport complete:")
    print(f"  Scored:     {stats['scored']} ({coverage:.1f}%)")
    print(f"  Unscored:   {stats['unscored']}")
    print(f"  Total:      {stats['total_synsets']}")


if __name__ == "__main__":
    main()
```

**Step 2: Run tests to verify they pass**

```bash
source .venv/bin/activate && python -m pytest data-pipeline/scripts/test_import_concreteness.py -v
```

Expected: all pass.

**Step 3: Commit**

```bash
git add data-pipeline/scripts/import_concreteness.py
git commit -m "feat(pipeline): import Brysbaert concreteness ratings per synset"
```

---

### Task 5: Add synset_concreteness to SCHEMA.sql and PRE_ENRICH.sql

**Files:**
- Modify: `data-pipeline/SCHEMA.sql`
- Note: `PRE_ENRICH.sql` — the concreteness table will be populated by running `import_concreteness.py` after restoring from PRE_ENRICH. However, if we want concreteness data baked into PRE_ENRICH, we need to run the import and re-dump. For now, just add the DDL to SCHEMA.sql so the table exists when created from scratch.

**Step 1: Add DDL to SCHEMA.sql**

Add after the `enrichment` table definition (near other synset-level metadata tables):

```sql
CREATE TABLE synset_concreteness (
    synset_id TEXT PRIMARY KEY,
    score REAL NOT NULL,
    source TEXT NOT NULL,
    FOREIGN KEY (synset_id) REFERENCES synsets(synset_id)
);
```

**Step 2: Run the import against our DB to populate it**

```bash
source .venv/bin/activate && python data-pipeline/scripts/import_concreteness.py
```

Check the output for coverage stats. We need a reasonable percentage of synsets scored.

**Step 3: Commit**

```bash
git add data-pipeline/SCHEMA.sql
git commit -m "schema: add synset_concreteness table"
```

---

### Task 6: Write failing Go tests for concreteness gate in GetForgeMatchesCurated

**Files:**
- Modify: `api/internal/db/db_curated_test.go`

The existing `setupCuratedTestDB` fixture needs a `synset_concreteness` table and test data. We add new test functions that verify the gate behaviour.

**Step 1: Write the failing tests**

Add a new setup function and tests after the existing curated tests:

```go
func setupConcretenessTestDB(t *testing.T) *sql.DB {
	t.Helper()
	tmpDir := t.TempDir()
	dbPath := filepath.Join(tmpDir, "test.db")

	db, err := sql.Open("sqlite3", dbPath)
	if err != nil {
		t.Fatal(err)
	}

	_, err = db.Exec(`
		CREATE TABLE synsets (synset_id TEXT PRIMARY KEY, pos TEXT, definition TEXT);
		CREATE TABLE lemmas (lemma TEXT, synset_id TEXT, PRIMARY KEY (lemma, synset_id));

		CREATE TABLE property_vocab_curated (
			vocab_id INTEGER PRIMARY KEY,
			synset_id TEXT NOT NULL,
			lemma TEXT NOT NULL,
			pos TEXT NOT NULL,
			polysemy INTEGER NOT NULL
		);

		CREATE TABLE vocab_clusters (
			vocab_id INTEGER PRIMARY KEY,
			cluster_id INTEGER NOT NULL,
			is_representative INTEGER NOT NULL DEFAULT 0,
			is_singleton INTEGER NOT NULL DEFAULT 0
		);
		CREATE INDEX idx_vc_cluster_conc ON vocab_clusters(cluster_id);

		CREATE TABLE synset_properties_curated (
			synset_id TEXT NOT NULL,
			vocab_id INTEGER NOT NULL,
			cluster_id INTEGER NOT NULL,
			snap_method TEXT NOT NULL,
			snap_score REAL,
			salience_sum REAL NOT NULL DEFAULT 1.0,
			PRIMARY KEY (synset_id, cluster_id)
		);
		CREATE INDEX idx_spc_conc_synset ON synset_properties_curated(synset_id);
		CREATE INDEX idx_spc_conc_cluster ON synset_properties_curated(cluster_id);

		CREATE TABLE cluster_antonyms (
			cluster_id_a INTEGER NOT NULL,
			cluster_id_b INTEGER NOT NULL,
			PRIMARY KEY (cluster_id_a, cluster_id_b)
		);

		CREATE TABLE synset_concreteness (
			synset_id TEXT PRIMARY KEY,
			score REAL NOT NULL,
			source TEXT NOT NULL
		);

		-- Vocab (all singletons)
		INSERT INTO property_vocab_curated VALUES (1, 'v1', 'hot', 'a', 1);
		INSERT INTO property_vocab_curated VALUES (2, 'v2', 'destructive', 'a', 1);
		INSERT INTO vocab_clusters VALUES (1, 1, 1, 1);
		INSERT INTO vocab_clusters VALUES (2, 2, 1, 1);

		-- Source: anger (abstract, concreteness 1.8)
		INSERT INTO synsets VALUES ('src-anger', 'n', 'strong displeasure');
		INSERT INTO lemmas VALUES ('anger', 'src-anger');
		INSERT INTO synset_properties_curated (synset_id, vocab_id, cluster_id, snap_method, snap_score) VALUES ('src-anger', 1, 1, 'exact', NULL);
		INSERT INTO synset_properties_curated (synset_id, vocab_id, cluster_id, snap_method, snap_score) VALUES ('src-anger', 2, 2, 'exact', NULL);
		INSERT INTO synset_concreteness VALUES ('src-anger', 1.8, 'brysbaert');

		-- Target: volcano (concrete, concreteness 4.9) — SHOULD PASS gate
		INSERT INTO synsets VALUES ('tgt-volcano', 'n', 'a mountain that erupts');
		INSERT INTO lemmas VALUES ('volcano', 'tgt-volcano');
		INSERT INTO synset_properties_curated (synset_id, vocab_id, cluster_id, snap_method, snap_score) VALUES ('tgt-volcano', 1, 1, 'exact', NULL);
		INSERT INTO synset_properties_curated (synset_id, vocab_id, cluster_id, snap_method, snap_score) VALUES ('tgt-volcano', 2, 2, 'exact', NULL);
		INSERT INTO synset_concreteness VALUES ('tgt-volcano', 4.9, 'brysbaert');

		-- Target: fury (abstract, concreteness 1.5) — SHOULD FAIL gate (less concrete than source)
		INSERT INTO synsets VALUES ('tgt-fury', 'n', 'wild rage');
		INSERT INTO lemmas VALUES ('fury', 'tgt-fury');
		INSERT INTO synset_properties_curated (synset_id, vocab_id, cluster_id, snap_method, snap_score) VALUES ('tgt-fury', 1, 1, 'exact', NULL);
		INSERT INTO synset_properties_curated (synset_id, vocab_id, cluster_id, snap_method, snap_score) VALUES ('tgt-fury', 2, 2, 'exact', NULL);
		INSERT INTO synset_concreteness VALUES ('tgt-fury', 1.5, 'brysbaert');

		-- Target: blaze (equal concreteness to source, 1.8) — SHOULD PASS gate
		INSERT INTO synsets VALUES ('tgt-blaze', 'n', 'a fierce fire');
		INSERT INTO lemmas VALUES ('blaze', 'tgt-blaze');
		INSERT INTO synset_properties_curated (synset_id, vocab_id, cluster_id, snap_method, snap_score) VALUES ('tgt-blaze', 1, 1, 'exact', NULL);
		INSERT INTO synset_properties_curated (synset_id, vocab_id, cluster_id, snap_method, snap_score) VALUES ('tgt-blaze', 2, 2, 'exact', NULL);
		INSERT INTO synset_concreteness VALUES ('tgt-blaze', 1.8, 'brysbaert');

		-- Target: storm (no concreteness data) — SHOULD PASS gate (missing = pass through)
		INSERT INTO synsets VALUES ('tgt-storm', 'n', 'violent weather');
		INSERT INTO lemmas VALUES ('storm', 'tgt-storm');
		INSERT INTO synset_properties_curated (synset_id, vocab_id, cluster_id, snap_method, snap_score) VALUES ('tgt-storm', 1, 1, 'exact', NULL);
		INSERT INTO synset_properties_curated (synset_id, vocab_id, cluster_id, snap_method, snap_score) VALUES ('tgt-storm', 2, 2, 'exact', NULL);
		-- No synset_concreteness row for storm
	`)
	if err != nil {
		t.Fatal(err)
	}

	return db
}

func TestGetForgeMatchesCurated_ConcretenessGateKeepsConcreteVehicle(t *testing.T) {
	db := setupConcretenessTestDB(t)
	defer db.Close()

	matches, err := GetForgeMatchesCurated(db, "src-anger", 50)
	if err != nil {
		t.Fatal(err)
	}

	var found bool
	for _, m := range matches {
		if m.SynsetID == "tgt-volcano" {
			found = true
		}
	}
	if !found {
		t.Error("expected volcano (more concrete than anger) to pass gate")
	}
}

func TestGetForgeMatchesCurated_ConcretenessGateFiltersLessConcrete(t *testing.T) {
	db := setupConcretenessTestDB(t)
	defer db.Close()

	matches, err := GetForgeMatchesCurated(db, "src-anger", 50)
	if err != nil {
		t.Fatal(err)
	}

	for _, m := range matches {
		if m.SynsetID == "tgt-fury" {
			t.Error("expected fury (less concrete than anger) to be filtered by gate")
		}
	}
}

func TestGetForgeMatchesCurated_ConcretenessGateAllowsEqual(t *testing.T) {
	db := setupConcretenessTestDB(t)
	defer db.Close()

	matches, err := GetForgeMatchesCurated(db, "src-anger", 50)
	if err != nil {
		t.Fatal(err)
	}

	var found bool
	for _, m := range matches {
		if m.SynsetID == "tgt-blaze" {
			found = true
		}
	}
	if !found {
		t.Error("expected blaze (equal concreteness to anger) to pass gate")
	}
}

func TestGetForgeMatchesCurated_ConcretenessGateMissingScorePassesThrough(t *testing.T) {
	db := setupConcretenessTestDB(t)
	defer db.Close()

	matches, err := GetForgeMatchesCurated(db, "src-anger", 50)
	if err != nil {
		t.Fatal(err)
	}

	var found bool
	for _, m := range matches {
		if m.SynsetID == "tgt-storm" {
			found = true
		}
	}
	if !found {
		t.Error("expected storm (no concreteness data) to pass through gate")
	}
}
```

**Step 2: Run Go tests to verify they fail**

```bash
cd api && go test ./internal/db/ -run TestGetForgeMatchesCurated_Concreteness -v
```

Expected: tests fail because `fury` is still returned (no gate yet).

**Step 3: Commit failing tests**

```bash
git add api/internal/db/db_curated_test.go
git commit -m "test(api): add failing tests for concreteness gate in GetForgeMatchesCurated"
```

---

### Task 7: Implement concreteness gate in GetForgeMatchesCurated

**Files:**
- Modify: `api/internal/db/db.go:119-205` (`GetForgeMatchesCurated` function)

**Step 1: Add the gate to the SQL query**

The gate needs to:
1. LEFT JOIN `synset_concreteness` for the source synset (to get source concreteness)
2. LEFT JOIN `synset_concreteness` for each candidate synset
3. Filter: keep only where candidate score >= source score, OR either score is NULL

Modify the query in `GetForgeMatchesCurated`. The key changes are:
- Add a CTE or subquery for source concreteness
- In the `sub` subquery (which does the final ORDER BY and LIMIT), add a WHERE clause that filters candidates

The cleanest approach: add `source_conc` as a scalar subquery at the top, then LEFT JOIN `synset_concreteness` on the candidate side, and filter in the existing WHERE:

```sql
WITH source_conc AS (
    SELECT score FROM synset_concreteness WHERE synset_id = ?
),
source_props AS (
    SELECT cluster_id FROM synset_properties_curated WHERE synset_id = ?
),
shared AS (
    ... existing ...
),
contrast AS (
    ... existing ...
)
SELECT ...
FROM (
    SELECT ...
    FROM ... all_matches ...
    LEFT JOIN shared ...
    LEFT JOIN contrast ...
    LEFT JOIN synset_concreteness tc ON tc.synset_id = all_matches.synset_id
    WHERE (
        tc.score >= (SELECT score FROM source_conc)
        OR tc.score IS NULL
        OR (SELECT score FROM source_conc) IS NULL
    )
    ORDER BY ...
    LIMIT ?
) sub
...
```

Note: the source synset_id parameter is used an extra time for the `source_conc` CTE, so the parameter list gains one more `?` — the sourceID is passed 4 times instead of 3.

**Step 2: Run the concreteness tests to verify they pass**

```bash
cd api && go test ./internal/db/ -run TestGetForgeMatchesCurated_Concreteness -v
```

Expected: all 4 concreteness tests pass.

**Step 3: Run ALL existing curated tests to verify no regressions**

```bash
cd api && go test ./internal/db/ -v
```

Expected: all pass. Existing fixture DBs don't have `synset_concreteness` table, so we need to handle that gracefully — the table might not exist. Two options:
- Create the table in all existing test fixture setups (simplest)
- Or use a conditional check in the query

The simplest approach: add `CREATE TABLE IF NOT EXISTS synset_concreteness (...)` to all existing `setup*TestDB` functions that test forge queries. This is a one-liner per fixture and keeps the production query clean.

**Step 4: Commit**

```bash
git add api/internal/db/db.go api/internal/db/db_curated_test.go
git commit -m "feat(api): add concreteness gate to GetForgeMatchesCurated"
```

---

### Task 8: Write failing Go tests for concreteness gate in GetForgeMatchesCuratedByLemma

**Files:**
- Modify: `api/internal/db/db_curated_test.go`

**Step 1: Write the failing tests**

Add concreteness data to the existing `setupSenseAlignmentTestDB` fixture and add tests. The ByLemma query has multiple source senses — the gate should compare each candidate against its matched source sense's concreteness.

```go
func setupSenseAlignmentConcretenessTestDB(t *testing.T) *sql.DB {
	t.Helper()
	tmpDir := t.TempDir()
	dbPath := filepath.Join(tmpDir, "test.db")

	db, err := sql.Open("sqlite3", dbPath)
	if err != nil {
		t.Fatal(err)
	}

	_, err = db.Exec(`
		CREATE TABLE synsets (synset_id TEXT PRIMARY KEY, pos TEXT, definition TEXT);
		CREATE TABLE lemmas (lemma TEXT, synset_id TEXT, PRIMARY KEY (lemma, synset_id));
		CREATE TABLE property_vocab_curated (
			vocab_id INTEGER PRIMARY KEY, synset_id TEXT NOT NULL,
			lemma TEXT NOT NULL, pos TEXT NOT NULL, polysemy INTEGER NOT NULL
		);
		CREATE TABLE vocab_clusters (
			vocab_id INTEGER PRIMARY KEY, cluster_id INTEGER NOT NULL,
			is_representative INTEGER NOT NULL DEFAULT 0, is_singleton INTEGER NOT NULL DEFAULT 0
		);
		CREATE INDEX idx_vc_cluster_sc ON vocab_clusters(cluster_id);
		CREATE TABLE synset_properties_curated (
			synset_id TEXT NOT NULL, vocab_id INTEGER NOT NULL, cluster_id INTEGER NOT NULL,
			snap_method TEXT NOT NULL, snap_score REAL, salience_sum REAL NOT NULL DEFAULT 1.0,
			PRIMARY KEY (synset_id, cluster_id)
		);
		CREATE INDEX idx_spc_sc_synset ON synset_properties_curated(synset_id);
		CREATE INDEX idx_spc_sc_cluster ON synset_properties_curated(cluster_id);
		CREATE TABLE cluster_antonyms (
			cluster_id_a INTEGER NOT NULL, cluster_id_b INTEGER NOT NULL,
			PRIMARY KEY (cluster_id_a, cluster_id_b)
		);
		CREATE TABLE synset_concreteness (
			synset_id TEXT PRIMARY KEY, score REAL NOT NULL, source TEXT NOT NULL
		);

		-- Source "light" has two senses
		-- light-photon (concrete: 4.5) and light-weight (abstract: 2.0)
		INSERT INTO synsets VALUES ('light-photon', 'n', 'electromagnetic radiation');
		INSERT INTO synsets VALUES ('light-weight', 'a', 'not heavy');
		INSERT INTO lemmas VALUES ('light', 'light-photon');
		INSERT INTO lemmas VALUES ('light', 'light-weight');
		INSERT INTO synset_concreteness VALUES ('light-photon', 4.5, 'brysbaert');
		INSERT INTO synset_concreteness VALUES ('light-weight', 2.0, 'brysbaert');

		-- Properties (all singletons)
		INSERT INTO property_vocab_curated VALUES (1, 'v1', 'bright', 'a', 1);
		INSERT INTO property_vocab_curated VALUES (2, 'v2', 'warm', 'a', 1);
		INSERT INTO property_vocab_curated VALUES (3, 'v3', 'airy', 'a', 1);
		INSERT INTO property_vocab_curated VALUES (4, 'v4', 'floating', 'a', 1);
		INSERT INTO vocab_clusters VALUES (1, 1, 1, 1);
		INSERT INTO vocab_clusters VALUES (2, 2, 1, 1);
		INSERT INTO vocab_clusters VALUES (3, 3, 1, 1);
		INSERT INTO vocab_clusters VALUES (4, 4, 1, 1);

		-- light-photon has: bright, warm
		INSERT INTO synset_properties_curated (synset_id, vocab_id, cluster_id, snap_method, snap_score)
			VALUES ('light-photon', 1, 1, 'exact', NULL);
		INSERT INTO synset_properties_curated (synset_id, vocab_id, cluster_id, snap_method, snap_score)
			VALUES ('light-photon', 2, 2, 'exact', NULL);

		-- light-weight has: airy, floating
		INSERT INTO synset_properties_curated (synset_id, vocab_id, cluster_id, snap_method, snap_score)
			VALUES ('light-weight', 3, 3, 'exact', NULL);
		INSERT INTO synset_properties_curated (synset_id, vocab_id, cluster_id, snap_method, snap_score)
			VALUES ('light-weight', 4, 4, 'exact', NULL);

		-- Target: sun (concrete 4.8, shares bright+warm with light-photon)
		-- Source sense light-photon is 4.5, sun is 4.8 → PASS (4.8 >= 4.5)
		INSERT INTO synsets VALUES ('tgt-sun', 'n', 'the star');
		INSERT INTO lemmas VALUES ('sun', 'tgt-sun');
		INSERT INTO synset_properties_curated (synset_id, vocab_id, cluster_id, snap_method, snap_score)
			VALUES ('tgt-sun', 1, 1, 'exact', NULL);
		INSERT INTO synset_properties_curated (synset_id, vocab_id, cluster_id, snap_method, snap_score)
			VALUES ('tgt-sun', 2, 2, 'exact', NULL);
		INSERT INTO synset_concreteness VALUES ('tgt-sun', 4.8, 'brysbaert');

		-- Target: feather (concrete 4.9, shares airy+floating with light-weight)
		-- Source sense light-weight is 2.0, feather is 4.9 → PASS (4.9 >= 2.0)
		INSERT INTO synsets VALUES ('tgt-feather', 'n', 'a plume');
		INSERT INTO lemmas VALUES ('feather', 'tgt-feather');
		INSERT INTO synset_properties_curated (synset_id, vocab_id, cluster_id, snap_method, snap_score)
			VALUES ('tgt-feather', 3, 3, 'exact', NULL);
		INSERT INTO synset_properties_curated (synset_id, vocab_id, cluster_id, snap_method, snap_score)
			VALUES ('tgt-feather', 4, 4, 'exact', NULL);
		INSERT INTO synset_concreteness VALUES ('tgt-feather', 4.9, 'brysbaert');

		-- Target: mood (abstract 1.5, shares airy+floating with light-weight)
		-- Source sense light-weight is 2.0, mood is 1.5 → FAIL (1.5 < 2.0)
		INSERT INTO synsets VALUES ('tgt-mood', 'n', 'emotional state');
		INSERT INTO lemmas VALUES ('mood', 'tgt-mood');
		INSERT INTO synset_properties_curated (synset_id, vocab_id, cluster_id, snap_method, snap_score)
			VALUES ('tgt-mood', 3, 3, 'exact', NULL);
		INSERT INTO synset_properties_curated (synset_id, vocab_id, cluster_id, snap_method, snap_score)
			VALUES ('tgt-mood', 4, 4, 'exact', NULL);
		INSERT INTO synset_concreteness VALUES ('tgt-mood', 1.5, 'brysbaert');
	`)
	if err != nil {
		t.Fatal(err)
	}

	return db
}

func TestGetForgeMatchesCuratedByLemma_ConcretenessGatePassesConcrete(t *testing.T) {
	db := setupSenseAlignmentConcretenessTestDB(t)
	defer db.Close()

	matches, err := GetForgeMatchesCuratedByLemma(db, "light", 50)
	if err != nil {
		t.Fatal(err)
	}

	var foundSun, foundFeather bool
	for _, m := range matches {
		if m.Word == "sun" {
			foundSun = true
		}
		if m.Word == "feather" {
			foundFeather = true
		}
	}
	if !foundSun {
		t.Error("expected sun to pass concreteness gate")
	}
	if !foundFeather {
		t.Error("expected feather to pass concreteness gate")
	}
}

func TestGetForgeMatchesCuratedByLemma_ConcretenessGateFiltersAbstract(t *testing.T) {
	db := setupSenseAlignmentConcretenessTestDB(t)
	defer db.Close()

	matches, err := GetForgeMatchesCuratedByLemma(db, "light", 50)
	if err != nil {
		t.Fatal(err)
	}

	for _, m := range matches {
		if m.Word == "mood" {
			t.Error("expected mood (less concrete than light-weight source sense) to be filtered")
		}
	}
}
```

**Step 2: Run tests to verify they fail**

```bash
cd api && go test ./internal/db/ -run TestGetForgeMatchesCuratedByLemma_Concreteness -v
```

Expected: mood appears in results (gate not implemented yet).

**Step 3: Commit**

```bash
git add api/internal/db/db_curated_test.go
git commit -m "test(api): add failing tests for concreteness gate in GetForgeMatchesCuratedByLemma"
```

---

### Task 9: Implement concreteness gate in GetForgeMatchesCuratedByLemma

**Files:**
- Modify: `api/internal/db/db.go:215-323` (`GetForgeMatchesCuratedByLemma` function)

**Step 1: Add the gate to the ByLemma query**

This query already has per-sense matching via `best_sense`. The gate should filter in `best_sense` or in the final `WHERE bs.rn = 1` clause. The cleanest approach: LEFT JOIN `synset_concreteness` for both the source sense and the target in the final SELECT, and add a WHERE filter.

After `WHERE bs.rn = 1`, add:

```sql
-- Concreteness gate: keep if target >= source, or either is NULL
LEFT JOIN synset_concreteness sc_src ON sc_src.synset_id = bs.source_id
LEFT JOIN synset_concreteness sc_tgt ON sc_tgt.synset_id = bs.target_id
WHERE bs.rn = 1
  AND (sc_tgt.score >= sc_src.score OR sc_tgt.score IS NULL OR sc_src.score IS NULL)
```

**Step 2: Run all concreteness tests**

```bash
cd api && go test ./internal/db/ -run Concreteness -v
```

Expected: all pass.

**Step 3: Run full Go test suite**

```bash
cd api && go test ./... -v
```

Expected: all pass.

**Step 4: Commit**

```bash
git add api/internal/db/db.go
git commit -m "feat(api): add concreteness gate to GetForgeMatchesCuratedByLemma"
```

---

### Task 10: Existing test fixture compatibility

**Files:**
- Modify: `api/internal/db/db_curated_test.go`

**Step 1: Add synset_concreteness table to existing fixtures**

Add `CREATE TABLE IF NOT EXISTS synset_concreteness (synset_id TEXT PRIMARY KEY, score REAL NOT NULL, source TEXT NOT NULL);` to:
- `setupCuratedTestDB`
- `setupSenseAlignmentTestDB`
- `setupLimitTestDB`

These fixtures have no concreteness rows, so the gate passes all candidates through (as designed).

**Step 2: Run full test suite**

```bash
cd api && go test ./... -v
```

Expected: all pass.

**Step 3: Commit**

```bash
git add api/internal/db/db_curated_test.go
git commit -m "test(api): add synset_concreteness table to existing test fixtures"
```

Note: This task may need to be done earlier (as part of Task 7) if existing tests break when the query references `synset_concreteness`. The implementer should merge this into Task 7 if needed.

---

### Task 11: Run concreteness import and MRR evaluation

**Files:**
- No code changes — this is a pipeline execution and measurement task.

**Step 1: Run the concreteness import**

```bash
source .venv/bin/activate && python data-pipeline/scripts/import_concreteness.py
```

Record the output: coverage percentage, scored vs unscored synsets.

**Step 2: Verify data in DB**

```bash
sqlite3 data-pipeline/output/lexicon_v2.db "SELECT COUNT(*) FROM synset_concreteness"
sqlite3 data-pipeline/output/lexicon_v2.db "SELECT AVG(score), MIN(score), MAX(score) FROM synset_concreteness"
sqlite3 data-pipeline/output/lexicon_v2.db "SELECT source, COUNT(*) FROM synset_concreteness GROUP BY source"
```

**Step 3: Run MRR evaluation**

```bash
source .venv/bin/activate
python data-pipeline/scripts/evaluate_mrr.py \
  --db data-pipeline/output/lexicon_v2.db --port 9091 -v \
  -o data-pipeline/output/eval_concreteness_gate.json
```

Compare MRR against baseline 0.0358. Expectation: flat or slight improvement.

**Step 4: Record results and commit**

Commit the evaluation results JSON and add a note to the design doc with the actual numbers.

```bash
git add data-pipeline/output/eval_concreteness_gate.json
git commit -m "data: concreteness gate MRR evaluation results"
```

---

### Task 12: Update documentation

**Files:**
- Modify: `data-pipeline/CLAUDE.md` — add Brysbaert concreteness to the Data Sources table
- Modify: `data-pipeline/SCHEMA.sql` — ensure `synset_concreteness` DDL is present (done in Task 5)
- Modify: `docs/designs/cascade-scoring-roadmap.md` — mark P2 as complete

**Step 1: Update data-pipeline/CLAUDE.md data sources table**

Add Brysbaert concreteness to the Data Sources table:

```
| Brysbaert Concreteness | Word concreteness ratings (1-5) | `data-pipeline/input/brysbaert-concreteness/*.txt` | https://github.com/ArtsEngine/concreteness | CC-BY |
```

**Step 2: Mark P2 complete in cascade-scoring-roadmap.md**

Change:
```
- [ ] **P2: Concreteness gate**
```
To:
```
- [x] **P2: Concreteness gate** — Brysbaert ratings, synset-level mean, SQL gate in both forge queries. MRR: [result].
```

**Step 3: Commit**

```bash
git add data-pipeline/CLAUDE.md docs/designs/cascade-scoring-roadmap.md
git commit -m "docs: update pipeline docs and mark P2 concreteness gate complete"
```
