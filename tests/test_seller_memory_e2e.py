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

    res = subprocess.run([pw_python, "-c", script], capture_output=True, text=True, check=False)
    assert res.returncode == 0, f"STDOUT:\n{res.stdout}\nSTDERR:\n{res.stderr}"
