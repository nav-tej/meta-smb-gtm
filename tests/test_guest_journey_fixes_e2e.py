"""Offline real Chromium E2E tests for Hermes guest-journey report fixes."""

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

import pytest
import uvicorn

from src.api.main import app


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
def guest_creator_server(monkeypatch: pytest.MonkeyPatch):
    """Run real FastAPI app in DEMO_MODE=true for guest /create E2E checks."""
    monkeypatch.setenv("DEMO_MODE", "true")
    monkeypatch.setenv("META_MODEL_API_KEY", "")
    monkeypatch.setenv("DEMO_KEY", "")

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


def test_guest_journey_report_fixes_e2e(guest_creator_server: str, tmp_path: Path) -> None:
    """Verify pre-filled productName, cleared export notice on shop switch, and 375px triage."""
    pw_python = _find_playwright_python()
    if pw_python is None:
        pytest.skip("Playwright Python runtime unavailable")

    script = textwrap.dedent(
        f"""
        import json
        from pathlib import Path
        from PIL import Image
        from playwright.sync_api import sync_playwright

        BASE = {guest_creator_server!r}
        OUT = Path({str(tmp_path)!r})

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            ctx = browser.new_context(
                viewport={{"width": 375, "height": 812}}, accept_downloads=True
            )
            page = ctx.new_page()
            page.goto(f"{{BASE}}/create", wait_until="domcontentloaded")
            page.wait_for_function(
                "() => (document.querySelector('#productName') || {{}}).value.length > 0"
            )

            # 1. Product name pre-filled for example shop & has placeholder
            assert "Ek Onkar" in page.locator("#productName").input_value()
            assert page.locator("#productName").get_attribute("placeholder")

            # Advance to Step 4 & export PNG
            page.locator("#nextButton").click()
            page.locator("#nextButton").click()
            page.locator("#reviewed").check()
            page.locator("#nextButton").click()
            page.wait_for_selector("#downloadFeed:visible")

            # 2. No horizontal overflow and no triage button truncation at 375px
            assert not page.evaluate("document.documentElement.scrollWidth > window.innerWidth")
            triage_metrics = page.evaluate(
                \"\"\"() => [...document.querySelectorAll('.ms-triage button')].map(b => ({{
                    text: b.textContent.trim(),
                    sw: b.scrollWidth,
                    cw: b.clientWidth,
                    h: b.getBoundingClientRect().height
                }}))\"\"\"
            )
            assert len(triage_metrics) >= 4
            for m in triage_metrics:
                assert m["sw"] <= m["cw"], f"Truncated triage button: {{m}}"
                assert m["h"] >= 44, f"Small touch target: {{m}}"

            with page.expect_download() as dl_feed:
                page.locator("#downloadFeed").click()
            feed_png = OUT / "feed.png"
            dl_feed.value.save_as(str(feed_png))
            with Image.open(feed_png) as im:
                assert im.size == (1080, 1350), im.size

            assert page.locator("#exportDoneOffer").is_visible()
            assert "Post exported" in (page.locator("#notice").text_content() or "")

            # 3. Switching shop or starting custom shop clears stale "Post exported" notice
            page.locator('[data-step="0"]').click()
            page.locator("#customProduct").click()
            assert page.locator("#notice").is_hidden()
            assert page.locator("#exportDoneOffer").is_hidden()

            page.locator("#artistExample").click()
            assert page.locator("#notice").is_hidden()
            assert "Ek Onkar" in page.locator("#productName").input_value()

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
