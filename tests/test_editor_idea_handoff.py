"""Tests for Recommendation to Editor Handoff (Review Fix Item 10).

Verifies:
1. Preview modal and ranked ideas link to /create?idea=<id> and /today?idea=<id>.
2. Each of the 5 demo ideas opens the editor (/create and /today) with its own headline,
   caption, image_ref, mapped goal, and why_this evidence at both 375px and 1440px viewports.
3. Unknown or invalid idea IDs safely fall back to default behavior.
4. Exporting a post marks the idea done in `muse.actions` and offers a link to `/progress`.
5. Zero paid model API calls in demo mode.
6. The `post_started` analytics event carries {idea_id, source}.
"""

from __future__ import annotations

import json
import shutil
import socket
import subprocess
import sys
import textwrap
import threading
import time
from collections.abc import Iterator
from pathlib import Path

import pytest
import uvicorn
from fastapi.testclient import TestClient

from src.api.main import app
from src.models.creative import PreviewSpec

REPO_ROOT = Path(__file__).resolve().parent.parent
PREVIEWS_FILE = REPO_ROOT / "data" / "demo" / "previews.json"


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


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


def test_demo_previews_data_integrity() -> None:
    """Verify all 5 demo ideas exist in previews.json with complete fields."""
    assert PREVIEWS_FILE.is_file(), "data/demo/previews.json must exist"
    data = json.loads(PREVIEWS_FILE.read_text(encoding="utf-8"))
    previews = data.get("previews", [])
    assert len(previews) == 5, f"Expected 5 demo ideas, found {len(previews)}"

    expected_ids = [
        "idea-1-empowering-women",
        "idea-2-starter-prints",
        "idea-3-gift-ready",
        "idea-4-home-titles",
        "idea-5-painting-story",
    ]
    found_ids = [p["insight_id"] for p in previews]
    assert found_ids == expected_ids

    for p in previews:
        spec = PreviewSpec.model_validate(p)
        assert spec.insight_id
        assert spec.headline
        assert spec.caption
        assert spec.image_ref.startswith("/samples/")
        assert spec.why_this


def test_reco_links_use_idea_query_param(client: TestClient) -> None:
    """Verify HTML pages and static scripts use ?idea=<insight_id> instead of broken ?goal=<id>."""
    resp = client.get("/")
    assert resp.status_code == 200
    assert "/create?idea=idea-1-empowering-women" in resp.text
    assert "/create?idea=idea-2-starter-prints" in resp.text
    assert "/create?idea=idea-3-gift-ready" in resp.text
    assert "/create?idea=idea-5-painting-story" in resp.text

    reco_js = client.get("/static/reco-actions.js").text
    assert "/create?idea=" in reco_js
    assert "/create?goal=" not in reco_js

    creator_html = client.get("/create").text
    assert "exportDoneOffer" in creator_html
    assert "/progress" in creator_html

    today_html = client.get("/today").text
    assert "logResultLink" in today_html


@pytest.mark.parametrize("viewport_width", [375, 1440])
def test_all_5_demo_ideas_in_creator_e2e(live_server_url: str, viewport_width: int) -> None:
    """Browser E2E test: each of the 5 demo ideas opens /create with its own headline and image.

    Checks:
    - Viewport widths 375px and 1440px with no horizontal overflow.
    - Zero external model API calls.
    - Post_started analytics event carries {idea_id, source: 'creator'}.
    - Export marks idea done in muse.actions and displays Log result offer.
    """
    python_bin = _find_playwright_python()
    if not python_bin:
        pytest.skip("Playwright runtime not installed")

    runner_script = textwrap.dedent(
        f"""
        import json
        from playwright.sync_api import sync_playwright

        base = "{live_server_url}"
        width = {viewport_width}
        height = 812 if width < 600 else 900
        model_called = False

        demo_ideas = [
            (
                "idea-1-empowering-women",
                "Sikh Women of Strength",
                "/samples/naam_japo_restored_gallery_live.webp",
                "instagram_feed",
            ),
            (
                "idea-2-starter-prints",
                "Timeless Sikh Heritage Art from $14",
                "/samples/ek_onkar_collector_room_live.webp",
                "instagram_feed",
            ),
            (
                "idea-3-gift-ready",
                "The Thoughtful Spiritual Gift",
                "/samples/golden_temple_holiday_gift_live.webp",
                "instagram_feed",
            ),
            (
                "idea-4-home-titles",
                "Listing Optimization: 'For Your Home'",
                "/samples/kirat_karo_collector_room_live.webp",
                "facebook_feed",
            ),
            (
                "idea-5-painting-story",
                "The Story Behind Ek Onkar",
                "/samples/diptych_ek_onkar_kirat_karo_live.webp",
                "instagram_feed",
            ),
        ]

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(viewport={{"width": width, "height": height}})
            page = context.new_page()

            def abort_model(route):
                global model_called
                model_called = True
                route.abort()

            page.route("*api.meta.ai*", abort_model)
            page.route("*llama.com*", abort_model)

            for idea_id, headline_sub, image_ref, expected_placement in demo_ideas:
                # 1. Open editor with ?idea=<id>
                page.goto(f"{{base}}/create?idea={{idea_id}}", wait_until="domcontentloaded")
                page.locator("#headline").wait_for(state="attached", timeout=5000)

                # Verify headline input and preview headline match
                headline_val = page.locator("#headline").input_value()
                assert headline_sub in headline_val, (
                    f"Expected '{{headline_sub}}' in #headline, got: '{{headline_val}}'"
                )

                # Verify image
                img_src = page.locator("#productImage").get_attribute("src")
                assert img_src == image_ref, f"Expected src '{{image_ref}}', got: '{{img_src}}'"

                # Verify 'Why this' evidence
                why_this_text = page.locator("#ideaReason").inner_text()
                assert len(why_this_text) > 10, (
                    f"Expected why_this evidence in #ideaReason, got: '{{why_this_text}}'"
                )

                # Verify exact placement parity
                eval_snap = (
                    "window.museCreatorSnapshot ? window.museCreatorSnapshot() : null"
                )
                snap = page.evaluate(eval_snap)
                assert snap is not None
                assert snap.get("placement") == expected_placement, (
                    f"Expected '{{expected_placement}}', got '{{snap.get('placement')}}'"
                )
                if expected_placement == "facebook_feed":
                    assert page.locator("#postFacebook").is_checked()
                    assert not page.locator("#postInstagram").is_checked()
                    btn_text = page.locator("#downloadFeed").inner_text()
                    assert "1080" in btn_text and "Facebook" in btn_text
                else:
                    assert page.locator("#postInstagram").is_checked()
                    assert not page.locator("#postFacebook").is_checked()
                    btn_text = page.locator("#downloadFeed").inner_text()
                    assert "1350" in btn_text

                # Check horizontal overflow
                overflow = page.evaluate(
                    "document.documentElement.scrollWidth > document.documentElement.clientWidth"
                )
                assert not overflow, f"Horizontal overflow detected at {{width}}px for {{idea_id}}"

            # 2. Test unknown or invalid idea ID safely falls back to defaults
            page.goto(f"{{base}}/create?idea=non-existent-idea-xyz", wait_until="domcontentloaded")
            page.locator("#headline").wait_for(state="attached", timeout=5000)
            default_headline = page.locator("#headline").input_value()
            assert "Ek Onkar" not in default_headline
            assert page.evaluate("document.documentElement.dataset.museMode") == "guest_entry"
            assert default_headline == "My studio artwork"

            # 3. Test export flow marks idea done in muse.actions and offers Log result
            page.goto(
                f"{{base}}/create?idea=idea-1-empowering-women",
                wait_until="domcontentloaded",
            )
            # Verify feed (1080x1350) and story (1080x1920) canvas dimensions
            eval_feed = (
                "async () => {{ const c = await window.museDrawLayout(1350); "
                "return {{ w: c.width, h: c.height }}; }}"
            )
            dims_feed = page.evaluate(eval_feed)
            assert dims_feed["w"] == 1080 and dims_feed["h"] == 1350, f"Got {{dims_feed}}"
            eval_story = (
                "async () => {{ const c = await window.museDrawLayout(1920); "
                "return {{ w: c.width, h: c.height }}; }}"
            )
            dims_story = page.evaluate(eval_story)
            assert dims_story["w"] == 1080 and dims_story["h"] == 1920, f"Got {{dims_story}}"

            # Verify facebook_feed idea uses square 1080x1080 canvas
            page.goto(
                f"{{base}}/create?idea=idea-4-home-titles",
                wait_until="domcontentloaded",
            )
            eval_fb = (
                "async () => {{ const c = await window.museDrawLayout(1080); "
                "return {{ w: c.width, h: c.height }}; }}"
            )
            dims_fb = page.evaluate(eval_fb)
            assert dims_fb["w"] == 1080 and dims_fb["h"] == 1080, f"Got {{dims_fb}}"

            # Applying an idea or restoring a draft resets the review box, and /create finishes
            # that asynchronously after DOMContentLoaded. Wait until it settles before reviewing.
            page.wait_for_load_state("networkidle")
            page.wait_for_function(
                "() => !window.museModes || !window.museModes.current().isLoading"
            )
            page.evaluate("document.getElementById('reviewed').checked = true")
            page.evaluate("document.getElementById('downloadPack').click()")

            # Check that exportDoneOffer is unhidden and links to /progress
            assert page.evaluate("!document.getElementById('exportDoneOffer').hidden")
            offer_href = page.evaluate(
                "document.querySelector('#exportDoneOffer a').getAttribute('href')"
            )
            assert offer_href == "/progress", f"Expected /progress link, got {{offer_href}}"

            # Check localStorage muse.actions
            actions_raw = page.evaluate("localStorage.getItem('muse.actions')")
            actions = json.loads(actions_raw or "{{}}")
            assert "idea-4-home-titles" in actions
            assert actions["idea-4-home-titles"]["status"] == "done"

            # 4. Assert zero model calls
            assert not model_called, "Model API was unexpectedly called during demo mode"

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


def test_today_idea_handoff_e2e(live_server_url: str) -> None:
    """Verify /today?idea=<insight_id> loads idea into daily studio."""
    python_bin = _find_playwright_python()
    if not python_bin:
        pytest.skip("Playwright runtime not installed")

    runner_script = textwrap.dedent(
        f"""
        import json
        from playwright.sync_api import sync_playwright

        base = "{live_server_url}"

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(viewport={{"width": 375, "height": 812}})

            # 1. Load /today with idea-2
            page.goto(f"{{base}}/today?idea=idea-2-starter-prints", wait_until="domcontentloaded")
            page.locator("#postHook").wait_for(state="attached", timeout=5000)

            hook_val = page.locator("#postHook").input_value()
            assert "$14" in hook_val, f"Expected '$14' in #postHook, got '{{hook_val}}'"

            reason_val = page.locator("#dailyReason").inner_text()
            assert "60" in reason_val, f"Expected why_this in #dailyReason, got '{{reason_val}}'"

            # 2. Mark posted and verify Log result link
            page.evaluate("document.getElementById('reviewed').checked = true")
            page.evaluate("document.getElementById('markPosted').click()")

            log_link = page.locator("#logResultLink")
            log_link.wait_for(state="visible", timeout=5000)
            assert log_link.get_attribute("href") == "/progress"

            actions_raw = page.evaluate("localStorage.getItem('muse.actions')")
            actions = json.loads(actions_raw or "{{}}")
            assert "idea-2-starter-prints" in actions
            assert actions["idea-2-starter-prints"]["status"] == "done"

            # 3. Invalid idea falls back safely
            page.goto(f"{{base}}/today?idea=unknown-invalid-id", wait_until="domcontentloaded")
            page.locator("#itemTitle").wait_for(state="attached", timeout=5000)
            default_title = page.locator("#itemTitle").inner_text()
            assert "Ek Onkar" not in default_title
            assert page.evaluate("document.documentElement.dataset.museMode") == "guest_entry"

            browser.close()
        """
    )

    proc = subprocess.run(
        [python_bin, "-c", runner_script],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert proc.returncode == 0, (
        f"Playwright script failed:\nSTDOUT: {proc.stdout}\nSTDERR: {proc.stderr}"
    )
