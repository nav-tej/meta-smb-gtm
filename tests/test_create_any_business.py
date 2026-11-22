"""Offline Chromium E2E & contract tests for any-business copy on /create and /first-ad."""

from __future__ import annotations

import os
import shutil
import socket
import subprocess
import sys
import textwrap
import threading
import time
from pathlib import Path
from typing import Any

import pytest
import uvicorn
from fastapi import HTTPException

from src.api.main import app
from src.services.accounts import AccountSession

REPO_ROOT = Path(__file__).resolve().parents[1]


def _find_playwright_python() -> str | None:
    for candidate in (sys.executable, "/usr/bin/python3", shutil.which("python3") or ""):
        if not candidate or not os.path.exists(candidate):
            continue
        probe = subprocess.run(
            [candidate, "-c", "import playwright.sync_api"],
            capture_output=True,
            text=True,
            check=False,
        )
        if probe.returncode == 0:
            return candidate
    return None


def test_script_versions_and_zero_em_dashes_in_first_ad() -> None:
    """Verify ?v= cache-busting bumps and zero em-dashes in first-ad customer strings."""
    creator_html = (REPO_ROOT / "src/api/static/creator.html").read_text(encoding="utf-8")
    first_ad_html = (REPO_ROOT / "src/api/static/first-ad.html").read_text(encoding="utf-8")
    first_ad_js = (REPO_ROOT / "src/api/static/first-ad.js").read_text(encoding="utf-8")

    assert "creator.js?v=20261121-uxgap18" in creator_html
    assert "first-ad.js?v=20261120-vu1" in first_ad_html
    assert "—" not in first_ad_html
    assert "—" not in first_ad_js


@pytest.fixture
def any_business_server(monkeypatch: pytest.MonkeyPatch):
    """Run FastAPI app with a signed-in services business fixture and zero paid calls."""
    user = AccountSession(
        user_id="svc-u1",
        email="founder@nplusalpha.test",
        email_verified=True,
        access_token="tok-svc",
        session_id=None,
    )

    async def fake_resolve(request: Any, _response: Any = None, require_verified: bool = False):
        if request.cookies.get("muse_e2e_user") == "svc-u1":
            return user
        if require_verified:
            raise HTTPException(401, "Sign in required")
        return None

    async def fake_snapshot(account: AccountSession | None) -> dict[str, Any]:
        if account is None:
            return {"configured": True, "user": None, "usage": None, "live_available": False}
        return {
            "configured": True,
            "user": {"id": account.user_id, "email": account.email, "email_verified": True},
            "usage": {"plan": "starter", "used": 0, "limit": 3, "remaining": 3},
            "runs_remaining": 3,
            "live_available": False,
        }

    async def fake_load(account: AccountSession) -> dict[str, Any]:
        return {
            "document": {
                "onboarding": {
                    "business_name": "n Plus Alpha Consulting",
                    "business_type": "services",
                    "website_url": "https://nplusalpha.test",
                    "shop_urls": ["https://nplusalpha.test"],
                    "completed_at": "2026-11-18T10:00:00Z",
                    "competitors": [],
                }
            },
            "version": 1,
            "owner_id": account.user_id,
        }

    monkeypatch.setenv("DEMO_MODE", "true")
    monkeypatch.setenv("ACCOUNTS_REQUIRED", "true")
    monkeypatch.setenv("META_MODEL_API_KEY", "")
    monkeypatch.setenv("DEMO_KEY", "")
    monkeypatch.setattr("src.api.accounts.resolve_account", fake_resolve)
    monkeypatch.setattr("src.services.accounts.resolve_account", fake_resolve)
    monkeypatch.setattr("src.api.accounts.snapshot", fake_snapshot)
    monkeypatch.setattr("src.api.accounts.load_workspace", fake_load)

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()

    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    for _ in range(50):
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                break
        except OSError:
            time.sleep(0.05)

    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        server.should_exit = True
        thread.join(timeout=2)


def test_create_and_first_ad_own_vs_sample_copy_and_upload_caption_e2e(
    any_business_server: str,
) -> None:
    """Verify upload caption, services own-workspace copy, and sample copy at 375px and 1440px."""
    pw_python = _find_playwright_python()
    if pw_python is None:
        pytest.skip("Playwright Python runtime unavailable")

    photo = str(REPO_ROOT / "tests/fixtures/product_photo.png")

    script = textwrap.dedent(
        f"""
        import json
        from playwright.sync_api import sync_playwright

        BASE = {any_business_server!r}
        PHOTO = {photo!r}

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)

            for width in (375, 1440):
                # 1. /create own workspace (services business + upload caption)
                co = browser.new_context(viewport={{"width": width, "height": 844}})
                co.add_cookies([{{"name": "muse_e2e_user", "value": "svc-u1", "url": BASE}}])
                po = co.new_page()
                po.goto(f"{{BASE}}/create", wait_until="domcontentloaded")
                po.wait_for_function(
                    "() => window.museAccount?.getSnapshot?.()?.user?.id === 'svc-u1'"
                )
                assert (
                    po.locator("#creatorStep1Eyebrow").inner_text()
                    == "START WITH WHAT YOU OFFER"
                )
                assert po.locator("#productNameLabel").inner_text() == "What are you promoting?"
                assert (
                    po.locator("#productName").get_attribute("placeholder")
                    == "A product, service or offer"
                )
                assert po.locator("#creatorPhotoEyebrow").inner_text() == "YOUR PHOTO"
                assert not po.evaluate("document.documentElement.scrollWidth > window.innerWidth")

                # Upload photo -> caption must update and contain zero sample artist wording
                po.locator("#productName").fill("AI growth audit")
                po.locator("#productPhoto").set_input_files(PHOTO)
                po.wait_for_function(
                    "() => (document.querySelector('#productImageCaption') || {{}})"
                    ".textContent.includes('Uploaded photo')"
                )
                cap = po.locator("#productImageCaption").inner_text()
                fact = po.locator("#productFactNote").text_content() or ""
                for forbidden in ("Ek Onkar", "Sarabjit", "SikhiArt", "artwork preview"):
                    assert forbidden not in cap, (forbidden, cap)
                    assert forbidden not in fact, (forbidden, fact)

                # Walk steps 2 -> 3 -> 4 with services item (no price)
                po.locator("#nextButton").click()
                po.locator("#nextButton").click()
                po.locator("#reviewed").check()
                po.locator("#nextButton").click()
                po.wait_for_selector("#downloadFeed:visible")
                assert not po.evaluate("document.documentElement.scrollWidth > window.innerWidth")

                # 2. /first-ad own workspace (services business)
                po.goto(f"{{BASE}}/first-ad", wait_until="domcontentloaded")
                po.wait_for_function(
                    "() => (document.querySelector('#faOutcomeVisitsTitle') || {{}})"
                    ".textContent === 'Bring visitors to your website'"
                )
                assert po.locator("#faOutcomeSalesTitle").inner_text() == "Test a direct offer"
                assert not po.evaluate("document.documentElement.scrollWidth > window.innerWidth")
                po.click('[data-fa-step="2"]')
                po.wait_for_selector("#faPanel2:not([hidden])")
                assert po.locator("#faProductNameLabel").inner_text() == "What are you promoting?"
                assert (
                    po.locator("#faImportBtn").inner_text() == "Load images from your website"
                )
                assert po.locator("#faDestWebsiteOpt").text_content() == "Your website"
                po.fill("#faProductName", "AI growth audit")
                po.fill("#faHeadline", "Book an AI growth audit")
                po.fill("#faCaption", "Practical roadmap for your marketing workflow.")
                po.click('[data-fa-step="4"]')
                po.wait_for_selector("#faPanel4:not([hidden])")
                prereq_txt = po.locator("#faPrereqList").inner_text()
                assert "product photo" not in prereq_txt.lower(), prereq_txt
                assert "—" not in po.locator("main").inner_text()
                assert not po.evaluate("document.documentElement.scrollWidth > window.innerWidth")
                co.close()

                # 3. /create sample workspace preserves artist wording
                cs = browser.new_context(viewport={{"width": width, "height": 844}})
                ps = cs.new_page()
                ps.goto(f"{{BASE}}/create?workspace=sample", wait_until="domcontentloaded")
                ps.wait_for_function(
                    "() => (document.querySelector('#productImageCaption') || {{}})"
                    ".textContent.includes('Ek Onkar')"
                )
                assert ps.locator("#creatorStep1Eyebrow").inner_text() == "START WITH WHAT YOU MAKE"
                assert ps.locator("#productNameLabel").inner_text() == "Product name"
                assert ps.locator("#creatorPhotoEyebrow").inner_text() == "THE WORK COMES FIRST"
                assert not ps.evaluate("document.documentElement.scrollWidth > window.innerWidth")

                # 4. /first-ad sample workspace preserves artist wording (without em-dashes)
                ps.goto(f"{{BASE}}/first-ad?workspace=sample", wait_until="domcontentloaded")
                ps.wait_for_function(
                    "() => (document.querySelector('#faOutcomeVisitsTitle') || {{}})"
                    ".textContent === 'Bring visitors to your shop'"
                )
                assert (
                    ps.locator("#faOutcomeSalesTitle").inner_text()
                    == "Test a direct product offer"
                )
                ps.click('[data-fa-step="2"]')
                ps.wait_for_selector("#faPanel2:not([hidden])")
                assert ps.locator("#faProductNameLabel").inner_text() == "Product or artwork name"
                assert ps.locator("#faImportBtn").inner_text() == "Load shop images"
                assert (
                    ps.locator("#faDestWebsiteOpt").text_content()
                    == "Studio website / product page"
                )
                assert "—" not in ps.locator("main").inner_text()
                assert not ps.evaluate("document.documentElement.scrollWidth > window.innerWidth")
                cs.close()

            browser.close()
        print(json.dumps({{"status": "ok"}}))
        """
    )

    proc = subprocess.run(
        [pw_python, "-c", script],
        capture_output=True,
        text=True,
        check=False,
        timeout=90,
    )
    assert proc.returncode == 0, f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
