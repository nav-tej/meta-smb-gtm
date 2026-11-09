"""PostHog analytics stays off without a key, never leaks secrets, never breaks billing."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx
from fastapi.testclient import TestClient

from src.api.main import app
from src.config import get_settings

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "src/api/static"
PAGES = ("index.html", "creator.html", "today.html", "digest.html")


@pytest.fixture(autouse=True)
def _settings(monkeypatch: pytest.MonkeyPatch) -> Any:
    monkeypatch.setenv("POSTHOG_KEY", "")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _enable(monkeypatch: pytest.MonkeyPatch, host: str = "https://us.i.posthog.com/") -> None:
    monkeypatch.setenv("POSTHOG_KEY", "phc_public_test_key")
    monkeypatch.setenv("POSTHOG_HOST", host)
    get_settings.cache_clear()


def test_config_is_disabled_without_a_key() -> None:
    body = TestClient(app).get("/api/v1/analytics/config").json()
    assert body == {"enabled": False}


def test_config_returns_only_the_public_key_and_host(monkeypatch: pytest.MonkeyPatch) -> None:
    _enable(monkeypatch)
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_should_not_leak")
    get_settings.cache_clear()
    response = TestClient(app).get("/api/v1/analytics/config")
    assert response.json() == {
        "enabled": True,
        "key": "phc_public_test_key",
        "host": "https://us.i.posthog.com",
    }
    assert "sk_test" not in response.text


@pytest.mark.asyncio
async def test_server_capture_is_best_effort(monkeypatch: pytest.MonkeyPatch) -> None:
    from src.clients import posthog

    assert await posthog.capture("x", "user-1") is False  # disabled: no request
    _enable(monkeypatch)
    with respx.mock(assert_all_called=False) as mock:
        route = mock.post("https://us.i.posthog.com/i/v0/e/")
        route.return_value = httpx.Response(200, json={"status": 1})
        assert await posthog.capture("subscription_paid", "user-1", {"plan": "starter"}) is True
        sent = route.calls.last.request
        assert b'"distinct_id":"user-1"' in sent.content.replace(b" ", b"")
        route.return_value = httpx.Response(500)
        assert await posthog.capture("x", "user-1") is False
        route.side_effect = httpx.ConnectError("down")
        assert await posthog.capture("x", "user-1") is False
        assert await posthog.capture("x", "") is False


def _paid_event() -> dict[str, Any]:
    return {
        "event_id": "evt_1",
        "created": 1,
        "kind": "invoice.paid",
        "object_id": "in_1",
        "customer": "cus_1",
        "action": "paid",
        "subscription": "sub_1",
        "user_id": "11111111-1111-1111-1111-111111111111",
        "plan": "starter",
        "period_start": 1_700_000_000,
        "period_end": 1_700_000_000 + 365 * 86400,
        "status": "active",
    }


@pytest.mark.parametrize(
    ("data", "enabled", "expected"),
    [
        (_paid_event(), True, ("subscription_paid", {"interval": "year", "plan": "starter"})),
        ({**_paid_event(), "action": "state", "status": "canceled"}, True, "subscription_canceled"),
        ({**_paid_event(), "action": "state", "status": "active"}, True, None),
        ({**_paid_event(), "user_id": None}, True, None),
        (_paid_event(), False, None),
    ],
)
@pytest.mark.asyncio
async def test_billing_reports_verified_events_only(
    monkeypatch: pytest.MonkeyPatch, data: dict[str, Any], enabled: bool, expected: Any
) -> None:
    from src.api import billing
    from src.clients import posthog

    if enabled:
        _enable(monkeypatch)
    sent: list[tuple[str, str, dict[str, Any]]] = []

    async def fake_capture(event: str, distinct_id: str, props: dict[str, Any]) -> bool:
        sent.append((event, distinct_id, props))
        return True

    monkeypatch.setattr(posthog, "capture", fake_capture)
    await billing._report_billing_event(data)
    if expected is None:
        assert sent == []
        return
    name = expected[0] if isinstance(expected, tuple) else expected
    assert sent[0][0] == name and sent[0][1] == data["user_id"]
    if isinstance(expected, tuple):
        for key, value in expected[1].items():
            assert sent[0][2][key] == value


def test_browser_snippet_is_privacy_safe_and_loaded_on_every_page() -> None:
    script = (STATIC / "analytics.js").read_text()
    for setting in (
        "disable_session_recording: true",
        "respect_dnt: true",
        "person_profiles: 'identified_only'",
        "before_send: scrub",
        "url.hash = ''",
    ):
        assert setting in script
    identify_args = script.split("identify(")[1].split(")")[0]
    assert re.search(r"user\.email\b(?!_)", identify_args) is None  # account ID only
    for page in PAGES:
        html = (STATIC / page).read_text()
        assert "/static/analytics.js" in html, page
        assert html.index("/static/analytics.js") < html.index("/static/account.js"), page


def test_privacy_page_discloses_posthog() -> None:
    privacy = (STATIC / "legal/privacy.html").read_text()
    assert "PostHog" in privacy and "never by email" in privacy


def test_portal_makes_plans_and_signup_obvious() -> None:
    html = TestClient(app).get("/portal").text
    assert 'data-open-pricing data-track="nav_plans">Plans &amp; pricing' in html
    assert "data-hero-primary" in html and 'data-track="hero_plans">See plans' in html
    assert 'class="hero-path"' in html and "20 runs a month" in html
    # Copy that contradicted paid plans or confused the two kinds of login is gone.
    for stale in ("No credit card", "Switch / Login", "Saved demo is free"):
        assert stale not in html
    account = (STATIC / "account.js").read_text()
    assert "Create free account" in account and "Saved demo is free" not in account


def test_paying_account_users_never_need_the_presenter_key() -> None:
    creator = (STATIC / "creator.js").read_text()
    today = (STATIC / "today.js").read_text()
    account = (STATIC / "account.js").read_text()
    # Account mode turns live on for verified users with runs and skips the unlock-key check.
    assert "!state.key && !state.defaultLive && !state.accountLive" in creator
    assert "state.accountLive = readiness.value.accounts_required === true" in creator
    assert (
        "if (state.readiness?.accounts_required && state.readiness?.provider_key_configured)"
        in today
    )
    # The presenter header is only sent when someone actually entered a key.
    assert "...(state.live && state.key ? { 'X-Demo-Key':" in creator
    assert "...(live && state.key ? { 'X-Demo-Key': state.key } : {})" in today
    # Running out of runs leads to plans, not a dead end.
    assert "window.museShell.openPricing()" in account
    assert "Credit purchases are coming later" not in account


def test_pages_always_revalidate() -> None:
    client = TestClient(app)
    for path in ("/", "/portal", "/create", "/today", "/digest", "/account"):
        assert client.get(path).headers["cache-control"] == "no-cache", path
