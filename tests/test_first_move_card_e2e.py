"""A seller who just finished setup is told what to do first, and the first analysis is real.

Right after setup the dashboard offered about fifteen controls at equal weight and no next step.
It now opens with a "Start here" card: analyze a competitor (1 run; free to view once saved) or
make today's post (free). The seller-memory panel shows one line until Muse remembers something.
Also covered: "Analyze seller" in the seller's own workspace used to send the row's first link,
the Meta Ad Library search, as the shop to analyze.
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


def test_first_move_wiring_and_copy() -> None:
    home = (STATIC_DIR / "welcome.js").read_text(encoding="utf-8")
    fn = home[home.index("function syncFirstMoveCard(") : home.index("let setupHeroHidLoggedOut")]
    assert "Your workspace is set up. Get your first result." in fn
    assert "Viewing it is free." in fn and "Uses 1 run" in fn
    assert "—" not in fn
    assert "li.dataset.url = competitorUrl(comp.url);" in home
    assert "syncFirstMoveCard(false);" in home

    memory = (STATIC_DIR / "seller-memory.js").read_text(encoding="utf-8")
    assert "id: 'smExpandContextBtn'" in memory and "'Set your goal'" in memory

    service = Path("src/services/seller_memory.py").read_text(encoding="utf-8")
    assert "across 5 listings" not in service
    assert "for up to 5 listings on" in service


def test_first_move_card_e2e(live_server_url: str) -> None:
    python_bin = _find_playwright_python()
    if not python_bin:
        pytest.skip("Playwright runtime not installed")

    runner_script = textwrap.dedent(
        f"""
        import json
        from playwright.sync_api import sync_playwright

        BASE = "{live_server_url}"
        USER = {{"id": "u-first-2", "email": "maker@mountainpottery.example",
                "email_verified": True}}
        COMP = {{"name": "Kiln Row Ceramics", "url": "https://kilnrow.example",
                "reason": "Similar mugs", "selected": True}}

        def setup(competitors):
            return {{"business_name": "Mountain Pottery Studio",
                    "shop_urls": ["https://mountainpottery.example/"],
                    "competitors": competitors, "completed_at": "2026-11-17T18:00:00Z",
                    "used_run": False,
                    "crawl_summary": {{"sample_titles": ["Speckled stoneware mug"],
                                      "price_range": "$28-$64"}}}}

        def open_page(browser, width, doc, signed_in=True):
            ctx = browser.new_context(viewport={{"width": width, "height": 900}})
            page = ctx.new_page()
            s = {{"analyzed": []}}
            errors = []
            page.on("pageerror", lambda e: errors.append(str(e)))

            def reply(route, payload, status=200):
                route.fulfill(status=status, content_type="application/json",
                              body=json.dumps(payload))

            def handle(route):
                url = route.request.url.split("?")[0]
                if url.endswith("/api/v1/account/me"):
                    if not signed_in:
                        return reply(route, {{"configured": True, "user": None, "usage": None,
                                             "live_available": False}})
                    return reply(route, {{"configured": True, "user": USER, "live_available": True,
                                         "usage": {{"plan": "trial", "used": 0, "limit": 3,
                                                   "remaining": 3, "resets_at": None}}}})
                if "/api/v1/account/workspace" in url and signed_in:
                    return reply(route, {{"document": doc, "version": 1, "owner_id": USER["id"]}})
                if url.endswith("/api/v1/analyze-competitors"):
                    s["analyzed"].append(json.loads(route.request.post_data or "{{}}"))
                    return reply(route, {{"detail": "Test stops here."}}, 503)
                return route.continue_()

            page.route("**/api/v1/**", handle)
            page.route(lambda u: not u.startswith(BASE) and not u.startswith("data:"),
                       lambda r: r.abort())
            return ctx, page, s, errors

        def card_text(page):
            return page.locator("#firstMoveCard").inner_text()

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)

            # 1. Just set up, one competitor, nothing analyzed: the card leads to the analysis,
            #    and the analysis is of the competitor's own site.
            for width in (375, 1440):
                ctx, page, s, errors = open_page(browser, width, {{"onboarding": setup([COMP])}})
                page.goto(BASE + "/", wait_until="networkidle")
                page.wait_for_selector("#firstMoveCard:not([hidden])", timeout=15000)
                text = card_text(page)
                assert "Your workspace is set up. Get your first result." in text, text
                assert "(you have 3 left)" in text, text
                btn = page.locator("#firstMoveCompetitorBtn")
                assert btn.inner_text() == "Analyze Kiln Row Ceramics · 1 run", btn.inner_text()
                assert page.locator("#firstMoveCard a").get_attribute("href") == "/today"
                assert not page.evaluate(
                    "document.documentElement.scrollWidth > document.documentElement.clientWidth"
                ), width
                # Memory panel: one line until Muse remembers something.
                page.wait_for_selector("#smExpandContextBtn", state="visible", timeout=10000)
                assert not page.locator("text=Apply to this draft (0 runs)").is_visible()
                if width == 1440:
                    page.click("#smExpandContextBtn")
                    page.wait_for_selector("text=Apply to this draft (0 runs)", timeout=5000)
                    with page.expect_request(lambda r: "analyze-competitors" in r.url,
                                             timeout=20000):
                        btn.click()
                    page.wait_for_timeout(300)
                    assert [a["competitor_url"] for a in s["analyzed"]] == [
                        "https://kilnrow.example"], s["analyzed"]
                    # Muse is told about this seller's shop, not the sample artist's.
                    context = s["analyzed"][0]["seller_context"]
                    assert "Mountain Pottery Studio" in context, context
                    assert "Speckled stoneware mug" in context and "$28-$64" in context, context
                    assert "Sikh" not in context and "artist" not in context, context
                assert not errors, errors
                ctx.close()

            # 2. Already analyzed: viewing is free and no run is asked for.
            doc = {{"onboarding": setup([COMP]),
                   "briefs": {{"https://kilnrow.example": {{"summary": "saved"}}}}}}
            ctx, page, s, errors = open_page(browser, 1440, doc)
            page.goto(BASE + "/", wait_until="networkidle")
            page.wait_for_selector("#firstMoveCard:not([hidden])", timeout=15000)
            assert page.locator("#firstMoveCompetitorBtn").inner_text() == "View analysis"
            assert "Viewing it is free." in card_text(page)
            # The note under the competitor list fits the workspace and stays that way.
            page.wait_for_timeout(1500)
            note = page.locator("#competitorSnapshotsNote").inner_text()
            assert note == (
                "Analyses you run are saved to your workspace. Viewing one again is free."), note
            page.goto(BASE + "/?workspace=sample", wait_until="networkidle")
            page.wait_for_function(
                "document.documentElement.dataset.museMode === 'account_sample'", timeout=15000)
            page.wait_for_timeout(1500)
            note = page.locator("#competitorSnapshotsNote").inner_text()
            assert note.startswith("Saved public snapshots from Nov 3, 2026."), note
            assert not errors, errors
            ctx.close()

            # 3. No competitor yet: the card points to adding one. Hiding it sticks.
            ctx, page, s, errors = open_page(browser, 1440, {{"onboarding": setup([])}})
            page.goto(BASE + "/", wait_until="networkidle")
            page.wait_for_selector("#firstMoveCard:not([hidden])", timeout=15000)
            page.click("#firstMoveCompetitorBtn")
            page.wait_for_function(
                "document.activeElement && document.activeElement.id === 'addCompetitorInput'",
                timeout=5000)
            page.click("#firstMoveCard .first-move-hide")
            assert page.locator("#firstMoveCard").is_hidden()
            page.reload(wait_until="networkidle")
            page.wait_for_timeout(1500)
            assert page.locator("#firstMoveCard").is_hidden()
            assert not errors, errors
            ctx.close()

            # 4. Guests and sellers who have not finished setup do not see it.
            for signed_in, doc in ((False, {{}}), (True, {{}})):
                ctx, page, s, errors = open_page(browser, 1440, doc, signed_in=signed_in)
                page.goto(BASE + "/", wait_until="networkidle")
                page.wait_for_timeout(1500)
                assert page.locator("#firstMoveCard").is_hidden(), signed_in
                ctx.close()
            browser.close()
        print("FIRST_MOVE_OK")
        """
    )
    proc = subprocess.run(
        [python_bin, "-c", runner_script], capture_output=True, text=True, timeout=240, check=False
    )
    assert proc.returncode == 0, f"STDOUT: {proc.stdout}\nSTDERR: {proc.stderr}"
    assert "FIRST_MOVE_OK" in proc.stdout
