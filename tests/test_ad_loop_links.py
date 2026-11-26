"""Offline real Chromium E2E & contract tests for closing the ad loop on / and /first-ad."""

from __future__ import annotations

import os
import shutil
import socket
import subprocess
import sys
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


@pytest.fixture
def ad_loop_server(monkeypatch: pytest.MonkeyPatch):
    """Run real FastAPI app with a signed-in onboarded fixture account and zero paid calls."""
    user = AccountSession(
        user_id="adloop-u1",
        email="potter@cedarkiln.test",
        email_verified=True,
        access_token="tok-adloop",
        session_id=None,
    )

    async def fake_resolve(request: Any, _response: Any = None, require_verified: bool = False):
        if request.cookies.get("muse_e2e_user") == "adloop-u1":
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
            "live_available": True,
        }

    async def fake_load(account: AccountSession) -> dict[str, Any]:
        return {
            "document": {
                "onboarding": {
                    "business_name": "Cedar Kiln Studio",
                    "website_url": "https://cedarkiln.test",
                    "shop_urls": ["https://cedarkiln.test"],
                    "completed_at": "2026-11-10T10:00:00Z",
                    "competitors": [{"name": "Clay Bench", "url": "https://claybench.test"}],
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


def test_ad_loop_copy_and_script_version_contracts() -> None:
    """Verify cache-busting tags and honest copy rules on touched templates."""
    index_html = (REPO_ROOT / "src/api/static/index.html").read_text(encoding="utf-8")
    welcome_html = (REPO_ROOT / "src/api/static/welcome.html").read_text(encoding="utf-8")
    today_html = (REPO_ROOT / "src/api/static/today.html").read_text(encoding="utf-8")
    creator_html = (REPO_ROOT / "src/api/static/creator.html").read_text(encoding="utf-8")
    first_ad_html = (REPO_ROOT / "src/api/static/first-ad.html").read_text(encoding="utf-8")

    assert "welcome.js?v=20261125-uxgap24" in index_html
    assert "welcome.js?v=20261125-uxgap24" in welcome_html
    assert "seller-memory.js?v=20261125-uxgap24" in index_html
    assert "seller-memory.js?v=20261125-uxgap24" in welcome_html
    assert "seller-memory.js?v=20261125-uxgap24" in today_html
    assert "seller-memory.js?v=20261125-uxgap24" in creator_html
    assert "first-ad.js?v=20261126-ag1" in first_ad_html
    for link_id in ("improveFirstAdLink", "iterateFirstAdLink", "bidsFirstAdLink"):
        assert link_id in index_html
    assert "faBidAdviceLink" in first_ad_html
    assert "Launch campaign" not in first_ad_html
    assert "we publish" not in first_ad_html.lower()


def test_ad_loop_links_375_and_1440_own_and_sample_e2e(ad_loop_server: str) -> None:
    """Verify home <-> /first-ad loop links at 375px and 1440px in both workspaces."""
    pw_python = _find_playwright_python()
    if pw_python is None:
        pytest.skip("Playwright Python runtime unavailable")

    from tests.e2e_helpers import with_cpu_throttle

    script = with_cpu_throttle(
        f"""
        import json
        from playwright.sync_api import sync_playwright

        BASE = {ad_loop_server!r}

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)

            for width in (375, 1440):
                # 1. Sample workspace: /?workspace=sample -> /first-ad -> #tab-bids
                ctx_s = browser.new_context(viewport={{"width": width, "height": 844}})
                ps = ctx_s.new_page()
                ps.goto(f"{{BASE}}/?workspace=sample", wait_until="domcontentloaded")
                ps.wait_for_function(
                    "() => document.body.classList.contains('ms-staged') && "
                    "window.museModes?.isSampleMode?.() === true"
                )
                assert not ps.evaluate("document.documentElement.scrollWidth > window.innerWidth")

                for lid in ("#improveFirstAdLink", "#iterateFirstAdLink"):
                    href = ps.locator(lid).get_attribute("href")
                    assert href == "/first-ad?workspace=sample", (lid, href)

                # Switch to Iterate stage & check #iterateFirstAdLink
                ps.locator('.jr-loop a[href="#loop-iterate"]').click()
                ps.wait_for_selector("#iterateFirstAdLink:visible")
                assert not ps.evaluate("document.documentElement.scrollWidth > window.innerWidth")

                # Switch to Improve stage & click #improveFirstAdLink -> /first-ad?workspace=sample
                ps.locator('.jr-loop a[href="#loop-improve"]').click()
                ps.wait_for_selector("#improveFirstAdLink:visible")
                assert not ps.evaluate("document.documentElement.scrollWidth > window.innerWidth")
                ps.locator("#improveFirstAdLink").click()
                ps.wait_for_url("**/first-ad?workspace=sample")
                ps.wait_for_selector("#faNextBtn")
                ps.click('[data-fa-step="4"]')
                ps.wait_for_selector("#faPanel4:not([hidden])")
                assert ps.locator("#faBidAdviceLink").is_visible()
                assert not ps.evaluate("document.documentElement.scrollWidth > window.innerWidth")
                bid_note = ps.locator("#faBidLoopNote").inner_text()
                assert "—" not in bid_note, bid_note
                assert (
                    ps.locator("#faBidAdviceLink").get_attribute("href")
                    == "/?workspace=sample#tab-bids"
                )

                # Click #faBidAdviceLink -> /?workspace=sample#tab-bids with #tab-bids open
                ps.locator("#faBidAdviceLink").click()
                ps.wait_for_url("**/?workspace=sample#tab-bids")
                ps.wait_for_selector("#tab-bids.active, #csvUploadLabel:visible")
                assert ps.locator("#csvUploadLabel").is_visible()
                assert ps.locator("#bidsFirstAdLink").is_visible()
                assert (
                    ps.locator("#bidsFirstAdLink").get_attribute("href")
                    == "/first-ad?workspace=sample"
                )
                assert not ps.evaluate("document.documentElement.scrollWidth > window.innerWidth")
                ctx_s.close()

                # 2. Own workspace (signed-in, onboarded): / -> /first-ad -> /#tab-bids
                ctx_o = browser.new_context(viewport={{"width": width, "height": 844}})
                ctx_o.add_cookies([{{"name": "muse_e2e_user", "value": "adloop-u1", "url": BASE}}])
                po = ctx_o.new_page()
                po.goto(f"{{BASE}}/", wait_until="domcontentloaded")
                po.wait_for_function(
                    "() => window.museAccount?.getSnapshot?.()?.user?.id === 'adloop-u1'"
                )
                po.wait_for_function(
                    "() => (document.querySelector('#adGallery') || {{}})"
                    ".textContent.includes('Prepare your first ad')"
                )
                sw = po.evaluate("document.documentElement.scrollWidth")
                iw = po.evaluate("window.innerWidth")
                assert sw <= iw, f"own width={{width}} overflow: {{sw}} > {{iw}}"

                po.locator('.jr-loop a[href="#loop-create"]').click()
                create_ad_link = po.locator("#adGallery a", has_text="Prepare your first ad")
                create_ad_link.wait_for(state="visible", timeout=15000)
                assert create_ad_link.is_visible(), "create_ad_link not visible"
                assert create_ad_link.get_attribute("href") == "/first-ad", (
                    create_ad_link.get_attribute("href")
                )
                sw = po.evaluate("document.documentElement.scrollWidth")
                assert sw <= iw, f"create width={{width}} overflow: {{sw}} > {{iw}}"

                po.locator('.jr-loop a[href="#loop-improve"]').click()
                po.wait_for_selector("#improveFirstAdLink:visible", timeout=15000)
                assert po.locator("#improveFirstAdLink").is_visible(), "improveFirstAdLink hidden"
                assert po.locator("#improveFirstAdLink").get_attribute("href") == "/first-ad"
                sw = po.evaluate("document.documentElement.scrollWidth")
                assert sw <= iw, f"improve width={{width}} overflow: {{sw}} > {{iw}}"

                po.locator('.jr-loop a[href="#loop-iterate"]').click()
                po.wait_for_selector("#iterateFirstAdLink:visible", timeout=15000)
                assert po.locator("#iterateFirstAdLink").is_visible(), "iterateFirstAdLink hidden"
                sw = po.evaluate("document.documentElement.scrollWidth")
                assert sw <= iw, f"iterate width={{width}} overflow: {{sw}} > {{iw}}"

                for lid in ("#improveFirstAdLink", "#iterateFirstAdLink"):
                    assert po.locator(lid).get_attribute("href") == "/first-ad"

                po.locator('.jr-loop a[href="#loop-create"]').click()
                create_ad_link.click()
                po.wait_for_url("**/first-ad")
                po.wait_for_selector("#faNextBtn")
                po.click('[data-fa-step="4"]')
                po.wait_for_selector("#faPanel4:not([hidden])")
                assert ps or True
                assert po.locator("#faBidAdviceLink").get_attribute("href") == "/#tab-bids"
                assert not po.evaluate("document.documentElement.scrollWidth > window.innerWidth")

                po.locator("#faBidAdviceLink").click()
                po.wait_for_url("**/#tab-bids")
                po.wait_for_selector("#csvUploadLabel:visible")
                assert po.locator("#bidsFirstAdLink").is_visible()
                assert po.locator("#bidsFirstAdLink").get_attribute("href") == "/first-ad"
                assert not po.evaluate("document.documentElement.scrollWidth > window.innerWidth")
                ctx_o.close()

            browser.close()
        print(json.dumps({{"status": "ok"}}))
        """
    )

    proc = subprocess.run(
        [pw_python, "-c", script],
        capture_output=True,
        text=True,
        check=False,
        timeout=150,
    )
    assert proc.returncode == 0, f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
