"""Tests for UX polish, error states, loading indicators, durable media, and accessibility."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

from fastapi.testclient import TestClient

from src.api.main import app

ROOT = Path(__file__).resolve().parent.parent
STATIC = ROOT / "src" / "api" / "static"
client = TestClient(app)


def test_portal_hero_and_header_ux_polish_and_unique_ids() -> None:
    resp = client.get("/")
    assert resp.status_code == 200
    html = resp.text

    # Logged-out hero uses loggedOutHeroTitle; workspace card uses heroTitle
    assert html.count('id="heroTitle"') == 1
    assert 'id="loggedOutHeroTitle"' in html
    assert 'aria-labelledby="loggedOutHeroTitle"' in html
    assert 'class="ingest-grid"' in html

    pricing_css = (STATIC / "pricing-modal.css").read_text(encoding="utf-8")
    shell_css = (STATIC / "muse-shell.css").read_text(encoding="utf-8")

    # Brand colors green #1b6e44 and gold #c59341 present in hero/shell styles
    assert "#1b6e44" in pricing_css
    assert "#c59341" in pricing_css
    assert "#c59341" in shell_css
    assert "@keyframes msSectionEnter" in shell_css


def test_loading_indicators_and_aria_busy_across_all_generation_surfaces() -> None:
    shell_css = (STATIC / "muse-shell.css").read_text(encoding="utf-8")
    today_css = (STATIC / "today.css").read_text(encoding="utf-8")
    creator_js = (STATIC / "creator.js").read_text(encoding="utf-8")
    today_js = (STATIC / "today.js").read_text(encoding="utf-8")
    research_js = (STATIC / "research.js").read_text(encoding="utf-8")
    index_html = (STATIC / "index.html").read_text(encoding="utf-8")

    # Universal aria-busy spinner and status spinners
    assert 'button[aria-busy="true"]::before' in shell_css
    assert 'label[aria-busy="true"]::before' in shell_css
    assert "#notice.busy::before" in today_css
    assert "#importStatus.busy::before" in today_css
    assert "#researchStatus.busy::before" in today_css

    # Creator, Today, Research, and Portal set aria-busy on AI actions
    assert "$('importProducts').setAttribute('aria-busy'" in creator_js
    assert "$('draftButton').setAttribute('aria-busy'" in creator_js
    assert "$('generateButton').setAttribute('aria-busy'" in creator_js
    busy_list = (
        "const BUSY_BUTTONS = ['musePlan', 'museImage', 'findItems', 'readListing', 'getPost']"
    )
    assert busy_list in today_js
    assert "$('discoverTargets').setAttribute('aria-busy','true')" in research_js
    assert 'id="screenshotUploadLabel"' in index_html
    assert 'id="csvUploadLabel"' in index_html


def test_accessibility_modal_focus_trap_and_keyboard_navigation() -> None:
    shell_js = (STATIC / "muse-shell.js").read_text(encoding="utf-8")
    creator_js = (STATIC / "creator.js").read_text(encoding="utf-8")
    today_js = (STATIC / "today.js").read_text(encoding="utf-8")
    today_html = (STATIC / "today.html").read_text(encoding="utf-8")
    index_html = (STATIC / "index.html").read_text(encoding="utf-8")

    # Universal dialog focus management in muse-shell.js
    assert "function mountDialogAccessibility()" in shell_js
    assert "HTMLDialogElement.prototype.showModal" in shell_js
    assert "this.__msOpener = document.activeElement" in shell_js

    # Setup dialog has aria-labelledby="setupTitle"
    assert '<dialog id="setup" aria-labelledby="setupTitle">' in today_html
    assert '<h2 id="setupTitle">Your item</h2>' in today_html

    # ArrowLeft / ArrowRight keyboard navigation on step tabs, goals, channels, and artwork pills
    assert "event.key === 'ArrowRight'" in creator_js
    assert "event.key === 'ArrowLeft'" in creator_js
    assert "event.key === 'ArrowRight'" in today_js
    assert "event.key === 'ArrowLeft'" in today_js
    assert "btn.setAttribute('aria-pressed', String(active))" in index_html


def test_error_states_and_durable_media_asset_url_in_node_runtime() -> None:
    """Verify creator.js, today.js, and muse-shell.js handle media_asset_url and friendly errors."""
    contract = subprocess.run(
        ["node", "tests/editor_drafts_contract.cjs"],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        check=True,
    )
    assert "media_asset_url and account isolation passed" in contract.stdout

    creator_src = (STATIC / "creator.js").read_text(encoding="utf-8")
    today_src = (STATIC / "today.js").read_text(encoding="utf-8")
    shell_src = (STATIC / "muse-shell.js").read_text(encoding="utf-8")

    assert r"\/api\/v1\/account\/media\/[0-9a-f]{32}\.(png|jpg|webp)" in creator_src
    assert r"\/api\/v1\/account\/media\/[0-9a-f]{32}\.(png|jpg|webp)" in today_src
    assert "const nextImage = assetUrl || inlineUrl;" in creator_src
    assert "const nextImage = assetUrl || inlineUrl;" in today_src
    assert "You appear to be offline. Your work is saved on this device" in shell_src
    assert "You appear to be offline. Your edits are saved on this device" in creator_src
    assert "Your session expired before Muse started, so no run was used" in creator_src
    assert "Muse is temporarily unavailable right now. No run was used" in creator_src
    assert "You appear to be offline. Your edits are saved on this device" in today_src
    assert "Your session expired before Muse started, so no run was used" in today_src
    assert "Muse is temporarily unavailable right now. No run was used" in today_src


def test_no_raw_error_templates_in_frontend_bundles() -> None:
    raw_pattern = r"Muse could not complete this request \(\$\{response\.status\}\)"
    for name in ("creator.js", "today.js", "research.js", "muse-shell.js"):
        content = (STATIC / name).read_text(encoding="utf-8")
        assert not re.search(raw_pattern, content)
