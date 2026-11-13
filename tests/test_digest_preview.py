"""Offline tests for Batch 2A personal digest preview & workspace draft preferences."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.digest_email import router as digest_router
from src.services import digest_preview
from src.services.accounts import AccountSession


def _make_app_with_store(
    monkeypatch: pytest.MonkeyPatch,
    workspaces: dict[str, dict[str, Any]],
    current_user_box: dict[str, AccountSession | None],
) -> TestClient:
    async def fake_resolve(
        request: Any, response: Any, require_verified: bool = False
    ) -> AccountSession | None:
        return current_user_box["user"]

    async def fake_load(account: AccountSession) -> dict[str, Any]:
        row = workspaces.get(account.user_id)
        if not row:
            return {"version": 0, "document": None}
        return {"version": row["version"], "document": json.loads(json.dumps(row["document"]))}

    async def fake_save(
        account: AccountSession,
        document: dict[str, Any],
        expected_version: int | None,
        expected_owner: str | None = None,
    ) -> dict[str, Any]:
        if expected_owner and expected_owner != account.user_id:
            from fastapi import HTTPException

            raise HTTPException(409, "Account mismatch.")
        row = workspaces.setdefault(account.user_id, {"version": 0, "document": {}})
        if expected_version is None or expected_version != row["version"]:
            from fastapi import HTTPException

            raise HTTPException(409, "Your workspace changed. Reload before saving.")
        row["version"] += 1
        row["document"] = json.loads(json.dumps(document))
        return {"version": row["version"], "document": row["document"], "owner_id": account.user_id}

    monkeypatch.setattr("src.api.digest_email.resolve_account", fake_resolve)
    monkeypatch.setattr("src.services.digest_preview.load_workspace", fake_load)
    monkeypatch.setattr("src.services.digest_preview.save_workspace", fake_save)

    app = FastAPI()
    app.include_router(digest_router, prefix="/api/v1")
    return TestClient(app)


def test_fake_clock_month31_leap_year_dst_and_biweekly_anchors() -> None:
    """Verify next-send windows across month-31, leap year, DST, biweekly, and paused."""
    # Monthly anchored to 31st: Jan 31 after 08:00 -> Feb 28 (non-leap 2026)
    w_non_leap = digest_preview.compute_next_send_window(
        cadence="monthly",
        timezone_name="America/New_York",
        now=datetime(2026, 1, 31, 15, 0, tzinfo=UTC),
        anchor_day=31,
    )
    assert w_non_leap.next_send_at is not None
    assert (
        w_non_leap.next_send_at.astimezone(digest_preview.ZoneInfo("America/New_York"))
        .date()
        .isoformat()
        == "2026-02-28"
    )

    # Leap year 2024: Jan 31 after 08:00 -> Feb 29
    w_leap = digest_preview.compute_next_send_window(
        cadence="monthly",
        timezone_name="America/New_York",
        now=datetime(2024, 1, 31, 15, 0, tzinfo=UTC),
        anchor_day=31,
    )
    assert w_leap.next_send_at is not None
    assert (
        w_leap.next_send_at.astimezone(digest_preview.ZoneInfo("America/New_York"))
        .date()
        .isoformat()
        == "2024-02-29"
    )

    # DST spring forward (2026-03-08): Monday 2026-03-09 08:00 EDT is UTC-4 (12:00 UTC)
    w_dst_spring = digest_preview.compute_next_send_window(
        cadence="weekly",
        timezone_name="America/New_York",
        now=datetime(2026, 3, 7, 14, 0, tzinfo=UTC),
    )
    assert w_dst_spring.next_send_at == datetime(2026, 3, 9, 12, 0, tzinfo=UTC)

    # DST fall back (2026-11-01): Monday 2026-11-02 08:00 EST is UTC-5 (13:00 UTC)
    w_dst_fall = digest_preview.compute_next_send_window(
        cadence="weekly",
        timezone_name="America/New_York",
        now=datetime(2026, 10, 31, 14, 0, tzinfo=UTC),
    )
    assert w_dst_fall.next_send_at == datetime(2026, 11, 2, 13, 0, tzinfo=UTC)

    # Biweekly anchored to 2026-01-05 stays on 14-day grid even when checked mid-week
    w_bi = digest_preview.compute_next_send_window(
        cadence="biweekly",
        timezone_name="UTC",
        now=datetime(2026, 1, 14, 10, 0, tzinfo=UTC),
        anchor_date="2026-01-05",
    )
    assert w_bi.next_send_at == datetime(2026, 1, 19, 8, 0, tzinfo=UTC)

    # Paused returns None
    w_paused = digest_preview.compute_next_send_window(
        cadence="paused",
        timezone_name="America/Los_Angeles",
        now=datetime(2026, 1, 14, 10, 0, tzinfo=UTC),
    )
    assert w_paused.next_send_at is None
    assert "paused" in w_paused.next_send_display.lower()

    with pytest.raises(ValueError):
        digest_preview.validate_timezone("Mars/Olympus_Mons")


def test_api_ab_ownership_unknown_field_preservation_and_concurrency(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Enforce server-side owner isolation, preserve unknown fields, and reject stale versions."""
    workspaces: dict[str, dict[str, Any]] = {
        "user-a": {
            "version": 2,
            "document": {
                "onboarding": {
                    "business_name": "Cedar Studio",
                    "competitors": ["https://comp-a.test"],
                },
                "custom_unknown_blob": {"keep_me": True},
            },
        },
        "user-b": {"version": 1, "document": {"onboarding": {"business_name": "Fern Clay"}}},
    }
    user_box: dict[str, AccountSession | None] = {"user": None}
    client = _make_app_with_store(monkeypatch, workspaces, user_box)

    # Unauthenticated blocked
    assert client.get("/api/v1/digest/preferences").status_code == 401
    assert client.put("/api/v1/digest/preferences", json={}).status_code == 401
    assert client.post("/api/v1/digest/preview", json={}).status_code == 401

    user_a = AccountSession(
        user_id="user-a",
        email="a@example.com",
        access_token="tok-a",
        session_id="sid-a",
        email_verified=True,
    )
    user_box["user"] = user_a

    # Cross-owner header or body rejected
    assert (
        client.get("/api/v1/digest/preferences", headers={"X-Muse-Owner": "user-b"}).status_code
        == 409
    )
    assert (
        client.put(
            "/api/v1/digest/preferences",
            json={"cadence": "monthly", "expected_version": 2, "expected_owner": "user-b"},
        ).status_code
        == 409
    )

    # Stale expected_version rejected
    assert (
        client.put(
            "/api/v1/digest/preferences",
            json={"cadence": "monthly", "expected_version": 1, "expected_owner": "user-a"},
        ).status_code
        == 409
    )

    # Valid save preserves unknown workspace keys & increments version
    saved = client.put(
        "/api/v1/digest/preferences",
        headers={"X-Muse-Owner": "user-a"},
        json={
            "cadence": "monthly",
            "anchor_day": 31,
            "timezone": "America/New_York",
            "topics": ["pricing", "suggested_moves"],
            "competitors": ["https://comp-a.test"],
            "expected_version": 2,
            "expected_owner": "user-a",
        },
    )
    assert saved.status_code == 200
    body = saved.json()
    assert body["version"] == 3
    assert body["draft_preferences"]["cadence"] == "monthly"
    assert workspaces["user-a"]["document"]["custom_unknown_blob"] == {"keep_me": True}
    assert workspaces["user-b"]["version"] == 1


@pytest.mark.asyncio
async def test_preview_topic_filtering_distinct_sellers_xss_and_zero_cost_spies(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify distinct recommendations, topic filtering, XSS escaping, and zero side effects."""
    calls = {"email": 0, "crawl": 0, "muse": 0}

    async def spy_email(*_a: Any, **_k: Any) -> bool:
        calls["email"] += 1
        return True

    async def spy_crawl(*_a: Any, **_k: Any) -> list[Any]:
        calls["crawl"] += 1
        return []

    def spy_muse(*_a: Any, **_k: Any) -> Any:
        calls["muse"] += 1
        raise AssertionError("Muse must not be called")

    monkeypatch.setattr("src.clients.email.send", spy_email)
    monkeypatch.setattr("src.services.competitor_monitor.crawl_entries", spy_crawl)
    monkeypatch.setattr("src.clients.meta.get_meta_client", spy_muse)

    doc_seller_1 = {
        "onboarding": {"business_name": "Cedar Printmaking", "product_name": "Botanical Linocut"},
        "preferences": {
            "goal": "win gift buyers",
            "access": {"minutes_per_week": 15},
            "memory_entries": [
                {
                    "id": "m1",
                    "key": "minutes_per_week",
                    "label": "Weekly time",
                    "value": "15 minutes per week",
                    "status": "accepted",
                    "category": "constraint",
                    "source": "user_input",
                }
            ],
        },
    }
    doc_seller_2 = {
        "onboarding": {"business_name": "Harbor Metalworks", "product_name": "Forged Tray"},
        "preferences": {
            "goal": "launch summer wholesale",
            "access": {"minutes_per_week": 120},
        },
    }
    docs = {"u1": doc_seller_1, "u2": doc_seller_2}

    async def fake_load(account: AccountSession) -> dict[str, Any]:
        return {"version": 1, "document": docs[account.user_id]}

    monkeypatch.setattr("src.services.digest_preview.load_workspace", fake_load)

    snap_key = digest_preview._key("https://xss-shop.test")
    snapshots = {
        snap_key: {
            "captured": datetime(2026, 11, 10, 12, 0, tzinfo=UTC).isoformat(),
            "report": {
                "url": "https://xss-shop.test",
                "status": "changed",
                "pages_seen": 12,
                "changes": [
                    {
                        "kind": "price_change",
                        "title": "<script>alert(1)</script>Linocut",
                        "url": "javascript:alert(1)",
                        "before": "$40",
                        "after": "$32",
                    },
                    {
                        "kind": "new_listing",
                        "title": "Winter Fern Print",
                        "url": "https://xss-shop.test/winter-fern",
                    },
                ],
                "counts": {"price_change": 1, "new_listing": 1},
            },
        }
    }

    async def loader(k: str) -> dict[str, Any] | None:
        return snapshots.get(k)

    p1 = await digest_preview.build_personal_digest_preview(
        AccountSession(
            user_id="u1",
            email="u1@example.com",
            access_token="tok-1",
            session_id="sid-1",
            email_verified=True,
        ),
        overrides=digest_preview.DigestDraftPreferences(
            cadence="weekly",
            topics=["pricing", "suggested_moves"],
            competitors=["https://xss-shop.test", "https://never-checked.test"],
        ),
        now=datetime(2026, 11, 13, 12, 0, tzinfo=UTC),
        snapshot_loader=loader,
    )
    p2 = await digest_preview.build_personal_digest_preview(
        AccountSession(
            user_id="u2",
            email="u2@example.com",
            access_token="tok-2",
            session_id="sid-2",
            email_verified=True,
        ),
        overrides=digest_preview.DigestDraftPreferences(
            cadence="weekly",
            topics=["suggested_moves"],
            competitors=[],
        ),
        now=datetime(2026, 11, 13, 12, 0, tzinfo=UTC),
        snapshot_loader=loader,
    )

    # Distinct recommendations & fit notes
    assert p1["recommendation"]["fit_note"] != p2["recommendation"]["fit_note"]
    assert "15 min/week" in p1["recommendation"]["fit_note"]
    assert "120 min/week" in p2["recommendation"]["fit_note"]

    # Topic filtering: only pricing change included (new_listing excluded)
    assert len(p1["changes"]) == 1
    assert p1["changes"][0]["kind"] == "price_change"
    assert p1["changes"][0]["url"] is None  # javascript: URL stripped

    # XSS escaped in HTML preview
    assert "<script>" not in p1["html"]
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in p1["html"]
    assert "javascript:alert" not in p1["html"]

    # Never-checked shop stays truthful with 0 crawls
    states = {s["host"]: s["state"] for s in p1["shops_status"]}
    assert states["never-checked.test"] == "never_checked"

    # Zero side effects
    assert p1["sends_triggered"] == 0
    assert p1["crawls_triggered"] == 0
    assert p1["runs_used"] == 0
    assert calls == {"email": 0, "crawl": 0, "muse": 0}
