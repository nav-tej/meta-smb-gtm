"""A finished competitor analysis stays in the seller's workspace and feeds their strategy.

Nov 25, production: Nav's analysis of a watched competitor succeeded, then the home saved it with
`POST /api/v1/account/workspace`, which the server answers 405, and dropped the error. A reload
lost the brief, and nothing reached the seller's notes or ranked moves. Now the home calls
`PUT /api/v1/competitors/saved`, which merges the competitor, its brief and its takeaway into the
saved workspace (src/services/saved_competitors.py).
"""

from __future__ import annotations

import json
from typing import Any

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from src.api import intel
from src.api.main import app
from src.models.intel import CompetitorBrief
from src.services.accounts import AccountSession
from src.services.saved_competitors import (
    MAX_SAVED_BRIEFS,
    analysis_takeaway,
    merge_saved_competitor,
)
from src.services.seller_memory import rank_seller_recommendations

NOW = "2026-11-26T07:00:00Z"


def _doc() -> dict[str, Any]:
    return {
        "onboarding": {
            "business_name": "n Plus Alpha Ventures",
            "business_type": "services",
            "completed_at": "2026-11-10T10:00:00Z",
            "competitors": [
                {"name": "Clutch B2B Marketing Directory", "url": "https://clutch.co/",
                 "reason": "Example", "selected": True},
                {"name": "Demand Curve", "url": "https://www.demandcurve.com",
                 "reason": "Growth advisory", "selected": True},
            ],
        },
        "preferences": {"goal": "More client inquiries"},
    }  # fmt: skip


def _brief(competitor_brief: CompetitorBrief, summary: str) -> CompetitorBrief:
    return competitor_brief.model_copy(update={"summary": summary})


def test_takeaway_fits_a_note_and_ends_at_a_sentence(competitor_brief: CompetitorBrief) -> None:
    short = _brief(competitor_brief, "Clutch ranks agencies by reviews. It sells listings.")
    assert analysis_takeaway(short) == "Clutch ranks agencies by reviews. It sells listings."
    long_text = ("Clutch lists thousands of agencies by city and service. " * 8).strip()
    takeaway = analysis_takeaway(_brief(competitor_brief, long_text))
    assert len(takeaway) <= 280 and takeaway.endswith(".")


def test_analysis_replaces_a_setup_note_and_is_kept_for_view(
    competitor_brief: CompetitorBrief,
) -> None:
    brief = _brief(competitor_brief, "Clutch ranks B2B agencies by verified client reviews.")
    doc, entry, added = merge_saved_competitor(
        _doc(), url="https://clutch.co/", name="Clutch", brief=brief, now_iso=NOW
    )
    assert added is False
    # Seller memory had no entries yet: seeded from setup in the same order, then updated.
    entries = doc["preferences"]["competitor_entries"]
    assert [e["url"] for e in entries] == ["https://clutch.co/", "https://www.demandcurve.com"]
    assert entry["rationale"] == "Clutch ranks B2B agencies by verified client reviews."
    assert entry["analysis_takeaway"] == entry["rationale"] and entry["analyzed_at"] == NOW
    assert entries[1]["rationale"] == "Growth advisory"
    assert doc["briefs"]["https://clutch.co/"]["summary"] == brief.summary
    # Setup's own record stays: completed_at and the same two competitors.
    assert doc["onboarding"]["completed_at"] == "2026-11-10T10:00:00Z"
    assert len(doc["onboarding"]["competitors"]) == 2


def test_a_note_the_seller_wrote_is_never_replaced(competitor_brief: CompetitorBrief) -> None:
    doc = _doc()
    doc["preferences"]["competitor_entries"] = [
        {"name": "Demand Curve", "url": "https://www.demandcurve.com/", "role": "price_reference",
         "rationale": "They charge $5k a month, I charge less", "reason": "Growth advisory",
         "selected": True},
    ]  # fmt: skip
    brief = _brief(competitor_brief, "Demand Curve sells growth playbooks to startups.")
    doc, entry, _ = merge_saved_competitor(
        doc, url="https://www.demandcurve.com", name="", brief=brief, now_iso=NOW
    )
    assert entry["rationale"] == "They charge $5k a month, I charge less"
    assert entry["role"] == "price_reference"
    assert entry["analysis_takeaway"] == "Demand Curve sells growth playbooks to startups."


def test_an_added_shop_joins_both_lists_and_respects_the_six_cap() -> None:
    doc, entry, added = merge_saved_competitor(
        _doc(), url="https://www.refinelabs.com", name="", now_iso=NOW
    )
    assert added is True and entry["name"] == "refinelabs.com" and entry["selected"] is True
    assert doc["onboarding"]["competitors"][-1]["url"] == "https://www.refinelabs.com"
    assert doc["preferences"]["competitor_entries"][-1]["url"] == "https://www.refinelabs.com"
    # Already watching six: the seventh is kept but not watched.
    full = _doc()
    full["onboarding"]["competitors"] = [
        {"name": f"Shop {i}", "url": f"https://shop{i}.test", "reason": "", "selected": True}
        for i in range(6)
    ]
    _, seventh, _ = merge_saved_competitor(full, url="https://seventh.test", now_iso=NOW)
    assert seventh["selected"] is False


def test_saved_briefs_are_capped_and_bad_addresses_refused(
    competitor_brief: CompetitorBrief,
) -> None:
    doc = _doc()
    for i in range(MAX_SAVED_BRIEFS + 2):
        doc, _, _ = merge_saved_competitor(
            doc, url=f"https://shop{i}.test", brief=competitor_brief, now_iso=NOW
        )
    assert len(doc["briefs"]) == MAX_SAVED_BRIEFS
    assert "https://shop0.test" not in doc["briefs"]
    assert f"https://shop{MAX_SAVED_BRIEFS + 1}.test" in doc["briefs"]
    with pytest.raises(ValueError):
        merge_saved_competitor(_doc(), url="not a url", now_iso=NOW)


def test_the_ranker_cites_the_saved_takeaway(competitor_brief: CompetitorBrief) -> None:
    brief = _brief(competitor_brief, "Clutch ranks B2B agencies by verified client reviews.")
    doc, _, _ = merge_saved_competitor(_doc(), url="https://clutch.co/", brief=brief, now_iso=NOW)
    from src.models.seller import CompetitorEntry

    entries = [CompetitorEntry.model_validate(e) for e in doc["preferences"]["competitor_entries"]]
    result = rank_seller_recommendations(
        business_name="n Plus Alpha Ventures",
        business_type="services",
        preferences=None,
        competitor_entries=entries,
    )
    assert "verified client reviews" in json.dumps(result)


class _Store:
    def __init__(self) -> None:
        self.slot: dict[str, Any] = {"document": _doc(), "version": 3, "owner_id": "u1"}
        self.saves: list[int | None] = []
        self.conflicts = 0


@pytest.fixture
def saved_route(monkeypatch: pytest.MonkeyPatch):
    store = _Store()
    account = AccountSession(
        user_id="u1", email="u1@walk.test", email_verified=True, access_token="t", session_id=None
    )

    async def fake_resolve(request: Any, _response: Any = None, require_verified: bool = False):
        if request.headers.get("x-test-signed-out"):
            raise HTTPException(401, "Sign in required")
        return account

    async def fake_load(_session: AccountSession) -> dict[str, Any]:
        return json.loads(json.dumps(store.slot))

    async def fake_save(_session, doc, expected_version=None, expected_owner=None):
        store.saves.append(expected_version)
        if store.conflicts:
            store.conflicts -= 1
            store.slot["version"] += 1  # another tab saved first
            raise HTTPException(409, "Your workspace changed. Reload before saving.")
        assert expected_version == store.slot["version"] and expected_owner == "u1"
        store.slot = {"document": doc, "version": store.slot["version"] + 1, "owner_id": "u1"}
        return json.loads(json.dumps(store.slot))

    monkeypatch.setattr(intel, "resolve_account", fake_resolve)
    monkeypatch.setattr(intel, "load_workspace", fake_load)
    monkeypatch.setattr(intel, "save_workspace", fake_save)
    return store


def _put(body: dict[str, Any], **headers: str):
    return TestClient(app).put(
        "/api/v1/competitors/saved", json=body, headers={"X-Muse-Owner": "u1", **headers}
    )


def test_route_saves_the_brief_and_retries_once_on_a_conflict(
    saved_route: _Store, brief_json: dict[str, Any]
) -> None:
    saved_route.conflicts = 1
    response = _put({"competitor_url": "https://clutch.co/", "name": "Clutch", "brief": brief_json})
    assert response.status_code == 200, response.text
    assert response.headers["cache-control"].startswith("private, no-store") or (
        "no-store" in response.headers["cache-control"]
    )
    data = response.json()
    assert data["saved"] is True and data["added"] is False
    assert data["competitor"]["rationale"] == data["competitor"]["analysis_takeaway"]
    assert saved_route.saves == [3, 4]  # reloaded and merged again after the conflict
    assert "https://clutch.co/" in saved_route.slot["document"]["briefs"]


def test_route_guards(saved_route: _Store) -> None:
    assert _put({"competitor_url": "https://x.test"}, **{"x-test-signed-out": "1"}).status_code == (
        401
    )
    no_owner = TestClient(app).put(
        "/api/v1/competitors/saved", json={"competitor_url": "https://x.test"}
    )
    assert no_owner.status_code == 409
    other = _put({"competitor_url": "https://x.test"}, **{"X-Muse-Owner": "someone-else"})
    assert other.status_code == 409
    social = _put({"competitor_url": "https://www.facebook.com/ads/library/?q=Clutch"})
    assert social.status_code == 422 and "Facebook or Instagram" in social.json()["detail"]
    assert _put({"competitor_url": "clutch dot co"}).status_code == 422
    assert saved_route.saves == []
