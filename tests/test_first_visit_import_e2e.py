"""After onboarding, the editors bring in the seller's own listings without a click.

Onboarding saves the shop website, but /today and /create used to open on a placeholder item
until the seller pressed "Find products". These checks pin the one-time request onboarding
leaves on the device, the two editors that honour it, and the guards around it: nothing is
scanned without the request, in the sample workspace, or over a draft the seller already has.
Every crawl is mocked in the browser; no network or Muse call is made.
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


def test_import_request_is_per_account_and_cleared_one_editor_at_a_time() -> None:
    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js not installed")
    harness = textwrap.dedent(
        """
        const fs = require('fs');
        const vm = require('vm');
        const assert = require('assert');
        const store = new Map();
        const localStorage = {
          getItem: (key) => (store.has(key) ? store.get(key) : null),
          setItem: (key, value) => store.set(key, String(value)),
          removeItem: (key) => store.delete(key),
        };
        const window = {
          addEventListener() {},
          location: { href: 'http://127.0.0.1/today', origin: 'http://127.0.0.1', search: '' },
        };
        vm.runInNewContext(fs.readFileSync(process.argv[1], 'utf8'), {
          window, localStorage, URL, URLSearchParams, console,
        });
        const modes = window.museModes;
        const key = 'muse.autoimport.pending.v1:seller-a';

        assert.strictEqual(modes.autoImportPending('seller-a', 'today'), false);
        modes.requestAutoImport('seller-a');
        assert.strictEqual(store.get(key), 'today,create');
        assert.strictEqual(modes.autoImportPending('seller-a', 'today'), true);
        assert.strictEqual(modes.autoImportPending('seller-a', 'create'), true);
        // Another account on the same device, a missing owner and unknown editors never match.
        assert.strictEqual(modes.autoImportPending('seller-b', 'today'), false);
        assert.strictEqual(modes.autoImportPending('', 'today'), false);
        assert.strictEqual(modes.autoImportPending('seller-a', 'digest'), false);

        modes.finishAutoImport('seller-a', 'today');
        assert.strictEqual(modes.autoImportPending('seller-a', 'today'), false);
        assert.strictEqual(modes.autoImportPending('seller-a', 'create'), true);
        modes.finishAutoImport('seller-a', 'create');
        assert.strictEqual(store.has(key), false);

        // Anything else stored under the key is ignored rather than trusted.
        store.set(key, 'digest,<script>,today');
        assert.strictEqual(modes.autoImportPending('seller-a', 'today'), true);
        assert.strictEqual(modes.autoImportPending('seller-a', '<script>'), false);
        modes.requestAutoImport('');
        assert.strictEqual(store.size, 1);
        console.log('IMPORT_REQUEST_OK');
        """
    )
    proc = subprocess.run(
        [node, "-e", harness, str(STATIC_DIR / "workspace-modes.js")],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert proc.returncode == 0, f"STDOUT: {proc.stdout}\nSTDERR: {proc.stderr}"
    assert "IMPORT_REQUEST_OK" in proc.stdout


def test_onboarding_leaves_the_request_only_for_a_signed_in_seller_with_a_shop() -> None:
    script = (STATIC_DIR / "welcome.js").read_text(encoding="utf-8")
    saved = script.index("state.completed_at = buildResult.completed_at")
    done = script.index("trackEvent('onboarding_completed'")
    completion = script[saved:done]
    assert "if (currentUser?.id && (state.shop_urls || []).some(Boolean)) {" in completion
    assert "window.museModes?.requestAutoImport?.(currentUser.id);" in completion
    # Nowhere else: visiting /welcome again or mirroring the server copy must not re-arm it.
    assert script.count("requestAutoImport") == 1


def test_editors_scan_only_on_request_and_without_a_muse_call() -> None:
    today = (STATIC_DIR / "today.js").read_text(encoding="utf-8")
    create = (STATIC_DIR / "creator.js").read_text(encoding="utf-8")
    for script, page in ((today, "today"), (create, "create")):
        start = script.index("async function autoImportSavedShop(")
        body = script[start : script.index("\n  }\n", start)]
        assert f"modes?.autoImportPending?.(owner, '{page}')" in body
        assert f"modes.finishAutoImport?.(owner, '{page}')" in body
        assert "/api/v1/ingest-storefront" in body
        assert "isEffectiveSample()" in body
        for paid in ("live=true", "use_muse", "generate-ads", "liveReady"):
            assert paid not in body
    # The request is honoured only once this account's workspace has loaded.
    assert "if (savedShop && !handoff) autoImportSavedShop(s.ownerId, savedShop.name);" in today
    assert (
        "if (savedShop && !requestedHandoffId()) autoImportSavedShop(s.ownerId, savedShop.name);"
        in create
    )


def test_first_visit_brings_in_the_sellers_listings_e2e(live_server_url: str) -> None:
    python_bin = _find_playwright_python()
    if not python_bin:
        pytest.skip("Playwright runtime not installed")

    runner_script = textwrap.dedent(
        f"""
        import json
        from playwright.sync_api import sync_playwright

        BASE = "{live_server_url}"
        USER = {{"id": "u-fern-123", "email": "fern@fernandkiln.example", "email_verified": True}}
        WORKSPACE = {{
            "document": {{
                "onboarding": {{
                    "business_name": "Fern & Kiln",
                    "shop_urls": ["https://fernandkiln.example"],
                    "completed_at": "2026-11-16T18:00:00Z",
                    "competitors": [],
                }}
            }},
            "version": 1,
            "owner_id": USER["id"],
        }}
        PNG = (
            "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQ"
            "DwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
        )
        FLAG = "muse.autoimport.pending.v1:" + USER["id"]
        DRAFT_KEY = "muse-editor-v1:daily:account:" + USER["id"]
        LISTINGS = {{
            "business_name": "Fern & Kiln",
            "channels": [{{"status": "fetched"}}],
            "discovered_catalog_items": [
                {{"title": "Speckled Stoneware Mug", "bucket": "products",
                  "url": "https://fernandkiln.example/products/mug", "price_hint": "$32"}},
                {{"title": "Ash Glaze Bowl", "bucket": "products",
                  "url": "https://fernandkiln.example/products/bowl", "price_hint": "$48"}},
            ],
        }}

        def reply(route, payload):
            route.fulfill(status=200, content_type="application/json", body=json.dumps(payload))

        def open_page(browser, width=1440, request_import=True, seed=None):
            ctx = browser.new_context(viewport={{"width": width, "height": 900}})
            calls = {{"ingest": 0, "outside": []}}
            seeded = dict(seed or {{}})
            if request_import:
                seeded[FLAG] = "today,create"
            # Seed once per browser context so a reload keeps whatever the page changed.
            ctx.add_init_script(
                "if (!localStorage.getItem('__seeded')) {{ localStorage.setItem('__seeded', '1');"
                " for (const [k, v] of Object.entries(" + json.dumps(seeded) + "))"
                " localStorage.setItem(k, v); }}"
            )
            page = ctx.new_page()
            errors = []
            page.on("pageerror", lambda e: errors.append(str(e)))

            def handle(route):
                url = route.request.url.split("?")[0]
                if url.endswith("/api/v1/account/me"):
                    return reply(route, {{
                        "configured": True,
                        "user": USER,
                        "usage": {{"plan": "starter", "used": 0, "limit": 3, "remaining": 3,
                                  "resets_at": None}},
                        "live_available": True,
                    }})
                if "/api/v1/account/workspace" in url:
                    return reply(route, WORKSPACE)
                if url.endswith("/api/v1/onboarding/status"):
                    return reply(route, {{
                        "completed": True, "completed_at": "2026-11-16T18:00:00Z",
                        "used_run": False, "plan": "starter", "runs_remaining": 3,
                    }})
                if url.endswith("/api/v1/ingest-storefront"):
                    calls["ingest"] += 1
                    assert (route.request.post_data_json or {{}}).get("website_url", "").startswith(
                        "https://fernandkiln.example"
                    )
                    return reply(route, LISTINGS)
                if url.endswith("/api/v1/product-reference"):
                    link = (route.request.post_data_json or {{}}).get("url", "")
                    title = "Speckled Stoneware Mug" if link.endswith("/mug") else "Ash Glaze Bowl"
                    return reply(route, {{
                        "title": title,
                        "description": "Hand-thrown stoneware with a speckled glaze.",
                        "price_hint": "$32",
                        "url": link,
                        "image_candidates": [{{
                            "id": "web-1", "image_data_url": PNG, "source_url": link,
                            "title": title, "width": 1200, "height": 1200,
                            "is_low_res": False, "provenance": "website",
                        }}],
                    }})
                return route.continue_()

            page.route("**/api/v1/**", handle)
            # Nothing in these flows may leave the local test server.
            page.route(
                lambda url: not url.startswith(BASE) and not url.startswith("data:"),
                lambda route: (calls["outside"].append(route.request.url), route.abort()),
            )
            return ctx, page, calls, errors

        def no_overflow(page, label):
            assert not page.evaluate(
                "document.documentElement.scrollWidth > document.documentElement.clientWidth"
            ), "Horizontal overflow on " + label

        def flag(page):
            return page.evaluate("localStorage.getItem(" + json.dumps(FLAG) + ")")

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)

            # 1. Fresh from onboarding: /today starts on the seller's first listing, unasked.
            for width in (1440, 375):
                ctx, page, calls, errors = open_page(browser, width=width)
                page.goto(BASE + "/today", wait_until="networkidle")
                assert page.evaluate("document.documentElement.dataset.museMode") == "account_own"
                page.wait_for_function(
                    "document.getElementById('itemTitle').textContent === 'Speckled Stoneware Mug'",
                    timeout=15000,
                )
                page.wait_for_function(
                    "document.querySelectorAll('#planCards button').length === 3", timeout=15000
                )
                page.wait_for_function(
                    "!document.getElementById('quickFindItems').disabled"
                    " && document.getElementById('notice').textContent.startsWith('Started with')",
                    timeout=15000,
                )
                assert calls["ingest"] == 1
                assert "Speckled Stoneware Mug" in page.locator("#postHook").input_value()
                assert "Speckled Stoneware Mug" in page.locator(
                    "#planCards button strong"
                ).first.inner_text()
                assert "Speckled Stoneware Mug" in page.locator("#dailyReason").inner_text()
                source = page.locator("#itemSource").inner_text().lower()
                assert "fernandkiln.example" in source and "check product facts" in source
                notice = page.locator("#notice").inner_text()
                assert "Started with" in notice and "fernandkiln.example" in notice
                # The photo is offered, never chosen for the seller.
                assert page.locator("#todayImageCandidatesGrid .muse-image-card").count() == 1
                assert page.evaluate("window.museDailySnapshot().imageMeta") is None
                assert flag(page) == "create"
                no_overflow(page, "/today " + str(width))

                # A reload recovers that draft and scans nothing again.
                page.goto(BASE + "/today", wait_until="networkidle")
                page.wait_for_timeout(400)
                assert calls["ingest"] == 1
                assert page.locator("#itemTitle").inner_text() == "Speckled Stoneware Mug"
                assert page.locator("#planCards button").count() == 3

                # 2. /create offers the listings and leaves the draft alone.
                page.goto(BASE + "/create", wait_until="networkidle")
                page.wait_for_selector("#importResults:not([hidden]) button", timeout=15000)
                assert calls["ingest"] == 2
                assert page.locator("#importResults button").count() == 2
                assert "Fern & Kiln" in page.locator("#importResults p").first.inner_text()
                assert page.locator("#productName").input_value() == "Product from Fern & Kiln"
                assert "Found 2 listings" in page.locator("#notice").inner_text()
                assert not page.evaluate("document.getElementById('importProducts').disabled")
                assert flag(page) is None
                no_overflow(page, "/create " + str(width))
                page.goto(BASE + "/create", wait_until="networkidle")
                page.wait_for_timeout(400)
                assert calls["ingest"] == 2
                assert not errors, errors
                assert not calls["outside"], calls["outside"]
                ctx.close()

            # 3. No request from onboarding: neither editor scans on its own.
            ctx, page, calls, errors = open_page(browser, request_import=False)
            page.goto(BASE + "/today", wait_until="networkidle")
            page.wait_for_timeout(400)
            page.goto(BASE + "/create", wait_until="networkidle")
            page.wait_for_timeout(400)
            assert calls["ingest"] == 0
            assert not errors, errors

            # 4. Pressing "Find products" still leaves three posts planned for the imported item.
            page.goto(BASE + "/today", wait_until="networkidle")
            assert page.locator("#planCards button").count() == 3
            page.click("#quickFindItems")
            page.wait_for_function(
                "document.getElementById('itemTitle').textContent === 'Speckled Stoneware Mug'",
                timeout=15000,
            )
            page.wait_for_function(
                "document.querySelectorAll('#planCards button').length === 3"
                " && document.querySelector('#planCards button strong').textContent"
                ".includes('Speckled Stoneware Mug')",
                timeout=15000,
            )
            assert calls["ingest"] == 1
            assert not errors, errors
            assert not calls["outside"], calls["outside"]
            ctx.close()

            # 5. Request present, sample workspace open: nothing is scanned and the request waits.
            ctx, page, calls, errors = open_page(browser)
            for path in ("/today?workspace=sample", "/create?workspace=sample"):
                page.goto(BASE + path, wait_until="networkidle")
                page.wait_for_timeout(400)
                mode = page.evaluate("document.documentElement.dataset.museMode")
                assert mode == "account_sample"
            assert calls["ingest"] == 0
            assert flag(page) == "today,create"
            assert not errors, errors
            ctx.close()

            # 6. Request present, but the seller already has their own item: it is left alone.
            draft = {{
                "schema": 1,
                "product": {{"title": "Walnut Serving Board", "description": "Hand-oiled walnut.",
                            "seller": "Fern & Kiln", "collection": "", "price": "",
                            "destination_url": "", "destination": "website"}},
                "original": "", "image": "", "imageMode": "original", "channel": "instagram",
                "selected": 0, "format": "image", "goal": "visits",
                "plans": {{}}, "edits": {{}}, "posted": {{}}, "offers": {{}},
            }}
            ctx, page, calls, errors = open_page(browser, seed={{DRAFT_KEY: json.dumps(draft)}})
            page.goto(BASE + "/today", wait_until="networkidle")
            page.wait_for_timeout(400)
            assert calls["ingest"] == 0
            assert page.locator("#itemTitle").inner_text() == "Walnut Serving Board"
            assert flag(page) == "create"
            assert not errors, errors
            ctx.close()

            # 7. The seller opens the sample shop while the scan is still running: the late
            #    result lands nowhere, and the request is honoured back in their own workspace.
            ctx, page, calls, errors = open_page(browser)
            held = []
            page.route("**/api/v1/ingest-storefront", lambda route: held.append(route))
            page.goto(BASE + "/today", wait_until="domcontentloaded")
            page.wait_for_function(
                "document.getElementById('notice').textContent"
                ".startsWith('Looking for your listings on fernandkiln.example')",
                timeout=15000,
            )
            assert len(held) == 1
            # The page stays usable while the scan runs.
            assert not page.evaluate("document.getElementById('quickFindItems').disabled")
            page.evaluate("window.museModes.enterSampleMode({{ artwork: 'naam_japo' }})")
            page.wait_for_selector("#todayImgSrcSampleBtn:not([hidden])")
            held[0].fulfill(
                status=200, content_type="application/json", body=json.dumps(LISTINGS)
            )
            page.wait_for_timeout(500)
            assert "Speckled" not in json.dumps(page.evaluate("window.museDailySnapshot()"))
            assert page.locator("#importItems button").count() == 0
            assert "Looking for your listings" not in (page.text_content("#notice") or "")
            assert flag(page) == "today,create"
            page.unroute("**/api/v1/ingest-storefront")
            page.evaluate("window.museModes.goToOwnWorkspace()")
            page.wait_for_function(
                "document.getElementById('itemTitle').textContent === 'Speckled Stoneware Mug'"
                " && document.getElementById('notice').textContent.startsWith('Started with')",
                timeout=15000,
            )
            assert calls["ingest"] == 1
            assert flag(page) == "create"
            assert not errors, errors
            assert not calls["outside"], calls["outside"]
            ctx.close()

            browser.close()
        print("FIRST_VISIT_IMPORT_OK")
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
    assert "FIRST_VISIT_IMPORT_OK" in proc.stdout


def test_finishing_onboarding_leaves_the_request_and_today_uses_it_e2e(
    live_server_url: str,
) -> None:
    """The whole path in one browser: the real wizard, then the first /today visit."""
    python_bin = _find_playwright_python()
    if not python_bin:
        pytest.skip("Playwright runtime not installed")

    runner_script = textwrap.dedent(
        f"""
        import json
        from playwright.sync_api import sync_playwright

        BASE = "{live_server_url}"
        USER = {{"id": "u-new-7", "email": "maker@mountainpottery.example", "email_verified": True}}
        FLAG = "muse.autoimport.pending.v1:" + USER["id"]
        store = {{"document": {{}}, "version": 1, "owner_id": USER["id"]}}
        calls = {{"ingest": 0, "outside": []}}
        LISTINGS = {{
            "business_name": "Mountain Pottery Studio",
            "total_channels": 1,
            "total_pages_crawled": 18,
            "channels": [{{
                "kind": "own_website", "url": "https://mountainpottery.example/",
                "host": "mountainpottery.example", "status": "fetched", "pages_found": 18,
            }}],
            "discovered_catalog_items": [
                {{"url": "https://mountainpottery.example/products/mug",
                  "title": "Speckled Stoneware Mug", "bucket": "products", "price_hint": "$24"}},
                {{"url": "https://mountainpottery.example/products/vase",
                  "title": "Kiln-Fired Vase Set", "bucket": "products", "price_hint": "$180"}},
            ],
            "detected_price_hints": ["$24", "$180"],
            "seller_context": "Mountain Pottery Studio",
        }}

        def reply(route, payload):
            route.fulfill(status=200, content_type="application/json", body=json.dumps(payload))

        def handle(route):
            url = route.request.url.split("?")[0]
            method = route.request.method
            done = (store["document"].get("onboarding") or {{}}).get("completed_at")
            if url.endswith("/api/v1/account/me"):
                return reply(route, {{
                    "configured": True, "user": USER,
                    "usage": {{"plan": "trial", "used": 0, "limit": 3, "remaining": 3,
                              "resets_at": None}},
                    "live_available": True,
                }})
            if "/api/v1/account/workspace" in url:
                if method != "GET":
                    payload = json.loads(route.request.post_data or "{{}}")
                    store["document"] = payload.get("document", {{}})
                    store["version"] += 1
                return reply(route, store)
            if url.endswith("/api/v1/onboarding/status"):
                return reply(route, {{
                    "completed": bool(done), "completed_at": done, "used_run": False,
                    "plan": "trial", "runs_remaining": 3,
                }})
            if url.endswith("/api/v1/onboarding/build") and method == "POST":
                store["document"]["onboarding"] = {{
                    **(route.request.post_data_json or {{}}),
                    "completed_at": "2026-11-16T18:00:00Z", "used_run": False,
                }}
                return reply(route, {{
                    "success": True, "charged": False, "used_run": False,
                    "runs_remaining": 3, "completed_at": "2026-11-16T18:00:00Z",
                    "workspace": store,
                }})
            if url.endswith("/api/v1/ingest-storefront"):
                calls["ingest"] += 1
                return reply(route, LISTINGS)
            if url.endswith("/api/v1/product-reference"):
                link = (route.request.post_data_json or {{}}).get("url", "")
                return reply(route, {{
                    "title": "Speckled Stoneware Mug",
                    "description": "Hand-thrown stoneware with a speckled glaze.",
                    "price_hint": "$24", "url": link, "image_candidates": [],
                }})
            return route.continue_()

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            ctx = browser.new_context(viewport={{"width": 1440, "height": 900}})
            page = ctx.new_page()
            errors = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.route("**/api/v1/**", handle)
            page.route(
                lambda url: not url.startswith(BASE) and not url.startswith("data:"),
                lambda route: (calls["outside"].append(route.request.url), route.abort()),
            )

            page.goto(BASE + "/welcome")
            page.wait_for_selector("#wkStep1:not([hidden])", timeout=10000)
            assert page.evaluate("localStorage.getItem(" + json.dumps(FLAG) + ")") is None
            page.fill("#wkShopUrl", "mountainpottery.example")
            page.fill("#wkBusinessName", "Mountain Pottery Studio")
            page.click("#wkScanShopBtn")
            page.wait_for_selector("#wkShopProof:not([hidden])")
            page.click("#wkStep1NextBtn")
            page.wait_for_selector("#wkStep2:not([hidden])")
            # Nothing is requested until the seller actually finishes.
            assert page.evaluate("localStorage.getItem(" + json.dumps(FLAG) + ")") is None
            page.click("#wkStep2NextBtn")
            page.wait_for_selector("#wkStep3:not([hidden])")
            page.click("#wkStep3NextBtn")
            page.wait_for_selector("#wkStep4:not([hidden])")
            page.click("#wkStep4FinishBtn")
            page.wait_for_selector("#wkStepDone:not([hidden])")
            assert (
                page.evaluate("localStorage.getItem(" + json.dumps(FLAG) + ")") == "today,create"
            )
            scans_in_onboarding = calls["ingest"]

            page.goto(BASE + "/today", wait_until="networkidle")
            page.wait_for_function(
                "document.getElementById('itemTitle').textContent === 'Speckled Stoneware Mug'"
                " && document.getElementById('notice').textContent.startsWith('Started with')",
                timeout=15000,
            )
            page.wait_for_function(
                "document.querySelectorAll('#planCards button').length === 3", timeout=15000
            )
            assert calls["ingest"] == scans_in_onboarding + 1
            assert page.evaluate("localStorage.getItem(" + json.dumps(FLAG) + ")") == "create"
            assert not errors, errors
            outside = [u for u in calls["outside"] if "fonts.g" not in u]
            assert not outside, outside
            browser.close()
        print("ONBOARDING_TO_TODAY_OK")
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
    assert "ONBOARDING_TO_TODAY_OK" in proc.stdout
