""" "Ask Muse what to do next" answers in place with moves the seller can act on.

The home research card used to parse a question into "Directive parsed: Focus: ... · Window: ..."
and offer "Confirm & Apply", which only saved the directive in the browser; nothing on the page
changed. It now shows the matching moves right away: in the sample shop, the moves from its saved
research with links straight to the post; in the seller's own workspace, the tool to start with.
"""

from __future__ import annotations

import re
import shutil
import socket
import subprocess
import sys
import textwrap
import threading
import time
from collections.abc import Iterator
from pathlib import Path
from typing import get_args

import pytest
import uvicorn

from src.api.main import STATIC_DIR, app
from src.models.directive import FocusArea


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


def test_steer_card_copy_and_every_focus_has_an_answer() -> None:
    index = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
    card_start = index.index('id="jrSteerResearch"')
    card = index[card_start : index.index("</article>", card_start)]
    for jargon in ("Parse directive", "Confirm &amp; Apply", "Track I", "Steerable research"):
        assert jargon not in card, jargon
    assert "Ask Muse what to do next" in card
    assert 'id="jrSteerAnswer"' in card
    assert "—" not in card

    reco = (STATIC_DIR / "reco-actions.js").read_text(encoding="utf-8")
    for table in ("SAMPLE_BY_FOCUS", "OWN_BY_FOCUS"):
        start = reco.index(f"var {table} = {{")
        body = reco[start : reco.index("};", start)]
        keys = set(re.findall(r"(\w+): [\[{]", body))
        assert keys == set(get_args(FocusArea)), (table, keys)
    # Every sample move links to an idea the sample studio accepts.
    modes = (STATIC_DIR / "workspace-modes.js").read_text(encoding="utf-8")
    for idea in re.findall(r"idea: '(idea-[\w-]+)'", reco):
        assert f"'{idea}'" in modes, idea
    assert "renderSteerAnswer(activeDirective && activeDirective.focus);" in reco


def test_steer_card_answers_with_actionable_moves_e2e(live_server_url: str) -> None:
    python_bin = _find_playwright_python()
    if not python_bin:
        pytest.skip("Playwright runtime not installed")

    runner_script = textwrap.dedent(
        f"""
        import json
        from playwright.sync_api import sync_playwright

        BASE = "{live_server_url}"
        USER = {{"id": "u-steer-1", "email": "maker@mountainpottery.example",
                "email_verified": True}}
        DONE = {{"business_name": "Mountain Pottery Studio",
                "shop_urls": ["https://mountainpottery.example/"],
                "competitors": [{{"name": "Desert Ceramics", "url": "https://desertceramics.example"}}],
                "completed_at": "2026-11-16T18:00:00Z", "used_run": False}}

        def open_page(browser, width, signed_in):
            ctx = browser.new_context(viewport={{"width": width, "height": 900}})
            page = ctx.new_page()
            errors = []
            page.on("pageerror", lambda e: errors.append(str(e)))

            def handle(route):
                url = route.request.url.split("?")[0]
                body = None
                if url.endswith("/api/v1/account/me"):
                    body = {{"configured": True, "user": USER if signed_in else None,
                            "usage": {{"plan": "trial", "used": 0, "limit": 3, "remaining": 3,
                                      "resets_at": None}} if signed_in else None,
                            "live_available": signed_in}}
                elif "/api/v1/account/workspace" in url and signed_in:
                    body = {{"document": {{"onboarding": DONE}}, "version": 1,
                            "owner_id": USER["id"]}}
                if body is None:
                    return route.continue_()
                route.fulfill(status=200, content_type="application/json", body=json.dumps(body))

            page.route("**/api/v1/**", handle)
            page.route(lambda u: not u.startswith(BASE) and not u.startswith("data:"),
                       lambda r: r.abort())
            return ctx, page, errors

        def ask(page, chip_text):
            page.locator(".jr-chip-btn", has_text=chip_text).click()
            page.wait_for_function(
                "(() => {{ const a = document.getElementById('jrSteerAnswer');"
                " return a && !a.hidden && a.querySelector('.jr-steer-move'); }})()",
                timeout=8000,
            )
            return page.evaluate(
                "Array.from(document.querySelectorAll('#jrSteerAnswer .jr-steer-move'))"
                ".map((a) => ({{href: a.getAttribute('href'),"
                " title: a.querySelector('strong').textContent}}))"
            )

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)

            # Sample shop: the answer is the matching saved moves, linking straight to the post.
            for width in (375, 1440):
                ctx, page, errors = open_page(browser, width, signed_in=False)
                page.goto(BASE + "/?workspace=sample#loop-research", wait_until="networkidle")
                page.locator("#jrSteerResearch").wait_for(state="visible", timeout=10000)
                moves = ask(page, "Weekly post ideas")
                assert [m["title"] for m in moves] == [
                    "Tell one painting story", "Feature your Empowering Women series"], moves
                for m in moves:
                    assert "workspace=sample" in m["href"] and "idea=idea-" in m["href"], m
                summary = page.locator("#jrDirectiveSummary").inner_text()
                assert "Focus:" in summary and "Directive parsed" not in summary, summary
                assert page.locator("#jrDirectiveCost").inner_text() == "No runs used"
                assert not page.evaluate(
                    "document.documentElement.scrollWidth > document.documentElement.clientWidth"
                ), width
                assert "idea=idea-3-gift-ready" in ask(page, "Gifts under $50")[0]["href"]
                moves = ask(page, "Why $59.99 entry")
                assert "idea=idea-2-starter-prints" in moves[0]["href"], moves
                page.locator("#jrSteerAnswer .jr-steer-move").first.click()
                page.wait_for_url("**/create?*idea=idea-2-starter-prints*", timeout=10000)
                assert "workspace=sample" in page.url, page.url
                assert not errors, errors
                ctx.close()

            # Own workspace: one move that points to the tool to start with, not sample data.
            ctx, page, errors = open_page(browser, 1440, signed_in=True)
            page.goto(BASE + "/", wait_until="networkidle")
            page.wait_for_function(
                "document.documentElement.dataset.museMode === 'account_own'", timeout=15000)
            page.locator("#jrSteerResearch").wait_for(state="visible", timeout=10000)
            moves = ask(page, "Weekly post ideas")
            assert moves == [{{"href": "/today", "title": "Plan this week’s posts"}}], moves
            # The sample shop's prices are not offered as questions in a seller's own workspace.
            chips = page.locator(".jr-chip-btn").all_inner_texts()
            assert not any("$" in c for c in chips), chips
            moves = ask(page, "How do my prices compare?")
            assert moves == [{{"href": "#loop-research",
                               "title": "Compare prices with a competitor"}}], moves
            assert not errors, errors
            ctx.close()
            browser.close()
        print("STEER_ANSWER_OK")
        """
    )
    proc = subprocess.run(
        [python_bin, "-c", runner_script], capture_output=True, text=True, timeout=180, check=False
    )
    assert proc.returncode == 0, f"STDOUT: {proc.stdout}\nSTDERR: {proc.stderr}"
    assert "STEER_ANSWER_OK" in proc.stdout
