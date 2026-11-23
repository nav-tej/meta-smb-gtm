"""Offline Chromium E2E tests for weekly automatic watchlist checks on /digest and /today."""

from __future__ import annotations

import os
import shutil
import socket
import subprocess
import sys
import threading
import time
from copy import deepcopy
from typing import Any

import pytest
import uvicorn
from fastapi import HTTPException

from src.api import accounts as accounts_api
from src.api import daily_brief as brief_api
from src.api import intel as intel_api
from src.api.main import app
from src.config import get_settings
from src.services import daily_brief as brief_service
from src.services import watchlist_store
from src.services.accounts import AccountSession
from tests.e2e_helpers import with_cpu_throttle


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
def auto_watchlist_server(monkeypatch: pytest.MonkeyPatch):
    """Run real FastAPI app with a toggleable WATCHLIST_AUTO_CHECK_ENABLED flag."""
    user = AccountSession(
        user_id="auto-wl-u1",
        email="founder@northstar.test",
        email_verified=True,
        access_token="tok-auto-wl",
        session_id=None,
    )
    flag_state: dict[str, Any] = {
        "enabled": False,
        "paused": False,
        "next_check_at": "2026-11-30T13:00:00Z",
        "last_auto_check_at": "2026-11-23T13:00:00Z",
    }
    doc: dict[str, Any] = {
        "onboarding": {
            "business_name": "Northstar Advisory",
            "business_type": "services",
            "website_url": "https://northstar.test",
            "completed_at": "2026-11-20T10:00:00Z",
            "competitors": [
                {"name": "Summit Consulting", "url": "https://summit.test"},
                {"name": "Harbor Partners", "url": "https://harbor.test"},
            ],
        },
        "preferences": {
            "goal": "Grow advisory inquiries",
            "access": {"minutes_per_week": 60, "channels": ["website", "linkedin"]},
            "competitor_checks": {
                "https://summit.test": {
                    "name": "Summit Consulting",
                    "url": "https://summit.test",
                    "status": "unchanged",
                    "source": "manual",
                    "checked_at": "2026-11-22T10:00:00Z",
                    "summary": "No changes since Nov 20.",
                    "error": "",
                }
            },
        },
        "outcomes": [],
    }
    table_checks: dict[str, dict[str, Any]] = {
        "https://summit.test": {
            "name": "Summit Consulting",
            "url": "https://summit.test",
            "status": "changed",
            "source": "auto",
            "checked_at": "2026-11-23T13:00:00Z",
            "summary": "1 new page since Nov 20.",
            "counts": {"new_listing": 1, "removed_listing": 0, "price_change": 0},
            "error": "",
        },
        "https://harbor.test": {
            "name": "Harbor Partners",
            "url": "https://harbor.test",
            "status": "unchanged",
            "source": "manual",
            "checked_at": "2026-11-22T12:00:00Z",
            "summary": "No changes since Nov 20.",
            "counts": {"new_listing": 0, "removed_listing": 0, "price_change": 0},
            "error": "",
        },
    }

    async def fake_resolve(request: Any, _response: Any = None, require_verified: bool = False):
        if request.cookies.get("muse_e2e_user") == "auto-wl-u1":
            return user
        if require_verified:
            raise HTTPException(401, "Sign in required")
        return None

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

    async def fake_load(account: AccountSession) -> dict[str, Any]:
        return {"document": deepcopy(doc), "version": 2, "owner_id": account.user_id}

    def fake_auto_enabled() -> bool:
        return bool(flag_state["enabled"])

    async def fake_get_checks(
        user_id: str, *, with_snapshots: bool = False
    ) -> dict[str, Any] | None:
        if not flag_state["enabled"]:
            return None
        return {
            "enabled": True,
            "checks": deepcopy(table_checks),
            "schedule": {
                "paused": flag_state["paused"],
                "next_check_at": flag_state["next_check_at"],
                "last_auto_check_at": flag_state["last_auto_check_at"],
            },
        }

    async def fake_set_paused(user_id: str, paused: bool) -> dict[str, Any]:
        flag_state["paused"] = bool(paused)
        return {
            "paused": flag_state["paused"],
            "next_check_at": flag_state["next_check_at"],
            "last_auto_check_at": flag_state["last_auto_check_at"],
        }

    monkeypatch.setenv("DEMO_MODE", "true")
    monkeypatch.setenv("ACCOUNTS_REQUIRED", "true")
    monkeypatch.setenv("META_MODEL_API_KEY", "")
    monkeypatch.setenv("DEMO_KEY", "")
    get_settings.cache_clear()
    monkeypatch.setattr(accounts_api, "resolve_account", fake_resolve)
    monkeypatch.setattr("src.services.accounts.resolve_account", fake_resolve)
    monkeypatch.setattr(accounts_api, "snapshot", fake_snapshot)
    monkeypatch.setattr(accounts_api, "load_workspace", fake_load)
    monkeypatch.setattr(intel_api, "resolve_account", fake_resolve)
    monkeypatch.setattr(intel_api, "load_workspace", fake_load)
    monkeypatch.setattr(brief_api, "resolve_account", fake_resolve)
    monkeypatch.setattr(brief_service, "load_workspace", fake_load)
    monkeypatch.setattr(watchlist_store, "auto_check_enabled", fake_auto_enabled)
    monkeypatch.setattr(watchlist_store, "get_checks", fake_get_checks)
    monkeypatch.setattr(watchlist_store, "set_paused", fake_set_paused)

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
        yield f"http://127.0.0.1:{port}", flag_state
    finally:
        server.should_exit = True
        thread.join(timeout=2)


@pytest.mark.parametrize("flag_on", [False, True])
def test_digest_and_today_auto_watchlist_375_and_1440_e2e(
    auto_watchlist_server: tuple[str, dict[str, Any]], flag_on: bool
) -> None:
    """Verify /digest and /today copy & controls at 375px and 1440px with flag off vs on."""
    pw_python = _find_playwright_python()
    if pw_python is None:
        pytest.skip("Playwright Python runtime unavailable")

    base_url, flag_state = auto_watchlist_server
    flag_state["enabled"] = flag_on
    flag_state["paused"] = False

    script = with_cpu_throttle(
        f"""
        from playwright.sync_api import sync_playwright

        BASE = {base_url!r}
        FLAG_ON = {flag_on!r}

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            try:
                for width in (375, 1440):
                    ctx = browser.new_context(viewport={{"width": width, "height": 844}})
                    ctx.add_cookies([{{
                        "name": "muse_e2e_user",
                        "value": "auto-wl-u1",
                        "url": BASE,
                    }}])
                    page = ctx.new_page()

                    # 1. /digest
                    page.goto(f"{{BASE}}/digest", wait_until="networkidle")
                    page.wait_for_selector("#dgCompetitors .dg-card")
                    assert not page.evaluate(
                        "() => document.documentElement.scrollWidth > window.innerWidth"
                    ), f"/digest horizontal overflow at {{width}}px"

                    body = page.locator("#digest").inner_text()
                    if FLAG_ON:
                        page.wait_for_selector("#dgAutoCheckBar")
                        note = page.locator("#dgAutoCheckNote").inner_text()
                        assert "Muse checks your watchlist once a week." in note, note
                        assert "Next check: about Mon, Nov 30." in note, note
                        assert "Automatic check" in body, body
                        assert "Checked by you" in body, body
                        cb = page.locator("#dgAutoCheckToggle")
                        assert cb.is_checked()
                        # Toggle pause off -> on (at 375px only so 1440px starts fresh unpaused)
                        if width == 375:
                            cb.uncheck()
                            page.wait_for_function(
                                "() => (document.getElementById('dgAutoCheckNote')"
                                "?.textContent || '').includes('paused')"
                            )
                            cb.check()
                            page.wait_for_function(
                                "() => (document.getElementById('dgAutoCheckNote')"
                                "?.textContent || '').includes('once a week')"
                            )
                    else:
                        assert page.locator("#dgAutoCheckBar").count() == 0
                        assert "once a week" not in body.lower(), body
                        assert "automatic check" not in body.lower(), body

                    # 2. /today?workspace=own
                    page.goto(f"{{BASE}}/today?workspace=own", wait_until="networkidle")
                    page.wait_for_function(
                        "() => (document.getElementById('msBrief')?.innerText || '')"
                        ".includes('Northstar Advisory')"
                    )
                    brief_text = page.locator("#msBrief").inner_text()
                    if FLAG_ON:
                        assert "Muse checks your watchlist once a week." in brief_text, brief_text
                        assert "Last check: Nov 23." in brief_text, brief_text
                    else:
                        assert "Check now (free) on your digest" in brief_text, brief_text
                        assert "once a week" not in brief_text.lower(), brief_text

                    ctx.close()
            finally:
                browser.close()
        """
    )
    proc = subprocess.run([pw_python, "-c", script], capture_output=True, text=True, check=False)
    assert proc.returncode == 0, f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
