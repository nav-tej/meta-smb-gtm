"""/today's daily brief and draft row fit visitors, the seller's own workspace and the sample shop.

Before pass 14 every state got the sample's header ("What changed at the shops you watch"), three
empty columns and a Re-check button. A setup prompt carried Accept, Dismiss, Archive and Adjust
buttons that were keyed to whatever title was on screen when the page loaded, so a choice on the
sample's focus could be stored under "Preparing your daily workspace". The draft buttons were
unstyled browser buttons above the page, "Checking device draft…" never went away, and on a phone
an empty 4:5 photo frame pushed the editor far down.

Now only the sample shop gets the full brief and triage, keyed to the idea on screen. The own
workspace and signed-out visitors get a short, honest card whose links open the sample brief or
jump to the editor. The draft row sits under the post actions, says where the draft lives, and
offers account saving and recovery only when they apply.
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

from src.api.main import app


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


def test_today_brief_and_draft_row_fit_each_state_e2e(live_server_url: str) -> None:
    python_bin = _find_playwright_python()
    if not python_bin:
        pytest.skip("Playwright runtime not installed")

    runner_script = textwrap.dedent(
        f"""
        import json, re
        from playwright.sync_api import sync_playwright

        BASE = "{live_server_url}"
        USER = {{"id": "u-brief", "email": "owner@northstar.example", "email_verified": True}}
        ONB = {{"business_name": "North Star Advisory", "shop_urls": ["https://northstar.example/"],
               "business_type": "services", "completed_at": "2026-11-18T18:00:00Z",
               "used_run": False}}
        ACCOUNT_BUTTONS = ["saveAccountDraft", "loadAccountDraft", "downloadDraft"]
        BAD_WORDS = re.compile(r"—|storefront &|Checking device draft", re.I)

        def open_page(browser, width, user):
            ctx = browser.new_context(viewport={{"width": width, "height": 900}})
            page = ctx.new_page()
            errors = []
            page.on("pageerror", lambda e: errors.append(str(e)))

            def handle(route):
                url = route.request.url.split("?")[0]
                body = None
                if url.endswith("/api/v1/account/me"):
                    body = {{"configured": True, "user": user,
                            "usage": {{"plan": "trial", "used": 0, "limit": 3, "remaining": 3,
                                      "resets_at": None}} if user else None,
                            "live_available": bool(user)}}
                elif "/api/v1/account/workspace" in url and user:
                    body = {{"document": {{"onboarding": ONB}}, "version": 1,
                            "owner_id": user["id"], "listing_import": {{"first_visit": True}}}}
                elif url.endswith("/api/v1/seller-memory") and user:
                    body = {{"authenticated": True, "owner_id": user["id"], "version": 1,
                            "business_name": ONB["business_name"], "business_type": "services",
                            "preferences": {{}}, "voice_profile": {{}}, "memory_entries": [],
                            "competitor_entries": [], "suggested_updates": [],
                            "dismiss_signals": []}}
                elif url.endswith("/api/v1/ingest-storefront"):
                    body = {{"discovered_catalog_items": []}}
                if body is None:
                    return route.continue_()
                route.fulfill(status=200, content_type="application/json", body=json.dumps(body))

            page.route("**/api/v1/**", handle)
            page.route(lambda u: not u.startswith(BASE) and not u.startswith("data:"),
                       lambda r: r.abort())
            return ctx, page, errors

        def settled(page, title):
            page.wait_for_function(
                "(t) => document.getElementById('msBriefTitle')?.textContent === t"
                " && !document.getElementById('msBrief').classList.contains('ms-loading')",
                arg=title, timeout=15000)
            # The draft row replaces the page's default line once the editor knows its workspace.
            page.wait_for_function(
                "document.getElementById('draftStatus').textContent"
                " !== 'Your draft is kept on this device as you edit.'", timeout=10000)

        def visible(page, selector):
            return page.locator(selector).first.is_visible()

        def draft_row(page):
            return page.evaluate(\"\"\"() => {{
                const row = document.querySelector('.editor .draft-storage');
                const buttons = row ? [...row.querySelectorAll('button')] : [];
                return {{
                    inEditor: Boolean(row),
                    beforeIntro: Boolean(
                        document.querySelector('main > section[aria-label="Draft storage"]')),
                    status: document.getElementById('draftStatus').textContent,
                    shown: buttons.filter(b => b.offsetParent).map(b => b.id),
                    unstyled: buttons.filter(b => getComputedStyle(b).borderStyle === 'outset')
                        .map(b => b.id),
                }};
            }}\"\"\")

        def move_key(page):
            # The focus card's key must come from the idea on screen, not the loading title.
            return page.evaluate(\"\"\"() => {{
                const move = document.querySelector('#msBrief .ms-move');
                const t = move.querySelector('strong').textContent.trim()
                    .replace(/\\\\s+/g, ' ').slice(0, 120);
                let h = 0; for (const ch of t) h = (h * 31 + ch.charCodeAt(0)) | 0;
                return [move.dataset.actionId || '', 'a' + (h >>> 0).toString(36), t];
            }}\"\"\")

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            for width in (375, 1440):
                # 1. Signed out: a short card that opens the sample brief, no triage, no columns.
                ctx, page, errors = open_page(browser, width, None)
                page.goto(BASE + "/today", wait_until="networkidle")
                settled(page, "See what a daily brief looks like")
                assert page.locator("#msBrief .ms-triage").count() == 0
                assert not visible(page, "#msBrief .ms-brief-columns")
                assert not page.get_by_role("button", name="Re-check now").is_visible()
                go = page.locator("#msBrief .ms-move-links a").first
                assert go.inner_text() == "Open the sample brief →"
                assert go.get_attribute("href") == "/today?workspace=sample"
                alt = page.locator("#msBrief .ms-move-alt").inner_text()
                assert alt == "Or start my own post ↓", alt
                row = draft_row(page)
                assert row["inEditor"] and not row["beforeIntro"], row
                assert row["status"] == ("Your draft is kept on this device as you edit."
                                         " Sign in to save it to an account."), row
                assert row["shown"] == ACCOUNT_BUTTONS, row
                assert row["unstyled"] == [], row
                brief = page.locator("#msBrief").inner_text()
                assert not BAD_WORDS.search(brief + row["status"]), brief
                if width == 375:
                    # No photo yet: no empty 4:5 frame and no crop controls on a phone.
                    assert visible(page, "#noPhoto")
                    assert not visible(page, "#postCanvas")
                    assert not visible(page, "#todayFrameControls")
                assert not page.evaluate(
                    "document.documentElement.scrollWidth > document.documentElement.clientWidth")
                # The card's main link really opens the sample brief.
                go.click()
                settled(page, "What changed at the shops you watch")
                assert not errors, errors
                ctx.close()

                # 2. Own workspace: honest header, links to the editor and the sample brief.
                ctx, page, errors = open_page(browser, width, USER)
                page.goto(BASE + "/today", wait_until="networkidle")
                settled(page, "Your shop’s brief is not built yet")
                page.wait_for_function(
                    "document.getElementById('itemTitle').textContent"
                    " === 'North Star Advisory · choose a service or offer'", timeout=15000)
                assert page.locator("#msBrief .ms-triage").count() == 0
                assert not visible(page, "#msBrief .ms-brief-columns")
                assert not page.get_by_role("button", name="Re-check now").is_visible()
                assert page.locator("#msBrief .ms-move-alt").inner_text() == "See a sample brief"
                row = draft_row(page)
                assert row["status"] == ("Your draft is kept on this device as you edit."
                                         " Save to account to open it on another device."), row
                assert row["shown"] == ACCOUNT_BUTTONS, row
                assert page.locator("label:has(#saveShopWebsite)").inner_text().strip() == (
                    "Remember this as my website when I find items")
                assert page.locator("#saveWebsiteOnlyBtn").inner_text() == "Save website only"
                assert not BAD_WORDS.search(page.locator("#msBrief").inner_text())
                go = page.locator("#msBrief .ms-move-links a").first
                assert go.inner_text() == "Start today’s post ↓"
                go.click()
                page.wait_for_function(
                    "document.activeElement && document.activeElement.id === 'quickShopUrl'",
                    timeout=5000)
                page.wait_for_function(
                    "(() => {{ const r = document.getElementById('todayWebsiteBar')"
                    ".getBoundingClientRect();"
                    " return r.top >= -2 && r.top < innerHeight / 2; }})()",
                    timeout=5000)
                assert not errors, errors
                ctx.close()

                # 3. Sample shop: the full brief, triage keyed to the idea on screen.
                ctx, page, errors = open_page(browser, width, None)
                page.goto(BASE + "/today?workspace=sample", wait_until="networkidle")
                settled(page, "What changed at the shops you watch")
                assert visible(page, "#msBrief .ms-brief-columns")
                assert page.get_by_role("button", name="Re-check now").is_visible()
                assert page.locator("#msBrief .ms-move .ms-triage button").count() == 4
                key, expected, title = move_key(page)
                assert key == expected, (key, expected, title)
                row = draft_row(page)
                assert row["status"] == (
                    "Sample shop drafts stay on this device and never mix with your own."), row
                assert row["shown"] == ["downloadDraft"], row
                page.locator("#msBrief .ms-move .ms-triage-accept").click()
                assert page.locator("#msBrief .ms-move .ms-triage-accept").inner_text() == (
                    "✓ In My actions")
                stored = page.evaluate(
                    "Object.entries(localStorage).filter(([k]) => k.includes('muse.actions'))"
                    ".map(([, v]) => JSON.parse(v))")
                assert any(key in e and e[key]["title"] == title for e in stored), stored
                assert not errors, errors
                ctx.close()
            browser.close()
        print("TODAY_BRIEF_STATES_OK")
        """
    )
    proc = subprocess.run(
        [python_bin, "-c", runner_script], capture_output=True, text=True, timeout=300, check=False
    )
    assert proc.returncode == 0, f"STDOUT: {proc.stdout}\nSTDERR: {proc.stderr}"
    assert "TODAY_BRIEF_STATES_OK" in proc.stdout
