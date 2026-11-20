"""Offline real Chromium E2E tests for Shop & Artist Image Suggestions."""

from __future__ import annotations

import base64
import io
import json
import os
import shutil
import socket
import subprocess
import sys
import textwrap
import threading
import time
from typing import Any

import pytest
import uvicorn
from fastapi import HTTPException
from PIL import Image

from src.api.main import app
from src.api.product_reference import get_product_reference_service
from src.models.intel import SitemapEntry
from src.services.accounts import AccountSession
from src.services.product_reference import (
    ProductImageCandidate,
    ProductReference,
    ProductReferenceError,
)


def _find_playwright_python() -> str | None:
    for candidate in (sys.executable, "/usr/bin/python3", shutil.which("python3") or ""):
        if not candidate or not os.path.exists(candidate):
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


def _png_data_url(width: int, height: int, color: tuple[int, int, int]) -> str:
    buf = io.BytesIO()
    Image.new("RGB", (width, height), color).save(buf, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode("ascii")


@pytest.fixture
def shop_images_server(monkeypatch: pytest.MonkeyPatch):
    """Run real FastAPI app with multi-account workspace and mocked ProductReferenceService."""
    muse_calls = {"count": 0}
    stores: dict[str, dict[str, Any]] = {
        "user-a": {
            "document": {
                "onboarding": {
                    "business_name": "Wild Meadow Press",
                    "website_url": "https://wildmeadow.test",
                    "shop_urls": ["https://wildmeadow.test"],
                    "completed_at": "2026-11-10T10:00:00Z",
                    "competitors": [],
                }
            },
            "version": 1,
            "owner_id": "user-a",
        },
        "user-b": {
            "document": {
                "onboarding": {
                    "business_name": "Cedar Kiln Ceramics",
                    "website_url": "https://cedarkiln.test",
                    "shop_urls": ["https://cedarkiln.test"],
                    "completed_at": "2026-11-10T10:00:00Z",
                    "competitors": [],
                }
            },
            "version": 1,
            "owner_id": "user-b",
        },
    }
    accounts = {
        "user-a": AccountSession(
            user_id="user-a",
            email="watercolor@wildmeadow.test",
            email_verified=True,
            access_token="tok-a",
            session_id=None,
        ),
        "user-b": AccountSession(
            user_id="user-b",
            email="ceramics@cedarkiln.test",
            email_verified=True,
            access_token="tok-b",
            session_id=None,
        ),
    }

    async def fake_resolve(request: Any, _response: Any = None, require_verified: bool = False):
        uid = request.cookies.get("muse_e2e_user") or request.headers.get("x-test-user")
        if not uid or uid not in accounts:
            if require_verified:
                raise HTTPException(401, "Sign in required")
            return None
        return accounts[uid]

    async def fake_load(account: AccountSession) -> dict[str, Any]:
        slot = stores[account.user_id]
        return {
            "document": json.loads(json.dumps(slot["document"])),
            "version": int(slot["version"]),
            "owner_id": account.user_id,
        }

    async def fake_save(
        account: AccountSession,
        doc: dict[str, Any],
        expected_version: Any = None,
        expected_owner: Any = None,
    ) -> dict[str, Any]:
        if expected_owner and expected_owner != account.user_id:
            raise HTTPException(409, "Account mismatch")
        slot = stores[account.user_id]
        if expected_version is not None and int(expected_version) != int(slot["version"]):
            raise HTTPException(409, "Version conflict")
        slot["document"] = json.loads(json.dumps(doc))
        slot["version"] += 1
        return {
            "document": json.loads(json.dumps(slot["document"])),
            "version": slot["version"],
            "owner_id": account.user_id,
        }

    async def fake_snapshot(account: AccountSession | None) -> dict[str, Any]:
        if account is None:
            return {"configured": True, "user": None, "usage": None, "live_available": False}
        return {
            "configured": True,
            "user": {"id": account.user_id, "email": account.email, "email_verified": True},
            "usage": {"plan": "starter", "used": 0, "limit": 3, "remaining": 3},
            "runs_remaining": 3,
            "live_available": True,
        }

    async def fake_collect(url: str, **_kwargs: Any):
        return (
            [
                SitemapEntry(
                    loc="https://wildmeadow.test/prints/botanical-linocut",
                    title="Botanical Linocut Print",
                    bucket="products",
                    price_hint="$48",
                ),
                SitemapEntry(
                    loc="https://wildmeadow.test/prints/blocked-page",
                    title="Blocked Gallery Page",
                    bucket="products",
                    price_hint="",
                ),
            ],
            ["https://wildmeadow.test/sitemap.xml"],
        )

    img_1 = _png_data_url(1200, 900, (35, 110, 75))
    img_2 = _png_data_url(960, 720, (170, 95, 45))
    img_low = _png_data_url(400, 300, (70, 90, 150))

    class FakeProductReferenceService:
        async def read(self, raw_url: str) -> ProductReference:
            if "blocked-page" in raw_url:
                raise ProductReferenceError("This page is blocked by the site's robots.txt rules.")
            if "empty-page" in raw_url:
                return ProductReference(
                    url=raw_url,
                    title="Empty Page",
                    description="No images found",
                    price_hint="$35",
                    image_data_url=None,
                    image_candidates=[],
                    source_note="Review details and add its photo.",
                )
            return ProductReference(
                url="https://wildmeadow.test/prints/botanical-linocut",
                title="Botanical Linocut Print",
                description="Hand-pulled botanical linocut on cotton rag.",
                price_hint="$48",
                image_data_url=img_1,
                image_width=1200,
                image_height=900,
                is_low_res=False,
                image_candidates=[
                    ProductImageCandidate(
                        id="web-1",
                        image_data_url=img_1,
                        source_url="https://wildmeadow.test/prints/botanical-linocut",
                        image_url="https://wildmeadow.test/img/botanical-1.png",
                        title="Botanical Linocut — Full sheet",
                        width=1200,
                        height=900,
                        is_low_res=False,
                        provenance="website",
                    ),
                    ProductImageCandidate(
                        id="web-2",
                        image_data_url=img_2,
                        source_url="https://wildmeadow.test/prints/botanical-linocut",
                        image_url="https://wildmeadow.test/img/botanical-2.png",
                        title="Botanical Linocut — Studio angle",
                        width=960,
                        height=720,
                        is_low_res=False,
                        provenance="website",
                    ),
                    ProductImageCandidate(
                        id="web-3",
                        image_data_url=img_low,
                        source_url="https://wildmeadow.test/prints/botanical-linocut",
                        image_url="https://wildmeadow.test/img/botanical-low.png",
                        title="Botanical Linocut — Thumbnail preview",
                        width=400,
                        height=300,
                        is_low_res=True,
                        provenance="website",
                    ),
                ],
                source_note="Photo and details imported from the public listing.",
            )

    def spy_meta(*args: Any, **kwargs: Any):
        muse_calls["count"] += 1
        raise AssertionError("Paid/provider Muse call unexpectedly triggered during offline E2E!")

    monkeypatch.setenv("DEMO_MODE", "true")
    monkeypatch.setenv("ACCOUNTS_REQUIRED", "true")
    monkeypatch.setenv("META_MODEL_API_KEY", "")
    monkeypatch.setattr("src.api.accounts.resolve_account", fake_resolve)
    monkeypatch.setattr("src.services.accounts.resolve_account", fake_resolve)
    monkeypatch.setattr("src.api.accounts.snapshot", fake_snapshot)
    monkeypatch.setattr("src.api.onboarding.snapshot", fake_snapshot)
    monkeypatch.setattr("src.api.accounts.load_workspace", fake_load)
    monkeypatch.setattr("src.api.accounts.save_workspace", fake_save)
    monkeypatch.setattr("src.api.intel.collect_entries", fake_collect)
    monkeypatch.setattr("src.clients.meta.get_meta_client", spy_meta)
    app.dependency_overrides[get_product_reference_service] = lambda: FakeProductReferenceService()

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()

    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    for _ in range(50):
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                break
        except OSError:
            time.sleep(0.05)

    try:
        yield f"http://127.0.0.1:{port}", muse_calls, img_2
    finally:
        app.dependency_overrides.clear()
        server.should_exit = True
        thread.join(timeout=2)


def test_shop_image_suggestions_sample_own_fallback_isolation_and_export_e2e(
    shop_images_server: tuple[str, dict[str, int], str],
) -> None:
    """Verify sample mode, non-sample selection, fallback, race isolation, and exports."""
    pw_python = _find_playwright_python()
    if pw_python is None:
        pytest.skip("Playwright Python runtime unavailable")

    base_url, muse_calls, img_2 = shop_images_server

    late_payload_a = json.dumps(
        {
            "url": "https://wildmeadow.test/botanical",
            "title": "Botanical Linocut",
            "description": "Hand-pulled print",
            "price_hint": "$48",
            "image_data_url": img_2,
            "image_width": 900,
            "image_height": 900,
            "is_low_res": False,
            "image_candidates": [
                {
                    "id": "late-a-1",
                    "image_data_url": img_2,
                    "source_url": "https://wildmeadow.test/botanical",
                    "image_url": "https://wildmeadow.test/botanical.png",
                    "title": "Late Account A Print",
                    "width": 900,
                    "height": 900,
                    "is_low_res": False,
                    "provenance": "website",
                }
            ],
        }
    )

    script = textwrap.dedent(
        f"""
        import json
        from PIL import Image
        from playwright.sync_api import sync_playwright

        base_url = {json.dumps(base_url)}
        img_2 = {json.dumps(img_2)}
        late_payload_a = {json.dumps(late_payload_a)}

        def assert_no_overflow(page, label):
            dims = page.evaluate(
                "() => ({{sw: document.documentElement.scrollWidth, iw: window.innerWidth}})"
            )
            assert dims["sw"] <= dims["iw"] + 2, f"{{label}} horizontal overflow: {{dims}}"

        def set_cookie(ctx, uid):
            if uid is None:
                ctx.clear_cookies()
            else:
                ctx.add_cookies([{{
                    "name": "muse_e2e_user",
                    "value": uid,
                    "url": base_url,
                }}])

        def first_visit_import_done(ctx):
            # The editors bring in a saved shop's listings once per account on a device
            # (tests/test_first_visit_import_e2e.py). The fakes here return the same listing for
            # every shop, so these checks run on a device where that has already happened and
            # each account starts from its placeholder draft, as before.
            ctx.add_init_script(
                "for (const uid of ['user-a', 'user-b']) "
                "localStorage.setItem('muse.autoimport.tried.v1:' + uid, 'today,create');"
            )

        with sync_playwright() as p:
            browser = p.chromium.launch()
            errors = []

            # 1. Guest Sample Mode (375px mobile): select -> crop -> export PNG
            ctx_m = browser.new_context(
                viewport={{"width": 375, "height": 844}}, accept_downloads=True
            )
            pm = ctx_m.new_page()
            pm.on("pageerror", lambda e: errors.append(str(e)))
            pm.goto(f"{{base_url}}/create?workspace=sample", wait_until="domcontentloaded")
            pm.wait_for_selector("#imgSrcSampleBtn:not([hidden])")
            assert_no_overflow(pm, "sample /create 375px")
            grid_txt = pm.text_content("#imageCandidatesGrid") or ""
            assert "Original artwork" in grid_txt
            assert "Saved generated ad examples" in grid_txt
            pm.click('#imageCandidatesGrid [data-use-image-id="sample-orig-naam-japo"]')
            pm.click('[data-step="2"]')
            pm.fill("#headline", "Naam Japo Sample Print")
            pm.click("#creatorCropToggle")
            pm.fill("#creatorFrameX", "20")
            pm.check("#reviewed")
            pm.click('[data-step="3"]')
            with pm.expect_download() as dl:
                pm.click("#downloadFeed")
            with Image.open(dl.value.path()) as exported:
                assert exported.size == (1080, 1350)
            with pm.expect_download() as dl_story:
                pm.click("#downloadStory")
            with Image.open(dl_story.value.path()) as exported_story:
                assert exported_story.size == (1080, 1920)
            with pm.expect_download() as dl_sq:
                pm.click("#downloadSquare")
            with Image.open(dl_sq.value.path()) as exported_sq:
                assert exported_sq.size == (1080, 1080)
            ctx_m.close()

            # 2. Non-sample artist on /create (1440px): website -> 2nd image -> export -> reload
            ctx_d = browser.new_context(
                viewport={{"width": 1440, "height": 900}}, accept_downloads=True
            )
            set_cookie(ctx_d, "user-a")
            first_visit_import_done(ctx_d)
            pd = ctx_d.new_page()
            pd.on("pageerror", lambda e: errors.append(str(e)))
            pd.goto(f"{{base_url}}/create", wait_until="domcontentloaded")
            pd.wait_for_selector("#shopUrl")
            assert pd.evaluate("document.getElementById('imgSrcSampleBtn')?.hidden === true")
            assert_no_overflow(pd, "own /create 1440px")

            pd.fill("#shopUrl", "https://wildmeadow.test")
            pd.click("#importProducts")
            pd.wait_for_selector('#imageCandidatesGrid [data-use-image-id="web-2"]')
            cand_text = pd.text_content("#imageCandidatesGrid") or ""
            assert "1200 × 900 px" in cand_text
            assert "Low-resolution web preview (400 × 300 px)" in cand_text
            assert "Sarabjit" not in cand_text

            # Explicitly choose SECOND image and confirm selection + copy
            pd.click('#imageCandidatesGrid [data-use-image-id="web-2"]')
            pd.fill("#productName", "Botanical Linocut Print")
            pd.click('[data-step="2"]')
            pd.fill("#headline", "Botanical Linocut Studio Edition")
            pd.click("#creatorCropToggle")
            pd.check("#reviewed")
            pd.click('[data-step="3"]')
            with pd.expect_download() as dl_own:
                pd.click("#downloadFeed")
            with Image.open(dl_own.value.path()) as exported_own:
                assert exported_own.size == (1080, 1350)

            snap_before = pd.evaluate("window.museCreatorSnapshot()")
            assert snap_before["image_meta"]["id"] == "web-2"
            assert snap_before["image_meta"]["sourceUrl"] == "https://wildmeadow.test/prints/botanical-linocut"
            assert snap_before["image_frame"]["fit"] == "cover"

            # Reload preserves chosen second image, source URL, and product without clobbering
            pd.reload(wait_until="domcontentloaded")
            pd.wait_for_selector("#headline")
            snap_after = pd.evaluate("window.museCreatorSnapshot()")
            assert snap_after["product"]["name"] == "Botanical Linocut Print"
            assert snap_after["image_meta"]["id"] == "web-2"
            assert snap_after["image_meta"]["sourceUrl"] == "https://wildmeadow.test/prints/botanical-linocut"
            pd.click('[data-step="0"]')
            pd.wait_for_selector("#productImage")
            assert pd.get_attribute("#productImage", "src") == img_2

            # 3. Repeated scan & blocked page fallback preserve existing photo & edits
            pd.click("#importProducts")
            pd.wait_for_selector('#importResults button.import-item')
            # Click blocked listing -> fallback copy while keeping img_2 & edited headline
            pd.locator('#importResults button.import-item', has_text="Blocked Gallery Page").click()
            pd.wait_for_function(
                "() => (document.getElementById('imagePickerStatus')?.textContent || '')"
                ".includes('retrieve an image from this page')"
            )
            assert pd.get_attribute("#productImage", "src") == img_2
            assert pd.input_value("#headline") == "Botanical Linocut Studio Edition"

            # 4. Today page (/today at 375px): website candidates + race isolation
            ctx_tm = browser.new_context(
                viewport={{"width": 375, "height": 844}}, accept_downloads=True
            )
            set_cookie(ctx_tm, "user-a")
            first_visit_import_done(ctx_tm)
            pt = ctx_tm.new_page()
            pt.on("pageerror", lambda e: errors.append(str(e)))
            pt.goto(f"{{base_url}}/today", wait_until="domcontentloaded")
            pt.wait_for_selector("#quickShopUrl")
            assert pt.evaluate("document.getElementById('todayImgSrcSampleBtn')?.hidden === true")
            assert_no_overflow(pt, "own /today 375px")

            # Hold Account A's /api/v1/product-reference while switching same-page to Account B
            held_today = []
            def hold_today_ref(route):
                if len(held_today) == 0:
                    held_today.append(route)
                else:
                    route.continue_()
            pt.route("**/api/v1/product-reference", hold_today_ref)
            pt.click("#quickFindItems")
            pt.wait_for_timeout(250)
            assert len(held_today) == 1
            # Same-page owner switch to user-b (no reload, no abort)
            set_cookie(ctx_tm, "user-b")
            pt.evaluate("window.museAccount.refresh()")
            pt.wait_for_function("window.museAccount?.getSnapshot?.()?.user?.id === 'user-b'")
            # Deliver Account A's late response while Account B is active
            try:
                held_today[0].fulfill(
                    status=200,
                    content_type="application/json",
                    body=late_payload_a,
                )
            except Exception:
                pass
            pt.wait_for_timeout(200)
            pt.unroute("**/api/v1/product-reference")
            snap_b = pt.evaluate("window.museDailySnapshot()")
            assert "Botanical Linocut" not in json.dumps(snap_b)
            today_grid_b = pt.text_content("#todayImageCandidatesGrid") or ""
            assert "Late Account A Print" not in today_grid_b
            assert snap_b["imageMeta"] is None

            # Same-page Own -> Sample mode switch on /today with late website response delivered
            held_today_mode = []
            def hold_today_mode_ref(route):
                if len(held_today_mode) == 0:
                    held_today_mode.append(route)
                else:
                    route.continue_()
            pt.route("**/api/v1/product-reference", hold_today_mode_ref)
            pt.fill("#quickShopUrl", "https://wildmeadow.test")
            pt.click("#quickFindItems")
            pt.wait_for_timeout(250)
            assert len(held_today_mode) == 1
            pt.evaluate("window.museModes.enterSampleMode({{ artwork: 'naam_japo' }})")
            pt.wait_for_selector("#todayImgSrcSampleBtn:not([hidden])")
            try:
                held_today_mode[0].fulfill(
                    status=200,
                    content_type="application/json",
                    body=late_payload_a,
                )
            except Exception:
                pass
            pt.wait_for_timeout(200)
            pt.unroute("**/api/v1/product-reference")
            today_grid_sample = pt.text_content("#todayImageCandidatesGrid") or ""
            assert "Late Account A Print" not in today_grid_sample
            assert "Original artwork" in today_grid_sample
            ctx_tm.close()

            # 5. Creator (/create) same-page delayed-response race isolation (A->B and Own->Sample)
            ctx_cr = browser.new_context(
                viewport={{"width": 1280, "height": 860}}, accept_downloads=True
            )
            set_cookie(ctx_cr, "user-a")
            first_visit_import_done(ctx_cr)
            pc = ctx_cr.new_page()
            pc.on("pageerror", lambda e: errors.append(str(e)))
            pc.goto(f"{{base_url}}/create", wait_until="domcontentloaded")
            pc.wait_for_selector("#shopUrl")
            pc.fill("#shopUrl", "https://wildmeadow.test")
            pc.click("#importProducts")
            pc.wait_for_selector("#importResults button.import-item")
            held_cr_acct = []
            def hold_cr_acct_ref(route):
                if len(held_cr_acct) == 0:
                    held_cr_acct.append(route)
                else:
                    route.continue_()
            pc.route("**/api/v1/product-reference", hold_cr_acct_ref)
            pc.locator("#importResults button.import-item").first.click()
            pc.wait_for_timeout(250)
            assert len(held_cr_acct) == 1
            set_cookie(ctx_cr, "user-b")
            pc.evaluate("window.museAccount.refresh()")
            pc.wait_for_function("window.museAccount?.getSnapshot?.()?.user?.id === 'user-b'")
            pc.fill("#productName", "Account B Product")
            try:
                held_cr_acct[0].fulfill(
                    status=200,
                    content_type="application/json",
                    body=late_payload_a,
                )
            except Exception:
                pass
            pc.wait_for_timeout(200)
            pc.unroute("**/api/v1/product-reference")
            assert pc.input_value("#productName") == "Account B Product"
            assert "Botanical Linocut" not in pc.input_value("#productName")
            assert "Late Account A Print" not in (pc.text_content("#imageCandidatesGrid") or "")
            assert pc.get_attribute("#productImage", "src") != img_2

            # Own -> Sample on /create while website candidate response is in-flight
            pc.evaluate("window.museModes.goToOwnWorkspace()")
            pc.wait_for_selector("#shopUrl")
            pc.fill("#shopUrl", "https://wildmeadow.test")
            pc.click("#importProducts")
            pc.wait_for_selector("#importResults button.import-item")
            held_cr_mode = []
            def hold_cr_mode_ref(route):
                if len(held_cr_mode) == 0:
                    held_cr_mode.append(route)
                else:
                    route.continue_()
            pc.route("**/api/v1/product-reference", hold_cr_mode_ref)
            pc.locator("#importResults button.import-item").first.click()
            pc.wait_for_timeout(250)
            assert len(held_cr_mode) == 1
            pc.evaluate("window.museModes.enterSampleMode({{ artwork: 'naam_japo' }})")
            pc.wait_for_selector("#imgSrcSampleBtn:not([hidden])")
            try:
                held_cr_mode[0].fulfill(
                    status=200,
                    content_type="application/json",
                    body=late_payload_a,
                )
            except Exception:
                pass
            pc.wait_for_timeout(200)
            pc.unroute("**/api/v1/product-reference")
            cr_sample_grid = pc.text_content("#imageCandidatesGrid") or ""
            assert "Late Account A Print" not in cr_sample_grid
            assert "Original artwork" in cr_sample_grid
            ctx_cr.close()

            assert not errors, f"Uncaught browser errors: {{errors}}"
            browser.close()
        """
    )

    res = subprocess.run(
        [pw_python, "-c", script],
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )
    assert res.returncode == 0, f"STDOUT:\n{res.stdout}\nSTDERR:\n{res.stderr}"
    assert muse_calls["count"] == 0
