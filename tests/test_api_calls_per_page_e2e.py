"""How many /api/v1 calls each page makes, and that no page keeps calling once it has loaded.

On Vercel every /api/v1 request runs the Python function once, so calls per page view are what
the free tier pays for. Argon found `/first-ad` asking for `account/me` in an endless loop
(`gemini/vercel-usage-nov20`); this guards against the next one.

For `/`, `/today`, `/create`, `/first-ad`, `/progress`, `/digest` and `/welcome`, signed out, in a
seller's own finished workspace and in the sample shop (21 page loads at 1440px, local server only):

- the calls on load stay at or under the counts measured on Nov 20 after identical in-flight GETs
  were shared (`account.js`), see docs/launch/ARGON_API_CALLS_PER_PAGE_NOV20.md;
- no request repeats with the same method, path, query and body during one load;
- nothing more is sent during 20 seconds of idle;
- one `muse:account-change` for the same seller causes at most one round of calls, then quiet.

Own-workspace `/today` and `/create` include the once-per-device shop listing import
(`POST /api/v1/ingest-storefront`); every load here is a new device.
"""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import threading
import time
from collections import Counter
from pathlib import Path
from typing import Any

import pytest
import uvicorn
from fastapi import HTTPException

from src.api.main import app
from src.services.accounts import AccountSession

PAGES = ["/", "/today", "/create", "/first-ad", "/progress", "/digest", "/welcome"]

# Calls on one load, measured Nov 20 2026 after the in-flight GET sharing (before: 145 in total).
CEILINGS: dict[str, dict[str, int]] = {
    "signed_out": {
        "/": 8, "/today": 4, "/create": 5, "/first-ad": 3, "/progress": 3, "/digest": 7,
        "/welcome": 3,
    },
    "own": {
        "/": 12, "/today": 8, "/create": 9, "/first-ad": 5, "/progress": 5, "/digest": 7,
        "/welcome": 4,
    },
    "sample": {
        "/": 11, "/today": 9, "/create": 8, "/first-ad": 4, "/progress": 4, "/digest": 10,
        "/welcome": 4,
    },
}  # fmt: skip

IDLE_SECONDS = 20


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
def calls_server(monkeypatch: pytest.MonkeyPatch):
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
    import importlib

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
    # The shop listing import is a public crawl; never leave the machine in a test.
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


def test_calls_per_page_stay_low_and_pages_go_quiet_e2e(calls_server: str) -> None:
    pw_python = _find_playwright_python()
    if pw_python is None:
        pytest.skip("Playwright Python runtime unavailable")

    from tests.e2e_helpers import with_cpu_throttle

    script = with_cpu_throttle(
        f"""
        import json, time
        from urllib.parse import urlparse
        from playwright.sync_api import sync_playwright

        BASE = {calls_server!r}
        PAGES = {PAGES!r}
        STATES = [("signed_out", None, ""), ("own", "calls-u1", ""),
                  ("sample", "calls-u1", "?workspace=sample")]
        IDLE = {IDLE_SECONDS}
        last = [time.time()]

        def quiet(page, seconds, limit):
            # Wait until no page has sent an /api/v1 request for `seconds`; False on `limit`.
            started = time.time()
            last[0] = time.time()
            while time.time() - last[0] < seconds:
                if time.time() - started > limit:
                    return False
                page.wait_for_timeout(200)
            return True

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            tabs = []
            for state, user, qs in STATES:
                for path in PAGES:
                    ctx = browser.new_context(viewport={{"width": 1440, "height": 900}})
                    if user:
                        ctx.add_cookies([{{"name": "muse_e2e_user", "value": user, "url": BASE}}])
                    page = ctx.new_page()
                    tab = {{"state": state, "page": path, "qs": qs, "phase": "load",
                            "load": [], "idle": [], "event": [],
                            "n": {{"load": 0, "idle": 0, "event": 0}}}}
                    def on_request(request, tab=tab):
                        url = urlparse(request.url)
                        if not url.path.startswith("/api/v1/"):
                            return
                        # A loop sends thousands: count them all, keep the first few.
                        tab["n"][tab["phase"]] += 1
                        if len(tab[tab["phase"]]) < 400:
                            tab[tab["phase"]].append([request.method, url.path, url.query,
                                                      request.post_data or ""])
                        last[0] = time.time()
                    page.on("request", on_request)
                    tabs.append((tab, page))
            for tab, page in tabs:
                page.goto(BASE + tab["page"] + tab["qs"], wait_until="domcontentloaded",
                          timeout=30000)
            anchor = tabs[0][1]
            loaded = quiet(anchor, 4, 60)
            settled = False
            if loaded:
                for tab, _ in tabs:
                    tab["phase"] = "idle"
                anchor.wait_for_timeout(IDLE * 1000)
                for tab, page in tabs:
                    tab["phase"] = "event"
                    page.evaluate(
                        "() => window.dispatchEvent(new CustomEvent('muse:account-change', "
                        "{{ detail: window.museAccount.getSnapshot() }}))"
                    )
                settled = quiet(anchor, 4, 30)
            out = [dict(tab, loaded=loaded, settled=settled) for tab, _ in tabs]
            browser.close()
        print(json.dumps(out))
        """
    )
    proc = subprocess.run(
        [pw_python, "-c", script], capture_output=True, text=True, check=False, timeout=240
    )
    assert proc.returncode == 0, f"STDOUT:\n{proc.stdout[-3000:]}\nSTDERR:\n{proc.stderr[-3000:]}"
    tabs = json.loads(proc.stdout.strip().splitlines()[-1])
    assert len(tabs) == 21

    problems: list[str] = []
    if not tabs[0]["loaded"]:
        problems.append("pages kept calling /api/v1 for 60 s after load (a request loop?)")
    for tab in tabs:
        where = f"{tab['state']} {tab['page']}"
        load = [tuple(call) for call in tab["load"]]
        count = tab["n"]
        ceiling = CEILINGS[tab["state"]][tab["page"]]
        if count["load"] > ceiling:
            problems.append(
                f"{where}: {count['load']} calls on load, ceiling {ceiling}: {load[:12]}"
            )
        repeats = sorted(call for call, n in Counter(load).items() if n > 1)
        if repeats:
            problems.append(f"{where}: repeated on load: {repeats[:6]}")
        if not tab["loaded"]:
            continue
        if count["idle"]:
            problems.append(f"{where}: {count['idle']} calls while idle: {tab['idle'][:12]}")
        if count["event"] > count["load"]:
            problems.append(
                f"{where}: one account-change caused {count['event']} calls "
                f"(load had {count['load']}): {tab['event'][:12]}"
            )
        if not tab["settled"]:
            problems.append(f"{where}: still calling 30 s after one account-change")
    assert not problems, "\n".join(problems)
