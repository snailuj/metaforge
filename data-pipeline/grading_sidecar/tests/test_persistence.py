from __future__ import annotations
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import json
import subprocess
import pytest
from grading_sidecar.persistence import append_jsonl, read_jsonl_skip_malformed

def test_append_writes_single_line(tmp_path):
    f = tmp_path / "out.jsonl"
    append_jsonl(f, {"a": 1, "b": "x"})
    assert f.read_text() == '{"a": 1, "b": "x"}\n'

def test_append_is_additive(tmp_path):
    f = tmp_path / "out.jsonl"
    append_jsonl(f, {"a": 1})
    append_jsonl(f, {"a": 2})
    lines = f.read_text().splitlines()
    assert [json.loads(l) for l in lines] == [{"a": 1}, {"a": 2}]

def test_append_nfc_normalises_unicode(tmp_path):
    f = tmp_path / "out.jsonl"
    decomposed = "café"  # 'cafe' + combining acute (NFD)
    composed = "café"     # precomposed 'é' (NFC)
    append_jsonl(f, {"word": decomposed})
    line = f.read_text().splitlines()[0]
    rec = json.loads(line)
    assert rec["word"] == composed

def test_read_skips_malformed_lines(tmp_path):
    f = tmp_path / "in.jsonl"
    f.write_text('{"a": 1}\nNOT JSON\n{"a": 2}\n')
    records, skipped = read_jsonl_skip_malformed(f)
    assert records == [{"a": 1}, {"a": 2}]
    assert skipped == 1

def test_read_missing_file_returns_empty(tmp_path):
    records, skipped = read_jsonl_skip_malformed(tmp_path / "missing.jsonl")
    assert records == []
    assert skipped == 0

def test_concurrent_append_no_corruption(tmp_path):
    """Spawn 4 subprocesses each appending 25 records; verify all 100 present, no truncation."""
    f = tmp_path / "out.jsonl"
    script = tmp_path / "writer.py"
    repo_root = Path(__file__).resolve().parent.parent.parent
    script.write_text(f"""
import sys, json
sys.path.insert(0, {str(repo_root)!r})
from grading_sidecar.persistence import append_jsonl
from pathlib import Path
worker = int(sys.argv[1])
for i in range(25):
    append_jsonl(Path({str(f)!r}), {{"worker": worker, "i": i}})
""")
    procs = [subprocess.Popen([sys.executable, str(script), str(w)]) for w in range(4)]
    for p in procs:
        p.wait()
        assert p.returncode == 0
    records, skipped = read_jsonl_skip_malformed(f)
    assert len(records) == 100
    assert skipped == 0
