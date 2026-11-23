"""Tests for own-workspace saved competitor checks in /today and YouTube content sources."""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, Mock

import httpx
import pytest
from fastapi import Request, Response
from fastapi.testclient import TestClient

from src.api import daily_brief as brief_api
from src.api.main import app
from src.clients.meta import MetaClient
from src.config import get_settings
from src.services import daily_brief as brief_service
from src.services.accounts import AccountSession

NOW = datetime(2026, 11, 21, 12, tzinfo=UTC)
OWN_BRIEF_URL = "/api/v1/daily-brief?workspace=own"
SAMPLE_SHA256 = "0effdbdc3d0017f98f8e86f7f1f50f8386d5824f3f0e1ac7b2a7d04ec8e78615"


def _own_doc(
    *,
    competitors: list[dict[str, Any]] | None = None,
    competitor_checks: dict[str, Any] | None = None,
) -> dict[str, Any]:
    prefs: dict[str, Any] = {
        "goal": "Grow inquiries",
        "access": {"minutes_per_week": 60, "channels": ["instagram", "website"]},
    }
    if competitor_checks is not None:
        prefs["competitor_checks"] = competitor_checks
    return {
        "onboarding": {
            "business_name": "Northstar Advisory",
            "business_type": "services",
            "completed_at": "2026-11-20T12:00:00Z",
            "competitors": competitors
            if competitors is not None
            else [
                {"name": "Rival None", "url": "https://rival-none.example/"},
                {"name": "Rival First", "url": "https://Rival-First.example/"},
                {"name": "Rival Changed", "url": "https://rival-changed.example"},
                {"name": "Rival Unchanged", "url": "https://rival-unchanged.example"},
                {"name": "Rival Error", "url": "https://rival-error.example"},
            ],
        },
        "preferences": prefs,
        "outcomes": [],
    }


@pytest.fixture
def brief_harness(
    _never_use_real_meta_key: None, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> SimpleNamespace:
    monkeypatch.setenv("DEMO_MODE", "true")
    monkeypatch.setenv("META_MODEL_API_KEY", "")
    monkeypatch.setenv("DEMO_KEY", "")
    monkeypatch.setenv("RESULT_CACHE_ENABLED", "true")
    monkeypatch.setenv("RESULT_CACHE_DIR", str(tmp_path / "cache"))
    get_settings.cache_clear()
    monkeypatch.setattr(
        MetaClient, "__init__", Mock(side_effect=AssertionError("Must not construct Muse"))
    )

    def no_network(*args: Any, **kwargs: Any) -> None:
        pytest.fail("Own brief attempted external HTTP")

    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", no_network)
    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", no_network)

    store: dict[str, Any] = {"doc": _own_doc()}
    session = AccountSession(
        user_id="user-own",
        email="owner@example.test",
        email_verified=True,
        access_token="offline",
        session_id=None,
    )

    async def resolve(
        request: Request, response: Response, require_verified: bool = False
    ) -> AccountSession | None:
        return session if request.headers.get("X-Test-Account") == "owner" else None

    async def load(account: AccountSession) -> dict[str, Any]:
        return {"document": deepcopy(store["doc"]), "owner_id": account.user_id}

    loader = AsyncMock(side_effect=load)
    monkeypatch.setattr(brief_api, "resolve_account", resolve)
    monkeypatch.setattr(brief_service, "load_workspace", loader)
    return SimpleNamespace(client=TestClient(app), store=store, loader=loader)


def test_own_brief_maps_every_saved_competitor_check_status(
    brief_harness: SimpleNamespace,
) -> None:
    brief_harness.store["doc"] = _own_doc(
        competitor_checks={
            "https://rival-first.example": {
                "status": "first_check",
                "checked_at": "2026-11-21T09:00:00Z",
                "summary": (
                    "First check: Muse now knows 12 of their pages."
                    " Changes show from the next check."
                ),
                "error": "",
            },
            "https://rival-changed.example": {
                "status": "changed",
                "checked_at": "2026-11-23T14:30:00Z",
                "summary": "2 new pages, 1 price change since Nov 21.",
                "error": "",
            },
            "https://rival-unchanged.example": {
                "status": "unchanged",
                "checked_at": "2026-11-22T10:00:00Z",
                "summary": "No changes since Nov 21.",
                "error": "",
            },
            "https://rival-error.example": {
                "status": "error",
                "checked_at": "2026-11-22T11:00:00Z",
                "summary": "",
                "error": "This site blocks automated reading.",
            },
        }
    )

    res = brief_harness.client.get(OWN_BRIEF_URL, headers={"X-Test-Account": "owner"})
    assert res.status_code == 200
    brief_harness.loader.assert_awaited_once()
    brief = res.json()
    by_name = {item["name"]: item for item in brief["items"]}

    assert by_name["Rival None"]["status"] == "unchecked"
    assert by_name["Rival None"]["note"] == "Not checked yet. Check now (free) on your digest."
    assert "checked_at" not in by_name["Rival None"]

    assert by_name["Rival First"]["status"] == "first"
    assert (
        by_name["Rival First"]["note"]
        == "First check: Muse now knows 12 of their pages. Changes show from the next check."
    )
    assert by_name["Rival First"]["checked_at"] == "2026-11-21T09:00:00Z"

    assert by_name["Rival Changed"]["status"] == "changed"
    assert by_name["Rival Changed"]["note"] == "2 new pages, 1 price change since Nov 21."
    assert by_name["Rival Changed"]["checked_at"] == "2026-11-23T14:30:00Z"

    assert by_name["Rival Unchanged"]["status"] == "unchanged"
    assert by_name["Rival Unchanged"]["note"] == "No changes since Nov 21."
    assert by_name["Rival Unchanged"]["checked_at"] == "2026-11-22T10:00:00Z"

    assert by_name["Rival Error"]["status"] == "failed"
    assert by_name["Rival Error"]["note"] == "This site blocks automated reading."
    assert by_name["Rival Error"]["checked_at"] == "2026-11-22T11:00:00Z"

    assert brief["overnight_note"] == (
        "Muse checks your watchlist when you press Check now (free) on your digest."
        " Last check: Nov 23."
    )
    assert "automatic" not in brief["overnight_note"].lower()
    assert "overnight" not in brief["overnight_note"].lower()


def test_own_brief_no_saved_checks_keeps_unchecked_wording(
    brief_harness: SimpleNamespace,
) -> None:
    res = brief_harness.client.get(OWN_BRIEF_URL, headers={"X-Test-Account": "owner"})
    assert res.status_code == 200
    brief = res.json()
    assert all(item["status"] == "unchecked" for item in brief["items"])
    assert all(
        item["note"] == "Not checked yet. Check now (free) on your digest."
        for item in brief["items"]
    )
    assert all("checked_at" not in item for item in brief["items"])
    assert (
        brief["overnight_note"]
        == "Muse checks your watchlist when you press Check now (free) on your digest."
    )


def test_sample_brief_json_is_byte_identical(
    brief_harness: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    class FixedDatetime(datetime):
        @classmethod
        def now(cls, tz: Any = None) -> datetime:
            return NOW

    monkeypatch.setattr(brief_service, "datetime", FixedDatetime)
    monkeypatch.setattr(brief_service, "_fresh_live_summaries", lambda: [])
    monkeypatch.setattr(
        brief_service.competitor_monitor,
        "load_changelog",
        lambda: SimpleNamespace(runs=[], last_checked_at=None),
    )
    monkeypatch.setattr(brief_service.competitor_monitor, "changes_since", lambda *args: [])
    res = brief_harness.client.get("/api/v1/daily-brief?workspace=sample")
    assert res.status_code == 200
    canonical = json.dumps(res.json(), sort_keys=True, separators=(",", ":"))
    assert hashlib.sha256(canonical.encode()).hexdigest() == SAMPLE_SHA256
