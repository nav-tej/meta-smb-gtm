"""Guard against idle /api/ request loops across every page and workspace state.

Motivation: headless browser tabs left open on `/first-ad` previously looped on
`GET /api/v1/account/me` (fixed in 6c9173c), sending 1.5M requests and triggering
Vercel team blocking.

For every page and state (`signed_out`, `own`, `sample`) covered by
`tests/test_api_calls_per_page_e2e.py` (7 pages x 3 states = 21 tabs on a local
127.0.0.1 server with the same fixtures):
- load each page and wait for initial load to settle;
- stay idle for 20 seconds;
- fail if any `/api/` endpoint is called more than twice during the idle window;
- always close every browser context and browser instance.
"""

from __future__ import annotations

import importlib
import json
import os
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

from src.api.main import app
from src.services.accounts import AccountSession

PAGES = ["/", "/today", "/create", "/first-ad", "/progress", "/digest", "/welcome"]
STATES = [
    ("signed_out", None, ""),
    ("own", "calls-u1", ""),
    ("sample", "calls-u1", "?workspace=sample"),
]
SETTLE_SECONDS = 3
IDLE_SECONDS = 20
MAX_IDLE_CALLS_PER_ENDPOINT = 2


def _find_playwright_python() -> str | None:
    candidates = [os.environ.get("PLAYWRIGHT_PYTHON"), "/usr/bin/python3", sys.executable]
    for candidate in candidates:
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


@pytest.fixture
def idle_loop_server(monkeypatch: pytest.MonkeyPatch):
    """Local 127.0.0.1 server with the exact fixtures from test_api_calls_per_page_e2e.py."""
    stores: dict[str, dict[str, Any]] = {
        "calls-u1": {
            "document": {
                "onboarding": {
                    "business_name": "Wild Meadow Prints",
                    "business_type": "products",
                    "website_url": "https://wildmeadow.test",
                    "shop_urls": ["https://wildmeadow.test"],
                    "completed_at": "2026-11-10T10:00:00Z",
                    "competitors": [{"name": "Acme Prints", "url": "https://acme-prints.test"}],
                    "preferences": {"goal": "Grow visits"},
                }
            },
            "version": 1,
            "owner_id": "calls-u1",
        }
    }
    account = AccountSession(
        user_id="calls-u1",
        email="owner@wildmeadow.test",
        email_verified=True,
        access_token="tok",
        session_id=None,
    )

    async def fake_resolve(request: Any, _response: Any = None, require_verified: bool = False):
        if request.cookies.get("muse_e2e_user") == "calls-u1":
            return account
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
        "src.api.digest_email",
        "src.api.intel",
        "src.api.billing",
        "src.api.media",
        "src.services.accounts",
        "src.services.daily_brief",
        "src.services.digest_preview",
        "src.services.outcomes",
    ):
        module = importlib.import_module(name)
        for attr, fake in fakes.items():
            if hasattr(module, attr):
                monkeypatch.setattr(module, attr, fake)
    monkeypatch.setattr("src.api.intel.collect_entries", no_crawl)

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
        yield f"http://127.0.0.1:{port}"
    finally:
        server.should_exit = True
        thread.join(timeout=3)


def test_no_page_loops_api_requests_while_idle_e2e(idle_loop_server: str) -> None:
    """Every page x state stays quiet (<= 2 calls per /api/ endpoint) during 20s idle."""
    pw_python = _find_playwright_python()
    if pw_python is None:
        pytest.skip("Playwright Python runtime unavailable")

    from tests.e2e_helpers import with_cpu_throttle

    script = with_cpu_throttle(
        f"""
        import json
        import time
        from urllib.parse import urlparse
        from playwright.sync_api import sync_playwright

        BASE = {idle_loop_server!r}
        PAGES = {PAGES!r}
        STATES = {STATES!r}
        SETTLE_SECONDS = {SETTLE_SECONDS}
        IDLE_SECONDS = {IDLE_SECONDS}

        results = []
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            try:
                for state, user, qs in STATES:
                    batch = []
                    try:
                        for path in PAGES:
                            ctx = browser.new_context(viewport={{"width": 1440, "height": 900}})
                            if user:
                                ctx.add_cookies([{{
                                    "name": "muse_e2e_user",
                                    "value": user,
                                    "url": BASE,
                                }}])
                            page = ctx.new_page()
                            rec = {{
                                "state": state,
                                "page": path,
                                "qs": qs,
                                "phase": "load",
                                "load_counts": {{}},
                                "idle_counts": {{}},
                            }}

                            def on_request(request, rec=rec):
                                url = urlparse(request.url)
                                if not url.path.startswith("/api/"):
                                    return
                                bucket = (
                                    rec["idle_counts"]
                                    if rec["phase"] == "idle"
                                    else rec["load_counts"]
                                )
                                bucket[url.path] = bucket.get(url.path, 0) + 1

                            page.on("request", on_request)
                            batch.append((ctx, page, rec))

                        for _ctx, page, rec in batch:
                            page.goto(
                                BASE + rec["page"] + rec["qs"],
                                wait_until="load",
                                timeout=30000,
                            )

                        # Let initial post-load fetches finish before starting the 20s idle window.
                        anchor = batch[0][1]
                        anchor.wait_for_timeout(SETTLE_SECONDS * 1000)

                        for _ctx, _page, rec in batch:
                            rec["phase"] = "idle"

                        deadline = time.monotonic() + IDLE_SECONDS
                        while time.monotonic() < deadline:
                            remaining_ms = max(50, int((deadline - time.monotonic()) * 1000))
                            anchor.wait_for_timeout(min(500, remaining_ms))

                        for _ctx, _page, rec in batch:
                            results.append({{
                                "state": rec["state"],
                                "page": rec["page"],
                                "load_counts": rec["load_counts"],
                                "idle_counts": rec["idle_counts"],
                            }})
                    finally:
                        for ctx, _page, _rec in batch:
                            try:
                                ctx.close()
                            except Exception:
                                pass
            finally:
                browser.close()

        print(json.dumps(results))
        """
    )

    proc = subprocess.run(
        [pw_python, "-c", script],
        capture_output=True,
        text=True,
        check=False,
        timeout=240,
    )
    assert proc.returncode == 0, f"STDOUT:\n{proc.stdout[-3000:]}\nSTDERR:\n{proc.stderr[-3000:]}"

    rows = json.loads(proc.stdout.strip().splitlines()[-1])
    assert len(rows) == len(PAGES) * len(STATES)
    if os.environ.get("MUSE_IDLE_PRINT") == "1":
        print("\nIDLE_COUNTS_JSON=" + json.dumps(rows))

    offenders: list[str] = []
    for row in rows:
        for endpoint, count in sorted(row["idle_counts"].items()):
            if count > MAX_IDLE_CALLS_PER_ENDPOINT:
                offenders.append(
                    f"{row['state']} {row['page']}: {endpoint} called {count} times "
                    f"during {IDLE_SECONDS}s idle (limit {MAX_IDLE_CALLS_PER_ENDPOINT})"
                )

    assert not offenders, "Idle /api/ request loop detected:\n" + "\n".join(offenders)
