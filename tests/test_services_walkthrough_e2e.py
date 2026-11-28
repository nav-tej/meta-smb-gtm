"""Services-business walkthrough E2E: /today, /create, /first-ad, /digest, /progress.

Walks the app as "n Plus Alpha Ventures" (services, LinkedIn + website, 60 min/wk,
expert_clear, 3 competitors, 1 YouTube video, 2 logged outcomes, free plan) at 375 and
1440 px, verifying zero sideways scroll, zero page errors, zero live Muse calls, and
that products and sample workspaces keep their original wording.
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
from tests.test_api_calls_per_page_e2e import _find_playwright_python

PHOTO = str(Path(__file__).resolve().parent / "fixtures/product_photo.png")
COMP1_URL = "https://brightpath.test"
COMP2_URL = "https://summitgrowth.test"
COMP3_URL = "https://ridgeway.test"


def _services_doc() -> dict[str, Any]:
    prefs: dict[str, Any] = {
        "goal": "More client inquiries",
        "experience": "some",
        "access": {
            "minutes_per_week": 60,
            "channels": ["linkedin", "website"],
            "can_change_prices": True,
            "ads_budget_band": "none",
        },
        "taste": {"tone": "expert_clear", "subjects_to_avoid": ""},
        "research_focus": "Fractional marketing leads",
        "competitor_entries": [
            {
                "name": "Brightpath Advisory",
                "url": COMP1_URL,
                "role": "similar_audience",
                "rationale": "Leads with a free 30-day growth audit.",
                "analysis_takeaway": "Leads with a free 30-day growth audit.",
                "analysis_summary": "Publishes weekly case studies and offers a free audit.",
                "analyzed_at": "2026-11-24T15:00:00Z",
                "ad_library_page_id": "104958162837",
                "selected": True,
            },
            {
                "name": "Summit Growth Partners",
                "url": COMP2_URL,
                "role": "price_reference",
                "rationale": "Publishes monthly retainer tiers starting at $4,500.",
                "selected": True,
            },
            {
                "name": "Ridgeway Consulting",
                "url": COMP3_URL,
                "selected": True,
            },
        ],
        "content_sources": {
            "youtube": {
                "videos": [
                    {
                        "video_id": "dQw4w9WgXcQ",
                        "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
                        "title": "How Fractional CMOs Fix Pipeline Leaks",
                        "author_name": "n Plus Alpha Ventures",
                        "thumbnail_url": "https://i.ytimg.com/vi/dQw4w9WgXcQ/hqdefault.jpg",
                        "added_at": "2026-11-25T10:00:00Z",
                    }
                ]
            }
        },
        "version": 1,
    }
    return {
        "onboarding": {
            "business_name": "n Plus Alpha Ventures",
            "business_type": "services",
            "website_url": "https://nplusalpha.test",
            "shop_urls": ["https://nplusalpha.test"],
            "completed": True,
            "completed_at": "2026-11-10T10:00:00Z",
            "preferences": json.loads(json.dumps(prefs)),
            "competitors": [
                {
                    "name": "Brightpath Advisory",
                    "url": COMP1_URL,
                    "reason": "Leads with a free 30-day growth audit.",
                    "ad_library_page_id": "104958162837",
                },
                {
                    "name": "Summit Growth Partners",
                    "url": COMP2_URL,
                    "reason": "Publishes monthly retainer tiers starting at $4,500.",
                },
                {
                    "name": "Ridgeway Consulting",
                    "url": COMP3_URL,
                    "reason": "",
                },
            ],
        },
        "preferences": prefs,
        "briefs": {
            COMP1_URL: {
                "competitor_url": COMP1_URL,
                "competitor_domain": "brightpath.test",
                "summary": "Publishes weekly case studies and offers a free audit.",
                "takeaway": "Leads with a free 30-day growth audit.",
                "analyzed_at": "2026-11-24T15:00:00Z",
            }
        },
        "outcomes": [
            {
                "id": "out_1",
                "title": "LinkedIn teardown on pipeline leaks",
                "date": "2026-11-20",
                "channel": "linkedin",
                "minutes": 30,
                "reach": 1420,
                "clicks": 38,
                "orders": 2,
                "revenue": 3000.0,
                "created_at": "2026-11-20T16:00:00Z",
            },
            {
                "id": "out_2",
                "title": "Website case study update",
                "date": "2026-11-23",
                "channel": "shop_direct",
                "minutes": 45,
                "reach": 610,
                "clicks": 19,
                "orders": 1,
                "revenue": 1500.0,
                "created_at": "2026-11-23T18:30:00Z",
            },
        ],
    }


def _products_doc() -> dict[str, Any]:
    return {
        "onboarding": {
            "business_name": "Wild Meadow Goods",
            "business_type": "products",
            "website_url": "https://wildmeadow.test",
            "shop_urls": ["https://wildmeadow.test"],
            "completed": True,
            "completed_at": "2026-11-10T10:00:00Z",
            "competitors": [],
        },
        "preferences": {
            "goal": "More sales",
            "access": {"minutes_per_week": 30, "channels": ["instagram"]},
        },
    }


@pytest.fixture
def services_walkthrough_server(monkeypatch: pytest.MonkeyPatch):
    stores = {
        "npa": {"document": _services_doc(), "version": 1, "owner_id": "npa"},
        "prod": {"document": _products_doc(), "version": 1, "owner_id": "prod"},
    }
    sessions = {
        uid: AccountSession(
            user_id=uid,
            email=f"{uid}@walk.test",
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
        # A free account is stored as "trial"; "free" never reaches this code in production.
        plan = "trial" if session.user_id == "npa" else "starter"
        return {
            "configured": True,
            "user": {"id": session.user_id, "email": session.email, "email_verified": True},
            "usage": {"plan": plan, "used": 0, "limit": 3, "remaining": 3},
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
        "src.api.digest_email",
        "src.api.intel",
        "src.api.media",
        "src.services.accounts",
        "src.services.outcomes",
        "src.services.daily_brief",
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


def test_services_walkthrough_fits_any_services_business_e2e(
    services_walkthrough_server: str,
) -> None:
    python_bin = _find_playwright_python()
    if not python_bin:
        pytest.skip("Playwright runtime not installed")

    script = f"""
from playwright.sync_api import sync_playwright

BASE = {services_walkthrough_server!r}
PHOTO = {PHOTO!r}

def check_no_overflow(page, label):
    sw, iw = page.evaluate("[document.documentElement.scrollWidth, window.innerWidth]")
    assert sw <= iw + 1, f"{{label}} overflow: scrollWidth={{sw}} > innerWidth={{iw}}"

with sync_playwright() as p:
    browser = p.chromium.launch()
    try:
        for width in (375, 1440):
            ctx = browser.new_context(viewport={{"width": width, "height": 900}})
            ctx.add_cookies([{{"name": "muse_e2e_user", "value": "npa", "url": BASE}}])
            page = ctx.new_page()
            page.add_init_script(
                "try {{ localStorage.setItem('muse.autoimport.tried.v1:npa', '1'); }}"
                " catch (_) {{}}"
            )
            errors = []
            page.on("pageerror", lambda e: errors.append(str(e)))

            # 1. /today
            page.goto(BASE + "/today", wait_until="networkidle", timeout=20000)
            page.wait_for_function(
                "() => document.body.innerText.includes('n Plus Alpha Ventures')",
                timeout=15000,
            )
            brief_text = page.locator("#msBrief").inner_text()
            assert "Built from n Plus Alpha Ventures' saved setup." in brief_text, brief_text
            assert "Ventures's" not in brief_text, brief_text

            page.evaluate("document.getElementById('resultsDetails').open = true")
            page.evaluate("document.querySelector('.sources').open = true")
            results_text = page.locator("#resultsDetails").inner_text()
            assert "From your channel insights or website." in results_text, results_text
            assert "or shop." not in results_text, results_text
            sources_text = page.locator(".sources").inner_text()
            assert "does not guarantee client inquiries or sales." in sources_text, sources_text

            page.click("#openSetup")
            setup_text = page.locator("#setup").inner_text()
            assert "Weekly client goal (optional)" in setup_text, setup_text
            assert "Weekly sales target" not in setup_text, setup_text
            page.click("#closeSetup")

            # Enter 7-day counts and confirm services wording ("link clicks · clients")
            page.fill("#views", "100")
            page.fill("#clicks", "12")
            page.fill("#sales", "2")
            page.click("#resultsForm button:not(#clearResults)")
            page.wait_for_function(
                "() => (document.getElementById('insightTitle')?.textContent || '')"
                ".includes('12 link clicks')",
                timeout=10000,
            )
            insight_title = page.locator("#insightTitle").inner_text()
            assert "12 link clicks · 2 clients" in insight_title, insight_title
            if width == 375:
                check_no_overflow(page, "/today@375")

            # 2. /create (all 4 steps)
            page.goto(BASE + "/create", wait_until="networkidle", timeout=20000)
            page.wait_for_function(
                "() => document.getElementById('sellerName')?.value === 'n Plus Alpha Ventures'",
                timeout=15000,
            )
            assert page.title() == "Create Your Next Post | Muse Growth Studio", page.title()
            page.evaluate("document.getElementById('moreDetails').open = true")
            assert page.locator("label[for='sellerName']").inner_text() == "Your business name"
            assert page.locator("#shopUrl").get_attribute("placeholder") == (
                "https://your-website.com"
            )
            page.locator("#productPhoto").set_input_files(PHOTO)
            page.wait_for_function(
                "() => (document.getElementById('productImageCaption')?.textContent || '')"
                ".includes('Uploaded photo')",
                timeout=10000,
            )
            if width == 375:
                check_no_overflow(page, "/create-step1@375")

            page.click("#nextButton")
            step2_text = page.locator("[data-panel='1']").inner_text()
            assert "Highlight a client outcome" in step2_text, step2_text
            assert "Offer a thoughtful gift" not in step2_text, step2_text
            if width == 375:
                check_no_overflow(page, "/create-step2@375")

            page.click("#nextButton")
            gen_btn = page.locator("#generateButton").inner_text()
            assert gen_btn == "Preview an AI background", gen_btn
            # Clicking next without review ticks error with services copy
            page.click("#nextButton")
            notice_txt = page.locator("#notice").inner_text()
            assert "offer details" in notice_txt and "product details" not in notice_txt, notice_txt
            page.check("#reviewed")
            if width == 375:
                check_no_overflow(page, "/create-step3@375")

            page.click("#nextButton")
            export_note = page.locator("#exportFilesNote").inner_text()
            assert "production print files" not in export_note, export_note
            assert not page.locator("#tryNext").is_visible()
            if width == 375:
                check_no_overflow(page, "/create-step4@375")

            # 3. /first-ad
            page.goto(BASE + "/first-ad", wait_until="networkidle", timeout=20000)
            page.wait_for_function(
                "() => (document.getElementById('faContextStatus')?.textContent || '')"
                ".includes('n Plus Alpha Ventures')",
                timeout=15000,
            )
            inq_desc = page.locator("#faOutcomeInquiriesDesc").inner_text()
            assert "start client conversations" in inq_desc, inq_desc
            assert "sell via messages" not in inq_desc, inq_desc
            page.click("[data-fa-step='2']")
            prod_ph = page.locator("#faProductName").get_attribute("placeholder") or ""
            assert "advisory retainer" in prod_ph and "featured product" not in prod_ph, prod_ph
            page.click("[data-fa-step='3']")
            aud_ph = page.locator("#faAudience").get_attribute("placeholder") or ""
            assert "Founders" in aud_ph and "local buyers" not in aud_ph, aud_ph
            if width == 375:
                check_no_overflow(page, "/first-ad@375")

            # 4. /digest
            page.goto(BASE + "/digest", wait_until="networkidle", timeout=20000)
            page.wait_for_function(
                "() => document.querySelectorAll('#dgCompetitors .dg-card').length === 3",
                timeout=15000,
            )
            assert page.title() == "Weekly competitor digest | Muse Growth Studio", page.title()
            draft_text = page.locator("#digestDraftForm").inner_text()
            assert "New and removed pages" in draft_text, draft_text
            assert "New and removed listings or pages" not in draft_text, draft_text
            if width == 375:
                check_no_overflow(page, "/digest@375")

            # 5. /progress (free plan -> $0/mo, Net Return +$4500, Saved to your account)
            page.goto(BASE + "/progress", wait_until="networkidle", timeout=20000)
            page.wait_for_function(
                "() => document.getElementById('pgMovesCount')?.textContent === '2'",
                timeout=15000,
            )
            assert page.locator("#pgPlanCost").inner_text() == "$0/mo"
            assert page.locator("#pgPlanCostSub").inner_text() == "Free account"
            assert page.locator("#pgRevenue").inner_text() == "$4500"
            assert page.locator("#pgRevenueSub").inner_text() == "Saved to your account"
            assert page.locator("#pgNetReturn").inner_text() == "+$4500"
            prog_body = page.evaluate("document.body.innerText")
            assert "sales result" not in prog_body, prog_body[:400]
            assert "seller-logged sales" not in prog_body, prog_body[:400]
            if width == 375:
                check_no_overflow(page, "/progress@375")

            assert not errors, f"Page errors at {{width}}: {{errors}}"
            ctx.close()

        # 6. Products account keeps products wording; Sample shop keeps sample wording
        pctx = browser.new_context(viewport={{"width": 1440, "height": 900}})
        pctx.add_cookies([{{"name": "muse_e2e_user", "value": "prod", "url": BASE}}])
        ppage = pctx.new_page()
        ppage.add_init_script(
            "try {{ localStorage.setItem('muse.autoimport.tried.v1:prod', '1'); }} catch (_) {{}}"
        )
        ppage.goto(BASE + "/create", wait_until="networkidle", timeout=20000)
        ppage.wait_for_function(
            "() => document.getElementById('sellerName')?.value === 'Wild Meadow Goods'",
            timeout=15000,
        )
        ppage.locator("#productPhoto").set_input_files(PHOTO)
        ppage.wait_for_function(
            "() => (document.getElementById('productImageCaption')?.textContent || '')"
            ".includes('Uploaded photo')",
            timeout=10000,
        )
        ppage.click("#nextButton")
        assert "Offer a thoughtful gift" in ppage.locator("[data-panel='1']").inner_text()
        ppage.click("#nextButton")
        assert ppage.locator("#generateButton").inner_text() == "Preview a room scene"
        pctx.close()

        sctx = browser.new_context(viewport={{"width": 1440, "height": 900}})
        spage = sctx.new_page()
        spage.goto(BASE + "/create?workspace=sample", wait_until="networkidle", timeout=20000)
        spage.wait_for_timeout(400)
        assert "Ek Onkar" in spage.evaluate("document.body.innerText")
        spage.click("#nextButton")
        assert "Offer a thoughtful gift" in spage.locator("[data-panel='1']").inner_text()
        spage.click("#nextButton")
        assert spage.locator("#generateButton").inner_text() == "Preview a room scene"
        sctx.close()
    finally:
        browser.close()
print("SERVICES_WALKTHROUGH_OK")
"""
    proc = subprocess.run(
        [python_bin, "-c", script],
        capture_output=True,
        text=True,
        timeout=240,
        check=False,
    )
    assert proc.returncode == 0, f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
    assert "SERVICES_WALKTHROUGH_OK" in proc.stdout
