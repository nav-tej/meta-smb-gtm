"""SEO head block, share assets, and Track G digest habit front-end test.

Verifies:
1. Canonical, meta description, robots, OG and Twitter tags on /, /today, /create, /digest.
2. og-cover.png exists with 1200x630 dimensions.
3. noindex on /welcome.
4. /digest frequency (weekly/biweekly) and topics (prices/listings/ideas) controls.
5. /digest account gate (no free-text email input, requires account, shows runs left).
6. Home page inline digest prompt card at value moments in #loop-improve.
7. Browser E2E at 375px and 1440px with zero model calls.
"""

from __future__ import annotations

import shutil
import socket
import subprocess
import sys
import textwrap
import threading
from collections.abc import Iterator
from pathlib import Path

import pytest
import uvicorn
from fastapi.testclient import TestClient
from PIL import Image

from src.api.main import app

REPO_ROOT = Path(__file__).resolve().parent.parent
STATIC_DIR = REPO_ROOT / "src" / "api" / "static"


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


@pytest.fixture(scope="module")
def live_server_url() -> Iterator[str]:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()

    config = uvicorn.Config(app=app, host="127.0.0.1", port=port, log_level="warning")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    base_url = f"http://127.0.0.1:{port}"
    import time

    for _ in range(50):
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.1):
                break
        except OSError:
            time.sleep(0.05)
    yield base_url
    server.should_exit = True


def test_og_cover_image_properties() -> None:
    """Verify og-cover.png exists and meets OpenGraph specifications (1200x630)."""
    cover_path = STATIC_DIR / "og-cover.png"
    assert cover_path.is_file(), "og-cover.png must exist in static directory"
    with Image.open(cover_path) as im:
        assert im.format == "PNG", f"Expected PNG, got {im.format}"
        assert im.size == (1200, 630), f"Expected (1200, 630), got {im.size}"


def test_seo_meta_tags_contract() -> None:
    """Verify title, meta descriptions, canonical, and robots directives on key pages."""
    client = TestClient(app)

    # 1. Home page (/)
    home_resp = client.get("/")
    assert home_resp.status_code == 200
    home_html = home_resp.text
    expected_title = "<title>Muse Growth Studio | AI marketing help for makers and artists</title>"
    assert expected_title in home_html
    assert 'name="description"' in home_html
    assert 'content="https://meta-smb-gtm.vercel.app/static/og-cover.png"' in home_html
    assert 'content="1200"' in home_html
    assert 'content="630"' in home_html
    assert 'name="twitter:card" content="summary_large_image"' in home_html
    assert 'href="https://meta-smb-gtm.vercel.app/"' in home_html
    assert '<script type="application/ld+json">' in home_html

    # 2. Today page (/today)
    today_resp = client.get("/today")
    assert today_resp.status_code == 200
    today_html = today_resp.text
    assert "<title>Daily Post Studio | Muse Growth Studio</title>" in today_html
    assert '<link rel="canonical" href="https://meta-smb-gtm.vercel.app/today">' in today_html
    assert '<meta name="robots" content="index, follow">' in today_html

    # 3. Creator page (/create)
    create_resp = client.get("/create")
    assert create_resp.status_code == 200
    create_html = create_resp.text
    assert "<title>Create Your Next Shop Post | Muse Growth Studio</title>" in create_html
    assert '<link rel="canonical" href="https://meta-smb-gtm.vercel.app/create">' in create_html
    assert '<meta name="robots" content="index, follow">' in create_html

    # 4. Digest page (/digest)
    digest_resp = client.get("/digest")
    assert digest_resp.status_code == 200
    digest_html = digest_resp.text
    expected_digest_title = (
        "<title>Weekly competitor digest for small shops | Muse Growth Studio</title>"
    )
    assert expected_digest_title in digest_html
    assert '<link rel="canonical" href="https://meta-smb-gtm.vercel.app/digest">' in digest_html

    # 5. Welcome onboarding page (/welcome) - must have noindex
    welcome_resp = client.get("/welcome")
    assert welcome_resp.status_code == 200
    welcome_html = welcome_resp.text
    assert '<meta name="robots" content="noindex"' in welcome_html


def test_digest_controls_and_account_requirement() -> None:
    """Verify /digest provides frequency, topic controls and enforces Revision 4 rules."""
    client = TestClient(app)
    resp = client.get("/digest")
    assert resp.status_code == 200
    html = resp.text

    # Account gate and info containers
    assert 'id="digestAccountGate"' in html
    assert 'id="digestAccountInfo"' in html
    assert 'id="digestSignInBtn"' in html
    assert "A free Muse account is required to subscribe" in html

    # Revision 4: No free-text email input
    assert 'type="email"' not in html
    assert 'id="digestHiddenEmail"' in html

    # Frequency selector
    assert 'id="digestFrequency"' in html
    assert 'value="weekly"' in html
    assert 'value="biweekly"' in html

    # Topic checkboxes
    assert 'value="prices"' in html
    assert 'value="listings"' in html
    assert 'value="ideas"' in html


@pytest.mark.parametrize("viewport_width", [375, 1440])
def test_digest_and_home_habit_browser_ui(live_server_url: str, viewport_width: int) -> None:
    """Browser verification: signed-out gate, signed-in controls, and home page prompt."""
    pw_python = _find_playwright_python()
    if pw_python is None:
        pytest.skip("Playwright Python runtime unavailable")

    runner_code = textwrap.dedent(
        f"""
        from playwright.sync_api import sync_playwright

        live_server_url = {live_server_url!r}
        viewport_width = {viewport_width}
        model_called = False

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(viewport={{"width": viewport_width, "height": 900}})
            page = context.new_page()

            def handle_model(route):
                global model_called
                model_called = True
                route.abort()

            page.route("*api.meta.ai*", handle_model)
            page.route("*llama.com*", handle_model)

            # Ensure subscription is enabled for testing
            page.route(
                "**/api/v1/digest/subscription",
                lambda r: r.fulfill(json={{"available": True}})
            )

            # -------------------------------------------------------------
            # 1. Test /digest in signed-out state: account gate shown
            # -------------------------------------------------------------
            page.goto(f"{{live_server_url}}/digest", wait_until="domcontentloaded")
            page.wait_for_selector("#digestSignup:not([hidden])")
            page.wait_for_selector("#digestAccountGate:not([hidden])")
            assert page.is_visible("#digestSignInBtn")
            assert not page.is_visible("#digestSignupForm")

            # -------------------------------------------------------------
            # 2. Test /digest in signed-in state: form and controls revealed
            # -------------------------------------------------------------
            # Intercept account session as signed in (with onboarding completed)
            fake_user = {{
                "configured": True,
                "user": {{
                    "id": "usr_maker_123",
                    "email": "artist@handmade.shop",
                    "email_verified": True
                }},
                "usage": {{"plan": "starter", "remaining": 3, "limit": 20}},
                "workspace": {{"onboarding": {{"completed_at": "2026-11-09T00:00:00Z"}}}},
                "live_available": True
            }}
            page.route("**/api/v1/account/me", lambda r: r.fulfill(json=fake_user))
            fake_ws = {{
                "version": 1,
                "document": {{
                    "onboarding": {{
                        "completed_at": "2026-11-09T00:00:00Z",
                        "shop_urls": ["https://myart.com"],
                        "competitors": ["https://www.sikhiart.com"],
                    }}
                }}
            }}
            page.route("**/api/v1/account/workspace*", lambda r: r.fulfill(json=fake_ws))
            page.goto(f"{{live_server_url}}/digest", wait_until="domcontentloaded")
            page.wait_for_selector("#digestSignupForm:not([hidden])")
            page.wait_for_selector("#digestAccountInfo:not([hidden])")

            info_text = page.locator("#digestAccountInfo").inner_text()
            assert "artist@handmade.shop" in info_text
            assert "3 runs remaining" in info_text

            # Verify frequency select and topic checkboxes
            freq = page.locator("#digestFrequency")
            assert freq.input_value() == "weekly"
            freq.select_option("biweekly")
            assert freq.input_value() == "biweekly"

            topics = page.locator('input[name="topic"]')
            assert topics.count() == 3

            # -------------------------------------------------------------
            # 3. Test home page inline digest habit prompt (#jrDigestPrompt)
            # -------------------------------------------------------------
            page.goto(
                f"{{live_server_url}}/?workspace=sample#loop-improve",
                wait_until="domcontentloaded"
            )
            page.wait_for_selector("#jrDigestPrompt")
            prompt_text = page.locator("#jrDigestPrompt").inner_text()
            assert (
                "Get this research in your inbox every Monday" in prompt_text
                or "Get your competitor digest" in prompt_text
            )

            # Verify preview modal contains link to /digest
            page.wait_for_selector(".jr-reco-thumb")
            page.locator(".jr-reco-thumb").first.click()
            page.wait_for_selector("#jrPreviewModal[open]")
            modal_text = page.locator("#jrPreviewModal").inner_text()
            assert "digest" in modal_text.lower()

            # -------------------------------------------------------------
            # 4. Blocker 2: Escape digest email containing markup
            # -------------------------------------------------------------
            markup_email = "<b id='injectedMarkup'>maker</b>@example.com"
            fake_user_markup = {{
                "configured": True,
                "user": {{
                    "id": "usr_xss_test",
                    "email": markup_email,
                    "email_verified": True
                }},
                "usage": {{"plan": "starter", "remaining": 2, "limit": 20}},
                "workspace": {{"onboarding": {{"completed_at": "2026-11-09T00:00:00Z"}}}},
                "live_available": True
            }}
            page.route("**/api/v1/account/me", lambda r: r.fulfill(json=fake_user_markup))
            page.goto(f"{{live_server_url}}/digest", wait_until="domcontentloaded")
            page.wait_for_selector("#digestAccountInfo:not([hidden])")
            assert (
                page.locator("#injectedMarkup").count() == 0
            ), "Markup in email must not be rendered as HTML"
            assert markup_email in page.locator("#digestUserEmail").inner_text()

            # Also check home page inline digest prompt with markup email
            sample_home = f"{{live_server_url}}/?workspace=sample#loop-improve"
            page.goto(sample_home, wait_until="domcontentloaded")
            page.wait_for_selector("#jrDigestPrompt")
            dispatch_ev = (
                "email => window.dispatchEvent(new CustomEvent('muse:account-change', "
                "{{ detail: {{ configured: true, user: "
                "{{ id: 'usr_xss_test', email: email, email_verified: true }}, "
                "usage: {{ remaining: 2 }} }} }}))"
            )
            page.evaluate(dispatch_ev, markup_email)
            page.wait_for_timeout(200)
            assert (
                page.locator("#injectedMarkup").count() == 0
            ), "Markup in email must not be rendered as HTML on home prompt"

            browser.close()

        assert not model_called, "Model API must not be called during digest/habit navigation"
        print("PASS")
        """
    )

    proc = subprocess.run(
        [pw_python, "-c", runner_code], capture_output=True, text=True, check=False
    )
    assert proc.returncode == 0, f"Playwright failed (stdout={proc.stdout}, stderr={proc.stderr})"
    assert "PASS" in proc.stdout
