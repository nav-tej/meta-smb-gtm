"""Weekly digest page, portal header link, watchlist cost label and the shell UI contract."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from src.api.main import app

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def test_digest_page_is_served_and_wired_to_free_endpoints(client: TestClient) -> None:
    resp = client.get("/digest")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/html")
    html = resp.text
    assert "Weekly Market Digest" in html
    assert "This week’s top insight" in html
    for node_id in ("dgCompetitors", "dgRecos", "dgStats", 'id="digest"'):
        assert node_id in html
    assert 'href="/portal"' in html
    for asset in ("/static/digest.js", "/static/digest.css", "/static/muse-shell.js"):
        assert asset in html
    script = (ROOT / "src/api/static/digest.js").read_text()
    # Rendering uses textContent only and never asks for a live (billed) result.
    assert "innerHTML" not in script
    assert "live=" not in script


def test_digest_page_data_endpoint_needs_no_model(client: TestClient) -> None:
    resp = client.get("/api/v1/weekly-digest")
    assert resp.status_code == 200
    body = resp.json()
    assert {"week_start", "week_end", "checks", "competitors", "highlights"} <= body.keys()


def test_portal_header_links_digest_and_add_shows_run_cost(client: TestClient) -> None:
    html = client.get("/portal").text
    assert '<a class="topbar-link" href="/digest">Weekly digest</a>' in html
    assert "Add · 🪙 1 run" in html
    assert "no run is used" in html


def test_shell_ui_contract() -> None:
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is required to execute ui_polish_contract.cjs")
    result = subprocess.run(
        [node, str(ROOT / "tests/ui_polish_contract.cjs")],
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )
    assert result.returncode == 0, f"STDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
    assert "UI POLISH CONTRACT PASSED" in result.stdout
