"""Offline real Chromium E2E & contract tests for state-aware home copy and sample freshness."""

from __future__ import annotations

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

from src.api.main import app
from src.models.directive import parse_research_directive
from src.services.accounts import AccountSession

REPO_ROOT = Path(__file__).resolve().parents[1]


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


def test_own_chips_parse_to_four_distinct_focuses_and_versions_match() -> None:
    """Verify own-workspace chip directives parse to pricing/products/gifting/posting & ?v=."""
    directives = [
        ("How do my prices compare with competitors?", "pricing"),
        ("Show me easier product moves for solo makers", "products"),
        ("Gift ideas for my shop this season", "gifting"),
        ("What should I post on Instagram this week?", "posting"),
    ]
    focuses = []
    for text, expected_focus in directives:
        parsed, msg = parse_research_directive(text)
        assert parsed is not None, msg
        assert parsed.focus == expected_focus, (text, parsed.focus)
        focuses.append(parsed.focus)
    assert len(set(focuses)) == 4

    index_html = (REPO_ROOT / "src/api/static/index.html").read_text(encoding="utf-8")
    assert "reco-actions.js?v=20261118-ag1" in index_html
    for name in (
        "index.html",
        "creator.html",
        "digest.html",
        "first-ad.html",
        "progress.html",
        "today.html",
    ):
        html = (REPO_ROOT / f"src/api/static/{name}").read_text(encoding="utf-8")
        assert "muse-shell.js?v=20261118-ag1" in html, name


@pytest.fixture
def state_copy_server(monkeypatch: pytest.MonkeyPatch):
    """Run FastAPI app supporting all 4 visitor states plus monitor error injection."""
    mode = {"configured": True}
    users = {
        "u-runs": AccountSession(
            user_id="u-runs",
            email="runs@cedarkiln.test",
            email_verified=True,
            access_token="tok-r",
            session_id=None,
        ),
        "u-empty": AccountSession(
            user_id="u-empty",
            email="empty@cedarkiln.test",
            email_verified=True,
            access_token="tok-e",
            session_id=None,
        ),
        "u-unverified": AccountSession(
            user_id="u-unverified",
            email="unverified@cedarkiln.test",
            email_verified=False,
            access_token="tok-u",
            session_id=None,
        ),
    }

    async def fake_resolve(request: Any, _response: Any = None, require_verified: bool = False):
        uid = request.cookies.get("muse_e2e_user")
        acc = users.get(uid) if uid else None
        if acc is None:
            if require_verified:
                raise HTTPException(401, "Sign in required")
            return None
        if require_verified and not acc.email_verified:
            raise HTTPException(403, "Confirm email")
        return acc

    async def fake_snapshot(account: AccountSession | None) -> dict[str, Any]:
        if not mode["configured"]:
            return {"configured": False, "user": None, "usage": None, "live_available": False}
        if account is None:
            return {"configured": True, "user": None, "usage": None, "live_available": False}
        rem = 3 if account.user_id == "u-runs" else 0
        return {
            "configured": True,
            "user": {
                "id": account.user_id,
                "email": account.email,
                "email_verified": account.email_verified,
            },
            "usage": {"plan": "starter", "used": 3 - rem, "limit": 3, "remaining": rem},
            "runs_remaining": rem,
            "live_available": account.email_verified and rem > 0,
        }

    async def fake_load(account: AccountSession) -> dict[str, Any]:
        return {
            "document": {
                "onboarding": {
                    "business_name": "Cedar Kiln Studio",
                    "website_url": "https://cedarkiln.test",
                    "shop_urls": ["https://cedarkiln.test"],
                    "completed_at": "2026-11-10T10:00:00Z",
                    "competitors": [{"name": "Clay Bench", "url": "https://claybench.test"}],
                }
            },
            "version": 1,
            "owner_id": account.user_id,
        }

    monkeypatch.setenv("DEMO_MODE", "true")
    monkeypatch.setenv("META_MODEL_API_KEY", "")
    monkeypatch.setenv("DEMO_KEY", "")
    monkeypatch.setattr("src.api.accounts.resolve_account", fake_resolve)
    monkeypatch.setattr("src.services.accounts.resolve_account", fake_resolve)
    monkeypatch.setattr("src.api.accounts.snapshot", fake_snapshot)
    monkeypatch.setattr("src.api.accounts.load_workspace", fake_load)

    @app.get("/__e2e__/set-configured/{flag}", include_in_schema=False)
    async def _set_cfg(flag: str) -> dict[str, bool]:
        mode["configured"] = flag == "1"
        return {"configured": mode["configured"]}

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
        yield f"http://127.0.0.1:{port}"
    finally:
        server.should_exit = True
        thread.join(timeout=2)


def test_four_visitor_states_and_sample_freshness_e2e(state_copy_server: str) -> None:
    """Verify 4 visitor states, own/sample chips, and sample freshness at 375px and 1440px."""
    pw_python = _find_playwright_python()
    if pw_python is None:
        pytest.skip("Playwright Python runtime unavailable")

    script = textwrap.dedent(
        f"""
        import json
        from urllib.request import urlopen
        from playwright.sync_api import sync_playwright

        BASE = {state_copy_server!r}

        def set_cfg(on: bool) -> None:
            urlopen(f"{{BASE}}/__e2e__/set-configured/{{'1' if on else '0'}}").read()

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)

            for width in (375, 1440):
                # 1. Local demo (configured = false)
                set_cfg(False)
                cd = browser.new_context(viewport={{"width": width, "height": 844}})
                pd = cd.new_page()
                pd.goto(f"{{BASE}}/", wait_until="domcontentloaded")
                pd.wait_for_function(
                    "() => (document.querySelector('#competitorSnapshotsNote') || {{}})"
                    ".textContent.includes('live server')"
                )
                assert "0 in demo" in pd.locator("#addCompetitorBtn").inner_text()
                assert "In this saved demo" in pd.locator("#addCompetitorCost").inner_text()
                assert "Muse Spark brief" not in pd.locator("#competitorSnapshotsNote").inner_text()
                assert not pd.evaluate("document.documentElement.scrollWidth > window.innerWidth")
                cd.close()

                # 2. Guest (configured = true, signed out)
                set_cfg(True)
                cg = browser.new_context(viewport={{"width": width, "height": 844}})
                pg = cg.new_page()
                pg.goto(f"{{BASE}}/", wait_until="domcontentloaded")
                pg.wait_for_function(
                    "() => (document.querySelector('#addCompetitorBtn') || {{}})"
                    ".textContent.trim() === 'Add shop'"
                )
                assert "3 free runs" in pg.locator("#addCompetitorCost").inner_text()
                snap_note_g = pg.locator("#competitorSnapshotsNote").inner_text()
                assert "Create a free account" in snap_note_g
                sample_chips = pg.locator("#jrSteerChips .jr-chip-btn").all_inner_texts()
                assert "Why $59.99 entry" in sample_chips, sample_chips
                assert "Gifts under $50" in sample_chips, sample_chips
                assert not pg.evaluate("document.documentElement.scrollWidth > window.innerWidth")
                cg.close()

                # 3. Signed in with runs (own workspace) -> own chips & 4 distinct focuses
                cr = browser.new_context(viewport={{"width": width, "height": 844}})
                cr.add_cookies([{{"name": "muse_e2e_user", "value": "u-runs", "url": BASE}}])
                pr = cr.new_page()
                pr.goto(f"{{BASE}}/", wait_until="domcontentloaded")
                pr.wait_for_function(
                    "() => (document.querySelector('#addCompetitorBtn') || {{}})"
                    ".textContent.includes('Add and analyze')"
                )
                assert "Uses 1 run." in pr.locator("#addCompetitorCost").inner_text()
                snap_note_r = pr.locator("#competitorSnapshotsNote").inner_text()
                assert "Muse Spark brief" not in snap_note_r
                assert "SikhiArt" not in snap_note_r
                own_chips = pr.locator("#jrSteerChips .jr-chip-btn").all_inner_texts()
                assert "How do my prices compare?" in own_chips, own_chips
                assert "Gift ideas" in own_chips, own_chips
                assert all("$59.99" not in c and "$50" not in c for c in own_chips), own_chips
                assert not pr.evaluate("document.documentElement.scrollWidth > window.innerWidth")

                # 4. Signed in viewing sample shop with monitor error injected
                def fake_monitor(route):
                    route.fulfill(
                        json={{
                            "run": {{
                                "checked_at": "2026-11-16T14:00:00Z",
                                "competitors": [
                                    {{
                                        "name": "SikhiArt.com",
                                        "status": "error",
                                        "error": "Timeout",
                                    }}
                                ],
                            }},
                            "notifications": [],
                        }}
                    )

                pr.route("**/api/v1/monitor**", fake_monitor)
                pr.goto(f"{{BASE}}/?workspace=sample", wait_until="domcontentloaded")
                pr.wait_for_selector(".ms-watch-time")
                pr.wait_for_timeout(300)
                watch_txt = pr.locator("#sellerList").inner_text()
                assert "Couldn’t check" not in watch_txt, watch_txt
                assert "Saved snapshot · Nov 3" in watch_txt, watch_txt
                snap_note_s = pr.locator("#competitorSnapshotsNote").inner_text()
                assert "New analyses use 1 run." in snap_note_s, snap_note_s
                sample_chips_2 = pr.locator("#jrSteerChips .jr-chip-btn").all_inner_texts()
                assert "Why $59.99 entry" in sample_chips_2, sample_chips_2
                assert not pr.evaluate("document.documentElement.scrollWidth > window.innerWidth")
                cr.close()

                # 5. Signed in without runs & unverified email
                for uid, expected_cost in [
                    ("u-empty", "No runs remaining"),
                    ("u-unverified", "Confirm your email"),
                ]:
                    cx = browser.new_context(viewport={{"width": width, "height": 844}})
                    cx.add_cookies([{{"name": "muse_e2e_user", "value": uid, "url": BASE}}])
                    px = cx.new_page()
                    px.goto(f"{{BASE}}/", wait_until="domcontentloaded")
                    px.wait_for_function(
                        "() => (document.querySelector('#addCompetitorBtn') || {{}})"
                        ".textContent.trim() === 'Add shop'"
                    )
                    assert expected_cost in px.locator("#addCompetitorCost").inner_text()
                    assert not px.evaluate(
                        "document.documentElement.scrollWidth > window.innerWidth"
                    )
                    cx.close()

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
