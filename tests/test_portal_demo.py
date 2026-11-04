"""Regression checks for the demo's workspace switch and creative preview handlers."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from src.api.main import app


def test_workspace_preview_uses_selected_product_and_edited_copy(tmp_path: Path) -> None:
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node is needed to execute the portal's JavaScript handlers")
    root = Path(__file__).resolve().parents[1]
    with TestClient(app) as client:
        response = client.get("/api/v1/demo-presets")
    assert response.status_code == 200
    presets = tmp_path / "presets.json"
    presets.write_text(json.dumps(response.json()))
    result = subprocess.run(
        [
            node,
            str(root / "tests/portal_demo_smoke.cjs"),
            str(root / "src/api/static/index.html"),
            str(presets),
        ],
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
