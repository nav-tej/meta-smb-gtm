"""Offline real Chromium E2E tests for Promotion Guidance & 5-click Editor Handoff."""

from __future__ import annotations

import base64
import io
import json
import os
import shutil
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path
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
def promotion_guidance_server(monkeypatch: pytest.MonkeyPatch):
    """Run real FastAPI app with two fixture accounts and zero live provider calls."""
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
                    "selling_goal": "sales",
                    "minutes_per_week": 60,
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
                    "selling_goal": "story",
                    "minutes_per_week": 90,
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
                    price_hint="",
                ),
            ],
            ["https://wildmeadow.test/sitemap.xml"],
        )

    img_1 = _png_data_url(1200, 900, (35, 110, 75))
    img_2 = _png_data_url(960, 720, (170, 95, 45))

    class FakeProductReferenceService:
        async def read(self, raw_url: str) -> ProductReference:
            return ProductReference(
                url="https://wildmeadow.test/prints/botanical-linocut",
                title="Botanical Linocut Print",
                description="Hand-pulled botanical linocut on cotton rag.",
                price_hint="",
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
                ],
                source_note="Photo and details imported from the public listing.",
            )

    def spy_meta(*args: Any, **kwargs: Any):
        muse_calls["count"] += 1
        raise AssertionError("Paid/provider Muse call unexpectedly triggered during offline E2E!")

    monkeypatch.setenv("DEMO_MODE", "true")
    monkeypatch.setenv("ACCOUNTS_REQUIRED", "true")
    monkeypatch.setenv("META_MODEL_API_KEY", "")
    monkeypatch.setenv("DEMO_KEY", "")
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
        yield f"http://127.0.0.1:{port}", muse_calls, stores
    finally:
        app.dependency_overrides.clear()
        server.should_exit = True
        thread.join(timeout=2)


def test_promotion_guidance_5_click_handoff_truthfulness_and_isolation_e2e(
    promotion_guidance_server: tuple[str, dict[str, int], dict[str, Any]],
    tmp_path: Path,
) -> None:
    """Verify truthful guidance, handoff->PNG clicks, reload/cloud persistence, and isolation."""
    pw_python = _find_playwright_python()
    if pw_python is None:
        pytest.skip("Playwright Python runtime unavailable")

    from tests.e2e_helpers import with_cpu_throttle

    base_url, muse_calls, stores = promotion_guidance_server

    script = with_cpu_throttle(
        f"""
        import json
        from pathlib import Path
        from PIL import Image
        from playwright.sync_api import sync_playwright

        BASE = {base_url!r}
        OUT = Path({str(tmp_path)!r})

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            ctx = browser.new_context(
                viewport={{"width": 1440, "height": 900}}, accept_downloads=True
            )
            ctx.add_cookies([{{
                "name": "muse_e2e_user",
                "value": "user-a",
                "url": BASE,
            }}])
            page = ctx.new_page()

            # 1. Guest Sample mode: /create?workspace=sample renders sample candidates & exports PNG
            ctx_guest = browser.new_context(
                viewport={{"width": 1440, "height": 900}}, accept_downloads=True
            )
            pg = ctx_guest.new_page()
            pg.goto(f"{{BASE}}/create?workspace=sample", wait_until="domcontentloaded")
            pg.wait_for_selector("#imgSrcSampleBtn:not([hidden])")
            pg.wait_for_selector('#imageCandidatesGrid [data-use-image-id]')
            grid_txt = pg.text_content("#imageCandidatesGrid") or ""
            assert "Original artwork" in grid_txt, grid_txt
            assert "Saved generated ad examples" in grid_txt, grid_txt
            pg.locator('#imageCandidatesGrid [data-use-image-id]').first.click()
            pg.locator("#nextButton").click()
            pg.locator("#nextButton").click()
            pg.locator("#reviewed").check()
            with pg.expect_download() as dl_sample_info:
                pg.locator("#nextButton").click()
                pg.locator("#downloadFeed").click()
            sample_png = OUT / "pg-sample-exported-1440.png"
            dl_sample_info.value.save_as(str(sample_png))
            with Image.open(sample_png) as im:
                assert im.size == (1080, 1350), im.size
            ctx_guest.close()

            # 2. Desktop own-account (user-a): no photo -> import -> select -> handoff -> PNG
            page.goto(f"{{BASE}}/", wait_until="domcontentloaded")
            page.wait_for_selector("#smShowImproveTabBtn", state="visible", timeout=15000)
            page.click("#smShowImproveTabBtn")
            page.wait_for_selector("#loop-improve ol.jr-recos li[data-sm-reco-id]")
            first_card = page.locator("#loop-improve ol.jr-recos li[data-sm-reco-id]").first
            card_text = first_card.inner_text()
            assert "Suggested starting approach" in card_text, card_text
            assert "Fresh Muse analysis" not in card_text, card_text
            assert "Missing facts:" in card_text, card_text
            page.screenshot(path=str(OUT / "pg-home-1440.png"), full_page=False)

            # Click 1: Make ad -> /create?sm_handoff=...
            clicks = 0
            first_card.locator("a", has_text="Make ad").click()
            clicks += 1
            page.wait_for_url("**/create**")
            page.wait_for_function(
                "() => document.getElementById('nextButton')?.textContent?.trim()"
                " === 'Make it yours →'"
            )

            # Click 2: Import shop products to open/populate image candidates
            page.fill("#shopUrl", "https://wildmeadow.test")
            page.click("#importProducts")
            clicks += 1
            page.wait_for_selector('#imageCandidatesGrid [data-use-image-id="web-2"]')

            # Click 3: Select existing image candidate
            page.click('#imageCandidatesGrid [data-use-image-id="web-2"]')
            clicks += 1
            page.wait_for_function(
                "() => (document.getElementById('productImage')?.getAttribute('src') || '')"
                ".startsWith('data:image/')"
            )

            # Click 4: Next -> skips Step 1 ("Your idea") and lands on Step 2 ("Make it yours")
            next_btn = page.locator("#nextButton")
            assert next_btn.inner_text().strip() == "Make it yours →", next_btn.inner_text()
            next_btn.click()
            clicks += 1
            page.wait_for_selector('#handoffGuidanceBox:not([hidden])')
            assert page.locator('[data-panel="2"]').is_visible()
            badge_txt = page.locator("#handoffProvenanceBadge").inner_text().strip()
            assert badge_txt == "Suggested starting approach"
            place_txt = page.locator("#handoffPlacementNote").inner_text()
            assert "App export preset (not verified Meta policy)" in place_txt
            assert page.locator("#handoffMissingFacts").is_visible()
            assert page.locator("#audienceHypothesis").is_visible()

            # Text edits (counted separately from navigation/picker/review/export clicks)
            page.fill("#headline", "Botanical Linocut Studio Proof")
            page.fill("#audienceHypothesis", "Art collectors buying botanical prints")
            page.screenshot(path=str(OUT / "pg-editor-step2-1440.png"), full_page=False)

            # Click 5: Tick #reviewed
            page.locator("#reviewed").check()
            clicks += 1

            # Click 6: Quick export feed PNG directly from Step 2
            quick_btn = page.locator("#quickExportFeedBtn")
            assert quick_btn.is_visible()
            assert quick_btn.bounding_box()["height"] >= 44
            with page.expect_download() as dl_info:
                quick_btn.click()
                clicks += 1
            dl = dl_info.value
            exported_path = OUT / "pg-exported-1440.png"
            dl.save_as(str(exported_path))
            with Image.open(exported_path) as im:
                assert im.size == (1080, 1350), im.size
            assert clicks == 6, f"Expected 6 clicks in no-photo candidate flow, got {{clicks}}"

            # Reload SAME ?sm_handoff=... URL: consumed handoff must not overwrite edits
            page.reload(wait_until="domcontentloaded")
            page.wait_for_function(
                "() => document.getElementById('headline')?.value"
                " === 'Botanical Linocut Studio Proof'"
            )
            page.wait_for_selector('#handoffGuidanceBox:not([hidden])')
            aud_after_reload = page.locator("#audienceHypothesis").input_value()
            assert aud_after_reload == "Art collectors buying botanical prints", aud_after_reload

            # Save to account, then load in a fresh context (empty localStorage) for user-a
            page.click("#saveAccountDraft")
            page.wait_for_function(
                "() => (document.getElementById('draftStatus')?.textContent || '')"
                ".includes('Saved to your account')"
            )
            ctx_a2 = browser.new_context(viewport={{"width": 1440, "height": 900}})
            ctx_a2.add_cookies([{{
                "name": "muse_e2e_user",
                "value": "user-a",
                "url": BASE,
            }}])
            page_a2 = ctx_a2.new_page()
            page_a2.goto(f"{{BASE}}/create", wait_until="domcontentloaded")
            page_a2.wait_for_function(
                "() => document.documentElement.dataset.museMode === 'account_own'"
            )
            page_a2.wait_for_selector("#loadAccountDraft:not([disabled])")
            page_a2.click("#loadAccountDraft")
            page_a2.wait_for_function(
                "() => document.getElementById('headline')?.value"
                " === 'Botanical Linocut Studio Proof'"
            )
            page_a2.wait_for_selector('#handoffGuidanceBox:not([hidden])')
            aud_cloud = page_a2.locator("#audienceHypothesis").input_value()
            assert aud_cloud == "Art collectors buying botanical prints", aud_cloud
            ctx_a2.close()

            # Verify no horizontal overflow at 1440px
            overflow_1440 = page.evaluate(
                "document.documentElement.scrollWidth > window.innerWidth"
            )
            assert not overflow_1440

            # 2. Invalid / wrong-owner sm_handoff safe recovery (keeps existing draft)
            page.goto(
                f"{{BASE}}/create?sm_handoff=sm_wrong_owner_or_expired",
                wait_until="domcontentloaded",
            )
            page.wait_for_selector("#notice:not([hidden])")
            notice_text = page.locator("#notice").inner_text()
            assert "expired, invalid, or belongs to a different account" in notice_text, notice_text
            hl_val = page.locator("#headline").input_value()
            assert hl_val == "Botanical Linocut Studio Proof", hl_val
            assert page.locator("#handoffGuidanceBox").is_hidden(), "guidance should be hidden"
            next_txt = page.locator("#nextButton").inner_text().strip()
            assert next_txt == "Ready to share →", next_txt

            # 4. Sample mode /create?workspace=sample does not mutate user-a's own draft
            page.goto(f"{{BASE}}/create?workspace=sample", wait_until="domcontentloaded")
            page.wait_for_selector('#imageCandidatesGrid [data-use-image-id]')
            page.goto(f"{{BASE}}/create", wait_until="domcontentloaded")
            page.wait_for_function(
                "() => document.getElementById('headline')?.value"
                " === 'Botanical Linocut Studio Proof'"
            )

            # 4. Second distinct own-account fixture (user-b Cedar Kiln Ceramics) isolation
            ctx_b = browser.new_context(
                viewport={{"width": 375, "height": 844}}, accept_downloads=True
            )
            ctx_b.add_cookies([{{
                "name": "muse_e2e_user",
                "value": "user-b",
                "url": BASE,
            }}])
            page_b = ctx_b.new_page()
            page_b.goto(f"{{BASE}}/", wait_until="domcontentloaded")
            page_b.wait_for_selector("#smShowImproveTabBtn", state="visible", timeout=15000)
            page_b.click("#smShowImproveTabBtn")
            page_b.wait_for_selector("#loop-improve ol.jr-recos li[data-sm-reco-id]")
            card_b = page_b.locator("#loop-improve ol.jr-recos li[data-sm-reco-id]").first
            assert "Suggested starting approach" in card_b.inner_text()
            assert not page_b.evaluate(
                "document.documentElement.scrollWidth > window.innerWidth"
            ), "375px home overflow"
            page_b.screenshot(path=str(OUT / "pg-home-375.png"), full_page=False)

            card_b.locator("a", has_text="Make ad").click()
            page_b.wait_for_url("**/create**")
            page_b.wait_for_function(
                "() => document.getElementById('nextButton')?.textContent?.trim()"
                " === 'Make it yours →'"
            )
            assert page_b.locator("#headline").input_value() != "Botanical Linocut Studio Proof"
            page_b.fill("#shopUrl", "https://cedarkiln.test")
            page_b.click("#importProducts")
            page_b.wait_for_selector('#imageCandidatesGrid [data-use-image-id="web-1"]')
            page_b.click('#imageCandidatesGrid [data-use-image-id="web-1"]')
            page_b.locator("#nextButton").click()
            page_b.wait_for_selector('#handoffGuidanceBox:not([hidden])')
            aud_b = page_b.locator("#audienceHypothesis").input_value()
            assert "Art collectors buying botanical prints" not in aud_b, aud_b
            assert not page_b.evaluate(
                "document.documentElement.scrollWidth > window.innerWidth"
            ), "375px editor overflow"
            assert page_b.locator("#quickExportFeedBtn").bounding_box()["height"] >= 44
            page_b.screenshot(path=str(OUT / "pg-editor-step2-375.png"), full_page=False)

            print(json.dumps({{"clicks": clicks, "exported_size": [1080, 1350], "status": "ok"}}))
            ctx_b.close()
            ctx.close()
            browser.close()
        """
    )

    proc = subprocess.run(
        [pw_python, "-c", script],
        capture_output=True,
        text=True,
        check=False,
        timeout=150,
    )
    assert proc.returncode == 0, f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
    assert muse_calls["count"] == 0
    # Verify draft-only audience edit was NOT written to account-wide seller memory
    seller_doc_json = json.dumps(stores["user-a"]["document"].get("seller_memory", {}))
    assert "Art collectors buying botanical prints" not in seller_doc_json
