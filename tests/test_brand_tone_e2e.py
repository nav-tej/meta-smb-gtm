"""Browser E2E tests for brand tone across /welcome?edit=1, /today, and /create.

Local 127.0.0.1 server only, fake accounts, zero live Muse calls, zero runs spent.
Checks 375 and 1440 px with no sideways scroll:
- Setup shows the 4 tone labels (no "Gallery", "collector", or "gift") and help line;
- A saved `collector_gallery` loads as "Polished & premium" and saving writes `polished_premium`;
- /today sends the saved tone in POST /api/v1/content-plan and renders tone-shaped starter hooks;
- /create's draft request carries the Tone line in product.brand_notes (answered with canned JSON);
- Sample /today and /create stay unchanged.
"""

from __future__ import annotations

import importlib
import json
import socket
import subprocess
import threading
import time
from pathlib import Path
from typing import Any

import pytest
import uvicorn
from fastapi import HTTPException

from src.api.main import app
from src.services.accounts import AccountSession
from src.services.brand_tone import BRAND_TONES
from tests.test_api_calls_per_page_e2e import _find_playwright_python

PHOTO = str(Path(__file__).resolve().parent / "fixtures/product_photo.png")


def _doc(name: str, btype: str, tone: str) -> dict[str, Any]:
    slug = name.split()[0].lower()
    prefs = {
        "goal": "More client inquiries",
        "experience": "some",
        "access": {
            "minutes_per_week": 30,
            "channels": ["website", "instagram"],
            "can_change_prices": True,
            "ads_budget_band": "none",
        },
        "taste": {"tone": tone, "subjects_to_avoid": ""},
        "research_focus": "Client inquiries",
        "version": 1,
    }
    return {
        "onboarding": {
            "business_name": name,
            "business_type": btype,
            "website_url": f"https://{slug}.test",
            "shop_urls": [f"https://{slug}.test"],
            "completed": True,
            "completed_at": "2026-11-10T10:00:00Z",
            "preferences": json.loads(json.dumps(prefs)),
            "competitors": [
                {
                    "name": "Brightpath Consulting",
                    "url": "https://brightpath.test",
                    "reason": "Same clients",
                }
            ],
        },
        "preferences": prefs,
    }


@pytest.fixture
def brand_tone_server(monkeypatch: pytest.MonkeyPatch):
    stores = {
        "legacy": {
            "document": _doc("North Star Advisory", "services", "collector_gallery"),
            "version": 1,
            "owner_id": "legacy",
        },
        "expert": {
            "document": _doc("Harbor Strategy", "services", "expert_clear"),
            "version": 1,
            "owner_id": "expert",
        },
    }
    sessions = {
        uid: AccountSession(
            user_id=uid,
            email=f"{uid}@tone.test",
            email_verified=True,
            access_token="tok",
            session_id=None,
        )
        for uid in stores
    }

    async def fake_resolve(request: Any, _response: Any = None, require_verified: bool = False):
        uid = request.cookies.get("muse_e2e_user")
        if uid in sessions:
            return sessions[uid]
        if require_verified:
            raise HTTPException(401, "Sign in required")
        return None

    async def fake_load(session: AccountSession) -> dict[str, Any]:
        return json.loads(json.dumps(stores[session.user_id]))

    async def fake_save(session, doc, expected_version=None, expected_owner=None):
        slot = stores[session.user_id]
        slot["document"] = json.loads(json.dumps(doc))
        slot["version"] = int(slot["version"]) + 1
        return json.loads(json.dumps(slot))

    async def fake_snapshot(session: AccountSession | None) -> dict[str, Any]:
        if session is None:
            return {"configured": True, "user": None, "usage": None, "live_available": False}
        return {
            "configured": True,
            "user": {"id": session.user_id, "email": session.email, "email_verified": True},
            "usage": {"plan": "starter", "used": 0, "limit": 3, "remaining": 3},
            "runs_remaining": 3,
            "live_available": True,
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
    yield f"http://127.0.0.1:{port}", stores
    server.should_exit = True
    thread.join(timeout=5)


def test_brand_tone_setup_today_create_and_sample_e2e(
    brand_tone_server: tuple[str, dict[str, Any]],
) -> None:
    python_bin = _find_playwright_python()
    if not python_bin:
        pytest.skip("Playwright runtime not installed")

    base_url, stores = brand_tone_server
    expected_expert_line = (
        f"Tone: {BRAND_TONES['expert_clear'].label}. {BRAND_TONES['expert_clear'].guide}"
    )

    script = f"""
import json
from playwright.sync_api import sync_playwright

BASE = {base_url!r}
PHOTO = {PHOTO!r}
EXPECTED_EXPERT_LINE = {expected_expert_line!r}
CANNED_AD = {{
    "variants": [{{
        "headline": "Canned expert headline",
        "primary_text": "Canned expert caption.",
        "image_prompt": "Clean workspace desk.",
    }}],
}}

with sync_playwright() as p:
    browser = p.chromium.launch()
    try:
        for width in (375, 1440):
            # 1. Setup (/welcome?edit=1) with legacy collector_gallery
            ctx = browser.new_context(viewport={{"width": width, "height": 900}})
            ctx.add_cookies([{{"name": "muse_e2e_user", "value": "legacy", "url": BASE}}])
            page = ctx.new_page()
            errors = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.goto(BASE + "/welcome?edit=1", wait_until="networkidle", timeout=20000)
            page.wait_for_function(
                "() => document.getElementById('wkBusinessName')?.value === 'North Star Advisory'",
                timeout=15000,
            )
            page.click("#wkStep1NextBtn")
            page.click("#wkStep2NextBtn")
            page.click("#wkStep3NextBtn")
            page.wait_for_selector("#wkStep4:not([hidden])")

            options = page.evaluate(
                "() => Array.from(document.querySelectorAll('#wkPrefTone option'))"
                ".map(o => [o.value, o.textContent.trim()])"
            )
            assert options == [
                ["warm_story", "Warm & story-led"],
                ["expert_clear", "Expert & clear"],
                ["polished_premium", "Polished & premium"],
                ["direct_offer", "Direct & offer-led"],
            ], options
            tone_field_text = page.locator("#wkPrefTone").locator("..").inner_text()
            for banned in ("Gallery", "collector", "gift"):
                assert banned.lower() not in tone_field_text.lower(), (banned, tone_field_text)
            assert "Shapes the wording of your starter posts and drafts." in tone_field_text

            # Legacy collector_gallery must load as polished_premium
            assert page.locator("#wkPrefTone").input_value() == "polished_premium"
            if width == 375:
                sw, iw = page.evaluate(
                    "[document.documentElement.scrollWidth, window.innerWidth]"
                )
                assert sw <= iw + 1, (sw, iw)

            # Save once on 1440 and verify the backend receives polished_premium
            if width == 1440:
                saved_bodies = []
                def _on_build(route):
                    saved_bodies.append(json.loads(route.request.post_data or "{{}}"))
                    route.continue_()
                page.route("**/api/v1/onboarding/build", _on_build)
                with page.expect_response("**/api/v1/onboarding/build"):
                    page.click("#wkStep4FinishBtn")
                assert saved_bodies, "Expected /api/v1/onboarding/build POST"
                assert saved_bodies[0]["preferences"]["taste"]["tone"] == "polished_premium"
            assert not errors, errors
            ctx.close()

            # 2. /today sends saved tone ("expert_clear") and starter hooks match it
            ctx = browser.new_context(viewport={{"width": width, "height": 900}})
            ctx.add_cookies([{{"name": "muse_e2e_user", "value": "expert", "url": BASE}}])
            page = ctx.new_page()
            page.add_init_script(
                "try {{ localStorage.setItem('muse.autoimport.tried.v1:expert', '1'); }}"
                " catch (_) {{}}"
            )
            errors = []
            plan_bodies = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            def _capture_plan(route):
                plan_bodies.append(json.loads(route.request.post_data or "{{}}"))
                route.continue_()
            page.route("**/api/v1/content-plan", _capture_plan)
            page.goto(BASE + "/today", wait_until="networkidle", timeout=20000)
            page.wait_for_function(
                "() => document.documentElement.dataset.museMode === 'account_own'",
                timeout=15000,
            )
            page.click("#openSetup")
            page.fill("#productName", "Strategy Audit")
            with page.expect_response("**/api/v1/content-plan"):
                page.click("#itemForm button.primary")
            assert plan_bodies, "Expected /api/v1/content-plan request"
            assert plan_bodies[-1].get("tone") == "expert_clear", plan_bodies[-1]
            page.wait_for_function(
                "() => (document.getElementById('postHook')?.value || '')"
                ".includes('solves a common problem')",
                timeout=10000,
            )
            if width == 375:
                sw, iw = page.evaluate(
                    "[document.documentElement.scrollWidth, window.innerWidth]"
                )
                assert sw <= iw + 1, (sw, iw)
            assert not errors, errors
            ctx.close()

            # 3. /create draft request carries Tone line in brand_notes (intercepted, 0 runs)
            ctx = browser.new_context(viewport={{"width": width, "height": 900}})
            ctx.add_cookies([{{"name": "muse_e2e_user", "value": "expert", "url": BASE}}])
            page = ctx.new_page()
            page.add_init_script(
                "try {{ localStorage.setItem('muse.autoimport.tried.v1:expert', '1'); }}"
                " catch (_) {{}}"
            )
            errors = []
            draft_bodies = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            def _mock_generate(route):
                draft_bodies.append(json.loads(route.request.post_data or "{{}}"))
                route.fulfill(
                    status=200,
                    content_type="application/json",
                    body=json.dumps(CANNED_AD),
                )
            page.route("**/api/v1/generate-ads**", _mock_generate)
            page.route(
                "**/api/v1/readiness**",
                lambda route: route.fulfill(
                    status=200,
                    content_type="application/json",
                    body=json.dumps(
                        {{
                            "default_mode": "live",
                            "accounts_required": True,
                            "provider_key_configured": True,
                        }}
                    ),
                ),
            )
            page.goto(BASE + "/create", wait_until="networkidle", timeout=20000)
            page.wait_for_function(
                "() => document.documentElement.dataset.museMode === 'account_own'"
                " && document.getElementById('sellerName')?.value === 'Harbor Strategy'",
                timeout=15000,
            )
            page.locator("#productPhoto").set_input_files(PHOTO)
            page.wait_for_function(
                "() => (document.getElementById('productImageCaption')?.textContent || '')"
                ".includes('Uploaded photo')",
                timeout=10000,
            )
            page.click("#nextButton")
            page.click("#nextButton")
            page.click("#writingHelp summary")
            page.wait_for_function("() => document.getElementById('liveMode')?.checked === true")
            page.click("#draftButton")
            page.wait_for_function(
                "() => document.getElementById('headline')?.value === 'Canned expert headline'",
                timeout=10000,
            )
            assert draft_bodies, "Expected /api/v1/generate-ads request"
            brand_notes = draft_bodies[0]["product"]["brand_notes"]
            assert EXPECTED_EXPERT_LINE in brand_notes, brand_notes
            assert len(brand_notes) <= 1000, len(brand_notes)
            if width == 375:
                sw, iw = page.evaluate(
                    "[document.documentElement.scrollWidth, window.innerWidth]"
                )
                assert sw <= iw + 1, (sw, iw)
            assert not errors, errors
            ctx.close()

        # 4. Sample /today and /create stay unchanged
        sctx = browser.new_context(viewport={{"width": 1440, "height": 900}})
        sctx.add_cookies([{{"name": "muse_e2e_user", "value": "expert", "url": BASE}}])
        spage = sctx.new_page()
        sample_plans = []
        def _cap_sample_plan(route):
            sample_plans.append(json.loads(route.request.post_data or "{{}}"))
            route.continue_()
        spage.route("**/api/v1/content-plan", _cap_sample_plan)
        spage.goto(BASE + "/today?workspace=sample", wait_until="networkidle", timeout=20000)
        spage.wait_for_timeout(500)
        assert "Ek Onkar" in spage.evaluate("document.body.innerText")
        for req in sample_plans:
            assert "tone" not in req or req["tone"] is None, req

        sample_drafts = []
        def _mock_sample_gen(route):
            sample_drafts.append(json.loads(route.request.post_data or "{{}}"))
            route.fulfill(status=200, content_type="application/json", body=json.dumps(CANNED_AD))
        spage.route("**/api/v1/generate-ads**", _mock_sample_gen)
        spage.route(
            "**/api/v1/readiness**",
            lambda route: route.fulfill(
                status=200,
                content_type="application/json",
                body=json.dumps(
                    {{
                        "default_mode": "live",
                        "accounts_required": True,
                        "provider_key_configured": True,
                    }}
                ),
            ),
        )
        spage.goto(BASE + "/create?workspace=sample", wait_until="networkidle", timeout=20000)
        spage.wait_for_timeout(500)
        assert "Ek Onkar" in spage.evaluate("document.body.innerText")
        spage.click("#nextButton")
        spage.click("#nextButton")
        spage.click("#writingHelp summary")
        spage.wait_for_function("() => document.getElementById('liveMode')?.checked === true")
        spage.click("#draftButton")
        spage.wait_for_function(
            "() => document.getElementById('headline')?.value === 'Canned expert headline'",
            timeout=10000,
        )
        assert sample_drafts, "Expected sample /api/v1/generate-ads request"
        sample_notes = sample_drafts[0]["product"]["brand_notes"]
        assert "Etsy is closed" in sample_notes, sample_notes
        assert "Tone:" not in sample_notes, sample_notes
        sctx.close()
    finally:
        browser.close()
print("BRAND_TONE_E2E_OK")
"""
    proc = subprocess.run(
        [python_bin, "-c", script],
        capture_output=True,
        text=True,
        timeout=240,
        check=False,
    )
    assert proc.returncode == 0, f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
    assert "BRAND_TONE_E2E_OK" in proc.stdout
    assert stores["legacy"]["document"]["preferences"]["taste"]["tone"] == "polished_premium"
