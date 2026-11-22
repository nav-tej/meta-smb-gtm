"""Home, /today, /progress and /digest fit a services business, and home stops contradicting itself.

Pass 17 walked the app as a consultancy ("North Star Advisory", services, LinkedIn, 30 minutes a
week, 3 runs left while live Muse was off). Home said "Who sells similar art", offered "Gift
ideas", printed "Linkedin", clipped the watch-role menus at the card edge, said "No runs remaining"
under a header that said "3 of 3 runs left", and said "Nothing saved yet" above a move that cited
the saved goal. /today's context bar showed the editor's goal key ("Goal: story") and "Apply
defaults to editor". A products seller keeps "Your shop" and "Gift ideas".
Real app, fixture accounts (every module that reads the account is patched), no live Muse calls.
"""

from __future__ import annotations

import importlib
import json
import socket
import subprocess
import threading
import time
from typing import Any

import pytest
import uvicorn
from fastapi import HTTPException

from src.api.main import app
from src.services.accounts import AccountSession
from src.services.seller_memory import _channel_name, rank_seller_recommendations
from tests.test_api_calls_per_page_e2e import _find_playwright_python


def _document(name: str, business_type: str, goal: str, channels: list[str]) -> dict[str, Any]:
    return {
        "onboarding": {
            "business_name": name,
            "business_type": business_type,
            "website_url": f"https://{name.split()[0].lower()}.test",
            "shop_urls": [f"https://{name.split()[0].lower()}.test"],
            "completed_at": "2026-11-10T10:00:00Z",
            "competitors": [
                {
                    "name": "Brightpath Consulting",
                    "url": "https://brightpath.test",
                    "reason": "Same clients",
                },
                {
                    "name": "Summit Growth",
                    "url": "https://summitgrowth.test",
                    "reason": "Similar offer",
                },
            ],
        },
        "preferences": {"goal": goal, "access": {"minutes_per_week": 30, "channels": channels}},
    }


USERS = {
    "svc": _document(
        "North Star Advisory", "services", "More client inquiries", ["linkedin", "website"]
    ),
    "prod": _document("Wild Meadow Prints", "products", "More sales", ["instagram", "website"]),
}


@pytest.fixture
def any_business_server(monkeypatch: pytest.MonkeyPatch):
    stores = {uid: {"document": doc, "version": 1, "owner_id": uid} for uid, doc in USERS.items()}
    sessions = {
        uid: AccountSession(
            user_id=uid,
            email=f"{uid}@walk.test",
            email_verified=True,
            access_token="tok",
            session_id=None,
        )
        for uid in USERS
    }

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
        # Runs are left, but live Muse is off: the state that used to read "No runs remaining".
        return {
            "configured": True,
            "user": {"id": session.user_id, "email": session.email, "email_verified": True},
            "usage": {"plan": "starter", "used": 0, "limit": 3, "remaining": 3},
            "runs_remaining": 3,
            "live_available": False,
        }

    async def no_crawl(*_args: Any, **_kwargs: Any) -> tuple[list[Any], list[str]]:
        return [], []

    def no_muse(*_args: Any, **_kwargs: Any) -> Any:
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
    monkeypatch.setattr("src.api.seller_memory.collect_entries", no_crawl)
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
    yield f"http://127.0.0.1:{port}"
    server.should_exit = True
    thread.join(timeout=5)


def test_channel_names_keep_brand_casing() -> None:
    assert [_channel_name(c) for c in ("linkedin", "tiktok", "x", "instagram", "website")] == [
        "LinkedIn",
        "TikTok",
        "X",
        "Instagram",
        "Website",
    ]
    result = rank_seller_recommendations(
        business_name="North Star Advisory",
        business_type="services",
        preferences=None,
    )
    text = json.dumps(result)
    assert "Linkedin" not in text and "Tiktok" not in text


def test_home_today_progress_and_digest_fit_a_services_business_e2e(
    any_business_server: str,
) -> None:
    python_bin = _find_playwright_python()
    if not python_bin:
        pytest.skip("Playwright runtime not installed")
    script = f"""
import json
from playwright.sync_api import sync_playwright

BASE = {any_business_server!r}

def text(page):
    return page.evaluate("document.body.innerText")

with sync_playwright() as p:
    browser = p.chromium.launch()
    for width in (1440, 375):
        ctx = browser.new_context(viewport={{"width": width, "height": 900}})
        ctx.add_cookies([{{"name": "muse_e2e_user", "value": "svc", "url": BASE}}])
        page = ctx.new_page()
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))

        page.goto(BASE + "/", wait_until="domcontentloaded")
        page.wait_for_function(
            "document.querySelector('#smHomeContextPanel .sm-sub, .sm-card .sm-sub')"
            " && document.body.innerText.includes('your 30 minutes a week')"
            " && document.body.innerText.includes('Top next move')",
            timeout=20000,
        )
        page.wait_for_function(
            "Array.from(document.querySelectorAll('#jrSteerChips .jr-chip-btn'))"
            ".some(b => b.textContent.trim() === 'More inquiries')",
            timeout=10000,
        )
        body = text(page)
        # The saved goal and minutes, not "Nothing saved yet".
        assert "your goal (more client inquiries) and your 30 minutes a week" in body, body
        assert "Nothing saved yet" not in body
        assert page.locator("#smExpandContextBtn").inner_text().strip() == "Change your goal"
        # Runs are left; live Muse is off. Say that, not "No runs remaining".
        cost = page.locator("#addCompetitorCost").inner_text()
        assert "Live analysis is unavailable right now" in cost, cost
        assert "No runs remaining" not in body
        assert page.locator("#addCompetitorBtn").inner_text().strip() == "Add competitor"
        # Words for a consultancy.
        for wrong in ("similar art", "Gift ideas", "Gifts under", "Linkedin", "Analyze seller",
                      "Your shop is set up", "shop pages scanned", "[live]"):
            assert wrong not in body, (wrong, width)
        assert "LinkedIn" in body
        assert "Your workspace is set up. Get your first result." in body
        kicker = page.locator("#activeWorkspaceKicker").inner_text().strip().lower()
        assert kicker == "your business", kicker
        assert "Many service businesses quote on request" in body
        # The watch-role menus sit inside their competitor row.
        clipped = page.evaluate('''() => Array.from(document.querySelectorAll(
            '#sellerList .jr-seller > .sm-comp-role-wrap select')).map((s) => {{
              const row = s.closest('.jr-seller').getBoundingClientRect();
              const box = s.getBoundingClientRect();
              return box.right > row.right + 1 || box.left < row.left - 1;
            }})''')
        assert clipped and not any(clipped), clipped
        assert not page.evaluate("document.documentElement.scrollWidth > window.innerWidth")

        page.goto(BASE + "/today", wait_until="domcontentloaded")
        page.wait_for_selector("#smStudioContextBar .sm-badge-goal", timeout=20000)
        goal = page.locator("#smStudioContextBar .sm-badge-goal").inner_text()
        assert goal == "Goal: Share what you do", goal
        assert page.locator("#smStudioApplyBtn").inner_text() == "Use this move in my post"
        body = text(page)
        assert "Put your link in your profile" in body, body
        assert "Back to making" not in body and "BACK TO MAKING" not in body
        assert "similar sellers" not in body

        page.goto(BASE + "/progress", wait_until="domcontentloaded")
        options = page.locator("#pgFormChannel option").all_inner_texts()
        assert "LinkedIn" in options and "Website or direct" in options, options
        assert "Online Shop / Direct" not in options

        page.goto(BASE + "/digest", wait_until="domcontentloaded")
        body = text(page)
        assert "What changed at the competitors you watch" in body, body
        assert "your shop website" not in body
        assert not errors, errors
        ctx.close()

    # A products seller keeps the shop words and the gift chip.
    ctx = browser.new_context(viewport={{"width": 1440, "height": 900}})
    ctx.add_cookies([{{"name": "muse_e2e_user", "value": "prod", "url": BASE}}])
    page = ctx.new_page()
    page.goto(BASE + "/", wait_until="domcontentloaded")
    page.wait_for_function(
        "Array.from(document.querySelectorAll('#jrSteerChips .jr-chip-btn'))"
        ".some(b => b.textContent.trim() === 'Gift ideas')",
        timeout=20000,
    )
    assert page.locator("#activeWorkspaceKicker").inner_text().strip().lower() == "your shop"
    page.goto(BASE + "/today", wait_until="domcontentloaded")
    page.wait_for_selector("#smStudioContextBar .sm-badge-goal", timeout=20000)
    goal = page.locator("#smStudioContextBar .sm-badge-goal").inner_text()
    assert goal.startswith("Goal: "), goal
    assert goal not in ("Goal: story", "Goal: visits", "Goal: gift"), goal
    browser.close()
print("ANY_BUSINESS_OK")
"""
    proc = subprocess.run(
        [python_bin, "-c", script], capture_output=True, text=True, timeout=240, check=False
    )
    assert proc.returncode == 0 and "ANY_BUSINESS_OK" in proc.stdout, (
        f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
    )
