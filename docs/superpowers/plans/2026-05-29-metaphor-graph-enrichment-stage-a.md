# Metaphor Graph Enrichment — Stage A Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Populate `metaphor_bridges` + `metaphor_bridge_steps` with proposals from four proposers (`cascade_v1`, `haiku_v1`, `haiku_sonnet_v1`, `haiku_v1_inapt_synthesised`) over the 200-topic Karpathy Loop 2 cohort. Idempotent, batched, no judgments written.

**Architecture:** Four independent ingest scripts (one per proposer) + a batch driver that walks 10 × 20 topics. All ingests share a single pre-flight topic-snap artefact. All write through `metaphor_graph.insert_bridge_with_raw_path` so the existing schema invariants and `BridgeSnapFailure` semantics apply uniformly.

**Tech Stack:** Python 3.12, SQLite 3, NLTK lemmatiser (already vendored in `metaphor_graph`), `lib/claude_client.prompt_json` for LLM calls, `subprocess` + `requests` for Go cascade harness.

**Spec:** `docs/superpowers/specs/2026-05-28-metaphor-graph-enrichment-stage-a.md`
**Branch:** `metaphor-graph/enrich-stage-a` (off `metaphor-graph/schema-base`)

---

## File Structure

| File | Purpose |
|------|---------|
| `data-pipeline/scripts/metaphor_graph_enrich_topics.py` | Pre-flight: snap 200 topic strings → curated synset_ids; write `metaphor_graph_topics_snapped.json` artefact |
| `data-pipeline/scripts/metaphor_graph_enrich_haiku.py` | Ingest Haiku Phase 2 apt JSONL → `proposer='haiku_v1'` bridges |
| `data-pipeline/scripts/metaphor_graph_enrich_inapt.py` | Synthesise weak-dim path from inapt Phase 2 JSONL (LLM call) → `proposer='haiku_v1_inapt_synthesised'` bridges |
| `data-pipeline/scripts/metaphor_graph_enrich_cascade.py` | Subprocess Go binary, query `/forge/suggest`, ingest → `proposer='cascade_v1'` bridges |
| `data-pipeline/scripts/metaphor_graph_enrich_sonnet.py` | Sonnet editorial-rewrite call + ingest → `proposer='haiku_sonnet_v1'` bridges |
| `data-pipeline/scripts/metaphor_graph_enrich_run.py` | Batch driver: walks 10 × 20 topics, calls four ingest functions per batch, writes progress markdown |
| `data-pipeline/scripts/test_metaphor_graph_enrich_topics.py` | Unit tests for topic-snap pre-flight |
| `data-pipeline/scripts/test_metaphor_graph_enrich_haiku.py` | Unit tests for Haiku apt ingest |
| `data-pipeline/scripts/test_metaphor_graph_enrich_inapt.py` | Unit tests for inapt synthesis + ingest |
| `data-pipeline/scripts/test_metaphor_graph_enrich_cascade.py` | Unit tests for cascade ingest |
| `data-pipeline/scripts/test_metaphor_graph_enrich_sonnet.py` | Unit tests for Sonnet edit + ingest |
| `data-pipeline/scripts/test_metaphor_graph_enrich_run.py` | Unit tests for batch driver + integration smoke |

## Shared Conventions

**Output paths** (relative to repo root):
- Snapped topics: `data-pipeline/output/metaphor_graph_topics_snapped.json`
- Inapt synth log: `data-pipeline/output/haiku_v1_inapt_synthesised_paths.jsonl`
- Sonnet audit log: `data-pipeline/output/metaphor_graph_sonnet_edits_<TS>.jsonl` (TS = `%Y%m%dT%H%M%S`)
- Progress markdown: `data-pipeline/output/metaphor_graph_enrich_progress.md`

**Topic input:** `data-pipeline/scripts/spike_2_topics.json` — 200 topics, fields `{word, gloss, source}`.

**Existing Haiku apt JSONL:** `data-pipeline/output/metaphor_spike_apt_phase2_20260525T004154.jsonl` — 200 lines, each `{topic, metaphors: [{vehicle, shared_features: [{dimension, concept}]}], _gloss}`.

**Existing Haiku inapt JSONL:** `data-pipeline/output/metaphor_spike_inapt_phase2_20260525T004154.jsonl` — 200 lines, each `{topic, inapt_metaphors: [{vehicle, inapt_reason_type, explanation}], _gloss}`.

**Snapped-topics artefact shape:**

```json
{
  "snapped": [{"word": "anger", "gloss": "...", "source": "phase_1b_spine", "topic_synset_id": "07515974"}],
  "dropped": [{"word": "...", "gloss": "...", "source": "...", "reason": "no_curated_synset"}],
  "snap_rate": 0.945,
  "input_count": 200,
  "snapped_count": 189
}
```

**Ingest function return shape (every ingest fn):**

```python
{
  "proposer": "haiku_v1",
  "topics_processed": int,
  "bridges_inserted": int,
  "bridges_skipped_existing": int,
  "bridges_skipped_snap_failure": int,
  "snap_failures": [{"topic": str, "vehicle": str, "failing_concepts": [str]}],
}
```

---

### Task 1: Topic snap pre-flight

**Files:**
- Create: `data-pipeline/scripts/metaphor_graph_enrich_topics.py`
- Create: `data-pipeline/scripts/test_metaphor_graph_enrich_topics.py`

- [ ] **Step 1: Write the failing test**

```python
# data-pipeline/scripts/test_metaphor_graph_enrich_topics.py
"""Tests for metaphor_graph_enrich_topics.snap_topics."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from metaphor_graph import apply_schema
from metaphor_graph_enrich_topics import snap_topics


@pytest.fixture
def conn() -> sqlite3.Connection:
    c = sqlite3.connect(":memory:", isolation_level=None, autocommit=True)
    c.execute("PRAGMA foreign_keys = ON")
    c.executescript("""
        CREATE TABLE synsets (synset_id TEXT PRIMARY KEY, pos TEXT NOT NULL, gloss TEXT);
        CREATE TABLE lemmas (lemma TEXT NOT NULL, synset_id TEXT NOT NULL REFERENCES synsets(synset_id));
        CREATE TABLE property_vocab_curated (synset_id TEXT NOT NULL UNIQUE REFERENCES synsets(synset_id), lemma TEXT NOT NULL);
        INSERT INTO synsets VALUES ('s_anger', 'n', 'anger gloss'), ('s_time', 'n', 'time gloss');
        INSERT INTO lemmas VALUES ('anger', 's_anger'), ('time', 's_time');
        INSERT INTO property_vocab_curated VALUES ('s_anger', 'anger'), ('s_time', 'time');
    """)
    apply_schema(c)
    yield c
    c.close()


def test_snap_topics_partitions_input(conn, tmp_path):
    topics_path = tmp_path / "topics.json"
    topics_path.write_text(json.dumps({
        "phase": "2",
        "topics": [
            {"word": "anger", "gloss": "a strong feeling", "source": "phase_1b_spine"},
            {"word": "time", "gloss": "an indefinite period", "source": "phase_1b_spine"},
            {"word": "qwertyfake", "gloss": "not real", "source": "test"},
        ],
    }))
    output_path = tmp_path / "snapped.json"

    report = snap_topics(conn, str(topics_path), str(output_path))

    assert report["input_count"] == 3
    assert report["snapped_count"] == 2
    assert report["snap_rate"] == pytest.approx(2 / 3)

    written = json.loads(output_path.read_text())
    assert {t["word"] for t in written["snapped"]} == {"anger", "time"}
    assert all("topic_synset_id" in t for t in written["snapped"])
    assert {t["word"] for t in written["dropped"]} == {"qwertyfake"}
    assert all(t["reason"] == "no_curated_synset" for t in written["dropped"])


def test_snap_topics_idempotent_rewrites_output(conn, tmp_path):
    topics_path = tmp_path / "topics.json"
    topics_path.write_text(json.dumps({"topics": [{"word": "anger", "gloss": "g", "source": "s"}]}))
    output_path = tmp_path / "snapped.json"

    snap_topics(conn, str(topics_path), str(output_path))
    snap_topics(conn, str(topics_path), str(output_path))

    written = json.loads(output_path.read_text())
    assert len(written["snapped"]) == 1
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd data-pipeline && .venv/bin/python -m pytest scripts/test_metaphor_graph_enrich_topics.py -v
```

Expected: `ModuleNotFoundError: No module named 'metaphor_graph_enrich_topics'`

- [ ] **Step 3: Write minimal implementation**

```python
# data-pipeline/scripts/metaphor_graph_enrich_topics.py
"""Pre-flight: snap topic strings from spike_2_topics.json to curated synset_ids.

Writes a partition of {snapped, dropped} to a JSON artefact consumed by all
downstream Stage A ingest scripts. Idempotent — re-running overwrites the
output file with the same partition.
"""
from __future__ import annotations

import argparse
import json
import logging
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from metaphor_graph import snap_concept_string  # noqa: E402

log = logging.getLogger(__name__)


def snap_topics(
    conn: sqlite3.Connection,
    topics_json_path: str,
    output_json_path: str,
) -> dict:
    """Snap each topic's `word` to a curated synset_id via snap_concept_string.

    Returns the same dict written to output_json_path: counts, snap_rate, and
    the {snapped, dropped} partition.
    """
    with open(topics_json_path) as f:
        topics_in = json.load(f)["topics"]

    snapped: list[dict] = []
    dropped: list[dict] = []
    for t in topics_in:
        sid = snap_concept_string(conn, t["word"])
        if sid is None:
            dropped.append({**t, "reason": "no_curated_synset"})
        else:
            snapped.append({**t, "topic_synset_id": sid})

    report = {
        "input_count": len(topics_in),
        "snapped_count": len(snapped),
        "snap_rate": len(snapped) / max(1, len(topics_in)),
        "snapped": snapped,
        "dropped": dropped,
    }
    Path(output_json_path).write_text(json.dumps(report, indent=2))
    log.info(
        "snap_topics: snapped=%d dropped=%d snap_rate=%.3f",
        len(snapped), len(dropped), report["snap_rate"],
    )
    return report


def main() -> int:
    logging.basicConfig(level=logging.INFO)
    p = argparse.ArgumentParser()
    p.add_argument("--db", required=True)
    p.add_argument("--topics", required=True)
    p.add_argument("--output", required=True)
    args = p.parse_args()
    conn = sqlite3.connect(args.db, isolation_level=None, autocommit=True)
    conn.execute("PRAGMA foreign_keys = ON")
    report = snap_topics(conn, args.topics, args.output)
    if report["snap_rate"] < 0.9:
        log.warning("snap rate %.3f below 0.9 threshold — cohort may need curation", report["snap_rate"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd data-pipeline && .venv/bin/python -m pytest scripts/test_metaphor_graph_enrich_topics.py -v
```

Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add data-pipeline/scripts/metaphor_graph_enrich_topics.py data-pipeline/scripts/test_metaphor_graph_enrich_topics.py
git commit -m "feat(metaphor-graph): topic-snap pre-flight for Stage A enrichment"
```

---

### Task 2: Haiku Phase 2 apt ingest

**Files:**
- Create: `data-pipeline/scripts/metaphor_graph_enrich_haiku.py`
- Create: `data-pipeline/scripts/test_metaphor_graph_enrich_haiku.py`

- [ ] **Step 1: Write the failing test**

```python
# data-pipeline/scripts/test_metaphor_graph_enrich_haiku.py
"""Tests for metaphor_graph_enrich_haiku.ingest_haiku_apt."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from metaphor_graph import apply_schema
from metaphor_graph_enrich_haiku import ingest_haiku_apt


@pytest.fixture
def conn() -> sqlite3.Connection:
    c = sqlite3.connect(":memory:", isolation_level=None, autocommit=True)
    c.execute("PRAGMA foreign_keys = ON")
    c.executescript("""
        CREATE TABLE synsets (synset_id TEXT PRIMARY KEY, pos TEXT NOT NULL, gloss TEXT);
        CREATE TABLE lemmas (lemma TEXT NOT NULL, synset_id TEXT NOT NULL REFERENCES synsets(synset_id));
        CREATE TABLE property_vocab_curated (synset_id TEXT NOT NULL UNIQUE REFERENCES synsets(synset_id), lemma TEXT NOT NULL);
        INSERT INTO synsets VALUES
          ('s_anger', 'n', 'anger'), ('s_fire', 'n', 'fire'),
          ('s_heat', 'n', 'heat'), ('s_destruction', 'n', 'destruction'),
          ('s_passion', 'n', 'passion');
        INSERT INTO lemmas VALUES
          ('anger', 's_anger'), ('fire', 's_fire'),
          ('heat', 's_heat'), ('destruction', 's_destruction'),
          ('passion', 's_passion');
        INSERT INTO property_vocab_curated VALUES
          ('s_anger', 'anger'), ('s_fire', 'fire'),
          ('s_heat', 'heat'), ('s_destruction', 'destruction'),
          ('s_passion', 'passion');
    """)
    apply_schema(c)
    yield c
    c.close()


@pytest.fixture
def snapped_topics_path(tmp_path):
    p = tmp_path / "snapped.json"
    p.write_text(json.dumps({
        "snapped": [{"word": "anger", "gloss": "g", "source": "s", "topic_synset_id": "s_anger"}],
        "dropped": [],
    }))
    return str(p)


@pytest.fixture
def haiku_apt_jsonl(tmp_path):
    p = tmp_path / "haiku_apt.jsonl"
    p.write_text(json.dumps({
        "topic": "anger",
        "metaphors": [
            {"vehicle": "fire", "shared_features": [
                {"dimension": "sensorimotor", "concept": "heat"},
                {"dimension": "functional", "concept": "destruction"},
            ]},
            {"vehicle": "passion", "shared_features": [
                {"dimension": "sensorimotor", "concept": "heat"},
            ]},
        ],
        "_gloss": "a strong feeling",
    }) + "\n")
    return str(p)


def test_ingest_inserts_one_bridge_per_shared_feature(conn, snapped_topics_path, haiku_apt_jsonl):
    report = ingest_haiku_apt(conn, snapped_topics_path, haiku_apt_jsonl)

    assert report["topics_processed"] == 1
    assert report["bridges_inserted"] == 3  # 2 for fire + 1 for passion
    assert report["bridges_skipped_snap_failure"] == 0

    rows = conn.execute(
        "SELECT topic_synset_id, vehicle_synset_id, proposer FROM metaphor_bridges ORDER BY bridge_id"
    ).fetchall()
    assert all(r[0] == "s_anger" for r in rows)
    assert all(r[2] == "haiku_v1" for r in rows)
    vehicles = sorted(r[1] for r in rows)
    assert vehicles == ["s_fire", "s_fire", "s_passion"]


def test_ingest_is_idempotent(conn, snapped_topics_path, haiku_apt_jsonl):
    ingest_haiku_apt(conn, snapped_topics_path, haiku_apt_jsonl)
    second = ingest_haiku_apt(conn, snapped_topics_path, haiku_apt_jsonl)

    assert second["bridges_inserted"] == 0
    assert second["bridges_skipped_existing"] == 3
    n = conn.execute("SELECT COUNT(*) FROM metaphor_bridges").fetchone()[0]
    assert n == 3


def test_ingest_skips_snap_failures(conn, snapped_topics_path, tmp_path):
    bad = tmp_path / "bad.jsonl"
    bad.write_text(json.dumps({
        "topic": "anger",
        "metaphors": [{"vehicle": "qwertyfake", "shared_features": [{"dimension": "x", "concept": "heat"}]}],
        "_gloss": "g",
    }) + "\n")
    report = ingest_haiku_apt(conn, snapped_topics_path, str(bad))
    assert report["bridges_skipped_snap_failure"] == 1
    assert report["bridges_inserted"] == 0
    assert report["snap_failures"][0]["vehicle"] == "qwertyfake"


def test_ingest_skips_topics_not_in_snapped_set(conn, snapped_topics_path, tmp_path):
    p = tmp_path / "haiku_apt.jsonl"
    p.write_text(
        json.dumps({"topic": "unsnapped_topic", "metaphors": [
            {"vehicle": "fire", "shared_features": [{"dimension": "x", "concept": "heat"}]}
        ], "_gloss": "g"}) + "\n"
    )
    report = ingest_haiku_apt(conn, snapped_topics_path, str(p))
    assert report["topics_processed"] == 0
    assert report["bridges_inserted"] == 0
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd data-pipeline && .venv/bin/python -m pytest scripts/test_metaphor_graph_enrich_haiku.py -v
```

Expected: `ModuleNotFoundError: No module named 'metaphor_graph_enrich_haiku'`

- [ ] **Step 3: Write minimal implementation**

```python
# data-pipeline/scripts/metaphor_graph_enrich_haiku.py
"""Ingest existing Haiku Phase 2 apt JSONL into metaphor_bridges as proposer='haiku_v1'.

Reuses metaphor_graph.insert_bridge_with_raw_path so snap-failure semantics are
identical to the rest of the metaphor-graph pipeline. Idempotent via the
schema's UNIQUE (topic_synset_id, vehicle_synset_id, proposer, path_hash)
constraint — duplicate inserts are caught by sqlite3.IntegrityError and
counted as bridges_skipped_existing.
"""
from __future__ import annotations

import argparse
import json
import logging
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from metaphor_graph import BridgeSnapFailure, insert_bridge_with_raw_path  # noqa: E402

log = logging.getLogger(__name__)


def ingest_haiku_apt(
    conn: sqlite3.Connection,
    snapped_topics_json_path: str,
    haiku_apt_jsonl_path: str,
    *,
    proposer: str = "haiku_v1",
) -> dict:
    snapped = json.loads(Path(snapped_topics_json_path).read_text())
    topic_to_sid = {t["word"]: t["topic_synset_id"] for t in snapped["snapped"]}

    bridges_inserted = 0
    bridges_skipped_existing = 0
    bridges_skipped_snap_failure = 0
    snap_failures: list[dict] = []
    topics_processed = 0

    proposed_at = datetime.now(timezone.utc).isoformat()

    with open(haiku_apt_jsonl_path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            entry = json.loads(line)
            topic = entry["topic"]
            topic_sid = topic_to_sid.get(topic)
            if topic_sid is None:
                continue
            topics_processed += 1
            for m in entry.get("metaphors", []):
                vehicle = m["vehicle"]
                for feat in m.get("shared_features", []):
                    concept = feat["concept"]
                    try:
                        insert_bridge_with_raw_path(
                            conn,
                            topic_synset_id=topic_sid,
                            vehicle_synset_id=vehicle,
                            proposer=proposer,
                            proposed_at=proposed_at,
                            raw_path=[concept],
                        )
                        bridges_inserted += 1
                    except BridgeSnapFailure:
                        bridges_skipped_snap_failure += 1
                        snap_failures.append({
                            "topic": topic, "vehicle": vehicle,
                            "failing_concepts": [concept],
                        })
                    except sqlite3.IntegrityError:
                        bridges_skipped_existing += 1

    report = {
        "proposer": proposer,
        "topics_processed": topics_processed,
        "bridges_inserted": bridges_inserted,
        "bridges_skipped_existing": bridges_skipped_existing,
        "bridges_skipped_snap_failure": bridges_skipped_snap_failure,
        "snap_failures": snap_failures,
    }
    log.info("ingest_haiku_apt: %s", report)
    return report
```

**Note on vehicle snap:** `insert_bridge_with_raw_path` requires the *vehicle* parameter as a pre-resolved synset_id, not a raw string. The test fixtures pass `"s_fire"` directly. For real Phase 2 vehicles (e.g. `"fire"`), the vehicle must first be snapped — handled in Step 3a below.

- [ ] **Step 3a: Add vehicle snap to implementation**

Replace the inner loop in Step 3 with:

```python
            for m in entry.get("metaphors", []):
                vehicle_raw = m["vehicle"]
                from metaphor_graph import snap_concept_string
                vehicle_sid = snap_concept_string(conn, vehicle_raw)
                if vehicle_sid is None:
                    bridges_skipped_snap_failure += 1
                    snap_failures.append({"topic": topic, "vehicle": vehicle_raw, "failing_concepts": ["<vehicle>"]})
                    continue
                for feat in m.get("shared_features", []):
                    concept = feat["concept"]
                    try:
                        insert_bridge_with_raw_path(
                            conn,
                            topic_synset_id=topic_sid,
                            vehicle_synset_id=vehicle_sid,
                            proposer=proposer,
                            proposed_at=proposed_at,
                            raw_path=[concept],
                        )
                        bridges_inserted += 1
                    except BridgeSnapFailure:
                        bridges_skipped_snap_failure += 1
                        snap_failures.append({"topic": topic, "vehicle": vehicle_raw, "failing_concepts": [concept]})
                    except sqlite3.IntegrityError:
                        bridges_skipped_existing += 1
```

And update the test fixture vehicle names to use raw strings (`"fire"`, `"passion"`, `"qwertyfake"`) — already done in the test as written.

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd data-pipeline && .venv/bin/python -m pytest scripts/test_metaphor_graph_enrich_haiku.py -v
```

Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add data-pipeline/scripts/metaphor_graph_enrich_haiku.py data-pipeline/scripts/test_metaphor_graph_enrich_haiku.py
git commit -m "feat(metaphor-graph): Haiku Phase 2 apt JSONL ingest (proposer=haiku_v1)"
```

---

### Task 3: Inapt path synthesis + ingest

**Files:**
- Create: `data-pipeline/scripts/metaphor_graph_enrich_inapt.py`
- Create: `data-pipeline/scripts/test_metaphor_graph_enrich_inapt.py`

- [ ] **Step 1: Write the failing test**

```python
# data-pipeline/scripts/test_metaphor_graph_enrich_inapt.py
"""Tests for metaphor_graph_enrich_inapt: synthesise + ingest."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from metaphor_graph import apply_schema
from metaphor_graph_enrich_inapt import synthesise_paths, ingest_inapt


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:", isolation_level=None, autocommit=True)
    c.execute("PRAGMA foreign_keys = ON")
    c.executescript("""
        CREATE TABLE synsets (synset_id TEXT PRIMARY KEY, pos TEXT NOT NULL, gloss TEXT);
        CREATE TABLE lemmas (lemma TEXT NOT NULL, synset_id TEXT NOT NULL REFERENCES synsets(synset_id));
        CREATE TABLE property_vocab_curated (synset_id TEXT NOT NULL UNIQUE REFERENCES synsets(synset_id), lemma TEXT NOT NULL);
        INSERT INTO synsets VALUES
          ('s_anger', 'n', 'a'), ('s_passion', 'n', 'p'), ('s_heat', 'n', 'h'),
          ('s_intensity', 'n', 'i');
        INSERT INTO lemmas VALUES
          ('anger', 's_anger'), ('passion', 's_passion'),
          ('heat', 's_heat'), ('intensity', 's_intensity');
        INSERT INTO property_vocab_curated VALUES
          ('s_anger', 'anger'), ('s_passion', 'passion'),
          ('s_heat', 'heat'), ('s_intensity', 'intensity');
    """)
    apply_schema(c)
    yield c
    c.close()


@pytest.fixture
def snapped_path(tmp_path):
    p = tmp_path / "snapped.json"
    p.write_text(json.dumps({
        "snapped": [{"word": "anger", "gloss": "g", "source": "s", "topic_synset_id": "s_anger"}],
        "dropped": [],
    }))
    return str(p)


@pytest.fixture
def inapt_jsonl(tmp_path):
    p = tmp_path / "inapt.jsonl"
    p.write_text(json.dumps({
        "topic": "anger",
        "inapt_metaphors": [
            {"vehicle": "passion", "inapt_reason_type": "single_dimension",
             "explanation": "Shares heat but passion is constructive."},
        ],
        "_gloss": "g",
    }) + "\n")
    return str(p)


def test_synthesise_writes_log_and_skips_existing(snapped_path, inapt_jsonl, tmp_path):
    log_path = tmp_path / "synth.jsonl"
    client = MagicMock()
    client.prompt_json.return_value = {"weak_concept": "heat"}

    report = synthesise_paths(client, snapped_path, inapt_jsonl, str(log_path))
    assert report["calls_made"] == 1
    assert report["entries_logged"] == 1
    line = json.loads(log_path.read_text().strip())
    assert line == {"topic": "anger", "vehicle": "passion",
                    "inapt_reason_type": "single_dimension",
                    "weak_concept": "heat",
                    "explanation": "Shares heat but passion is constructive."}

    client.prompt_json.reset_mock()
    report2 = synthesise_paths(client, snapped_path, inapt_jsonl, str(log_path))
    assert report2["calls_made"] == 0
    assert report2["entries_logged"] == 0


def test_ingest_inapt_inserts_bridges_from_log(conn, snapped_path, tmp_path):
    log_path = tmp_path / "synth.jsonl"
    log_path.write_text(json.dumps({
        "topic": "anger", "vehicle": "passion",
        "inapt_reason_type": "single_dimension",
        "weak_concept": "heat",
        "explanation": "Shares heat but passion is constructive.",
    }) + "\n")

    report = ingest_inapt(conn, snapped_path, str(log_path))
    assert report["bridges_inserted"] == 1
    assert report["proposer"] == "haiku_v1_inapt_synthesised"
    row = conn.execute(
        "SELECT proposer, rationale FROM metaphor_bridges"
    ).fetchone()
    assert row[0] == "haiku_v1_inapt_synthesised"
    assert "Shares heat" in row[1]


def test_ingest_inapt_idempotent(conn, snapped_path, tmp_path):
    log_path = tmp_path / "synth.jsonl"
    log_path.write_text(json.dumps({
        "topic": "anger", "vehicle": "passion",
        "inapt_reason_type": "single_dimension",
        "weak_concept": "heat",
        "explanation": "x",
    }) + "\n")
    ingest_inapt(conn, snapped_path, str(log_path))
    r2 = ingest_inapt(conn, snapped_path, str(log_path))
    assert r2["bridges_inserted"] == 0
    assert r2["bridges_skipped_existing"] == 1
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd data-pipeline && .venv/bin/python -m pytest scripts/test_metaphor_graph_enrich_inapt.py -v
```

Expected: `ModuleNotFoundError`.

- [ ] **Step 3: Write minimal implementation**

```python
# data-pipeline/scripts/metaphor_graph_enrich_inapt.py
"""Two-phase inapt enrichment for the metaphor graph.

Phase A — synthesise: per (topic, inapt_vehicle, explanation) from the Haiku
Phase 2 inapt JSONL, ask a cheap LLM to extract a single weak-dimension
concept that captures *why* the metaphor is weak. Append the result to a
synth-log JSONL so subsequent runs do not re-spend the LLM call.

Phase B — ingest: walk the synth-log JSONL and insert one single-step
bridge per entry as proposer='haiku_v1_inapt_synthesised'. The bridge's
rationale carries the original explanation prose verbatim.
"""
from __future__ import annotations

import argparse
import json
import logging
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from metaphor_graph import BridgeSnapFailure, insert_bridge_with_raw_path, snap_concept_string  # noqa: E402

log = logging.getLogger(__name__)

WEAK_DIM_PROMPT = """You are extracting the single weak shared dimension from a failed metaphor.

Topic: {topic}
Vehicle: {vehicle}
Reason type: {inapt_reason_type}
Explanation: {explanation}

Identify the ONE concept (single English word, lowercase, no punctuation) that
captures the weak shared dimension cited in the explanation. This is the
dimension that makes someone *almost* see the metaphor before realising it
doesn't quite work.

Return JSON: {{"weak_concept": "..."}}
"""


def _load_existing_synth(log_path: str) -> set[tuple[str, str]]:
    seen = set()
    p = Path(log_path)
    if not p.exists():
        return seen
    for line in p.read_text().splitlines():
        if not line.strip():
            continue
        entry = json.loads(line)
        seen.add((entry["topic"], entry["vehicle"]))
    return seen


def synthesise_paths(
    claude_client,
    snapped_topics_json_path: str,
    inapt_jsonl_path: str,
    synth_log_path: str,
) -> dict:
    snapped = json.loads(Path(snapped_topics_json_path).read_text())
    topic_set = {t["word"] for t in snapped["snapped"]}
    seen = _load_existing_synth(synth_log_path)

    calls_made = 0
    entries_logged = 0

    with open(synth_log_path, "a") as out:
        with open(inapt_jsonl_path) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                entry = json.loads(line)
                topic = entry["topic"]
                if topic not in topic_set:
                    continue
                for m in entry.get("inapt_metaphors", []):
                    key = (topic, m["vehicle"])
                    if key in seen:
                        continue
                    prompt = WEAK_DIM_PROMPT.format(
                        topic=topic, vehicle=m["vehicle"],
                        inapt_reason_type=m["inapt_reason_type"],
                        explanation=m["explanation"],
                    )
                    resp = claude_client.prompt_json(prompt)
                    calls_made += 1
                    weak = resp["weak_concept"].strip().lower()
                    out.write(json.dumps({
                        "topic": topic, "vehicle": m["vehicle"],
                        "inapt_reason_type": m["inapt_reason_type"],
                        "weak_concept": weak,
                        "explanation": m["explanation"],
                    }) + "\n")
                    out.flush()
                    seen.add(key)
                    entries_logged += 1

    return {"calls_made": calls_made, "entries_logged": entries_logged}


def ingest_inapt(
    conn: sqlite3.Connection,
    snapped_topics_json_path: str,
    synth_log_path: str,
    *,
    proposer: str = "haiku_v1_inapt_synthesised",
) -> dict:
    snapped = json.loads(Path(snapped_topics_json_path).read_text())
    topic_to_sid = {t["word"]: t["topic_synset_id"] for t in snapped["snapped"]}

    bridges_inserted = 0
    bridges_skipped_existing = 0
    bridges_skipped_snap_failure = 0
    snap_failures: list[dict] = []
    topics_processed = 0

    proposed_at = datetime.now(timezone.utc).isoformat()

    with open(synth_log_path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            entry = json.loads(line)
            topic_sid = topic_to_sid.get(entry["topic"])
            if topic_sid is None:
                continue
            topics_processed += 1
            vehicle_sid = snap_concept_string(conn, entry["vehicle"])
            if vehicle_sid is None:
                bridges_skipped_snap_failure += 1
                snap_failures.append({"topic": entry["topic"], "vehicle": entry["vehicle"],
                                      "failing_concepts": ["<vehicle>"]})
                continue
            try:
                insert_bridge_with_raw_path(
                    conn,
                    topic_synset_id=topic_sid,
                    vehicle_synset_id=vehicle_sid,
                    proposer=proposer,
                    proposed_at=proposed_at,
                    raw_path=[entry["weak_concept"]],
                    rationale=entry["explanation"],
                )
                bridges_inserted += 1
            except BridgeSnapFailure:
                bridges_skipped_snap_failure += 1
                snap_failures.append({"topic": entry["topic"], "vehicle": entry["vehicle"],
                                      "failing_concepts": [entry["weak_concept"]]})
            except sqlite3.IntegrityError:
                bridges_skipped_existing += 1

    return {
        "proposer": proposer,
        "topics_processed": topics_processed,
        "bridges_inserted": bridges_inserted,
        "bridges_skipped_existing": bridges_skipped_existing,
        "bridges_skipped_snap_failure": bridges_skipped_snap_failure,
        "snap_failures": snap_failures,
    }
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd data-pipeline && .venv/bin/python -m pytest scripts/test_metaphor_graph_enrich_inapt.py -v
```

Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add data-pipeline/scripts/metaphor_graph_enrich_inapt.py data-pipeline/scripts/test_metaphor_graph_enrich_inapt.py
git commit -m "feat(metaphor-graph): inapt path synthesis + ingest (proposer=haiku_v1_inapt_synthesised)"
```

---

### Task 4: Cascade ingest via Go subprocess

**Files:**
- Create: `data-pipeline/scripts/metaphor_graph_enrich_cascade.py`
- Create: `data-pipeline/scripts/test_metaphor_graph_enrich_cascade.py`

- [ ] **Step 1: Write the failing test**

```python
# data-pipeline/scripts/test_metaphor_graph_enrich_cascade.py
"""Tests for metaphor_graph_enrich_cascade.ingest_cascade.

Subprocess and HTTP layer are dependency-injected so tests don't need to
spin up Go.
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from metaphor_graph import apply_schema
from metaphor_graph_enrich_cascade import ingest_cascade


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:", isolation_level=None, autocommit=True)
    c.execute("PRAGMA foreign_keys = ON")
    c.executescript("""
        CREATE TABLE synsets (synset_id TEXT PRIMARY KEY, pos TEXT NOT NULL, gloss TEXT);
        CREATE TABLE lemmas (lemma TEXT NOT NULL, synset_id TEXT NOT NULL REFERENCES synsets(synset_id));
        CREATE TABLE property_vocab_curated (synset_id TEXT NOT NULL UNIQUE REFERENCES synsets(synset_id), lemma TEXT NOT NULL);
        INSERT INTO synsets VALUES
          ('s_anger', 'n', 'a'), ('s_fire', 'n', 'f'),
          ('s_heat', 'n', 'h'), ('s_destruction', 'n', 'd');
        INSERT INTO lemmas VALUES
          ('anger', 's_anger'), ('fire', 's_fire'),
          ('heat', 's_heat'), ('destruction', 's_destruction');
        INSERT INTO property_vocab_curated VALUES
          ('s_anger', 'anger'), ('s_fire', 'fire'),
          ('s_heat', 'heat'), ('s_destruction', 'destruction');
    """)
    apply_schema(c)
    yield c
    c.close()


@pytest.fixture
def snapped_path(tmp_path):
    p = tmp_path / "snapped.json"
    p.write_text(json.dumps({
        "snapped": [{"word": "anger", "gloss": "g", "source": "s", "topic_synset_id": "s_anger"}],
        "dropped": [],
    }))
    return str(p)


def test_ingest_cascade_inserts_one_bridge_per_shared_property(conn, snapped_path):
    fetcher = MagicMock(return_value={
        "candidates": [
            {"vehicle": "fire", "shared_properties": [
                {"property": "heat"},
                {"property": "destruction"},
            ]},
        ],
    })
    report = ingest_cascade(conn, snapped_path, suggest_fn=fetcher, limit=10)

    assert report["bridges_inserted"] == 2
    assert report["proposer"] == "cascade_v1"
    fetcher.assert_called_once_with(topic="anger", limit=10)
    rows = conn.execute("SELECT vehicle_synset_id FROM metaphor_bridges ORDER BY bridge_id").fetchall()
    assert [r[0] for r in rows] == ["s_fire", "s_fire"]


def test_ingest_cascade_handles_empty_response(conn, snapped_path):
    fetcher = MagicMock(return_value={"candidates": []})
    report = ingest_cascade(conn, snapped_path, suggest_fn=fetcher, limit=10)
    assert report["bridges_inserted"] == 0
    assert report["topics_processed"] == 1
    assert report["topics_empty_response"] == 1


def test_ingest_cascade_idempotent(conn, snapped_path):
    fetcher = MagicMock(return_value={
        "candidates": [{"vehicle": "fire", "shared_properties": [{"property": "heat"}]}],
    })
    ingest_cascade(conn, snapped_path, suggest_fn=fetcher, limit=10)
    r2 = ingest_cascade(conn, snapped_path, suggest_fn=fetcher, limit=10)
    assert r2["bridges_inserted"] == 0
    assert r2["bridges_skipped_existing"] == 1
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd data-pipeline && .venv/bin/python -m pytest scripts/test_metaphor_graph_enrich_cascade.py -v
```

Expected: `ModuleNotFoundError`.

- [ ] **Step 3: Write minimal implementation**

```python
# data-pipeline/scripts/metaphor_graph_enrich_cascade.py
"""Cascade ingest: query Go /forge/suggest per topic, ingest as proposer='cascade_v1'.

The Go binary lifecycle (start on free port, wait healthy, kill) is delegated
to a suggest_fn callable so tests can substitute a mock. The CLI entrypoint
provides the real implementation: subprocess Popen + requests.get poll.
"""
from __future__ import annotations

import argparse
import json
import logging
import sqlite3
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

sys.path.insert(0, str(Path(__file__).resolve().parent))

from metaphor_graph import BridgeSnapFailure, insert_bridge_with_raw_path, snap_concept_string  # noqa: E402

log = logging.getLogger(__name__)


def ingest_cascade(
    conn: sqlite3.Connection,
    snapped_topics_json_path: str,
    *,
    suggest_fn: Callable[..., dict],
    limit: int = 10,
    proposer: str = "cascade_v1",
) -> dict:
    snapped = json.loads(Path(snapped_topics_json_path).read_text())
    bridges_inserted = 0
    bridges_skipped_existing = 0
    bridges_skipped_snap_failure = 0
    snap_failures: list[dict] = []
    topics_processed = 0
    topics_empty_response = 0

    proposed_at = datetime.now(timezone.utc).isoformat()

    for t in snapped["snapped"]:
        topics_processed += 1
        resp = suggest_fn(topic=t["word"], limit=limit)
        candidates = resp.get("candidates", [])
        if not candidates:
            topics_empty_response += 1
            continue
        for c in candidates:
            vehicle_raw = c["vehicle"]
            vehicle_sid = snap_concept_string(conn, vehicle_raw)
            if vehicle_sid is None:
                bridges_skipped_snap_failure += 1
                snap_failures.append({"topic": t["word"], "vehicle": vehicle_raw,
                                      "failing_concepts": ["<vehicle>"]})
                continue
            for sp in c.get("shared_properties", []):
                prop = sp["property"] if isinstance(sp, dict) else sp
                try:
                    insert_bridge_with_raw_path(
                        conn,
                        topic_synset_id=t["topic_synset_id"],
                        vehicle_synset_id=vehicle_sid,
                        proposer=proposer,
                        proposed_at=proposed_at,
                        raw_path=[prop],
                    )
                    bridges_inserted += 1
                except BridgeSnapFailure:
                    bridges_skipped_snap_failure += 1
                    snap_failures.append({"topic": t["word"], "vehicle": vehicle_raw,
                                          "failing_concepts": [prop]})
                except sqlite3.IntegrityError:
                    bridges_skipped_existing += 1

    return {
        "proposer": proposer,
        "topics_processed": topics_processed,
        "topics_empty_response": topics_empty_response,
        "bridges_inserted": bridges_inserted,
        "bridges_skipped_existing": bridges_skipped_existing,
        "bridges_skipped_snap_failure": bridges_skipped_snap_failure,
        "snap_failures": snap_failures,
    }


def make_go_suggest_fn(binary_path: str, db_path: str, port: int = 9192) -> Callable[..., dict]:
    """Start Go binary, return a suggest_fn that queries /forge/suggest.

    Caller is responsible for terminating via the returned fn's `_proc` attr.
    """
    import requests  # local import — tests do not need this dependency
    proc = subprocess.Popen(
        [binary_path, "--db", db_path, "--port", str(port)],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    base = f"http://127.0.0.1:{port}"
    deadline = time.time() + 30
    while time.time() < deadline:
        try:
            r = requests.get(f"{base}/health", timeout=1)
            if r.status_code == 200:
                break
        except requests.RequestException:
            time.sleep(0.2)
    else:
        proc.terminate()
        raise RuntimeError("Go binary did not become healthy within 30s")

    def fn(*, topic: str, limit: int) -> dict:
        r = requests.get(f"{base}/forge/suggest", params={"word": topic, "limit": limit}, timeout=30)
        r.raise_for_status()
        return r.json()

    fn._proc = proc  # type: ignore[attr-defined]
    return fn
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd data-pipeline && .venv/bin/python -m pytest scripts/test_metaphor_graph_enrich_cascade.py -v
```

Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add data-pipeline/scripts/metaphor_graph_enrich_cascade.py data-pipeline/scripts/test_metaphor_graph_enrich_cascade.py
git commit -m "feat(metaphor-graph): cascade ingest via Go subprocess (proposer=cascade_v1)"
```

---

### Task 5: Sonnet edit + ingest

**Files:**
- Create: `data-pipeline/scripts/metaphor_graph_enrich_sonnet.py`
- Create: `data-pipeline/scripts/test_metaphor_graph_enrich_sonnet.py`

- [ ] **Step 1: Write the failing test**

```python
# data-pipeline/scripts/test_metaphor_graph_enrich_sonnet.py
"""Tests for metaphor_graph_enrich_sonnet: edit + ingest."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from metaphor_graph import apply_schema
from metaphor_graph_enrich_sonnet import run_sonnet_edits, ingest_sonnet


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:", isolation_level=None, autocommit=True)
    c.execute("PRAGMA foreign_keys = ON")
    c.executescript("""
        CREATE TABLE synsets (synset_id TEXT PRIMARY KEY, pos TEXT NOT NULL, gloss TEXT);
        CREATE TABLE lemmas (lemma TEXT NOT NULL, synset_id TEXT NOT NULL REFERENCES synsets(synset_id));
        CREATE TABLE property_vocab_curated (synset_id TEXT NOT NULL UNIQUE REFERENCES synsets(synset_id), lemma TEXT NOT NULL);
        INSERT INTO synsets VALUES
          ('s_anger', 'n', 'a'), ('s_fire', 'n', 'f'),
          ('s_heat', 'n', 'h'), ('s_intensity', 'n', 'i'),
          ('s_volcano', 'n', 'v');
        INSERT INTO lemmas VALUES
          ('anger', 's_anger'), ('fire', 's_fire'),
          ('heat', 's_heat'), ('intensity', 's_intensity'),
          ('volcano', 's_volcano');
        INSERT INTO property_vocab_curated VALUES
          ('s_anger', 'anger'), ('s_fire', 'fire'),
          ('s_heat', 'heat'), ('s_intensity', 'intensity'),
          ('s_volcano', 'volcano');
    """)
    apply_schema(c)
    yield c
    c.close()


@pytest.fixture
def snapped_path(tmp_path):
    p = tmp_path / "snapped.json"
    p.write_text(json.dumps({
        "snapped": [{"word": "anger", "gloss": "g", "source": "s", "topic_synset_id": "s_anger"}],
        "dropped": [],
    }))
    return str(p)


@pytest.fixture
def haiku_apt_jsonl(tmp_path):
    p = tmp_path / "haiku_apt.jsonl"
    p.write_text(json.dumps({
        "topic": "anger",
        "metaphors": [{"vehicle": "fire", "shared_features": [{"dimension": "x", "concept": "heat"}]}],
        "_gloss": "a strong feeling",
    }) + "\n")
    return str(p)


def test_run_sonnet_edits_writes_audit_jsonl(snapped_path, haiku_apt_jsonl, tmp_path):
    audit = tmp_path / "sonnet_audit.jsonl"
    client = MagicMock()
    client.prompt_json.return_value = {
        "topic": "anger", "vehicles": [
            {"vehicle": "volcano", "path_concepts": ["heat", "intensity"]}
        ]
    }
    report = run_sonnet_edits(client, snapped_path, haiku_apt_jsonl, str(audit))

    assert report["calls_made"] == 1
    line = json.loads(audit.read_text().strip())
    assert line["topic"] == "anger"
    assert line["vehicles"][0]["vehicle"] == "volcano"


def test_ingest_sonnet_inserts_from_audit(conn, snapped_path, tmp_path):
    audit = tmp_path / "sonnet_audit.jsonl"
    audit.write_text(json.dumps({
        "topic": "anger",
        "vehicles": [
            {"vehicle": "volcano", "path_concepts": ["heat", "intensity"]}
        ],
    }) + "\n")
    report = ingest_sonnet(conn, snapped_path, str(audit))

    assert report["bridges_inserted"] == 2
    assert report["proposer"] == "haiku_sonnet_v1"
    rows = conn.execute("SELECT vehicle_synset_id, proposer FROM metaphor_bridges").fetchall()
    assert all(r[0] == "s_volcano" and r[1] == "haiku_sonnet_v1" for r in rows)


def test_ingest_sonnet_idempotent(conn, snapped_path, tmp_path):
    audit = tmp_path / "sonnet_audit.jsonl"
    audit.write_text(json.dumps({
        "topic": "anger",
        "vehicles": [{"vehicle": "volcano", "path_concepts": ["heat"]}],
    }) + "\n")
    ingest_sonnet(conn, snapped_path, str(audit))
    r2 = ingest_sonnet(conn, snapped_path, str(audit))
    assert r2["bridges_inserted"] == 0
    assert r2["bridges_skipped_existing"] == 1
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd data-pipeline && .venv/bin/python -m pytest scripts/test_metaphor_graph_enrich_sonnet.py -v
```

Expected: `ModuleNotFoundError`.

- [ ] **Step 3: Write minimal implementation**

```python
# data-pipeline/scripts/metaphor_graph_enrich_sonnet.py
"""Sonnet editorial-rewrite pass + ingest.

Per topic, send Sonnet the full Haiku apt entry (topic, gloss, all Haiku
vehicles + their shared_features) with a prompt instructing full editorial
rewrite: substitute weak vehicles, sharpen paths, return polished list of 10
vehicles each with 3-6 one-word path concepts. Audit JSONL records Sonnet's
verbatim response so post-hoc inspection of editorial decisions is possible
even if the schema or ingest semantics change.
"""
from __future__ import annotations

import argparse
import json
import logging
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from metaphor_graph import BridgeSnapFailure, insert_bridge_with_raw_path, snap_concept_string  # noqa: E402

log = logging.getLogger(__name__)

SONNET_EDIT_PROMPT = """You are a literary metaphor editor reviewing a junior writer's draft.

Topic: {topic}
Gloss: {gloss}

Draft metaphors (vehicle + the dimensions the junior writer thought were shared):
{draft_json}

Your task: full editorial rewrite. Substitute weak vehicles. Sharpen the shared
dimensions. Aim for vivid cross-domain mappings that a literary writer would
actually use — not dead-metaphor cliches and not single-dimension surface
similarities.

Return 10 vehicles, each with 3-6 one-word path concepts (lowercase, no
punctuation). Each path concept is a curated dimension along which topic and
vehicle structurally match.

Return JSON:
{{
  "topic": "{topic}",
  "vehicles": [
    {{"vehicle": "<single english word>", "path_concepts": ["<word>", ...]}}
  ]
}}
"""


def run_sonnet_edits(
    claude_client,
    snapped_topics_json_path: str,
    haiku_apt_jsonl_path: str,
    audit_jsonl_path: str,
) -> dict:
    snapped = json.loads(Path(snapped_topics_json_path).read_text())
    topic_set = {t["word"] for t in snapped["snapped"]}

    calls_made = 0
    with open(audit_jsonl_path, "a") as audit:
        with open(haiku_apt_jsonl_path) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                entry = json.loads(line)
                topic = entry["topic"]
                if topic not in topic_set:
                    continue
                draft = [{"vehicle": m["vehicle"], "dimensions": [s["concept"] for s in m.get("shared_features", [])]}
                         for m in entry.get("metaphors", [])]
                prompt = SONNET_EDIT_PROMPT.format(
                    topic=topic,
                    gloss=entry.get("_gloss", ""),
                    draft_json=json.dumps(draft, indent=2),
                )
                resp = claude_client.prompt_json(prompt)
                calls_made += 1
                audit.write(json.dumps(resp) + "\n")
                audit.flush()
    return {"calls_made": calls_made}


def ingest_sonnet(
    conn: sqlite3.Connection,
    snapped_topics_json_path: str,
    audit_jsonl_path: str,
    *,
    proposer: str = "haiku_sonnet_v1",
) -> dict:
    snapped = json.loads(Path(snapped_topics_json_path).read_text())
    topic_to_sid = {t["word"]: t["topic_synset_id"] for t in snapped["snapped"]}

    bridges_inserted = 0
    bridges_skipped_existing = 0
    bridges_skipped_snap_failure = 0
    snap_failures: list[dict] = []
    topics_processed = 0

    proposed_at = datetime.now(timezone.utc).isoformat()

    with open(audit_jsonl_path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            entry = json.loads(line)
            topic_sid = topic_to_sid.get(entry["topic"])
            if topic_sid is None:
                continue
            topics_processed += 1
            for v in entry.get("vehicles", []):
                vehicle_raw = v["vehicle"]
                vehicle_sid = snap_concept_string(conn, vehicle_raw)
                if vehicle_sid is None:
                    bridges_skipped_snap_failure += 1
                    snap_failures.append({"topic": entry["topic"], "vehicle": vehicle_raw,
                                          "failing_concepts": ["<vehicle>"]})
                    continue
                for concept in v.get("path_concepts", []):
                    try:
                        insert_bridge_with_raw_path(
                            conn,
                            topic_synset_id=topic_sid,
                            vehicle_synset_id=vehicle_sid,
                            proposer=proposer,
                            proposed_at=proposed_at,
                            raw_path=[concept],
                        )
                        bridges_inserted += 1
                    except BridgeSnapFailure:
                        bridges_skipped_snap_failure += 1
                        snap_failures.append({"topic": entry["topic"], "vehicle": vehicle_raw,
                                              "failing_concepts": [concept]})
                    except sqlite3.IntegrityError:
                        bridges_skipped_existing += 1

    return {
        "proposer": proposer,
        "topics_processed": topics_processed,
        "bridges_inserted": bridges_inserted,
        "bridges_skipped_existing": bridges_skipped_existing,
        "bridges_skipped_snap_failure": bridges_skipped_snap_failure,
        "snap_failures": snap_failures,
    }
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd data-pipeline && .venv/bin/python -m pytest scripts/test_metaphor_graph_enrich_sonnet.py -v
```

Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add data-pipeline/scripts/metaphor_graph_enrich_sonnet.py data-pipeline/scripts/test_metaphor_graph_enrich_sonnet.py
git commit -m "feat(metaphor-graph): Sonnet editorial-rewrite + ingest (proposer=haiku_sonnet_v1)"
```

---

### Task 6: Batch driver

**Files:**
- Create: `data-pipeline/scripts/metaphor_graph_enrich_run.py`
- Create: `data-pipeline/scripts/test_metaphor_graph_enrich_run.py`

- [ ] **Step 1: Write the failing test**

```python
# data-pipeline/scripts/test_metaphor_graph_enrich_run.py
"""Tests for the batch driver."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from metaphor_graph import apply_schema
from metaphor_graph_enrich_run import run_batches, chunk_topics


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:", isolation_level=None, autocommit=True)
    c.execute("PRAGMA foreign_keys = ON")
    c.executescript("""
        CREATE TABLE synsets (synset_id TEXT PRIMARY KEY, pos TEXT NOT NULL, gloss TEXT);
        CREATE TABLE lemmas (lemma TEXT NOT NULL, synset_id TEXT NOT NULL REFERENCES synsets(synset_id));
        CREATE TABLE property_vocab_curated (synset_id TEXT NOT NULL UNIQUE REFERENCES synsets(synset_id), lemma TEXT NOT NULL);
    """)
    apply_schema(c)
    yield c
    c.close()


def test_chunk_topics_partitions_evenly():
    snapped = {"snapped": [{"word": f"t{i}"} for i in range(50)]}
    chunks = chunk_topics(snapped, batch_size=20)
    assert len(chunks) == 3
    assert [len(c) for c in chunks] == [20, 20, 10]


def test_run_batches_invokes_each_proposer_per_batch(conn, tmp_path):
    snapped_path = tmp_path / "snapped.json"
    snapped_path.write_text(json.dumps({
        "snapped": [{"word": f"t{i}", "gloss": "g", "source": "s", "topic_synset_id": f"s_t{i}"}
                    for i in range(5)],
        "dropped": [],
    }))
    progress_path = tmp_path / "progress.md"

    mocks = {
        "ingest_haiku_apt": MagicMock(return_value={"proposer": "haiku_v1", "bridges_inserted": 3}),
        "ingest_inapt": MagicMock(return_value={"proposer": "haiku_v1_inapt_synthesised", "bridges_inserted": 2}),
        "ingest_cascade": MagicMock(return_value={"proposer": "cascade_v1", "bridges_inserted": 5}),
        "ingest_sonnet": MagicMock(return_value={"proposer": "haiku_sonnet_v1", "bridges_inserted": 4}),
    }
    report = run_batches(
        conn,
        str(snapped_path),
        batch_size=20,
        progress_md_path=str(progress_path),
        ingest_fns=mocks,
    )

    assert report["batches_run"] == 1
    assert report["totals"]["haiku_v1"] == 3
    assert report["totals"]["cascade_v1"] == 5
    for k, m in mocks.items():
        assert m.call_count == 1, f"{k} should be called once per batch"
    md = progress_path.read_text()
    assert "batch 1" in md.lower()
    assert "haiku_v1" in md and "cascade_v1" in md


def test_run_batches_appends_progress_on_rerun(conn, tmp_path):
    snapped_path = tmp_path / "snapped.json"
    snapped_path.write_text(json.dumps({
        "snapped": [{"word": "t1", "gloss": "g", "source": "s", "topic_synset_id": "s_t1"}],
        "dropped": [],
    }))
    progress_path = tmp_path / "progress.md"
    mocks = {k: MagicMock(return_value={"proposer": k, "bridges_inserted": 0})
             for k in ["ingest_haiku_apt", "ingest_inapt", "ingest_cascade", "ingest_sonnet"]}
    run_batches(conn, str(snapped_path), batch_size=20,
                progress_md_path=str(progress_path), ingest_fns=mocks)
    run_batches(conn, str(snapped_path), batch_size=20,
                progress_md_path=str(progress_path), ingest_fns=mocks)
    md = progress_path.read_text()
    assert md.count("batch 1") == 2
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd data-pipeline && .venv/bin/python -m pytest scripts/test_metaphor_graph_enrich_run.py -v
```

Expected: `ModuleNotFoundError`.

- [ ] **Step 3: Write minimal implementation**

```python
# data-pipeline/scripts/metaphor_graph_enrich_run.py
"""Batch driver: walks the 200-topic cohort in 10 batches of 20, calling each
ingest fn per batch and writing an append-only progress markdown.

Ingest fns are dependency-injected so tests don't spin up subprocesses or
LLM clients. The CLI entrypoint binds the real implementations.
"""
from __future__ import annotations

import argparse
import json
import logging
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

sys.path.insert(0, str(Path(__file__).resolve().parent))

log = logging.getLogger(__name__)


def chunk_topics(snapped: dict, *, batch_size: int) -> list[list[dict]]:
    topics = snapped["snapped"]
    return [topics[i:i + batch_size] for i in range(0, len(topics), batch_size)]


def _write_progress_row(progress_md_path: str, batch_idx: int, batch_reports: dict[str, dict]) -> None:
    ts = datetime.now(timezone.utc).isoformat()
    lines = [f"\n## batch {batch_idx} — {ts}\n"]
    lines.append("| proposer | bridges_inserted | skipped_existing | snap_failures |")
    lines.append("|---|---|---|---|")
    for proposer, rep in batch_reports.items():
        lines.append(
            f"| {proposer} | {rep.get('bridges_inserted', 0)} | "
            f"{rep.get('bridges_skipped_existing', 0)} | "
            f"{rep.get('bridges_skipped_snap_failure', 0)} |"
        )
    with open(progress_md_path, "a") as f:
        f.write("\n".join(lines) + "\n")


def run_batches(
    conn: sqlite3.Connection,
    snapped_topics_json_path: str,
    *,
    batch_size: int,
    progress_md_path: str,
    ingest_fns: dict[str, Callable[..., dict]],
) -> dict:
    snapped = json.loads(Path(snapped_topics_json_path).read_text())
    batches = chunk_topics(snapped, batch_size=batch_size)

    totals: dict[str, int] = {"haiku_v1": 0, "haiku_v1_inapt_synthesised": 0,
                              "cascade_v1": 0, "haiku_sonnet_v1": 0}

    for idx, batch in enumerate(batches, start=1):
        log.info("running batch %d (%d topics)", idx, len(batch))

        batch_snapped_path = f"{snapped_topics_json_path}.batch{idx}"
        Path(batch_snapped_path).write_text(json.dumps({"snapped": batch, "dropped": []}))

        try:
            batch_reports = {
                "haiku_v1": ingest_fns["ingest_haiku_apt"](conn, batch_snapped_path),
                "haiku_v1_inapt_synthesised": ingest_fns["ingest_inapt"](conn, batch_snapped_path),
                "cascade_v1": ingest_fns["ingest_cascade"](conn, batch_snapped_path),
                "haiku_sonnet_v1": ingest_fns["ingest_sonnet"](conn, batch_snapped_path),
            }
        finally:
            Path(batch_snapped_path).unlink(missing_ok=True)

        for proposer, rep in batch_reports.items():
            totals[proposer] = totals.get(proposer, 0) + rep.get("bridges_inserted", 0)

        _write_progress_row(progress_md_path, idx, batch_reports)

    return {"batches_run": len(batches), "totals": totals}
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd data-pipeline && .venv/bin/python -m pytest scripts/test_metaphor_graph_enrich_run.py -v
```

Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add data-pipeline/scripts/metaphor_graph_enrich_run.py data-pipeline/scripts/test_metaphor_graph_enrich_run.py
git commit -m "feat(metaphor-graph): Stage A batch driver — 10 × 20 topic batches"
```

---

### Task 7: CLI entrypoint + integration smoke

**Files:**
- Modify: `data-pipeline/scripts/metaphor_graph_enrich_run.py` (add `main()` + binding logic)
- Modify: `data-pipeline/scripts/test_metaphor_graph_enrich_run.py` (add integration test)

- [ ] **Step 1: Write the failing integration test**

Append to `data-pipeline/scripts/test_metaphor_graph_enrich_run.py`:

```python
def test_integration_no_judgments_means_no_metaphor_link_rows(conn, tmp_path):
    """After Stage A runs end-to-end against mocked proposers, the graph_edges
    view should expose zero metaphor_link rows because no judgments exist.

    This is the load-bearing invariant: Stage A populates the proposal pool;
    Stage B (eyeballer) is what turns proposals into graph structure.
    """
    snapped_path = tmp_path / "snapped.json"
    conn.executescript("""
        INSERT INTO synsets VALUES
          ('s_anger', 'n', 'a'), ('s_fire', 'n', 'f'), ('s_heat', 'n', 'h');
        INSERT INTO lemmas VALUES
          ('anger', 's_anger'), ('fire', 's_fire'), ('heat', 's_heat');
        INSERT INTO property_vocab_curated VALUES
          ('s_anger', 'anger'), ('s_fire', 'fire'), ('s_heat', 'heat');
    """)
    from metaphor_graph import insert_bridge_with_raw_path, apply_graph_view
    apply_graph_view(conn)
    insert_bridge_with_raw_path(
        conn, topic_synset_id="s_anger", vehicle_synset_id="s_fire",
        proposer="cascade_v1", proposed_at="2026-05-29T00:00:00Z",
        raw_path=["heat"],
    )
    n_bridges = conn.execute("SELECT COUNT(*) FROM metaphor_bridges").fetchone()[0]
    n_metaphor_links = conn.execute(
        "SELECT COUNT(*) FROM graph_edges WHERE relation = 'metaphor_link'"
    ).fetchone()[0]
    assert n_bridges == 1
    assert n_metaphor_links == 0
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd data-pipeline && .venv/bin/python -m pytest scripts/test_metaphor_graph_enrich_run.py::test_integration_no_judgments_means_no_metaphor_link_rows -v
```

Expected: passes (this test exercises existing code paths only — it's a load-bearing assertion, not a new feature).

If it fails: investigate why `apply_graph_view` or `insert_bridge_with_raw_path` is not behaving as the schema spec promises — could be a real bug in the schema-base branch.

- [ ] **Step 3: Add CLI main() to metaphor_graph_enrich_run.py**

Append to `metaphor_graph_enrich_run.py`:

```python
def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    p = argparse.ArgumentParser()
    p.add_argument("--db", required=True)
    p.add_argument("--snapped-topics", required=True,
                   help="Path to metaphor_graph_topics_snapped.json")
    p.add_argument("--haiku-apt-jsonl", required=True)
    p.add_argument("--haiku-inapt-jsonl", required=True)
    p.add_argument("--inapt-synth-log", required=True,
                   help="Path to haiku_v1_inapt_synthesised_paths.jsonl (created if missing)")
    p.add_argument("--sonnet-audit", required=True)
    p.add_argument("--go-binary", required=True)
    p.add_argument("--progress-md", required=True)
    p.add_argument("--batch-size", type=int, default=20)
    p.add_argument("--port", type=int, default=9192)
    args = p.parse_args()

    from claude_client import prompt_json
    from metaphor_graph_enrich_haiku import ingest_haiku_apt
    from metaphor_graph_enrich_inapt import synthesise_paths, ingest_inapt
    from metaphor_graph_enrich_cascade import ingest_cascade, make_go_suggest_fn
    from metaphor_graph_enrich_sonnet import run_sonnet_edits, ingest_sonnet

    class _CC:
        def prompt_json(self, prompt: str) -> dict:
            return prompt_json(prompt, model="claude-haiku-4-5-20251001")

    cc_haiku = _CC()

    class _CC_Sonnet:
        def prompt_json(self, prompt: str) -> dict:
            return prompt_json(prompt, model="claude-sonnet-4-6")

    cc_sonnet = _CC_Sonnet()

    synthesise_paths(cc_haiku, args.snapped_topics, args.haiku_inapt_jsonl, args.inapt_synth_log)
    run_sonnet_edits(cc_sonnet, args.snapped_topics, args.haiku_apt_jsonl, args.sonnet_audit)

    suggest_fn = make_go_suggest_fn(args.go_binary, args.db, port=args.port)
    try:
        conn = sqlite3.connect(args.db, isolation_level=None, autocommit=True)
        conn.execute("PRAGMA foreign_keys = ON")

        def _haiku_ingest(c, snapped_path):
            return ingest_haiku_apt(c, snapped_path, args.haiku_apt_jsonl)
        def _inapt_ingest(c, snapped_path):
            return ingest_inapt(c, snapped_path, args.inapt_synth_log)
        def _cascade_ingest(c, snapped_path):
            return ingest_cascade(c, snapped_path, suggest_fn=suggest_fn)
        def _sonnet_ingest(c, snapped_path):
            return ingest_sonnet(c, snapped_path, args.sonnet_audit)

        report = run_batches(
            conn, args.snapped_topics,
            batch_size=args.batch_size,
            progress_md_path=args.progress_md,
            ingest_fns={
                "ingest_haiku_apt": _haiku_ingest,
                "ingest_inapt": _inapt_ingest,
                "ingest_cascade": _cascade_ingest,
                "ingest_sonnet": _sonnet_ingest,
            },
        )
        log.info("Stage A complete: %s", report)
    finally:
        suggest_fn._proc.terminate()  # type: ignore[attr-defined]
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run full test suite**

```bash
cd data-pipeline && .venv/bin/python -m pytest scripts/test_metaphor_graph_enrich_*.py -v
```

Expected: all tests pass (topics: 2, haiku: 4, inapt: 3, cascade: 3, sonnet: 3, run: 4 — total 19).

- [ ] **Step 5: Commit**

```bash
git add data-pipeline/scripts/metaphor_graph_enrich_run.py data-pipeline/scripts/test_metaphor_graph_enrich_run.py
git commit -m "feat(metaphor-graph): Stage A CLI entrypoint + integration smoke (no judgments → no metaphor_link rows)"
```

---

## Self-Review Notes

- Every task uses TDD with explicit RED → GREEN → COMMIT.
- All four proposer functions return the same shape `{proposer, topics_processed, bridges_inserted, bridges_skipped_existing, bridges_skipped_snap_failure, snap_failures}`.
- Idempotency is enforced at the SQLite layer via the schema's `UNIQUE` constraint; every ingest catches `sqlite3.IntegrityError` for the existing-skip count.
- Dependency injection (LLM client, suggest_fn, ingest_fns) keeps tests fast and deterministic.
- Vehicle and path concept strings are both snapped via `metaphor_graph.snap_concept_string`. `BridgeSnapFailure` is the load-bearing exception for path-snap failures; vehicle-snap failures are caught separately because `snap_concept_string` returns `None` on miss.
- The integration smoke test verifies the schema-spec invariant: no judgments → no `metaphor_link` rows in `graph_edges`. This catches regressions in `apply_graph_view` even though Stage A doesn't write judgments.

## What Stage A does NOT do

- No judgments. `metaphor_judgments` stays empty after Stage A. Stage B is where that table fills.
- No re-spending Haiku calls on the apt cohort — we reuse `metaphor_spike_apt_phase2_20260525T004154.jsonl`.
- No multi-hop bridge generation. The schema's `metaphor_bridge_steps` supports multi-step paths but every Stage A bridge is single-step (one shared concept per bridge). Multi-hop generation is a Stage B+ concern.
- No vehicle disambiguation. If Sonnet says "fire" and Haiku says "flame", they're different vehicles. The eyeballer will flag.

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-05-29-metaphor-graph-enrichment-stage-a.md`.

**Recommended execution:** Subagent-driven development via `superpowers:subagent-driven-development` — fresh subagent per task, spec-compliance + code-quality review per task, fast iteration.
