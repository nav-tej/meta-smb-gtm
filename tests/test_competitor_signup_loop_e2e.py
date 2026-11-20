"""Competitor suggestions in setup are real, and guests are led to an account without losing work.

Setup step 3 used to "suggest" competitors from a saved example made for nplusalpha.com (Clutch,
Upwork, Toptal), ticked and saved for every seller, with invented pottery shops as a fallback. It
now asks Muse to suggest shops from the seller's own website (1 run), unticked. A guest who asks
for suggestions, or wants a shop analyzed on the home page, is asked to create a free account;
after sign-in the setup wizard keeps their progress and the shops they added.
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

import pytest
import uvicorn

from src.api.main import STATIC_DIR, app


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


def test_setup_suggestions_are_real_and_honest_about_cost() -> None:
    wizard = (STATIC_DIR / "welcome.js").read_text(encoding="utf-8")
    start = wizard.index("const suggestBtnLabel")
    handler = wizard[start : wizard.index("getElementById('wkAddCompBtn')", start)]
    assert "/api/v1/research-targets?live=true" in handler
    assert "body: JSON.stringify({ website: shopUrl })" in handler
    assert "selected: false" in handler
    for gone in ("research-example", "desertceramics", "earthandclay", "artisankiln", "clutch"):
        assert gone not in handler, gone
    assert "window.museAccount?.open?.('signup'" in handler

    page = (STATIC_DIR / "welcome.html").read_text(encoding="utf-8")
    step3 = page[page.index('id="wkStep3"') : page.index('id="wkStep4"')]
    assert "Suggest similar shops (1 run)" in step3
    assert "0 runs" not in step3 and "completely free" not in step3
    assert "—" not in step3

    home = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
    # A guest no longer gets a silent no-op from "Request analysis".
    assert "!window.museAccount.liveReady()) return;" not in home
    assert "promptForLiveRuns(url, btn); return; }" in home
    assert "if (li?.dataset?.url) return li.dataset.url;" in home


def test_signup_loop_and_real_suggestions_e2e(live_server_url: str) -> None:
    python_bin = _find_playwright_python()
    if not python_bin:
        pytest.skip("Playwright runtime not installed")

    runner_script = textwrap.dedent(
        f"""
        import json
        from playwright.sync_api import sync_playwright

        BASE = "{live_server_url}"
        USER = {{"id": "u-loop-1", "email": "maker@mountainpottery.example",
                "email_verified": True}}
        SHOP = "https://mountainpottery.example/"
        GUEST_SETUP = {{
            "step": 3, "business_name": "Mountain Pottery Studio", "shop_urls": [SHOP],
            "competitors": [{{"name": "Rival Clay", "url": "https://rivalclay.example/",
                             "role": "similar_audience", "reason": "Same mugs",
                             "selected": True}}],
        }}
        TARGETS = {{
            "business_summary": "Handmade stoneware mugs and vases.",
            "targets": [
                {{"name": "Kiln Row Ceramics", "url": "https://kilnrow.example",
                 "reason": "Sells stoneware mugs at similar prices"}},
                {{"name": "Glaze Lab", "url": "https://glazelab.example",
                 "reason": "Same gift buyers"}},
            ],
            "next_move": "Compare mug prices.", "evidence_urls": [],
            "provenance": "Muse suggestions from your website snapshot.",
        }}

        def open_page(browser, width=1440):
            ctx = browser.new_context(viewport={{"width": width, "height": 900}})
            page = ctx.new_page()
            s = {{"signed_in": False, "targets_status": 200, "asked": [], "example": 0}}
            errors = []
            page.on("pageerror", lambda e: errors.append(str(e)))

            def reply(route, payload, status=200):
                route.fulfill(status=status, content_type="application/json",
                              body=json.dumps(payload))

            def handle(route):
                url = route.request.url.split("?")[0]
                if url.endswith("/api/v1/account/me"):
                    if not s["signed_in"]:
                        return reply(route, {{"configured": True, "user": None, "usage": None,
                                             "live_available": False}})
                    return reply(route, {{"configured": True, "user": USER, "live_available": True,
                                         "usage": {{"plan": "trial", "used": 0, "limit": 3,
                                                   "remaining": 3, "resets_at": None}}}})
                if "/api/v1/account/workspace" in url and s["signed_in"]:
                    return reply(route, {{"document": {{}}, "version": 1, "owner_id": USER["id"]}})
                if url.endswith("/api/v1/research-targets"):
                    s["asked"].append(json.loads(route.request.post_data or "{{}}"))
                    if s["targets_status"] != 200:
                        return reply(route, {{"detail": "Your 3 free Muse runs are used. "
                                             "Pick a plan for more runs."}}, 429)
                    return reply(route, TARGETS)
                if url.endswith("/api/v1/research-example"):
                    s["example"] += 1
                return route.continue_()

            page.route("**/api/v1/**", handle)
            page.route(lambda u: not u.startswith(BASE) and not u.startswith("data:"),
                       lambda r: r.abort())
            return ctx, page, s, errors

        def dialog_text(page):
            page.wait_for_selector("dialog.ma-dialog[open]", timeout=8000)
            return page.locator("dialog.ma-dialog[open]").inner_text()

        def comp_names(page):
            return page.locator("#wkCompList li strong").all_inner_texts()

        def handoff(page):
            return page.evaluate("JSON.parse(localStorage.getItem('muse.signup_handoff.v1'))")

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)

            # 1. A guest in setup asks for suggestions: a free-account prompt, and after sign-in
            #    the wizard is back on step 3 with everything they entered.
            ctx, page, s, errors = open_page(browser, width=375)
            # Seed the guest's progress once, before any page script runs.
            page.add_init_script(
                "if (!sessionStorage.getItem('seeded')) {{"
                " localStorage.setItem('muse_onboarding_anon', "
                + json.dumps(json.dumps(GUEST_SETUP))
                + "); sessionStorage.setItem('seeded', '1'); }}"
            )
            page.goto(BASE + "/welcome", wait_until="domcontentloaded")
            page.wait_for_selector("#wkStep3:not([hidden])", timeout=10000)
            assert "free account" in page.locator("#wkSuggestNote").inner_text()
            page.click("#wkDiscoverCompBtn")
            assert "suggest shops like yours" in dialog_text(page)
            assert handoff(page)["from"] == "wizard" and handoff(page)["step"] == 3
            assert not s["asked"] and not s["example"]

            s["signed_in"] = True
            with page.expect_navigation(timeout=15000):
                page.evaluate("window.museAccount.refresh()")
            page.wait_for_selector("#wkStep3:not([hidden])", timeout=10000)
            assert "Rival Clay" in comp_names(page), comp_names(page)
            assert page.evaluate("localStorage.getItem('muse_onboarding_anon')") is None
            assert handoff(page) is None
            saved = page.evaluate("JSON.parse(localStorage.getItem('muse_onboarding_u-loop-1'))")
            assert saved["shop_urls"] == [SHOP], saved

            # 2. Signed in: Muse suggests from their own website, 1 run, results unticked.
            page.click("#wkDiscoverCompBtn")
            page.wait_for_function(
                "document.getElementById('wkSuggestNote').textContent.includes('suggested 2')",
                timeout=10000)
            assert s["asked"] == [{{"website": SHOP}}], s["asked"]
            names = comp_names(page)
            assert names == ["Rival Clay", "Kiln Row Ceramics", "Glaze Lab"], names
            ticks = page.locator("#wkCompList li input[type=checkbox]").evaluate_all(
                "(els) => els.map((e) => e.checked)")
            assert ticks == [True, False, False], ticks
            assert not page.evaluate(
                "document.documentElement.scrollWidth > document.documentElement.clientWidth")

            #    No runs left: the reason is shown and the button works again.
            s["targets_status"] = 429
            page.click("#wkDiscoverCompBtn")
            page.wait_for_selector("#wkStep3Error:not([hidden])", timeout=10000)
            assert "runs are used" in page.locator("#wkStep3Error").inner_text()
            label = page.locator("#wkDiscoverCompBtn").inner_text()
            assert label == "Suggest similar shops (1 run)", label
            assert not s["example"]
            assert not errors, errors
            ctx.close()

            # 3. A guest on home adds a shop: a free-account prompt instead of "needs a live
            #    server", and the shop is waiting in setup after sign-in.
            ctx, page, s, errors = open_page(browser)
            page.goto(BASE + "/", wait_until="networkidle")
            page.fill("#addCompetitorInput", "https://rival-shop.example")
            page.locator("#addCompetitorInput").press("Enter")
            assert "analyze rival-shop.example" in dialog_text(page)
            row = page.locator("#sellerList li.added").last
            assert "Sign in to analyze" in row.inner_text(), row.inner_text()
            assert handoff(page)["competitors"] == ["https://rival-shop.example/"], handoff(page)
            page.keyboard.press("Escape")

            #    A sample shop's "Request analysis" prompts too, without carrying it into setup.
            page.locator("#sellerList li:not(.added) .js-live-brief",
                         has_text="Request analysis").first.click()
            assert "analyze shops you choose" in dialog_text(page)
            assert handoff(page)["competitors"] == ["https://rival-shop.example/"]
            page.keyboard.press("Escape")

            s["signed_in"] = True
            page.evaluate("window.museAccount.refresh()")
            page.wait_for_url("**/welcome", timeout=15000)
            page.wait_for_selector("#wkStep1:not([hidden])", timeout=10000)
            saved = page.evaluate("JSON.parse(localStorage.getItem('muse_onboarding_u-loop-1'))")
            urls = [c["url"] for c in saved["competitors"]]
            assert urls == ["https://rival-shop.example/"], saved["competitors"]
            assert not errors, errors
            ctx.close()
            browser.close()
        print("SIGNUP_LOOP_OK")
        """
    )
    proc = subprocess.run(
        [python_bin, "-c", runner_script], capture_output=True, text=True, timeout=240, check=False
    )
    assert proc.returncode == 0, f"STDOUT: {proc.stdout}\nSTDERR: {proc.stderr}"
    assert "SIGNUP_LOOP_OK" in proc.stdout
