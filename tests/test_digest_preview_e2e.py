"""Real Chromium offline E2E test for Batch 2A personal digest preview & draft preferences."""

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
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
import uvicorn

from src.api.main import app
from src.services.accounts import AccountSession


def _find_playwright_python() -> str | None:
    candidates = [sys.executable, shutil.which("python3") or "", "/usr/bin/python3"]
    for exe in candidates:
        if not exe or not Path(exe).exists():
            continue
        probe = subprocess.run(
            [exe, "-c", "import playwright.sync_api; from PIL import Image"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        if probe.returncode == 0:
            return exe
    return None


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


@pytest.fixture
def digest_preview_server(
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[tuple[str, dict[str, int]]]:
    monkeypatch.setenv("DEMO_MODE", "true")
    monkeypatch.delenv("RESEND_API_KEY", raising=False)
    monkeypatch.delenv("META_MODEL_API_KEY", raising=False)

    spies = {"email": 0, "crawl": 0, "muse": 0}
    workspaces: dict[str, dict[str, Any]] = {
        "user-a": {
            "version": 1,
            "document": {
                "onboarding": {
                    "business_name": "Cedar & Pine Studio",
                    "product_name": "Botanical Linocut",
                    "competitors": ["https://comp-alpha.test"],
                },
                "preferences": {
                    "goal": "win holiday gift buyers",
                    "access": {"minutes_per_week": 25},
                },
            },
        },
        "user-b": {
            "version": 1,
            "document": {
                "onboarding": {
                    "business_name": "Oak & Clay Pottery",
                    "product_name": "Stoneware Mug",
                    "competitors": ["https://comp-beta.test"],
                },
                "preferences": {
                    "goal": "grow wholesale orders",
                    "access": {"minutes_per_week": 60},
                },
            },
        },
    }

    async def fake_resolve(
        request: Any, response: Any, require_verified: bool = False
    ) -> AccountSession | None:
        uid = request.cookies.get("muse_e2e_user")
        if uid == "user-a":
            return AccountSession(
                user_id="user-a",
                email="a@example.com",
                access_token="tok-a",
                session_id="sid-a",
                email_verified=True,
            )
        if uid == "user-b":
            return AccountSession(
                user_id="user-b",
                email="b@example.com",
                access_token="tok-b",
                session_id="sid-b",
                email_verified=True,
            )
        return None

    async def fake_snapshot(account: AccountSession | None) -> dict[str, Any]:
        if account is None:
            return {"authenticated": False, "user": None}
        return {
            "authenticated": True,
            "user": {"id": account.user_id, "email": account.email, "email_verified": True},
            "usage": {"remaining": 3},
            "workspace": workspaces[account.user_id]["document"],
        }

    async def fake_load(account: AccountSession) -> dict[str, Any]:
        row = workspaces[account.user_id]
        return {"version": row["version"], "document": json.loads(json.dumps(row["document"]))}

    async def fake_save(
        account: AccountSession,
        document: dict[str, Any],
        expected_version: int | None,
        expected_owner: str | None = None,
    ) -> dict[str, Any]:
        row = workspaces[account.user_id]
        row["version"] += 1
        row["document"] = json.loads(json.dumps(document))
        return {"version": row["version"], "document": row["document"], "owner_id": account.user_id}

    async def spy_email(*_a: Any, **_k: Any) -> bool:
        spies["email"] += 1
        return True

    async def spy_crawl(*_a: Any, **_k: Any) -> list[Any]:
        spies["crawl"] += 1
        return []

    def spy_muse(*_a: Any, **_k: Any) -> Any:
        spies["muse"] += 1
        raise AssertionError("Muse must not be called")

    monkeypatch.setattr("src.api.digest_email.resolve_account", fake_resolve)
    monkeypatch.setattr("src.api.accounts.resolve_account", fake_resolve)
    monkeypatch.setattr("src.api.accounts.snapshot", fake_snapshot)
    monkeypatch.setattr("src.services.digest_preview.load_workspace", fake_load)
    monkeypatch.setattr("src.services.digest_preview.save_workspace", fake_save)
    monkeypatch.setattr("src.clients.email.send", spy_email)
    monkeypatch.setattr("src.services.competitor_monitor.crawl_entries", spy_crawl)
    monkeypatch.setattr("src.clients.meta.get_meta_client", spy_muse)

    port = _free_port()
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    for _ in range(50):
        if server.started:
            break
        time.sleep(0.05)

    try:
        yield f"http://127.0.0.1:{port}", spies
    finally:
        server.should_exit = True
        thread.join(timeout=5)


def test_digest_preview_and_draft_preferences_mobile_and_desktop_e2e(
    digest_preview_server: tuple[str, dict[str, int]],
) -> None:
    """Verify 375px/1440px Chromium saving/reloading draft preferences and preview offline."""
    pw_python = _find_playwright_python()
    if pw_python is None:
        pytest.skip("Playwright Python runtime unavailable")

    base_url, spies = digest_preview_server

    script = textwrap.dedent(
        f"""
        from playwright.sync_api import sync_playwright

        base_url = {json.dumps(base_url)}

        def assert_no_overflow(page, label):
            dims = page.evaluate(
                "() => ({{sw: document.documentElement.scrollWidth, iw: window.innerWidth}})"
            )
            assert dims["sw"] <= dims["iw"] + 2, f"{{label}} horizontal overflow: {{dims}}"

        with sync_playwright() as p:
            browser = p.chromium.launch()
            errors = []

            viewports = [
                ("mobile", {{"width": 375, "height": 844}}),
                ("desktop", {{"width": 1440, "height": 900}}),
            ]
            for vp_name, vp in viewports:
                ctx = browser.new_context(viewport=vp)
                ctx.add_cookies([{{
                    "name": "muse_e2e_user",
                    "value": "user-a",
                    "url": base_url,
                }}])
                page = ctx.new_page()
                page.on("pageerror", lambda e: errors.append(str(e)))
                page.goto(f"{{base_url}}/digest", wait_until="domcontentloaded")
                page.wait_for_selector("#digestDraftForm:not([hidden])")
                page.wait_for_selector("#digestEmailPreviewBox:not([hidden])")
                assert_no_overflow(page, f"/digest {{vp_name}}")

                banner = page.text_content("#draftOnlyBanner") or ""
                assert "Preview & draft settings only" in banner
                sub_note = page.text_content("#draftExistingSubNote") or ""
                assert "not configured" in sub_note.lower()

                if vp_name == "mobile":
                    page.select_option("#draftCadence", "monthly")
                    page.wait_for_selector("#draftAnchorDayWrap:not([hidden])")
                    page.fill("#draftAnchorDay", "31")
                    page.select_option("#draftTimezone", "America/New_York")
                    page.uncheck('input[name="draftTopic"][value="listing_changes"]')
                    page.click("#draftSaveBtn")
                    page.wait_for_function(
                        "document.getElementById('draftSaveStatus')?.textContent.includes('saved')"
                    )
                    # Reload and verify persistence from server workspace
                    page.reload(wait_until="domcontentloaded")
                    page.wait_for_selector("#digestDraftForm:not([hidden])")
                    page.wait_for_selector("#digestEmailPreviewBox:not([hidden])")
                    assert page.input_value("#draftCadence") == "monthly"
                    assert page.input_value("#draftAnchorDay") == "31"
                    assert page.input_value("#draftTimezone") == "America/New_York"
                    assert not page.is_checked('input[name="draftTopic"][value="listing_changes"]')
                    assert page.is_checked('input[name="draftTopic"][value="pricing"]')

                # Toggle Plain text tab and verify content
                page.click("#previewTabText")
                page.wait_for_selector("#digestPreviewText:not([hidden])")
                txt = page.text_content("#digestPreviewText") or ""
                assert "TOP MOVE:" in txt
                assert "America/New_York" in txt
                srcdoc = page.get_attribute("#digestPreviewFrame", "srcdoc") or ""
                assert "Cedar &amp; Pine Studio" in srcdoc
                ctx.close()

            assert not errors, f"Uncaught browser errors: {{errors}}"
            browser.close()
        """
    )

    env = os.environ.copy()
    env.setdefault("DEMO_MODE", "true")
    res = subprocess.run(
        [pw_python, "-c", script],
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
        env=env,
    )
    assert res.returncode == 0, f"STDOUT:\n{res.stdout}\nSTDERR:\n{res.stderr}"
    assert spies == {"email": 0, "crawl": 0, "muse": 0}


def test_digest_preview_account_switch_and_race_regressions_e2e(
    digest_preview_server: tuple[str, dict[str, int]],
) -> None:
    """Verify A->B delayed r.json(), failed B load, sign-out, and reversed preview race."""
    pw_python = _find_playwright_python()
    if pw_python is None:
        pytest.skip("Playwright Python runtime unavailable")

    base_url, spies = digest_preview_server

    script = textwrap.dedent(
        f"""
        from playwright.sync_api import sync_playwright

        base_url = {json.dumps(base_url)}

        with sync_playwright() as p:
            browser = p.chromium.launch()
            errors = []
            ctx = browser.new_context(viewport={{"width": 1280, "height": 800}})
            ctx.add_cookies([{{
                "name": "muse_e2e_user",
                "value": "user-a",
                "url": base_url,
            }}])
            page = ctx.new_page()
            page.on("pageerror", lambda e: errors.append(str(e)))

            # 1) Load Account A
            page.goto(f"{{base_url}}/digest", wait_until="domcontentloaded")
            page.wait_for_selector("#digestDraftForm:not([hidden])")
            page.wait_for_selector("#digestEmailPreviewBox:not([hidden])")
            srcdoc_a = page.get_attribute("#digestPreviewFrame", "srcdoc") or ""
            assert "Cedar &amp; Pine Studio" in srcdoc_a

            # Hold Account A's r.json() body while switching A -> B
            page.evaluate(
                '''() => {{
                    const origFetch = window.fetch.bind(window);
                    window.__origFetch = origFetch;
                    let holdNextPreviewJson = true;
                    window.fetch = async (input, init) => {{
                        const url = typeof input === 'string' ? input : (input?.url || '');
                        if (holdNextPreviewJson && url.includes('/api/v1/digest/preview')) {{
                            holdNextPreviewJson = false;
                            const body = {{
                                subject: 'HOSTILE_A_SECRET',
                                next_send_display: 'HOSTILE_A_WINDOW',
                                html: '<p>HOSTILE_A_SECRET</p>',
                                text: 'HOSTILE_A_SECRET',
                                draft_preferences: {{
                                    cadence: 'biweekly',
                                    topics: ['pricing'],
                                    timezone: 'UTC',
                                    competitors: ['https://hostile-a.test'],
                                }},
                            }};
                            return {{
                                ok: true,
                                status: 200,
                                json: () => new Promise((resolve) => {{
                                    window.__resolveHeldJson = () => resolve(body);
                                }}),
                            }};
                        }}
                        return origFetch(input, init);
                    }};
                }}'''
            )

            page.click("#draftPreviewBtn")
            page.wait_for_function("() => typeof window.__resolveHeldJson === 'function'")

            # Switch cookie to user-b and dispatch direct A -> B account-change event
            ctx.add_cookies([{{
                "name": "muse_e2e_user",
                "value": "user-b",
                "url": base_url,
            }}])
            page.evaluate(
                '''() => {{
                    window.dispatchEvent(new CustomEvent('muse:account-change', {{
                        detail: {{ user: {{ id: 'user-b', email: 'b@example.com' }} }},
                    }}));
                }}'''
            )
            page.wait_for_function(
                "() => (document.getElementById('digestPreviewFrame')"
                "?.getAttribute('srcdoc') || '').includes('Oak &amp; Clay Pottery')"
            )

            # Now resolve Account A's delayed r.json()
            page.evaluate("() => window.__resolveHeldJson()")
            page.wait_for_timeout(150)

            b_srcdoc = page.get_attribute("#digestPreviewFrame", "srcdoc") or ""
            b_subj = page.text_content("#previewSubject") or ""
            b_win = page.text_content("#previewWindow") or ""
            b_txt = page.text_content("#digestPreviewText") or ""
            b_shops = page.eval_on_selector_all(
                'input[name="draftShop"]', "els => els.map(e => e.value)"
            )
            for hostile in ("HOSTILE_A_SECRET", "HOSTILE_A_WINDOW", "hostile-a.test", "Cedar"):
                assert hostile not in b_srcdoc, f"Leaked {{hostile}} into B srcdoc"
                assert hostile not in b_subj, f"Leaked {{hostile}} into B subject"
                assert hostile not in b_win, f"Leaked {{hostile}} into B window"
                assert hostile not in b_txt, f"Leaked {{hostile}} into B text"
                assert all(hostile not in v for v in b_shops), (
                    f"Leaked {{hostile}} into B shops: {{b_shops}}"
                )
            assert "Oak &amp; Clay Pottery" in b_srcdoc

            # 2) Failed B -> A load (HTTP 503): no B state exposed, save disabled
            def fail_prefs(route):
                route.fulfill(
                    status=503,
                    content_type="application/json",
                    body='{{"detail": "Workspace unavailable"}}',
                )

            page.route("**/api/v1/digest/preferences", fail_prefs)
            ctx.add_cookies([{{
                "name": "muse_e2e_user",
                "value": "user-a",
                "url": base_url,
            }}])
            page.evaluate(
                '''() => {{
                    window.dispatchEvent(new CustomEvent('muse:account-change', {{
                        detail: {{ user: {{ id: 'user-a', email: 'a@example.com' }} }},
                    }}));
                }}'''
            )
            page.wait_for_function(
                "() => (document.getElementById('draftSaveStatus')?.textContent || '')"
                ".includes('Workspace unavailable')"
            )
            assert page.get_attribute("#digestEmailPreviewBox", "hidden") is not None
            assert (page.get_attribute("#digestPreviewFrame", "srcdoc") or "") == ""
            assert (page.text_content("#previewSubject") or "") == ""
            assert (page.text_content("#digestPreviewText") or "") == ""
            assert page.is_disabled("#draftSaveBtn")
            cleared_shops = page.eval_on_selector_all(
                'input[name="draftShop"]', "els => els.map(e => e.value)"
            )
            assert all(v == "" for v in cleared_shops)
            page.unroute("**/api/v1/digest/preferences")

            # 3) Sign-out clears DOM and hides draft form/preview
            ctx.add_cookies([{{
                "name": "muse_e2e_user",
                "value": "user-a",
                "url": base_url,
            }}])
            page.evaluate(
                '''() => {{
                    window.dispatchEvent(new CustomEvent('muse:account-change', {{
                        detail: {{ user: {{ id: 'user-a', email: 'a@example.com' }} }},
                    }}));
                }}'''
            )
            page.wait_for_function(
                "() => (document.getElementById('digestPreviewFrame')"
                "?.getAttribute('srcdoc') || '').includes('Cedar &amp; Pine Studio')"
            )
            page.evaluate(
                '''() => {{
                    window.dispatchEvent(new CustomEvent('muse:account-change', {{
                        detail: {{ user: null }},
                    }}));
                }}'''
            )
            page.wait_for_selector("#draftAccountGate:not([hidden])")
            assert page.get_attribute("#digestDraftForm", "hidden") is not None
            assert page.get_attribute("#digestEmailPreviewBox", "hidden") is not None
            assert (page.get_attribute("#digestPreviewFrame", "srcdoc") or "") == ""

            # 4) Reversed same-owner preview completion: slow 'weekly' vs fast 'monthly'
            page.evaluate(
                '''() => {{
                    window.dispatchEvent(new CustomEvent('muse:account-change', {{
                        detail: {{ user: {{ id: 'user-a', email: 'a@example.com' }} }},
                    }}));
                }}'''
            )
            page.wait_for_function(
                "() => !document.getElementById('draftSaveBtn')?.disabled"
            )
            page.evaluate(
                '''() => {{
                    const origFetch = window.__origFetch || window.fetch.bind(window);
                    let holdNextWeekly = true;
                    window.fetch = async (input, init) => {{
                        const url = typeof input === 'string' ? input : (input?.url || '');
                        if (holdNextWeekly && url.includes('/api/v1/digest/preview')) {{
                            const rawBody = typeof init?.body === 'string' ? init.body : '';
                            if (rawBody.includes('"cadence":"weekly"')) {{
                                holdNextWeekly = false;
                                const resp = await origFetch(input, init);
                                const data = await resp.json();
                                return {{
                                    ok: resp.ok,
                                    status: resp.status,
                                    json: () => new Promise((resolve) => {{
                                        window.__releaseSlowWeekly = () => resolve(data);
                                    }}),
                                }};
                            }}
                        }}
                        return origFetch(input, init);
                    }};
                }}'''
            )
            page.click("#draftPreviewBtn")
            page.wait_for_function("() => typeof window.__releaseSlowWeekly === 'function'")
            page.select_option("#draftCadence", "paused")
            page.wait_for_function(
                "() => (document.getElementById('previewWindow')?.textContent || '')"
                ".toLowerCase().includes('paused')"
            )
            page.evaluate("() => window.__releaseSlowWeekly()")
            page.wait_for_timeout(150)

            assert page.input_value("#draftCadence") == "paused"
            assert "paused" in (page.text_content("#previewWindow") or "").lower()

            ctx.close()
            assert not errors, f"Uncaught browser errors: {{errors}}"
            browser.close()
        """
    )

    env = os.environ.copy()
    env.setdefault("DEMO_MODE", "true")
    res = subprocess.run(
        [pw_python, "-c", script],
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
        env=env,
    )
    assert res.returncode == 0, f"STDOUT:\n{res.stdout}\nSTDERR:\n{res.stderr}"
    assert spies == {"email": 0, "crawl": 0, "muse": 0}
