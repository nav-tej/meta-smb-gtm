"""Offline contracts for the compact daily posting workspace."""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from src.api.main import app


def test_today_entry_assets_and_starter_plan_never_call_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def forbidden_network(*args: object, **kwargs: object) -> None:
        raise AssertionError("Daily starter requests cannot touch external services")

    monkeypatch.setattr(httpx.AsyncClient, "send", forbidden_network)
    client = TestClient(app)
    response = client.get("/today")
    assert response.status_code == 200
    assert "One good post today." in response.text
    assets = re.findall(r'(?:src|href)="(/static/today\.[^"]+)"', response.text)
    assert len(assets) == 2
    for asset in assets:
        assert client.get(asset).status_code == 200
    result = client.post(
        "/api/v1/content-plan",
        json={"product": {"title": "My bowl"}, "channels": ["instagram"], "use_muse": False},
    )
    assert result.status_code == 200
    assert result.json()["mode"] == "starter"
    assert len(result.json()["posts"]) == 3


def test_daily_ui_behavior_without_network_or_browser() -> None:
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is needed for the offline daily UI harness")
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        [node, str(root / "tests/today_studio_contract.cjs")],
        cwd=root,
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "DAILY STUDIO CONTRACT PASSED" in result.stdout
