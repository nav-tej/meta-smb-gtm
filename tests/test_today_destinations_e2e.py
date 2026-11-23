"""Offline browser coverage for /today destinations and wording by workspace."""

from __future__ import annotations

import socket
import subprocess
import threading
import time
from collections.abc import Iterator

import pytest
import uvicorn

from src.api.main import app


@pytest.fixture(scope="module")
def today_server() -> Iterator[str]:
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    for _ in range(100):
        if server.started:
            break
        time.sleep(0.05)
    assert server.started
    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        server.should_exit = True
        thread.join(timeout=5)


@pytest.mark.parametrize("width", [375, 1440])
def test_today_destinations_and_wording(today_server: str, width: int) -> None:
    """Exercise real UI, exported captions, legacy drafts, handoffs and save status."""
    script = r'''
import json
import sys
from playwright.sync_api import sync_playwright, expect

BASE, WIDTH = sys.argv[1], int(sys.argv[2])
OWN = {
    "website": "My website",
    "booking": "Booking or contact page",
    "etsy": "Etsy shop or listing",
    "shopify": "Shopify store",
    "other": "Other link",
}
SAMPLE = {
    "pixels": "Pixels",
    "fineartamerica": "Fine Art America",
    "saatchi": "Saatchi Art",
    "website": "Artist website",
    "other": "My shop / inquiry page",
}
LINK = "https://seller.example/details"
USER = {"id": "today-dest-owner", "email": "owner@seller.example", "email_verified": True}
KEY = "muse-editor-v1:daily:account:today-dest-owner"


def options(page):
    return page.locator("#destination option").evaluate_all(
        "(els) => Object.fromEntries(els.map(e => [e.value, e.textContent]))"
    )


def copied(page):
    page.select_option("#format", "text")
    page.fill("#postHook", "A clear invitation")
    page.fill("#postCaption", "Find the details here.")
    page.check("#reviewed")
    page.evaluate("window.copiedCaption = null")
    page.click("#copyOnly")
    page.wait_for_function("window.copiedCaption !== null")
    return page.evaluate("window.copiedCaption")


def seed(page, key, value):
    page.evaluate("([k,v]) => localStorage.setItem(k, JSON.stringify(v))", [key, value])


with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    for kind in ("products", "services", "both", "sample"):
        ctx = browser.new_context(viewport={"width": WIDTH, "height": 900})
        ctx.add_init_script("""Object.defineProperty(navigator, 'clipboard', {
            value: {writeText: async text => {window.copiedCaption = text;}}
        });""")
        page = ctx.new_page()
        errors, paid = [], []
        page.on("pageerror", lambda e: errors.append(str(e)))
        doc = {
            "onboarding": {
                "business_name": "Seller Example",
                "business_type": kind,
                "shop_urls": [LINK],
                "completed_at": "2026-11-20T12:00:00Z",
            }
        }

        def route_api(route):
            url = route.request.url.split("?")[0]
            data = None
            if "live=true" in route.request.url or url.endswith("/generate-ads"):
                paid.append(route.request.url)
                return route.abort()
            if url.endswith("/account/me"):
                data = {
                    "configured": True,
                    "user": USER,
                    "live_available": False,
                    "usage": {"plan": "trial", "used": 0, "limit": 3, "remaining": 3},
                }
            elif url.endswith("/account/workspace"):
                if route.request.method == "PUT":
                    payload = json.loads(route.request.post_data)
                    doc.clear()
                    doc.update(payload["document"])
                data = {"document": doc, "version": 1, "owner_id": USER["id"]}
            elif url.endswith("/seller-memory"):
                data = {
                    "authenticated": True,
                    "owner_id": USER["id"],
                    "version": 1,
                    "business_name": "Seller Example",
                    "business_type": kind,
                    "preferences": {},
                    "voice_profile": {},
                    "memory_entries": [],
                    "competitor_entries": [],
                    "suggested_updates": [],
                    "dismiss_signals": [],
                }
            elif url.endswith("/readiness"):
                data = {
                    "default_mode": "demo",
                    "accounts_required": True,
                    "provider_key_configured": False,
                }
            elif url.endswith("/ingest-storefront"):
                raise AssertionError("No listing scan is authorized by this fixture")
            elif url.endswith("/daily-brief") and "workspace=own" in route.request.url:
                # The real route needs a server-side session this fixture does not fake; its 401
                # would open the "session ended" dialog.
                move = {
                    "title": "Share one thing you made this week",
                    "reason": "Uses your saved setup.",
                    "href": "/create?workspace=own",
                    "impact": "medium",
                    "recommendation": {
                        "id": "share",
                        "title": "Share one thing you made this week",
                    },
                }
                data = {
                    "business_name": "Seller Example",
                    "items": [],
                    "move": move,
                    "focus": move,
                    "action_items": [move],
                    "overnight_changes": [],
                    "overnight_note": "",
                    "trends": [],
                    "source": "Saved context. 0 runs spent.",
                }
            if data is None:
                return route.continue_()
            route.fulfill(status=200, content_type="application/json", body=json.dumps(data))

        page.route("**/api/v1/**", route_api)
        page.route(
            lambda u: not u.startswith(BASE) and not u.startswith("data:"), lambda r: r.abort()
        )
        path = "/today?workspace=" + ("sample" if kind == "sample" else "own")
        page.goto(BASE + path, wait_until="networkidle")
        page.wait_for_function(
            'window.museDailySnapshot && '
            'document.querySelectorAll("#planCards button").length === 3'
        )
        assert options(page) == (SAMPLE if kind == "sample" else OWN), options(page)
        assert page.get_attribute("#researchWebsite", "placeholder") == "your-website.com"
        assert not page.evaluate("document.documentElement.scrollWidth > innerWidth")
        sample = kind == "sample"
        words = {
            "products": "product",
            "services": "service or offer",
            "both": "product or service",
        }
        expected_scene = (
            "A simple, softly lit room. Keep attention on the artwork."
            if sample
            else "A simple, softly lit setting. Keep attention on the " + words[kind] + "."
        )
        assert page.input_value("#scenePrompt") == expected_scene
        note = page.locator("#sceneNote").text_content()
        assert note == (
            "AI scenes can change artwork details. Compare with your original."
            if sample
            else "AI scenes can change details in your photo. Compare with your original."
        )
        hint = page.locator("#itemHint").text_content()
        assert (
            ("Pixels is your preferred shop." in hint)
            if sample
            else (words[kind] in hint and "Pixels" not in hint)
        )
        assert page.locator("#destinationLink").text_content() == (
            "Pixels ↗" if sample else "My website ↗"
        )

        # Defaults must not replace a scene typed by the seller during channel renders.
        page.locator(".small-details summary").click()
        page.fill("#scenePrompt", "Use the supplied photo with a plain blue background.")
        page.click("[data-channel=facebook]")
        assert (
            page.input_value("#scenePrompt")
            == "Use the supplied photo with a plain blue background."
        )
        fb = copied(page)
        expected_link = "https://sarabjit-singh.pixels.com/" if sample else LINK
        assert expected_link in fb and "link in my profile" not in fb, fb
        for channel in ("instagram", "tiktok"):
            page.click("[data-channel=" + channel + "]")
            caption = copied(page)
            line = (
                "Explore the work through the link in my profile."
                if sample
                else "Learn more about this " + words[kind] + " through the link in my profile."
            )
            assert line in caption and expected_link not in caption, caption

        page.click("#openSetup")
        page.select_option("#destination", "saatchi" if sample else "booking")
        hint = page.locator("#itemHint").text_content()
        assert (
            ("other shops may carry different work." in hint)
            if sample
            else (
                "Booking or contact page keeps its own price and link." in hint
                and words[kind] in hint
            )
        )
        page.click("#closeSetup")

        if not sample:
            # Refreshes triggered by Save/Load must preserve the action's status and draft bytes.
            page.click("#loadAccountDraft")
            expect(page.locator("#draftStatus")).to_have_text(
                "No account draft for this editor yet. Save this draft first."
            )
            page.wait_for_load_state("networkidle")
            assert page.locator("#draftStatus").text_content().startswith("No account draft")
            page.click("#saveAccountDraft")
            expect(page.locator("#draftStatus")).to_have_text(
                "Saved to your account. Later edits stay on this device until you save again."
            )
            page.wait_for_load_state("networkidle")
            assert page.locator("#draftStatus").text_content().startswith("Saved to your account.")
            before = page.evaluate("(k) => localStorage.getItem(k)", KEY)
            page.evaluate("window.museAccount.refresh()")
            page.wait_for_load_state("networkidle")
            assert page.evaluate("(k) => localStorage.getItem(k)", KEY) == before
            draft = json.loads(before)
            # All legacy destination values normalize without dropping links or prices.
            for legacy in ("pixels", "fineartamerica", "saatchi"):
                draft["product"].update(destination=legacy, destination_url=LINK, price="$25")
                # Leave the editor before seeding: its pagehide handler saves the active draft.
                page.goto(BASE + "/api/v1/health", wait_until="load")
                seed(page, KEY, draft)
                page.goto(BASE + path, wait_until="networkidle")
                expect(page.locator("#destination")).to_have_value("other")
                snapshot = page.evaluate("window.museDailySnapshot().product")
                assert snapshot["destination"] == "other" and snapshot["destination_url"] == LINK
                assert snapshot["price"] == "$25"
                assert options(page) == OWN
                assert page.input_value("#scenePrompt") == expected_scene
                # Recommendation handoffs also normalize, retaining the loaded draft's link.
                handoff = {
                    "owner_id": USER["id"],
                    "workspace_mode": "own",
                    "destination": legacy,
                    "product_name": "An offer",
                    "title": "Share the details",
                    "action": "Invite a question",
                    "recommendation_id": "legacy-handoff",
                }
                seed(page, "muse.sm.handoff.today-dest-owner.legacy-handoff", handoff)
                page.goto(BASE + path + "&sm_handoff=legacy-handoff", wait_until="networkidle")
                snapshot = page.evaluate("window.museDailySnapshot().product")
                assert snapshot["destination"] == "other" and snapshot["destination_url"] == LINK
                assert page.input_value("#destination") == "other"
                assert page.evaluate("window.museDailySnapshot().idea_id") == "legacy-handoff"
            # Same-page mode switching rebuilds options and restores own draft destination.
            page.evaluate("window.museModes.enterSampleMode()")
            page.wait_for_function(
                "document.querySelector('#destination option')?.value === 'pixels'"
            )
            assert options(page) == SAMPLE
            assert (
                page.input_value("#scenePrompt")
                == "A simple, softly lit room. Keep attention on the artwork."
            )
            page.evaluate("window.museModes.goToOwnWorkspace()")
            page.wait_for_function(
                "document.querySelector('#destination option')?.value === 'website'"
            )
            assert options(page) == OWN
        assert not errors, errors
        assert not paid, paid
        ctx.close()
    browser.close()
print("PASS: products, services, both, sample, legacy drafts/handoffs, statuses at", WIDTH)
'''
    result = subprocess.run(
        ["/usr/bin/python3", "-c", script, today_server, str(width)],
        capture_output=True,
        text=True,
        timeout=180,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
