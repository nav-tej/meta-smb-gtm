"""Revision 4 Digest Rules tests.

Tests:
1. Subscribing requires a signed-in account and uses verified email (rejects unauthed with 401).
2. Digest email shows runs left.
3. Zero runs: exactly one 'paused' email sent, then nothing until runs return.
4. Resumption: when runs return (>0), digest delivery resumes normally.
5. Unsubscribe always wins: idempotent, sets status unsubscribed, RFC 8058 headers present.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlsplit

import pytest
from fastapi.testclient import TestClient

from src.api.main import app
from src.clients import email
from src.config import get_settings
from src.models.intel import SitemapEntry
from src.services import alerts, digest_email
from src.services.accounts import AccountSession

SUB_ID = "66666666-6666-4000-8000-666666666666"
SHOP = "https://competitor.shop.example"


class MemoryStore:
    def __init__(self) -> None:
        self.data: dict[str, Any] = {}

    async def get(self, key: str) -> dict[str, Any] | None:
        return self.data.get(key)

    async def put(self, key: str, value: dict[str, Any]) -> None:
        self.data[key] = value


@pytest.fixture
def mail_outbox(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    monkeypatch.setenv("RESEND_API_KEY", "re_test_placeholder")
    monkeypatch.setenv("EMAIL_TOKEN_SECRET", "test-secret")
    monkeypatch.setenv("APP_URL", "https://muse.test")
    monkeypatch.setenv("CRON_SECRET", "")
    get_settings.cache_clear()
    monkeypatch.setattr(digest_email, "configured", lambda: True)
    sent: list[dict[str, Any]] = []

    async def fake_send(to: str, subject: str, html: str, text: str, **kwargs: Any) -> bool:
        sent.append({"to": to, "subject": subject, "html": html, "text": text, **kwargs})
        return True

    monkeypatch.setattr(email, "send", fake_send)
    alerts.reset()
    yield sent
    get_settings.cache_clear()


@pytest.fixture
def rpc_mock(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    state: dict[str, Any] = {"calls": [], "replies": {}}

    async def fake_rpc(name: str, params: dict[str, Any]) -> dict[str, Any]:
        state["calls"].append((name, params))
        return state["replies"].get(name, {"allowed": True})

    monkeypatch.setattr(digest_email, "_rpc", fake_rpc)
    return state


def test_subscribe_requires_signed_in_account(
    mail_outbox: list[dict[str, Any]], rpc_mock: dict[str, Any]
) -> None:
    """Anonymous callers cannot subscribe to the weekly digest (401 Unauthorized)."""
    client = TestClient(app)
    resp = client.post(
        "/api/v1/digest/subscribe",
        json={"competitors": [SHOP], "frequency": "weekly"},
    )
    assert resp.status_code == 401
    assert "Sign in" in resp.json()["detail"] or "account" in resp.json()["detail"]
    assert len(mail_outbox) == 0


def test_subscribe_uses_verified_account_email_not_body(
    monkeypatch: pytest.MonkeyPatch,
    mail_outbox: list[dict[str, Any]],
    rpc_mock: dict[str, Any],
) -> None:
    """Server enforces subscription with verified account email, ignoring arbitrary body emails."""
    verified_user = AccountSession(
        user_id=SUB_ID,
        email="real_seller@studio.example",
        email_verified=True,
        access_token="valid-token",
        session_id=None,
    )

    async def fake_resolve(*_args: Any, **_kwargs: Any) -> AccountSession:
        return verified_user

    monkeypatch.setattr("src.api.digest_email.resolve_account", fake_resolve)
    rpc_mock["replies"]["muse_digest_subscribe"] = {
        "allowed": True,
        "id": SUB_ID,
        "send_confirm": True,
    }

    client = TestClient(app)
    resp = client.post(
        "/api/v1/digest/subscribe",
        json={
            "email": "attacker_supplied@victim.test",
            "competitors": [SHOP],
            "frequency": "weekly",
        },
    )
    assert resp.status_code == 200

    # The subscription was registered for real_seller, NOT attacker_supplied
    assert len(mail_outbox) == 1
    assert mail_outbox[0]["to"] == "real_seller@studio.example"
    subscribe_call = next(c for c in rpc_mock["calls"] if c[0] == "muse_digest_subscribe")
    assert subscribe_call[1]["p_email"] == "real_seller@studio.example"


@pytest.mark.asyncio
async def test_digest_displays_runs_left_in_email(
    mail_outbox: list[dict[str, Any]], rpc_mock: dict[str, Any]
) -> None:
    """When runs remain, weekly digest email clearly displays runs left."""
    store = MemoryStore()

    async def fake_fetch(_url: str) -> list[SitemapEntry]:
        return [
            SitemapEntry(loc=f"{SHOP}/item-1", title="Handmade Ceramic Mug", price="$35"),
        ]

    due_subscribers = [
        {"id": SUB_ID, "email": "seller@pottery.example", "competitors": [SHOP]},
    ]
    rpc_mock["replies"]["muse_digest_due"] = {"allowed": True, "subscribers": due_subscribers}

    async def fake_runs(_email: str) -> int:
        return 5

    now = datetime(2026, 11, 16, 10, tzinfo=UTC)
    summary = await digest_email.run_weekly(
        fetch_entries=fake_fetch,
        store=store,  # type: ignore[arg-type]
        now=now,
        runs_lookup=fake_runs,
    )
    assert summary["sent"] == 1
    assert summary["paused"] == 0
    assert len(mail_outbox) == 1

    msg = mail_outbox[0]
    assert "Runs remaining this month: 5" in msg["text"]
    assert "Runs remaining this month:" in msg["html"]
    assert "5" in msg["html"]


@pytest.mark.asyncio
async def test_zero_runs_sends_one_pause_email_then_pauses(
    mail_outbox: list[dict[str, Any]], rpc_mock: dict[str, Any]
) -> None:
    """Zero runs triggers exactly one pause notification; further crons do nothing until reset."""
    store = MemoryStore()

    async def fake_fetch(_url: str) -> list[SitemapEntry]:
        return [SitemapEntry(loc=f"{SHOP}/item-1", title="Product", price="$20")]

    due_subscribers = [
        {"id": SUB_ID, "email": "zeroruns@shop.example", "competitors": [SHOP]},
    ]
    rpc_mock["replies"]["muse_digest_due"] = {"allowed": True, "subscribers": due_subscribers}

    current_runs = 0

    async def runs_getter(_email: str) -> int:
        return current_runs

    # Week 1: 0 runs -> triggers single pause email
    week1 = datetime(2026, 11, 16, 10, tzinfo=UTC)
    summary1 = await digest_email.run_weekly(
        fetch_entries=fake_fetch,
        store=store,  # type: ignore[arg-type]
        now=week1,
        runs_lookup=runs_getter,
    )
    assert summary1["paused"] == 1
    assert summary1["sent"] == 0
    assert len(mail_outbox) == 1
    assert mail_outbox[0]["subject"] == "Your weekly competitor digest is paused (0 runs remaining)"
    assert "0 runs remaining" in mail_outbox[0]["text"]
    assert "/#pricing" in mail_outbox[0]["html"]

    # Week 2: still 0 runs -> does NOT send another email (silent pause)
    mail_outbox.clear()
    week2 = datetime(2026, 11, 23, 10, tzinfo=UTC)
    summary2 = await digest_email.run_weekly(
        fetch_entries=fake_fetch,
        store=store,  # type: ignore[arg-type]
        now=week2,
        runs_lookup=runs_getter,
    )
    assert summary2["paused"] == 0
    assert summary2["sent"] == 0
    assert len(mail_outbox) == 0

    # Week 3: subscriber upgrades or gets quota reset (runs = 20) -> digest resumes!
    current_runs = 20
    week3 = datetime(2026, 11, 30, 10, tzinfo=UTC)
    summary3 = await digest_email.run_weekly(
        fetch_entries=fake_fetch,
        store=store,  # type: ignore[arg-type]
        now=week3,
        runs_lookup=runs_getter,
    )
    assert summary3["sent"] == 1
    assert summary3["paused"] == 0
    assert len(mail_outbox) == 1
    assert "Runs remaining this month: 20" in mail_outbox[0]["text"]


@pytest.mark.asyncio
async def test_unsubscribe_always_wins_and_headers_present(
    mail_outbox: list[dict[str, Any]], rpc_mock: dict[str, Any]
) -> None:
    """Unsubscribe token/link always sets status to unsubscribed and is idempotent."""
    client = TestClient(app, follow_redirects=False)

    # 1. Unsubscribe link works and redirects cleanly
    leave_url = urlsplit(digest_email.unsubscribe_url(SUB_ID))
    resp = client.get(f"{leave_url.path}?{leave_url.query}")
    assert resp.status_code == 303
    assert resp.headers["location"] == "/digest?email=unsubscribed"
    expected_call = ("muse_digest_set_status", {"p_id": SUB_ID, "p_status": "unsubscribed"})
    assert expected_call in rpc_mock["calls"]

    # 2. RFC 8058 one-click mail header unsubscribe
    resp_rfc = client.post(f"{leave_url.path}?{leave_url.query}")
    assert resp_rfc.status_code == 200
    assert resp_rfc.json() == {"unsubscribed": True}

    # 3. Repeated unsubscribe is idempotent
    resp_repeat = client.get(f"{leave_url.path}?{leave_url.query}")
    assert resp_repeat.status_code == 303
    assert resp_repeat.headers["location"] == "/digest?email=unsubscribed"
