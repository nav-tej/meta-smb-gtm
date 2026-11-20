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
    editor_notice, home_notice = notice.split("} else {", 1)
    assert "if (setupPendingEditor) {" in editor_notice
    assert "This page shows a sample shop" in editor_notice
    # The editors work before setup, so their notice keeps a way into the seller's own workspace.
    assert "buildButton('Open my workspace', 'back-to-own', 'secondary')" in editor_notice
    # The dashboard has no workspace of their own to go back to yet.
    assert "This dashboard shows a sample shop" in home_notice
    assert "back-to-own" not in home_notice
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

    # The editors ask only while a signed-in seller views the sample shop, never in their own.
    check = modes[modes.index("async function checkSetupPending(") :]
    check = check[: check.index("\n  }\n")]
    assert "window.museAccount?.loadWorkspace?.(ownerId)" in check
    assert "current().ownerId !== ownerId" in check
    assert "ws.document?.onboarding?.completed_at ? null : ownerId, { editor: true }" in check
    for name in ("today.js", "creator.js"):
        source = (STATIC_DIR / name).read_text(encoding="utf-8")
        call = "if (s.state === 'account_sample') window.museModes?.checkSetupPending?.(s.ownerId);"
        assert source.count(call) == 1, name
        assert source.index("if (s.isSample) {") < source.index(call), name
    # Every other page asks on its own; home and the wizard decide from the workspace they read.
    auto = modes[modes.index("function maybeCheckSetup(") : modes.index("function notify()")]
    assert "s.state !== 'account_sample' && s.state !== 'account_own'" in auto
    assert "mark === 'page'" in auto and "dataset?.setupCheck" in auto
    assert "maybeCheckSetup(resolved);" in modes
    for name in ("index.html", "welcome.html"):
        head = (STATIC_DIR / name).read_text(encoding="utf-8")[:200]
        assert '<html lang="en" data-setup-check="page">' in head, name
    for name in ("first-ad.html", "progress.html", "digest.html"):
        head = (STATIC_DIR / name).read_text(encoding="utf-8")[:300]
        assert "data-setup-check" not in head, name
    # In their own workspace the editors report from the read they already make.
    for name in ("today.html", "creator.html"):
        head = (STATIC_DIR / name).read_text(encoding="utf-8")[:300]
        assert '<html lang="en" data-setup-check="editor">' in head, name
    for name in ("today.js", "creator.js"):
        source = (STATIC_DIR / name).read_text(encoding="utf-8")
        assert source.count("window.museModes?.noteSetup?.(s.ownerId, ws);") == 1, name
    assert "mark === 'editor' && s.state === 'account_own'" in auto
    notice_fn = modes[modes.index("function renderSetupNotice(") : modes.index("function notify()")]
    assert "badge.textContent = 'Setup not finished';" in notice_fn
    assert "buildButton('Finish setup', 'finish-setup', 'primary')" in notice_fn
    assert "—" not in notice_fn

    # The demo hero speaks to a signed-in seller, not a guest.
    index = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
    hero_start = index.index('id="setupHero"')
    setup_hero = index[hero_start : index.index("</section>", hero_start)]
    assert "Finish setup to see your own shop here." in setup_hero
    assert 'href="/welcome"' in setup_hero and "uses none of your runs" in setup_hero
    for guest_only in ("No account needed", "free demo", "sign in", "—"):
        assert guest_only.lower() not in setup_hero.lower(), guest_only
    assert (
        "syncSetupHero(Boolean(setupPending && modeState.isSample), Boolean(modeState.isSample));"
        in home
    )

    # Copy fixes on /today.
    shell = (STATIC_DIR / "muse-shell.js").read_text(encoding="utf-8")
    assert "add your shop website & competitors in Setup or /create" not in shell
    assert "(/today?workspace=sample)" not in shell
    assert "n+α" not in (STATIC_DIR / "today.html").read_text(encoding="utf-8")


def test_dashboard_before_setup_is_an_explicit_demo_e2e(live_server_url: str) -> None:
    python_bin = _find_playwright_python()
    if not python_bin:
        pytest.skip("Playwright runtime not installed")

    from tests.e2e_helpers import with_cpu_throttle

    runner_script = with_cpu_throttle(
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
                # The hero speaks to a signed-in seller and points to setup.
                page.wait_for_selector("#setupHero", state="visible", timeout=10000)
                assert not page.locator("#loggedOutHero").is_visible()
                assert not page.locator(".hero-bridge").is_visible()
                assert page.locator("#setupHeroTitle").inner_text() == (
                    "Finish setup to see your own shop here."
                )
                runs = page.locator("#setupHeroRuns").inner_text()
                assert runs.startswith("3 of 3 runs left"), runs
                assert page.locator("#setupHeroFinishBtn").get_attribute("href") == "/welcome"
                no_overflow(page, "demo dashboard " + str(width))

                # A background account refresh does not throw them out of the demo.
                with page.expect_response(
                    lambda r: r.url.split("?")[0].endswith("/api/v1/account/me")
                ):
                    page.evaluate("window.museAccount.refresh()")
                page.wait_for_function(
                    "(document.getElementById('museModeBanner') || {{dataset: {{}}}})"
                    ".dataset.setup === 'pending'",
                    timeout=15000,
                )
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
            page.goto(BASE + "/", wait_until="domcontentloaded")
            page.wait_for_function(
                "() => document.documentElement.dataset.museMode === 'guest_entry'",
                timeout=15000,
            )
            assert mode(page) == "guest_entry"
            assert page.evaluate(BANNER)["hidden"] is True
            session["signed_in"] = True
            with page.expect_response(
                lambda r: r.url.split("?")[0].endswith("/api/v1/account/me")
            ):
                page.evaluate("window.museAccount.refresh()")
            page.wait_for_url("**/welcome", wait_until="domcontentloaded", timeout=15000)
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
            assert not page.locator("#setupHero").is_visible()
            assert not page.locator("#museSetupNotice").is_visible()

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
            assert page.locator("#loggedOutHero").is_visible()
            assert not page.locator("#setupHero").is_visible()
            assert not errors, errors
            ctx.close()

            #    Signing out of the demo brings the guest hero back.
            ctx, page, session, errors = open_page(browser)
            page.goto(BASE + "/", wait_until="domcontentloaded")
            page.wait_for_selector("#setupHero", state="visible", timeout=15000)
            session["signed_in"] = False
            page.evaluate("window.museAccount.refresh()")
            page.wait_for_selector("#loggedOutHero", state="visible", timeout=10000)
            assert not page.locator("#setupHero").is_visible()
            assert page.locator(".hero-bridge").is_visible()
            assert not errors, errors
            ctx.close()

            # 8. Opened directly before setup, a page in the seller's own workspace says setup is
            #    not finished. Sellers who finished setup see nothing extra.
            for page_path, width in (("/today", 375), ("/first-ad", 1440), ("/digest", 375)):
                for onboarding, expect in ((None, True), (DONE, False)):
                    ctx, page, session, errors = open_page(
                        browser, width=width, onboarding=onboarding
                    )
                    with page.expect_response(lambda r: "/api/v1/account/workspace" in r.url):
                        page.goto(BASE + page_path, wait_until="domcontentloaded")
                    page.wait_for_timeout(700)
                    label = page_path + " " + str(width) + " setup_pending=" + str(expect)
                    assert mode(page) == "account_own", label
                    assert page.evaluate(BANNER)["hidden"] is True, label
                    notice = page.locator("#museSetupNotice")
                    assert notice.is_visible() is expect, label
                    if expect:
                        assert notice.locator(".muse-mode-badge").inner_text().lower() == (
                            "setup not finished"
                        ), label
                        prev = page.evaluate(
                            "document.getElementById('museSetupNotice').previousElementSibling"
                            "?.matches('body > header') || false"
                        )
                        top = page.evaluate(
                            "Math.round(document.getElementById('museSetupNotice')"
                            ".getBoundingClientRect().top)"
                        )
                        assert prev or top < 5, (label, top)
                        no_overflow(page, label)
                        if page_path == "/digest":
                            notice.locator("button").click()
                            page.wait_for_url("**/welcome", wait_until="domcontentloaded")
                    assert not errors, (label, errors)
                    ctx.close()

            # 6. The editors say the same thing before setup, and keep a way into the seller's
            #    own workspace, since /today and /create work without setup.
            for page_path, width in (("/today", 375), ("/create", 1440), ("/today", 1440)):
                ctx, page, session, errors = open_page(browser, width=width)
                page.goto(BASE + page_path + "?workspace=sample", wait_until="domcontentloaded")
                page.wait_for_function(
                    "(document.getElementById('museModeBanner') || {{dataset: {{}}}})"
                    ".dataset.setup === 'pending'",
                    timeout=15000,
                )
                label = page_path + " " + str(width)
                assert mode(page) == "account_sample", label
                banner = page.evaluate(BANNER)
                assert banner["badge"] == "Demo data", label
                assert "This page shows a sample shop, Art of Sarabjit Singh, not yours" in (
                    banner["text"]
                ), label
                assert banner["buttons"] == ["Finish setup", "Open my workspace"], banner
                assert banner["top"] < 250, (label, banner["top"])
                assert page.locator("#museModeBanner").is_visible(), label
                no_overflow(page, "demo " + label)
                if width == 375 or page_path == "/create":
                    page.locator("#museModeBanner button", has_text="Finish setup").click()
                    page.wait_for_url("**/welcome", wait_until="domcontentloaded")
                else:
                    page.locator("#museModeBanner button", has_text="Open my workspace").click()
                    page.wait_for_function(
                        "document.documentElement.dataset.museMode === 'account_own'",
                        timeout=10000,
                    )
                    assert "workspace=sample" not in page.url, page.url
                    assert page.evaluate(BANNER)["hidden"] is True
                assert not errors, (label, errors)
                ctx.close()

            # 7. The other pages that show the sample say the same, with no page-specific code.
            for page_path, width in (("/first-ad", 375), ("/progress", 1440), ("/digest", 375)):
                ctx, page, session, errors = open_page(browser, width=width)
                page.goto(BASE + page_path + "?workspace=sample", wait_until="domcontentloaded")
                page.wait_for_function(
                    "(document.getElementById('museModeBanner') || {{dataset: {{}}}})"
                    ".dataset.setup === 'pending'",
                    timeout=15000,
                )
                label = page_path + " " + str(width)
                banner = page.evaluate(BANNER)
                assert banner["badge"] == "Demo data", (label, banner)
                assert banner["buttons"] == ["Finish setup", "Open my workspace"], (label, banner)
                assert page.locator("#museModeBanner").is_visible(), label
                no_overflow(page, "demo " + label)
                assert not errors, (label, errors)
                ctx.close()

            #    Setup finished: the editors show the ordinary sample notice.
            for page_path in ("/today", "/create"):
                ctx, page, session, errors = open_page(browser, onboarding=DONE)
                with page.expect_response(lambda r: "/api/v1/account/workspace" in r.url):
                    page.goto(BASE + page_path + "?workspace=sample", wait_until="domcontentloaded")
                page.wait_for_timeout(500)
                banner = page.evaluate(BANNER)
                assert banner["state"] == "account_sample", (page_path, banner)
                assert banner["setup"] is None and banner["badge"] == "Sample shop", banner
                assert banner["buttons"] == ["Back to my workspace"], banner
                assert not errors, (page_path, errors)
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
