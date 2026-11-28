"""Non-artist products seller walkthrough E2E: /today, /create, /first-ad, /digest, /progress, /account.

Walks the app as "Ember & Wick Candle Co." (products, Etsy + Shopify, More sales,
Instagram + Facebook, 30 min/wk, polished_premium, trial plan, 2 candle competitors
with 1 saved analysis, 1 saved /create draft, 1 logged outcome with revenue) at 375 and
1440 px, verifying zero sideways scroll, zero page errors, zero live Muse calls, that
every products wording fix holds, and that the sample artist keeps every original word.
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

REPO_ROOT = Path(__file__).resolve().parents[1]
PHOTO = str(Path(__file__).resolve().parent / "fixtures/product_photo.png")
COMP1_URL = "https://hearthandwax.test"
COMP2_URL = "https://cedarandflame.test"


def test_products_walkthrough_script_versions() -> None:
    """Changed static scripts are bumped to 20261128-ag2 on every page that loads them."""
    creator_html = (REPO_ROOT / "src/api/static/creator.html").read_text(encoding="utf-8")
    today_html = (REPO_ROOT / "src/api/static/today.html").read_text(encoding="utf-8")
    first_ad_html = (REPO_ROOT / "src/api/static/first-ad.html").read_text(encoding="utf-8")
    assert "creator.js?v=20261128-ag2" in creator_html
    assert "today.js?v=20261128-ag2" in today_html
    assert "first-ad.js?v=20261128-ag2" in first_ad_html


def _candle_shop_doc() -> dict[str, Any]:
    prefs: dict[str, Any] = {
        "goal": "More sales",
        "experience": "some",
        "access": {
            "minutes_per_week": 30,
            "channels": ["instagram", "facebook"],
            "can_change_prices": True,
            "ads_budget_band": "none",
        },
        "taste": {"tone": "polished_premium", "subjects_to_avoid": ""},
        "research_focus": "Small-batch soy candles and gift sets",
        "competitor_entries": [
            {
                "name": "Hearth & Wax",
                "url": COMP1_URL,
                "role": "similar_audience",
                "rationale": "Bundles three 8oz seasonal scents for $68 with gift wrap.",
                "analysis_takeaway": "Bundles three 8oz seasonal scents for $68 with gift wrap.",
                "analysis_summary": "Runs seasonal scent drops and 3-candle gift bundles.",
                "analyzed_at": "2026-11-24T15:00:00Z",
                "ad_library_page_id": "209876543210",
                "selected": True,
            },
            {
                "name": "Cedar & Flame",
                "url": COMP2_URL,
                "role": "price_reference",
                "rationale": "Sells single amber-jar soy candles at $28 on Shopify.",
                "selected": True,
            },
        ],
        "version": 1,
    }
    saved_creator_draft: dict[str, Any] = {
        "schema": 1,
        "workspace": "own",
        "custom": True,
        "copyEdited": True,
        "sceneEdited": False,
        "goal": "story",
        "placement": "instagram_feed",
        "original": "",
        "image": "",
        "imageKind": "original",
        "sampleImage": "",
        "imageMeta": None,
        "imageFrame": {"fit": "contain", "x": 0, "y": 0},
        "product": {
            "name": "Smoked Cedar 8oz Soy Candle",
            "price": "$28",
            "seller": "Ember & Wick Candle Co.",
            "description": "Hand-poured soy wax with cedarwood, amber, and a clean cotton wick.",
            "link": "https://emberandwick.test/products/smoked-cedar",
            "collection": "Autumn Apothecary",
            "destination": "shopify",
        },
        "headline": "Smoked Cedar, poured in small batches",
        "caption": "Warm cedarwood and soft amber for quiet evenings. Hand-poured in 8oz reusable glass.",
        "scene": "Clean, softly lit surface with natural daylight and simple modern styling. Describe only the surroundings; do not change the product.",
        "cta": "Shop now",
        "provenance": "Original-photo layout. No personalized image generated.",
        "artwork": None,
        "idea_id": None,
        "handoffActive": False,
        "handoffContext": None,
        "handoffId": None,
        "offers": {
            "shopify": {
                "price": "$28",
                "link": "https://emberandwick.test/products/smoked-cedar",
            }
        },
        "channels": ["instagram", "facebook"],
        "step": 0,
    }
    return {
        "onboarding": {
            "business_name": "Ember & Wick Candle Co.",
            "business_type": "products",
            "website_url": "https://emberandwick.test",
            "shop_urls": [
                "https://emberandwick.test",
                "https://emberandwick.etsy.com",
            ],
            "completed": True,
            "completed_at": "2026-11-10T10:00:00Z",
            "preferences": json.loads(json.dumps(prefs)),
            "competitors": [
                {
                    "name": "Hearth & Wax",
                    "url": COMP1_URL,
                    "reason": "Bundles three 8oz seasonal scents for $68 with gift wrap.",
                    "ad_library_page_id": "209876543210",
                },
                {
                    "name": "Cedar & Flame",
                    "url": COMP2_URL,
                    "reason": "Sells single amber-jar soy candles at $28 on Shopify.",
                },
            ],
        },
        "preferences": prefs,
        "briefs": {
            COMP1_URL: {
                "competitor_url": COMP1_URL,
                "competitor_domain": "hearthandwax.test",
                "summary": "Runs seasonal scent drops and 3-candle gift bundles.",
                "takeaway": "Bundles three 8oz seasonal scents for $68 with gift wrap.",
                "analyzed_at": "2026-11-24T15:00:00Z",
            }
        },
        "documents": {
            "creator": saved_creator_draft,
        },
        "outcomes": [
            {
                "id": "out_candle_1",
                "title": "Instagram reel pouring Smoked Cedar batch",
                "date": "2026-11-22",
                "channel": "instagram_feed",
                "minutes": 25,
                "reach": 940,
                "clicks": 42,
                "orders": 6,
                "revenue": 240.0,
                "created_at": "2026-11-22T18:00:00Z",
            }
        ],
    }


@pytest.fixture
def products_walkthrough_server(monkeypatch: pytest.MonkeyPatch):
    stores = {
        "ewc": {"document": _candle_shop_doc(), "version": 1, "owner_id": "ewc"},
    }
    sessions = {
        "ewc": AccountSession(
            user_id="ewc",
            email="hello@emberandwick.test",
            email_verified=True,
            access_token="tok-ewc",
            session_id=None,
        )
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
            "usage": {"plan": "trial", "used": 0, "limit": 3, "remaining": 3},
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


def test_products_walkthrough_fits_non_artist_shop_e2e(
    products_walkthrough_server: str,
) -> None:
    python_bin = _find_playwright_python()
    if not python_bin:
        pytest.skip("Playwright runtime not installed")

    script = f"""
from playwright.sync_api import sync_playwright

BASE = {products_walkthrough_server!r}
PHOTO = {PHOTO!r}

def check_no_overflow(page, label):
    sw, iw = page.evaluate("[document.documentElement.scrollWidth, window.innerWidth]")
    assert sw <= iw + 1, f"{{label}} overflow: scrollWidth={{sw}} > innerWidth={{iw}}"

with sync_playwright() as p:
    browser = p.chromium.launch()
    try:
        for width in (375, 1440):
            ctx = browser.new_context(viewport={{"width": width, "height": 900}})
            ctx.add_cookies([{{"name": "muse_e2e_user", "value": "ewc", "url": BASE}}])
            page = ctx.new_page()
            page.add_init_script(
                "try {{ localStorage.setItem('muse.autoimport.tried.v1:ewc', '1'); }}"
                " catch (_) {{}}"
            )
            errors = []
            page.on("pageerror", lambda e: errors.append(str(e)))

            # 1. /today — own products seller: no Series / Abstracts / art words in setup modal
            page.goto(BASE + "/today", wait_until="networkidle", timeout=20000)
            page.wait_for_function(
                "() => document.body.innerText.includes('Ember & Wick Candle Co.')",
                timeout=15000,
            )
            page.click("#openSetup")
            col_label = page.locator("#collectionLabel").inner_text()
            assert col_label == "Collection (optional)", col_label
            series_opts = page.evaluate(
                "Array.from(document.querySelectorAll('#series option')).map(o => o.value)"
            )
            assert series_opts == [], f"Unexpected art datalist options: {{series_opts}}"
            page.click("#closeSetup")
            if width == 375:
                check_no_overflow(page, "/today@375")

            # 2. /create — all 4 steps + saved account draft load, zero art/print/marketplace leaks
            page.goto(BASE + "/create", wait_until="networkidle", timeout=20000)
            page.wait_for_function(
                "() => document.getElementById('sellerName')?.value === 'Ember & Wick Candle Co.'",
                timeout=15000,
            )
            import_hint = page.locator("#importHint").inner_text()
            for forbidden in ("Pixels", "Fine Art America", "Saatchi"):
                assert forbidden not in import_hint, import_hint
            save_btn_txt = page.locator("#saveWebsiteOnlyBtn").text_content() or ""
            assert "my shop" in save_btn_txt and "studio" not in save_btn_txt.lower(), save_btn_txt

            more_summary = page.locator("#moreDetails > summary").inner_text()
            assert "collection" in more_summary.lower() and "series" not in more_summary.lower(), more_summary
            page.evaluate("document.getElementById('moreDetails').open = true")
            prod_col_label = page.locator("label[for='productCollection']").inner_text()
            assert "Collection" in prod_col_label and "Series" not in prod_col_label, prod_col_label
            prod_col_ph = page.locator("#productCollection").get_attribute("placeholder") or ""
            assert "collection" in prod_col_ph.lower() and "series" not in prod_col_ph.lower(), prod_col_ph

            page.locator("#productPhoto").set_input_files(PHOTO)
            page.wait_for_function(
                "() => (document.getElementById('productImageCaption')?.textContent || '')"
                ".includes('Uploaded photo')",
                timeout=10000,
            )
            if width == 375:
                check_no_overflow(page, "/create-step1@375")

            # Step 2
            page.click("#nextButton")
            if width == 375:
                check_no_overflow(page, "/create-step2@375")

            # Step 3: neutral scene prompt (no restrained frame) & product scene button (no room scene)
            page.click("#nextButton")
            gen_btn = page.locator("#generateButton").inner_text()
            assert gen_btn == "Preview a product scene", gen_btn
            page.evaluate("document.getElementById('writingHelp').open = true")
            scene_val = page.locator("#scene").input_value()
            assert "softly lit surface" in scene_val, scene_val
            assert "restrained frame" not in scene_val and "clean wall" not in scene_val, scene_val
            page.check("#reviewed")
            if width == 375:
                check_no_overflow(page, "/create-step3@375")

            # Step 4: no production print files, no series label in posting checklist
            page.click("#nextButton")
            export_note = page.locator("#exportFilesNote").inner_text()
            assert "production print files" not in export_note, export_note
            posting_steps = page.locator("#postingSteps").inner_text()
            assert "collection label" in posting_steps and "series label" not in posting_steps, posting_steps
            if width == 375:
                check_no_overflow(page, "/create-step4@375")

            # Load saved account draft for Smoked Cedar 8oz Soy Candle
            page.click("#loadAccountDraft")
            page.wait_for_function(
                "() => document.getElementById('productName')?.value === 'Smoked Cedar 8oz Soy Candle'",
                timeout=10000,
            )

            # 3. /first-ad — products placeholders & outcomes (no AI growth audit / book calls / prints)
            page.goto(BASE + "/first-ad", wait_until="networkidle", timeout=20000)
            page.wait_for_function(
                "() => (document.getElementById('faContextStatus')?.textContent || '')"
                ".includes('Ember & Wick Candle Co.')",
                timeout=15000,
            )
            assert page.locator("#faOutcomeVisitsTitle").inner_text() == "Bring visitors to your shop"
            visits_desc = page.locator("#faOutcomeVisitsDesc").inner_text()
            assert "Etsy, Shopify, or website product pages" in visits_desc, visits_desc
            assert "book a call" not in visits_desc.lower() and "studio" not in visits_desc.lower(), visits_desc
            inq_desc = page.locator("#faOutcomeInquiriesDesc").inner_text()
            assert "custom orders" in inq_desc and "book calls" not in inq_desc.lower(), inq_desc

            page.click("[data-fa-step='2']")
            prod_ph = page.locator("#faProductName").get_attribute("placeholder") or ""
            assert "candle" in prod_ph.lower() or "featured product" in prod_ph.lower(), prod_ph
            assert "growth audit" not in prod_ph.lower() and "consultation" not in prod_ph.lower(), prod_ph
            cta_ph = page.locator("#faCta").get_attribute("placeholder") or ""
            assert "Shop now" in cta_ph and "Book a call" not in cta_ph, cta_ph

            page.click("[data-fa-step='3']")
            aud_ph = page.locator("#faAudience").get_attribute("placeholder") or ""
            assert "handmade gifts" in aud_ph.lower(), aud_ph
            assert "marketing help" not in aud_ph.lower() and "botanical" not in aud_ph.lower(), aud_ph
            if width == 375:
                check_no_overflow(page, "/first-ad@375")

            # 4. /digest — 2 candle competitors with saved analysis on Hearth & Wax
            page.goto(BASE + "/digest", wait_until="networkidle", timeout=20000)
            page.wait_for_function(
                "() => document.querySelectorAll('#dgCompetitors .dg-card').length === 2",
                timeout=15000,
            )
            dg_text = page.locator("#dgCompetitors").inner_text()
            assert "Hearth & Wax" in dg_text and "Cedar & Flame" in dg_text, dg_text
            assert "From your analysis" in dg_text, dg_text
            if width == 375:
                check_no_overflow(page, "/digest@375")

            # 5. /progress — trial plan ($0/mo), 1 move, $240 revenue, +$240 net return
            page.goto(BASE + "/progress", wait_until="networkidle", timeout=20000)
            page.wait_for_function(
                "() => document.getElementById('pgMovesCount')?.textContent === '1'",
                timeout=15000,
            )
            assert page.locator("#pgPlanCost").inner_text() == "$0/mo"
            assert page.locator("#pgPlanCostSub").inner_text() == "Free account"
            assert page.locator("#pgRevenue").inner_text() == "$240"
            assert page.locator("#pgNetReturn").inner_text() == "+$240"
            if width == 375:
                check_no_overflow(page, "/progress@375")

            # 6. /account — signed-in workspace loads cleanly with zero overflow
            page.goto(BASE + "/account", wait_until="networkidle", timeout=20000)
            page.wait_for_function(
                "() => document.body.innerText.includes('Ember & Wick Candle Co.')",
                timeout=15000,
            )
            if width == 375:
                check_no_overflow(page, "/account@375")

            assert not errors, f"Page errors at {{width}}: {{errors}}"
            ctx.close()

        # 7. Sample artist (?workspace=sample) keeps EVERY original word unchanged
        sctx = browser.new_context(viewport={{"width": 1440, "height": 900}})
        spage = sctx.new_page()

        # /today?workspace=sample
        spage.goto(BASE + "/today?workspace=sample", wait_until="networkidle", timeout=20000)
        spage.wait_for_function(
            "() => document.body.innerText.includes('Ek Onkar')",
            timeout=15000,
        )
        spage.click("#openSetup")
        assert spage.locator("#collectionLabel").inner_text() == "Series (optional)"
        sample_series = spage.evaluate(
            "Array.from(document.querySelectorAll('#series option')).map(o => o.value)"
        )
        assert "Abstracts" in sample_series, sample_series
        spage.click("#closeSetup")

        # /create?workspace=sample
        spage.goto(BASE + "/create?workspace=sample", wait_until="networkidle", timeout=20000)
        spage.wait_for_function(
            "() => (document.getElementById('productImageCaption')?.textContent || '')"
            ".includes('Ek Onkar')",
            timeout=15000,
        )
        assert "Pixels, Fine Art America and Saatchi" in spage.locator("#importHint").inner_text()
        assert "series" in spage.locator("#moreDetails > summary").inner_text().lower()
        spage.evaluate("document.getElementById('moreDetails').open = true")
        assert "Series or collection" in spage.locator("label[for='productCollection']").inner_text()
        spage.click("#nextButton")
        spage.click("#nextButton")
        assert spage.locator("#generateButton").inner_text() == "Preview a room scene"
        spage.evaluate("document.getElementById('writingHelp').open = true")
        assert "restrained frame" in spage.locator("#scene").input_value()
        spage.check("#reviewed")
        spage.click("#nextButton")
        assert "not production print files" in spage.locator("#exportFilesNote").inner_text()
        assert "series label" in spage.locator("#postingSteps").inner_text()

        # /first-ad?workspace=sample
        spage.goto(BASE + "/first-ad?workspace=sample", wait_until="networkidle", timeout=20000)
        spage.wait_for_function(
            "() => (document.getElementById('faOutcomeVisitsDesc')?.textContent || '')"
            ".includes('studio listing')",
            timeout=15000,
        )
        spage.click("[data-fa-step='2']")
        assert spage.locator("#faProductName").get_attribute("placeholder") == "e.g., Botanical Linocut Print"
        spage.click("[data-fa-step='3']")
        assert "botanical prints" in (spage.locator("#faAudience").get_attribute("placeholder") or "")
        sctx.close()
    finally:
        browser.close()
print("PRODUCTS_WALKTHROUGH_OK")
"""
    proc = subprocess.run(
        [python_bin, "-c", script],
        capture_output=True,
        text=True,
        timeout=240,
        check=False,
    )
    assert proc.returncode == 0, f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
    assert "PRODUCTS_WALKTHROUGH_OK" in proc.stdout
