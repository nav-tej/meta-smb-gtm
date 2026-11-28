"""Own /digest cards show linked Meta Ad Library pages and saved analysis notes.

Verifies at 375 and 1440 px on a local server with fake accounts (no crawls, no Muse):
- a competitor with a valid ad_library_page_id shows "See their ads on Meta ↗" (page URL);
- one without (or with an invalid ID) shows the "(all advertisers)" keyword search and
  "Link their exact page" -> /#loop-research;
- one with analyzed_at shows its saved note, "From your analysis, <Mon D>", and
  "View analysis" -> /#loop-research; one without analyzed_at never shows "From your analysis";
- ?workspace=sample stays unchanged.
"""

from __future__ import annotations

import importlib
import json
import socket
import subprocess
import threading
import time
from typing import Any

import pytest
import uvicorn
from fastapi import HTTPException

from src.api.main import app
from src.services.accounts import AccountSession
from tests.test_api_calls_per_page_e2e import _find_playwright_python

OWN_DOC: dict[str, Any] = {
    "onboarding": {
        "business_name": "North Star Advisory",
        "business_type": "services",
        "website_url": "https://northstar.test",
        "shop_urls": ["https://northstar.test"],
        "completed_at": "2026-11-10T10:00:00Z",
        "competitors": [
            {
                "name": "Brightpath Consulting",
                "url": "https://brightpath.test",
                "reason": "Same clients",
                "ad_library_page_id": "123456789012",
            },
            {
                "name": "Summit Growth Partners LLC",
                "url": "https://summitgrowth.test",
                "reason": "Similar offer",
            },
            {
                "name": "Invalid Page Co",
                "url": "https://invalidpage.test",
                "reason": "Testing bad page ID",
                "ad_library_page_id": "javascript:alert(1)",
            },
        ],
    },
    "preferences": {
        "goal": "More client inquiries",
        "access": {"minutes_per_week": 30, "channels": ["linkedin", "website"]},
        "competitor_entries": [
            {
                "name": "Brightpath Consulting",
                "url": "https://brightpath.test",
                "role": "similar_audience",
                "rationale": "Pushes 30-day audit retainers with clear pricing.",
                "analyzed_at": "2026-11-24T15:00:00Z",
                "ad_library_page_id": "123456789012",
                "selected": True,
            },
            {
                "name": "Summit Growth Partners LLC",
                "url": "https://summitgrowth.test",
                "role": "similar_audience",
                "reason": "Similar offer",
                "selected": True,
            },
            {
                "name": "Invalid Page Co",
                "url": "https://invalidpage.test",
                "role": "similar_audience",
                "reason": "Testing bad page ID",
                "ad_library_page_id": "javascript:alert(1)",
                "selected": True,
            },
        ],
    },
}


@pytest.fixture
def digest_saved_context_server(monkeypatch: pytest.MonkeyPatch):
    store = {"document": json.loads(json.dumps(OWN_DOC)), "version": 1, "owner_id": "svc"}
    session = AccountSession(
        user_id="svc",
        email="svc@digest.test",
        email_verified=True,
        access_token="tok",
        session_id=None,
    )

    async def fake_resolve(request: Any, _response: Any = None, require_verified: bool = False):
        if request.cookies.get("muse_e2e_user") == "svc":
            return session
        if require_verified:
            raise HTTPException(401, "Sign in required")
        return None

    async def fake_load(_session: AccountSession) -> dict[str, Any]:
        return json.loads(json.dumps(store))

    async def fake_save(_session, doc, expected_version=None, expected_owner=None):
        store["document"] = json.loads(json.dumps(doc))
        store["version"] = int(store["version"]) + 1
        return json.loads(json.dumps(store))

    async def fake_snapshot(sess: AccountSession | None) -> dict[str, Any]:
        if sess is None:
            return {"configured": True, "user": None, "usage": None, "live_available": False}
        return {
            "configured": True,
            "user": {"id": sess.user_id, "email": sess.email, "email_verified": True},
            "usage": {"plan": "starter", "used": 0, "limit": 3, "remaining": 3},
            "runs_remaining": 3,
            "live_available": False,
        }

    async def no_crawl(*_args: Any, **_kwargs: Any) -> tuple[list[Any], list[str]]:
        return [], []

    def no_muse(*_args: Any, **_kwargs: Any) -> Any:
        raise AssertionError("no live Muse calls in this test")

    monkeypatch.setenv("DEMO_MODE", "true")
    monkeypatch.setenv("ACCOUNTS_REQUIRED", "true")
    monkeypatch.setenv("META_MODEL_API_KEY", "")
    monkeypatch.setenv("DEMO_KEY", "")
    fakes = {
        "resolve_account": fake_resolve,
        "load_workspace": fake_load,
        "save_workspace": fake_save,
        "snapshot": fake_snapshot,
    }
    for name in (
        "src.api.accounts",
        "src.api.onboarding",
        "src.api.preferences",
        "src.api.seller_memory",
        "src.api.daily_brief",
        "src.api.outcomes",
        "src.api.intel",
        "src.api.media",
        "src.services.accounts",
    ):
        module = importlib.import_module(name)
        for attr, fake in fakes.items():
            if hasattr(module, attr):
                monkeypatch.setattr(module, attr, fake)
    monkeypatch.setattr("src.api.intel.collect_entries", no_crawl)
    monkeypatch.setattr("src.api.seller_memory.collect_entries", no_crawl)
    monkeypatch.setattr("src.clients.meta.get_meta_client", no_muse)

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    for _ in range(80):
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.1):
                break
        except OSError:
            time.sleep(0.05)
    yield f"http://127.0.0.1:{port}"
    server.should_exit = True
    thread.join(timeout=5)


def test_digest_uses_saved_ad_library_pages_and_analysis_notes_e2e(
    digest_saved_context_server: str,
) -> None:
    python_bin = _find_playwright_python()
    if not python_bin:
        pytest.skip("Playwright runtime not installed")

    script = f"""
from playwright.sync_api import sync_playwright

BASE = {digest_saved_context_server!r}
EXPECTED_PAGE_URL = (
    "https://www.facebook.com/ads/library/?active_status=active&ad_type=all"
    "&country=ALL&view_all_page_id=123456789012&search_type=page&media_type=all"
)
EXPECTED_SEARCH_URL = (
    "https://www.facebook.com/ads/library/?active_status=active&ad_type=all"
    "&country=ALL&q=Summitgrowth&search_type=keyword_unordered&media_type=all"
)

with sync_playwright() as p:
    browser = p.chromium.launch()
    try:
        for width in (375, 1440):
            ctx = browser.new_context(viewport={{"width": width, "height": 900}})
            ctx.add_cookies([{{"name": "muse_e2e_user", "value": "svc", "url": BASE}}])
            page = ctx.new_page()
            errors = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.goto(BASE + "/digest", wait_until="networkidle", timeout=20000)
            page.wait_for_function(
                "() => document.querySelectorAll('#dgCompetitors .dg-card').length === 3",
                timeout=15000,
            )

            cards = page.locator("#dgCompetitors .dg-card")

            # Card 1: linked Ad Library page + saved analysis note & date
            c0 = cards.nth(0)
            c0_text = c0.inner_text()
            assert "Brightpath Consulting" in c0_text, c0_text
            assert "Pushes 30-day audit retainers with clear pricing." in c0_text, c0_text
            assert "From your analysis, Nov 24" in c0_text, c0_text
            assert "(all advertisers)" not in c0_text, c0_text
            assert "Link their exact page" not in c0_text, c0_text

            ad_link = c0.locator("a.dg-meta-ad-link")
            assert ad_link.inner_text() == "See their ads on Meta ↗"
            assert ad_link.get_attribute("href") == EXPECTED_PAGE_URL

            view_link = c0.locator("a.dg-view-analysis")
            assert view_link.inner_text() == "View analysis"
            assert view_link.get_attribute("href") == "/#loop-research"

            # Card 2: no linked page -> labeled keyword search + Link their exact page
            c1 = cards.nth(1)
            c1_text = c1.inner_text()
            assert "Summit Growth Partners LLC" in c1_text, c1_text
            assert "Similar offer" in c1_text, c1_text
            assert "From your analysis" not in c1_text, c1_text
            assert "View analysis" not in c1_text, c1_text

            kw_link = c1.locator("a.dg-meta-ad-link")
            assert kw_link.inner_text() == "Search Meta ads for “Summitgrowth” (all advertisers) ↗"
            assert kw_link.get_attribute("href") == EXPECTED_SEARCH_URL

            exact_link = c1.locator("a.dg-link-exact-page")
            assert exact_link.inner_text() == "Link their exact page"
            assert exact_link.get_attribute("href") == "/#loop-research"

            # Card 3: invalid ad_library_page_id rejected -> falls back to keyword search
            c2 = cards.nth(2)
            c2_text = c2.inner_text()
            assert "From your analysis" not in c2_text, c2_text
            c2_ad = c2.locator("a.dg-meta-ad-link")
            assert "(all advertisers)" in c2_ad.inner_text()
            assert "javascript:" not in (c2_ad.get_attribute("href") or "")
            assert c2.locator("a.dg-link-exact-page").is_visible()

            if width == 375:
                sw, iw = page.evaluate(
                    "[document.documentElement.scrollWidth, window.innerWidth]"
                )
                assert sw <= iw + 1, f"overflow at 375: scrollWidth={{sw}} > innerWidth={{iw}}"
            assert not errors, f"page errors at {{width}}: {{errors}}"
            ctx.close()

        # Sample digest stays unchanged
        sctx = browser.new_context(viewport={{"width": 1440, "height": 900}})
        spage = sctx.new_page()
        serrors = []
        spage.on("pageerror", lambda e: serrors.append(str(e)))
        spage.goto(BASE + "/digest?workspace=sample", wait_until="networkidle", timeout=20000)
        spage.wait_for_function(
            "() => document.body.innerText.includes('SikhiArt.com')",
            timeout=15000,
        )
        stxt = spage.locator("#dgCompetitors").inner_text()
        assert "SikhiArt.com" in stxt and "Gurinderpreet Kaur" in stxt, stxt
        assert "Link their exact page" not in stxt, stxt
        assert "From your analysis" not in stxt, stxt
        assert "See their ads on Meta" not in stxt, stxt
        assert not serrors, serrors
        sctx.close()
    finally:
        browser.close()
print("DIGEST_SAVED_CONTEXT_OK")
"""
    proc = subprocess.run(
        [python_bin, "-c", script],
        capture_output=True,
        text=True,
        timeout=180,
        check=False,
    )
    assert proc.returncode == 0, f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
    assert "DIGEST_SAVED_CONTEXT_OK" in proc.stdout
