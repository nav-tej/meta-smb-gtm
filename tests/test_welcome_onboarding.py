"""Track H — Signed-in 4-step shop onboarding (/welcome) and honest workspace tests."""

from __future__ import annotations

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
from fastapi.testclient import TestClient

from src.api.main import app


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


def test_welcome_route_serves_onboarding_page() -> None:
    client = TestClient(app)
    resp = client.get("/welcome")
    assert resp.status_code == 200
    assert "Set Up Your Shop" in resp.text
    assert 'id="wkStep1"' in resp.text
    assert 'id="wkStep2"' in resp.text
    assert 'id="wkStep3"' in resp.text
    assert 'id="wkStep4"' in resp.text
    assert 'id="wkStepDone"' in resp.text
    assert "Sample shop" in resp.text


@pytest.mark.parametrize("viewport_width", [375, 1440])
def test_welcome_onboarding_full_flow_and_honest_workspace(
    live_server_url: str, viewport_width: int
) -> None:
    pw_python = _find_playwright_python()
    if pw_python is None:
        pytest.skip("Playwright Python runtime unavailable")

    runner_code = textwrap.dedent(
        f"""
        import json
        from playwright.sync_api import sync_playwright

        live_server_url = {live_server_url!r}
        viewport_width = {viewport_width}
        workspace_store = {{"document": {{}}, "version": 1, "owner_id": "u-new-1"}}
        model_api_called = False
        remaining_runs = 2

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(viewport={{"width": viewport_width, "height": 900}})
            page = context.new_page()
            page.on("console", lambda msg: print(f"CONSOLE: {{msg.text}}", flush=True))
            page.on("pageerror", lambda err: print(f"PAGEERROR: {{err}}", flush=True))
            def handle_model(route):
                global model_api_called
                model_api_called = True
                route.abort()

            page.route("*api.meta.ai*", handle_model)
            page.route("*llama.com*", handle_model)

            def handle_route(route):
                global model_api_called, remaining_runs
                try:
                    url = route.request.url
                    method = route.request.method
                    print(f"ROUTE: {{method}} {{url}}", flush=True)

                    is_spend = url.endswith("/api/v1/credits/spend")
                    is_build = url.endswith("/api/v1/onboarding/build")
                    if is_spend and method == "POST":
                        remaining_runs = max(0, remaining_runs - 1)
                        route.fulfill(
                            status=200,
                            content_type="application/json",
                            body=json.dumps({{
                                "balance": remaining_runs,
                                "starting_balance": 3,
                                "enforced": True,
                                "persistent": True,
                                "note": "",
                            }}),
                        )
                        return
                    if is_build and method == "POST":
                        post_data = route.request.post_data_json or {{}}
                        workspace_store["document"]["onboarding"] = {{
                            **post_data,
                            "completed_at": "2026-11-10T12:00:00Z",
                            "used_run": False,
                        }}
                        route.fulfill(
                            status=200,
                            content_type="application/json",
                            body=json.dumps({{
                                "success": True,
                                "charged": False,
                                "used_run": False,
                                "runs_remaining": remaining_runs,
                                "completed_at": "2026-11-10T12:00:00Z",
                                "workspace": workspace_store,
                            }}),
                        )
                        return

                    if url.endswith("/api/v1/account/me"):
                        route.fulfill(
                            status=200,
                            content_type="application/json",
                            body=json.dumps(
                                {{
                                    "configured": True,
                                    "user": {{
                                        "id": "u-new-1",
                                        "email": "maker@mountainpottery.com",
                                        "email_verified": True,
                                    }},
                                    "usage": {{
                                        "plan": "trial",
                                        "used": 0,
                                        "limit": 3,
                                        "remaining": remaining_runs,
                                        "resets_at": None,
                                    }},
                                    "live_available": remaining_runs > 0,
                                }}
                            ),
                        )
                        return

                    if "/api/v1/account/workspace" in url:
                        if method == "GET":
                            route.fulfill(
                                status=200,
                                content_type="application/json",
                                body=json.dumps(workspace_store),
                            )
                        else:
                            payload = json.loads(route.request.post_data or "{{}}")
                            workspace_store["document"] = payload.get("document", {{}})
                            workspace_store["version"] += 1
                            route.fulfill(
                                status=200,
                                content_type="application/json",
                                body=json.dumps(workspace_store),
                            )
                        return

                    if url.endswith("/api/v1/ingest-storefront") and method == "POST":
                        body = json.loads(route.request.post_data or "{{}}")
                        route.fulfill(
                            status=200,
                            content_type="application/json",
                            body=json.dumps(
                                {{
                                    "business_name": body.get("business_name")
                                    or "Mountain Pottery",
                                    "total_channels": 1,
                                    "total_pages_crawled": 18,
                                    "channels": [
                                        {{
                                            "kind": "own_website",
                                            "url": "https://mountainpottery.com/",
                                            "host": "mountainpottery.com",
                                            "status": "fetched",
                                            "pages_found": 18,
                                        }}
                                    ],
                                    "discovered_catalog_items": [
                                        {{
                                            "url": "https://mountainpottery.com/products/mug",
                                            "title": "Speckled Stoneware Mug",
                                            "bucket": "products",
                                            "price_hint": "$24",
                                        }},
                                        {{
                                            "url": "https://mountainpottery.com/products/vase",
                                            "title": "Kiln-Fired Vase Set",
                                            "bucket": "products",
                                            "price_hint": "$180",
                                        }},
                                        {{
                                            "url": "https://instagram.com/mountainpottery",
                                            "title": "Instagram link",
                                            "bucket": "social",
                                            "price_hint": None,
                                        }},
                                    ],
                                    "detected_price_hints": ["$24", "$180"],
                                    "seller_context": "Mountain Pottery Studio",
                                }}
                            ),
                        )
                        return

                    route.continue_()
                except Exception as route_err:
                    print(f"ROUTE EXCEPTION: {{route_err}}", flush=True)

            page.route("**/api/v1/**", handle_route)

            # 1. Visiting /account as a brand-new signed-in user redirects to /welcome
            page.goto(f"{{live_server_url}}/account")
            page.wait_for_selector("#wkStep1:not([hidden])", timeout=10000)
            assert "/welcome" in page.url, f"Expected /welcome in url but got {{page.url}}"

            page.evaluate(
                "window.__trackedEvents = []; "
                "window.museTrack = (n, p) => window.__trackedEvents.push({{name: n, props: p}});"
            )

            overflow = page.evaluate(
                "document.documentElement.scrollWidth > document.documentElement.clientWidth"
            )
            assert overflow is False, f"Horizontal overflow at {{viewport_width}}px"

            # 2. Step 1: Enter bare domain + business name and scan shop (free · 0 runs)
            page.fill("#wkShopUrl", "mountainpottery.com")
            page.fill("#wkBusinessName", "Mountain Pottery Studio")
            page.click("#wkScanShopBtn")
            page.wait_for_selector("#wkShopProof:not([hidden])")
            proof_text = page.text_content("#wkShopProof") or ""
            assert "Mountain Pottery Studio" in proof_text
            assert "$24 to $180" in proof_text
            assert "Sarabjit" not in proof_text

            page.click("#wkStep1NextBtn")
            page.wait_for_selector("#wkStep2:not([hidden])")

            # 3. Verify resume across reload and socials chip detection (free · 0 runs)
            page.reload(wait_until="domcontentloaded")
            page.evaluate(
                "window.__trackedEvents = window.__trackedEvents || []; "
                "window.museTrack = (n, p) => window.__trackedEvents.push({{name: n, props: p}});"
            )
            page.wait_for_selector("#wkStep2:not([hidden])")

            chips_text = page.text_content("#wkSocialChips") or ""
            assert "@mountainpottery" in chips_text
            page.click("#wkStep2NextBtn")
            page.wait_for_selector("#wkStep3:not([hidden])")

            # 4. Step 3: Competitor watchlist is free (0 runs)
            cost_banner = page.text_content("#wkCompCostBanner") or ""
            assert "free" in cost_banner.lower()
            assert "0 runs" in cost_banner

            page.fill("#wkManualCompUrl", "desertceramics.com")
            page.fill("#wkManualCompReason", "Similar handmade stoneware mugs")
            page.click("#wkAddCompBtn")
            comp_list_text = page.text_content("#wkCompList") or ""
            assert "desertceramics.com" in comp_list_text

            # Check that remaining runs is still 2 before Step 4
            runs_pill_text = page.text_content("#wkRunsPill") or ""
            assert "2 runs left" in runs_pill_text

            page.click("#wkStep3NextBtn")
            page.wait_for_selector("#wkStep4:not([hidden])")

            # 5. Step 4: Discloses free 0-run cost on completion and finishes
            disclosure_text = page.text_content("#wkRunDisclosureBox") or ""
            assert "free (0 runs used)" in disclosure_text

            page.select_option("#wkPrefExperience", "new")
            page.fill("#wkPrefFocus", "Highlight stoneware gift sets under $60")
            page.click("#wkStep4FinishBtn")
            page.wait_for_selector("#wkStepDone:not([hidden])")
            page.wait_for_selector("#wkDoneTitle:has-text('workspace is ready')")

            # 6. Step 5 completion screen: Explains what that run produced
            done_text = page.text_content("#wkStepDone") or ""
            assert "Mountain Pottery Studio workspace is ready" in done_text
            assert "What Muse read" in done_text
            assert "What it found" in done_text
            assert "$24 to $180" in done_text
            assert "What a run is" in done_text
            assert "2 runs left" in done_text or "runs remaining" in done_text.lower()
            assert "What is cached" in done_text
            assert "@mountainpottery" in done_text

            # Verify PostHog events
            events = page.evaluate("window.__trackedEvents")

            completed_ev = next(e for e in events if e["name"] == "onboarding_completed")
            assert completed_ev["props"] == {{
                "has_socials": True,
                "competitor_count": 1,
                "used_run": False,
            }}

            explainer_ev = next(e for e in events if e["name"] == "onboarding_explainer_viewed")
            assert explainer_ev["props"]["used_run"] is False

            # Verify no URLs or social handles leaked into analytics
            serialized_events = json.dumps(events)
            assert "mountainpottery.com" not in serialized_events
            assert "@mountainpottery" not in serialized_events

            # 7. Navigate to home loop (/) and verify user's own data and NO Sarabjit data
            page.click("#wkOpenWorkspaceBtn")
            page.wait_for_url(f"{{live_server_url}}/")
            page.wait_for_timeout(200)

            active_label = page.text_content("#activeWorkspaceLabel") or ""
            assert active_label == "Mountain Pottery Studio", f"Got {{active_label!r}}"
            journey_text = page.text_content("#journey") or ""
            assert "Mountain Pottery Studio" in journey_text
            assert "$24 to $180" in journey_text
            assert "desertceramics.com" in journey_text
            assert "SikhiArt" not in journey_text
            assert "Ek Onkar" not in journey_text

            # 8. Opening Sample shop (?workspace=sample) shows the Sarabjit sample shop
            page.goto(f"{{live_server_url}}/?workspace=sample", wait_until="domcontentloaded")
            page.wait_for_timeout(200)
            sample_label = page.text_content("#activeWorkspaceLabel") or ""
            assert "Art of Sarabjit Singh" in sample_label

            assert model_api_called is False
            browser.close()
            print("PLAYWRIGHT ONBOARDING FLOW PASSED")
        """
    )
    res = subprocess.run(
        [pw_python, "-c", runner_code],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert res.returncode == 0, f"STDOUT:\n{res.stdout}\nSTDERR:\n{res.stderr}"
    assert "PLAYWRIGHT ONBOARDING FLOW PASSED" in res.stdout
