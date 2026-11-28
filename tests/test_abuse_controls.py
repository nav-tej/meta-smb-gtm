"""Offline abuse regressions: no live providers, Auth, cloud database or email delivery."""

from __future__ import annotations

import asyncio
import copy
import hashlib
import os
import shutil
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi import HTTPException, Request
from fastapi.testclient import TestClient

from src.api.main import app
from src.config import get_settings
from src.models.intel import SitemapEntry
from src.services import accounts, credits, scan_guard, usage_meter
from src.utils.sitemap import SitemapError

ROOT = Path(__file__).resolve().parents[1]


def settings(monkeypatch: pytest.MonkeyPatch, **values: Any) -> None:
    for key, value in values.items():
        monkeypatch.setenv(
            key.upper(), str(value).lower() if isinstance(value, bool) else str(value)
        )
    get_settings.cache_clear()


@pytest.fixture(autouse=True)
def clean_guards() -> Any:
    scan_guard.reset()
    accounts.reset_email_throttle()
    usage_meter.clear_request_context()
    yield
    scan_guard.reset()
    accounts.reset_email_throttle()
    usage_meter.clear_request_context()


def request(ip: str = "203.0.113.8") -> Request:
    return Request({"type": "http", "headers": [(b"x-forwarded-for", ip.encode())]})


def test_refund_copied_handles_cannot_mint_credits() -> None:
    hold = credits.reserve("anon:fixture")
    duplicate = copy.copy(hold)
    credits.refund(hold, "fixture")
    credits.refund(duplicate, "replay")
    assert credits.balance("anon:fixture") == get_settings().trial_runs


def test_completed_hold_cannot_be_refunded_by_a_copy() -> None:
    hold = credits.reserve("anon:fixture")
    duplicate = copy.copy(hold)
    credits.commit(hold)
    credits.refund(duplicate, "replay")
    assert credits.balance("anon:fixture") == get_settings().trial_runs - 1


def test_parallel_refunds_settle_one_ledger_hold() -> None:
    hold = credits.reserve("anon:fixture")
    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(lambda _: credits.refund(copy.copy(hold), "replay"), range(40)))
    assert credits.balance("anon:fixture") == get_settings().trial_runs


def test_credit_holder_capacity_never_evicts_a_spent_account(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(credits, "MAX_HOLDERS", 2)
    for owner in ("anon:first", "anon:second"):
        credits.commit(credits.reserve(owner))
    with pytest.raises(credits.CreditsUnavailableError):
        credits.reserve("anon:third")
    assert credits.balance("anon:first") == get_settings().trial_runs - 1


def test_pending_credit_holds_are_bounded(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(credits, "MAX_PENDING_HOLDS", 2)
    credits.reserve("anon:first")
    credits.reserve("anon:first")
    with pytest.raises(credits.CreditsUnavailableError):
        credits.reserve("anon:first")
    assert credits.balance("anon:first") == get_settings().trial_runs - 2


def test_failed_refund_write_remains_retryable(monkeypatch: pytest.MonkeyPatch) -> None:
    from contextlib import contextmanager

    hold = credits.reserve("anon:fixture")
    original = credits._locked_ledger

    @contextmanager
    def unavailable() -> Any:
        raise credits.CreditsUnavailableError("fixture unavailable")
        yield  # pragma: no cover

    monkeypatch.setattr(credits, "_locked_ledger", unavailable)
    credits.refund(hold, "fixture")
    assert hold.settled is False
    monkeypatch.setattr(credits, "_locked_ledger", original)
    credits.refund(hold, "retry")
    assert credits.balance("anon:fixture") == get_settings().trial_runs


def test_scan_rotation_cannot_evict_a_live_visitor_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    settings(monkeypatch, scans_per_visitor_per_10_min=1)
    monkeypatch.setattr(scan_guard, "MAX_VISITORS", 2)
    assert scan_guard.reserve_scans("first", 1) is None
    assert scan_guard.reserve_scans("second", 1) is None
    assert scan_guard.reserve_scans("third", 1) == 600
    assert scan_guard.reserve_scans("first", 1) is not None
    assert len(scan_guard._visits) == 2


def test_scan_capacity_recovers_only_after_old_windows_expire(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings(monkeypatch, scans_per_visitor_per_10_min=1)
    monkeypatch.setattr(scan_guard, "MAX_VISITORS", 1)
    monkeypatch.setattr(scan_guard, "_now", lambda: 0.0)
    assert scan_guard.reserve_scans("first", 1) is None
    monkeypatch.setattr(scan_guard, "_now", lambda: 600.0)
    assert scan_guard.reserve_scans("second", 1) is None
    assert len(scan_guard._visits) == 1


@pytest.mark.asyncio
async def test_identical_inflight_crawls_use_one_fetch(monkeypatch: pytest.MonkeyPatch) -> None:
    settings(monkeypatch, scan_cache_seconds=0)
    release = asyncio.Event()
    calls = 0

    async def fetch() -> Any:
        nonlocal calls
        calls += 1
        await release.wait()
        return [SitemapEntry(loc="https://shop.test/item")], []

    first = asyncio.create_task(scan_guard.crawl("https://shop.test", 20, fetch))
    second = asyncio.create_task(scan_guard.crawl("https://SHOP.test/", 20, fetch))
    await asyncio.sleep(0.02)
    release.set()
    a, b = await asyncio.gather(first, second)
    assert calls == 1
    assert a == b
    assert a[0][0] is not b[0][0]


@pytest.mark.asyncio
async def test_cancelled_scan_waiter_cannot_cancel_a_shared_crawl() -> None:
    release = asyncio.Event()
    calls = 0

    async def fetch() -> Any:
        nonlocal calls
        calls += 1
        await release.wait()
        return [], []

    a = asyncio.create_task(scan_guard.crawl("https://shop.test", 20, fetch))
    b = asyncio.create_task(scan_guard.crawl("https://shop.test", 20, fetch))
    await asyncio.sleep(0.02)
    a.cancel()
    with pytest.raises(asyncio.CancelledError):
        await a
    release.set()
    assert await b == ([], [])
    assert calls == 1


@pytest.mark.asyncio
async def test_inflight_scan_capacity_is_bounded(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(scan_guard, "MAX_INFLIGHT_CRAWLS", 1)
    release = asyncio.Event()

    async def fetch() -> Any:
        await release.wait()
        return [], []

    first = asyncio.create_task(scan_guard.crawl("https://one.test", 20, fetch))
    await asyncio.sleep(0.02)
    try:
        with pytest.raises(HTTPException) as error:
            await scan_guard.crawl("https://two.test", 20, fetch)
        assert error.value.status_code == 503
    finally:
        release.set()
        await first


@pytest.mark.asyncio
async def test_crawl_deadline_does_not_cache_a_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    settings(monkeypatch, scan_cache_seconds=900)
    monkeypatch.setattr(scan_guard, "MAX_CRAWL_SECONDS", 0.01)
    release = asyncio.Event()

    async def fetch() -> Any:
        await release.wait()
        return [], []

    try:
        with pytest.raises(SitemapError, match="in time"):
            await asyncio.wait_for(scan_guard.crawl("https://slow.test", 20, fetch), timeout=0.2)
    finally:
        release.set()
    assert scan_guard.cached_crawl("https://slow.test", 20) is None


@pytest.mark.asyncio
async def test_hosted_public_scan_reserves_whole_batch_before_fetch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings(monkeypatch, hosted_environment=True, scans_per_visitor_per_10_min=6)
    events = []

    async def reserve(kind: str, visitor: str, count: int, *args: Any) -> None:
        events.append((kind, visitor, count))

    async def fetch() -> Any:
        events.append("fetch")
        return [], []

    monkeypatch.setattr(usage_meter, "reserve_public_work", reserve)
    assert scan_guard.reserve_scans("hashed-visitor", 2) is None
    await scan_guard.crawl("https://one.test", 20, fetch)
    await scan_guard.crawl("https://two.test", 20, fetch)
    assert events == [("scan", "hashed-visitor", 2), "fetch", "fetch"]


@pytest.mark.asyncio
async def test_shared_durable_refusal_blocks_all_scan_fetches(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings(monkeypatch, hosted_environment=True, scans_per_visitor_per_10_min=6)
    calls = []

    async def denied(*args: Any, **kwargs: Any) -> None:
        raise HTTPException(429, "fixture denied", headers={"Retry-After": "600"})

    async def fetch() -> Any:
        calls.append("fetch")
        return [], []

    monkeypatch.setattr(usage_meter, "reserve_public_work", denied)
    assert scan_guard.reserve_scans("visitor", 2) is None
    with pytest.raises(HTTPException) as error:
        await scan_guard.crawl("https://one.test", 20, fetch)
    assert error.value.status_code == 429
    assert calls == []


def test_email_counter_capacity_is_bounded_without_eviction(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(accounts, "MAX_EMAIL_BUCKETS", 2)
    accounts.throttle_email_send(request(), "a@example.test", now=1.0)
    with pytest.raises(HTTPException) as error:
        accounts.throttle_email_send(request("198.51.100.1"), "b@example.test", now=1.0)
    assert error.value.status_code == 429
    assert len(accounts._email_sends) == 2
    accounts.throttle_email_send(request("198.51.100.1"), "b@example.test", now=902.0)
    assert len(accounts._email_sends) == 2


def test_parallel_email_requests_obey_one_local_address_limit() -> None:
    def attempt(_: int) -> bool:
        try:
            accounts.throttle_email_send(request(), "a@example.test", now=1.0)
            return True
        except HTTPException:
            return False

    with ThreadPoolExecutor(max_workers=12) as pool:
        accepted = list(pool.map(attempt, range(60)))
    assert sum(accepted) == accounts.EMAIL_SENDS_PER_ADDRESS


@pytest.mark.parametrize("action", ["signup", "resend", "recover"])
def test_hosted_email_admission_precedes_auth_provider(
    monkeypatch: pytest.MonkeyPatch,
    action: str,
) -> None:
    settings(monkeypatch, hosted_environment=True, app_url="https://testserver")
    events = []

    async def denied(kind: str, visitor: str, count: int, address: str | None = None) -> None:
        events.append(kind)
        assert visitor == hashlib.sha256(b"203.0.113.8").hexdigest()
        assert address == hashlib.sha256(b"a@example.test").hexdigest()
        raise HTTPException(429, "fixture denied")

    async def forbidden(*args: Any, **kwargs: Any) -> None:
        pytest.fail("Refused email must not reach Auth")

    from src.api import accounts as account_api

    monkeypatch.setattr(usage_meter, "reserve_public_work", denied)
    monkeypatch.setattr(account_api, "get_supabase_client", lambda: SimpleNamespace(auth=forbidden))
    body = {"email": "a@example.test"}
    if action == "signup":
        body["password"] = "fixture-long-password-123"
    response = TestClient(app, base_url="https://testserver").post(
        f"/api/v1/account/{action}",
        json=body,
        headers={"Origin": "https://testserver", "X-Forwarded-For": "203.0.113.8"},
    )
    assert response.status_code == 429, response.text
    assert events == ["email"]


@pytest.mark.parametrize("failure", ["limit", "backend", "invalid"])
@pytest.mark.asyncio
async def test_public_work_refuses_safely_when_shared_store_refuses(
    monkeypatch: pytest.MonkeyPatch,
    failure: str,
) -> None:
    from src.clients import supabase

    async def rpc(*args: Any, **kwargs: Any) -> Any:
        if failure == "backend":
            raise RuntimeError("fixture private provider text")
        return {
            "allowed": False,
            "status_code": 429 if failure == "limit" else 400,
            "retry_after": 3600,
            "message": "fixture private provider text",
        }

    monkeypatch.setattr(supabase, "get_supabase_client", lambda: SimpleNamespace(rpc=rpc))
    with pytest.raises(HTTPException) as error:
        await usage_meter.reserve_public_work("scan", "f" * 64, 1)
    assert error.value.status_code == (429 if failure == "limit" else 503)
    assert "private provider" not in error.value.detail
    if failure == "limit":
        assert error.value.headers["Retry-After"] == "3600"


def test_hosted_presenter_key_cannot_bypass_durable_account_metering(
    monkeypatch: pytest.MonkeyPatch,
    brief_json: dict[str, Any],
) -> None:
    settings(monkeypatch, hosted_environment=True, accounts_required=False, demo_key="fixture-key")
    from src.api.bids import get_bid_advisor_service
    from tests.conftest import build_campaign

    async def forbidden(*args: Any, **kwargs: Any) -> None:
        pytest.fail("Hosted legacy key must not reach the provider")

    app.dependency_overrides[get_bid_advisor_service] = lambda: SimpleNamespace(advise=forbidden)
    try:
        response = TestClient(app).post(
            "/api/v1/bid-advice?live=true",
            headers={"X-Demo-Key": "fixture-key"},
            json={
                "campaign": build_campaign().model_dump(mode="json"),
                "competitor_brief": brief_json,
            },
        )
    finally:
        app.dependency_overrides.pop(get_bid_advisor_service, None)
    assert response.status_code == 503


def test_abuse_migration_on_disposable_pglite() -> None:
    base = os.environ.get("BILLING_PGLITE_DIR", "")
    node = shutil.which("node")
    if not node or not Path(base, "dist/index.js").is_file():
        pytest.skip("Set BILLING_PGLITE_DIR to local PGlite")
    result = subprocess.run(
        [node, str(ROOT / "tests/abuse_controls_sql.mjs")],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr[-4000:]
    assert "abuse SQL: 14 checks passed" in result.stdout


@pytest.mark.parametrize("has_cookie", [False, True])
def test_unverified_or_missing_account_cannot_reserve_or_call_provider(
    monkeypatch: pytest.MonkeyPatch,
    brief_json: dict[str, Any],
    has_cookie: bool,
) -> None:
    settings(monkeypatch, accounts_required=True, hosted_environment=True, demo_key="fixture-key")
    from src.api.bids import get_bid_advisor_service
    from tests.conftest import build_campaign

    async def verify(*args: Any, **kwargs: Any) -> accounts.AccountSession:
        return accounts.AccountSession(
            "11111111-1111-4111-8111-111111111111", "a@example.test", False, "fixture", None
        )

    async def forbidden(*args: Any, **kwargs: Any) -> None:
        pytest.fail("Unverified request reached usage store or provider")

    monkeypatch.setattr(accounts, "verify_token", verify)
    monkeypatch.setattr(usage_meter, "_rpc", forbidden)
    app.dependency_overrides[get_bid_advisor_service] = lambda: SimpleNamespace(advise=forbidden)
    client = TestClient(app)
    if has_cookie:
        client.cookies.set("muse_access", "fixture")
    try:
        response = client.post(
            "/api/v1/bid-advice?live=true",
            headers={"X-Demo-Key": "fixture-key"},
            json={
                "campaign": build_campaign().model_dump(mode="json"),
                "competitor_brief": brief_json,
            },
        )
    finally:
        app.dependency_overrides.pop(get_bid_advisor_service, None)
    assert response.status_code == (403 if has_cookie else 401)
    assert usage_meter.current_operation_id() is None


@pytest.mark.asyncio
async def test_large_workspace_is_rejected_before_database_write(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def forbidden(*args: Any, **kwargs: Any) -> None:
        pytest.fail("Oversized workspace reached the database")

    monkeypatch.setattr(accounts, "get_supabase_client", forbidden)
    account = accounts.AccountSession(
        "11111111-1111-4111-8111-111111111111", "a@example.test", True, "fixture", None
    )
    with pytest.raises(HTTPException) as error:
        await accounts.save_workspace(account, {"large": "x" * (3 * 1024 * 1024)}, 0)
    assert error.value.status_code == 413
