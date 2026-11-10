"""Tests for Step 4b: Non-Sample Artist Workspace Isolation.

Nav's correction (Nov 10):
The end customer is any independent or small artist. Sikh art, SikhiArt.com and
the four watchlist competitors belong strictly to the sample shop (Art of Sarabjit Singh).
Nothing about that niche may be assumed for a real account.

This test proves:
A fixture account for a different kind of artist (Elena Vance Watercolor Studio,
landscape and botanical watercolor prints) completes onboarding, loads its workspace,
and sees ZERO sample-shop terms anywhere in its workspace data, suggestions, or directives.
"""

from __future__ import annotations

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
from fastapi.testclient import TestClient

from src.api.main import app
from src.services.accounts import AccountSession

FORBIDDEN_SAMPLE_TERMS = [
    "Sikh",
    "Sarabjit",
    "Gurpurab",
    "Vaisakhi",
    "Ek Onkar",
    "SikhiArt",
    "Triton Museum",
    "Kala Sangam",
]


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def test_non_sample_artist_onboarding_and_zero_sample_terms(
    monkeypatch: pytest.MonkeyPatch, client: TestClient
) -> None:
    """A landscape watercolor artist completes onboarding and sees ZERO sample-shop terms."""
    # 1. Real artist account session
    user = AccountSession(
        user_id="99999999-9999-4000-8000-999999999999",
        email="elena@wildmeadowstudio.com",
        email_verified=True,
        access_token="token-elena",
        session_id=None,
    )
    workspace_store: dict[str, Any] = {"document": {}, "version": 1}

    async def fake_resolve(*_args: Any, **_kwargs: Any) -> AccountSession:
        return user

    async def fake_load(_account: AccountSession) -> dict[str, Any]:
        return {
            "document": workspace_store["document"],
            "version": workspace_store["version"],
            "owner_id": user.user_id,
        }

    async def fake_save(
        _account: AccountSession,
        doc: dict[str, Any],
        expected_version: Any = None,
        expected_owner: Any = None,
    ) -> dict[str, Any]:
        workspace_store["document"] = doc
        workspace_store["version"] += 1
        return {"document": doc, "version": workspace_store["version"], "owner_id": user.user_id}

    async def fake_snapshot(_account: AccountSession) -> dict[str, Any]:
        return {
            "configured": True,
            "user": {"id": user.user_id, "email": user.email, "email_verified": True},
            "usage": {"plan": "starter", "used": 0, "limit": 3, "remaining": 3, "resets_at": None},
            "live_available": True,
        }

    monkeypatch.setattr("src.api.onboarding.resolve_account", fake_resolve)
    monkeypatch.setattr("src.api.onboarding.load_workspace", fake_load)
    monkeypatch.setattr("src.api.onboarding.save_workspace", fake_save)
    monkeypatch.setattr("src.api.onboarding.snapshot", fake_snapshot)

    monkeypatch.setattr("src.api.directives.resolve_account", fake_resolve)
    monkeypatch.setattr("src.api.directives.load_workspace", fake_load)

    monkeypatch.setattr("src.api.accounts.resolve_account", fake_resolve)
    monkeypatch.setattr("src.api.accounts.load_workspace", fake_load)

    monkeypatch.setattr("src.api.outcomes.resolve_account", fake_resolve)
    monkeypatch.setattr("src.services.outcomes.load_workspace", fake_load)
    monkeypatch.setattr("src.services.outcomes.save_workspace", fake_save)
    monkeypatch.setattr("src.services.accounts.snapshot", fake_snapshot)

    # 2. Complete onboarding with real watercolor artist shop data
    build_payload = {
        "business_name": "Elena Vance Watercolor Studio",
        "shop_urls": [
            "https://elenavanceart.com",
            "https://elenavanceart.etsy.com",
        ],
        "socials": [{"platform": "instagram", "handle": "@elenavanceart"}],
        "competitors": [
            {
                "name": "Wild Meadow Studio",
                "url": "https://www.wildmeadowstudio.com",
                "reason": "Botanical and landscape watercolor prints",
            }
        ],
        "preferences": {
            "medium": "Watercolor & Gouache",
            "price_range": "$25–$180",
        },
    }

    resp = client.post(
        "/api/v1/onboarding/build",
        json=build_payload,
        headers={"Content-Type": "application/json", "X-Muse-Owner": user.user_id},
    )
    assert resp.status_code == 200, f"Onboarding failed: {resp.text}"
    onboarding_data = resp.json()
    assert onboarding_data["success"] is True

    # 3. Retrieve account workspace and verify zero sample terms
    ws_doc = workspace_store["document"]
    ws_text = str(ws_doc)

    for term in FORBIDDEN_SAMPLE_TERMS:
        assert term.lower() not in ws_text.lower(), (
            f"Sample term '{term}' leaked into watercolor workspace document!"
        )

    # 4. Verify directives suggestions adapt to this artist and competitor
    sug_resp = client.get("/api/v1/directives/suggestions")
    assert sug_resp.status_code == 200
    suggestions = sug_resp.json()
    assert len(suggestions) >= 4

    pricing_sug = suggestions[0]["text"]
    assert "Wild Meadow Studio" in pricing_sug or "competitor entry prices" in pricing_sug
    assert "SikhiArt" not in pricing_sug

    all_sug_text = " ".join(s["text"] for s in suggestions)
    for term in FORBIDDEN_SAMPLE_TERMS:
        assert term.lower() not in all_sug_text.lower(), (
            f"Sample term '{term}' leaked into watercolor suggestions: {all_sug_text}"
        )

    # 5. Verify outcomes are scoped to this account without sample leak
    outcomes_resp = client.get("/api/v1/outcomes")
    assert outcomes_resp.status_code == 200
    outcomes_data = outcomes_resp.json()
    assert len(outcomes_data["outcomes"]) == 0
    assert outcomes_data["summary"]["moves_count"] == 0
    assert outcomes_data["summary"]["net_roi_usd"] is None

    outcomes_text = str(outcomes_data)
    for term in FORBIDDEN_SAMPLE_TERMS:
        assert term.lower() not in outcomes_text.lower(), (
            f"Sample term '{term}' leaked into watercolor outcomes!"
        )


@pytest.fixture(scope="module")
def live_server_url() -> str:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()

    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    base_url = f"http://127.0.0.1:{port}"
    for _ in range(50):
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.1):
                break
        except OSError:
            time.sleep(0.05)
    yield base_url
    server.should_exit = True


def _find_playwright_python() -> str | None:
    for candidate in (sys.executable, "/usr/bin/python3", shutil.which("python3") or ""):
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


def test_non_sample_artist_seo_and_llms_txt(client: TestClient) -> None:
    """Public SEO, robots, and llms.txt must not claim Muse is restricted to one niche."""
    repo_root = Path(__file__).resolve().parents[1]
    llms_path = repo_root / "src" / "api" / "static" / "llms.txt"
    sitemap_path = repo_root / "src" / "api" / "static" / "sitemap.xml"
    robots_path = repo_root / "src" / "api" / "static" / "robots.txt"

    assert llms_path.is_file()
    assert sitemap_path.is_file()
    assert robots_path.is_file()

    llms_txt = llms_path.read_text(encoding="utf-8")
    for term in FORBIDDEN_SAMPLE_TERMS:
        assert term.lower() not in llms_txt.lower(), (
            f"Forbidden sample term '{term}' found in llms.txt!"
        )

    sitemap_xml = sitemap_path.read_text(encoding="utf-8")
    for term in FORBIDDEN_SAMPLE_TERMS:
        assert term.lower() not in sitemap_xml.lower(), (
            f"Forbidden sample term '{term}' found in sitemap.xml!"
        )

    # Header check on /account, /welcome, /progress
    for path in ("/account", "/welcome", "/progress"):
        resp = client.get(path)
        assert resp.status_code == 200
        assert "noindex" in resp.headers.get("x-robots-tag", "").lower()


def test_watercolor_artist_browser_isolation_and_account_switch(live_server_url: str) -> None:
    """E2E Playwright test: Elena Vance Watercolor Studio completes browser onboarding,
    verifies /today, /create, /progress, and /daily-brief are free of sample terms,
    then switches to a second account without cross-account leakage.
    """
    python_bin = _find_playwright_python()
    if not python_bin:
        pytest.skip("Playwright runtime not installed")

    runner_script = textwrap.dedent(
        f"""
        import json
        from playwright.sync_api import sync_playwright

        base = "{live_server_url}"
        forbidden = {FORBIDDEN_SAMPLE_TERMS!r}

        elena_user = {{
            "id": "u-elena-999",
            "email": "elena@wildmeadowstudio.com",
            "email_verified": True,
        }}
        oak_user = {{
            "id": "u-oak-888",
            "email": "oak@potterycraft.com",
            "email_verified": True,
        }}

        active_user = elena_user
        elena_workspace = {{
            "document": {{
                "onboarding": {{
                    "business_name": "Elena Vance Watercolor Studio",
                    "shop_urls": ["https://elenavanceart.com"],
                    "socials": [{{"platform": "instagram", "handle": "@elenavanceart"}}],
                    "competitors": [{{
                        "name": "Wild Meadow Studio",
                        "url": "https://www.wildmeadowstudio.com",
                        "reason": "Botanical and landscape watercolor prints",
                    }}],
                    "preferences": {{"medium": "Watercolor & Gouache"}},
                    "completed_at": "2026-11-10T12:00:00Z",
                    "used_run": False,
                }}
            }},
            "version": 1,
            "owner_id": "u-elena-999",
        }}
        oak_workspace = {{
            "document": {{
                "onboarding": {{
                    "business_name": "Oak & Pine Ceramics",
                    "shop_urls": ["https://oakandpine.shop"],
                    "socials": [{{"platform": "instagram", "handle": "@oakpine"}}],
                    "competitors": [{{
                        "name": "Cedar Stoneware",
                        "url": "https://cedarstoneware.test",
                        "reason": "Functional tableware",
                    }}],
                    "preferences": {{"medium": "Stoneware Ceramics"}},
                    "completed_at": "2026-11-10T12:00:00Z",
                    "used_run": False,
                }}
            }},
            "version": 1,
            "owner_id": "u-oak-888",
        }}

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(viewport={{"width": 1440, "height": 900}})
            page = context.new_page()

            def handle_route(route):
                global active_user
                url = route.request.url
                method = route.request.method

                if url.endswith("/api/v1/account/me"):
                    route.fulfill(
                        status=200,
                        content_type="application/json",
                        body=json.dumps({{
                            "configured": True,
                            "user": active_user,
                            "usage": {{
                                "plan": "starter",
                                "used": 0,
                                "limit": 3,
                                "remaining": 3,
                                "resets_at": None,
                            }},
                            "live_available": True,
                        }}),
                    )
                    return

                if "/api/v1/account/workspace" in url:
                    ws = elena_workspace if active_user["id"] == "u-elena-999" else oak_workspace
                    if method in ("GET", "PUT"):
                        route.fulfill(
                            status=200, content_type="application/json", body=json.dumps(ws)
                        )
                        return

                if url.endswith("/api/v1/onboarding/status"):
                    route.fulfill(
                        status=200,
                        content_type="application/json",
                        body=json.dumps({{
                            "completed": True,
                            "completed_at": "2026-11-10T12:00:00Z",
                            "used_run": False,
                            "plan": "starter",
                            "runs_remaining": 3,
                        }}),
                    )
                    return

                if "/api/v1/daily-brief" in url:
                    ws = elena_workspace if active_user["id"] == "u-elena-999" else oak_workspace
                    shop_name = ws["document"]["onboarding"]["business_name"]
                    is_elena = active_user["id"] == "u-elena-999"
                    comp_name = "Wild Meadow Studio" if is_elena else "Cedar Stoneware"
                    route.fulfill(
                        status=200,
                        content_type="application/json",
                        body=json.dumps({{
                            "date": "2026-11-10",
                            "generated_at": "2026-11-10T12:00:00Z",
                            "source": f"Built 2026-11-10 for {{shop_name}}. 0 runs spent.",
                            "items": [{{
                                "name": comp_name,
                                "url": "https://www.wildmeadowstudio.com",
                                "where": "Website",
                                "snapshot_age": "monitored",
                                "fresh": False,
                                "summary": "Watched competitor shop",
                            }}],
                            "move": {{
                                "title": f"Feature a collection from {{shop_name}}",
                                "reason": (
                                    "Highlight your unique pieces and compare catalog gaps "
                                    "with your competitors."
                                ),
                                "href": "/create",
                                "impact": "high",
                                "source": f"Workspace for {{shop_name}}",
                            }},
                            "fresh_analyses": 0,
                            "focus": {{
                                "title": f"Feature a collection from {{shop_name}}",
                                "reason": (
                                    "Highlight your unique pieces and compare catalog gaps "
                                    "with your competitors."
                                ),
                                "href": "/create",
                                "impact": "high",
                                "source": f"Workspace for {{shop_name}}",
                            }},
                            "action_items": [],
                            "overnight_changes": [],
                            "overnight_note": f"Watching competitors for {{shop_name}}.",
                            "trends": [],
                            "trends_source": f"Account workspace for {{shop_name}}",
                            "inputs": f"account:{{shop_name}}",
                        }}),
                    )
                    return

                if url.endswith("/api/v1/outcomes"):
                    route.fulfill(
                        status=200,
                        content_type="application/json",
                        body=json.dumps({{
                            "outcomes": [],
                            "summary": {{
                                "moves_count": 0,
                                "total_revenue_usd": 0.0,
                                "total_time_minutes": 0,
                                "plan_cost_usd": 0.0,
                                "net_roi_usd": None,
                            }}
                        }}),
                    )
                    return

                route.continue_()

            page.route("**/api/v1/**", handle_route)

            # 1. Visit /welcome with Elena Vance session
            page.goto(f"{{base}}/welcome", wait_until="networkidle")
            page.locator("#wkMain").wait_for(state="attached", timeout=5000)
            welcome_text = page.locator("body").inner_text()
            for term in forbidden:
                assert term.lower() not in welcome_text.lower(), (
                    f"Forbidden term {{term}} found on /welcome"
                )

            # 2. Visit /today
            page.goto(f"{{base}}/today", wait_until="networkidle")
            page.locator("#postHook").wait_for(state="attached", timeout=5000)
            today_text = page.locator("body").inner_text()
            for term in forbidden:
                assert term.lower() not in today_text.lower(), (
                    f"Forbidden term {{term}} found on /today"
                )

            # 3. Visit /create
            page.goto(f"{{base}}/create", wait_until="networkidle")
            page.locator("#headline").wait_for(state="attached", timeout=5000)
            create_text = page.locator("body").inner_text()
            for term in forbidden:
                assert term.lower() not in create_text.lower(), (
                    f"Forbidden term {{term}} found on /create"
                )

            # 4. Visit /progress
            page.goto(f"{{base}}/progress", wait_until="networkidle")
            page.locator("#pgFormTitle").wait_for(state="attached", timeout=5000)
            progress_text = page.locator("body").inner_text()
            for term in forbidden:
                assert term.lower() not in progress_text.lower(), (
                    f"Forbidden term {{term}} found on /progress"
                )

            # 5. Switch to Account B (Oak & Pine Ceramics) in the same browser
            active_user = oak_user
            page.goto(f"{{base}}/today", wait_until="networkidle")
            page.locator("#postHook").wait_for(state="attached", timeout=5000)
            today_oak_text = page.locator("body").inner_text()
            assert "Elena Vance" not in today_oak_text, (
                "Elena Vance leaked into Oak & Pine session!"
            )
            for term in forbidden:
                assert term.lower() not in today_oak_text.lower(), (
                    f"Forbidden term {{term}} on /today for Account B"
                )

            browser.close()
        """
    )

    proc = subprocess.run(
        [python_bin, "-c", runner_script],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert proc.returncode == 0, (
        f"Playwright script failed:\nSTDOUT: {proc.stdout}\nSTDERR: {proc.stderr}"
    )
