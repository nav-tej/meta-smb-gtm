"""Batch A end-to-end tests for Workspace Modes, Website Import, and Sample Ad Formats."""

from __future__ import annotations

import os
import re
import shutil
import socket
import subprocess
import sys
import textwrap
import threading
import time
from pathlib import Path

import pytest
import uvicorn
from fastapi.testclient import TestClient

from src.api.main import app

REPO_ROOT = Path(__file__).resolve().parents[1]
STATIC_DIR = REPO_ROOT / "src" / "api" / "static"


@pytest.fixture(scope="module")
def live_server_url() -> str:
    """Start an ephemeral uvicorn server for headless browser E2E checks."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()

    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error")
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


def test_presenter_controls_removed_from_customer_surfaces() -> None:
    """Customer pages and JS modules contain no presenter unlock or X-Demo-Key UI."""
    client = TestClient(app)
    for route in ("/", "/welcome", "/create", "/today", "/digest", "/progress"):
        res = client.get(route)
        assert res.status_code == 200, f"GET {route} failed: {res.status_code}"
        html = res.text
        assert 'id="unlockKey"' not in html, f"Found #unlockKey in {route}"
        assert 'class="operator"' not in html, f"Found .operator block in {route}"
        assert "X-Demo-Key" not in html, f"Found X-Demo-Key in {route}"
        assert "Demo presenter" not in html, f"Found Demo presenter text in {route}"
        assert "/static/workspace-modes.js" in html, f"Missing workspace-modes.js on {route}"
        assert html.index("/static/account.js") < html.index("/static/workspace-modes.js"), (
            f"workspace-modes.js must load after account.js on {route}"
        )

    for js_name in (
        "creator.js",
        "today.js",
        "research.js",
        "workspace-modes.js",
        "digest.js",
    ):
        text = (STATIC_DIR / js_name).read_text(encoding="utf-8")
        assert "X-Demo-Key" not in text, f"Found X-Demo-Key in {js_name}"
        assert "unlockKey" not in text, f"Found unlockKey in {js_name}"
        assert "Demo unlock" not in text, f"Found Demo unlock in {js_name}"


def test_sample_ad_formats_gallery_markup_contract() -> None:
    """Landing page exposes 4:5 Feed, 9:16 Story, and 1:1 Square proof cards."""
    html = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
    assert 'id="sampleAdFormatsGallery"' in html
    assert "4:5" in html and "1080×1350" in html
    assert "9:16" in html and "1080×1920" in html
    assert "1:1" in html and "1080×1080" in html
    assert "Original artwork" in html
    assert "Illustrative saved AI scene" in html
    assert "Sample showcase · not a competitor ad" in html
    assert "/create?workspace=sample&amp;placement=instagram_feed&amp;artwork=ek_onkar" in html
    assert "/create?workspace=sample&amp;placement=instagram_story&amp;artwork=naam_japo" in html
    assert "/create?workspace=sample&amp;placement=facebook_feed&amp;artwork=kirat_karo" in html
    assert not re.search(r"unlockKey|X-Demo-Key", html)


@pytest.mark.parametrize("viewport_width", [375, 1440])
def test_guest_sample_formats_and_presenter_immunity_e2e(
    live_server_url: str, tmp_path: Path, viewport_width: int
) -> None:
    """Verify public sample format cards, modal, fallback posters, and exact PNG exports."""
    pw_python = _find_playwright_python()
    if not pw_python:
        pytest.skip("Playwright runtime not installed")

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
        width = int(sys.argv[2])
        shot_dir = Path(sys.argv[3])
        height = 667 if width < 600 else 900

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                viewport={"width": width, "height": height},
                accept_downloads=True,
            )
            page = context.new_page()
            errors = []
            page.on("pageerror", lambda exc: errors.append(str(exc)))
            page.on(
                "console",
                lambda msg: errors.append(msg.text) if msg.type == "error" else None,
            )
            page.route(
                "*api.meta.ai*",
                lambda route: (_ for _ in ()).throw(
                    AssertionError(f"Paid call attempted: {route.request.url}")
                ),
            )
            page.route(
                "*llama.com*",
                lambda route: (_ for _ in ()).throw(
                    AssertionError(f"Paid call attempted: {route.request.url}")
                ),
            )

            # 1. Guest entry on / shows Sample Ad Formats near the top with 3 formats
            page.goto(f"{base}/", wait_until="networkidle")
            gallery = page.locator("#sampleAdFormatsGallery")
            gallery.wait_for(state="visible", timeout=5000)
            cards = gallery.locator(".sample-format-card")
            assert cards.count() == 3, f"Expected 3 sample cards, got {cards.count()}"

            gallery_text = gallery.inner_text()
            for expected in (
                "4:5",
                "1080×1350",
                "9:16",
                "1080×1920",
                "1:1",
                "1080×1080",
                "Original artwork",
                "Illustrative saved AI scene",
                "Art of Sarabjit Singh",
                "Sample showcase",
            ):
                assert expected in gallery_text, f"Missing {expected!r} in gallery"

            img_stats = gallery.evaluate(
                '''(el) => Array.from(el.querySelectorAll('img')).map((img) => ({
                    src: img.getAttribute('src'),
                    complete: img.complete,
                    w: img.naturalWidth,
                    h: img.naturalHeight,
                }))'''
            )
            assert len(img_stats) >= 6, f"Expected >= 6 images (original+AI pairs), got {img_stats}"
            for st in img_stats:
                assert st["complete"] and st["w"] > 0 and st["h"] > 0, f"Broken image: {st}"

            assert not page.evaluate(
                "document.documentElement.scrollWidth > document.documentElement.clientWidth"
            ), f"Horizontal overflow on / at {width}px"
            page.screenshot(path=str(shot_dir / f"landing_gallery_{width}.png"))

            # 2. Modal #adDialog inspection from ad grid (open stage 2 Create first)
            page.locator('.jr-loop a[href="#loop-create"]').click()
            page.locator("#adGallery button.jr-ad").first.click()
            dialog = page.locator("#adDialog")
            dialog.wait_for(state="visible", timeout=5000)
            assert len(page.locator("#adDialogTitle").inner_text().strip()) > 3
            page.locator("#adDialog .jr-dialog-close").click()
            dialog.wait_for(state="hidden", timeout=5000)

            # 3. Presenter query params must never re-enable operator UI
            page.goto(f"{base}/create?demo=1&presenter=1&operator=1", wait_until="networkidle")
            assert page.locator("#unlockKey").count() == 0
            assert page.locator(".operator").count() == 0
            assert "Demo presenter" not in page.locator("body").inner_text()

            page.goto(f"{base}/today?presenter=1", wait_until="networkidle")
            assert page.locator("#unlockKey").count() == 0
            assert page.locator(".operator").count() == 0
            assert "Demo presenter" not in page.locator("body").inner_text()

            # 4. Placement handoff from Story 9:16 card -> /create exports exact PNG dimensions
            page.goto(
                f"{base}/create?workspace=sample&placement=instagram_story&artwork=naam_japo",
                wait_until="networkidle",
            )
            banner = page.locator("#museModeBanner")
            banner.wait_for(state="visible", timeout=5000)
            assert "Set up your own shop" in banner.inner_text()
            assert "Naam Japo" in page.locator("#productName").input_value()
            page.wait_for_function(
                "() => document.getElementById('previewCanvas')?.height === 1920",
                timeout=5000,
            )
            assert "primary" in (page.locator("#downloadStory").get_attribute("class") or "")

            page.locator("[data-step='2']").first.click()
            page.locator("#reviewed").check()
            page.locator("[data-step='3']").first.click()

            expected_sizes = [
                ("#downloadFeed", (1080, 1350)),
                ("#downloadStory", (1080, 1920)),
                ("#downloadSquare", (1080, 1080)),
            ]
            for btn_sel, size in expected_sizes:
                with page.expect_download() as dl_info:
                    page.locator(btn_sel).click()
                data = Path(dl_info.value.path()).read_bytes()
                with Image.open(io.BytesIO(data)) as img:
                    assert img.size == size, f"{btn_sel}: expected {size}, got {img.size}"

            assert not errors, f"Browser runtime errors: {errors}"
            browser.close()

            # 5. Broken asset + /api/v1/demo-presets 500 fallback test
            ctx2 = p.chromium.launch(headless=True)
            b2_ctx = ctx2.new_context(viewport={"width": width, "height": height})
            p2 = b2_ctx.new_page()
            p2.route("**/samples/**", lambda r: r.abort())
            p2.route(
                "**/api/v1/demo-presets",
                lambda r: r.fulfill(status=500, body="upstream error"),
            )
            p2.goto(f"{base}/", wait_until="networkidle")
            p2.locator("#sampleAdFormatsGallery").wait_for(state="visible", timeout=5000)
            p2.wait_for_timeout(200)
            fallback_imgs = p2.locator("#sampleAdFormatsGallery img").evaluate_all(
                "els => els.map(e => ({ complete: e.complete, w: e.naturalWidth, src: e.src }))"
            )
            assert len(fallback_imgs) >= 6
            for st in fallback_imgs:
                assert st["complete"] and st["w"] > 0, f"Fallback SVG failed: {st}"
            assert p2.locator("#adGallery button.jr-ad").count() >= 3
            ctx2.close()
        print("GUEST_SAMPLE_FORMATS_OK")
        """
    )

    res = subprocess.run(
        [
            pw_python,
            "-c",
            script,
            live_server_url,
            str(viewport_width),
            str(shot_dir),
            str(REPO_ROOT / "tests/fixtures/product_photo.png"),
        ],
        capture_output=True,
        text=True,
        timeout=90,
        check=False,
    )
    assert res.returncode == 0, f"STDOUT:\n{res.stdout}\nSTDERR:\n{res.stderr}"
    assert "GUEST_SAMPLE_FORMATS_OK" in res.stdout


@pytest.mark.parametrize("viewport_width", [375, 1440])
def test_signed_in_workspace_modes_isolation_import_and_auth_safety_e2e(
    live_server_url: str, tmp_path: Path, viewport_width: int
) -> None:
    """Test signed-in My workspace, zero Sarabjit flash, URL scan isolation, & auth failures."""
    pw_python = _find_playwright_python()
    if not pw_python:
        pytest.skip("Playwright runtime not installed")

    shot_dir = Path(os.environ.get("MUSE_E2E_SCREENSHOT_DIR", str(tmp_path)))
    shot_dir.mkdir(parents=True, exist_ok=True)

    script = textwrap.dedent(
        """
        import json
        import sys
        import time
        from pathlib import Path
        from playwright.sync_api import sync_playwright

        base = sys.argv[1]
        width = int(sys.argv[2])
        shot_dir = Path(sys.argv[3])
        height = 667 if width < 600 else 900

        elena_ws = {
            "document": {
                "onboarding": {
                    "business_name": "Elena Vance Watercolor Studio",
                    "shop_urls": ["https://elenavanceart.com"],
                    "socials": [{"platform": "instagram", "handle": "@elenavanceart"}],
                    "competitors": [
                        {
                            "name": "Wild Meadow Studio",
                            "url": "https://wildmeadow.test",
                            "reason": "Botanical watercolors",
                        }
                    ],
                    "preferences": {"medium": "Watercolor"},
                    "completed_at": "2026-11-10T12:00:00Z",
                    "used_run": False,
                }
            },
            "version": 1,
            "owner_id": "u-elena-999",
        }
        oak_ws = {
            "document": {
                "onboarding": {
                    "business_name": "Oak & Pine Ceramics",
                    "shop_urls": ["https://oakandpine.shop"],
                    "socials": [],
                    "competitors": [],
                    "completed_at": "2026-11-10T12:00:00Z",
                    "used_run": False,
                }
            },
            "version": 2,
            "owner_id": "u-oak-888",
        }

        state = {
            "me_status": 200,
            "me_delay": 0.25,
            "ws_delay": 0.0,
            "user_id": "u-elena-999",
            "ingest_fail": False,
            "ws_puts": [],
        }

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(viewport={"width": width, "height": height})
            page = context.new_page()
            errors = []
            page.on("pageerror", lambda exc: errors.append(str(exc)))

            def handle_api(route):
                url = route.request.url
                method = route.request.method
                if url.endswith("/api/v1/account/me"):
                    if state["me_delay"]:
                        time.sleep(state["me_delay"])
                    if state["me_status"] != 200:
                        route.fulfill(
                            status=state["me_status"],
                            content_type="application/json",
                            body=json.dumps({"detail": f"Auth error {state['me_status']}"}),
                        )
                        return
                    uid = state["user_id"]
                    route.fulfill(
                        status=200,
                        content_type="application/json",
                        body=json.dumps(
                            {
                                "configured": True,
                                "user": {
                                    "id": uid,
                                    "email": f"{uid}@studio.test",
                                    "email_verified": True,
                                },
                                "usage": {"plan": "starter", "used": 0, "limit": 5, "remaining": 5},
                                "live_available": True,
                            }
                        ),
                    )
                    return

                if "/api/v1/account/workspace" in url:
                    if state["ws_delay"]:
                        time.sleep(state["ws_delay"])
                    ws = elena_ws if state["user_id"] == "u-elena-999" else oak_ws
                    if method == "PUT":
                        payload = route.request.post_data_json or {}
                        state["ws_puts"].append(payload)
                        ws["document"] = payload.get("document", ws["document"])
                        ws["version"] += 1
                    route.fulfill(
                        status=200,
                        content_type="application/json",
                        body=json.dumps(ws),
                    )
                    return

                if url.endswith("/api/v1/readiness"):
                    route.fulfill(
                        status=200,
                        content_type="application/json",
                        body=json.dumps(
                            {
                                "default_mode": "saved",
                                "accounts_required": True,
                                "provider_key_configured": True,
                            }
                        ),
                    )
                    return

                if url.endswith("/api/v1/ingest-storefront"):
                    if state["ingest_fail"]:
                        route.fulfill(
                            status=500,
                            content_type="application/json",
                            body=json.dumps({"detail": "Temporary crawl failure"}),
                        )
                        return
                    body = route.request.post_data_json or {}
                    route.fulfill(
                        status=200,
                        content_type="application/json",
                        body=json.dumps(
                            {
                                "business_name": body.get("business_name") or "Scanned Shop",
                                "channels": [{"status": "fetched"}],
                                "discovered_catalog_items": [
                                    {
                                        "title": "Botanical Print 12x16",
                                        "url": "https://oneoff-test.example/botanical",
                                        "price_hint": "$45",
                                        "bucket": "products",
                                    }
                                ],
                            }
                        ),
                    )
                    return

                if url.endswith("/api/v1/content-plan"):
                    body = route.request.post_data_json or {}
                    title = body.get("product", {}).get("title") or "Studio Item"
                    route.fulfill(
                        status=200,
                        content_type="application/json",
                        body=json.dumps(
                            {
                                "mode": "starter",
                                "posts": [
                                    {
                                        "day_offset": i,
                                        "channel": "instagram",
                                        "format": "image",
                                        "hook": f"{title} post {i+1}",
                                        "caption": f"Sharing {title}.",
                                        "visual_direction": "Show artwork.",
                                        "posting_tip": "Keep it clear.",
                                    }
                                    for i in range(3)
                                ],
                                "insight": {"next_action": "Share once."},
                                "sources": [],
                            }
                        ),
                    )
                    return

                if "/api/v1/daily-brief" in url:
                    route.fulfill(
                        status=200,
                        content_type="application/json",
                        body=json.dumps(
                            {
                                "date": "2026-11-11",
                                "source": "Workspace for Elena Vance Watercolor Studio",
                                "items": [],
                                "move": {
                                    "title": "Share Monsoon Lotuses",
                                    "reason": "Keep your own shop moving.",
                                    "href": "/create",
                                },
                            }
                        ),
                    )
                    return

                route.continue_()

            page.route("**/api/v1/**", handle_api)

            # Monitor for any transient Sarabjit/Ek Onkar flash during initial loading on /create
            page.add_init_script(
                '''
                window.__sarabjitFlash = false;
                const checkFlash = () => {
                  const main = document.querySelector('main');
                  const mode = document.documentElement.dataset.museMode || '';
                  if (
                    main &&
                    getComputedStyle(main).display !== 'none' &&
                    mode !== 'account_sample'
                  ) {
                    const txt = main.innerText || '';
                    if (/sarabjit|ek onkar/i.test(txt) && /account_own|loading/.test(mode)) {
                      window.__sarabjitFlash = txt.slice(0, 200);
                    }
                  }
                };
                document.addEventListener('DOMContentLoaded', () => {
                  new MutationObserver(checkFlash).observe(document.documentElement, {
                    subtree: true, childList: true, characterData: true, attributes: true
                  });
                });
                '''
            )

            # 1. /create in account_own: prominent website import & customer live status
            page.goto(f"{base}/create", wait_until="networkidle")
            assert page.evaluate("document.documentElement.dataset.museMode") == "account_own"
            assert not page.evaluate("window.__sarabjitFlash"), (
                f"Sarabjit flash detected: {page.evaluate('window.__sarabjitFlash')}"
            )
            assert "Sarabjit" not in page.locator("body").inner_text()
            assert "Ek Onkar" not in page.locator("body").inner_text()
            assert page.locator("#shopUrl").is_visible()
            assert page.locator("#directPhotoUpload").is_visible()
            assert page.locator("#accountLiveBox").is_visible()
            assert "5 runs left" in page.locator("#liveEligibilityNote").inner_text()
            assert not page.evaluate(
                "document.documentElement.scrollWidth > document.documentElement.clientWidth"
            ), f"Horizontal overflow on /create at {width}px"
            page.screenshot(path=str(shot_dir / f"create_own_{width}.png"))

            # Edit draft manually across Step 1 and Step 3, then test draft-only + 500 scans
            page.locator("#productName").fill("Monsoon Lotuses")
            page.locator("#productPhoto").set_input_files(sys.argv[4])
            page.wait_for_function(
                "() => !document.getElementById('productImage')?.hidden"
            )
            page.locator('nav.steps [data-step="2"]').click()
            page.locator("#headline").fill("Original Watercolor Series")
            page.locator("#caption").fill("Hand-painted on Arches 300gsm paper.")
            page.locator('nav.steps [data-step="0"]').click()

            puts_before = len(state["ws_puts"])
            page.locator("#saveShopWebsite").uncheck()
            page.locator("#shopUrl").fill("https://oneoff-test.example")
            page.locator("#importProducts").click()
            page.locator("#importResults").wait_for(state="visible", timeout=5000)
            assert len(state["ws_puts"]) == puts_before, "Draft-only scan modified studio website"

            # Failed scan preserves existing draft fields
            state["ingest_fail"] = True
            page.locator("#importProducts").click()
            page.wait_for_timeout(200)
            state["ingest_fail"] = False
            assert page.locator("#productName").input_value() == "Monsoon Lotuses"
            assert page.locator("#headline").input_value() == "Original Watercolor Series"
            assert page.locator("#caption").input_value() == "Hand-painted on Arches 300gsm paper."

            # Explicit Save website persists into onboarding.shop_urls without losing other fields
            page.locator("#shopUrl").fill("https://monsoonwatercolors.example")
            page.locator("#saveWebsiteOnlyBtn").click()
            page.wait_for_function(
                "() => (document.getElementById('savedShopWebsiteNote')?.textContent || '')"
                ".includes('monsoonwatercolors.example')"
            )
            assert len(state["ws_puts"]) == puts_before + 1
            saved_onb = state["ws_puts"][-1]["document"]["onboarding"]
            assert "https://monsoonwatercolors.example/" in saved_onb["shop_urls"][0]
            assert saved_onb["business_name"] == "Elena Vance Watercolor Studio"

            # 2. Switch to Sample shop via button -> isolated :sample + persistent Back button
            page.locator("#artistExample").click()
            page.locator("#museModeBanner").wait_for(state="visible", timeout=5000)
            assert page.evaluate("document.documentElement.dataset.museMode") == "account_sample"
            assert "Ek Onkar" in page.locator("#productName").input_value()
            page.locator('nav.steps [data-step="2"]').click()
            page.locator("#headline").fill("Sample Edit Only")

            own_raw = page.evaluate(
                "localStorage.getItem('muse-editor-v1:creator:account:u-elena-999')"
            )
            sample_raw = page.evaluate("localStorage.getItem('muse-editor-v1:creator:sample')")
            assert "Original Watercolor Series" in (own_raw or "")
            assert "Sample Edit Only" not in (own_raw or "")
            assert "Sample Edit Only" in (sample_raw or "")

            # Back to my workspace restores personal draft cleanly
            page.locator("#museModeBanner button").first.click()
            page.wait_for_function(
                "() => document.documentElement.dataset.museMode === 'account_own'"
            )
            assert page.locator("#productName").input_value() == "Monsoon Lotuses"
            assert page.locator("#headline").input_value() == "Original Watercolor Series"

            # Unsupported links must not switch to sample or discard a recovered personal draft.
            for query in ("idea=personal-watercolor-launch", "artwork=my-own-watercolor",
                          "workspace=own&idea=bogus-unrecognized-id"):
                page.goto(f"{base}/create?{query}", wait_until="networkidle")
                assert page.evaluate("document.documentElement.dataset.museMode") == "account_own"
                assert page.locator("#headline").input_value() == "Original Watercolor Series"
                assert page.locator("#productName").input_value() == "Monsoon Lotuses"
            page.goto(f"{base}/create", wait_until="networkidle")

            # Direct sample ?idea= URL + browser history.back() restores personal workspace
            page.goto(f"{base}/create?idea=idea-1-empowering-women", wait_until="networkidle")
            assert page.evaluate("document.documentElement.dataset.museMode") == "account_sample"
            page.go_back(wait_until="networkidle")
            assert page.evaluate("document.documentElement.dataset.museMode") == "account_own"
            assert page.locator("#headline").input_value() == "Original Watercolor Series"

            # 3. /today website bar, /digest, /progress stay clean in account_own
            page.goto(f"{base}/today", wait_until="networkidle")
            assert page.evaluate("document.documentElement.dataset.museMode") == "account_own"
            assert page.locator("#todayWebsiteBar").is_visible()
            assert "Sarabjit" not in page.locator("body").inner_text()
            assert "Ek Onkar" not in page.locator("body").inner_text()

            page.goto(f"{base}/digest", wait_until="networkidle")
            assert "Sarabjit" not in page.locator("body").inner_text()

            page.goto(f"{base}/progress", wait_until="networkidle")
            assert "Sarabjit" not in page.locator("body").inner_text()

            # 4. /api/v1/account/me 500 & 401 never fall back to sample shop
            state["me_delay"] = 0.0
            state["me_status"] = 500
            for path in ("/create", "/today", "/", "/digest"):
                page.goto(f"{base}{path}", wait_until="networkidle")
                assert page.evaluate("document.documentElement.dataset.museMode") == "error", (
                    f"Expected error mode on {path}"
                )
                banner = page.locator("#museModeBanner")
                banner.wait_for(state="visible", timeout=5000)
                assert "Retry" in banner.inner_text()
                assert "Ek Onkar" not in page.locator("body").inner_text()

            state["me_status"] = 401
            page.goto(f"{base}/create", wait_until="networkidle")
            assert page.evaluate("document.documentElement.dataset.museMode") == "expired"
            assert "expired" in page.locator("#museModeBanner").inner_text().lower()

            # 5. Stale workspace response cannot overwrite switched account Oak & Pine
            state["me_status"] = 200
            state["ws_delay"] = 0.25
            page.goto(f"{base}/create", wait_until="domcontentloaded")
            state["user_id"] = "u-oak-888"
            state["ws_delay"] = 0.0
            page.goto(f"{base}/create", wait_until="networkidle")
            assert "Elena Vance" not in page.locator("body").inner_text()

            assert not errors, f"Browser runtime errors: {errors}"
            browser.close()
        print("SIGNED_IN_WORKSPACE_MODES_OK")
        """
    )

    res = subprocess.run(
        [
            pw_python,
            "-c",
            script,
            live_server_url,
            str(viewport_width),
            str(shot_dir),
            str(REPO_ROOT / "tests/fixtures/product_photo.png"),
        ],
        capture_output=True,
        text=True,
        timeout=90,
        check=False,
    )
    assert res.returncode == 0, f"STDOUT:\n{res.stdout}\nSTDERR:\n{res.stderr}"
    assert "SIGNED_IN_WORKSPACE_MODES_OK" in res.stdout
