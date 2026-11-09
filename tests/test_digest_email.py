"""Weekly competitor digest by email (offline: database, Resend and crawler are fakes)."""

from __future__ import annotations

import os
import shutil
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlsplit

import pytest
from fastapi.testclient import TestClient

from src.api.main import app
from src.clients import email
from src.config import get_settings
from src.models.intel import SitemapEntry
from src.services import alerts, digest_email

SUB = "44444444-4444-4444-4444-444444444444"
SHOP = "https://shop.example"


@pytest.fixture
def mail(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
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
def rpc(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    state: dict[str, Any] = {"calls": [], "replies": {}}

    async def fake_rpc(name: str, params: dict[str, Any]) -> dict[str, Any]:
        state["calls"].append((name, params))
        reply = state["replies"].get(name, {"allowed": True})
        if reply.get("allowed") is not True:
            raise digest_email.DigestError(reply["status_code"], reply["message"])
        return reply

    monkeypatch.setattr(digest_email, "_rpc", fake_rpc)
    return state


class MemoryStore(digest_email.SnapshotStore):
    def __init__(self) -> None:
        self.data: dict[str, dict[str, Any]] = {}

    async def get(self, key: str) -> dict[str, Any] | None:
        return self.data.get(key)

    async def put(self, key: str, value: dict[str, Any]) -> None:
        self.data[key] = value


# ---------- input and links ----------


def test_shop_links_are_normalized_and_limited() -> None:
    assert digest_email.normalize_shops([" shop.example/ ", "https://shop.example"]) == [SHOP]
    for bad in ([], ["ftp://x.example"], ["a.example", "b.example", "c.example", "d.example"]):
        with pytest.raises(digest_email.DigestError):
            digest_email.normalize_shops(bad)


def test_signed_links_reject_tampering(mail: list[dict[str, Any]]) -> None:
    query = parse_qs(urlsplit(digest_email.confirm_url(SUB, [SHOP])).query)
    packed, token = query["c"][0], query["t"][0]
    assert digest_email.verify_confirm(SUB, packed, token) == [SHOP]
    other = digest_email._pack(["https://evil.example"])
    assert digest_email.verify_confirm(SUB, other, token) is None
    assert (
        digest_email.verify_confirm("55555555-5555-5555-5555-555555555555", packed, token) is None
    )
    leave = parse_qs(urlsplit(digest_email.unsubscribe_url(SUB)).query)["t"][0]
    assert digest_email.verify_unsubscribe(SUB, leave) and not digest_email.verify_unsubscribe(
        SUB, "x"
    )


# ---------- routes ----------


def test_sign_up_is_closed_without_email_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RESEND_API_KEY", "")
    get_settings.cache_clear()
    client = TestClient(app)
    assert client.get("/api/v1/digest/subscription").json() == {"available": False}
    response = client.post(
        "/api/v1/digest/subscribe", json={"email": "a@example.com", "competitors": [SHOP]}
    )
    assert response.status_code == 503
    get_settings.cache_clear()


def test_sign_up_sends_one_confirmation_and_never_reveals_status(
    mail: list[dict[str, Any]], rpc: dict[str, Any]
) -> None:
    client = TestClient(app)
    rpc["replies"]["muse_digest_subscribe"] = {"allowed": True, "id": SUB, "send_confirm": True}
    first = client.post(
        "/api/v1/digest/subscribe",
        json={"email": "Ana@Example.com", "competitors": ["shop.example"]},
    )
    rpc["replies"]["muse_digest_subscribe"] = {"allowed": True, "id": SUB, "send_confirm": False}
    again = client.post(
        "/api/v1/digest/subscribe", json={"email": "ana@example.com", "competitors": [SHOP]}
    )
    assert first.status_code == again.status_code == 200
    assert first.json() == again.json()
    assert len(mail) == 1 and mail[0]["to"] == "ana@example.com"
    assert "https://muse.test/api/v1/digest/confirm?" in mail[0]["html"]
    assert rpc["calls"][0][1]["p_competitors"] == [SHOP]


def test_sign_up_rate_limit_is_passed_through(
    mail: list[dict[str, Any]], rpc: dict[str, Any]
) -> None:
    rpc["replies"]["muse_digest_subscribe"] = {
        "allowed": False,
        "status_code": 429,
        "message": "Too many sign-ups from this network today.",
    }
    response = TestClient(app).post(
        "/api/v1/digest/subscribe", json={"email": "a@example.com", "competitors": [SHOP]}
    )
    assert response.status_code == 429 and mail == []


def test_confirm_and_unsubscribe_links(mail: list[dict[str, Any]], rpc: dict[str, Any]) -> None:
    client = TestClient(app, follow_redirects=False)
    confirm = urlsplit(digest_email.confirm_url(SUB, [SHOP]))
    ok = client.get(f"{confirm.path}?{confirm.query}")
    assert ok.status_code == 303 and ok.headers["location"] == "/digest?email=confirmed"
    assert rpc["calls"][-1] == (
        "muse_digest_set_status",
        {"p_id": SUB, "p_status": "active", "p_competitors": [SHOP]},
    )
    bad = client.get(f"{confirm.path}?{confirm.query}x")
    assert bad.headers["location"] == "/digest?email=link-invalid"

    leave = urlsplit(digest_email.unsubscribe_url(SUB))
    out = client.get(f"{leave.path}?{leave.query}")
    assert out.headers["location"] == "/digest?email=unsubscribed"
    one_click = client.post(f"{leave.path}?{leave.query}")
    assert one_click.status_code == 200 and one_click.json() == {"unsubscribed": True}
    assert client.post(f"{leave.path}?id={SUB}&t=bad").status_code == 400


def test_weekly_job_only_runs_for_the_scheduler(
    mail: list[dict[str, Any]], monkeypatch: pytest.MonkeyPatch
) -> None:
    async def fake_run() -> dict[str, int]:
        return {"due": 0, "sent": 0, "failed": 0, "shops": 0}

    monkeypatch.setattr(digest_email, "run_weekly", fake_run)
    client = TestClient(app)
    assert client.get("/api/v1/digest/send").status_code == 403
    assert (
        client.get("/api/v1/digest/send", headers={"user-agent": "vercel-cron/1.0"}).json()["due"]
        == 0
    )
    monkeypatch.setenv("CRON_SECRET", "s3cret")
    get_settings.cache_clear()
    assert (
        client.get("/api/v1/digest/send", headers={"user-agent": "vercel-cron/1.0"}).status_code
        == 401
    )
    assert (
        client.get("/api/v1/digest/send", headers={"authorization": "Bearer s3cret"}).status_code
        == 200
    )


# ---------- weekly run ----------


def _entries(*items: tuple[str, str, str]) -> list[SitemapEntry]:
    return [SitemapEntry(loc=loc, title=title, price_hint=price) for loc, title, price in items]


@pytest.mark.asyncio
async def test_weekly_run_baselines_then_reports_changes_once_per_shop(
    mail: list[dict[str, Any]], rpc: dict[str, Any]
) -> None:
    store = MemoryStore()
    crawls: list[str] = []
    pages = _entries(
        (f"{SHOP}/products/a", "Print A", "$40"), (f"{SHOP}/products/b", "Print B", "$50")
    )

    async def fetch(url: str) -> list[SitemapEntry]:
        crawls.append(url)
        return pages

    due = [
        {"id": SUB, "email": "a@example.com", "competitors": [SHOP]},
        {
            "id": "55555555-5555-5555-5555-555555555555",
            "email": "b@example.com",
            "competitors": [SHOP],
        },
    ]
    rpc["replies"]["muse_digest_due"] = {"allowed": True, "subscribers": due}
    week1 = datetime(2026, 11, 9, 15, tzinfo=UTC)
    summary = await digest_email.run_weekly(fetch_entries=fetch, store=store, now=week1)
    assert summary == {"due": 2, "sent": 2, "failed": 0, "shops": 1}
    assert crawls == [SHOP]  # shared shop crawled once
    assert "We started watching this shop: 2 public pages" in mail[0]["text"]
    assert mail[0]["headers"]["List-Unsubscribe-Post"] == "List-Unsubscribe=One-Click"
    assert mail[0]["idempotency_key"].startswith(f"digest-{SUB}-2026-W")

    # A repeat inside 6 days reuses the stored report instead of crawling again.
    await digest_email.run_weekly(fetch_entries=fetch, store=store, now=week1 + timedelta(hours=1))
    assert crawls == [SHOP]

    pages = _entries(
        (f"{SHOP}/products/a", "Print A", "$45"),
        (f"{SHOP}/products/c", "<script>alert(1)</script> Print C", "$60"),
    )
    mail.clear()
    await digest_email.run_weekly(fetch_entries=fetch, store=store, now=week1 + timedelta(days=7))
    message = mail[0]
    assert message["subject"] == "Competitor digest: 3 changes this week"
    assert "Print A — $40 → $45" in message["text"]
    assert "&lt;script&gt;" in message["html"] and "<script>" not in message["html"]
    assert "Removed listings (1)" in message["text"]
    assert "https://muse.test/api/v1/digest/unsubscribe?" in message["html"]
    assert ("muse_digest_mark_sent", {"p_id": SUB}) in rpc["calls"]


@pytest.mark.asyncio
async def test_a_blocked_shop_is_reported_honestly_and_unsafe_links_are_not_linked(
    mail: list[dict[str, Any]], rpc: dict[str, Any]
) -> None:
    async def blocked(url: str) -> list[SitemapEntry]:
        raise RuntimeError("403")

    rpc["replies"]["muse_digest_due"] = {
        "allowed": True,
        "subscribers": [{"id": SUB, "email": "a@example.com", "competitors": [SHOP]}],
    }
    await digest_email.run_weekly(fetch_entries=blocked, store=MemoryStore())
    assert "could not read this shop" in mail[0]["text"]
    assert digest_email._safe_link("javascript:alert(1)") is None


@pytest.mark.asyncio
async def test_nothing_is_sent_without_email_settings(
    monkeypatch: pytest.MonkeyPatch, rpc: dict[str, Any]
) -> None:
    monkeypatch.setenv("RESEND_API_KEY", "")
    get_settings.cache_clear()
    assert (await digest_email.run_weekly(store=MemoryStore()))["due"] == 0
    assert rpc["calls"] == []
    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_alerts_are_throttled_per_kind(mail: list[dict[str, Any]]) -> None:
    assert await alerts.alert("Stripe webhook not recorded", "evt_1 failed")
    assert not await alerts.alert("Stripe webhook not recorded", "evt_2 failed")
    assert await alerts.alert("Weekly digest not sent", "x")
    assert [m["to"] for m in mail] == ["help@nplusalpha.com", "help@nplusalpha.com"]


def test_digest_sql_on_local_postgres() -> None:
    pglite = os.environ.get("BILLING_PGLITE_DIR", "")
    node = shutil.which("node")
    if not node or not pglite or not Path(pglite, "dist/index.js").is_file():
        pytest.skip("Set BILLING_PGLITE_DIR to a local @electric-sql/pglite install to run")
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        [node, str(root / "tests/digest_sql.mjs")], capture_output=True, text=True, timeout=120
    )
    assert result.returncode == 0, result.stdout + result.stderr[-3000:]
    assert "digest SQL checks passed" in result.stdout
