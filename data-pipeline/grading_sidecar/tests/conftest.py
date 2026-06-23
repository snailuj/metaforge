from __future__ import annotations
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import pytest
from fastapi.testclient import TestClient

@pytest.fixture
def client(monkeypatch):
    """TestClient with GRADING_DEV=1 to bypass secret check in tests."""
    monkeypatch.setenv("GRADING_DEV", "1")
    from grading_sidecar.app import create_app
    app = create_app()
    return TestClient(app)
