from __future__ import annotations
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import asyncio
import logging
import pytest
from unittest.mock import patch, MagicMock
from grading_sidecar.autocommit import autocommit_once

def test_autocommit_calls_git_add_and_commit(tmp_path):
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout=b"", stderr=b"")
        autocommit_once(repo_root=str(tmp_path), grading_subdir="data-pipeline/grading/")
    cmds = [call.args[0] for call in mock_run.call_args_list]
    assert any("add" in c for c in cmds)
    assert any("commit" in c for c in cmds)

def test_autocommit_tolerates_no_changes(tmp_path):
    with patch("subprocess.run") as mock_run:
        mock_run.side_effect = [
            MagicMock(returncode=0, stdout=b"", stderr=b""),  # add
            MagicMock(returncode=1, stdout=b"nothing to commit", stderr=b""),  # commit returncode=1
        ]
        # Should not raise on returncode=1 ('nothing to commit')
        autocommit_once(repo_root=str(tmp_path), grading_subdir="data-pipeline/grading/")

def test_autocommit_logs_failure(tmp_path, caplog):
    with patch("subprocess.run") as mock_run:
        mock_run.side_effect = Exception("git not found")
        with caplog.at_level(logging.ERROR):
            autocommit_once(repo_root=str(tmp_path), grading_subdir="data-pipeline/grading/")
    assert any("autocommit failed" in r.message.lower() for r in caplog.records)
