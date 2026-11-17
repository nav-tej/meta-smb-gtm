"""A signed-in seller who has not finished setup can see the dashboard, as an explicit demo.

The home page used to send them straight back to the setup wizard, so there was no way to look
at the dashboard first. It now shows the sample shop, says plainly that the data is a demo and
not theirs, and points to the wizard. Arriving from sign-in still goes to the wizard, and
nothing changes for guests or for sellers who finished setup.
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

    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error")
    server = uvicorn.Server(config)
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


def test_demo_notice_copy_and_wiring() -> None:
    modes = (STATIC_DIR / "workspace-modes.js").read_text(encoding="utf-8")
    start = modes.index("} else if (setupPending) {")
    notice = modes[start : modes.index("} else if (s.state === 'account_sample') {", start)]
    assert "badge.textContent = 'Demo data';" in notice
    assert "a sample shop, Art of Sarabjit Singh, not yours" in notice
    assert "Finish setup to see your own shop and competitors here." in notice
    assert "buildButton('Finish setup', 'finish-setup', 'primary')" in notice
    # There is no workspace of their own to go back to yet.
    assert "back-to-own" not in notice
    assert "—" not in notice
    assert "window.location.assign('/welcome');" in modes
    # Only for the account a page has actually checked, and only while it views the sample.
    assert "s.state === 'account_sample' && s.ownerId === setupPendingOwner" in modes

    home = (STATIC_DIR / "welcome.js").read_text(encoding="utf-8")
    start = home.index("async function applyHomeModeState(")
    rule = home[start : home.index("if (modeState.isSample) {", start)]
    # Sign-in landings still go to the wizard; the demo is for coming back to the dashboard.
    assert "window.location.pathname === '/account' || query.has('oauth')" in rule
    assert "homeSawSignedOut" in rule
    assert "window.museModes.enterSampleMode()" in rule
    assert "setSetupPending?.(setupPending ? server.user.id : null)" in rule


def test_dashboard_before_setup_is_an_explicit_demo_e2e(live_server_url: str) -> None:
    python_bin = _find_playwright_python()
    if not python_bin:
        pytest.skip("Playwright runtime not installed")

    runner_script = textwrap.dedent(
        f"""
        import json
        from playwright.sync_api import sync_playwright

        BASE = "{live_server_url}"
        USER = {{"id": "u-new-21", "email": "maker@mountainpottery.example",
                "email_verified": True}}
        DONE = {{
            "business_name": "Mountain Pottery Studio",
            "shop_urls": ["https://mountainpottery.example/"],
            "competitors": [{{"name": "Desert Ceramics", "url": "https://desertceramics.example",
                             "reason": "Similar stoneware"}}],
            "completed_at": "2026-11-16T18:00:00Z",
            "used_run": False,
        }}

        def reply(route, payload):
            route.fulfill(status=200, content_type="application/json", body=json.dumps(payload))

        def open_page(browser, width=1440, signed_in=True, onboarding=None):
            ctx = browser.new_context(viewport={{"width": width, "height": 900}})
            page = ctx.new_page()
            session = {{"signed_in": signed_in, "outside": []}}
            errors = []
            page.on("pageerror", lambda e: errors.append(str(e)))

            def handle(route):
                url = route.request.url.split("?")[0]
                if url.endswith("/api/v1/account/me"):
                    if not session["signed_in"]:
                        return reply(route, {{"configured": True, "user": None, "usage": None,
                                             "live_available": False}})
                    return reply(route, {{
                        "configured": True, "user": USER,
                        "usage": {{"plan": "trial", "used": 0, "limit": 3, "remaining": 3,
                                  "resets_at": None}},
                        "live_available": True,
                    }})
                if "/api/v1/account/workspace" in url:
                    document = {{"onboarding": onboarding}} if onboarding else {{}}
                    return reply(route, {{"document": document, "version": 1,
                                         "owner_id": USER["id"]}})
                if url.endswith("/api/v1/onboarding/status"):
                    return reply(route, {{
                        "authenticated": True, "completed": bool(onboarding),
                        "completed_at": (onboarding or {{}}).get("completed_at"),
                        "used_run": False, "runs_remaining": 3,
                    }})
                return route.continue_()

            page.route("**/api/v1/**", handle)
            page.route(
                lambda url: not url.startswith(BASE) and not url.startswith("data:"),
                lambda route: (session["outside"].append(route.request.url), route.abort()),
            )
            return ctx, page, session, errors

        BANNER = '''(() => {{
            const b = document.getElementById('museModeBanner');
            if (!b) return null;
            const prev = b.previousElementSibling;
            return {{
                hidden: b.hidden,
                state: b.dataset.modeState,
                setup: b.dataset.setup || null,
                badge: (b.querySelector('.muse-mode-badge') || {{}}).textContent || '',
                text: (b.querySelector('.muse-mode-text') || {{}}).textContent || '',
                buttons: Array.from(b.querySelectorAll('button')).map((x) => x.textContent),
                underHeader: Boolean(prev && prev.matches('body > header')),
                top: Math.round(b.getBoundingClientRect().top),
            }};
        }})()'''

        def mode(page):
            return page.evaluate("document.documentElement.dataset.museMode")

        def path(page):
            return page.url.replace(BASE, "")

        def no_overflow(page, label):
            assert not page.evaluate(
                "document.documentElement.scrollWidth > document.documentElement.clientWidth"
            ), "Horizontal overflow on " + label

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)

            # 1. Signed in, setup not finished, opens the dashboard: an explicit demo, not a
            #    bounce to the wizard. The notice is the first thing under the page header.
            for width in (1440, 375):
                ctx, page, session, errors = open_page(browser, width=width)
                page.goto(BASE + "/", wait_until="domcontentloaded")
                page.wait_for_function(
                    "(document.getElementById('museModeBanner') || {{dataset: {{}}}})"
                    ".dataset.setup === 'pending'",
                    timeout=15000,
                )
                assert path(page) == "/?workspace=sample", path(page)
                assert mode(page) == "account_sample"
                banner = page.evaluate(BANNER)
                assert banner["hidden"] is False and banner["state"] == "account_sample"
                assert banner["badge"] == "Demo data"
                assert "sample shop, Art of Sarabjit Singh, not yours" in banner["text"]
                assert "Finish setup to see your own shop and competitors here." in banner["text"]
                assert banner["buttons"] == ["Finish setup"], banner["buttons"]
                assert banner["underHeader"] is True
                assert banner["top"] < 200, banner["top"]
                assert page.locator("#museModeBanner").is_visible()
                label = page.locator("#activeWorkspaceLabel").inner_text()
                assert "Sample shop" in label, label
                # The seller's own (empty) workspace is not what is on screen.
                assert "Mountain Pottery" not in page.locator("body").inner_text()
                no_overflow(page, "demo dashboard " + str(width))

                # A background account refresh does not throw them out of the demo.
                page.evaluate("window.museAccount.refresh()")
                page.wait_for_timeout(600)
                assert path(page) == "/?workspace=sample", path(page)
                assert page.evaluate(BANNER)["setup"] == "pending"

                page.locator("#museModeBanner button").click()
                page.wait_for_url("**/welcome", wait_until="domcontentloaded")
                page.wait_for_selector("#wkStep1:not([hidden])", timeout=10000)
                assert not errors, errors
                assert not session["outside"], session["outside"]
                ctx.close()

            # 2. The workspace switcher does not offer a workspace that does not exist yet.
            ctx, page, session, errors = open_page(browser)
            page.goto(BASE + "/?workspace=sample", wait_until="domcontentloaded")
            page.wait_for_selector("#ownWorkspaceOptionBtn", state="attached", timeout=15000)
            assert page.evaluate(BANNER)["setup"] == "pending"
            option = page.locator("#ownWorkspaceOptionBtn").text_content()
            assert "Finish setup to open your own workspace." in option, option
            assert "Your shop" not in option, option
            page.evaluate("document.getElementById('ownWorkspaceOptionBtn').click()")
            page.wait_for_url("**/welcome", wait_until="domcontentloaded")
            assert not errors, errors
            ctx.close()

            # 3. Arriving from sign-in still goes to the wizard: the /account landing...
            ctx, page, session, errors = open_page(browser)
            page.goto(BASE + "/account", wait_until="domcontentloaded")
            page.wait_for_url("**/welcome", wait_until="domcontentloaded")
            ctx.close()

            #    ...and signing in on the dashboard itself.
            ctx, page, session, errors = open_page(browser, signed_in=False)
            page.goto(BASE + "/", wait_until="networkidle")
            assert mode(page) == "guest_entry"
            assert page.evaluate(BANNER)["hidden"] is True
            session["signed_in"] = True
            page.evaluate("window.museAccount.refresh()")
            page.wait_for_url("**/welcome", wait_until="domcontentloaded")
            ctx.close()

            # 4. Setup finished: the seller's own dashboard, with no demo notice.
            ctx, page, session, errors = open_page(browser, onboarding=DONE)
            page.goto(BASE + "/", wait_until="networkidle")
            page.wait_for_function(
                "document.getElementById('activeWorkspaceLabel').textContent"
                " === 'Mountain Pottery Studio'",
                timeout=15000,
            )
            assert path(page) == "/", path(page)
            assert mode(page) == "account_own"
            banner = page.evaluate(BANNER)
            assert banner["hidden"] is True and banner["setup"] is None

            #    Looking at the sample shop from there is the ordinary sample view.
            page.goto(BASE + "/?workspace=sample", wait_until="networkidle")
            page.wait_for_selector("#ownWorkspaceOptionBtn", state="attached", timeout=15000)
            banner = page.evaluate(BANNER)
            assert banner["setup"] is None and banner["badge"] == "Sample shop"
            assert banner["buttons"] == ["Back to my workspace"], banner["buttons"]
            assert banner["underHeader"] is False
            option = page.locator("#ownWorkspaceOptionBtn").text_content()
            assert "Your shop" in option and "Finish setup" not in option, option
            assert not errors, errors
            ctx.close()

            # 5. Guests see the sample shop exactly as before.
            ctx, page, session, errors = open_page(browser, signed_in=False)
            page.goto(BASE + "/?workspace=sample", wait_until="networkidle")
            assert mode(page) == "guest_sample"
            banner = page.evaluate(BANNER)
            assert banner["hidden"] is False and banner["setup"] is None
            assert banner["badge"] == "Sample shop example"
            assert banner["underHeader"] is False
            assert "Finish setup" not in banner["buttons"]
            assert not errors, errors
            ctx.close()

            browser.close()
        print("SETUP_DEMO_STATE_OK")
        """
    )

    proc = subprocess.run(
        [python_bin, "-c", runner_script],
        capture_output=True,
        text=True,
        timeout=180,
        check=False,
    )
    assert proc.returncode == 0, (
        f"Playwright script failed:\nSTDOUT: {proc.stdout}\nSTDERR: {proc.stderr}"
    )
    assert "SETUP_DEMO_STATE_OK" in proc.stdout
