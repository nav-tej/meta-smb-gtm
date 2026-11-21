"""Which API responses Vercel's CDN may keep, and which it never may.

Every /api/v1 request on Vercel runs the Python function. Responses that are the same for every
visitor (the sample shop's data, the change log, public configuration) carry
`Vercel-CDN-Cache-Control`, so the CDN answers repeat views without running the function, while
browsers get `public, max-age=0` and always ask again. The CDN cache key ignores cookies, so a
response may only be shared if building it never looks at the account: these routes must not call
`resolve_account`, must not set a cookie, and must give a signed-in visitor the same bytes as a
guest. Account routes, a seller's own brief and an explicit rebuild stay uncached.
"""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

from src.api.cache_policy import (
    PRIVATE_API_CACHE_CONTROL,
    SHARED_BROWSER_CACHE_CONTROL,
    SHARED_VERCEL_CDN_CACHE_CONTROL,
)
from src.api.main import app

SHARED = [
    "/api/v1/analytics/config",
    "/api/v1/demo-presets",
    "/api/v1/previews",
    "/api/v1/monitor",
    "/api/v1/monitor?limit=5",
    "/api/v1/weekly-digest",
    "/api/v1/readiness",
    "/api/v1/daily-brief",
    "/api/v1/daily-brief?workspace=sample",
]


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("DEMO_MODE", "true")
    monkeypatch.setenv("META_MODEL_API_KEY", "")
    monkeypatch.setenv("DEMO_KEY", "")
    return TestClient(app)


def _never_read_the_account(monkeypatch: pytest.MonkeyPatch) -> None:
    async def boom(*_args: Any, **_kwargs: Any) -> None:
        raise AssertionError("a shared response must not read the account")

    for mod in ("src.services.accounts", "src.api.accounts", "src.api.daily_brief"):
        monkeypatch.setattr(f"{mod}.resolve_account", boom, raising=False)


@pytest.mark.parametrize("path", SHARED)
def test_shared_responses_are_cacheable_and_never_read_the_account(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, path: str
) -> None:
    _never_read_the_account(monkeypatch)
    guest = client.get(path)
    signed_in = TestClient(app, cookies={"muse_access": "someone-elses-session"}).get(path)
    assert guest.status_code == 200, (path, guest.text[:200])
    assert guest.headers["vercel-cdn-cache-control"] == SHARED_VERCEL_CDN_CACHE_CONTROL, path
    # The browser always asks again. stale-while-revalidate here would reach browsers on a local
    # server, which then revalidate in the background and never let `networkidle` arrive.
    assert guest.headers["cache-control"] == SHARED_BROWSER_CACHE_CONTROL, path
    assert "stale" not in guest.headers["cache-control"], path
    assert "set-cookie" not in guest.headers, path
    assert "vary" not in {k.lower() for k in guest.headers}, path
    assert signed_in.content == guest.content, path
    assert "set-cookie" not in signed_in.headers, path


def test_own_brief_and_rebuild_are_never_shared(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def signed_out(*_args: Any, **_kwargs: Any) -> None:
        return None

    monkeypatch.setattr("src.api.daily_brief.resolve_account", signed_out)
    for path in ("/api/v1/daily-brief?workspace=own", "/api/v1/daily-brief?refresh=true"):
        response = client.get(path)
        assert response.status_code == 200, path
        assert response.headers["cache-control"] == PRIVATE_API_CACHE_CONTROL, path
        assert "vercel-cdn-cache-control" not in response.headers, path


@pytest.mark.parametrize("path", ["/api/v1/account/me", "/api/v1/credits", "/health"])
def test_visitor_specific_and_health_routes_stay_uncached(client: TestClient, path: str) -> None:
    response = client.get(path)
    assert "vercel-cdn-cache-control" not in response.headers, path
    assert "s-maxage" not in response.headers.get("cache-control", ""), path
