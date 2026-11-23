"""Offline Chromium E2E tests for pasted YouTube video links in 'What Muse remembers'."""

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
from src.services import youtube_videos as yv
from src.services.accounts import AccountSession
from tests.e2e_helpers import with_cpu_throttle

VID_1 = "VidOne00001"
VID_2 = "VidTwo00002"


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
def youtube_links_server(monkeypatch: pytest.MonkeyPatch):
    """Run real FastAPI app with a signed-in fixture account and faked oEmbed lookup."""
    user = AccountSession(
        user_id="yt-links-u1",
        email="founder@northstar.test",
        email_verified=True,
        access_token="tok-yt-links",
        session_id=None,
    )
    workspace_state: dict[str, Any] = {
        "version": 1,
        "doc": {
            "onboarding": {
                "business_name": "Northstar Advisory",
                "business_type": "services",
                "website_url": "https://northstar.test",
                "completed_at": "2026-11-20T10:00:00Z",
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
        if request.cookies.get("muse_e2e_user") == "yt-links-u1":
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

    async def fake_fetch_video_info(video_id: str) -> dict[str, str]:
        catalog = {
            VID_1: (
                "Q4 B2B Pipeline Audit <img src=x onerror=window.__xss=1>",
                "Northstar Advisory",
            ),
            VID_2: ("Pricing Advisory Retainers", "Northstar Advisory"),
        }
        title, author = catalog.get(video_id, (f"Video {video_id}", "Northstar Advisory"))
        url, thumb = yv.build_video_urls(video_id)
        return {
            "video_id": video_id,
            "title": title,
            "author_name": author,
            "url": url,
            "thumbnail_url": thumb,
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
    monkeypatch.setattr(memory_api, "fetch_video_info", fake_fetch_video_info)

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


def test_youtube_pasted_links_memory_modal_375_and_1440_own_and_sample_e2e(
    youtube_links_server: str,
) -> None:
    """Verify pasted YouTube links UI at 375px and 1440px (own vs sample)."""
    pw_python = _find_playwright_python()
    if pw_python is None:
        pytest.skip("Playwright Python runtime unavailable")

    script = with_cpu_throttle(
        f"""
        from playwright.sync_api import sync_playwright

        BASE = {youtube_links_server!r}
        VID_1 = {VID_1!r}
        VID_2 = {VID_2!r}

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            try:
                for width in (375, 1440):
                    # 1. Own workspace: paste links, save, verify rebuilt watch URLs, remove
                    ctx = browser.new_context(viewport={{"width": width, "height": 844}})
                    ctx.add_cookies([{{
                        "name": "muse_e2e_user",
                        "value": "yt-links-u1",
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
                    page.wait_for_selector("#smYouTubeLinksInput")

                    block_text = page.locator("#smYouTubeSourceBlock").inner_text()
                    assert "Your YouTube videos" in block_text, block_text
                    assert "Muse reads the title of each video you paste." in block_text, block_text
                    assert "automatically" not in block_text.lower(), block_text
                    assert "watches" not in block_text.lower(), block_text

                    page.fill(
                        "#smYouTubeLinksInput",
                        f"https://www.youtube.com/watch?v={{VID_1}}\\nhttps://youtu.be/{{VID_2}}",
                    )
                    page.click("#smYouTubeSaveBtn")
                    page.wait_for_selector("#smYouTubeVideoList li")

                    links = page.locator("#smYouTubeVideoList a")
                    assert links.count() == 2, f"expected 2 videos, got {{links.count()}}"
                    hrefs = [links.nth(i).get_attribute("href") for i in range(2)]
                    assert hrefs == [
                        f"https://www.youtube.com/watch?v={{VID_1}}",
                        f"https://www.youtube.com/watch?v={{VID_2}}",
                    ], hrefs
                    for i in range(2):
                        assert links.nth(i).get_attribute("target") == "_blank"
                        assert links.nth(i).get_attribute("rel") == "noopener noreferrer"

                    assert page.evaluate("() => window.__xss === undefined")
                    assert "<img src=x" in links.nth(0).inner_text()

                    overflow = page.evaluate(
                        "() => document.documentElement.scrollWidth > window.innerWidth"
                    )
                    assert not overflow, f"horizontal overflow at {{width}}px"
                    body_lower = page.evaluate("() => document.body.innerText.toLowerCase()")
                    assert "sarabjit" not in body_lower
                    assert "ek onkar" not in body_lower

                    page.click("#smYouTubeRemoveBtn")
                    page.wait_for_function(
                        "() => document.getElementById('smYouTubeVideoList') === null"
                    )
                    assert page.locator("#smYouTubeRemoveBtn").count() == 0
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
