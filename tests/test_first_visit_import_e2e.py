"""The editors bring in the seller's own listings without a click.

Onboarding saves the shop website, but /today and /create used to open on a placeholder item
until the seller pressed "Find products". The account workspace now says when a shop website is
saved (`listing_import.first_visit`), and each editor acts on that once per account on a device.
These checks pin the server signal, the per-device memory, the two editors that honour it, and
the guards around it: nothing is scanned without the signal, in the sample workspace, or over a
draft the seller already has. Every crawl is mocked in the browser; no network or Muse call is
made.
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
from typing import Any

import pytest
import uvicorn
from fastapi.testclient import TestClient

from src.api.accounts import listing_import_hint
from src.api.main import STATIC_DIR, app
from src.services import accounts as accounts_service
from src.services.accounts import AccountSession


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


def test_workspace_read_says_when_a_shop_website_is_saved(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert listing_import_hint({"onboarding": {"shop_urls": ["https://fernandkiln.example"]}}) == {
        "first_visit": True
    }
    # Finishing setup is not required: a website saved from an editor counts too.
    assert listing_import_hint({"onboarding": {"shop_urls": ["", " https://a.example "]}}) == {
        "first_visit": True
    }
    for document in (
        None,
        {},
        {"onboarding": None},
        {"onboarding": {"completed_at": "2026-11-16T18:00:00Z"}},
        {"onboarding": {"shop_urls": []}},
        {"onboarding": {"shop_urls": ["", "  ", None, 7]}},
        {"onboarding": {"shop_urls": "https://fernandkiln.example"}},
        {"shop_urls": ["https://fernandkiln.example"]},
    ):
        assert listing_import_hint(document) == {"first_visit": False}, document

    user = AccountSession(
        user_id="00000000-0000-4000-8000-000000000007",
        email="fern@example.test",
        email_verified=True,
        access_token="token-fern",
        session_id=None,
    )
    stored: dict[str, Any] = {
        # Finished setup long before this signal existed; nothing was ever written for it.
        "document": {
            "onboarding": {
                "business_name": "Fern & Kiln",
                "shop_urls": ["https://fernandkiln.example"],
                "completed_at": "2026-11-08T09:00:00Z",
            },
            "documents": {"daily": {"hook": "kept"}},
        },
        "version": 6,
    }

    class FakeSupabase:
        async def workspace(self, user_id: str) -> list[dict[str, Any]]:
            assert user_id == user.user_id
            return [stored]

    async def fake_resolve(*_args: Any, **_kwargs: Any) -> AccountSession:
        return user

    monkeypatch.setattr("src.api.accounts.resolve_account", fake_resolve)
    monkeypatch.setattr(accounts_service, "get_supabase_client", lambda: FakeSupabase())

    client = TestClient(app)
    payload = client.get("/api/v1/account/workspace", headers={"X-Muse-Owner": user.user_id}).json()
    assert payload["listing_import"] == {"first_visit": True}
    # Derived on the way out: the saved document and its version are untouched.
    assert payload["document"] == stored["document"]
    assert "listing_import" not in payload["document"]
    assert payload["version"] == 6 and payload["owner_id"] == user.user_id

    stored["document"] = {"documents": {"daily": {"hook": "kept"}}}
    payload = client.get("/api/v1/account/workspace", headers={"X-Muse-Owner": user.user_id}).json()
    assert payload["listing_import"] == {"first_visit": False}


def test_each_editor_remembers_per_account_that_it_tried_on_this_device() -> None:
    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js not installed")
    harness = textwrap.dedent(
        """
        const fs = require('fs');
        const vm = require('vm');
        const assert = require('assert');
        const store = new Map();
        let broken = false;
        const localStorage = {
          getItem: (key) => {
            if (broken) throw new Error('blocked');
            return store.has(key) ? store.get(key) : null;
          },
          setItem: (key, value) => {
            if (broken) throw new Error('blocked');
            store.set(key, String(value));
          },
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
        const key = 'muse.autoimport.tried.v1:seller-a';
        const offered = { document: {}, listing_import: { first_visit: true } };

        // The server has to say so. A saved website in the document is not enough.
        const onboarding = { shop_urls: ['https://a.example'], completed_at: 'x' };
        const unsignalled = [
          undefined, null, {}, { document: { onboarding } }, { listing_import: {} },
          { listing_import: { first_visit: 'true' } }, { listing_import: { first_visit: 1 } },
        ];
        for (const ws of unsignalled) {
          assert.strictEqual(modes.autoImportPending('seller-a', 'today', ws), false);
        }
        assert.strictEqual(modes.autoImportPending('seller-a', 'today', offered), true);
        assert.strictEqual(modes.autoImportPending('seller-a', 'create', offered), true);
        assert.strictEqual(modes.autoImportPending('', 'today', offered), false);
        assert.strictEqual(modes.autoImportPending('seller-a', 'digest', offered), false);
        assert.strictEqual(store.size, 0);

        modes.finishAutoImport('seller-a', 'create');
        assert.strictEqual(store.get(key), 'create');
        assert.strictEqual(modes.autoImportPending('seller-a', 'create', offered), false);
        assert.strictEqual(modes.autoImportPending('seller-a', 'today', offered), true);
        // Another account on the same device starts fresh.
        assert.strictEqual(modes.autoImportPending('seller-b', 'create', offered), true);
        modes.finishAutoImport('seller-a', 'today');
        modes.finishAutoImport('seller-a', 'today');
        assert.strictEqual(store.get(key), 'today,create');
        assert.strictEqual(modes.autoImportPending('seller-a', 'today', offered), false);

        // Unknown editors and a missing owner are never recorded.
        modes.finishAutoImport('seller-a', 'digest');
        modes.finishAutoImport('', 'today');
        assert.strictEqual(store.size, 1);
        assert.strictEqual(store.get(key), 'today,create');

        // Anything else stored under the key is ignored rather than trusted.
        store.set(key, 'digest,<script>');
        assert.strictEqual(modes.autoImportPending('seller-a', 'today', offered), true);

        // Storage blocked: nothing can be remembered, so nothing is scanned unasked.
        broken = true;
        assert.strictEqual(modes.autoImportPending('seller-b', 'today', offered), false);
        modes.finishAutoImport('seller-b', 'today');
        broken = false;
        assert.strictEqual(store.has('muse.autoimport.tried.v1:seller-b'), false);

        // The earlier device request from onboarding is gone.
        assert.strictEqual(modes.requestAutoImport, undefined);
        console.log('IMPORT_MEMORY_OK');
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
    assert "IMPORT_MEMORY_OK" in proc.stdout


def test_editors_scan_only_on_the_server_signal_and_without_a_muse_call() -> None:
    today = (STATIC_DIR / "today.js").read_text(encoding="utf-8")
    create = (STATIC_DIR / "creator.js").read_text(encoding="utf-8")
    for script, page in ((today, "today"), (create, "create")):
        start = script.index("async function autoImportSavedShop(")
        body = script[start : script.index("\n  }\n", start)]
        assert f"modes?.autoImportPending?.(owner, '{page}', workspace)" in body
        assert f"modes.finishAutoImport?.(owner, '{page}')" in body
        assert "/api/v1/ingest-storefront" in body
        assert "isEffectiveSample()" in body
        for paid in ("live=true", "use_muse", "generate-ads", "liveReady"):
            assert paid not in body
    # Only with the workspace this account just loaded, and never over a recommendation handoff.
    assert (
        "if (savedShop && !handoff) "
        "autoImportSavedShop(s.ownerId, savedShop.name, savedShop.workspace);" in today
    )
    assert (
        "if (savedShop && !requestedHandoffId()) "
        "autoImportSavedShop(s.ownerId, savedShop.name, savedShop.workspace);" in create
    )
    # Onboarding no longer leaves anything on the device for this.
    for name in ("welcome.js", "today.js", "creator.js", "workspace-modes.js"):
        assert "requestAutoImport" not in (STATIC_DIR / name).read_text(encoding="utf-8"), name


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
        USER_B = {{"id": "u-oak-456", "email": "oak@oakandpine.example", "email_verified": True}}
        WORKSPACE_B = {{
            "document": {{
                "onboarding": {{
                    "business_name": "Oak & Pine",
                    "shop_urls": ["https://oakandpine.example"],
                    "completed_at": "2026-11-12T09:00:00Z",
                    "competitors": [],
                }}
            }},
            "version": 1,
            "owner_id": USER_B["id"],
            "listing_import": {{"first_visit": True}},
        }}
        LISTINGS_B = {{
            "business_name": "Oak & Pine",
            "channels": [{{"status": "fetched"}}],
            "discovered_catalog_items": [
                {{"title": "Turned Oak Bowl", "bucket": "products",
                  "url": "https://oakandpine.example/products/oak-bowl", "price_hint": "$64"}},
            ],
        }}
        TRIED_PREFIX = "muse.autoimport.tried.v1:"
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

        # Each call is a new browser context: the same account on a device that remembers nothing.
        def open_page(browser, width=1440, offer=True, seed=None):
            ctx = browser.new_context(viewport={{"width": width, "height": 900}})
            calls = {{"ingest": 0, "outside": [], "user": USER}}
            seeded = dict(seed or {{}})
            # Without the server signal the response looks like every older mocked workspace.
            workspace = dict(WORKSPACE)
            if offer:
                workspace["listing_import"] = {{"first_visit": True}}
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
                        "user": calls["user"],
                        "usage": {{"plan": "starter", "used": 0, "limit": 3, "remaining": 3,
                                  "resets_at": None}},
                        "live_available": True,
                    }})
                if "/api/v1/account/workspace" in url:
                    return reply(route, WORKSPACE_B if calls["user"] is USER_B else workspace)
                if url.endswith("/api/v1/onboarding/status"):
                    return reply(route, {{
                        "completed": True, "completed_at": "2026-11-16T18:00:00Z",
                        "used_run": False, "plan": "starter", "runs_remaining": 3,
                    }})
                if url.endswith("/api/v1/ingest-storefront"):
                    calls["ingest"] += 1
                    site = (route.request.post_data_json or {{}}).get("website_url", "")
                    if site.startswith("https://oakandpine.example"):
                        return reply(route, LISTINGS_B)
                    assert site.startswith("https://fernandkiln.example"), site
                    return reply(route, LISTINGS)
                if url.endswith("/api/v1/product-reference"):
                    link = (route.request.post_data_json or {{}}).get("url", "")
                    title = "Speckled Stoneware Mug" if link.endswith("/mug") else "Ash Glaze Bowl"
                    if "oakandpine" in link:
                        title = "Turned Oak Bowl"
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
                if url.endswith("/api/v1/daily-brief") and "workspace=own" in route.request.url:
                    # The real route needs a server-side session this fixture does not fake.
                    move = {{"title": "Share one thing you made this week",
                             "reason": "Uses your saved setup.", "href": "/create?workspace=own",
                             "impact": "medium",
                             "recommendation": {{"id": "share",
                                                "title": "Share one thing you made this week"}}}}
                    return reply(route, {{
                        "business_name": "Fern & Kiln", "items": [], "move": move, "focus": move,
                        "action_items": [move], "overnight_changes": [], "overnight_note": "",
                        "trends": [], "source": "Saved context. 0 runs spent.",
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

        def tried(page, user=USER):
            key = TRIED_PREFIX + user["id"]
            return page.evaluate("localStorage.getItem(" + json.dumps(key) + ")")

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)

            # 1. First visit on a device (two of them here): /today starts on the seller's first
            #    listing, unasked. The account finished setup earlier; nothing local says so.
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
                assert tried(page) == "today"
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
                assert tried(page) == "today,create"
                no_overflow(page, "/create " + str(width))
                page.goto(BASE + "/create", wait_until="networkidle")
                page.wait_for_timeout(400)
                assert calls["ingest"] == 2
                assert not errors, errors
                assert not calls["outside"], calls["outside"]
                ctx.close()

            # 3. The server does not say so: neither editor scans, saved shop website or not.
            ctx, page, calls, errors = open_page(browser, offer=False)
            page.goto(BASE + "/today", wait_until="networkidle")
            page.wait_for_timeout(400)
            page.goto(BASE + "/create", wait_until="networkidle")
            page.wait_for_timeout(400)
            assert calls["ingest"] == 0
            assert tried(page) is None
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

            # 5. Sample workspace open: nothing is scanned and nothing is recorded as tried.
            ctx, page, calls, errors = open_page(browser)
            for path in ("/today?workspace=sample", "/create?workspace=sample"):
                page.goto(BASE + path, wait_until="networkidle")
                page.wait_for_timeout(400)
                mode = page.evaluate("document.documentElement.dataset.museMode")
                assert mode == "account_sample"
            assert calls["ingest"] == 0
            assert tried(page) is None
            assert not errors, errors
            ctx.close()

            # 6. The seller already has their own item on this device: it is left alone for good.
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
            assert tried(page) == "today"
            assert not errors, errors
            ctx.close()

            # 7. The seller opens the sample shop while the scan is still running: the late
            #    result lands nowhere, and the import runs once they are back in their workspace.
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
            assert tried(page) is None
            page.unroute("**/api/v1/ingest-storefront")
            page.evaluate("window.museModes.goToOwnWorkspace()")
            page.wait_for_function(
                "document.getElementById('itemTitle').textContent === 'Speckled Stoneware Mug'"
                " && document.getElementById('notice').textContent.startsWith('Started with')",
                timeout=15000,
            )
            assert calls["ingest"] == 1
            assert tried(page) == "today"
            assert not errors, errors
            assert not calls["outside"], calls["outside"]
            ctx.close()

            # 8. Another account signs in on the same tab while the first account's scan is
            #    still running. The first scan is dropped: whatever it returns lands nowhere and
            #    is recorded for neither account. The second account gets its own listings.
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
            calls["user"] = USER_B
            page.evaluate("window.museAccount.refresh()")
            page.wait_for_function(
                "window.museAccount.getSnapshot().user?.id === 'u-oak-456'"
                " && document.getElementById('notice').textContent"
                ".startsWith('Looking for your listings on oakandpine.example')",
                timeout=15000,
            )
            assert len(held) == 2
            sites = [(r.request.post_data_json or {{}}).get("website_url", "") for r in held]
            assert sites[0].startswith("https://fernandkiln.example"), sites
            assert sites[1].startswith("https://oakandpine.example"), sites
            try:
                held[0].fulfill(
                    status=200, content_type="application/json", body=json.dumps(LISTINGS)
                )
            except Exception:
                pass  # Already cancelled by the page when the account changed.
            page.wait_for_timeout(500)
            shown = json.dumps(page.evaluate("window.museDailySnapshot()"))
            assert "Speckled" not in shown and "fernandkiln" not in shown, shown
            assert page.locator("#importItems button").count() == 0
            assert tried(page) is None and tried(page, USER_B) is None
            held[1].fulfill(
                status=200, content_type="application/json", body=json.dumps(LISTINGS_B)
            )
            page.wait_for_function(
                "document.getElementById('itemTitle').textContent === 'Turned Oak Bowl'"
                " && document.getElementById('notice').textContent.startsWith('Started with')",
                timeout=15000,
            )
            shown = json.dumps(page.evaluate("window.museDailySnapshot()"))
            assert "oakandpine.example" in shown and "Speckled" not in shown, shown
            assert page.locator("#importItems button").count() == 1
            assert tried(page, USER_B) == "today" and tried(page) is None
            assert not errors, errors
            assert not calls["outside"], calls["outside"]
            ctx.close()

            # 9. Muse refuses the scan (too many from this connection, 429, see scan_guard.py):
            #    each editor shows Muse's own words, records nothing as tried, and the next visit
            #    scans again and brings the listing in.
            REFUSAL = (
                "Muse has checked a lot of websites from your connection in the last few "
                "minutes. Try again in 4 minutes, or enter the details yourself."
            )
            ctx, page, calls, errors = open_page(browser)
            refused = []

            def refuse(route):
                refused.append(route.request.url)
                route.fulfill(
                    status=429, content_type="application/json",
                    headers={{"Retry-After": "200"}}, body=json.dumps({{"detail": REFUSAL}}),
                )

            page.route("**/api/v1/ingest-storefront", refuse)
            page.goto(BASE + "/today", wait_until="domcontentloaded")
            page.wait_for_function(
                "document.getElementById('notice').textContent === " + json.dumps(REFUSAL),
                timeout=15000,
            )
            assert page.locator("#importStatus").inner_text() == REFUSAL
            assert tried(page) is None
            page.goto(BASE + "/create", wait_until="domcontentloaded")
            page.wait_for_function(
                "document.getElementById('importHint').textContent === " + json.dumps(REFUSAL),
                timeout=15000,
            )
            assert tried(page) is None
            assert len(refused) == 2
            page.unroute("**/api/v1/ingest-storefront")
            page.goto(BASE + "/today", wait_until="domcontentloaded")
            page.wait_for_function(
                "document.getElementById('itemTitle').textContent === 'Speckled Stoneware Mug'"
                " && document.getElementById('notice').textContent.startsWith('Started with')",
                timeout=15000,
            )
            assert tried(page) == "today"
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


def test_the_wizard_saves_the_shop_and_the_first_today_visit_uses_it_e2e(
    live_server_url: str,
) -> None:
    """The whole path in one browser: nothing is scanned before setup; once the real wizard has
    saved the shop website, the first /today visit starts on the seller's listing.

    The mocked workspace applies the server's rule (a saved shop website), which
    test_workspace_read_says_when_a_shop_website_is_saved pins against the real route.
    """
    python_bin = _find_playwright_python()
    if not python_bin:
        pytest.skip("Playwright runtime not installed")

    runner_script = textwrap.dedent(
        f"""
        import json
        from playwright.sync_api import sync_playwright

        BASE = "{live_server_url}"
        USER = {{"id": "u-new-7", "email": "maker@mountainpottery.example", "email_verified": True}}
        TRIED = "muse.autoimport.tried.v1:" + USER["id"]
        store = {{"document": {{}}, "version": 1, "owner_id": USER["id"]}}

        def with_signal(ws):
            urls = (ws["document"].get("onboarding") or {{}}).get("shop_urls") or []
            saved = any(isinstance(u, str) and u.strip() for u in urls)
            return {{**ws, "listing_import": {{"first_visit": saved}}}}
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
                return reply(route, with_signal(store))
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

            # Signed in, nothing set up yet: the editor has no shop website to look at.
            page.goto(BASE + "/today", wait_until="networkidle")
            assert page.evaluate("document.documentElement.dataset.museMode") == "account_own"
            page.wait_for_timeout(400)
            assert calls["ingest"] == 0
            assert page.evaluate("localStorage.getItem(" + json.dumps(TRIED) + ")") is None

            page.goto(BASE + "/welcome")
            page.wait_for_selector("#wkStep1:not([hidden])", timeout=10000)
            page.fill("#wkShopUrl", "mountainpottery.example")
            page.fill("#wkBusinessName", "Mountain Pottery Studio")
            page.click("#wkScanShopBtn")
            page.wait_for_selector("#wkShopProof:not([hidden])")
            page.click("#wkStep1NextBtn")
            page.wait_for_selector("#wkStep2:not([hidden])")
            page.click("#wkStep2NextBtn")
            page.wait_for_selector("#wkStep3:not([hidden])")
            page.click("#wkStep3NextBtn")
            page.wait_for_selector("#wkStep4:not([hidden])")
            page.click("#wkStep4FinishBtn")
            page.wait_for_selector("#wkStepDone:not([hidden])")
            saved_urls = store["document"]["onboarding"]["shop_urls"]
            assert saved_urls == ["https://mountainpottery.example/"], saved_urls
            # The wizard itself leaves nothing on the device for the editors.
            assert page.evaluate(
                "Object.keys(localStorage).filter((k) => k.includes('autoimport')).length"
            ) == 0
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
            assert page.evaluate("localStorage.getItem(" + json.dumps(TRIED) + ")") == "today"
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
