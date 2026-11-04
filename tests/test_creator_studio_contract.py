"""The guided creator entry point and all its packaged assets work offline."""

import re
import shutil
import subprocess
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from src.api.main import app


def test_creator_entry_and_assets_are_available_without_provider_calls(monkeypatch):
    async def forbid_network(*args, **kwargs):
        raise AssertionError("The creator entry must not call an external service")

    monkeypatch.setattr(httpx.AsyncClient, "send", forbid_network)
    client = TestClient(app)
    response = client.get("/create")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assets = re.findall(r'(?:src|href)="(/static/creator\.[^"]+)"', response.text)
    assert len(assets) == 2
    for path in assets:
        result = client.get(path)
        assert result.status_code == 200, path
        assert len(result.content) > 100
    assert client.get("/api/v1/demo-presets").status_code == 200


@pytest.mark.parametrize("path", ["/", "/portal"])
def test_existing_workspace_links_to_guided_creator(path):
    response = TestClient(app).get(path)
    assert response.status_code == 200
    assert 'href="/create"' in response.text


def test_creator_edits_reach_exports_and_saved_actions_never_spend():
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node is needed for the offline creator handler checks")
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        [
            node,
            str(root / "tests/creator_studio_contract.cjs"),
            str(root / "src/api/static/creator.js"),
        ],
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
