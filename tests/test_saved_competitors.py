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
from src.api.onboarding import OnboardingBuildRequest, _merged_preferences
from src.models.intel import CompetitorBrief
from src.services.accounts import AccountSession
from src.services.saved_competitors import (
    AD_LIBRARY_KEYWORD_LINK,
    MAX_SAVED_BRIEFS,
    ad_library_page_url,
    analysis_takeaway,
    merge_saved_competitor,
    parse_ad_library_page_id,
    remove_saved_competitors,
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


PAGE_LINK = (
    "https://www.facebook.com/ads/library/?active_status=active&ad_type=all&country=ALL"
    "&view_all_page_id=104958162837&search_type=page&media_type=all"
)
KEYWORD_LINK = (
    "https://www.facebook.com/ads/library/?active_status=active&ad_type=all&country=ALL"
    "&q=Clutch&search_type=keyword_unordered&media_type=all"
)


def test_only_an_advertiser_page_link_or_id_counts() -> None:
    assert parse_ad_library_page_id(PAGE_LINK) == "104958162837"
    assert parse_ad_library_page_id(" 104958162837 ") == "104958162837"
    assert parse_ad_library_page_id(PAGE_LINK.replace("https://www.", "")) == "104958162837"
    with pytest.raises(ValueError, match="keyword search"):
        parse_ad_library_page_id(KEYWORD_LINK)
    for bad in (
        "https://clutch.co/",
        "https://www.facebook.com/clutchco",
        "12",
        "evil.com/ads/library?view_all_page_id=104958162837",
    ):
        with pytest.raises(ValueError):
            parse_ad_library_page_id(bad)
    assert "view_all_page_id=104958162837" in ad_library_page_url("104958162837")


def test_page_link_is_kept_on_both_lists_and_can_be_removed() -> None:
    doc, entry, _ = merge_saved_competitor(
        _doc(), url="https://clutch.co/", ad_library_page_id="104958162837", now_iso=NOW
    )
    assert entry["ad_library_page_id"] == "104958162837"
    assert doc["onboarding"]["competitors"][0]["ad_library_page_id"] == "104958162837"
    doc, entry, _ = merge_saved_competitor(
        doc, url="https://clutch.co", ad_library_page_id="", now_iso=NOW
    )
    assert "ad_library_page_id" not in entry
    assert "ad_library_page_id" not in doc["onboarding"]["competitors"][0]


def test_route_links_a_page_and_refuses_a_keyword_search(saved_route: _Store) -> None:
    ok = _put({"competitor_url": "https://clutch.co/", "ad_library_url": PAGE_LINK})
    assert ok.status_code == 200, ok.text
    assert ok.json()["competitor"]["ad_library_page_id"] == "104958162837"
    assert "view_all_page_id=104958162837" in ok.json()["competitor"]["ad_library_url"]
    bad = _put({"competitor_url": "https://clutch.co/", "ad_library_url": KEYWORD_LINK})
    assert bad.status_code == 422 and bad.json()["detail"] == AD_LIBRARY_KEYWORD_LINK


def _analyzed_doc(competitor_brief: CompetitorBrief) -> dict[str, Any]:
    """Demand Curve linked to its Ad Library page, analyzed, with the seller's own note and role."""
    doc, _, _ = merge_saved_competitor(
        _doc(),
        url="https://www.demandcurve.com",
        brief=_brief(competitor_brief, "They sell a growth program to seed-stage founders."),
        ad_library_page_id="104958162837",
        now_iso=NOW,
    )
    entry = doc["preferences"]["competitor_entries"][1]
    entry.update(rationale="Same founders we pitch", role="price_reference")
    return doc


def test_editing_setup_keeps_each_competitors_page_and_analysis(
    competitor_brief: CompetitorBrief,
) -> None:
    """Nov 28: saving setup rebuilt the watchlist from setup's copy and dropped every saved page,
    analysis, note and role, which is what the seller adds on the home after setup."""
    doc = _analyzed_doc(competitor_brief)
    # What setup posts after loading the saved note and role (welcome.js `withSavedContext`);
    # the seller unticked nothing and removed Clutch.
    posted = [
        {**doc["onboarding"]["competitors"][1], "role": "price_reference",
         "rationale": "Same founders we pitch"},
    ]  # fmt: skip
    body = OnboardingBuildRequest(edit=True, competitors=posted)
    entries = _merged_preferences(body, doc, keep_existing=True)["competitor_entries"]
    assert [e["url"] for e in entries] == ["https://www.demandcurve.com"]
    kept = entries[0]
    assert kept["ad_library_page_id"] == "104958162837"
    assert kept["analysis_takeaway"].startswith("They sell a growth program")
    assert kept["analyzed_at"] == NOW and kept["analysis_summary"]
    assert kept["rationale"] == "Same founders we pitch" and kept["role"] == "price_reference"
    # A first build has nothing to keep; an edit never revives a competitor setup removed.
    first = _merged_preferences(OnboardingBuildRequest(competitors=posted), {}, keep_existing=False)
    assert "analysis_takeaway" not in first["competitor_entries"][0]
    # A page ID that isn't 5 to 20 digits is never copied from setup's answers.
    junk = OnboardingBuildRequest(
        competitors=[{"url": "https://x.test", "ad_library_page_id": "1"}]
    )
    assert "ad_library_page_id" not in _merged_preferences(junk, {})["competitor_entries"][0]


def test_removing_takes_competitors_off_both_lists_and_keeps_their_analysis(
    competitor_brief: CompetitorBrief,
) -> None:
    doc = _analyzed_doc(competitor_brief)
    doc["preferences"]["watch"] = {
        "competitor_urls": ["https://clutch.co/", "https://www.demandcurve.com"]
    }
    doc["onboarding"]["preferences"] = {"watch": {"competitor_urls": ["https://clutch.co"]}}
    before = json.loads(json.dumps(doc))
    out, removed = remove_saved_competitors(doc, ["https://www.demandcurve.com/", "https://x.test"])
    assert removed == ["Demand Curve"]
    assert [c["url"] for c in out["onboarding"]["competitors"]] == ["https://clutch.co/"]
    assert [e["url"] for e in out["preferences"]["competitor_entries"]] == ["https://clutch.co/"]
    assert out["preferences"]["watch"]["competitor_urls"] == ["https://clutch.co/"]
    assert "https://www.demandcurve.com" in out["briefs"]  # "View analysis" if they come back
    assert doc == before  # the input document is never changed
    out, removed = remove_saved_competitors(out, ["clutch.co"])
    assert removed == ["Clutch B2B Marketing Directory"]
    assert out["onboarding"]["competitors"] == [] and out["preferences"]["competitor_entries"] == []
    assert out["onboarding"]["preferences"]["watch"]["competitor_urls"] == []
    assert remove_saved_competitors({}, ["https://clutch.co"]) == ({}, [])


def _remove(urls: list[str], **headers: str):
    return TestClient(app).post(
        "/api/v1/competitors/saved/remove",
        json={"urls": urls},
        headers={"X-Muse-Owner": "u1", **headers},
    )


def test_route_removes_competitors_and_returns_the_setup_rows(saved_route: _Store) -> None:
    signed_out = _remove(["https://clutch.co/"], **{"x-test-signed-out": "1"})
    assert signed_out.status_code == 401
    assert _remove(["https://clutch.co/"], **{"X-Muse-Owner": "someone-else"}).status_code == 409
    assert _remove([]).status_code == 422
    nothing = _remove(["https://not-watched.test"])
    assert nothing.status_code == 200 and nothing.json()["removed"] == []
    assert saved_route.saves == []  # nothing to remove, nothing saved
    saved_route.conflicts = 1
    ok = _remove(["https://clutch.co/"])
    assert ok.status_code == 200, ok.text
    assert "no-store" in ok.headers["cache-control"]
    data = ok.json()
    assert data["removed"] == ["Clutch B2B Marketing Directory"]
    assert [c["name"] for c in data["onboarding"]["competitors"]] == ["Demand Curve"]
    assert saved_route.saves == [3, 4]  # reloaded and removed again after the conflict
    assert [c["url"] for c in saved_route.slot["document"]["onboarding"]["competitors"]] == [
        "https://www.demandcurve.com"
    ]
