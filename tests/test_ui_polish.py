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


def _phone_css() -> str:
    css = (ROOT / "src/api/static/muse-shell.css").read_text()
    start = css.index("Phones (≤640px)")
    return css[start:]


def test_phone_header_collapses_only_on_portal_and_digest(client: TestClient) -> None:
    portal = client.get("/portal").text
    assert '<header class="topbar ms-topbar">' in portal
    # The watchlist bar and logged-out hero are styled from pricing-modal.css.
    assert "/static/pricing-modal.css" in portal
    assert '<header class="topbar ms-topbar">' in client.get("/digest").text
    # /create keeps its own header; the phone menu must not restyle it.
    assert "ms-topbar" not in client.get("/create").text
    script = (ROOT / "src/api/static/muse-shell.js").read_text()
    assert "function mountMobileNav()" in script
    assert "mountMobileNav();" in script
    assert "document.querySelector('header.ms-topbar')" in script


def test_phone_css_covers_padding_dropdowns_and_tap_targets() -> None:
    css = _phone_css()
    assert "@media (max-width: 640px)" in css
    assert ".ms-topbar .topbar-right { display: contents; }" in css
    assert ".shell { padding: 16px 16px 32px !important; }" in css
    assert ".monitoring-right { display: flex !important;" in css
    assert ".logged-out-hero-ctas { flex-direction: column;" in css
    assert ".ms-triage button { min-height: 44px;" in css
    # Header dropdowns are pinned near-full-width instead of fixed-width popovers.
    assert ".ms-notif-menu, .ms-credits-menu { position: fixed; left: 12px; right: 12px;" in css
    assert ".ms-account-menu { position: fixed; left: 12px; right: 12px;" in css
    # Generic .topbar rules would leak into /create; phone header rules stay scoped.
    for line in css.splitlines():
        stripped = line.strip()
        if stripped.startswith(".topbar") and "{" in stripped:
            raise AssertionError(f"unscoped header rule: {stripped}")
