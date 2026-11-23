"""Offline Chromium E2E tests for own-workspace YouTube videos in 'What Muse remembers'."""

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
from src.api import seller_memory as memory_api
from src.api.main import app
from src.services.accounts import AccountSession
from tests.e2e_helpers import with_cpu_throttle

VALID_CHANNEL_ID = "UC1234567890abcdefABCD12"
VALID_FEED_URL = f"https://www.youtube.com/feeds/videos.xml?channel_id={VALID_CHANNEL_ID}"


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
def own_sources_server(monkeypatch: pytest.MonkeyPatch):
    """Run real FastAPI app with a signed-in fixture user who has a YouTube social."""
    user = AccountSession(
        user_id="yt-e2e-u1",
        email="founder@northstar.test",
        email_verified=True,
        access_token="tok-yt-e2e",
        session_id=None,
    )
    workspace_state: dict[str, Any] = {
        "version": 1,
        "fetch_calls": 0,
        "doc": {
            "onboarding": {
                "business_name": "Northstar Advisory",
                "business_type": "services",
                "website_url": "https://northstar.test",
                "completed_at": "2026-11-20T10:00:00Z",
                "socials": [{"platform": "youtube", "handle": "@northstaradvisory"}],
                "competitors": [{"name": "Summit Consulting", "url": "https://summit.test"}],
            },
            "preferences": {
                "goal": "Book 5 advisory calls this month",
                "access": {"minutes_per_week": 60, "channels": ["youtube", "linkedin"]},
            },
            "voice_profile": {},
            "outcomes": [],
        },
    }

    async def fake_resolve(request: Any, _response: Any = None, require_verified: bool = False):
        if request.cookies.get("muse_e2e_user") == "yt-e2e-u1":
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
        return {
            "document": deepcopy(workspace_state["doc"]),
            "version": workspace_state["version"],
            "owner_id": account.user_id,
        }

    async def fake_save(
        account: AccountSession,
        doc: dict[str, Any],
        *,
        expected_version: int | None = None,
        expected_owner: str | None = None,
    ) -> dict[str, Any]:
        if expected_version is not None and expected_version != workspace_state["version"]:
            raise HTTPException(409, "Version conflict")
        workspace_state["doc"] = deepcopy(doc)
        workspace_state["version"] += 1
        return {
            "document": deepcopy(workspace_state["doc"]),
            "version": workspace_state["version"],
            "owner_id": account.user_id,
        }

    async def fake_fetch_youtube(channel_url: str) -> dict[str, Any]:
        workspace_state["fetch_calls"] += 1
        call_num = workspace_state["fetch_calls"]
        # Odd calls: initial load (4 videos, UI shows 3 newest); even calls: refreshed video list
        if call_num % 2 == 1:
            videos = [
                {
                    "video_id": "VidOne00001",
                    "title": "Q4 B2B Pipeline Audit <img src=x onerror=window.__xss=1>",
                    "published": "2026-11-22",
                    "description": "Quarterly review walkthrough.",
                    "url": "https://www.youtube.com/watch?v=VidOne00001",
                    "thumbnail_url": "https://i.ytimg.com/vi/VidOne00001/hqdefault.jpg",
                },
                {
                    "video_id": "VidTwo00002",
                    "title": "Pricing Advisory Retainers",
                    "published": "2026-11-18",
                    "description": "Retainer structure guide.",
                    "url": "https://www.youtube.com/watch?v=VidTwo00002",
                    "thumbnail_url": "https://i.ytimg.com/vi/VidTwo00002/hqdefault.jpg",
                },
                {
                    "video_id": "VidThr00003",
                    "title": "Discovery Call Checklist",
                    "published": "2026-11-12",
                    "description": "Questions for first calls.",
                    "url": "https://www.youtube.com/watch?v=VidThr00003",
                    "thumbnail_url": "https://i.ytimg.com/vi/VidThr00003/hqdefault.jpg",
                },
                {
                    "video_id": "VidFou00004",
                    "title": "Older Fourth Video Hidden",
                    "published": "2026-11-01",
                    "description": "Should not appear in top 3.",
                    "url": "https://www.youtube.com/watch?v=VidFou00004",
                    "thumbnail_url": "https://i.ytimg.com/vi/VidFou00004/hqdefault.jpg",
                },
            ]
        else:
            videos = [
                {
                    "video_id": "VidRef00005",
                    "title": "Refreshed Video Alpha",
                    "published": "2026-11-23",
                    "description": "Brand new upload.",
                    "url": "https://www.youtube.com/watch?v=VidRef00005",
                    "thumbnail_url": "https://i.ytimg.com/vi/VidRef00005/hqdefault.jpg",
                },
                {
                    "video_id": "VidOne00001",
                    "title": "Q4 B2B Pipeline Audit",
                    "published": "2026-11-22",
                    "description": "Quarterly review walkthrough.",
                    "url": "https://www.youtube.com/watch?v=VidOne00001",
                    "thumbnail_url": "https://i.ytimg.com/vi/VidOne00001/hqdefault.jpg",
                },
                {
                    "video_id": "VidTwo00002",
                    "title": "Pricing Advisory Retainers",
                    "published": "2026-11-18",
                    "description": "Retainer structure guide.",
                    "url": "https://www.youtube.com/watch?v=VidTwo00002",
                    "thumbnail_url": "https://i.ytimg.com/vi/VidTwo00002/hqdefault.jpg",
                },
            ]
        return {
            "channel_url": channel_url,
            "feed_url": VALID_FEED_URL,
            "fetched_at": "2026-11-23T12:00:00+00:00",
            "videos": videos,
        }

    monkeypatch.setenv("DEMO_MODE", "true")
    monkeypatch.setenv("ACCOUNTS_REQUIRED", "true")
    monkeypatch.setenv("META_MODEL_API_KEY", "")
    monkeypatch.setenv("DEMO_KEY", "")
    monkeypatch.setattr(accounts_api, "resolve_account", fake_resolve)
    monkeypatch.setattr("src.services.accounts.resolve_account", fake_resolve)
    monkeypatch.setattr(accounts_api, "snapshot", fake_snapshot)
    monkeypatch.setattr(accounts_api, "load_workspace", fake_load)
    monkeypatch.setattr(memory_api, "resolve_account", fake_resolve)
    monkeypatch.setattr(memory_api, "load_workspace", fake_load)
    monkeypatch.setattr(memory_api, "save_workspace", fake_save)
    monkeypatch.setattr(memory_api, "fetch_youtube_channel_videos", fake_fetch_youtube)

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


def test_youtube_videos_memory_modal_375_and_1440_own_and_sample_e2e(
    own_sources_server: str,
) -> None:
    """Verify YouTube videos in 'What Muse remembers' at 375px and 1440px (own vs sample)."""
    pw_python = _find_playwright_python()
    if pw_python is None:
        pytest.skip("Playwright Python runtime unavailable")

    script = with_cpu_throttle(
        f"""
        from playwright.sync_api import sync_playwright

        BASE = {own_sources_server!r}

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            try:
                for width in (375, 1440):
                    # 1. Own workspace: signed-in user with YouTube social in setup
                    ctx = browser.new_context(viewport={{"width": width, "height": 844}})
                    ctx.add_cookies([{{
                        "name": "muse_e2e_user",
                        "value": "yt-e2e-u1",
                        "url": BASE,
                    }}])
                    page = ctx.new_page()
                    page.goto(f"{{BASE}}/", wait_until="domcontentloaded")
                    page.wait_for_function(
                        "() => document.body.classList.contains('ms-staged') && "
                        "document.documentElement.getAttribute('data-muse-mode') === 'account_own'"
                    )
                    page.wait_for_selector("#smOpenMemoryBtn")
                    page.click("#smOpenMemoryBtn")
                    page.wait_for_selector("#smMemoryModalBackdrop:not([hidden])")
                    page.wait_for_selector("#smYouTubeReadSocialBtn")

                    # Click "Read my recent videos (free)" -> 3 videos appear
                    page.click("#smYouTubeReadSocialBtn")
                    page.wait_for_selector("#smYouTubeVideoList li")
                    items = page.locator("#smYouTubeVideoList li")
                    assert items.count() == 3, f"expected 3 videos, got {{items.count()}}"

                    links = page.locator("#smYouTubeVideoList a")
                    assert links.count() == 3
                    hrefs = [links.nth(i).get_attribute("href") for i in range(3)]
                    assert hrefs == [
                        "https://www.youtube.com/watch?v=VidOne00001",
                        "https://www.youtube.com/watch?v=VidTwo00002",
                        "https://www.youtube.com/watch?v=VidThr00003",
                    ], hrefs
                    for i in range(3):
                        assert links.nth(i).get_attribute("target") == "_blank"
                        assert links.nth(i).get_attribute("rel") == "noopener noreferrer"

                    # Hostile markup in title rendered as text, zero XSS
                    assert page.evaluate("() => window.__xss === undefined")
                    assert "<img src=x" in links.nth(0).inner_text()

                    # No horizontal overflow and no sample terms in own workspace
                    overflow = page.evaluate(
                        "() => document.documentElement.scrollWidth > window.innerWidth"
                    )
                    assert not overflow, f"horizontal overflow at {{width}}px"
                    body_lower = page.evaluate("() => document.body.innerText.toLowerCase()")
                    assert "sarabjit" not in body_lower, "sample term leaked"
                    assert "ek onkar" not in body_lower, "sample term leaked"

                    # Click Refresh (free) -> updated video list renders
                    page.click("#smYouTubeRefreshBtn")
                    page.wait_for_function(
                        "() => (document.getElementById('smYouTubeVideoList')?.innerText || '')"
                        ".includes('Refreshed Video Alpha')"
                    )
                    assert page.locator("#smYouTubeVideoList li").count() == 3

                    # Click Remove -> returns to Read my recent videos (free)
                    page.click("#smYouTubeRemoveBtn")
                    page.wait_for_selector("#smYouTubeReadSocialBtn")
                    assert page.locator("#smYouTubeVideoList").count() == 0
                    ctx.close()

                    # 2. Sample workspace never shows the YouTube block
                    ctx_s = browser.new_context(viewport={{"width": width, "height": 844}})
                    ps = ctx_s.new_page()
                    ps.goto(f"{{BASE}}/?workspace=sample", wait_until="domcontentloaded")
                    ps.wait_for_function(
                        "() => document.body.classList.contains('ms-staged') && "
                        "window.museModes?.isSampleMode?.() === true"
                    )
                    ps.wait_for_selector("#smOpenMemoryBtn")
                    ps.click("#smOpenMemoryBtn")
                    ps.wait_for_selector("#smMemoryModalBackdrop:not([hidden])")
                    assert ps.locator("#smYouTubeSourceBlock").count() == 0
                    ctx_s.close()
            finally:
                browser.close()
        """
    )
    proc = subprocess.run([pw_python, "-c", script], capture_output=True, text=True, check=False)
    assert proc.returncode == 0, f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
