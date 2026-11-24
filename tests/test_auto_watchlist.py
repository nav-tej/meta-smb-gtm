"""Unit, route, and PGlite SQL tests for automatic weekly watchlist checks."""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi import HTTPException, Request, Response
from fastapi.testclient import TestClient

from src.api import daily_brief as brief_api
from src.api import intel as intel_api
from src.api.main import app
from src.config import get_settings
from src.models.intel import SitemapEntry
from src.services import daily_brief as brief_service
from src.services import scan_guard, watchlist_store
from src.services.accounts import AccountSession


def test_watchlist_sql_on_local_postgres() -> None:
    pglite = os.environ.get("BILLING_PGLITE_DIR", "")
    node = shutil.which("node")
    if not node or not pglite or not Path(pglite, "dist/index.js").is_file():
        pytest.skip("Set BILLING_PGLITE_DIR to a local @electric-sql/pglite install to run")
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        [node, str(root / "tests/watchlist_sql.mjs")],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr[-3000:]
    assert "watchlist SQL checks passed" in result.stdout


@pytest.fixture
def watchlist_harness(
    _never_use_real_meta_key: None, monkeypatch: pytest.MonkeyPatch
) -> SimpleNamespace:
    scan_guard.reset()
    monkeypatch.setenv("DEMO_MODE", "true")
    monkeypatch.setenv("META_MODEL_API_KEY", "")
    monkeypatch.setenv("DEMO_KEY", "")
    monkeypatch.setenv("SCANS_PER_VISITOR_PER_10_MIN", "0")
    monkeypatch.setenv("WATCHLIST_AUTO_CHECK_ENABLED", "false")
    monkeypatch.setenv("WATCHLIST_AUTO_CHECK_ACCOUNTS_PER_RUN", "10")
    get_settings.cache_clear()

    def no_network(*args: Any, **kwargs: Any) -> None:
        pytest.fail("Watchlist test attempted real outbound HTTP")

    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", no_network)
    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", no_network)

    state: dict[str, Any] = {
        "version": 4,
        "doc": {
            "onboarding": {
                "business_name": "Northstar Advisory",
                "business_type": "services",
                "completed_at": "2026-11-20T12:00:00Z",
                "competitors": [{"name": "Rival Alpha", "url": "https://rival-alpha.example"}],
            },
            "preferences": {
                "goal": "Grow inquiries",
                "access": {"minutes_per_week": 60, "channels": ["website", "linkedin"]},
                "competitor_checks": {
                    "https://rival-alpha.example": {
                        "name": "Rival Alpha",
                        "url": "https://rival-alpha.example",
                        "status": "first_check",
                        "checked_at": "2026-11-20T10:00:00Z",
                        "summary": "First check: Muse now knows 1 of their pages.",
                        "error": "",
                        "pages": [
                            {
                                "loc": "https://rival-alpha.example/services",
                                "title": "Services",
                                "price_hint": "$200",
                                "lastmod": "2026-11-19",
                            }
                        ],
                    }
                },
            },
            "outcomes": [],
        },
        "table_checks": {},
        "schedule": {
            "paused": False,
            "next_check_at": "2026-11-30T13:00:00Z",
            "last_auto_check_at": None,
        },
    }

    verified = AccountSession(
        user_id="11111111-1111-4111-8111-111111111111",
        email="owner@northstar.test",
        email_verified=True,
        access_token="offline",
        session_id=None,
    )
    unverified = AccountSession(
        user_id="22222222-2222-4222-8222-222222222222",
        email="unverified@northstar.test",
        email_verified=False,
        access_token="offline",
        session_id=None,
    )

    async def fake_resolve(
        request: Request, response: Response, require_verified: bool = False
    ) -> AccountSession | None:
        auth = request.headers.get("X-Test-Auth", "")
        if auth == "verified":
            return verified
        if auth == "unverified":
            if require_verified:
                raise HTTPException(403, "Verify your email first")
            return unverified
        if require_verified:
            raise HTTPException(401, "Sign in required")
        return None

    async def fake_load(account: AccountSession) -> dict[str, Any]:
        return {
            "document": deepcopy(state["doc"]),
            "version": state["version"],
            "owner_id": account.user_id,
        }

    async def fake_save(
        account: AccountSession,
        doc: dict[str, Any],
        *,
        expected_version: int | None = None,
        expected_owner: str | None = None,
    ) -> dict[str, Any]:
        if expected_version is not None and expected_version != state["version"]:
            raise HTTPException(409, "Version conflict")
        state["doc"] = deepcopy(doc)
        state["version"] += 1
        return {
            "document": deepcopy(state["doc"]),
            "version": state["version"],
            "owner_id": account.user_id,
        }

    async def fake_collect(url: str, max_urls: int = 30) -> tuple[list[SitemapEntry], list[str]]:
        return (
            [
                SitemapEntry(
                    loc="https://rival-alpha.example/services",
                    title="Services",
                    price_hint="$200",
                )
            ],
            [f"{url}/sitemap.xml"],
        )

    async def fake_get_checks(
        user_id: str, *, with_snapshots: bool = False, raise_on_error: bool = False
    ) -> dict[str, Any] | None:
        if not watchlist_store.auto_check_enabled():
            return None
        checks_out: dict[str, dict[str, Any]] = {}
        for url, row in state["table_checks"].items():
            entry = deepcopy(row)
            if not with_snapshots:
                entry.pop("pages", None)
            checks_out[url] = entry
        return {
            "enabled": True,
            "checks": checks_out,
            "schedule": deepcopy(state["schedule"]),
        }

    async def fake_save_checks(
        user_id: str,
        *,
        source: str,
        checks: list[dict[str, Any]],
        keep_urls: list[str],
    ) -> dict[str, Any]:
        keep_set = set(keep_urls)
        for row in checks:
            site_url = row["site_url"]
            entry = dict(row.get("result") or {})
            entry.update(
                {
                    "url": site_url,
                    "status": row["status"],
                    "source": source,
                    "checked_at": row["checked_at"],
                    "summary": row["summary"],
                    "error": row["error"],
                    "partial": row["partial"],
                    "pages": (row.get("snapshot") or {}).get("pages", []),
                }
            )
            state["table_checks"][site_url] = entry
        state["table_checks"] = {k: v for k, v in state["table_checks"].items() if k in keep_set}
        state["schedule"]["next_check_at"] = "2026-11-30T13:00:00Z"
        if source == "auto":
            state["schedule"]["last_auto_check_at"] = "2026-11-23T13:00:00Z"
        return deepcopy(state["schedule"])

    async def fake_set_paused(user_id: str, paused: bool) -> dict[str, Any]:
        state["schedule"]["paused"] = bool(paused)
        return deepcopy(state["schedule"])

    save_ws_mock = AsyncMock(side_effect=fake_save)
    get_checks_mock = AsyncMock(side_effect=fake_get_checks)
    save_checks_mock = AsyncMock(side_effect=fake_save_checks)
    set_paused_mock = AsyncMock(side_effect=fake_set_paused)
    collect_mock = AsyncMock(side_effect=fake_collect)

    monkeypatch.setattr(intel_api, "resolve_account", fake_resolve)
    monkeypatch.setattr(intel_api, "load_workspace", fake_load)
    monkeypatch.setattr(intel_api, "save_workspace", save_ws_mock)
    monkeypatch.setattr(intel_api, "collect_entries", collect_mock)
    monkeypatch.setattr(brief_api, "resolve_account", fake_resolve)
    monkeypatch.setattr(brief_service, "load_workspace", fake_load)
    monkeypatch.setattr(watchlist_store, "get_checks", get_checks_mock)
    monkeypatch.setattr(watchlist_store, "save_checks", save_checks_mock)
    monkeypatch.setattr(watchlist_store, "set_paused", set_paused_mock)

    return SimpleNamespace(
        client=TestClient(app),
        state=state,
        save_ws_mock=save_ws_mock,
        get_checks_mock=get_checks_mock,
        save_checks_mock=save_checks_mock,
        set_paused_mock=set_paused_mock,
        collect_mock=collect_mock,
    )


def test_flag_off_keeps_exact_legacy_behavior(watchlist_harness: SimpleNamespace) -> None:
    # Cron and pause routes are 404 when flag is off
    assert watchlist_harness.client.get("/api/v1/watchlist/run").status_code == 404
    assert (
        watchlist_harness.client.post(
            "/api/v1/competitors/auto-check",
            headers={"X-Test-Auth": "verified"},
            json={"paused": True},
        ).status_code
        == 404
    )

    # GET /competitors/checks returns legacy checks with enabled=False and private, no-store
    got = watchlist_harness.client.get(
        "/api/v1/competitors/checks", headers={"X-Test-Auth": "verified"}
    )
    assert got.status_code == 200
    assert "private" in got.headers["cache-control"]
    assert "no-store" in got.headers["cache-control"]
    assert got.json()["auto_check"]["enabled"] is False
    assert "https://rival-alpha.example" in got.json()["competitor_checks"]
    watchlist_harness.get_checks_mock.assert_not_awaited()

    # Button saves to workspace and bumps version (legacy behavior)
    res = watchlist_harness.client.post(
        "/api/v1/competitors/check",
        headers={"X-Test-Auth": "verified"},
        json={"expected_version": 4},
    )
    assert res.status_code == 200
    assert res.json()["version"] == 5
    watchlist_harness.save_ws_mock.assert_awaited_once()
    watchlist_harness.save_checks_mock.assert_not_awaited()

    # Own /today brief says manual wording, never "once a week"
    brief = watchlist_harness.client.get(
        "/api/v1/daily-brief?workspace=own", headers={"X-Test-Auth": "verified"}
    )
    assert brief.status_code == 200
    note = brief.json()["overnight_note"]
    assert "Check now (free) on your digest" in note
    assert "once a week" not in note.lower()


def test_flag_on_button_saves_to_table_without_workspace_write_and_uses_legacy_fallback(
    watchlist_harness: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("WATCHLIST_AUTO_CHECK_ENABLED", "true")
    get_settings.cache_clear()

    # Table is initially empty, but legacy workspace has the previous baseline for rival-alpha.
    # Pressing Check now should diff against legacy baseline (-> unchanged, not first_check),
    # save to watchlist_store, and NEVER call save_workspace!
    res = watchlist_harness.client.post(
        "/api/v1/competitors/check",
        headers={"X-Test-Auth": "verified"},
        json={"expected_version": 4},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["version"] == 4  # unchanged — no workspace write!
    assert body["competitors"][0]["status"] == "unchanged"
    assert body["competitors"][0]["source"] == "manual"
    assert body["auto_check"]["enabled"] is True
    watchlist_harness.save_ws_mock.assert_not_awaited()
    watchlist_harness.save_checks_mock.assert_awaited_once()

    # Stale expected_version still returns 409 before fetching
    stale = watchlist_harness.client.post(
        "/api/v1/competitors/check",
        headers={"X-Test-Auth": "verified"},
        json={"expected_version": 1},
    )
    assert stale.status_code == 409

    # GET /competitors/checks is 401 signed out, 403 unverified, 200 verified
    assert watchlist_harness.client.get("/api/v1/competitors/checks").status_code == 401
    assert (
        watchlist_harness.client.get(
            "/api/v1/competitors/checks", headers={"X-Test-Auth": "unverified"}
        ).status_code
        == 403
    )
    got = watchlist_harness.client.get(
        "/api/v1/competitors/checks", headers={"X-Test-Auth": "verified"}
    )
    assert got.status_code == 200
    assert "private" in got.headers["cache-control"]
    assert "no-store" in got.headers["cache-control"]
    assert got.json()["auto_check"]["enabled"] is True
    assert got.json()["competitor_checks"]["https://rival-alpha.example"]["status"] == "unchanged"

    # Own /today brief says "once a week" when flag is on and not paused
    brief = watchlist_harness.client.get(
        "/api/v1/daily-brief?workspace=own", headers={"X-Test-Auth": "verified"}
    )
    assert brief.status_code == 200
    assert brief.json()["overnight_note"].startswith("Muse checks your watchlist once a week.")

    # Pause route toggles paused=True -> brief reverts to manual wording
    p = watchlist_harness.client.post(
        "/api/v1/competitors/auto-check",
        headers={"X-Test-Auth": "verified"},
        json={"paused": True},
    )
    assert p.status_code == 200
    assert p.json()["auto_check"]["paused"] is True
    brief_paused = watchlist_harness.client.get(
        "/api/v1/daily-brief?workspace=own", headers={"X-Test-Auth": "verified"}
    )
    assert "Check now (free) on your digest" in brief_paused.json()["overnight_note"]
    get_settings.cache_clear()


def test_cron_auth_strict_and_runner_handles_errors_budget_and_privacy(
    watchlist_harness: SimpleNamespace,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    monkeypatch.setenv("WATCHLIST_AUTO_CHECK_ENABLED", "true")
    monkeypatch.setenv("WATCHLIST_AUTO_CHECK_ACCOUNTS_PER_RUN", "10")
    get_settings.cache_clear()

    # Empty CRON_SECRET -> 401 even with vercel-cron user-agent
    monkeypatch.delenv("CRON_SECRET", raising=False)
    r_empty = watchlist_harness.client.get(
        "/api/v1/watchlist/run",
        headers={"Authorization": "Bearer ", "User-Agent": "vercel-cron/1.0"},
    )
    assert r_empty.status_code == 401

    monkeypatch.setenv("CRON_SECRET", "super-secret-token")
    # Missing Authorization -> 401
    assert watchlist_harness.client.get("/api/v1/watchlist/run").status_code == 401
    # Wrong Authorization -> 401
    assert (
        watchlist_harness.client.get(
            "/api/v1/watchlist/run", headers={"Authorization": "Bearer wrong-token"}
        ).status_code
        == 401
    )
    # User-agent alone -> 401 (no user-agent fallback!)
    assert (
        watchlist_harness.client.get(
            "/api/v1/watchlist/run", headers={"User-Agent": "vercel-cron/1.0"}
        ).status_code
        == 401
    )

    # Seed 4 claimed sellers:
    # 1. unconfirmed email -> skipped without crawling, pushed a week out
    # 2. raises error during workspace load -> counted in errors, does not stop seller 3
    # 3. confirmed with 1 competitor -> checked and saved with source="auto"
    # 4. confirmed with 0 competitors -> pushed a week out
    u_unconf = "aaaa1111-1111-4111-8111-111111111111"
    u_boom = "bbbb2222-2222-4222-8222-222222222222"
    u_ok = "cccc3333-3333-4333-8333-333333333333"
    u_empty = "dddd4444-4444-4444-8444-444444444444"

    claim_mock = AsyncMock(
        return_value=[
            {"user_id": u_unconf, "onboarding": {}, "preferences": {}},
            {"user_id": u_boom, "onboarding": {}, "preferences": {}},
            {
                "user_id": u_ok,
                "onboarding": {
                    "business_name": "Secret Seller Co",
                    "competitors": [{"name": "Secret Rival", "url": "https://secret-rival.test"}],
                },
                "preferences": {},
            },
            {"user_id": u_empty, "onboarding": {"competitors": []}, "preferences": {}},
        ]
    )

    async def fake_confirmed(uid: str) -> bool:
        return uid != u_unconf

    async def fake_load_doc(uid: str) -> dict[str, Any] | None:
        if uid == u_boom:
            raise RuntimeError("transient db error")
        return None

    monkeypatch.setattr(watchlist_store, "claim_due", claim_mock)
    monkeypatch.setattr(
        watchlist_store, "is_email_confirmed", AsyncMock(side_effect=fake_confirmed)
    )
    monkeypatch.setattr(
        watchlist_store, "load_workspace_document", AsyncMock(side_effect=fake_load_doc)
    )

    with caplog.at_level(logging.INFO):
        ok = watchlist_harness.client.get(
            "/api/v1/watchlist/run",
            headers={"Authorization": "Bearer super-secret-token"},
        )
    assert ok.status_code == 200
    data = ok.json()
    assert data["sellers_checked"] == 2  # u_ok + u_empty
    assert data["sites_checked"] == 1  # secret-rival.test
    assert data["skipped_unconfirmed"] == 1
    assert data["errors"] == 1
    assert data["stopped_for_budget"] is False

    # Response and logs contain NO seller IDs, names, or URLs
    combined = ok.text + "\n" + "\n".join(r.getMessage() for r in caplog.records)
    for secret_str in (u_unconf, u_boom, u_ok, u_empty, "Secret Seller Co", "secret-rival.test"):
        assert secret_str not in combined

    # Time budget stops processing before claiming/checking remaining sellers
    monkeypatch.setattr(intel_api, "WATCHLIST_RUN_BUDGET_SECONDS", 0.0)
    budget_res = watchlist_harness.client.get(
        "/api/v1/watchlist/run",
        headers={"Authorization": "Bearer super-secret-token"},
    )
    assert budget_res.status_code == 200
    assert budget_res.json()["stopped_for_budget"] is True
    assert budget_res.json()["sellers_checked"] == 0
    get_settings.cache_clear()


# ---------------------------------------------------------------------------
# Review fixes (Nov 24): Auth lookup error, per-site timeout & worst-case
# budget, failed table read during check, and size-safe row trimming
# ---------------------------------------------------------------------------

import asyncio  # noqa: E402
import json  # noqa: E402

from src.clients.supabase import SupabaseError  # noqa: E402
from src.services.competitor_checks import (  # noqa: E402
    PER_SITE_CRAWL_TIMEOUT_SECONDS,
    run_watchlist_checks,
)


@pytest.mark.asyncio
async def test_auth_lookup_error_raises_and_never_prunes_rows(
    watchlist_harness: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    # 1. watchlist_store.is_email_confirmed propagates SupabaseError instead of returning False
    class FailingSupabase:
        async def auth(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
            raise SupabaseError(503, "Auth unavailable")

    monkeypatch.setattr(watchlist_store, "get_supabase_client", lambda: FailingSupabase())
    with pytest.raises(SupabaseError):
        await watchlist_store.is_email_confirmed("11111111-1111-4111-8111-111111111111")

    # 2. In GET /api/v1/watchlist/run: Auth error counts errors==1 and leaves saved rows untouched
    monkeypatch.setenv("WATCHLIST_AUTO_CHECK_ENABLED", "true")
    monkeypatch.setenv("CRON_SECRET", "review-secret")
    get_settings.cache_clear()

    uid = "11111111-1111-4111-8111-111111111111"
    watchlist_harness.state["table_checks"]["https://rival-alpha.example"] = {
        "url": "https://rival-alpha.example",
        "status": "unchanged",
        "checked_at": "2026-11-22T10:00:00Z",
        "summary": "Saved baseline",
    }
    monkeypatch.setattr(
        watchlist_store,
        "claim_due",
        AsyncMock(return_value=[{"user_id": uid, "onboarding": {}, "preferences": {}}]),
    )
    monkeypatch.setattr(
        watchlist_store,
        "is_email_confirmed",
        AsyncMock(side_effect=SupabaseError(503, "Auth down")),
    )

    res = watchlist_harness.client.get(
        "/api/v1/watchlist/run",
        headers={"Authorization": "Bearer review-secret"},
    )
    assert res.status_code == 200
    assert res.json()["errors"] == 1
    assert res.json()["skipped_unconfirmed"] == 0
    watchlist_harness.save_checks_mock.assert_not_awaited()
    assert "https://rival-alpha.example" in watchlist_harness.state["table_checks"]
    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_per_site_crawl_timeout_and_worst_case_run_budget() -> None:
    scan_guard.reset()

    async def hanging_collect(url: str, max_urls: int = 30) -> tuple[list[SitemapEntry], list[str]]:
        await asyncio.sleep(5.0)
        return [], []

    results, _stored, _pages = await run_watchlist_checks(
        [{"name": "Slow Rival", "url": "https://slow-rival.example"}],
        {},
        checked_at="2026-11-24T00:00:00Z",
        scan_url_fn=lambda u: (u, "slow-rival.example", False),
        collect_entries_fn=hanging_collect,
        source="auto",
        per_site_timeout=0.05,
    )
    assert len(results) == 1
    assert results[0]["status"] == "error"
    assert results[0]["error_kind"] == "timeout"
    assert "took too long" in results[0]["error"].lower()

    # Budget leaves room for one worst-case seller (6 sites x per-site timeout) before 280s
    assert PER_SITE_CRAWL_TIMEOUT_SECONDS <= 25.0
    assert (
        intel_api.WATCHLIST_RUN_BUDGET_SECONDS + intel_api.WATCHLIST_WORST_CASE_SELLER_SECONDS
        <= 280.0
    )


def test_failed_table_read_during_check_returns_503_and_saves_nothing(
    watchlist_harness: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("WATCHLIST_AUTO_CHECK_ENABLED", "true")
    monkeypatch.setenv("CRON_SECRET", "review-secret")
    get_settings.cache_clear()

    async def failing_get_checks(
        user_id: str, *, with_snapshots: bool = False, raise_on_error: bool = False
    ) -> dict[str, Any] | None:
        if raise_on_error:
            raise SupabaseError(503, "DB read failed")
        return None

    monkeypatch.setattr(watchlist_store, "get_checks", AsyncMock(side_effect=failing_get_checks))

    # 1. Button returns 503 with plain message and saves nothing
    btn = watchlist_harness.client.post(
        "/api/v1/competitors/check",
        headers={"X-Test-Auth": "verified"},
        json={"expected_version": 4},
    )
    assert btn.status_code == 503
    assert (
        btn.json()["detail"]
        == "Muse couldn't check your watchlist right now. Try again in a few minutes."
    )
    watchlist_harness.save_checks_mock.assert_not_awaited()
    watchlist_harness.save_ws_mock.assert_not_awaited()

    # 2. Scheduled run counts errors==1 and saves nothing
    uid = "11111111-1111-4111-8111-111111111111"
    monkeypatch.setattr(
        watchlist_store,
        "claim_due",
        AsyncMock(
            return_value=[
                {
                    "user_id": uid,
                    "onboarding": {
                        "competitors": [{"name": "Rival", "url": "https://rival-alpha.example"}]
                    },
                    "preferences": {},
                }
            ]
        ),
    )
    monkeypatch.setattr(watchlist_store, "is_email_confirmed", AsyncMock(return_value=True))
    monkeypatch.setattr(watchlist_store, "load_workspace_document", AsyncMock(return_value=None))

    run = watchlist_harness.client.get(
        "/api/v1/watchlist/run",
        headers={"Authorization": "Bearer review-secret"},
    )
    assert run.status_code == 200
    assert run.json()["errors"] == 1
    assert run.json()["sellers_checked"] == 0
    watchlist_harness.save_checks_mock.assert_not_awaited()
    get_settings.cache_clear()


def test_oversized_30_pages_and_45_changes_trim_to_size_safe_rows() -> None:
    def long_url(prefix: str, idx: int) -> str:
        base = f"https://longstore.example/{prefix}/{idx}/"
        return base + ("x" * (500 - len(base)))

    long_title = "T" * 140
    pages = [
        {
            "loc": long_url("p", i),
            "title": long_title,
            "price_hint": "$199.99",
            "lastmod": "2026-11-23",
        }
        for i in range(30)
    ]
    result_item = {
        "name": "Long Store",
        "url": "https://longstore.example",
        "status": "changed",
        "checked_at": "2026-11-24T00:00:00Z",
        "summary": "15 new pages, 15 removed pages, 15 price changes.",
        "error": "",
        "partial": False,
        "new_pages": [
            {"loc": long_url("new", i), "title": long_title, "price_hint": "$199.99"}
            for i in range(15)
        ],
        "removed_pages": [
            {"loc": long_url("rem", i), "title": long_title, "price_hint": "$149.99"}
            for i in range(15)
        ],
        "price_changes": [
            {
                "loc": long_url("prc", i),
                "title": long_title,
                "old_price": "$149.99",
                "new_price": "$199.99",
            }
            for i in range(15)
        ],
    }
    assert len(json.dumps(result_item).encode("utf-8")) > watchlist_store.MAX_RESULT_JSON_BYTES
    stored = {
        "pages": pages,
        "checked_at": "2026-11-24T00:00:00Z",
        "partial": False,
    }
    rows = watchlist_store.build_db_check_rows([result_item], {"https://longstore.example": stored})
    assert len(rows) == 1
    result_bytes = len(json.dumps(rows[0]["result"]).encode("utf-8"))
    snapshot_bytes = len(json.dumps(rows[0]["snapshot"]).encode("utf-8"))
    assert result_bytes <= watchlist_store.MAX_RESULT_JSON_BYTES <= 32768
    assert snapshot_bytes <= watchlist_store.MAX_SNAPSHOT_JSON_BYTES <= 65536
