"""Unit, route, and Chromium E2E tests for own-workspace competitor watchlist checks."""

from __future__ import annotations

import importlib
import json
import os
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any

import pytest
import uvicorn
from fastapi import HTTPException
from fastapi.testclient import TestClient

from src.api.main import app
from src.config import get_settings
from src.models.intel import SitemapEntry
from src.services import scan_guard
from src.services.accounts import AccountSession
from src.services.competitor_checks import (
    MAX_COMPETITORS_PER_CHECK,
    MAX_PRICE_HINT_LENGTH,
    MAX_STORED_PAGES_PER_COMPETITOR,
    MAX_TITLE_LENGTH,
    classify_check_error,
    compute_top_insight,
    diff_competitor_pages,
    entries_to_snapshot_pages,
    error_competitor_result,
    extract_selected_competitors,
)

REPO_ROOT = Path(__file__).resolve().parents[1]


def _find_playwright_python() -> str | None:
    for candidate in (os.environ.get("PLAYWRIGHT_PYTHON"), "/usr/bin/python3", sys.executable):
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


def test_digest_script_versions_and_copy_contracts() -> None:
    """Verify cache-busting pins and removal of old digest wording."""
    digest_html = (REPO_ROOT / "src/api/static/digest.html").read_text(encoding="utf-8")
    digest_js = (REPO_ROOT / "src/api/static/digest.js").read_text(encoding="utf-8")
    assert "digest.js?v=20261123-uxgap21" in digest_html
    assert "digest-signup.js?v=20261122-ag1" in digest_html
    assert "Canonical preview topics" not in digest_html
    assert "What to include" in digest_html
    assert "Queued for your scheduled digest updates" not in digest_js


def test_diff_first_check_new_removed_price_change_and_unchanged() -> None:
    """Verify first check, diffing (new/removed/price), unchanged, and top insight."""
    day1_pages = entries_to_snapshot_pages(
        [
            SitemapEntry(
                loc="https://summit.test/services/seo-audit",
                title="SEO Audit",
                price_hint="$500",
            ),
            SitemapEntry(
                loc="https://summit.test/services/content-sprint",
                title="Content Sprint",
                price_hint="$900",
            ),
        ]
    )

    res1, snap1 = diff_competitor_pages(
        None,
        day1_pages,
        name="Summit Growth",
        url="https://summit.test",
        checked_at="2026-11-20T10:00:00Z",
    )
    assert res1["status"] == "first_check"
    assert res1["counts"] == {"new_listing": 0, "removed_listing": 0, "price_change": 0}
    assert (
        res1["summary"]
        == "First check: Muse now knows 2 of their pages. Changes show from the next check."
    )
    assert compute_top_insight([res1], "2026-11-20T10:00:00Z")["kind"] == "first_check"

    # Unchanged second check
    res_same, snap_same = diff_competitor_pages(
        snap1,
        day1_pages,
        name="Summit Growth",
        url="https://summit.test",
        checked_at="2026-11-21T10:00:00Z",
    )
    assert res_same["status"] == "unchanged"
    assert res_same["counts"] == {"new_listing": 0, "removed_listing": 0, "price_change": 0}
    unchanged_insight = compute_top_insight([res_same], "2026-11-21T10:00:00Z")
    assert unchanged_insight["title"] == "No changes at the competitors you watch since Nov 20"

    # Changed third check: 1 new page, 1 removed page, 1 price change
    day3_pages = entries_to_snapshot_pages(
        [
            SitemapEntry(
                loc="https://summit.test/services/seo-audit",
                title="SEO Audit",
                price_hint="$650",
            ),
            SitemapEntry(
                loc="https://summit.test/services/ai-strategy",
                title="AI Strategy Advisory",
                price_hint="$1200",
            ),
        ]
    )
    res3, _snap3 = diff_competitor_pages(
        snap_same,
        day3_pages,
        name="Summit Growth",
        url="https://summit.test",
        checked_at="2026-11-22T10:00:00Z",
    )
    assert res3["status"] == "changed"
    assert res3["counts"] == {"new_listing": 1, "removed_listing": 1, "price_change": 1}
    assert [p["title"] for p in res3["new_pages"]] == ["AI Strategy Advisory"]
    assert [p["title"] for p in res3["removed_pages"]] == ["Content Sprint"]
    assert res3["price_changes"] == [
        {
            "loc": "https://summit.test/services/seo-audit",
            "title": "SEO Audit",
            "old_price": "$500",
            "new_price": "$650",
        }
    ]
    insight = compute_top_insight([res3], "2026-11-22T10:00:00Z")
    assert insight["title"] == "Summit Growth added 1 page"
    assert "Watching" not in insight["title"]


def test_caps_selected_filtering_and_error_preserves_baseline() -> None:
    """Verify page/title/competitor caps, selected filtering, and error baseline preservation."""
    entries = [
        SitemapEntry(
            loc=f"https://big.test/p/{i}",
            title="A" * 200,
            price_hint="$" + "9" * 60,
        )
        for i in range(45)
    ]
    pages = entries_to_snapshot_pages(entries)
    assert len(pages) == MAX_STORED_PAGES_PER_COMPETITOR
    assert len(pages[0]["title"]) == MAX_TITLE_LENGTH
    assert len(pages[0]["price_hint"]) == MAX_PRICE_HINT_LENGTH

    doc = {
        "preferences": {
            "competitor_entries": [
                {"name": "Skipped", "url": "https://skip.test", "selected": False},
                *[
                    {"name": f"Comp {i}", "url": f"https://comp{i}.test/", "selected": True}
                    for i in range(10)
                ],
            ]
        }
    }
    selected = extract_selected_competitors(doc)
    assert len(selected) == MAX_COMPETITORS_PER_CHECK
    assert all(item["url"] != "https://skip.test" for item in selected)

    err_kind, err_msg = classify_check_error("HTTP 403 Forbidden")
    assert err_kind == "blocked"
    assert "blocks automated reading" in err_msg
    assert classify_check_error("ReadTimeout")[0] == "timeout"
    assert classify_check_error("no sitemap found")[0] == "no_sitemap"

    prev_snap = {"checked_at": "2026-11-20T10:00:00Z", "page_count": 2, "pages": pages[:2]}
    err_res, err_stored = error_competitor_result(
        prev_snap,
        name="Blocked Co",
        url="https://blocked.test",
        checked_at="2026-11-22T10:00:00Z",
        error_kind="blocked",
        error_message=err_msg,
    )
    assert err_res["status"] == "error"
    assert err_res["error_kind"] == "blocked"
    assert len(err_stored["pages"]) == 2


def test_big_site_window_shift_never_invents_removed_or_new_pages() -> None:
    """A site bigger than the 30-page window: a shifted window is not a change (pass 21)."""
    from datetime import datetime

    def window(start: int, *, dated: dict[int, str] | None = None) -> list[dict[str, str]]:
        dated = dated or {}
        return entries_to_snapshot_pages(
            [
                SitemapEntry(
                    loc=f"https://big.test/p/{i}",
                    title=f"Page {i}",
                    lastmod=datetime.fromisoformat(dated[i]) if i in dated else None,
                )
                for i in range(start, start + MAX_STORED_PAGES_PER_COMPETITOR)
            ]
        )

    res1, snap1 = diff_competitor_pages(
        None,
        window(0),
        name="Big Co",
        url="https://big.test",
        checked_at="2026-11-20T10:00:00Z",
        truncated=True,
    )
    assert res1["partial"] is True
    assert "(they have more)" in res1["summary"]

    # The window slid by two pages: two old pages entered, two left, none of it dated.
    res2, snap2 = diff_competitor_pages(
        snap1,
        window(2, dated={30: "2026-01-05", 31: "2026-01-06"}),
        name="Big Co",
        url="https://big.test",
        checked_at="2026-11-21T10:00:00Z",
        truncated=True,
    )
    assert res2["counts"] == {"new_listing": 0, "removed_listing": 0, "price_change": 0}
    assert res2["status"] == "unchanged"
    assert "does not report removed pages" in res2["summary"]

    # A page dated on or after the last check does count, as "new or updated".
    res3, _ = diff_competitor_pages(
        snap2,
        window(3, dated={32: "2026-11-21"}),
        name="Big Co",
        url="https://big.test",
        checked_at="2026-11-22T10:00:00Z",
        truncated=True,
    )
    assert res3["counts"] == {"new_listing": 1, "removed_listing": 0, "price_change": 0}
    assert [p["title"] for p in res3["new_pages"]] == ["Page 32"]
    assert res3["summary"].startswith("Found 1 new or updated page since Nov 21.")
    insight = compute_top_insight([res3], "2026-11-22T10:00:00Z")
    assert insight["title"] == "Big Co has 1 new or updated page"

    # A snapshot saved before the flag existed is still treated as a full window.
    legacy = {k: v for k, v in snap1.items() if k != "partial"}
    res_legacy, _ = diff_competitor_pages(
        legacy,
        window(5),
        name="Big Co",
        url="https://big.test",
        checked_at="2026-11-21T10:00:00Z",
    )
    assert res_legacy["counts"]["removed_listing"] == 0
    assert res_legacy["counts"]["new_listing"] == 0


def test_competitors_check_route_auth_429_409_and_diff(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify 401 signed-out, 403 unverified, 429 Retry-After, 409 conflict, and two-check diff."""
    scan_guard.reset()
    user_verified = AccountSession(
        user_id="chk-u1",
        email="owner@nplusalpha.test",
        email_verified=True,
        access_token="tok",
        session_id=None,
    )
    user_unverified = AccountSession(
        user_id="chk-u2",
        email="unverified@nplusalpha.test",
        email_verified=False,
        access_token="tok2",
        session_id=None,
    )
    store: dict[str, Any] = {
        "version": 3,
        "owner_id": "chk-u1",
        "document": {
            "onboarding": {"business_name": "n Plus Alpha Consulting"},
            "preferences": {
                "competitor_entries": [
                    {"name": "Summit Growth", "url": "https://summit.test", "selected": True}
                ]
            },
        },
    }

    async def fake_resolve(request: Any, _response: Any = None, require_verified: bool = False):
        mode = request.headers.get("x-test-auth", "")
        if mode == "verified":
            return user_verified
        if mode == "unverified":
            if require_verified:
                raise HTTPException(403, "Verify your email first.")
            return user_unverified
        if require_verified:
            raise HTTPException(401, "Sign in required")
        return None

    async def fake_load(_account: AccountSession) -> dict[str, Any]:
        return json.loads(json.dumps(store))

    async def fake_save(
        _account: AccountSession,
        doc: dict[str, Any],
        expected_version: Any = None,
        expected_owner: Any = None,
    ) -> dict[str, Any]:
        if expected_version is not None and int(expected_version) != int(store["version"]):
            raise HTTPException(409, "Workspace conflict")
        store["document"] = json.loads(json.dumps(doc))
        store["version"] += 1
        return json.loads(json.dumps(store))

    crawl_state = {"round": 1}

    async def fake_collect(url: str, max_urls: int = 30) -> tuple[list[SitemapEntry], list[str]]:
        if crawl_state["round"] == 1:
            return (
                [
                    SitemapEntry(loc=f"{url}/services/audit", title="Audit", price_hint="$500"),
                    SitemapEntry(loc=f"{url}/services/advisory", title="Advisory", price_hint=""),
                ],
                [f"{url}/sitemap.xml"],
            )
        return (
            [
                SitemapEntry(loc=f"{url}/services/audit", title="Audit", price_hint="$650"),
                SitemapEntry(loc=f"{url}/services/advisory", title="Advisory", price_hint=""),
                SitemapEntry(loc=f"{url}/services/ai-ops", title="AI Ops Sprint", price_hint=""),
            ],
            [f"{url}/sitemap.xml"],
        )

    monkeypatch.setattr("src.api.intel.resolve_account", fake_resolve)
    monkeypatch.setattr("src.api.intel.load_workspace", fake_load)
    monkeypatch.setattr("src.api.intel.save_workspace", fake_save)
    monkeypatch.setattr("src.api.intel.collect_entries", fake_collect)

    client = TestClient(app)

    # 1. Signed out -> 401
    r401 = client.post("/api/v1/competitors/check", json={})
    assert r401.status_code == 401

    # 2. Unverified email -> 403
    r403 = client.post(
        "/api/v1/competitors/check",
        json={},
        headers={"x-test-auth": "unverified"},
    )
    assert r403.status_code == 403

    # 3. Version conflict -> 409
    r409 = client.post(
        "/api/v1/competitors/check",
        json={"expected_version": 999},
        headers={"x-test-auth": "verified"},
    )
    assert r409.status_code == 409

    # 4. First check -> baseline saved, version 4
    r1 = client.post(
        "/api/v1/competitors/check",
        json={"expected_version": 3},
        headers={"x-test-auth": "verified"},
    )
    assert r1.status_code == 200, r1.text
    d1 = r1.json()
    assert d1["version"] == 4
    assert d1["competitors"][0]["status"] == "first_check"
    assert "First check: Muse now knows 2 of their pages." in d1["competitors"][0]["summary"]

    # 5. Second check -> real diff (1 new page, 1 price change), version 5
    crawl_state["round"] = 2
    r2 = client.post(
        "/api/v1/competitors/check",
        json={"expected_version": 4},
        headers={"x-test-auth": "verified"},
    )
    assert r2.status_code == 200, r2.text
    d2 = r2.json()
    assert d2["version"] == 5
    assert d2["competitors"][0]["status"] == "changed"
    assert d2["competitors"][0]["counts"] == {
        "new_listing": 1,
        "removed_listing": 0,
        "price_change": 1,
    }
    assert d2["top_insight"]["title"] == "Summit Growth added 1 page"

    # 6. Scan guard rate limit -> 429 with Retry-After
    monkeypatch.setenv("SCANS_PER_VISITOR_PER_10_MIN", "1")
    monkeypatch.setenv("SCAN_CACHE_SECONDS", "0")
    get_settings.cache_clear()
    scan_guard.reset()
    try:
        ok = client.post(
            "/api/v1/competitors/check",
            json={"expected_version": 5},
            headers={"x-test-auth": "verified"},
        )
        assert ok.status_code == 200
        limited = client.post(
            "/api/v1/competitors/check",
            json={"expected_version": 6},
            headers={"x-test-auth": "verified"},
        )
        assert limited.status_code == 429
        assert int(limited.headers.get("Retry-After", "0")) >= 1
    finally:
        get_settings.cache_clear()
        scan_guard.reset()


@pytest.fixture
def own_digest_server(monkeypatch: pytest.MonkeyPatch):
    """Real FastAPI server on 127.0.0.1 with fixture account and rotating fake sitemap pages."""
    scan_guard.reset()
    store: dict[str, Any] = {
        "version": 1,
        "owner_id": "dg-u1",
        "document": {
            "onboarding": {
                "business_name": "n Plus Alpha Consulting",
                "business_type": "services",
                "website_url": "https://nplusalpha.test",
                "shop_urls": ["https://nplusalpha.test"],
                "completed_at": "2026-11-20T10:00:00Z",
                "competitors": [
                    {"name": "Summit Growth", "url": "https://summit.test", "selected": True}
                ],
            },
            "preferences": {
                "competitor_entries": [
                    {"name": "Summit Growth", "url": "https://summit.test", "selected": True}
                ]
            },
        },
    }
    account = AccountSession(
        user_id="dg-u1",
        email="founder@nplusalpha.test",
        email_verified=True,
        access_token="tok-dg",
        session_id=None,
    )

    async def fake_resolve(request: Any, _response: Any = None, require_verified: bool = False):
        if request.cookies.get("muse_e2e_user") == "dg-u1":
            return account
        if require_verified:
            raise HTTPException(401, "Sign in required")
        return None

    async def fake_load(_session: AccountSession) -> dict[str, Any]:
        return json.loads(json.dumps(store))

    async def fake_save(
        _session: AccountSession,
        doc: dict[str, Any],
        expected_version: Any = None,
        expected_owner: Any = None,
    ) -> dict[str, Any]:
        if expected_version is not None and int(expected_version) != int(store["version"]):
            raise HTTPException(409, "Workspace conflict")
        store["document"] = json.loads(json.dumps(doc))
        store["version"] += 1
        return json.loads(json.dumps(store))

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

    calls = {"n": 0}

    async def fake_collect(url: str, max_urls: int = 30) -> tuple[list[SitemapEntry], list[str]]:
        calls["n"] += 1
        if calls["n"] == 1:
            return (
                [
                    SitemapEntry(
                        loc=f"{url}/services/growth-audit",
                        title="Growth Audit",
                        price_hint="$500",
                    ),
                    SitemapEntry(
                        loc=f"{url}/services/workshops",
                        title="Team Workshops",
                        price_hint="",
                    ),
                ],
                [f"{url}/sitemap.xml"],
            )
        return (
            [
                SitemapEntry(
                    loc=f"{url}/services/growth-audit",
                    title="Growth Audit",
                    price_hint="$650",
                ),
                SitemapEntry(
                    loc=f"{url}/services/workshops",
                    title="Team Workshops",
                    price_hint="",
                ),
                SitemapEntry(
                    loc=f"{url}/services/ai-roadmap",
                    title="AI Roadmap Sprint",
                    price_hint="$1200",
                ),
            ],
            [f"{url}/sitemap.xml"],
        )

    monkeypatch.setenv("DEMO_MODE", "true")
    monkeypatch.setenv("ACCOUNTS_REQUIRED", "true")
    monkeypatch.setenv("META_MODEL_API_KEY", "")
    monkeypatch.setenv("DEMO_KEY", "")
    monkeypatch.setenv("SCAN_CACHE_SECONDS", "0")
    get_settings.cache_clear()

    fakes = {
        "resolve_account": fake_resolve,
        "load_workspace": fake_load,
        "save_workspace": fake_save,
        "snapshot": fake_snapshot,
    }
    for mod_name in (
        "src.api.accounts",
        "src.api.intel",
        "src.api.digest_email",
        "src.api.seller_memory",
        "src.services.accounts",
        "src.services.digest_preview",
    ):
        mod = importlib.import_module(mod_name)
        for attr, fn in fakes.items():
            if hasattr(mod, attr):
                monkeypatch.setattr(mod, attr, fn)
    monkeypatch.setattr("src.api.intel.collect_entries", fake_collect)

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
        get_settings.cache_clear()
        scan_guard.reset()


def test_own_digest_competitor_checks_e2e(own_digest_server: tuple[str, dict[str, int]]) -> None:
    """Chromium E2E at 375px and 1440px: own digest two-check diff + sample digest unchanged."""
    pw_python = _find_playwright_python()
    if pw_python is None:
        pytest.skip("Playwright Python runtime unavailable")

    from tests.e2e_helpers import with_cpu_throttle

    base_url, calls = own_digest_server

    script = with_cpu_throttle(
        f"""
        import json
        from playwright.sync_api import sync_playwright

        BASE = {base_url!r}

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            try:
                # 1. Own workspace at 1440px: initial state -> Check 1 (baseline) -> Check 2 (diff)
                ctx = browser.new_context(viewport={{"width": 1440, "height": 900}})
                ctx.add_cookies([{{"name": "muse_e2e_user", "value": "dg-u1", "url": BASE}}])
                page = ctx.new_page()
                page.goto(BASE + "/digest", wait_until="domcontentloaded")
                page.wait_for_selector("#dgCheckNowBtn:not([hidden])", timeout=15000)

                body_before = page.locator("main").inner_text()
                assert "Not checked yet" in body_before, body_before
                assert "Queued for your scheduled digest updates" not in body_before
                assert "Canonical preview topics" not in body_before
                assert "What to include" in body_before
                assert "Watching 1" not in page.locator("#dgHeroTitle").inner_text()
                assert (
                    page.locator('#digestDraftForm input[name="draftShop"]').first.input_value()
                    == "https://summit.test"
                )
                assert not page.evaluate(
                    "document.documentElement.scrollWidth > window.innerWidth"
                )

                # First check -> baseline
                with page.expect_response(
                    lambda r: r.url.endswith("/api/v1/competitors/check")
                    and r.request.method == "POST",
                    timeout=15000,
                ):
                    page.locator("#dgCheckNowBtn").click()
                page.wait_for_function(
                    "() => (document.querySelector('#dgCompetitors')?.textContent || '')"
                    ".includes('First check: Muse now knows 2 of their pages')",
                    timeout=15000,
                )
                hero_first = page.locator("#dgHeroTitle").inner_text()
                assert "Baseline saved for 1 competitor" in hero_first, hero_first

                # Second check -> real diff (new page + price change)
                with page.expect_response(
                    lambda r: r.url.endswith("/api/v1/competitors/check")
                    and r.request.method == "POST",
                    timeout=15000,
                ):
                    page.locator("#dgCheckNowBtn").click()
                page.wait_for_function(
                    "() => (document.querySelector('#dgHeroTitle')?.textContent || '')"
                    ".includes('Summit Growth added 1 page')",
                    timeout=15000,
                )
                comp_txt = page.locator("#dgCompetitors").inner_text()
                assert "AI Roadmap Sprint" in comp_txt, comp_txt
                assert "$500 to $650" in comp_txt, comp_txt
                assert "Queued" not in comp_txt
                assert not page.evaluate(
                    "document.documentElement.scrollWidth > window.innerWidth"
                )
                ctx.close()

                # 2. Mobile 375px own workspace (reads saved check from workspace, no overflow)
                ctx_m = browser.new_context(viewport={{"width": 375, "height": 844}})
                ctx_m.add_cookies([{{"name": "muse_e2e_user", "value": "dg-u1", "url": BASE}}])
                pm = ctx_m.new_page()
                pm.goto(BASE + "/digest", wait_until="domcontentloaded")
                pm.wait_for_function(
                    "() => (document.querySelector('#dgHeroTitle')?.textContent || '')"
                    ".includes('Summit Growth added 1 page')",
                    timeout=15000,
                )
                assert not pm.evaluate("document.documentElement.scrollWidth > window.innerWidth")
                ctx_m.close()

                # 3. Sample digest unchanged at 375px and 1440px (no Check now button)
                for width in (375, 1440):
                    cs = browser.new_context(viewport={{"width": width, "height": 844}})
                    ps = cs.new_page()
                    ps.goto(BASE + "/digest?workspace=sample", wait_until="domcontentloaded")
                    ps.wait_for_function(
                        "() => (document.querySelector('#digestStatus')?.textContent || '')"
                        ".includes('Sample shop')",
                        timeout=15000,
                    )
                    assert ps.locator("#dgCheckNowBtn").is_hidden()
                    assert "SikhiArt.com" in ps.locator("#dgCompetitors").inner_text()
                    assert not ps.evaluate(
                        "document.documentElement.scrollWidth > window.innerWidth"
                    )
                    cs.close()
            finally:
                browser.close()
        print(json.dumps({{"status": "ok"}}))
        """
    )

    proc = subprocess.run(
        [pw_python, "-c", script],
        capture_output=True,
        text=True,
        check=False,
        timeout=120,
    )
    assert proc.returncode == 0, f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
    assert calls["n"] == 2
