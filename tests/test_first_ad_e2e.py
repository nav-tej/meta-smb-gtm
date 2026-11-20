"""Offline real Chromium E2E tests for 'Run your first ad' 4-step workflow."""

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
from pathlib import Path
from typing import Any

import pytest
import uvicorn
from fastapi import HTTPException
from PIL import Image

from src.api.main import app
from src.api.product_reference import get_product_reference_service
from src.services.accounts import AccountSession
from src.services.product_reference import ProductImageCandidate, ProductReference

ARTIFACT_SCRATCH_DIR = Path(
    "/Users/nav/.gemini/antigravity/brain/45550847-bc70-4498-b227-06554decc39e/scratch"
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
def first_ad_server(monkeypatch: pytest.MonkeyPatch):
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

    img_1 = _png_data_url(1200, 900, (35, 110, 75))

    class FakeProductReferenceService:
        async def read(self, raw_url: str) -> ProductReference:
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
                ],
                source_note="Photo imported from listing.",
            )

    def spy_meta(*args: Any, **kwargs: Any):
        muse_calls["count"] += 1
        raise AssertionError("Paid/provider Muse call unexpectedly triggered!")

    monkeypatch.setenv("DEMO_MODE", "true")
    monkeypatch.setenv("ACCOUNTS_REQUIRED", "true")
    monkeypatch.setenv("META_MODEL_API_KEY", "")
    monkeypatch.setenv("DEMO_KEY", "")
    monkeypatch.setattr("src.api.accounts.resolve_account", fake_resolve)
    monkeypatch.setattr("src.services.accounts.resolve_account", fake_resolve)
    monkeypatch.setattr("src.api.accounts.snapshot", fake_snapshot)
    monkeypatch.setattr("src.api.accounts.load_workspace", fake_load)
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
        yield f"http://127.0.0.1:{port}", muse_calls
    finally:
        app.dependency_overrides.clear()
        server.should_exit = True
        thread.join(timeout=2)


def test_first_ad_4_step_workflow_validation_persistence_and_exports_e2e(
    first_ad_server: tuple[str, dict[str, int]],
) -> None:
    """Verify /first-ad at 1440px and 375px with validation, reload, isolation, and exports."""
    pw_python = _find_playwright_python()
    if pw_python is None:
        pytest.skip("Playwright Python runtime unavailable")

    ARTIFACT_SCRATCH_DIR.mkdir(parents=True, exist_ok=True)
    base_url, muse_calls = first_ad_server

    script = textwrap.dedent(
        f"""
        import json
        from pathlib import Path
        from PIL import Image
        from playwright.sync_api import sync_playwright

        BASE = {base_url!r}
        OUT = Path({str(ARTIFACT_SCRATCH_DIR)!r})

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)

            # 1. Desktop (1440px) user-a 4-step workflow
            ctx_a = browser.new_context(
                viewport={{"width": 1440, "height": 900}}, accept_downloads=True
            )
            ctx_a.add_cookies([{{"name": "muse_e2e_user", "value": "user-a", "url": BASE}}])
            pa = ctx_a.new_page()
            pa.goto(f"{{BASE}}/first-ad", wait_until="domcontentloaded")
            pa.wait_for_selector("#faProvenanceBadge")
            pa.wait_for_function(
                "() => Boolean(window.localStorage) && "
                "document.querySelector('#faNotPublishedBadge') !== null"
            )
            pa.wait_for_timeout(300)
            pw_count = pa.locator('main input[type="password"]').count()
            assert pw_count == 0, f"password count={{pw_count}}"
            prov_txt = pa.locator("#faProvenanceBadge").text_content() or ""
            assert "Suggested starting approach" in prov_txt, f"prov_txt={{prov_txt!r}}"
            np_txt = pa.locator("#faNotPublishedBadge").text_content() or ""
            assert "Not published" in np_txt, f"np_txt={{np_txt!r}}"

            # Step 1: Choose visits + paid test
            pa.locator('[data-fa-outcome="visits"]').click()
            pa.locator('input[name="faPaidMode"][value="paid"]').check()
            pa.locator("#faNextBtn").click()

            # Step 2: Creative & destination
            pa.wait_for_selector("#faPanel2:not([hidden])")
            pa.fill("#faProductName", "Botanical Linocut")
            pa.fill("#faHeadline", "Hand-pulled Botanical Linocut")
            pa.fill("#faCaption", "Printed on cotton rag in small batches.")
            pa.fill("#faDestinationUrl", "https://wildmeadow.test/prints/botanical-linocut")
            pa.fill("#faShopUrl", "https://wildmeadow.test")
            pa.click("#faImportBtn")
            pa.wait_for_selector('[data-fa-cand-id="web-1"]')
            pa.click('[data-fa-cand-id="web-1"]')
            pa.locator("#faNextBtn").click()

            # Step 3: Audience, budget & date validation
            pa.wait_for_selector("#faPanel3:not([hidden])")
            pa.fill("#faAudience", "People buying botanical art gifts")
            # Invalid budget (0) must block advancing
            pa.fill("#faBudgetAmount", "0")
            pa.locator("#faNextBtn").click()
            assert pa.locator("#faBudgetError").is_visible()
            assert pa.locator("#faPanel3").is_visible()
            # Valid budget, invalid endDate < startDate must block advancing
            pa.fill("#faBudgetAmount", "12")
            pa.fill("#faStartDate", "2026-12-10")
            pa.fill("#faEndDate", "2026-12-05")
            pa.locator("#faNextBtn").click()
            assert pa.locator("#faDateError").is_visible()
            assert pa.locator("#faPanel3").is_visible()
            # Valid endDate advances to Step 4
            pa.fill("#faEndDate", "2026-12-15")
            pa.locator("#faNextBtn").click()

            # Step 4: Review & manual Ads Manager handoff
            pa.wait_for_selector("#faPanel4:not([hidden])")
            assert "Not published" in (pa.locator("#faPublishStatus").text_content() or "")
            prereq_txt = pa.locator("#faPrereqList").inner_text()
            assert "Manual Meta setup required" in prereq_txt
            pa.screenshot(path=str(OUT / "fa-review-1440.png"), full_page=False)

            pa.locator("#faReviewed").check()
            with pa.expect_download() as dl_png:
                pa.locator("#faFinalFeedBtn").click()
            png_path = OUT / "fa-exported-1440.png"
            dl_png.value.save_as(str(png_path))
            with Image.open(png_path) as im:
                assert im.size == (1080, 1350), im.size

            with pa.expect_download() as dl_txt:
                pa.locator("#faDownloadChecklistBtn").click()
            txt_path = OUT / "fa-checklist.txt"
            dl_txt.value.save_as(str(txt_path))
            txt_body = txt_path.read_text(encoding="utf-8")
            assert "STATUS: NOT PUBLISHED" in txt_body
            assert "Hand-pulled Botanical Linocut" in txt_body

            assert not pa.evaluate("document.documentElement.scrollWidth > window.innerWidth")

            # Reload persists user-a progress
            pa.reload(wait_until="domcontentloaded")
            pa.wait_for_selector("#faPanel4:not([hidden])")
            assert pa.locator("#faHeadline").input_value() == "Hand-pulled Botanical Linocut"
            assert pa.locator("#faBudgetAmount").input_value() == "12"

            # 2. Mobile (375px) user-b isolation & layout check
            ctx_b = browser.new_context(viewport={{"width": 375, "height": 844}})
            ctx_b.add_cookies([{{"name": "muse_e2e_user", "value": "user-b", "url": BASE}}])
            pb = ctx_b.new_page()
            pb.goto(f"{{BASE}}/first-ad", wait_until="domcontentloaded")
            pb.wait_for_selector("#faNextBtn")
            pb.wait_for_timeout(300)
            assert pb.locator("#faHeadline").input_value() != "Hand-pulled Botanical Linocut"
            assert not pb.evaluate("document.documentElement.scrollWidth > window.innerWidth")
            assert pb.locator("#faNextBtn").bounding_box()["height"] >= 44
            pb.screenshot(path=str(OUT / "fa-step1-375.png"), full_page=False)
            ctx_b.close()

            # 3. Sample mode isolation (?workspace=sample)
            ctx_s = browser.new_context(
                viewport={{"width": 1440, "height": 900}}, accept_downloads=True
            )
            ps = ctx_s.new_page()
            ps.goto(f"{{BASE}}/first-ad?workspace=sample", wait_until="domcontentloaded")
            ps.wait_for_function(
                "() => ((document.querySelector('#faProductName') || {{}}).value || '')"
                ".includes('Ek Onkar')"
            )
            assert "Artist example" in ps.locator("#faProvenanceBadge").inner_text()
            assert "Ek Onkar" in ps.locator("#faProductName").input_value()
            ps.click('[data-fa-step="4"]')
            ps.locator("#faReviewed").check()
            with ps.expect_download() as dl_s:
                ps.locator("#faFinalFeedBtn").click()
            s_png = OUT / "fa-sample-exported.png"
            dl_s.value.save_as(str(s_png))
            with Image.open(s_png) as im:
                assert im.size == (1080, 1350), im.size
            ctx_s.close()

            # user-a still has their own draft intact
            pa.reload(wait_until="domcontentloaded")
            pa.wait_for_selector("#faPanel4:not([hidden])")
            assert pa.locator("#faHeadline").input_value() == "Hand-pulled Botanical Linocut"
            ctx_a.close()
            browser.close()
            print(json.dumps({{"status": "ok"}}))
        """
    )

    proc = subprocess.run(
        [pw_python, "-c", script],
        capture_output=True,
        text=True,
        check=False,
        timeout=90,
    )
    assert proc.returncode == 0, f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
    assert muse_calls["count"] == 0
