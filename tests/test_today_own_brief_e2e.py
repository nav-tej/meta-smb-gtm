"""Real-route own daily briefs, handoffs and stale-response isolation in Chromium."""

from __future__ import annotations

import asyncio
import importlib
import json
import os
import socket
import subprocess
import threading
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
import uvicorn
from fastapi import HTTPException

from src.api.main import app
from src.services.accounts import AccountSession
from tests.test_api_calls_per_page_e2e import _find_playwright_python

PHOTO = Path(__file__).resolve().parent / "fixtures/product_photo.png"
USERS = {
    "services": 120,
    "products": 120,
    "budget": 5,
    "setup": 120,
    "failure": 120,
    "delayed": 120,
}
NAMES = {uid: f"{uid.title()} Meadow Business" for uid in USERS}


def _document(uid: str, minutes: int) -> dict[str, Any]:
    return {
        "onboarding": {
            "business_name": NAMES[uid],
            "business_type": "services" if uid == "services" else "products",
            "website_url": "https://wildmeadow.test",
            "shop_urls": ["https://wildmeadow.test"],
            "completed_at": None if uid == "setup" else "2026-11-10T10:00:00Z",
            "competitors": [
                {
                    "name": f"{uid} rival {i}",
                    "url": f"https://{uid}-rival-{i}.test",
                    "selected": True,
                    "role": "similar_audience",
                }
                for i in range(2)
            ],
        },
        "outcomes": []
        if uid == "budget"
        else [
            {
                "id": f"{uid}-result",
                "title": f"{uid} private result",
                "date": "2026-11-21",
                "channel": "instagram",
                "reach": 31,
                "clicks": 7,
                "orders": 2,
                "revenue": 42.5,
                "notes": f"{uid} result note",
                "minutes": 15,
            }
        ],
        "preferences": {
            "goal": "Grow visits",
            "access": {"minutes_per_week": minutes, "channels": ["instagram", "website"]},
        },
    }


@pytest.fixture
def own_brief_server(monkeypatch: pytest.MonkeyPatch) -> Iterator[tuple[str, dict[str, Any]]]:
    stores = {
        uid: {"document": _document(uid, minutes), "version": 1, "owner_id": uid}
        for uid, minutes in USERS.items()
    }
    sessions = {
        uid: AccountSession(
            user_id=uid,
            email=f"{uid}@wildmeadow.test",
            email_verified=True,
            access_token="tok",
            session_id=None,
        )
        for uid in USERS
    }
    calls: dict[str, Any] = {"muse": 0, "brief": [], "crawl": 0, "external": 0}

    async def fake_resolve(
        request: Any, _response: Any = None, require_verified: bool = False
    ) -> AccountSession | None:
        uid = request.cookies.get("muse_e2e_user")
        if uid in sessions:
            return sessions[uid]
        if require_verified:
            raise HTTPException(401, "Sign in required")
        return None

    async def fake_load(session: AccountSession) -> dict[str, Any]:
        return json.loads(json.dumps(stores[session.user_id]))

    async def fake_save(
        session: AccountSession,
        doc: dict[str, Any],
        expected_version: int | None = None,
        expected_owner: str | None = None,
    ) -> dict[str, Any]:
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
        calls["crawl"] += 1
        return [], []

    def no_muse(*_args: Any, **_kwargs: Any) -> Any:
        calls["muse"] += 1
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
        "src.services.daily_brief",
        "src.services.outcomes",
    ):
        module = importlib.import_module(name)
        for attr, fake in fakes.items():
            if hasattr(module, attr):
                monkeypatch.setattr(module, attr, fake)
    monkeypatch.setattr("src.api.intel.collect_entries", no_crawl)
    monkeypatch.setattr("src.clients.meta.get_meta_client", no_muse)

    # Only inject transport failures/latency: successful responses still use the real
    # route, workspace service and ranker. No browser-level API response mocks.
    route_module = importlib.import_module("src.api.daily_brief")
    real_daily_brief = route_module.daily_brief

    async def controlled_brief(**kwargs: Any) -> Any:
        account = kwargs.get("account")
        uid = account.user_id if account else "sample"
        calls["brief"].append(uid)
        if uid == "failure" and calls["brief"].count(uid) == 1:
            raise HTTPException(503, "Fixture temporary failure")
        if uid == "delayed":
            await asyncio.sleep(2)
        return await real_daily_brief(**kwargs)

    monkeypatch.setattr(route_module, "daily_brief", controlled_brief)

    # A stray backend HTTP request must fail locally, not contact a provider.
    async def no_external(*_args: Any, **_kwargs: Any) -> Any:
        calls["external"] += 1
        raise AssertionError("External HTTP forbidden in own brief E2E")

    monkeypatch.setattr("httpx.AsyncClient.send", no_external)

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
        yield f"http://127.0.0.1:{port}", calls
    finally:
        server.should_exit = True
        thread.join(timeout=3)


BROWSER_SCRIPT = r'''
import json, re, sys
from pathlib import Path
from urllib.parse import urlparse, parse_qs
from playwright.sync_api import sync_playwright, expect

BASE, WIDTH, SCENARIO, USER, ARTIFACTS, PHOTO = json.loads(sys.argv[1])
BAD = re.compile(
    r"Sarabjit|SikhiArt|Empowering Women|Pixels|Saatchi|Fine Art America|overnight changes at", re.I
)
NAME = USER.title() + " Meadow Business"
artifacts = Path(ARTIFACTS)
artifacts.mkdir(parents=True, exist_ok=True)

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    ctx = browser.new_context(viewport={"width": WIDTH, "height": 900})
    if USER:
        ctx.add_cookies([{"name": "muse_e2e_user", "value": USER, "url": BASE}])
    page = ctx.new_page()
    errors, requests, replies, navigations = [], [], [], []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.on("request", lambda req: navigations.append(req.url)
            if req.is_navigation_request() and req.frame == page.main_frame else None)
    page.on("request", lambda req: requests.append((req.method, req.url)))
    page.on(
        "response",
        lambda response: (
            replies.append(response) if "/api/v1/daily-brief" in response.url else None
        ),
    )
    ctx.route(
        lambda url: not url.startswith(BASE) and not url.startswith(("data:", "blob:")),
        lambda route: route.abort(),
    )

    def settled(title):
        expect(page.locator("#msBriefTitle")).to_have_text(title, timeout=15000)
        expect(page.locator("#msBrief")).not_to_have_class(re.compile("ms-loading"), timeout=15000)

    def private_brief():
        text = page.locator("#msBrief").inner_text()
        assert not BAD.search(text), text
        assert page.locator("#msBrief .ms-triage").count() == 0
        return text

    def capture(label):
        path = artifacts / f"{WIDTH}-{SCENARIO}-{USER or 'guest'}-{label}.png"
        page.locator("#msBrief").screenshot(path=str(path))
        print("SCREENSHOT=" + str(path), flush=True)

    def own_requests():
        return [
            url
            for method, url in requests
            if "/api/v1/daily-brief" in url and "workspace=own" in url
        ]

    def sample_state():
        settled("What changed at the shops you watch")
        expect(page.locator("#msBrief .ms-brief-columns")).to_be_visible()
        assert page.locator("#msBrief .ms-move .ms-triage button").count() == 4
        assert "SikhiArt" in page.locator("#msBrief").inner_text()

    try:
        if SCENARIO == "guard":
            page.goto(BASE + "/today?workspace=own", wait_until="domcontentloaded")
            page.wait_for_function(
                "() => performance.getEntriesByType('resource')"
                ".some(e => e.name.includes('/seller-memory'))"
            )
            # Wait for the actual pending request, without intercepting its response.
            while not own_requests():
                page.wait_for_timeout(10)
            assert not replies, "The delayed brief must still be in flight at the switch"
            if USER == "delayed":
                if WIDTH == 375:
                    page.evaluate("window.museModes.enterSampleMode({sample: 'sarabjit_singh'})")
                    sample_state()
                else:
                    ctx.add_cookies([{"name": "muse_e2e_user", "value": "products", "url": BASE}])
                    page.evaluate("window.museAccount.refresh()")
                    page.wait_for_function("window.museModes.current().ownerId === 'products'")
            if WIDTH == 375:
                # The same document must reject the completed old-mode response.
                for _ in range(100):
                    if any("workspace=own" in response.url for response in replies):
                        break
                    page.wait_for_timeout(50)
                old = next(response for response in replies if "workspace=own" in response.url)
                old.finished()
                page.wait_for_timeout(100)
                assert len(own_requests()) == 1, own_requests()
            else:
                # today.js intentionally reloads when the account changes, cancelling
                # the prior document's request. Each document gets exactly one read.
                settled("Products Meadow Business · today’s brief")
                assert len(navigations) == 2, navigations
                assert len(own_requests()) == 2, own_requests()
                assert "products private result" in page.locator("#msBrief").inner_text()
            assert "Delayed Meadow Business" not in page.locator("#msBrief").text_content()
            assert "delayed rival" not in page.locator("#msBrief").text_content()
            assert "delayed private result" not in page.locator("#msBrief").text_content()
            if WIDTH == 375:
                sample_state()
            else:
                assert not BAD.search(page.locator("#msBrief").text_content())
            capture("switched")
        elif SCENARIO == "states":
            url = "/today?workspace=sample" if USER == "sample" else "/today"
            page.goto(BASE + url, wait_until="networkidle")
            if USER == "sample":
                sample_state()
                assert not own_requests()
            elif USER == "setup":
                settled("Your shop’s brief is not built yet")
                expect(page.locator("#museSetupNotice")).to_be_visible()
                expect(page.locator("#msBrief .ms-brief-columns")).not_to_be_visible()
                assert page.locator("#msBrief .ms-triage").count() == 0
                assert len(own_requests()) == 1
                assert replies[-1].status == 409
                assert "setup private result" not in page.locator("#msBrief").text_content()
            else:
                settled("See what a daily brief looks like")
                assert not own_requests()
                expect(page.locator("#msBrief .ms-brief-columns")).not_to_be_visible()
                assert page.locator("#msBrief .ms-triage").count() == 0
                assert (
                    page.locator("#msBrief .ms-move-links a").first.get_attribute("href")
                    == "/today?workspace=sample"
                )
            capture("unchanged")
        else:
            page.goto(BASE + "/today?workspace=own", wait_until="networkidle")
            if SCENARIO == "failure":
                settled("Your shop’s brief is not built yet")
                expect(page.locator("#msBrief .ms-brief-retry")).to_be_visible()
                assert "Could not load your brief" in page.locator("#msBrief").inner_text()
                private_brief()
                assert len(own_requests()) == 1
                capture("failed")
                page.locator("#msBrief .ms-brief-retry").click()
            settled(NAME + " · today’s brief")
            text = private_brief()
            expected_reads = 2 if SCENARIO == "failure" else 1
            assert len(own_requests()) == expected_reads, own_requests()
            brief = next(
                response.json() for response in reversed(replies) if response.status == 200
            )
            assert brief["business_name"] == NAME
            assert len(brief["items"]) == 2
            assert page.locator("#msBrief .ms-watch li").count() == 2
            assert "not checked yet" in text.lower(), text
            assert "does not check" in text and "overnight yet" in text
            for other in ("services", "products", "budget"):
                if other != USER:
                    assert other + " rival" not in text
                    assert other + " private result" not in text
            if USER == "services":
                assert not re.search(
                    r"\b(shop|shops|collection|collections|catalog)\b", text, re.I
                ), text
            if USER == "budget":
                assert "Heads up:" in text
                assert "Why this fits:" not in page.locator("#msBrief .ms-move").inner_text()
                assert "after posting" in text.lower()
            else:
                results = page.locator('#msBrief [aria-label="Performance trends"]')
                assert USER + " private result" in results.inner_text()
                assert USER + " result note" in results.inner_text()
                for value in ("31", "7", "2", "42.5"):
                    assert value in results.inner_text(), results.inner_text()
            first = brief["action_items"][0]["recommendation"]
            expect(page.locator("#smStudioContextBar")).to_contain_text(
                "Selected move: " + first["title"]
            )
            assert page.locator("#msBrief .ms-move strong").inner_text() == first["title"]
            links = page.locator("#msBrief .ms-action a")
            assert links.count() == len(brief["action_items"])
            for href in links.evaluate_all('(nodes) => nodes.map(n => n.getAttribute("href"))'):
                assert href == "/create?workspace=own", href
            assert not page.evaluate(
                "document.documentElement.scrollWidth > document.documentElement.clientWidth"
            )
            capture("loaded")
            before = len(requests)
            with page.expect_response(
                lambda response: "/api/v1/daily-brief?workspace=own" in response.url
            ):
                page.get_by_role("button", name="Re-check now", exact=True).click()
            settled(NAME + " · today’s brief")
            assert len(own_requests()) == expected_reads + 1
            assert "0 runs" in page.get_by_role(
                "button", name="Re-check now", exact=True
            ).get_attribute("title")
            assert not any(
                "/monitor" in url or "/generate-ads" in url or "/credits/spend" in url
                for method, url in requests[before:]
            ), requests[before:]
            assert page.evaluate("window.museAccount.getSnapshot().usage.remaining") == 3
            if SCENARIO == "own":
                # Exercise the focus link and every action link, not just their hrefs.
                selectors = ["#msBrief .ms-move-links a:first-child"] + [
                    f"#msBrief .ms-action:nth-child({i + 1}) a"
                    for i in range(len(brief["action_items"]))
                ]
                recommendations = [first] + [
                    move["recommendation"] for move in brief["action_items"]
                ]
                for index, (selector, rec) in enumerate(zip(selectors, recommendations)):
                    if index:
                        page.goto(BASE + "/today?workspace=own", wait_until="networkidle")
                        settled(NAME + " · today’s brief")
                        expect(page.locator("#smStudioContextBar")).to_contain_text(
                            "Selected move:"
                        )
                    page.locator(selector).click()
                    page.wait_for_url("**/create?workspace=own&sm_handoff=*")
                    page.wait_for_function(
                        "document.documentElement.dataset.museMode === 'account_own'"
                    )
                    hid = parse_qs(urlparse(page.url).query)["sm_handoff"][0]
                    payload = page.evaluate(
                        """(id) => Object.entries(localStorage)
                        .filter(([key]) => key.startsWith('muse.sm.handoff.'))
                        .map(([,value]) => JSON.parse(value)).find(value => value.id === id)""",
                        hid,
                    )
                    assert payload["owner_id"] == USER, payload
                    assert payload["workspace_mode"] == "own", payload
                    for key in ("title", "action", "why_this_fits", "over_budget", "channel"):
                        assert payload[key] == rec[key], (key, payload, rec)
                    assert payload["recommendation_id"] == rec["id"]
                    defaults = rec["editor_defaults"]
                    for key in (
                        "business_name",
                        "minutes_per_week",
                        "context_summary",
                        "placement",
                        "cta",
                    ):
                        assert payload[key] == defaults[key], (key, payload, defaults)
                    if not page.input_value("#productName").strip():
                        page.fill("#productName", "Meadow offer")
                    page.locator("#productPhoto").set_input_files(PHOTO)
                    page.wait_for_function(
                        "() => !!document.getElementById('productImage')?.getAttribute('src')"
                    )
                    page.locator("#nextButton").click()
                    expect(page.locator("#handoffGuidanceBox")).to_be_visible()
                    why = page.locator("#handoffWhyFits").inner_text()
                    label = "Heads up:" if rec["over_budget"] else "Why this fits:"
                    assert why.startswith(label) and rec["why_this_fits"] in why, why
        assert not errors, errors
    finally:
        ctx.close()
        browser.close()
print("TODAY_OWN_BRIEF_OK")
'''


@pytest.mark.parametrize("width", [375, 1440])
@pytest.mark.parametrize(
    ("scenario", "user"),
    [
        ("own", "services"),
        ("own", "products"),
        ("own", "budget"),
        ("states", ""),
        ("states", "setup"),
        ("states", "sample"),
        ("failure", "failure"),
        ("guard", "delayed"),
    ],
)
def test_today_own_brief_e2e(
    own_brief_server: tuple[str, dict[str, Any]],
    tmp_path: Path,
    width: int,
    scenario: str,
    user: str,
) -> None:
    python_bin = _find_playwright_python()
    if python_bin is None:
        pytest.skip("Playwright Python runtime unavailable")
    base_url, calls = own_brief_server
    artifacts = Path(os.environ.get("TODAY_OWN_BRIEF_ARTIFACT_DIR", str(tmp_path)))
    proc = subprocess.run(
        [
            python_bin,
            "-c",
            BROWSER_SCRIPT,
            json.dumps([base_url, width, scenario, user, str(artifacts), str(PHOTO)]),
        ],
        capture_output=True,
        text=True,
        check=False,
        timeout=120,
    )
    print(proc.stdout, end="")
    assert proc.returncode == 0, f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
    assert "TODAY_OWN_BRIEF_OK" in proc.stdout
    assert calls["muse"] == 0
    assert calls["external"] == 0
