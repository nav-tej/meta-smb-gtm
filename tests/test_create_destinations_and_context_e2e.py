"""Offline Chromium E2E tests for /create destinations, Muse brand_notes, and legacy drafts."""

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
def create_destinations_server(monkeypatch: pytest.MonkeyPatch):
    """Run FastAPI app with services + products seller fixtures and zero paid calls."""
    users = {
        "svc-u1": AccountSession(
            user_id="svc-u1",
            email="founder@nplusalpha.test",
            email_verified=True,
            access_token="tok-svc",
            session_id=None,
        ),
        "prod-u1": AccountSession(
            user_id="prod-u1",
            email="maker@cedarloom.test",
            email_verified=True,
            access_token="tok-prod",
            session_id=None,
        ),
    }

    workspaces = {
        "svc-u1": {
            "business_name": "n Plus Alpha Consulting",
            "business_type": "services",
            "website_url": "https://nplusalpha.test",
            "shop_urls": ["https://nplusalpha.test"],
            "completed_at": "2026-11-18T10:00:00Z",
            "competitors": [],
        },
        "prod-u1": {
            "business_name": "Cedar & Loom Goods",
            "business_type": "products",
            "website_url": "https://cedarloom.test",
            "shop_urls": ["https://cedarloom.test"],
            "completed_at": "2026-11-18T10:00:00Z",
            "competitors": [],
        },
    }

    async def fake_resolve(request: Any, _response: Any = None, require_verified: bool = False):
        uid = request.cookies.get("muse_e2e_user")
        if uid in users:
            return users[uid]
        if require_verified:
            raise HTTPException(401, "Sign in required")
        return None

    async def fake_snapshot(account: AccountSession | None) -> dict[str, Any]:
        if account is None:
            return {"configured": True, "user": None, "usage": None, "live_available": False}
        return {
            "configured": True,
            "user": {"id": account.user_id, "email": account.email, "email_verified": True},
            "usage": {"plan": "starter", "used": 0, "limit": 5, "remaining": 5},
            "runs_remaining": 5,
            "live_available": True,
        }

    async def fake_load(account: AccountSession) -> dict[str, Any]:
        return {
            "document": {"onboarding": workspaces[account.user_id]},
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


def test_create_destinations_muse_context_and_legacy_draft_e2e(
    create_destinations_server: str,
) -> None:
    """Verify own destinations, route-mocked Muse payload, sample guard, and legacy draft."""
    pw_python = _find_playwright_python()
    if pw_python is None:
        pytest.skip("Playwright Python runtime unavailable")

    photo = str(REPO_ROOT / "tests/fixtures/product_photo.png")

    from tests.e2e_helpers import with_cpu_throttle

    script = with_cpu_throttle(
        f"""
        import json
        from playwright.sync_api import sync_playwright

        BASE = {create_destinations_server!r}
        PHOTO = {photo!r}

        FORBIDDEN_OWN_DESTS = ("Pixels", "Fine Art America", "Saatchi Art", "Artist website")
        EXPECTED_OWN_DESTS = [
            "My website",
            "Booking or contact page",
            "Etsy shop or listing",
            "Shopify store",
            "Other link",
        ]
        EXPECTED_SAMPLE_DESTS = [
            "Pixels",
            "Fine Art America",
            "Saatchi Art",
            "Artist website",
            "My shop / inquiry page",
        ]

        def mock_live_routes(page, captured):
            def handle_readiness(route):
                route.fulfill(
                    status=200,
                    content_type="application/json",
                    body=json.dumps({{
                        "default_mode": "live",
                        "accounts_required": True,
                        "provider_key_configured": True,
                    }}),
                )

            def handle_generate(route):
                body = json.loads(route.request.post_data or "{{}}")
                captured.append({{"url": route.request.url, "body": body}})
                route.fulfill(
                    status=200,
                    content_type="application/json",
                    body=json.dumps({{
                        "variants": [{{
                            "headline": "Mocked headline",
                            "primary_text": "Mocked caption copy.",
                            "image_prompt": "Clean bright studio daylight.",
                        }}]
                    }}),
                )

            page.route("**/api/v1/readiness**", handle_readiness)
            page.route("**/api/v1/generate-ads**", handle_generate)

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)

            for width in (375, 1440):
                # 1. Services seller own workspace
                cs = browser.new_context(viewport={{"width": width, "height": 844}})
                cs.add_cookies([{{"name": "muse_e2e_user", "value": "svc-u1", "url": BASE}}])
                ps = cs.new_page()
                svc_captured = []
                mock_live_routes(ps, svc_captured)
                ps.goto(f"{{BASE}}/create", wait_until="domcontentloaded")
                ps.wait_for_function(
                    "() => (document.querySelector('#sellerName') || {{}}).value"
                    " === 'n Plus Alpha Consulting'"
                )
                assert not ps.evaluate("document.documentElement.scrollWidth > window.innerWidth")

                opts = ps.locator("#promotionDestination option").all_inner_texts()
                assert opts == EXPECTED_OWN_DESTS, opts
                for bad in FORBIDDEN_OWN_DESTS:
                    assert bad not in opts, (bad, opts)

                # Neutral photo caption and no sample/product-layout wording
                cap_before = ps.locator("#productImageCaption").inner_text()
                assert cap_before == "Your photo will appear here.", cap_before
                assert "Your product photo will appear here." not in ps.locator("main").inner_text()
                assert "—" not in ps.locator("main").inner_text()

                # Switch destination -> services-aware notice, no artwork
                ps.locator("#promotionDestination").select_option("booking")
                notice = ps.locator("#notice").inner_text()
                assert "Booking or contact page" in notice, notice
                assert "service or offer" in notice.lower(), notice
                assert "artwork" not in notice.lower(), notice

                # Upload photo, enter offer, and trigger route-mocked live draft
                ps.locator("#productName").fill("AI growth audit")
                ps.locator("#productPhoto").set_input_files(PHOTO)
                ps.wait_for_function(
                    "() => (document.querySelector('#productImageCaption') || {{}})"
                    ".textContent.includes('Uploaded photo')"
                )
                ps.locator("#nextButton").click()
                ps.locator("#nextButton").click()
                ps.locator("#writingHelp summary").click()
                ps.wait_for_function("() => document.querySelector('#liveMode')?.checked === true")
                ps.locator("#draftButton").click()
                ps.wait_for_function(
                    "() => (document.querySelector('#headline') || {{}}).value"
                    " === 'Mocked headline'"
                )
                assert len(svc_captured) == 1, svc_captured
                assert "live=true" in svc_captured[0]["url"]
                svc_brand = svc_captured[0]["body"]["product"]["brand_notes"]
                svc_brief_ctx = svc_captured[0]["body"]["competitor_brief"]["seller_context"]
                assert "n Plus Alpha Consulting" in svc_brand, svc_brand
                assert "Services" in svc_brand, svc_brand
                assert "Booking or contact page" in svc_brand, svc_brand
                for forbidden in ("Etsy is closed", "artist", "artwork"):
                    assert forbidden.lower() not in svc_brand.lower(), (forbidden, svc_brand)
                    assert forbidden.lower() not in svc_brief_ctx.lower(), (
                        forbidden,
                        svc_brief_ctx,
                    )

                # Verify checklist on step 4 has no artwork or product wording for services
                ps.locator("#reviewed").check()
                ps.locator("#nextButton").click()
                ps.wait_for_selector("#downloadFeed:visible")
                checklist_txt = ps.locator("#postingSteps").inner_text()
                assert "artwork" not in checklist_txt.lower(), checklist_txt
                assert "product" not in checklist_txt.lower(), checklist_txt
                assert not ps.evaluate("document.documentElement.scrollWidth > window.innerWidth")
                cs.close()

                # 2. Products seller own workspace
                cp = browser.new_context(viewport={{"width": width, "height": 844}})
                cp.add_cookies([{{"name": "muse_e2e_user", "value": "prod-u1", "url": BASE}}])
                pp = cp.new_page()
                prod_captured = []
                mock_live_routes(pp, prod_captured)
                pp.goto(f"{{BASE}}/create", wait_until="domcontentloaded")
                pp.wait_for_function(
                    "() => (document.querySelector('#sellerName') || {{}}).value"
                    " === 'Cedar & Loom Goods'"
                )
                assert not pp.evaluate("document.documentElement.scrollWidth > window.innerWidth")
                prod_opts = pp.locator("#promotionDestination option").all_inner_texts()
                assert prod_opts == EXPECTED_OWN_DESTS, prod_opts
                for bad in FORBIDDEN_OWN_DESTS:
                    assert bad not in prod_opts, (bad, prod_opts)

                pp.locator("#promotionDestination").select_option("etsy")
                prod_notice = pp.locator("#notice").inner_text()
                assert "Etsy shop or listing" in prod_notice, prod_notice
                assert "artwork" not in prod_notice.lower(), prod_notice
                assert "product" in prod_notice.lower(), prod_notice

                pp.locator("#productName").fill("Hand-loomed cedar runner")
                pp.locator("#productPhoto").set_input_files(PHOTO)
                pp.wait_for_function(
                    "() => (document.querySelector('#productImageCaption') || {{}})"
                    ".textContent.includes('Uploaded photo')"
                )
                pp.locator("#nextButton").click()
                pp.locator("#nextButton").click()
                pp.locator("#writingHelp summary").click()
                pp.wait_for_function("() => document.querySelector('#liveMode')?.checked === true")
                pp.locator("#draftButton").click()
                pp.wait_for_function(
                    "() => (document.querySelector('#headline') || {{}}).value"
                    " === 'Mocked headline'"
                )
                assert len(prod_captured) == 1, prod_captured
                prod_brand = prod_captured[0]["body"]["product"]["brand_notes"]
                assert "Cedar & Loom Goods" in prod_brand, prod_brand
                assert "Products" in prod_brand, prod_brand
                assert "Etsy shop or listing" in prod_brand, prod_brand
                for forbidden in ("Etsy is closed", "artist", "artwork"):
                    assert forbidden.lower() not in prod_brand.lower(), (forbidden, prod_brand)
                cp.close()

                # 3. Sample shop regression guard
                cm = browser.new_context(viewport={{"width": width, "height": 844}})
                cm.add_cookies([{{"name": "muse_e2e_user", "value": "svc-u1", "url": BASE}}])
                pm = cm.new_page()
                sample_captured = []
                mock_live_routes(pm, sample_captured)
                pm.goto(f"{{BASE}}/create?workspace=sample", wait_until="domcontentloaded")
                pm.wait_for_function(
                    "() => (document.querySelector('#productImageCaption') || {{}})"
                    ".textContent.includes('Ek Onkar')"
                )
                assert not pm.evaluate("document.documentElement.scrollWidth > window.innerWidth")
                sample_opts = pm.locator("#promotionDestination option").all_inner_texts()
                assert sample_opts == EXPECTED_SAMPLE_DESTS, sample_opts

                pm.locator("#nextButton").click()
                pm.locator("#nextButton").click()
                pm.locator("#writingHelp summary").click()
                pm.wait_for_function("() => document.querySelector('#liveMode')?.checked === true")
                pm.locator("#draftButton").click()
                pm.wait_for_function(
                    "() => (document.querySelector('#headline') || {{}}).value"
                    " === 'Mocked headline'"
                )
                assert len(sample_captured) == 1, sample_captured
                sample_brand = sample_captured[0]["body"]["product"]["brand_notes"]
                assert "For this artist, Etsy is closed." in sample_brand, sample_brand
                assert "artwork" in sample_brand.lower(), sample_brand
                cm.close()

            # 4. Old saved draft with destination='pixels' loads cleanly in own workspace
            cl = browser.new_context(viewport={{"width": 1440, "height": 844}})
            cl.add_cookies([{{"name": "muse_e2e_user", "value": "svc-u1", "url": BASE}}])
            legacy_draft = {{
                "schema": 1,
                "workspace": "own",
                "custom": True,
                "copyEdited": True,
                "sceneEdited": False,
                "goal": "visit",
                "placement": "instagram_feed",
                "original": "",
                "image": "",
                "imageKind": "original",
                "sampleImage": "",
                "imageMeta": None,
                "imageFrame": {{"fit": "contain", "x": 0, "y": 0}},
                "product": {{
                    "name": "Legacy consulting audit",
                    "seller": "n Plus Alpha Consulting",
                    "price": "$250",
                    "description": "Saved before destination update.",
                    "link": "https://nplusalpha.test/legacy-offer",
                    "collection": "",
                    "destination": "pixels",
                }},
                "headline": "Legacy consulting audit",
                "caption": "Saved draft caption.",
                "scene": "Clean bright studio.",
                "cta": "",
                "provenance": "Original-photo layout. No new image generated.",
                "artwork": None,
                "idea_id": None,
                "handoffActive": False,
                "handoffContext": None,
                "handoffId": None,
                "offers": {{
                    "pixels": {{
                        "link": "https://nplusalpha.test/legacy-offer",
                        "price": "$250",
                    }}
                }},
                "channels": ["instagram"],
                "step": 0,
            }}
            draft_json = json.dumps(json.dumps(legacy_draft))
            cl.add_init_script(
                "localStorage.setItem("
                "'muse-editor-v1:creator:account:svc-u1', " + draft_json + ");"
            )
            pl = cl.new_page()
            errors = []
            pl.on("pageerror", lambda err: errors.append(str(err)))
            pl.goto(f"{{BASE}}/create", wait_until="domcontentloaded")
            pl.wait_for_function(
                "() => (document.querySelector('#productName') || {{}}).value"
                " === 'Legacy consulting audit'"
            )
            assert not errors, errors
            assert pl.locator("#promotionDestination").input_value() == "other"
            assert pl.locator("#productLink").input_value() == "https://nplusalpha.test/legacy-offer"
            assert pl.locator("#productPrice").input_value() == "$250"
            cl.close()

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
