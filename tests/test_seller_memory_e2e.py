"""Headless Chromium mobile (375px) E2E tests for Seller Memory (PRD Section 12, Batch 1)."""

from __future__ import annotations

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

from src.api.main import app
from src.models.intel import SitemapEntry
from src.services.accounts import AccountSession
from src.utils.sitemap import SitemapError


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


@pytest.fixture
def e2e_server(monkeypatch: pytest.MonkeyPatch):
    """Run real FastAPI app with stateful multi-account workspace & crawl fixture."""
    scan_round = {"count": 0}
    stores: dict[str, dict[str, Any]] = {
        "user-a": {"document": {}, "version": 1, "owner_id": "user-a"},
        "user-b": {
            "document": {
                "onboarding": {
                    "business_name": "Cedar Kiln Ceramics",
                    "website_url": "https://cedarkiln.test",
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
            raise HTTPException(409, "Workspace owner mismatch")
        slot = stores[account.user_id]
        if expected_version is not None and int(expected_version) != int(slot["version"]):
            raise HTTPException(409, "Workspace version conflict")
        slot["document"] = json.loads(json.dumps(doc))
        slot["version"] = int(slot["version"]) + 1
        return {
            "document": json.loads(json.dumps(slot["document"])),
            "version": int(slot["version"]),
            "owner_id": account.user_id,
        }

    async def fake_snapshot(account: AccountSession | None) -> dict[str, Any]:
        if account is None:
            return {
                "configured": True,
                "user": None,
                "usage": None,
                "live_available": False,
            }
        return {
            "configured": True,
            "user": {
                "id": account.user_id,
                "email": account.email,
                "email_verified": True,
            },
            "usage": {
                "plan": "starter",
                "used": 0,
                "limit": 3,
                "remaining": 3,
                "resets_at": None,
            },
            "live_available": True,
        }

    async def fake_collect(url: str, **_kwargs: Any) -> tuple[list[SitemapEntry], list[str]]:
        if "blocked" in url:
            raise SitemapError("Blocked by robots policy")
        scan_round["count"] += 1
        # Initial crawl finds $35; subsequent rescan call finds $48 so rescan diff is clear.
        price = "$35" if scan_round["count"] == 1 else "$48"
        return (
            [
                SitemapEntry(
                    loc="https://wildmeadow.test/prints/autumn-meadow",
                    bucket="products",
                    title="Autumn Meadow Watercolor Gift Print",
                    price_hint=price,
                )
            ],
            ["https://wildmeadow.test/sitemap.xml"],
        )

    for mod in (
        "src.api.accounts",
        "src.api.onboarding",
        "src.api.preferences",
        "src.api.seller_memory",
    ):
        monkeypatch.setattr(f"{mod}.resolve_account", fake_resolve)
        monkeypatch.setattr(f"{mod}.load_workspace", fake_load)
        monkeypatch.setattr(f"{mod}.save_workspace", fake_save)
    for mod in ("src.api.accounts", "src.api.onboarding"):
        monkeypatch.setattr(f"{mod}.snapshot", fake_snapshot)
    monkeypatch.setattr("src.api.intel.collect_entries", fake_collect)
    monkeypatch.setattr("src.api.seller_memory.collect_entries", fake_collect)

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()

    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    base_url = f"http://127.0.0.1:{port}"
    for _ in range(60):
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.1):
                break
        except OSError:
            time.sleep(0.05)

    yield base_url, stores
    server.should_exit = True


def test_seller_memory_full_mobile_multi_browser_workflow(
    e2e_server: tuple[str, dict[str, Any]],
) -> None:
    """Exercise Batch 1 end-to-end in headless Chromium at 375px across two contexts."""
    pw_python = _find_playwright_python()
    if pw_python is None:
        pytest.skip("Playwright Python runtime unavailable")

    base_url, _stores = e2e_server

    script = textwrap.dedent(
        f"""
        import json
        from playwright.sync_api import sync_playwright

        base_url = {base_url!r}

        def assert_no_overflow(page, label):
            offenders = page.evaluate('''() => {{
                const cw = document.documentElement.clientWidth;
                if (document.documentElement.scrollWidth <= cw) return [];
                const bad = [];
                document.querySelectorAll('*').forEach((el) => {{
                    const r = el.getBoundingClientRect();
                    if (r.right > cw + 1 || r.left < -1) {{
                        bad.push(el.tagName + '#' + el.id + ':' + Math.round(r.right));
                    }}
                }});
                return bad.slice(0, 8);
            }}''')
            assert not offenders, f"Horizontal overflow on {{label}}: {{offenders}}"

        def set_user_cookie(ctx, uid):
            ctx.clear_cookies()
            if uid:
                ctx.add_cookies([{{
                    "name": "muse_e2e_user",
                    "value": uid,
                    "url": base_url,
                }}])

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            ctx1 = browser.new_context(viewport={{"width": 375, "height": 844}})
            ctx2 = browser.new_context(viewport={{"width": 375, "height": 844}})

            # Block outbound model hosts as an extra zero-debit safety belt
            for c in (ctx1, ctx2):
                c.route("*api.meta.ai*", lambda r: r.abort())
                c.route("*llama.com*", lambda r: r.abort())

            set_user_cookie(ctx1, "user-a")
            set_user_cookie(ctx2, "user-a")

            page = ctx1.new_page()
            errors = []
            page.on("pageerror", lambda err: errors.append(str(err)))

            # --- 1. Onboarding scan -> edit -> rescan diff -> skip Step 4 ---
            page.goto(f"{{base_url}}/welcome", wait_until="domcontentloaded")
            page.wait_for_selector("#wkStep1:not([hidden])")
            assert_no_overflow(page, "/welcome")

            page.fill("#wkShopUrl", "https://wildmeadow.test")
            page.fill("#wkBusinessName", "Wild Meadow Watercolor Studio")
            page.click("#wkScanShopBtn")
            page.wait_for_selector("#smOnboardingScanReview:not([hidden])")

            scan_text = page.text_content("#smOnboardingScanReview") or ""
            assert "Observed fact" in scan_text, scan_text
            assert "Interpretation" in scan_text, scan_text
            assert "https://wildmeadow.test" in scan_text, scan_text
            price_sel = '#smOnboardingScanReview [data-sm-entry-id="obs-price-range"] input'
            init_price_val = page.input_value(price_sel)
            assert "$35" in init_price_val, init_price_val

            # Seller corrects the observed price entry
            price_inp = page.locator(price_sel)
            price_inp.fill("Archival watercolor prints start at $40")
            price_inp.dispatch_event("change")
            page.wait_for_selector('#smOnboardingScanReview:has-text("Edited by you")')

            # Rescan: crawler returns $48, diff preserves seller's $40 edit
            page.click("#wkScanShopBtn")
            page.wait_for_selector("#smRescanDiffBox")
            diff_text = page.text_content("#smRescanDiffBox") or ""
            assert "Preserved your edit" in diff_text
            assert "$40" in diff_text and "$48" in diff_text
            assert page.input_value(price_sel) == "Archival watercolor prints start at $40"

            page.click("#wkStep1NextBtn")
            page.wait_for_selector("#wkStep2:not([hidden])")
            page.click("#wkStep2NextBtn")
            page.wait_for_selector("#wkStep3:not([hidden])")

            # Add watched competitor with explicit role = similar_audience
            page.fill("#wkManualCompUrl", "https://riverbend.test")
            page.fill("#wkManualCompReason", "Great tabletop gift bundles")
            page.click("#wkAddCompBtn")
            page.wait_for_selector("#wkCompList li .sm-comp-role")
            page.click("#wkStep3NextBtn")
            page.wait_for_selector("#wkStep4:not([hidden])")

            # Skip optional questions in Step 4; scanned + edited entries must persist
            page.click("#wkStep4SkipBtn")
            page.wait_for_selector("#wkStepDone:not([hidden])")
            page.wait_for_selector('#wkStepDone[data-sm-synced="true"]')

            # --- 2. Home (/): competitor role change shifts top recommendation ---
            page.click("#wkOpenWorkspaceBtn")
            page.wait_for_url(f"{{base_url}}/")
            page.wait_for_selector("#smContextPanel")
            page.wait_for_selector("#smTopMovePreview")
            page.wait_for_selector("#sellerList .sm-home-comp-role")
            assert_no_overflow(page, "/ home")

            journey_text = page.inner_text("#journey") or ""
            assert "sarabjit" not in journey_text.lower(), journey_text
            assert "sikhiart" not in journey_text.lower(), journey_text
            assert "Wild Meadow Watercolor Studio" in journey_text, journey_text

            first_top_id = page.get_attribute("#smTopMovePreview", "data-sm-top-id")
            assert first_top_id == "move-similar-audience", first_top_id
            first_why = page.text_content("#smTopMovePreview .sm-why-line") or ""
            assert "Similar audience" in first_why, first_why

            # Change competitor role -> price_reference & update rationale
            comp_rationale = page.locator("#sellerList .sm-home-comp-rationale").first
            comp_rationale.fill("Benchmark $40 entry prints")
            comp_rationale.dispatch_event("change")
            page.wait_for_timeout(150)
            comp_role = page.locator("#sellerList .sm-home-comp-role").first
            comp_role.select_option("price_reference")

            page.wait_for_selector('#smWhatChangedBanner:not([hidden])')
            page.wait_for_selector('#smTopMovePreview[data-sm-top-id="move-price-positioning"]')
            new_why = page.text_content("#smTopMovePreview .sm-why-line") or ""
            assert "Price reference" in new_why, new_why
            assert "Benchmark $40 entry prints" in new_why, new_why

            # --- 3. Temporary draft override leaves saved shop default untouched ---
            page.fill("#smCtxGoal", "Share watercolor studio process story")
            page.fill("#smCtxMinutes", "15")
            page.click("#smApplyDraftBtn")
            page.wait_for_selector('#smContextPanel:has-text("Draft override active")')
            page.wait_for_selector('#smTopMovePreview[data-sm-top-id="move-inspiration-story"]')
            page.click("#smClearDraftBtn")
            page.wait_for_timeout(200)

            # --- 4. Second Browser Context restores profile + tests 409 Conflict ---
            page2 = ctx2.new_page()
            page2.goto(f"{{base_url}}/", wait_until="domcontentloaded")
            page2.wait_for_selector("#sellerList .sm-home-comp-role")
            ctx2_role = page2.locator("#sellerList .sm-home-comp-role").first.input_value()
            assert ctx2_role == "price_reference", ctx2_role
            page2.click("#smOpenMemoryBtn")
            page2.wait_for_selector("#smMemoryModalBackdrop:not([hidden])")
            modal2_text = page2.text_content("#smMemoryModalBody") or ""
            assert "Archival watercolor prints start at $40" in modal2_text
            page2.click("#smCloseMemoryModalBtn")

            # Context 2 saves a new shop default -> increments server version
            page2.fill("#smCtxGoal", "Promote holiday framed originals")
            page2.click("#smSaveDefaultBtn")
            page2.wait_for_timeout(300)

            # Context 1 (older version) saves conflicting goal -> 409 conflict preserves both
            page.fill("#smCtxGoal", "Launch coastal mini studies")
            page.click("#smSaveDefaultBtn")
            page.wait_for_selector("#smConflictModalBackdrop:not([hidden])")
            conflict_text = page.text_content("#smConflictModalBackdrop") or ""
            assert "Launch coastal mini studies" in conflict_text
            assert "Promote holiday framed originals" in conflict_text
            page.click("#smConflictKeepMineBtn")
            page.wait_for_selector("#smConflictModalBackdrop[hidden]", state="attached")

            # --- 5. Sign-out & A-to-B Account Isolation ---
            set_user_cookie(ctx1, None)
            page.goto(f"{{base_url}}/", wait_until="domcontentloaded")
            page.wait_for_timeout(400)
            signed_out_mem = page.evaluate("window.museSellerMemory.getState().memoryEntries")
            assert all(
                "coastal mini studies" not in (e.get("value") or "").lower()
                for e in signed_out_mem
            )

            set_user_cookie(ctx1, "user-b")
            page.goto(f"{{base_url}}/", wait_until="domcontentloaded")
            page.wait_for_selector("#smContextPanel")
            page.click("#smOpenMemoryBtn")
            page.wait_for_selector("#smMemoryModalBackdrop:not([hidden])")
            b_modal = page.text_content("#smMemoryModalBody") or ""
            assert "wild meadow" not in b_modal.lower()
            assert "coastal mini studies" not in b_modal.lower()
            assert "sarabjit" not in b_modal.lower()
            page.click("#smCloseMemoryModalBtn")

            # --- 6. Switch back to Account A: Voice Fixture + Suggestion + Forget ---
            set_user_cookie(ctx1, "user-a")
            page.goto(f"{{base_url}}/", wait_until="domcontentloaded")
            page.wait_for_selector("#smContextPanel")
            page.click("#smOpenMemoryBtn")
            page.wait_for_selector("#smMemoryModalBackdrop:not([hidden])")

            # Sample watercolor voice note fixture (0 runs, editable before approve)
            page.click("#smUseVoiceFixtureBtn")
            page.wait_for_selector('#smVoiceTranscriptBox:not([hidden])')
            assert "Archival" in (page.input_value("#smVoiceTranscriptEdit") or "")
            page.click("#smReviewTranscriptBtn")
            page.wait_for_selector("#smApproveProposalsBtn")
            # Dismiss the 15-min proposal during review so too_much_time suggestion tests below
            page.click(
                '#smProposalReviewArea [data-sm-entry-id="pref-minutes-per-week"] .sm-btn-danger'
            )
            page.click("#smApproveProposalsBtn")
            page.wait_for_selector('#smMemoryModalBody [data-modal-entry-id="pref-avoid-phrases"]')
            updated_modal = page.text_content("#smMemoryModalBody") or ""
            assert "discount" in updated_modal.lower() or "cheap" in updated_modal.lower()
            page.click("#smCloseMemoryModalBtn")

            # Open Improve stage -> dismiss two recommendations with 'too_much_time'
            page.click("#smShowImproveTabBtn")
            page.wait_for_selector("#loop-improve:not([hidden]) ol.jr-recos li:not([hidden])")
            recos_dismiss = "#loop-improve ol.jr-recos li:not([hidden]) .ms-triage-dismiss"
            for _ in range(2):
                page.locator(recos_dismiss).first.click()
                page.locator('.ms-dismiss-chip[data-reason="too_much_time"]').first.click()
                page.wait_for_timeout(150)

            sug_sel = '#smSuggestionContainer [data-suggestion-id="suggest-prefer-15min"]'
            page.wait_for_selector(sug_sel)
            cur_mins_before = page.evaluate(
                "window.museSellerMemory.getState().preferences?.access?.minutes_per_week"
            )
            assert cur_mins_before != 15

            page.click('[data-approve-suggestion="suggest-prefer-15min"]')
            page.wait_for_timeout(300)
            cur_mins_after = page.evaluate(
                "window.museSellerMemory.getState().preferences?.access?.minutes_per_week"
            )
            assert cur_mins_after == 15

            # Open Memory modal -> Forget price_range entry -> stops appearing
            page.click("#smOpenMemoryBtn")
            forget_sel = '#smMemoryModalBody [data-forget-entry="obs-price-range"]'
            page.wait_for_selector(forget_sel)
            page.click(forget_sel)
            page.wait_for_timeout(300)
            assert page.locator(forget_sel).count() == 0

            # Also verify /today renders context bar with zero overflow & zero Sarabjit leak
            page.goto(f"{{base_url}}/today", wait_until="domcontentloaded")
            page.wait_for_selector("#smStudioContextBar")
            assert_no_overflow(page, "/today")
            today_bar = page.text_content("#smStudioContextBar") or ""
            assert "Wild Meadow" in today_bar or "15 min/wk" in today_bar
            assert "sarabjit" not in today_bar.lower()

            # Also verify /create renders context bar with zero overflow & zero Sarabjit leak
            page.goto(f"{{base_url}}/create", wait_until="domcontentloaded")
            page.wait_for_selector("#smStudioContextBar")
            assert_no_overflow(page, "/create")
            create_bar = page.text_content("#smStudioContextBar") or ""
            assert "Wild Meadow" in create_bar or "15 min/wk" in create_bar
            assert "sarabjit" not in create_bar.lower()

            assert not errors, f"Uncaught page errors: {{errors}}"
            browser.close()
        """
    )

    res = subprocess.run(
        [pw_python, "-c", script],
        capture_output=True,
        text=True,
        check=False,
        timeout=90,
    )
    assert res.returncode == 0, f"STDOUT:\n{res.stdout}\nSTDERR:\n{res.stderr}"


def test_batch1_corrections_security_merge_drafts_and_handoff_e2e(
    e2e_server: tuple[str, dict[str, Any]],
) -> None:
    """Verify Slices 1-5 in headless Chromium across desktop (1440px) and mobile (375px)."""
    pw_python = _find_playwright_python()
    if pw_python is None:
        pytest.skip("Playwright Python runtime unavailable")

    base_url, stores = e2e_server

    # Seed user-a with multi-product/currency memory, extras, and hostile source_url cases
    stores["user-a"]["version"] = 2
    stores["user-a"]["document"] = {
        "onboarding": {
            "business_name": "Wild Meadow Press",
            "website_url": "https://wildmeadow.test",
            "completed_at": "2026-11-10T10:00:00Z",
            "competitors": [
                {
                    "name": "Story Peer",
                    "url": "https://storypeer.test",
                    "role": "inspiration",
                    "rationale": "Strong process storytelling",
                    "selected": True,
                },
                {
                    "name": "Gift Peer",
                    "url": "https://giftpeer.test",
                    "role": "similar_audience",
                    "rationale": "Seasonal gift buyers",
                    "selected": True,
                },
            ],
        },
        "voice_profile": {"formality": "casual", "future_voice": "earthy-note"},
        "preferences": {
            "goal": "Sell botanical gifts",
            "audience": "Gift buyers",
            "future_root_flag": "keep-root",
            "access": {
                "minutes_per_week": 60,
                "channels": ["instagram", "facebook"],
                "future_access": "weekend-keep",
            },
            "taste": {"tone": "casual", "future_taste": "botanical-keep"},
            "memory_entries": [
                {
                    "id": "obs-eur-print",
                    "key": "price_range",
                    "label": "Website price",
                    "value": "Prints start at EUR 45",
                    "kind": "observation",
                    "scope": "product",
                    "product_key": "Botanical Linocut",
                    "destination": "website",
                    "source": "shop_scan",
                    "source_url": "https://wildmeadow.test/prints/botanical",
                    "confidence": "observed",
                    "status": "accepted",
                },
                {
                    "id": "obs-usd-card",
                    "key": "price_range",
                    "label": "Etsy price",
                    "value": "Cards start at $18",
                    "kind": "observation",
                    "scope": "product",
                    "product_key": "Meadow Cards",
                    "destination": "etsy",
                    "source": "shop_scan",
                    "source_url": "https://wildmeadow.test/cards/meadow",
                    "confidence": "observed",
                    "status": "accepted",
                },
                {
                    "id": "obs-xss-js",
                    "key": "catalog_note",
                    "label": "Hostile JS URL test",
                    "value": "Check link sanitization",
                    "kind": "observation",
                    "scope": "shop_default",
                    "source": "shop_scan",
                    "source_url": "javascript:alert(1)",
                    "confidence": "observed",
                    "status": "accepted",
                },
                {
                    "id": "obs-xss-data",
                    "key": "catalog_note",
                    "label": "Hostile data URL test",
                    "value": "Check data URI sanitization",
                    "kind": "observation",
                    "scope": "shop_default",
                    "source": "shop_scan",
                    "source_url": "data:text/html,<script>alert(1)</script>",
                    "confidence": "observed",
                    "status": "accepted",
                },
                {
                    "id": "pref-min",
                    "key": "minutes_per_week",
                    "label": "Weekly time budget",
                    "value": "60 minutes / week",
                    "kind": "preference",
                    "scope": "shop_default",
                    "source": "user_input",
                    "confidence": "confirmed",
                    "status": "accepted",
                },
            ],
            "competitor_entries": [
                {
                    "name": "Story Peer",
                    "url": "https://storypeer.test",
                    "role": "inspiration",
                    "rationale": "Strong process storytelling",
                    "selected": True,
                },
                {
                    "name": "Gift Peer",
                    "url": "https://giftpeer.test",
                    "role": "similar_audience",
                    "rationale": "Seasonal gift buyers",
                    "selected": True,
                },
            ],
        },
    }

    script = textwrap.dedent(
        f"""
        import base64
        import json
        import os
        import tempfile
        import urllib.request
        from playwright.sync_api import sync_playwright

        base_url = {base_url!r}

        # Valid 2x2 PNG bytes (no external binary files needed)
        TINY_PNG = base64.b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAAAIAAAACCAIAAAD91JpzAAAADklEQVR4nGP4z8DwHwAFAAH/iZk9HQAAAABJRU5ErkJggg=="
        )

        def assert_no_overflow(page, label):
            offenders = page.evaluate('''() => {{
                const cw = document.documentElement.clientWidth;
                if (document.documentElement.scrollWidth <= cw) return [];
                const bad = [];
                document.querySelectorAll('*').forEach((el) => {{
                    const r = el.getBoundingClientRect();
                    if (r.right > cw + 1 || r.left < -1) {{
                        bad.push(el.tagName + '#' + el.id + ':' + Math.round(r.right));
                    }}
                }});
                return bad.slice(0, 8);
            }}''')
            assert not offenders, f"Horizontal overflow on {{label}}: {{offenders}}"

        def set_user_cookie(ctx, uid):
            ctx.clear_cookies()
            if uid:
                ctx.add_cookies([{{
                    "name": "muse_e2e_user",
                    "value": uid,
                    "url": base_url,
                }}])

        with tempfile.TemporaryDirectory() as tmpdir, sync_playwright() as p:
            png_path = os.path.join(tmpdir, "custom-art.png")
            with open(png_path, "wb") as f:
                f.write(TINY_PNG)

            browser = p.chromium.launch(headless=True)
            ctx_desk = browser.new_context(
                viewport={{"width": 1440, "height": 900}},
                accept_downloads=True,
            )
            ctx_mob = browser.new_context(
                viewport={{"width": 375, "height": 844}},
                accept_downloads=True,
            )
            for c in (ctx_desk, ctx_mob):
                c.route("*api.meta.ai*", lambda r: r.abort())
                c.route("*llama.com*", lambda r: r.abort())

            set_user_cookie(ctx_desk, "user-a")
            page = ctx_desk.new_page()
            page.set_default_timeout(10000)
            errors = []
            page.on("pageerror", lambda err: errors.append(str(err)))

            # --- 1. Hostile source_url check in modal DOM (Desktop 1440px) ---
            page.goto(f"{{base_url}}/", wait_until="domcontentloaded")
            page.wait_for_selector("#smOpenMemoryBtn")
            assert_no_overflow(page, "/ desktop 1440")
            page.click("#smOpenMemoryBtn")
            page.wait_for_selector("#smMemoryModalBackdrop:not([hidden])")
            hrefs = page.evaluate(
                "() => Array.from(document.querySelectorAll('#smMemoryModalBody a'))"
                ".map((a) => a.getAttribute('href'))"
            )
            assert "https://wildmeadow.test/prints/botanical" in hrefs
            assert not any(
                (h or "").lower().startswith(("javascript:", "data:", "vbscript:"))
                for h in hrefs
            ), hrefs
            modal_txt = page.text_content("#smMemoryModalBody") or ""
            assert "javascript:alert(1)" in modal_txt  # rendered as safe inert text
            page.click("#smCloseMemoryModalBtn")

            # --- 2. Two-draft isolation, EUR/USD scoping, and real Ignore button ---
            page.fill("#smCtxProduct", "Botanical Linocut")
            page.fill("#smCtxDestination", "website")
            page.click("#smApplyDraftBtn")
            page.wait_for_function(
                "() => window.museSellerMemory.getState()"
                ".recommendResult?.editor_defaults?.price_claim === 'EUR 45'"
            )
            def_d1 = page.evaluate(
                "window.museSellerMemory.getState().recommendResult?.editor_defaults"
            )
            assert def_d1["price_claim"] == "EUR 45", def_d1

            # Click real 'Ignore for draft' button for 'Weekly time budget'
            page.click("#smShowImproveTabBtn")
            ign_sel = (
                '#loop-improve ol.jr-recos .sm-used-chip '
                'button[aria-label*="Weekly time budget"]'
            )
            page.wait_for_selector(ign_sel)
            page.locator(ign_sel).first.click()
            page.wait_for_function(
                "() => {{ const d = window.museSellerMemory.getState().draftOverride || {{}}; "
                "return (d.ignore_entry_ids || d.ignored_entry_ids || [])"
                ".includes('pref-min'); }}"
            )
            page.wait_for_function('''() => {{
                const recs = (
                    window.museSellerMemory.getState().recommendResult?.recommendations || []
                );
                return !recs.flatMap((r) => (r.used_entries || []).map((u) => u.id))
                    .includes('pref-min');
            }}''')
            used_after_ignore = page.evaluate('''() => {{
                const recs = (
                    window.museSellerMemory.getState().recommendResult?.recommendations || []
                );
                return recs.flatMap((r) => (r.used_entries || []).map((u) => u.id));
            }}''')
            assert "pref-min" not in used_after_ignore, used_after_ignore

            # Switch to Draft 2 -> apply Meadow Cards / etsy -> $18 isolated from Draft 1
            page.select_option("#smDraftSlotSelect", "draft-2")
            page.wait_for_function(
                "() => window.museSellerMemory.getState().draftId === 'draft-2'"
            )
            page.fill("#smCtxProduct", "Meadow Cards")
            page.fill("#smCtxDestination", "etsy")
            page.click("#smApplyDraftBtn")
            page.wait_for_function(
                "() => window.museSellerMemory.getState()"
                ".recommendResult?.editor_defaults?.price_claim === '$18'"
            )
            def_d2 = page.evaluate(
                "window.museSellerMemory.getState().recommendResult?.editor_defaults"
            )
            assert def_d2["price_claim"] == "$18", def_d2

            # Switch back to Draft 1 -> EUR 45 + ignore list preserved!
            page.select_option("#smDraftSlotSelect", "default")
            page.wait_for_function(
                "() => window.museSellerMemory.getState().draftId === 'default' && "
                "window.museSellerMemory.getState()"
                ".recommendResult?.editor_defaults?.price_claim === 'EUR 45'"
            )
            def_d1_back = page.evaluate(
                "window.museSellerMemory.getState().recommendResult?.editor_defaults"
            )
            assert def_d1_back["price_claim"] == "EUR 45", def_d1_back

            # Clear draft override before merge test
            page.click("#smClearDraftBtn")
            page.wait_for_function(
                "() => !window.museSellerMemory.getState().draftOverride?.active"
            )

            # --- 3. Three-way Conflict Merge preserves server fields & extras ---
            cur_state = page.evaluate("window.museSellerMemory.getState()")
            put_req = urllib.request.Request(
                f"{{base_url}}/api/v1/seller-memory",
                method="PUT",
                headers={{
                    "Content-Type": "application/json",
                    "Cookie": "muse_e2e_user=user-a",
                    "X-Muse-Owner": "user-a",
                }},
                data=json.dumps({{
                    "expected_version": cur_state["version"],
                    "expected_owner": "user-a",
                    "preferences": {{
                        "goal": "Server concurrent holiday focus",
                        "audience": cur_state["preferences"]["audience"],
                        "access": cur_state["preferences"]["access"],
                        "taste": cur_state["preferences"]["taste"],
                    }},
                    "voice_profile": cur_state["voiceProfile"],
                    "memory_entries": cur_state["memoryEntries"],
                    "competitor_entries": cur_state["competitorEntries"],
                }}).encode("utf-8"),
            )
            with urllib.request.urlopen(put_req) as resp:
                assert resp.status == 200

            # Local edit only changes minutes to 25 (leaves goal untouched) -> 409 conflict
            page.fill("#smCtxMinutes", "25")
            page.click("#smSaveDefaultBtn")
            page.wait_for_selector("#smConflictModalBackdrop:not([hidden])")
            page.click("#smConflictMergeBtn")
            page.wait_for_selector("#smConflictModalBackdrop[hidden]", state="attached")
            page.wait_for_timeout(300)

            merged = page.evaluate("window.museSellerMemory.getState()")
            assert (
                merged["preferences"]["goal"] == "Server concurrent holiday focus"
            ), merged["preferences"]
            assert (
                merged["preferences"]["access"]["minutes_per_week"] == 25
            ), merged["preferences"]["access"]
            assert merged["preferences"]["future_root_flag"] == "keep-root"
            assert merged["preferences"]["access"]["future_access"] == "weekend-keep"
            assert merged["preferences"]["taste"]["future_taste"] == "botanical-keep"
            assert merged["voiceProfile"]["future_voice"] == "earthy-note"

            # --- 4. Non-top rec handoff to /create (uploaded photo + export PNG) ---
            page.fill("#smCtxProduct", "Botanical Linocut")
            page.fill("#smCtxDestination", "website")
            page.click("#smApplyDraftBtn")
            page.wait_for_function(
                "() => window.museSellerMemory.getState()"
                ".recommendResult?.editor_defaults?.price_claim === 'EUR 45'"
            )

            # Upload custom photo on /create as user-a so device draft holds it
            page_create = ctx_desk.new_page()
            page_create.on("pageerror", lambda err: errors.append(str(err)))
            page_create.goto(f"{{base_url}}/create", wait_until="domcontentloaded")
            page_create.wait_for_selector("#productPhoto", state="attached")
            page_create.set_input_files("#productPhoto", png_path)
            page_create.wait_for_function(
                "() => (document.getElementById('productImage')?.getAttribute('src') || '')"
                ".startsWith('data:image/')"
            )
            page_create.close()

            # Pick NON-TOP recommendation (index 1, NOT rec[0]) from /
            page.click("#smShowImproveTabBtn")
            page.wait_for_selector("#loop-improve ol.jr-recos li[data-sm-reco-id]")
            recos = page.evaluate(
                "window.museSellerMemory.getState().recommendResult.recommendations"
            )
            assert len(recos) >= 2, recos
            top_rec = recos[0]
            non_top_rec = recos[1]
            assert top_rec["id"] != non_top_rec["id"]
            assert top_rec["title"] != non_top_rec["title"]

            second_li = page.locator(
                f'#loop-improve ol.jr-recos li[data-sm-reco-id="{{non_top_rec["id"]}}"]'
            )
            make_ad_href = second_li.locator("a", has_text="Make ad").get_attribute("href")
            assert make_ad_href and "sm_handoff=" in make_ad_href
            assert "idea=" not in make_ad_href
            assert "Wild Meadow Press" not in make_ad_href

            # Click non-top Make ad link
            second_li.locator("a", has_text="Make ad").click()
            page.wait_for_url("**/create?sm_handoff=*")
            page.wait_for_selector("#smStudioContextBar")
            page.wait_for_timeout(300)
            assert_no_overflow(page, "/create desktop 1440")

            # Must carry non-top recommendation & uploaded photo, ZERO Sarabjit leak
            assert not page.locator("#artistExample").is_visible()
            snap_create = page.evaluate("window.museCreatorSnapshot()")
            assert snap_create["idea_id"] == non_top_rec["id"], snap_create
            assert snap_create["headline"] == non_top_rec["title"], snap_create
            assert snap_create["caption"] == non_top_rec["action"], snap_create
            assert snap_create["cta"] == non_top_rec["cta"], snap_create
            assert snap_create["product"]["name"] == "Botanical Linocut", snap_create
            expected_create_price = (
                (non_top_rec.get("editor_defaults") or {{}}).get("price_claim") or ""
            )
            assert snap_create["product"]["price"] == expected_create_price, snap_create
            assert snap_create["product"]["link"] == "", snap_create
            assert "sarabjit" not in json.dumps(snap_create).lower()
            assert "ek onkar" not in json.dumps(snap_create).lower()
            src_img = page.locator("#productImage").get_attribute("src") or ""
            assert src_img.startswith("data:image/"), src_img

            # Canvas preview renders & PNG export produces real PNG bytes
            dims = page.evaluate(
                "async () => {{ const c = await window.museDrawLayout(1350); "
                "return {{ w: c.width, h: c.height }}; }}"
            )
            assert dims == {{"w": 1080, "h": 1350}}
            page.click('[data-step="2"]')
            page.wait_for_selector("#reviewed")
            page.check("#reviewed")
            page.click('[data-step="3"]')
            page.wait_for_selector("#downloadFeed")
            with page.expect_download() as dl_info:
                page.click("#downloadFeed")
            dl_path = dl_info.value.path()
            with open(dl_path, "rb") as f:
                assert f.read(4) == b"\\x89PNG"

            # --- 5. Unrecognized ?idea=bogus while signed in keeps own workspace ---
            page.goto(
                f"{{base_url}}/create?idea=bogus-unrecognized-id",
                wait_until="domcontentloaded",
            )
            page.wait_for_timeout(300)
            assert not page.locator("#artistExample").is_visible()
            bogus_hl = page.locator("#headline").input_value()
            assert "ek onkar" not in bogus_hl.lower(), bogus_hl

            # --- 6. Non-top rec handoff to /today on mobile 375px + export ---
            page_m = ctx_mob.new_page()
            page_m.on("pageerror", lambda err: errors.append(str(err)))
            set_user_cookie(ctx_mob, "user-a")
            page_m.goto(f"{{base_url}}/today", wait_until="domcontentloaded")
            page_m.wait_for_selector("#photo", state="attached")
            page_m.set_input_files("#photo", png_path)
            page_m.wait_for_function("() => Boolean(document.getElementById('postCanvas')?.width)")

            page_m.goto(f"{{base_url}}/", wait_until="domcontentloaded")
            page_m.wait_for_selector("#smShowImproveTabBtn")
            page_m.click("#smShowImproveTabBtn")
            page_m.wait_for_selector("#loop-improve ol.jr-recos li[data-sm-reco-id]")
            m_recos = page_m.evaluate(
                "window.museSellerMemory.getState().recommendResult.recommendations"
            )
            assert len(m_recos) >= 2
            m_non_top = m_recos[1]
            m_li = page_m.locator(
                f'#loop-improve ol.jr-recos li[data-sm-reco-id="{{m_non_top["id"]}}"]'
            )
            draft_href = m_li.locator("a", has_text="Draft daily post").get_attribute("href")
            assert draft_href and "sm_handoff=" in draft_href and "idea=" not in draft_href
            m_li.locator("a", has_text="Draft daily post").click()
            page_m.wait_for_url("**/today?sm_handoff=*")
            page_m.wait_for_selector("#smStudioContextBar")
            page_m.wait_for_timeout(350)
            assert_no_overflow(page_m, "/today mobile 375")

            snap_today = page_m.evaluate("window.museDailySnapshot()")
            assert snap_today["idea_id"] == m_non_top["id"], snap_today
            assert snap_today["copy"]["hook"] == m_non_top["title"], snap_today
            assert snap_today["copy"]["caption"] == m_non_top["action"], snap_today
            assert snap_today["cta"] == m_non_top["cta"], snap_today
            assert snap_today["product"]["destination_url"] == "", snap_today
            assert "sarabjit" not in json.dumps(snap_today).lower()
            assert "ek onkar" not in json.dumps(snap_today).lower()
            has_uploaded = page_m.evaluate("Boolean(document.getElementById('postCanvas')?.width)")
            assert has_uploaded

            page_m.check("#reviewed")
            with page_m.expect_download() as m_dl_info:
                page_m.click("#getPost")
            m_dl_path = m_dl_info.value.path()
            with open(m_dl_path, "rb") as f:
                assert f.read(4) == b"\\x89PNG"

            # --- 7. All-channels-excluded banner + no-reload A -> signout -> B guard ---
            page.goto(f"{{base_url}}/", wait_until="domcontentloaded")
            page.wait_for_selector("#smOpenMemoryBtn")
            page.click("#smOpenMemoryBtn")
            page.wait_for_selector("#smFreeContextInput")
            page.fill(
                "#smFreeContextInput",
                "No website, no instagram, no facebook, no etsy, "
                "no tiktok, no pinterest, no youtube.",
            )
            page.click("#smInterpretTextBtn")
            page.wait_for_selector("#smApproveProposalsBtn")
            page.click("#smApproveProposalsBtn")
            excl_modal_sel = (
                '#smMemoryModalBody [data-modal-entry-id="pref-excluded-channels"]'
            )
            page.wait_for_selector(excl_modal_sel)
            page.click("#smCloseMemoryModalBtn")

            page.wait_for_selector("#smMissingInfoBanner:not([hidden])")
            banner_txt = page.text_content("#smMissingInfoBanner") or ""
            assert "excluded" in banner_txt.lower() or "channel" in banner_txt.lower(), banner_txt
            assert page.locator("#loop-improve ol.jr-recos li[data-sm-reco-id]").count() == 0

            # Reset excluded channels entry so user-a has normal state
            page.click("#smOpenMemoryBtn")
            forget_excl_sel = (
                '#smMemoryModalBody [data-forget-entry="pref-excluded-channels"]'
            )
            page.wait_for_selector(forget_excl_sel)
            page.click(forget_excl_sel)
            page.wait_for_selector(forget_excl_sel, state="detached")
            page.click("#smCloseMemoryModalBtn")

            # Hold next /recommend AND next PUT for A across signout + switch to B
            held_routes = []
            def hold_rec(route):
                if len(held_routes) == 0:
                    held_routes.append(route)
                else:
                    route.continue_()
            page.route("**/api/v1/seller-memory/recommend", hold_rec)

            held_puts = []
            put_attempts = []
            def track_and_hold_put(route):
                if route.request.method == "PUT":
                    put_attempts.append(route.request.headers.get("x-muse-owner"))
                    if len(held_puts) == 0:
                        held_puts.append(route)
                        return
                route.continue_()
            page.route("**/api/v1/seller-memory", track_and_hold_put)

            # Trigger async /recommend (fire-and-forget; do not return Promise to page.evaluate)
            # + first held PUT + second queued PUT for A
            page.evaluate("() => {{ window.museSellerMemory.reload(); }}")
            page.fill("#smCtxGoal", "In-flight save 1 from Account A")
            page.click("#smSaveDefaultBtn")
            page.fill("#smCtxGoal", "Queued save 2 from Account A")
            page.click("#smSaveDefaultBtn")
            page.wait_for_timeout(200)
            assert len(held_routes) == 1
            assert len(held_puts) == 1
            assert len(put_attempts) == 1

            # Open modal so private DOM exists, then sign out WITHOUT reload
            page.click("#smOpenMemoryBtn")
            page.wait_for_selector("#smMemoryModalBackdrop:not([hidden])")
            set_user_cookie(ctx_desk, None)
            page.evaluate('''async () => {{
                await window.museAccount?.refresh?.();
            }}''')
            page.wait_for_timeout(200)

            # Modal & private UI must close/empty synchronously on signout
            assert page.evaluate(
                "document.getElementById('smMemoryModalBackdrop')?.hidden === true"
            )
            assert "Wild Meadow Press" not in (page.text_content("#smMemoryModalBody") or "")
            guest_raw = page.evaluate("localStorage.getItem('muse.sm.guest_sample.v1')")
            assert guest_raw in (None, "") or "wild meadow" not in guest_raw.lower()

            # Switch without reload to user-b
            set_user_cookie(ctx_desk, "user-b")
            page.evaluate('''async () => {{
                await window.museAccount?.refresh?.();
            }}''')
            page.wait_for_timeout(300)

            # Release delayed Account A responses -> queued PUT #2 must abort,
            # and delayed responses must not overwrite Account B!
            held_routes[0].continue_()
            held_puts[0].continue_()
            page.wait_for_timeout(350)
            assert len(put_attempts) == 1, f"Stale queued PUT executed: {{put_attempts}}"
            state_b = page.evaluate("window.museSellerMemory.getState()")
            assert state_b["ownerId"] == "user-b", state_b
            assert all(
                "Botanical Linocut" not in str(e)
                and "Wild Meadow" not in str(e)
                and "Account A" not in str(e)
                for e in state_b["memoryEntries"]
            )
            panel_b = page.text_content("#smContextPanel") or ""
            assert "Wild Meadow" not in panel_b
            assert "Account A" not in panel_b

            assert not errors, f"Uncaught page errors: {{errors}}"
            page.unroute("**/api/v1/seller-memory/recommend")
            page.unroute("**/api/v1/seller-memory")
            browser.close()
        """
    )

    try:
        res = subprocess.run(
            [pw_python, "-c", script],
            capture_output=True,
            text=True,
            check=False,
            timeout=60,
        )
    except subprocess.TimeoutExpired as exc:
        pytest.fail(
            f"Playwright subprocess timed out after 60s.\nSTDOUT:\n{exc.stdout}\n"
            f"STDERR:\n{exc.stderr}"
        )
    assert res.returncode == 0, f"STDOUT:\n{res.stdout}\nSTDERR:\n{res.stderr}"
