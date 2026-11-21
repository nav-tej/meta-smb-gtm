"""A move longer than the seller's week says "Heads up" all the way into /create.

Pass 15 labelled over-budget moves "Heads up" on the home card, but the handoff to /create did
not carry `over_budget`, so the editor's guidance box still said "Why this fits:" over "Takes
about N minutes, more than your 5 minutes a week". The handoff now carries the flag.
Real app, fixture accounts (every module that reads the account is patched), no live Muse calls.
"""

from __future__ import annotations

import importlib
import json
import socket
import subprocess
import threading
import time
from pathlib import Path
from typing import Any

import pytest
import uvicorn
from fastapi import HTTPException

from src.api.main import app
from src.services.accounts import AccountSession
from tests.test_api_calls_per_page_e2e import _find_playwright_python

PHOTO = Path(__file__).resolve().parent / "fixtures/product_photo.png"
USERS = {"budget-over": 5, "budget-fits": 120}


def _document(minutes: int) -> dict[str, Any]:
    return {
        "onboarding": {
            "business_name": "Wild Meadow Prints",
            "business_type": "products",
            "website_url": "https://wildmeadow.test",
            "shop_urls": ["https://wildmeadow.test"],
            "completed_at": "2026-11-10T10:00:00Z",
            "competitors": [],
        },
        "preferences": {
            "goal": "Grow visits",
            "access": {"minutes_per_week": minutes, "channels": ["instagram", "website"]},
        },
    }


@pytest.fixture
def budget_server(monkeypatch: pytest.MonkeyPatch):
    stores = {
        uid: {"document": _document(minutes), "version": 1, "owner_id": uid}
        for uid, minutes in USERS.items()
    }
    sessions = {
        uid: AccountSession(
            user_id=uid,
            email=f"{uid}@wildmeadow.test",
            email_verified=True,
            access_token="tok",
            session_id=None,
        )
        for uid in USERS
    }
    calls = {"muse": 0}

    async def fake_resolve(request: Any, _response: Any = None, require_verified: bool = False):
        uid = request.cookies.get("muse_e2e_user")
        if uid in sessions:
            return sessions[uid]
        if require_verified:
            raise HTTPException(401, "Sign in required")
        return None

    async def fake_load(session: AccountSession) -> dict[str, Any]:
        return json.loads(json.dumps(stores[session.user_id]))

    async def fake_save(session, doc, expected_version=None, expected_owner=None):
        slot = stores[session.user_id]
        slot["document"] = json.loads(json.dumps(doc))
        slot["version"] = int(slot["version"]) + 1
        return json.loads(json.dumps(slot))

    async def fake_snapshot(session: AccountSession | None) -> dict[str, Any]:
        if session is None:
            return {"configured": True, "user": None, "usage": None, "live_available": False}
        return {
            "configured": True,
            "user": {"id": session.user_id, "email": session.email, "email_verified": True},
            "usage": {"plan": "starter", "used": 0, "limit": 3, "remaining": 3},
            "runs_remaining": 3,
            "live_available": True,
        }

    async def no_crawl(*_args: Any, **_kwargs: Any) -> tuple[list[Any], list[str]]:
        return [], []

    def no_muse(*_args: Any, **_kwargs: Any) -> Any:
        calls["muse"] += 1
        raise AssertionError("no live Muse calls in this test")

    monkeypatch.setenv("DEMO_MODE", "true")
    monkeypatch.setenv("ACCOUNTS_REQUIRED", "true")
    monkeypatch.setenv("META_MODEL_API_KEY", "")
    monkeypatch.setenv("DEMO_KEY", "")
    fakes = {
        "resolve_account": fake_resolve,
        "load_workspace": fake_load,
        "save_workspace": fake_save,
        "snapshot": fake_snapshot,
    }
    for name in (
        "src.api.accounts",
        "src.api.onboarding",
        "src.api.preferences",
        "src.api.seller_memory",
        "src.api.daily_brief",
        "src.api.outcomes",
        "src.api.intel",
        "src.api.media",
        "src.services.accounts",
    ):
        module = importlib.import_module(name)
        for attr, fake in fakes.items():
            if hasattr(module, attr):
                monkeypatch.setattr(module, attr, fake)
    monkeypatch.setattr("src.api.intel.collect_entries", no_crawl)
    monkeypatch.setattr("src.clients.meta.get_meta_client", no_muse)

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    for _ in range(80):
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.1):
                break
        except OSError:
            time.sleep(0.05)
    try:
        yield f"http://127.0.0.1:{port}", calls
    finally:
        server.should_exit = True
        thread.join(timeout=3)


def test_over_budget_move_says_heads_up_on_home_and_in_create_e2e(budget_server) -> None:
    pw_python = _find_playwright_python()
    if pw_python is None:
        pytest.skip("Playwright Python runtime unavailable")
    base_url, calls = budget_server

    from tests.e2e_helpers import with_cpu_throttle

    script = with_cpu_throttle(
        f"""
        import json
        from playwright.sync_api import sync_playwright

        BASE = {base_url!r}
        PHOTO = {str(PHOTO)!r}
        CASES = [("budget-over", "Heads up:", "Why this fits:"),
                 ("budget-fits", "Why this fits:", "Heads up:")]

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            for user, label, other in CASES:
                ctx = browser.new_context(viewport={{"width": 1440, "height": 900}})
                ctx.add_cookies([{{"name": "muse_e2e_user", "value": user, "url": BASE}}])
                page = ctx.new_page()
                page.goto(f"{{BASE}}/", wait_until="domcontentloaded")
                page.wait_for_selector("#smShowImproveTabBtn", state="visible", timeout=15000)
                page.click("#smShowImproveTabBtn")
                card = page.locator("#loop-improve ol.jr-recos li[data-sm-reco-id]").first
                card.wait_for(state="visible", timeout=15000)
                text = card.inner_text()
                assert label in text and other not in text, (user, text)

                card.locator("a", has_text="Make ad").click()
                page.wait_for_url("**/create**")
                page.wait_for_function(
                    "() => document.documentElement.dataset.museMode === 'account_own'"
                )
                if not (page.input_value("#productName") or "").strip():
                    page.fill("#productName", "Meadow print")
                page.locator("#productPhoto").set_input_files(PHOTO)
                page.wait_for_function(
                    "() => (document.getElementById('productImage')?.getAttribute('src') || '')"
                    ".length > 0"
                )
                page.locator("#nextButton").click()
                page.wait_for_selector("#handoffGuidanceBox:not([hidden])", timeout=15000)
                why = page.locator("#handoffWhyFits").inner_text().strip()
                assert why.startswith(label) and other not in why, (user, why)
                ctx.close()
            browser.close()
        print(json.dumps({{"status": "ok"}}))
        """
    )
    proc = subprocess.run(
        [pw_python, "-c", script], capture_output=True, text=True, check=False, timeout=150
    )
    assert proc.returncode == 0, f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
    assert calls["muse"] == 0
