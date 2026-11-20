"""A seller can change their setup later, and Muse knows whether they sell products or services.

Nav set up nplusalpha.com, a consulting business, and found three gaps:
- Setup assumed a product shop. Step 1 now asks "What do you offer?" and guesses from the scan.
- Once setup was finished it could not be changed: the server ignored a second submit, and step 4
  reopened with default answers. "Edit shop setup" in the account dialog opens setup with the saved
  answers, and "Save changes" stores them (free).
- "How can I get more leads from Clutch or Toptal traffic" was read as a pricing question.
"""

from __future__ import annotations

import shutil
import socket
import subprocess
import sys
import textwrap
import threading
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
import uvicorn
from fastapi.testclient import TestClient

from src.api.main import app
from src.models.directive import parse_research_directive
from src.services.accounts import AccountSession


def test_leads_questions_get_a_leads_focus() -> None:
    for text in (
        "How can i get more leads from clutch or toptal traffic",
        "Get more clients for my consulting work",
        "More inquiries and bookings this month",
    ):
        directive, explanation = parse_research_directive(text)
        assert directive is not None and directive.focus == "leads", (text, explanation)
        assert "Focus: Leads" in explanation
    # Questions that already had a focus keep it.
    assert parse_research_directive("What should I post on Instagram this week?")[0].focus == (
        "posting"
    )
    assert parse_research_directive("How do my prices compare with competitors?")[0].focus == (
        "pricing"
    )


def _account_fixtures(monkeypatch: pytest.MonkeyPatch, store: dict[str, Any]) -> AccountSession:
    user = AccountSession(
        user_id="22222222-2222-4000-8000-222222222222",
        email="nav@consulting.example",
        email_verified=True,
        access_token="token-2",
        session_id=None,
    )

    async def fake_resolve(*_args: Any, **_kwargs: Any) -> AccountSession:
        return user

    async def fake_load(_account: AccountSession) -> dict[str, Any]:
        return {
            "document": store["document"],
            "version": store["version"],
            "owner_id": user.user_id,
        }

    async def fake_save(
        _account: AccountSession, doc: dict[str, Any], expected_version: Any = None, **_: Any
    ) -> dict[str, Any]:
        assert expected_version == store["version"]
        store["document"] = doc
        store["version"] += 1
        return {"document": doc, "version": store["version"], "owner_id": user.user_id}

    async def fake_snapshot(_account: AccountSession) -> dict[str, Any]:
        return {"usage": {"remaining": 3}}

    monkeypatch.setattr("src.api.onboarding.resolve_account", fake_resolve)
    monkeypatch.setattr("src.api.onboarding.load_workspace", fake_load)
    monkeypatch.setattr("src.api.onboarding.save_workspace", fake_save)
    monkeypatch.setattr("src.api.onboarding.snapshot", fake_snapshot)
    return user


def test_editing_a_finished_setup_saves_and_keeps_the_completion(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store: dict[str, Any] = {
        "document": {
            "onboarding": {
                "business_name": "n Plus Alpha",
                "shop_urls": ["https://nplusalpha.example/"],
                "competitors": [{"name": "Old Co", "url": "https://old.example"}],
                "completed": True,
                "completed_at": "2026-11-17T18:00:00+00:00",
                "used_run": False,
            },
            "preferences": {"memory_entries": [{"id": "m1"}], "research_focus": "old focus"},
        },
        "version": 4,
    }
    user = _account_fixtures(monkeypatch, store)
    client = TestClient(app)
    headers = {"Content-Type": "application/json", "X-Muse-Owner": user.user_id}
    body = {
        "business_name": "n Plus Alpha Ventures",
        "business_type": "services",
        "shop_urls": ["https://nplusalpha.example/"],
        "competitors": [{"name": "Growth Partners", "url": "https://growth.example"}],
        "preferences": {"research_focus": "Leads from marketplaces"},
    }

    # A repeated first build (no edit flag) still changes nothing.
    stale = client.post("/api/v1/onboarding/build", json=body, headers=headers)
    assert stale.status_code == 200 and "updated" not in stale.json()
    assert store["document"]["onboarding"]["business_name"] == "n Plus Alpha"

    edited = client.post("/api/v1/onboarding/build", json={**body, "edit": True}, headers=headers)
    assert edited.status_code == 200, edited.text
    data = edited.json()
    assert data["updated"] is True and data["charged"] is False
    assert data["completed_at"] == "2026-11-17T18:00:00+00:00"
    onboarding = store["document"]["onboarding"]
    assert onboarding["business_name"] == "n Plus Alpha Ventures"
    assert onboarding["business_type"] == "services"
    assert onboarding["completed_at"] == "2026-11-17T18:00:00+00:00"
    assert [c["url"] for c in onboarding["competitors"]] == ["https://growth.example"]
    prefs = store["document"]["preferences"]
    assert prefs["research_focus"] == "Leads from marketplaces"
    assert prefs["memory_entries"] == [{"id": "m1"}], "an edit must keep what Muse remembers"
    assert [c["url"] for c in prefs["competitor_entries"]] == ["https://growth.example"]

    bad = client.post(
        "/api/v1/onboarding/build", json={**body, "business_type": "shop"}, headers=headers
    )
    assert bad.status_code == 422


@pytest.fixture(scope="module")
def live_server_url() -> Iterator[str]:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    for _ in range(50):
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.1):
                break
        except OSError:
            time.sleep(0.05)
    yield f"http://127.0.0.1:{port}"
    server.should_exit = True


def _find_playwright_python() -> str | None:
    for candidate in (sys.executable, "/usr/bin/python3", shutil.which("python3") or ""):
        if not candidate or not Path(candidate).exists():
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


def test_setup_edit_and_offer_e2e(live_server_url: str) -> None:
    python_bin = _find_playwright_python()
    if not python_bin:
        pytest.skip("Playwright runtime not installed")

    runner_script = textwrap.dedent(
        f"""
        import json
        from playwright.sync_api import sync_playwright

        BASE = "{live_server_url}"
        USER = {{"id": "u-edit-1", "email": "nav@consulting.example", "email_verified": True}}
        DONE = {{"business_name": "n Plus Alpha Ventures",
                 "business_type": "services",
                 "shop_urls": ["https://nplusalpha.example/"],
                 "socials": [], "competitors": [], "skipped": [],
                 "crawl_summary": {{"business_name": "n Plus Alpha Ventures", "pages_crawled": 9,
                                   "products_count": 9, "price_range": "",
                                   "sample_titles": ["Services", "Case studies"]}},
                 "preferences": {{"experience": "runs_ads",
                                 "access": {{"channels": ["website"], "can_change_prices": True,
                                            "minutes_per_week": 60, "ads_budget_band": "none"}},
                                 "taste": {{"tone": "warm_story", "subjects_to_avoid": ""}},
                                 "research_focus": "Leads from Clutch and Toptal"}},
                 "completed": True, "completed_at": "2026-11-17T18:00:00Z", "used_run": False}}

        def open_page(browser, width, doc):
            ctx = browser.new_context(viewport={{"width": width, "height": 900}})
            page = ctx.new_page()
            s = {{"doc": json.loads(json.dumps(doc)), "version": 1, "builds": []}}
            errors = []
            page.on("pageerror", lambda e: errors.append(str(e)))

            def reply(route, payload, status=200):
                route.fulfill(status=status, content_type="application/json",
                              body=json.dumps(payload))

            def handle(route):
                req = route.request
                url = req.url.split("?")[0]
                if url.endswith("/api/v1/account/me"):
                    return reply(route, {{"configured": True, "user": USER, "live_available": True,
                                         "usage": {{"plan": "trial", "used": 0, "limit": 3,
                                                   "remaining": 3, "resets_at": None}}}})
                if "/api/v1/account/workspace" in url:
                    if req.method in ("PUT", "POST"):
                        body = json.loads(req.post_data or "{{}}")
                        s["doc"] = body.get("document") or {{}}
                        s["version"] += 1
                    return reply(route, {{"document": s["doc"], "version": s["version"],
                                         "owner_id": USER["id"]}})
                if url.endswith("/api/v1/onboarding/build"):
                    body = json.loads(req.post_data or "{{}}")
                    s["builds"].append(body)
                    return reply(route, {{"success": True, "charged": False, "used_run": False,
                                         "updated": True, "runs_remaining": 3,
                                         "completed_at": "2026-11-17T18:00:00Z"}})
                if url.endswith("/api/v1/ingest-storefront"):
                    return reply(route, {{"business_name": "Quiet Advisory",
                        "total_pages_crawled": 4, "detected_price_hints": [],
                        "discovered_catalog_items": [
                            {{"url": "https://quiet.example/services", "title": "Services",
                              "bucket": "other"}},
                            {{"url": "https://quiet.example/case-studies/acme",
                              "title": "Case study: Acme", "bucket": "other"}},
                            {{"url": "https://quiet.example/about", "title": "About",
                              "bucket": "pages"}}]}})
                if url.endswith("/api/v1/onboarding/status"):
                    return reply(route, {{"authenticated": True, "completed": False}})
                return route.continue_()

            page.route("**/api/v1/**", handle)
            page.route(lambda u: not u.startswith(BASE) and not u.startswith("data:"),
                       lambda r: r.abort())
            return ctx, page, s, errors

        def no_overflow(page, label):
            assert not page.evaluate(
                "document.documentElement.scrollWidth > document.documentElement.clientWidth"
            ), label

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)

            # 1. Editing a finished setup: saved answers load, "Save changes" stores them.
            for width in (375, 1440):
                ctx, page, s, errors = open_page(browser, width, {{"onboarding": DONE}})
                page.goto(BASE + "/welcome?edit=1", wait_until="networkidle")
                page.wait_for_selector("#wkEditBanner", timeout=15000)
                banner = page.locator("#wkEditBanner").inner_text()
                assert "Editing the setup for n Plus Alpha Ventures." in banner, banner
                assert "—" not in banner
                assert page.locator("#wkStep1").is_visible()
                assert page.locator("#wkBusinessName").input_value() == "n Plus Alpha Ventures"
                assert page.locator('input[name="wkOffer"][value="services"]').is_checked()
                no_overflow(page, "edit step 1 " + str(width))
                if width == 1440:
                    page.fill("#wkBusinessName", "n Plus Alpha")
                    page.check('input[name="wkOffer"][value="both"]')
                    page.click("#wkStep1NextBtn")
                    page.wait_for_selector("#wkStep2:not([hidden])", timeout=10000)
                    page.click("#wkStep2NextBtn")
                    page.wait_for_selector("#wkStep3:not([hidden])", timeout=10000)
                    page.click("#wkStep3NextBtn")
                    page.wait_for_selector("#wkStep4:not([hidden])", timeout=10000)
                    assert page.locator("#wkPrefFocus").input_value() == (
                        "Leads from Clutch and Toptal")
                    assert page.locator("#wkPrefMinutes").input_value() == "60"
                    finish = page.locator("#wkStep4FinishBtn")
                    label = finish.inner_text()
                    assert label == "Save changes (free · 0 runs)", label
                    finish.click()
                    page.wait_for_selector("#wkStepDone:not([hidden])", timeout=10000)
                    assert page.locator("#wkDoneTitle").inner_text() == (
                        "Changes saved for n Plus Alpha")
                    build = s["builds"][-1]
                    assert build["edit"] is True, build
                    assert build["business_type"] == "both", build
                    assert build["business_name"] == "n Plus Alpha", build
                    assert build["preferences"]["research_focus"] == (
                        "Leads from Clutch and Toptal"), build
                assert not errors, errors
                ctx.close()

            # 2. A new seller: the scan of a consulting site suggests "Services".
            ctx, page, s, errors = open_page(browser, 1440, {{}})
            page.goto(BASE + "/welcome", wait_until="networkidle")
            page.wait_for_selector("#wkStep1:not([hidden])", timeout=15000)
            assert page.locator("#wkEditBanner").count() == 0
            assert page.locator('input[name="wkOffer"][value="products"]').is_checked()
            page.fill("#wkShopUrl", "quiet.example")
            page.click("#wkScanShopBtn")
            page.wait_for_selector("#wkShopProof:not([hidden])", timeout=10000)
            assert page.locator('input[name="wkOffer"][value="services"]').is_checked()
            hint = page.locator("#wkOfferHint").inner_text()
            assert "Muse guessed “Services” from your website" in hint, hint
            assert not errors, errors
            ctx.close()

            # 3. Settings: the account dialog links to setup for a signed-in seller. (On a phone
            #    the account button sits in the header menu, so the dialog is opened directly.)
            for width in (1440, 375):
                ctx, page, s, errors = open_page(browser, width, {{"onboarding": DONE}})
                page.goto(BASE + "/", wait_until="networkidle")
                if width == 1440:
                    page.locator(".ma-account-button").click()
                else:
                    page.evaluate("window.museAccount.open('account')")
                link = page.locator(".ma-dialog a.ma-setup-link")
                link.wait_for(state="visible", timeout=10000)
                assert link.inner_text() == "Edit shop setup"
                assert link.get_attribute("href") == "/welcome?edit=1"
                no_overflow(page, "account dialog " + str(width))
                assert not errors, errors
                ctx.close()
            browser.close()
        print("SETUP_EDIT_OK")
        """
    )
    proc = subprocess.run(
        [python_bin, "-c", runner_script], capture_output=True, text=True, timeout=240, check=False
    )
    assert proc.returncode == 0, f"STDOUT: {proc.stdout}\nSTDERR: {proc.stderr}"
    assert "SETUP_EDIT_OK" in proc.stdout
