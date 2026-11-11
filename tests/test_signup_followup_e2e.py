"""Browser regression tests for signed-out privacy, 375px auth recovery, and photo export."""

from __future__ import annotations

import os
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

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURE_PHOTO = REPO_ROOT / "tests" / "fixtures" / "product_photo.png"


@pytest.fixture(scope="module")
def live_server_url() -> Iterator[str]:
    """Start an isolated local uvicorn server for browser E2E checks."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()

    config = uvicorn.Config(app=app, host="127.0.0.1", port=port, log_level="warning")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{port}"

    for _ in range(50):
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.1):
                break
        except OSError:
            time.sleep(0.05)
    yield base_url
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


def _run_pw(script: str, *args: str) -> str:
    python_bin = _find_playwright_python()
    if not python_bin:
        pytest.skip("Playwright runtime not installed")
    res = subprocess.run(
        [python_bin, "-c", script, *args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=90,
        check=False,
    )
    assert res.returncode == 0, f"STDOUT:\n{res.stdout}\nSTDERR:\n{res.stderr}"
    return res.stdout


def test_signed_out_privacy_reset_reload_back_and_account_b(
    live_server_url: str, tmp_path: Path
) -> None:
    """Sign-out immediately clears Account A from DOM while preserving owner storage."""
    shot_dir = Path(os.environ.get("MUSE_E2E_SCREENSHOT_DIR", str(tmp_path)))
    shot_dir.mkdir(parents=True, exist_ok=True)
    script = textwrap.dedent(
        """
        import json
        import sys
        from pathlib import Path
        from playwright.sync_api import sync_playwright

        base = sys.argv[1]
        shot_dir = Path(sys.argv[2])

        user_a = {
            "id": "usr-privacy-a",
            "email": "alpha@ceramics.example",
            "email_verified": True,
        }
        user_b = {
            "id": "usr-privacy-b",
            "email": "bespoke@glass.example",
            "email_verified": True,
        }
        doc_a = {
            "onboarding": {
                "business_name": "Alpha Ceramics Studio",
                "shop_urls": ["https://alphaceramics.example"],
                "competitors": [{
                    "name": "Rival Pottery",
                    "url": "https://rivalpottery.example",
                    "reason": "Direct ceramic competitor",
                    "selected": True,
                }],
                "socials": [{
                    "platform": "instagram",
                    "handle": "@alphaceramics",
                    "confirmed": True,
                }],
                "crawl_summary": {"pages_crawled": 7, "price_range": "$38-$120"},
                "completed": True,
                "completed_at": "2026-11-10T10:00:00Z",
            }
        }
        doc_b = {
            "onboarding": {
                "business_name": "Bespoke Glassworks",
                "shop_urls": ["https://bespokeglass.example"],
                "competitors": [],
                "socials": [],
                "crawl_summary": {"pages_crawled": 3, "price_range": "$60-$190"},
                "completed": True,
                "completed_at": "2026-11-10T11:00:00Z",
            }
        }

        state = {"active": "a"}

        def make_me():
            if state["active"] == "a":
                return {
                    "configured": True,
                    "user": user_a,
                    "usage": {"plan": "trial", "used": 0, "limit": 3, "remaining": 3},
                    "live_available": True,
                }
            if state["active"] == "b":
                return {
                    "configured": True,
                    "user": user_b,
                    "usage": {"plan": "trial", "used": 1, "limit": 3, "remaining": 2},
                    "live_available": True,
                }
            return {"configured": True, "user": None, "usage": None, "live_available": False}

        def handle_account(route):
            req = route.request
            url = req.url
            if "/api/v1/account/me" in url:
                route.fulfill(
                    status=200,
                    content_type="application/json",
                    body=json.dumps(make_me()),
                )
                return
            if "/api/v1/account/workspace" in url and req.method == "GET":
                if state["active"] == "a":
                    route.fulfill(
                        status=200,
                        content_type="application/json",
                        body=json.dumps({
                            "document": doc_a,
                            "version": 4,
                            "owner_id": user_a["id"],
                        }),
                    )
                elif state["active"] == "b":
                    route.fulfill(
                        status=200,
                        content_type="application/json",
                        body=json.dumps({
                            "document": doc_b,
                            "version": 2,
                            "owner_id": user_b["id"],
                        }),
                    )
                else:
                    route.fulfill(
                        status=401,
                        content_type="application/json",
                        body=json.dumps({"detail": "Signed out"}),
                    )
                return
            if "/api/v1/account/signout" in url and req.method == "POST":
                state["active"] = None
                route.fulfill(
                    status=200,
                    content_type="application/json",
                    body=json.dumps({"message": "Signed out."}),
                )
                return
            if "/api/v1/account/signin" in url and req.method == "POST":
                payload = json.loads(req.post_data or "{}")
                email = payload.get("email", "")
                state["active"] = "b" if "bespoke" in email else "a"
                route.fulfill(
                    status=200,
                    content_type="application/json",
                    body=json.dumps(make_me()),
                )
                return
            if "/api/v1/preferences/signals" in url:
                route.fulfill(
                    status=200,
                    content_type="application/json",
                    body=json.dumps({"success": True}),
                )
                return
            route.fulfill(status=200, content_type="application/json", body="{}")

        account_a_only_terms = [
            "Alpha Ceramics Studio",
            "alphaceramics.example",
            "Rival Pottery",
            "@alphaceramics",
            "$38-$120",
            "Alpha bowl triage move",
        ]
        private_terms = [*account_a_only_terms, "[live]"]

        def assert_clean_dom(page, stage):
            body_inner = page.locator("body").inner_text()
            body_raw = page.evaluate("() => document.body.textContent || ''")
            for term in private_terms:
                assert term not in body_inner, (
                    f"[{stage}] Private A term {term!r} leaked in visible DOM"
                )
                assert term not in body_raw, (
                    f"[{stage}] Private A term {term!r} leaked in hidden DOM"
                )
            assert page.locator("#loggedOutHero").is_visible(), (
                f"[{stage}] Hero CTA should be visible after sign-out"
            )
            assert page.locator("#ownWorkspaceOptionBtn").count() == 0, (
                f"[{stage}] Switcher still has #ownWorkspaceOptionBtn"
            )

        def wait_for_eyebrow(page, name):
            page.wait_for_function(
                '''(expected) => {
                    const el = document.querySelector('.jr-eyebrow');
                    return el && (el.textContent || '').includes(expected);
                }''',
                arg=name,
            )

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(viewport={"width": 1440, "height": 900})
            page = context.new_page()
            page.route("**/api/v1/account/**", handle_account)
            page.route("**/api/v1/preferences/**", handle_account)

            # Seed owner-bound drafts/actions for Account A before signing in on /
            page.goto(f"{base}/?workspace=sample", wait_until="domcontentloaded")
            page.evaluate(
                '''() => {
                    localStorage.setItem(
                        'muse_onboarding_usr-privacy-a',
                        JSON.stringify({
                            business_name: 'Alpha Ceramics Studio',
                            completed_at: '2026-11-10T10:00:00Z',
                        })
                    );
                    localStorage.setItem(
                        'muse-editor-v1:creator:usr-privacy-a',
                        JSON.stringify({ caption: 'Private Account A Draft' })
                    );
                    localStorage.setItem(
                        'muse.outcomes.usr-privacy-a',
                        JSON.stringify([{ id: 'out-a', revenue: 120 }])
                    );
                    localStorage.setItem(
                        'muse.actions.usr-privacy-a',
                        JSON.stringify({
                            act_alpha: {
                                status: 'accepted',
                                title: 'Alpha bowl triage move',
                                href: '/create',
                            }
                        })
                    );
                    localStorage.removeItem('muse.workspace_mode.v1');
                }'''
            )

            # 1. Load / signed in as Account A and expand full workspace
            page.goto(f"{base}/", wait_until="networkidle")
            wait_for_eyebrow(page, "Alpha Ceramics Studio")
            page.locator("#toggleWorkspace").click()
            page.locator("#heroTitle").wait_for(state="visible")
            assert "Alpha Ceramics Studio" in page.locator("#heroTitle").inner_text()
            assert "Alpha bowl triage move" in page.locator("#myActions").inner_text()
            page.screenshot(path=str(shot_dir / "privacy_account_a_signed_in.png"))

            # 2. Sign out via topbar control -> zero Account A DOM immediately without reload
            page.locator(".ma-signout").click()
            page.wait_for_function(
                "() => !document.querySelector('#loggedOutHero')?.hidden"
            )
            page.wait_for_timeout(150)
            assert_clean_dom(page, "immediate_signout")
            page.screenshot(path=str(shot_dir / "privacy_signed_out_immediate.png"))

            # Verify DOM cleared while owner-bound localStorage drafts remain preserved
            storage = page.evaluate(
                '''() => ({
                    onb_a: localStorage.getItem('muse_onboarding_usr-privacy-a'),
                    draft_a: localStorage.getItem('muse-editor-v1:creator:usr-privacy-a'),
                    outcomes_a: localStorage.getItem('muse.outcomes.usr-privacy-a'),
                    actions_a: localStorage.getItem('muse.actions.usr-privacy-a'),
                    anon_actions: localStorage.getItem('muse.actions'),
                })'''
            )
            assert storage["onb_a"] and "Alpha Ceramics Studio" in storage["onb_a"]
            assert storage["draft_a"] and "Private Account A Draft" in storage["draft_a"]
            assert storage["outcomes_a"] and "out-a" in storage["outcomes_a"]
            assert storage["actions_a"] and "Alpha bowl triage move" in storage["actions_a"]
            assert not (
                storage["anon_actions"]
                and "Alpha bowl triage move" in storage["anon_actions"]
            )

            # 3. Reload while signed out -> zero Account A DOM
            page.reload(wait_until="networkidle")
            assert_clean_dom(page, "reload_signed_out")

            # 4. Back navigation + bfcache pageshow restore after sign-out
            state["active"] = "a"
            page.goto(f"{base}/", wait_until="networkidle")
            wait_for_eyebrow(page, "Alpha Ceramics Studio")
            page.goto(f"{base}/create", wait_until="networkidle")
            page.locator(".ma-signout").click()
            page.wait_for_timeout(100)
            page.go_back(wait_until="networkidle")
            page.evaluate(
                '''() => window.dispatchEvent(
                    new PageTransitionEvent('pageshow', { persisted: true })
                )'''
            )
            page.wait_for_timeout(120)
            assert_clean_dom(page, "back_navigation_after_signout")

            # 5. Sign in as Account B -> sees B, zero A
            page.locator(".ma-account-button").click()
            page.locator("#ma-email").fill("bespoke@glass.example")
            page.locator("#ma-password").fill("bespoke-password-123")
            page.locator("form .ma-primary").click()
            wait_for_eyebrow(page, "Bespoke Glassworks")
            if page.locator("#workspaceDetail").is_hidden():
                page.locator("#toggleWorkspace").click()
            page.locator("#heroTitle").wait_for(state="visible")
            page.wait_for_function(
                '''() => (
                    document.querySelector('#heroTitle')?.textContent || ''
                ).includes('Bespoke Glassworks')'''
            )
            body_b = page.locator("body").inner_text()
            body_b_raw = page.evaluate("() => document.body.textContent || ''")
            for term in account_a_only_terms:
                assert term not in body_b, f"[account_b] Leaked A in text: {term!r}"
                assert term not in body_b_raw, f"[account_b] Leaked A in DOM: {term!r}"
            assert "Bespoke Glassworks" in body_b
            page.screenshot(path=str(shot_dir / "privacy_account_b_signed_in.png"))

            # 6. Mobile 375x667 sign-out check via drawer
            mobile = browser.new_context(viewport={"width": 375, "height": 667})
            mpage = mobile.new_page()
            mpage.route("**/api/v1/account/**", handle_account)
            mpage.route("**/api/v1/preferences/**", handle_account)
            state["active"] = "a"
            mpage.goto(f"{base}/", wait_until="networkidle")
            wait_for_eyebrow(mpage, "Alpha Ceramics Studio")
            mpage.locator(".ms-menu-btn").click()
            mpage.locator("header.ms-nav-open .ma-signout").click()
            mpage.wait_for_function(
                "() => !document.querySelector('#loggedOutHero')?.hidden"
            )
            assert_clean_dom(mpage, "mobile_375_signout")
            mpage.screenshot(path=str(shot_dir / "privacy_mobile_375_signed_out.png"))

            browser.close()
        print("PRIVACY_E2E_OK")
        """
    )
    assert "PRIVACY_E2E_OK" in _run_pw(script, live_server_url, str(shot_dir))


def test_mobile_375_dialog_forgot_password_and_retry_feedback(
    live_server_url: str, tmp_path: Path
) -> None:
    """Verify 375px dialog fit, Forgot password? visibility, 409 switch, and retry feedback."""
    shot_dir = Path(os.environ.get("MUSE_E2E_SCREENSHOT_DIR", str(tmp_path)))
    shot_dir.mkdir(parents=True, exist_ok=True)
    script = textwrap.dedent(
        """
        import json
        import sys
        from pathlib import Path
        from playwright.sync_api import sync_playwright

        base = sys.argv[1]
        shot_dir = Path(sys.argv[2])

        def handle_account(route):
            req = route.request
            url = req.url
            if "/api/v1/account/me" in url:
                route.fulfill(
                    status=200,
                    content_type="application/json",
                    body=json.dumps({
                        "configured": True,
                        "user": None,
                        "usage": None,
                        "live_available": False,
                    }),
                )
                return
            if "/api/v1/account/signup" in url and req.method == "POST":
                route.fulfill(
                    status=409,
                    content_type="application/json",
                    body=json.dumps({
                        "detail": (
                            "Could not create a new account with those details. "
                            "If you already registered, sign in or use Forgot password? below."
                        )
                    }),
                )
                return
            if "/api/v1/account/signin" in url and req.method == "POST":
                route.fulfill(
                    status=401,
                    content_type="application/json",
                    body=json.dumps({"detail": "Invalid email or password."}),
                )
                return
            if "/api/v1/account/recover" in url and req.method == "POST":
                route.fulfill(
                    status=200,
                    content_type="application/json",
                    body=json.dumps({
                        "message": (
                            "If that account exists, check your email for a password reset link."
                        )
                    }),
                )
                return
            route.fulfill(status=200, content_type="application/json", body="{}")

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(viewport={"width": 375, "height": 667})
            page = context.new_page()
            page.route("**/api/v1/account/**", handle_account)

            # Assert /welcome loads synced ?v= assets cleanly
            resp = page.goto(f"{base}/welcome", wait_until="domcontentloaded")
            assert resp.status == 200
            html_welcome = resp.text()
            assert "account.js?v=20261110-fix1" in html_welcome
            assert "account.css?v=20261110-fix1" in html_welcome

            page.goto(f"{base}/", wait_until="networkidle")
            page.locator('[data-hero-primary][data-action="signup"]').click()
            dlg = page.locator(".ma-dialog")
            dlg.wait_for(state="visible")

            # Focus should land on email input instead of .ma-close
            active_id = page.evaluate(
                "() => document.activeElement?.id || document.activeElement?.className"
            )
            assert active_id == "ma-email", f"Expected focus on ma-email, got {active_id}"

            # Active tab & Forgot password? both visible and within viewport on 375x667
            signup_tab_cls = (
                page.locator(".ma-tabs button", has_text="Create account").get_attribute("class")
                or ""
            )
            assert "ma-tab-active" in signup_tab_cls
            recover = page.locator(".ma-recover")
            assert recover.is_visible(), "Forgot password? must be visible on 375px signup dialog"
            metrics = page.evaluate(
                '''() => {
                    const d = document.querySelector('.ma-dialog');
                    const r = document.querySelector('.ma-recover').getBoundingClientRect();
                    return {
                        sh: d.scrollHeight,
                        ch: d.clientHeight,
                        rb: r.bottom,
                        vh: window.innerHeight,
                    };
                }'''
            )
            assert metrics["sh"] <= metrics["ch"] + 2, f"Dialog overflows 375x667: {metrics}"
            assert metrics["rb"] <= metrics["vh"], f"Forgot password clipped: {metrics}"
            page.screenshot(path=str(shot_dir / "mobile_375_signup_dialog.png"))

            # Short password triggers explicit inline validation with email preserved
            page.locator("#ma-email").fill("hermes@example.test")
            page.locator("#ma-password").fill("short")
            page.locator("form .ma-primary").click()
            msg = page.locator(".ma-message").inner_text()
            assert "12 characters" in msg and "(5/12" in msg, f"Unexpected msg: {msg}"
            assert page.locator("#ma-email").input_value() == "hermes@example.test"

            # Duplicate signup 409 auto-switches to Sign in tab with Forgot password? exposed
            page.locator("#ma-password").fill("existing-password-123")
            page.locator("form .ma-primary").click()
            page.wait_for_function(
                "() => document.querySelector('#ma-title')?.textContent === 'Welcome back.'"
            )
            assert page.locator("#ma-email").input_value() == "hermes@example.test"
            signin_tab_cls = (
                page.locator(".ma-tabs button", has_text="Sign in").get_attribute("class") or ""
            )
            assert "ma-tab-active" in signin_tab_cls
            assert recover.is_visible()
            page.screenshot(path=str(shot_dir / "mobile_375_conflict_switched_signin.png"))

            # Retry feedback on failed sign-in increments cleanly
            page.locator("#ma-password").fill("wrong-attempt-password")
            page.locator("form .ma-primary").click()
            page.wait_for_function(
                '''() => (
                    document.querySelector('.ma-message')?.textContent || ''
                ).includes('Attempt')'''
            )
            assert "Attempt" in page.locator(".ma-message").inner_text()

            # Click Forgot password? -> Reset password screen with email still populated
            recover.click()
            assert page.locator("#ma-title").inner_text() == "Reset your password."
            assert page.locator("#ma-email").input_value() == "hermes@example.test"

            browser.close()
        print("MOBILE_DIALOG_E2E_OK")
        """
    )
    assert "MOBILE_DIALOG_E2E_OK" in _run_pw(script, live_server_url, str(shot_dir))


def test_375px_add_photo_action_and_real_fixture_first_export(
    live_server_url: str, tmp_path: Path
) -> None:
    """Blocked export surfaces Add photo; fixture PNG produces exact PNG exports at 375px."""
    assert FIXTURE_PHOTO.is_file(), "Fixture photo missing"
    shot_dir = Path(os.environ.get("MUSE_E2E_SCREENSHOT_DIR", str(tmp_path)))
    shot_dir.mkdir(parents=True, exist_ok=True)
    script = textwrap.dedent(
        """
        import io
        import sys
        from pathlib import Path
        from PIL import Image
        from playwright.sync_api import sync_playwright

        base = sys.argv[1]
        shot_dir = Path(sys.argv[2])
        fixture = sys.argv[3]

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                viewport={"width": 375, "height": 667},
                accept_downloads=True,
            )
            page = context.new_page()

            # Block any paid model calls
            def abort_model(route):
                raise AssertionError(f"Unexpected paid/external call: {route.request.url}")

            page.route("*api.meta.ai*", abort_model)
            page.route("*llama.com*", abort_model)

            # 1. /create at 375px: blocked export surfaces Add photo button
            page.goto(f"{base}/create", wait_until="networkidle")
            assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
            page.locator("#customProduct").click()
            page.locator("#productName").fill("Hand-Thrown Stoneware Bowl")
            assert page.locator("#directPhotoUpload").is_visible()

            page.locator("#nextButton").click()
            add_btn = page.locator("#notice .notice-action-btn")
            add_btn.wait_for(state="visible")
            assert add_btn.inner_text() == "Add photo"
            page.screenshot(
                path=str(shot_dir / "create_375_blocked_add_photo.png"),
                full_page=True,
            )

            # Upload real fixture photo via clickable Add photo CTA inside notice
            with page.expect_file_chooser() as fc_info:
                add_btn.click()
            fc_info.value.set_files(fixture)

            page.wait_for_function(
                '''() => {
                    const img = document.querySelector('#productImage');
                    return img && img.complete && img.naturalWidth > 0;
                }'''
            )
            assert page.locator("#directPhotoUpload").inner_text() == "Change photo"

            # Step 0 -> Step 1 -> Step 2 (original photo) -> Step 3
            page.locator("#nextButton").click()
            page.locator("#nextButton").click()
            page.locator("#originalButton").click()
            assert "Original-photo layout" in page.locator("#sceneLabel").inner_text()
            assert "Original-photo layout" in page.locator("#imageProvenance").inner_text()
            page.locator("#reviewed").check()
            caption_preview = page.locator("#previewCaption").inner_text()
            assert len(caption_preview.strip()) > 10
            page.locator("#nextButton").click()
            page.wait_for_timeout(350)
            assert page.locator("#shareMissingPhoto").is_hidden()
            assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
            page.screenshot(path=str(shot_dir / "create_375_export_ready.png"))

            # Real PNG downloads: verify PNG magic bytes & 1080x1350 / 1080x1920 dimensions
            png_sig = bytes.fromhex("89504e470d0a1a0a")
            with page.expect_download() as dl_feed:
                page.locator("#downloadFeed").click()
            feed_bytes = Path(dl_feed.value.path()).read_bytes()
            assert feed_bytes.startswith(png_sig)
            with Image.open(io.BytesIO(feed_bytes)) as img_f:
                assert img_f.size == (1080, 1350), f"Expected 1080x1350, got {img_f.size}"

            with page.expect_download() as dl_story:
                page.locator("#downloadStory").click()
            story_bytes = Path(dl_story.value.path()).read_bytes()
            assert story_bytes.startswith(png_sig)
            with Image.open(io.BytesIO(story_bytes)) as img_s:
                assert img_s.size == (1080, 1920), f"Expected 1080x1920, got {img_s.size}"

            # 2. /today at 375px: missing photo shows Add photo overlay + notice, then real export
            page.goto(f"{base}/today", wait_until="networkidle")
            assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
            page.locator("#openSetup").click()
            page.locator("#productName").fill("Studio Mug")
            page.locator("#shopUrl").fill("https://example.test/mug")
            page.evaluate(
                '''() => {
                    document.querySelector('#itemForm').dispatchEvent(
                        new Event('submit', { cancelable: true, bubbles: true })
                    );
                }'''
            )
            page.wait_for_timeout(150)
            page.locator("#getPost").click()
            today_add_btn = page.locator("#notice .notice-action-btn")
            today_add_btn.wait_for(state="visible")
            assert page.locator("#noPhotoAddBtn").is_visible()
            page.screenshot(
                path=str(shot_dir / "today_375_blocked_add_photo.png"),
                full_page=True,
            )

            with page.expect_file_chooser() as fc_today:
                page.locator("#noPhotoAddBtn").click()
            fc_today.value.set_files(fixture)
            page.wait_for_function("() => document.querySelector('#noPhoto')?.hidden === true")
            page.locator("details.small-details summary").click()
            page.locator("#useOriginal").click()
            assert "Original image" in page.locator("#imageNote").inner_text()
            page.locator("#reviewed").check()
            assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")

            with page.expect_download() as dl_today:
                page.locator("#getPost").click()
            today_bytes = Path(dl_today.value.path()).read_bytes()
            assert today_bytes.startswith(png_sig)
            with Image.open(io.BytesIO(today_bytes)) as img_t:
                assert img_t.size == (1080, 1350), f"Expected 1080x1350, got {img_t.size}"
            page.screenshot(path=str(shot_dir / "today_375_exported.png"))

            browser.close()
        print("PHOTO_EXPORT_375_E2E_OK")
        """
    )
    assert "PHOTO_EXPORT_375_E2E_OK" in _run_pw(
        script, live_server_url, str(shot_dir), str(FIXTURE_PHOTO)
    )
