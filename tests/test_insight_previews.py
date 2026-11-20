"""Track B: Insight-to-Ad Previews and 1:1 demo creative specs.

Tests:
1. PreviewSpec and PreviewEvidence contract validation against data/demo/previews.json.
2. GET /api/v1/previews endpoint serving 1:1 demo previews.
3. Playwright browser tests at 375px and 1440px verifying preview thumbnails on every
   ranked idea, opening the preview dialog, placement switching (4:5, 9:16, FB),
   side-by-side competitor compare view, copy-ready checklist for non-post moves,
   and zero model calls.
"""

from __future__ import annotations

import json
import shutil
import socket
import subprocess
import sys
import textwrap
import threading
from collections.abc import Iterator
from pathlib import Path

import pytest
import uvicorn
from fastapi.testclient import TestClient

from src.api.main import app
from src.models.creative import PreviewEvidence, PreviewSpec

REPO_ROOT = Path(__file__).resolve().parent.parent
PREVIEWS_FILE = REPO_ROOT / "data" / "demo" / "previews.json"


@pytest.fixture(scope="module")
def live_server_url() -> Iterator[str]:
    """Spin up a real uvicorn server in-process on an ephemeral localhost port."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()

    config = uvicorn.Config(app=app, host="127.0.0.1", port=port, log_level="warning")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    base_url = f"http://127.0.0.1:{port}"
    import time

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


def test_preview_models_and_fixture_integrity() -> None:
    """Verify PreviewSpec contract and data/demo/previews.json schema compliance."""
    assert PREVIEWS_FILE.is_file(), "data/demo/previews.json must exist"
    data = json.loads(PREVIEWS_FILE.read_text(encoding="utf-8"))
    assert "previews" in data
    previews = data["previews"]
    assert len(previews) == 5, f"Expected 5 preview specs, found {len(previews)}"

    for entry in previews:
        spec = PreviewSpec.model_validate(entry)
        assert spec.insight_id
        assert spec.headline
        assert spec.caption
        assert spec.image_ref
        assert spec.why_this
        assert len(spec.evidence) >= 1
        for ev in spec.evidence:
            assert isinstance(ev, PreviewEvidence)
            assert ev.label

    # Specific assertions for the 5 ideas
    women_spec = next(p for p in previews if p["insight_id"] == "idea-1-empowering-women")
    assert "Empowering Women" in women_spec["headline"] or "Sikh Women" in women_spec["headline"]
    assert women_spec["competitor_card"]["name"] == "SikhiArt"

    starter_spec = next(p for p in previews if p["insight_id"] == "idea-2-starter-prints")
    assert "$14" in starter_spec["headline"]
    assert "$59.99" in starter_spec["why_this"] or "$60" in starter_spec["why_this"]

    gift_spec = next(p for p in previews if p["insight_id"] == "idea-3-gift-ready")
    assert "Gift" in gift_spec["headline"] or "gift" in gift_spec["caption"]

    home_spec = next(p for p in previews if p["insight_id"] == "idea-4-home-titles")
    assert len(home_spec["checklist"]) == 3
    assert any("for Your Home" in step for step in home_spec["checklist"])

    story_spec = next(p for p in previews if p["insight_id"] == "idea-5-painting-story")
    assert "Ek Onkar" in story_spec["headline"] or "Ek Onkar" in story_spec["caption"]


def test_previews_api_endpoint() -> None:
    """Verify GET /api/v1/previews returns the 1:1 preview specs."""
    client = TestClient(app)
    resp = client.get("/api/v1/previews")
    assert resp.status_code == 200
    data = resp.json()
    assert "previews" in data
    assert len(data["previews"]) == 5
    ids = [p["insight_id"] for p in data["previews"]]
    assert "idea-1-empowering-women" in ids
    assert "idea-4-home-titles" in ids


@pytest.mark.parametrize("viewport_width", [375, 1440])
def test_insight_previews_browser_ui(live_server_url: str, viewport_width: int) -> None:
    """Playwright E2E test verifying 1:1 preview thumbnails and interactive modal."""
    pw_python = _find_playwright_python()
    if pw_python is None:
        pytest.skip("Playwright Python runtime unavailable")

    runner_code = textwrap.dedent(
        f"""
        import json
        from playwright.sync_api import sync_playwright

        live_server_url = {live_server_url!r}
        viewport_width = {viewport_width}
        model_api_called = False

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(viewport={{"width": viewport_width, "height": 900}})
            page = context.new_page()

            def handle_model(route):
                global model_api_called
                model_api_called = True
                route.abort()

            page.route("*api.meta.ai*", handle_model)
            page.route("*llama.com*", handle_model)

            # 1. Navigate to home page with #loop-improve hash
            page.goto(f"{{live_server_url}}/#loop-improve", wait_until="domcontentloaded")
            page.wait_for_selector("#loop-improve .jr-recos li")

            # 2. Verify all 5 ranked moves have a preview thumbnail button
            thumbs = page.query_selector_all("#loop-improve .jr-recos li .jr-reco-thumb")
            assert len(thumbs) == 5, f"Expected 5 preview thumbnails, found {{len(thumbs)}}"

            # Check horizontal overflow
            overflow = page.evaluate(
                "document.documentElement.scrollWidth > document.documentElement.clientWidth"
            )
            assert overflow is False, f"Horizontal overflow detected at {{viewport_width}}px"

            # 3. Click first idea thumbnail (Empowering Women) and verify modal contents
            page.click("#loop-improve .jr-recos li:nth-child(1) .jr-reco-thumb")
            page.wait_for_selector("#jrPreviewModal[open]")

            headline_text = page.text_content("#jrPostHeadline") or ""
            assert "Sikh Women" in headline_text or "Strength" in headline_text

            caption_text = page.text_content("#jrPostCaption") or ""
            assert "Empowering Women" in caption_text

            why_text = page.text_content("#jrWhyBadge") or ""
            assert "SikhiArt" in why_text

            handle_text = page.text_content("#jrPostHandle") or ""
            assert "@" in handle_text

            # 4. Test Placement Switching
            media_box = page.locator("#jrMediaBox")

            # Switch to Story (9:16)
            page.click('button[data-placement="instagram_story"]')
            page.wait_for_selector("#jrMediaBox.jr-aspect-9-16")

            # Switch to Facebook feed (1.91:1)
            page.click('button[data-placement="facebook_feed"]')
            page.wait_for_selector("#jrMediaBox.jr-aspect-fb")

            # Switch back to Instagram feed (4:5)
            page.click('button[data-placement="instagram_feed"]')
            page.wait_for_selector("#jrMediaBox.jr-aspect-4-5")

            # 5. Test Competitor Compare View Toggle
            page.click("#jrCompareBtn")
            page.wait_for_selector("#jrCompFrame:not([hidden])")
            comp_text = page.text_content("#jrCompFrame") or ""
            assert "SikhiArt" in comp_text
            assert "$59.99" in comp_text

            # Toggle off compare
            page.click("#jrCompareBtn")
            page.wait_for_selector("#jrCompFrame[hidden]")

            # 6. Test Non-Post Idea (Item 4: Add 'for your home' to three titles)
            # Close dialog first
            page.click(".jr-close-btn")
            page.wait_for_selector("#jrPreviewModal", state="hidden")

            # Click 4th idea thumbnail
            page.click("#loop-improve .jr-recos li:nth-child(4) .jr-reco-thumb")
            page.wait_for_selector("#jrPreviewModal[open]")

            # Verify checklist card is visible for this non-post move
            page.wait_for_selector("#jrChecklistCard:not([hidden])")
            checklist_text = page.text_content("#jrChecklistItems") or ""
            assert "for Your Home" in checklist_text
            assert "Ek Onkar" in checklist_text

            assert model_api_called is False
            browser.close()
            print("INSIGHT PREVIEWS BROWSER TEST PASSED")
        """
    )
    res = subprocess.run(
        [pw_python, "-c", runner_code],
        capture_output=True,
        text=True,
        timeout=35,
        check=False,
    )
    assert res.returncode == 0, f"STDOUT:\n{res.stdout}\nSTDERR:\n{res.stderr}"
