"""/today and the suggested moves fit the seller's business, not the sample artist.

A consulting business that finished setup used to see "Featured piece · <name>" as its item,
starter posts about brushwork and collectors, and suggested moves about entry prices, gifts,
commissions and "up to 5 listings on your shop". A seller's own workspace now gets posts and moves
that fit what setup says they offer (products, services or both), no invented item name until
they pick one, and no product-listing scan for a services website. The sample shop is unchanged.
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
from src.models.content_plan import ContentPlanRequest
from src.models.seller import SellerPreferences
from src.services.accounts import AccountSession
from src.services.content_plan import starter_plan
from src.services.seller_memory import rank_seller_recommendations

ART_WORDS = ("artwork", "brushwork", "collector", "piece", "studio item", "signature")


def _plan_text(business_type: str | None, **product: str) -> str:
    request = ContentPlanRequest.model_validate(
        {
            "product": {"title": "AI growth audit", **product},
            "channels": ["instagram", "facebook", "x", "tiktok"],
            "business_type": business_type,
        }
    )
    return starter_plan(request).model_dump_json().lower()


def test_starter_plan_fits_the_business_type() -> None:
    services = _plan_text("services")
    for word in ART_WORDS:
        assert word not in services, word
    assert "who ai growth audit is for." in services
    assert "message me to ask how this could work for you." in services
    products = _plan_text("products", title="Speckled mug")
    for word in ART_WORDS:
        assert word not in products, word
    # The sample artist (no business type) keeps the original wording.
    sample = _plan_text(None)
    assert "a piece of my work, shared with you." in sample
    assert "use the original artwork with padding" in sample
    assert "ask me about this piece." in sample


def test_content_plan_route_takes_business_type() -> None:
    client = TestClient(app)
    body = {"product": {"title": "AI growth audit"}, "channels": ["instagram"]}
    ok = client.post("/api/v1/content-plan", json={**body, "business_type": "services"})
    assert ok.status_code == 200, ok.text
    assert ok.json()["posts"][1]["hook"] == "Who AI growth audit is for."
    bad = client.post("/api/v1/content-plan", json={**body, "business_type": "shop"})
    assert bad.status_code == 422


SHOP_MOVE_WORDS = ("listing", "gift", "commission", "entry price", "studio", "artwork", "piece")


def _move_text(business_type: str | None, goal: str = "") -> tuple[str, str]:
    result = rank_seller_recommendations(
        business_name="North Star Advisory",
        business_type=business_type,  # type: ignore[arg-type]
        preferences=SellerPreferences(goal=goal),
    )
    moves = result["recommendations"]
    return moves[0]["id"], " ".join(f"{m['title']} {m['action']} {m['cta']}" for m in moves)


def test_services_business_gets_services_moves() -> None:
    top, text = _move_text("services")
    for word in SHOP_MOVE_WORDS:
        assert word not in text.lower(), word
    assert top.startswith("move-services-"), top
    # A seller who wants more leads is offered the move that invites questions and calls.
    assert _move_text("services", goal="More leads from consulting clients")[0] == (
        "move-services-invite"
    )
    # Without a business type (the sample artist, older clients) the moves are unchanged.
    _, shop = _move_text(None)
    assert "Refresh titles & descriptions for up to 5 listings" in shop
    assert "commissions" in shop


def test_seller_memory_returns_and_uses_business_type(monkeypatch: pytest.MonkeyPatch) -> None:
    user = AccountSession(
        user_id="33333333-3333-4000-8000-333333333333",
        email="owner@northstar.example",
        email_verified=True,
        access_token="token-3",
        session_id=None,
    )

    async def fake_resolve(*_args: Any, **_kwargs: Any) -> AccountSession:
        return user

    async def fake_load(_account: AccountSession) -> dict[str, Any]:
        onboarding = {"business_name": "North Star Advisory", "business_type": "services"}
        return {"document": {"onboarding": onboarding}, "version": 2, "owner_id": user.user_id}

    monkeypatch.setattr("src.api.seller_memory.resolve_account", fake_resolve)
    monkeypatch.setattr("src.api.seller_memory.load_workspace", fake_load)
    client = TestClient(app)
    memory = client.get("/api/v1/seller-memory")
    assert memory.status_code == 200, memory.text
    assert memory.json()["business_type"] == "services"
    body = {
        "business_name": "North Star Advisory",
        "business_type": "services",
        "preferences": {},
        "competitor_entries": [],
    }
    ranked = client.post("/api/v1/seller-memory/recommend", json=body)
    assert ranked.status_code == 200, ranked.text
    assert all(m["id"].startswith("move-services-") for m in ranked.json()["recommendations"])
    bad = client.post("/api/v1/seller-memory/recommend", json={**body, "business_type": "shop"})
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


def test_today_fits_services_and_products_sellers_e2e(live_server_url: str) -> None:
    python_bin = _find_playwright_python()
    if not python_bin:
        pytest.skip("Playwright runtime not installed")

    runner_script = textwrap.dedent(
        f"""
        import json, re
        from playwright.sync_api import sync_playwright

        BASE = "{live_server_url}"
        ART = re.compile(r"artwork|brushwork|collectors|featured piece|studio item|artist website",
                         re.I)

        def onboarding(name, url, business_type):
            return {{"business_name": name, "shop_urls": [url], "business_type": business_type,
                    "completed_at": "2026-11-18T18:00:00Z", "used_run": False}}

        def open_page(browser, width, user, onb):
            ctx = browser.new_context(viewport={{"width": width, "height": 900}})
            page = ctx.new_page()
            seen = {{"errors": [], "ingest": 0, "plans": [], "recommend": []}}
            page.on("pageerror", lambda e: seen["errors"].append(str(e)))

            def handle(route):
                url = route.request.url.split("?")[0]
                body = None
                if url.endswith("/api/v1/account/me"):
                    body = {{"configured": True, "user": user,
                            "usage": {{"plan": "trial", "used": 0, "limit": 3, "remaining": 3,
                                      "resets_at": None}} if user else None,
                            "live_available": bool(user)}}
                elif "/api/v1/account/workspace" in url and user:
                    body = {{"document": {{"onboarding": onb}}, "version": 1,
                            "owner_id": user["id"], "listing_import": {{"first_visit": True}}}}
                elif url.endswith("/api/v1/seller-memory") and user:
                    body = {{"authenticated": True, "owner_id": user["id"], "version": 1,
                            "business_name": onb["business_name"],
                            "business_type": onb["business_type"], "preferences": {{}},
                            "voice_profile": {{}}, "memory_entries": [],
                            "competitor_entries": [], "suggested_updates": [],
                            "dismiss_signals": []}}
                elif url.endswith("/api/v1/seller-memory/recommend"):
                    seen["recommend"].append(json.loads(route.request.post_data or "{{}}"))
                elif url.endswith("/api/v1/ingest-storefront"):
                    seen["ingest"] += 1
                    body = {{"discovered_catalog_items": []}}
                elif url.endswith("/api/v1/content-plan"):
                    seen["plans"].append(json.loads(route.request.post_data or "{{}}"))
                if body is None:
                    return route.continue_()
                route.fulfill(status=200, content_type="application/json", body=json.dumps(body))

            page.route("**/api/v1/**", handle)
            page.route(lambda u: not u.startswith(BASE) and not u.startswith("data:"),
                       lambda r: r.abort())
            return ctx, page, seen

        def hooks(page):
            return page.locator("#planCards button strong").all_inner_texts()

        def post_texts(page):
            # Every planned post, including text inside the collapsed "Image ideas" panel.
            texts = []
            for i in range(page.locator("#planCards button").count()):
                page.locator("#planCards button").nth(i).click()
                texts += [page.input_value("#postHook"), page.input_value("#postCaption"),
                          page.evaluate("document.getElementById('visualDirection').textContent")]
            page.locator("#planCards button").first.click()
            return " | ".join(texts)

        def no_overflow(page, label):
            assert not page.evaluate(
                "document.documentElement.scrollWidth > document.documentElement.clientWidth"
            ), label

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)

            for width in (375, 1440):
                # A consulting business: services posts, no listing scan, no invented item.
                user = {{"id": f"u-svc-{{width}}", "email": "owner@northstar.example",
                        "email_verified": True}}
                onb = onboarding("North Star Advisory", "https://northstar.example/", "services")
                ctx, page, seen = open_page(browser, width, user, onb)
                page.goto(BASE + "/today", wait_until="networkidle")
                page.wait_for_function(
                    "document.getElementById('itemTitle').textContent"
                    " === 'North Star Advisory · choose a service or offer'", timeout=15000)
                assert hooks(page) == ["What North Star Advisory helps with",
                                       "A recent project, in plain words",
                                       "How working with North Star Advisory goes"], hooks(page)
                main = page.locator("main").inner_text() + post_texts(page)
                assert not ART.search(main), ART.search(main)
                assert seen["ingest"] == 0
                # The context bar names the business and suggests a services move.
                page.wait_for_function(
                    "(() => {{ const b = document.getElementById('smStudioContextBar');"
                    " return b && b.textContent.includes('Your context · North Star Advisory')"
                    " && b.textContent.includes('Selected move'); }})()", timeout=10000)
                bar = page.locator("#smStudioContextBar").inner_text()
                assert not re.search(r"listing|gift|commission|studio", bar, re.I), bar
                assert seen["recommend"][-1]["business_type"] == "services"
                assert page.locator("#goal").input_value() == "inquiries"
                assert page.locator("#goal option[value=visits]").inner_text() == "Website visits"
                no_overflow(page, f"services {{width}}")

                # Another channel: still the local starter posts, never the placeholder label.
                page.click("[data-channel=facebook]")
                page.wait_for_function(
                    "document.querySelectorAll('#planCards button').length === 3", timeout=8000)
                assert all("choose a service" not in h for h in hooks(page)), hooks(page)
                assert seen["plans"] == [], seen["plans"]

                # Naming the service: the plan fits a service and the request says so.
                page.click("#todayManualBtn")
                assert page.locator("#productName").input_value() == ""
                assert page.get_attribute("#productName", "placeholder") == (
                    "Name the service or offer")
                page.fill("#productName", "AI growth audit")
                page.click("#itemForm button.primary")
                page.wait_for_function(
                    "Array.from(document.querySelectorAll('#planCards button strong'))"
                    ".some((s) => s.textContent.includes('AI growth audit'))", timeout=10000)
                assert seen["plans"] and seen["plans"][-1]["business_type"] == "services"
                named = page.locator("main").inner_text() + post_texts(page)
                assert not ART.search(named), ART.search(named)
                assert not seen["errors"], seen["errors"]
                ctx.close()

            # A products seller with nothing imported: no "Featured piece", no art words.
            user = {{"id": "u-prod-1", "email": "maker@fernandkiln.example",
                    "email_verified": True}}
            onb = onboarding("Fern & Kiln", "https://fernandkiln.example/", "products")
            ctx, page, seen = open_page(browser, 1440, user, onb)
            page.goto(BASE + "/today", wait_until="networkidle")
            page.wait_for_function(
                "document.getElementById('itemTitle').textContent"
                " === 'Fern & Kiln · choose an item'", timeout=15000)
            page.wait_for_function("document.getElementById('importStatus').textContent"
                                   ".startsWith('No listings found')", timeout=10000)
            assert seen["ingest"] == 1
            assert hooks(page)[0] == "New from Fern & Kiln", hooks(page)
            made = page.locator("main").inner_text() + post_texts(page)
            assert not ART.search(made), ART.search(made)
            assert page.locator("#destination option[value=website]").inner_text() == "My website"
            assert not seen["errors"], seen["errors"]
            ctx.close()

            # The sample shop keeps the artist's wording.
            ctx, page, seen = open_page(browser, 1440, None, None)
            page.goto(BASE + "/today?workspace=sample", wait_until="networkidle")
            page.wait_for_function(
                "document.getElementById('itemTitle').textContent === 'Ek Onkar'", timeout=15000)
            assert hooks(page)[1] == "Behind Ek Onkar: materials & story", hooks(page)
            assert page.locator("#destination option[value=website]").inner_text() == (
                "Artist website")
            assert page.locator("#goal option[value=visits]").inner_text() == "Shop visits"
            assert not seen["errors"], seen["errors"]
            ctx.close()
            browser.close()
        print("TODAY_ANY_BUSINESS_OK")
        """
    )
    proc = subprocess.run(
        [python_bin, "-c", runner_script], capture_output=True, text=True, timeout=240, check=False
    )
    assert proc.returncode == 0, f"STDOUT: {proc.stdout}\nSTDERR: {proc.stderr}"
    assert "TODAY_ANY_BUSINESS_OK" in proc.stdout
