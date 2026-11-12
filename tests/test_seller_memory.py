"""Backend unit & API tests for Seller Memory (PRD Section 12, Batch 1)."""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

from src.api.main import app
from src.config import get_settings
from src.models.intel import SitemapEntry
from src.models.seller import (
    AccessPreferences,
    CompetitorEntry,
    SellerMemoryEntry,
    SellerPreferences,
)
from src.services.accounts import AccountSession
from src.utils.sitemap import SitemapError


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def _install_multi_account_workspace(
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[dict[str, dict[str, Any]], dict[str, AccountSession]]:
    """Install in-memory stateful workspace store supporting optimistic versioning & A/B users."""
    stores: dict[str, dict[str, Any]] = {
        "user-a": {"document": {}, "version": 1, "owner_id": "user-a"},
        "user-b": {"document": {}, "version": 1, "owner_id": "user-b"},
    }
    accounts = {
        "user-a": AccountSession(
            user_id="user-a",
            email="watercolor@example.test",
            email_verified=True,
            access_token="tok-a",
            session_id=None,
        ),
        "user-b": AccountSession(
            user_id="user-b",
            email="ceramics@example.test",
            email_verified=True,
            access_token="tok-b",
            session_id=None,
        ),
    }

    async def fake_resolve(request: Any, _response: Any = None, require_verified: bool = False):
        auth_uid = request.headers.get("x-test-user")
        if not auth_uid:
            if require_verified:
                from fastapi import HTTPException

                raise HTTPException(401, "Sign in required")
            return None
        return accounts[auth_uid]

    async def fake_load(account: AccountSession) -> dict[str, Any]:
        slot = stores[account.user_id]
        return {
            "document": dict(slot["document"]),
            "version": int(slot["version"]),
            "owner_id": account.user_id,
        }

    async def fake_save(
        account: AccountSession,
        doc: dict[str, Any],
        expected_version: Any = None,
        expected_owner: Any = None,
    ) -> dict[str, Any]:
        from fastapi import HTTPException

        if expected_owner and expected_owner != account.user_id:
            raise HTTPException(409, "Workspace owner mismatch")
        slot = stores[account.user_id]
        if expected_version is not None and int(expected_version) != int(slot["version"]):
            raise HTTPException(409, "Workspace version conflict")
        slot["document"] = dict(doc)
        slot["version"] = int(slot["version"]) + 1
        return {
            "document": dict(doc),
            "version": int(slot["version"]),
            "owner_id": account.user_id,
        }

    for mod in (
        "src.api.seller_memory",
        "src.api.preferences",
        "src.api.onboarding",
    ):
        monkeypatch.setattr(f"{mod}.resolve_account", fake_resolve)
        monkeypatch.setattr(f"{mod}.load_workspace", fake_load)
        monkeypatch.setattr(f"{mod}.save_workspace", fake_save)

    return stores, accounts


def test_shop_scan_separates_observations_from_interpretations_and_no_invented_prices(
    monkeypatch: pytest.MonkeyPatch, client: TestClient
) -> None:
    """Shop scan labels observations vs interpretations, preserves source+date, never invents $."""

    async def fake_collect(url: str, **_kwargs: Any) -> tuple[list[SitemapEntry], list[str]]:
        if "blocked-portfolio" in url:
            raise SitemapError("Blocked by robots policy")
        return (
            [
                SitemapEntry(
                    loc="https://wildmeadow.test/prints/meadow-mist",
                    bucket="products",
                    title="Meadow Mist Archival Watercolor Print — Gift Edition",
                    price_hint=None,  # Deliberately absent! Must NOT invent prices!
                )
            ],
            ["https://wildmeadow.test/sitemap.xml"],
        )

    monkeypatch.setattr("src.api.seller_memory.collect_entries", fake_collect)
    monkeypatch.setattr("src.api.intel.collect_entries", fake_collect)

    # First check ingest-storefront directly returns honest empty price range instead of $14-$22
    ingest_resp = client.post(
        "/api/v1/ingest-storefront",
        json={"business_name": "Wild Meadow Studio", "website_url": "https://wildmeadow.test"},
    )
    assert ingest_resp.status_code == 200
    ingest_data = ingest_resp.json()
    assert ingest_data["detected_price_hints"] == []
    assert "No public prices detected on crawled pages" in ingest_data["seller_context"]

    # Now check Seller Memory scan endpoint with one open site and one failing extra URL
    scan_resp = client.post(
        "/api/v1/seller-memory/scan",
        json={
            "business_name": "Wild Meadow Studio",
            "website_url": "https://wildmeadow.test",
            "extra_urls": ["https://blocked-portfolio.test/about"],
        },
    )
    assert scan_resp.status_code == 200
    data = scan_resp.json()
    assert data["runs_used"] == 0
    assert data["scan_date"]
    assert any("Blocked" in w for w in data["partial_warnings"])

    proposals = data["proposed_entries"]
    observations = [p for p in proposals if p["kind"] == "observation"]
    interpretations = [p for p in proposals if p["kind"] == "interpretation"]
    assert observations, "Expected at least one observed fact"
    assert interpretations, "Expected at least one interpretation"
    assert all(p["source_url"] and p["scan_date"] for p in proposals)
    assert all(p["confidence"] == "inferred" and p["uncertainty"] for p in interpretations)
    # Must NOT invent a price_range observation when none was detected
    assert not any(p["key"] == "price_range" for p in proposals)

    serialized_all = str(data).lower()
    for banned in ("sikh", "sarabjit", "sikhiart", "$14", "$22"):
        assert banned not in serialized_all


def test_rescan_diff_preserves_seller_edited_observation(client: TestClient) -> None:
    """Rescanning proposes diff changes while marking manually edited entries as preserved."""
    edited_price = SellerMemoryEntry(
        id="obs-price-range",
        key="price_range",
        label="Observed listing prices",
        value="Archival watercolor prints start at $42",
        kind="observation",
        scope="product",
        source="shop_scan",
        source_url="https://wildmeadow.test/prints",
        scan_date="2026-11-10",
        confidence="observed",
        status="accepted",
        seller_edited=True,
    )

    resp = client.post(
        "/api/v1/seller-memory/scan",
        json={
            "business_name": "Wild Meadow Studio",
            "website_url": "https://wildmeadow.test",
            "snapshot_items": [
                {
                    "url": "https://wildmeadow.test/prints/valley",
                    "title": "Valley Mist Watercolor Print",
                    "bucket": "products",
                    "price_hint": "$35",
                }
            ],
            "existing_entries": [edited_price.model_dump(mode="json")],
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["preserved_edits_count"] == 1
    diffs = data["diff"]
    price_diff = next(d for d in diffs if d["key"] == "price_range")
    assert price_diff["change_type"] == "changed"
    assert price_diff["before_value"] == "Archival watercolor prints start at $42"
    assert "$35" in price_diff["after_value"]
    assert price_diff["preserves_seller_edit"] is True


def test_voice_fixture_consent_gate_and_conflict_detection(
    monkeypatch: pytest.MonkeyPatch, client: TestClient
) -> None:
    """Voice fixture parses cleanly at 0 runs; live enforces consent & demo gate before billing."""
    from src.api import demo as demo_api
    from src.services import usage_meter

    fixtures_resp = client.get("/api/v1/seller-memory/voice-fixtures")
    assert fixtures_resp.status_code == 200
    fixtures = fixtures_resp.json()["fixtures"]
    assert any(f["id"] == "watercolor_studio" for f in fixtures)

    provider_calls: list[dict[str, Any]] = []
    billing_calls: list[str] = []

    class FakeMetaClient:
        async def transcribe_audio(
            self, audio_bytes: bytes, *, filename: str = "voice.webm", mime_type: str = "audio/webm"
        ) -> str:
            provider_calls.append(
                {"size": len(audio_bytes), "filename": filename, "mime_type": mime_type}
            )
            return "I have 20 minutes a week and my linen prints are EUR 40."

    async def spy_authorize(
        user_id: str, ip_hash: str, op_id: str, session_id: str | None = None
    ) -> str:
        billing_calls.append(f"authorize:{user_id}")
        return "op-voice-1"

    async def spy_finish(outcome: str, operation_id: str = "") -> None:
        billing_calls.append(f"finish:{outcome}:{operation_id}")

    async def spy_spend(*args: Any, **kwargs: Any):
        billing_calls.append("spend_credit")
        yield True

    monkeypatch.setattr("src.api.seller_memory.get_meta_client", lambda: FakeMetaClient())
    monkeypatch.setattr(usage_meter, "authorize_operation", spy_authorize)
    monkeypatch.setattr(usage_meter, "finish_operation", spy_finish)
    monkeypatch.setattr(demo_api, "_spend_credit", spy_spend)
    monkeypatch.setenv("DEMO_MODE", "true")
    monkeypatch.setenv("DEMO_KEY", "unit-demo-key")
    monkeypatch.setenv("ACCOUNTS_REQUIRED", "false")
    get_settings.cache_clear()

    try:
        # 1. Missing consent fails with 400 BEFORE demo/billing/provider even with ?live=true
        bad_consent = client.post(
            "/api/v1/seller-memory/voice/transcribe?live=true",
            headers={"X-Demo-Key": "unit-demo-key"},
            json={"audio_base64": "dGVzdA==", "filename": "note.webm", "consent_confirmed": False},
        )
        assert bad_consent.status_code == 400
        assert provider_calls == []
        assert billing_calls == []

        # 2. In explicit DEMO_MODE=true without live=true, consented call returns 403
        no_live = client.post(
            "/api/v1/seller-memory/voice/transcribe",
            json={"audio_base64": "dGVzdA==", "filename": "note.webm", "consent_confirmed": True},
        )
        assert no_live.status_code == 403
        assert provider_calls == []
        assert billing_calls == []

        # 3. With ?live=true but invalid X-Demo-Key in demo mode -> 403 (0 provider/billing calls)
        bad_key = client.post(
            "/api/v1/seller-memory/voice/transcribe?live=true",
            headers={"X-Demo-Key": "wrong-key"},
            json={"audio_base64": "dGVzdA==", "filename": "note.webm", "consent_confirmed": True},
        )
        assert bad_key.status_code == 403
        assert provider_calls == []
        assert billing_calls == []

        # 4. Eligible mocked live request with consent + valid key invokes provider
        ok_live = client.post(
            "/api/v1/seller-memory/voice/transcribe?live=true",
            headers={"X-Demo-Key": "unit-demo-key"},
            json={"audio_base64": "dGVzdA==", "filename": "note.webm", "consent_confirmed": True},
        )
        assert ok_live.status_code == 200
        assert "EUR 40" in ok_live.json()["transcript"]
        assert len(provider_calls) == 1

        # 5. Accounts-required eligible live rejects without consent BEFORE billing
        provider_calls.clear()
        billing_calls.clear()
        monkeypatch.setenv("ACCOUNTS_REQUIRED", "true")
        get_settings.cache_clear()
        _, accounts = _install_multi_account_workspace(monkeypatch)

        async def _fake_acct_resolve(
            request: Any, _response: Any = None, require_verified: bool = False
        ):
            uid = request.headers.get("x-test-user")
            return accounts[uid] if uid else None

        monkeypatch.setattr("src.services.accounts.resolve_account", _fake_acct_resolve)

        no_consent_acct = client.post(
            "/api/v1/seller-memory/voice/transcribe?live=true",
            headers={"X-Test-User": "user-a"},
            json={"audio_base64": "dGVzdA==", "filename": "note.webm", "consent_confirmed": False},
        )
        assert no_consent_acct.status_code == 400
        assert provider_calls == []
        assert billing_calls == []

        ok_acct = client.post(
            "/api/v1/seller-memory/voice/transcribe?live=true",
            headers={"X-Test-User": "user-a"},
            json={"audio_base64": "dGVzdA==", "filename": "note.webm", "consent_confirmed": True},
        )
        assert ok_acct.status_code == 200
        assert len(provider_calls) == 1
        assert billing_calls == ["authorize:user-a", "finish:completed:op-voice-1"]
    finally:
        monkeypatch.undo()
        get_settings.cache_clear()

    # Demo voice fixture parses cleanly at 0 runs and flags conflicts without auto-saving
    existing = SellerMemoryEntry(
        id="obs-price-range",
        key="price_range",
        label="Observed listing prices",
        value="Prints start at $28",
        kind="observation",
        scope="product",
        source="shop_scan",
        status="accepted",
    )
    interp = client.post(
        "/api/v1/seller-memory/interpret",
        json={
            "source_type": "voice_demo_fixture",
            "fixture_id": "watercolor_studio",
            "existing_entries": [existing.model_dump(mode="json")],
        },
    )
    assert interp.status_code == 200
    body = interp.json()
    assert body["runs_used"] == 0
    assert body["source_type"] == "voice_demo_fixture"
    keys = {p["key"] for p in body["proposed_entries"]}
    assert {"minutes_per_week", "subjects_to_avoid", "price_range"} <= keys
    assert any(c["key"] == "price_range" for c in body["conflicts"])


def test_competitor_role_change_shifts_top_recommendation_and_draft_override_stays_temporary(
    monkeypatch: pytest.MonkeyPatch, client: TestClient
) -> None:
    """Competitor role changes shift top recommendation; draft override leaves defaults."""
    stores, _ = _install_multi_account_workspace(monkeypatch)
    pref = SellerPreferences(
        goal="Sell archival watercolor prints",
        audience="Gift buyers",
        access=AccessPreferences(minutes_per_week=25, channels=["instagram"]),
    )
    stores["user-a"]["document"] = {
        "onboarding": {"business_name": "Wild Meadow Watercolor"},
        "preferences": pref.model_dump(mode="json"),
    }

    # First: watched competitor has role == similar_audience
    r1 = client.post(
        "/api/v1/seller-memory/recommend",
        headers={"X-Test-User": "user-a", "X-Muse-Owner": "user-a"},
        json={
            "business_name": "Wild Meadow Watercolor",
            "product_name": "Morning Mist 8x10 Print",
            "preferences": pref.model_dump(mode="json"),
            "competitor_entries": [
                {
                    "name": "Riverbend Studio",
                    "url": "https://riverbend.test",
                    "role": "similar_audience",
                    "rationale": "Strong gift packaging for home buyers",
                    "selected": True,
                }
            ],
        },
    )
    assert r1.status_code == 200
    top1 = r1.json()["recommendations"][0]
    assert top1["id"] == "move-similar-audience"
    assert "Similar audience" in top1["why_this_fits"]

    # Switch SAME competitor to role == price_reference -> top recommendation & rationale must shift
    r2 = client.post(
        "/api/v1/seller-memory/recommend",
        headers={"X-Test-User": "user-a", "X-Muse-Owner": "user-a"},
        json={
            "business_name": "Wild Meadow Watercolor",
            "product_name": "Morning Mist 8x10 Print",
            "preferences": pref.model_dump(mode="json"),
            "previous_top_id": top1["id"],
            "competitor_entries": [
                {
                    "name": "Riverbend Studio",
                    "url": "https://riverbend.test",
                    "role": "price_reference",
                    "rationale": "Anchor entry prints around $35",
                    "selected": True,
                }
            ],
        },
    )
    assert r2.status_code == 200
    d2 = r2.json()
    top2 = d2["recommendations"][0]
    assert top2["id"] == "move-price-positioning"
    assert d2["what_changed"]
    assert "Price reference" in top2["why_this_fits"]
    assert "Anchor entry prints around $35" in top2["why_this_fits"]
    assert d2["editor_defaults"]["goal"] == "visit"

    # Temporary draft override changes ranker output without mutating persisted workspace
    r3 = client.post(
        "/api/v1/seller-memory/recommend",
        headers={"X-Test-User": "user-a", "X-Muse-Owner": "user-a"},
        json={
            "business_name": "Wild Meadow Watercolor",
            "product_name": "Morning Mist 8x10 Print",
            "draft_override": {
                "goal": "story and studio process",
                "minutes_per_week": 15,
                "price_claim": "$35",
            },
        },
    )
    assert r3.status_code == 200
    assert "temporary draft-only context" in (r3.json()["what_changed"] or "").lower()
    assert stores["user-a"]["document"]["preferences"]["access"]["minutes_per_week"] == 25


def test_conflict_409_forget_entry_feedback_suggestions_and_owner_isolation(
    monkeypatch: pytest.MonkeyPatch, client: TestClient
) -> None:
    """Verify optimistic 409 conflict, entry deletion, suggestion approval, and A/B isolation."""
    stores, _ = _install_multi_account_workspace(monkeypatch)

    # Save initial profile on Account A
    entry_goal = SellerMemoryEntry(
        id="pref-goal",
        key="goal",
        label="Main goal",
        value="Highlight botanical prints",
        kind="preference",
        scope="shop_default",
        source="user_input",
        status="accepted",
    )
    entry_avoid = SellerMemoryEntry(
        id="pref-avoid",
        key="subjects_to_avoid",
        label="Avoid words",
        value="cheap",
        kind="preference",
        scope="shop_default",
        source="user_input",
        status="accepted",
    )
    comp = CompetitorEntry(
        name="Flora Press",
        url="https://florapress.test",
        role="inspiration",
        rationale="Clean brush close-ups",
    )

    save1 = client.put(
        "/api/v1/seller-memory",
        headers={"X-Test-User": "user-a", "X-Muse-Owner": "user-a"},
        json={
            "expected_version": 1,
            "expected_owner": "user-a",
            "preferences": {
                "goal": "Highlight botanical prints",
                "access": {"minutes_per_week": 30},
            },
            "memory_entries": [
                entry_goal.model_dump(mode="json"),
                entry_avoid.model_dump(mode="json"),
            ],
            "competitor_entries": [comp.model_dump(mode="json")],
        },
    )
    assert save1.status_code == 200
    v2 = save1.json()["version"]
    assert v2 == 2

    # Stale expected_version == 1 triggers 409 returning BOTH server state for conflict resolution
    conflict = client.put(
        "/api/v1/seller-memory",
        headers={"X-Test-User": "user-a", "X-Muse-Owner": "user-a"},
        json={
            "expected_version": 1,
            "expected_owner": "user-a",
            "preferences": {
                "goal": "Push holiday commissions",
                "access": {"minutes_per_week": 20},
            },
        },
    )
    assert conflict.status_code == 409
    c_body = conflict.json()
    assert c_body["server_version"] == 2
    assert c_body["server_preferences"]["goal"] == "Highlight botanical prints"
    assert len(c_body["server_memory_entries"]) == 2

    # Owner mismatch header must fail cleanly and never leak to user-b
    wrong_owner = client.put(
        "/api/v1/seller-memory",
        headers={"X-Test-User": "user-b", "X-Muse-Owner": "user-a"},
        json={"expected_version": 1, "expected_owner": "user-a"},
    )
    assert wrong_owner.status_code == 409

    # Account B reads its own isolated memory (zero Account A leaks, zero sample-shop leaks)
    mem_b = client.get(
        "/api/v1/seller-memory",
        headers={"X-Test-User": "user-b", "X-Muse-Owner": "user-b"},
    )
    assert mem_b.status_code == 200
    assert mem_b.json()["memory_entries"] == []
    assert "botanical" not in str(mem_b.json()).lower()

    # Delete/forget entry on Account A -> stops appearing in memory & avoid list
    del_resp = client.delete(
        "/api/v1/seller-memory/entries/pref-avoid",
        headers={"X-Test-User": "user-a", "X-Muse-Owner": "user-a"},
    )
    assert del_resp.status_code == 200
    assert "cheap" not in del_resp.json()["preferences"]["taste"]["subjects_to_avoid"]
    assert all(e["id"] != "pref-avoid" for e in del_resp.json()["memory_entries"])

    # Repeated 'too_much_time' dismiss signals create a PENDING suggestion WITHOUT auto-applying!
    sig_resp = client.post(
        "/api/v1/preferences/signals",
        headers={"X-Test-User": "user-a", "X-Muse-Owner": "user-a"},
        json={
            "expected_owner": "user-a",
            "dismiss_signals": [
                {"id": "m1", "title": "Long post", "reason": "too_much_time"},
                {"id": "m2", "title": "Multi edit", "reason": "too_much_time"},
            ],
        },
    )
    assert sig_resp.status_code == 200
    s_data = sig_resp.json()
    assert s_data["pending_suggestions_count"] >= 1
    assert any(s["id"] == "suggest-prefer-15min" for s in s_data["suggested_updates"])
    # Crucially, minutes_per_week MUST STILL BE 30 until explicitly approved!
    assert stores["user-a"]["document"]["preferences"]["access"]["minutes_per_week"] == 30

    # Approve the suggestion explicitly -> now minutes_per_week becomes 15
    app_resp = client.post(
        "/api/v1/seller-memory/suggestions/suggest-prefer-15min/respond",
        headers={"X-Test-User": "user-a", "X-Muse-Owner": "user-a"},
        json={"decision": "approve", "expected_owner": "user-a"},
    )
    assert app_resp.status_code == 200
    assert app_resp.json()["preferences"]["access"]["minutes_per_week"] == 15
    assert any(
        e["key"] == "minutes_per_week" and "15" in e["value"]
        for e in app_resp.json()["memory_entries"]
    )


def test_put_requires_explicit_expected_version_and_preserves_unknown_extras(
    monkeypatch: pytest.MonkeyPatch, client: TestClient
) -> None:
    """PUT requires expected_version (409 when omitted) and preserves unknown extras."""
    stores, _ = _install_multi_account_workspace(monkeypatch)
    stores["user-a"]["version"] = 3
    stores["user-a"]["document"] = {
        "onboarding": {"business_name": "Studio North"},
        "preferences": {
            "goal": "Promote studio prints",
            "future_pref_flag": "keep-me",
            "access": {
                "minutes_per_week": 30,
                "channels": ["instagram"],
                "future_access_slot": "weekends",
            },
            "taste": {"tone": "warm", "future_taste_palette": "ochre"},
            "memory_entries": [
                {
                    "id": "obs-p1",
                    "key": "price_range",
                    "label": "Price range",
                    "value": "Prints start at EUR 45",
                    "kind": "observation",
                    "scope": "product",
                    "source": "shop_scan",
                    "status": "accepted",
                    "custom_entry_meta": "keep-entry",
                },
                {
                    "id": "pref-avoid",
                    "key": "subjects_to_avoid",
                    "label": "Avoid",
                    "value": "flashy",
                    "kind": "preference",
                    "scope": "shop_default",
                    "source": "user_input",
                    "status": "accepted",
                },
            ],
            "competitor_entries": [
                {
                    "name": "Peer One",
                    "url": "https://peer.example.test",
                    "role": "similar_audience",
                    "selected": True,
                    "custom_comp_flag": 42,
                }
            ],
        },
        "voice_profile": {"formality": "casual", "future_voice_marker": "poetic"},
        "dismiss_signals": [
            {"id": "d1", "title": "Long post", "reason": "too_much_time"},
            {"id": "d2", "title": "Complex shoot", "reason": "too_much_time"},
        ],
    }

    # 1. Missing expected_version returns 409 conflict with snapshots
    no_ver = client.put(
        "/api/v1/seller-memory",
        headers={"X-Test-User": "user-a", "X-Muse-Owner": "user-a"},
        json={"preferences": {"goal": "Stale client overwrite"}},
    )
    assert no_ver.status_code == 409
    assert no_ver.json()["server_version"] == 3
    assert stores["user-a"]["document"]["preferences"]["goal"] == "Promote studio prints"

    # 2. Explicit matching PUT preserves unknown fields at root & nested models
    ok_put = client.put(
        "/api/v1/seller-memory",
        headers={"X-Test-User": "user-a", "X-Muse-Owner": "user-a"},
        json={
            "expected_version": 3,
            "expected_owner": "user-a",
            "preferences": {
                "goal": "Sell winter gift prints",
                "access": {"minutes_per_week": 20, "channels": ["instagram"]},
                "taste": {"tone": "personal"},
            },
            "voice_profile": {"formality": "formal"},
            "memory_entries": stores["user-a"]["document"]["preferences"]["memory_entries"],
            "competitor_entries": stores["user-a"]["document"]["preferences"]["competitor_entries"],
        },
    )
    assert ok_put.status_code == 200
    put_body = ok_put.json()
    assert put_body["preferences"]["future_pref_flag"] == "keep-me"
    assert put_body["preferences"]["access"]["future_access_slot"] == "weekends"
    assert put_body["preferences"]["taste"]["future_taste_palette"] == "ochre"
    assert put_body["voice_profile"]["future_voice_marker"] == "poetic"
    assert put_body["memory_entries"][0]["custom_entry_meta"] == "keep-entry"
    assert put_body["competitor_entries"][0]["custom_comp_flag"] == 42

    # 3. DELETE entry preserves all unknown fields
    del_resp = client.delete(
        "/api/v1/seller-memory/entries/pref-avoid",
        headers={"X-Test-User": "user-a", "X-Muse-Owner": "user-a"},
    )
    assert del_resp.status_code == 200
    del_body = del_resp.json()
    assert del_body["preferences"]["future_pref_flag"] == "keep-me"
    assert del_body["preferences"]["access"]["future_access_slot"] == "weekends"
    assert del_body["preferences"]["taste"]["future_taste_palette"] == "ochre"
    assert del_body["voice_profile"]["future_voice_marker"] == "poetic"

    # 4. Suggestions evaluate & respond preserve all unknown fields
    eval_resp = client.post(
        "/api/v1/seller-memory/suggestions/evaluate",
        headers={"X-Test-User": "user-a", "X-Muse-Owner": "user-a"},
    )
    assert eval_resp.status_code == 200
    assert stores["user-a"]["document"]["preferences"]["future_pref_flag"] == "keep-me"

    app_resp = client.post(
        "/api/v1/seller-memory/suggestions/suggest-prefer-15min/respond",
        headers={"X-Test-User": "user-a", "X-Muse-Owner": "user-a"},
        json={"decision": "approve", "expected_owner": "user-a"},
    )
    assert app_resp.status_code == 200
    app_body = app_resp.json()
    assert app_body["preferences"]["access"]["minutes_per_week"] == 15
    assert app_body["preferences"]["future_pref_flag"] == "keep-me"
    assert app_body["preferences"]["access"]["future_access_slot"] == "weekends"
    assert app_body["preferences"]["taste"]["future_taste_palette"] == "ochre"
    assert app_body["voice_profile"]["future_voice_marker"] == "poetic"


def test_context_truth_currency_product_destination_ignore_and_all_channels_excluded(
    monkeypatch: pytest.MonkeyPatch, client: TestClient
) -> None:
    """Currency, product/destination scope, ignore keys, and channel exclusions hold."""

    async def fake_collect(*args: Any, **kwargs: Any) -> tuple[list[SitemapEntry], list[str]]:
        return (
            [
                SitemapEntry(
                    loc="https://euroatelier.example/prints/alpine-STUDY",
                    title="Alpine Study 8x10 Print — EUR 45",
                    bucket="products",
                    price_hint="EUR 45",
                )
            ],
            ["https://euroatelier.example/sitemap.xml"],
        )

    monkeypatch.setattr("src.api.seller_memory.collect_entries", fake_collect)
    scan_resp = client.post(
        "/api/v1/seller-memory/scan",
        json={
            "website_url": "https://euroatelier.example",
            "business_name": "Euro Atelier",
            "product_key": "Alpine Study",
            "destination": "website",
        },
    )
    assert scan_resp.status_code == 200
    price_obs = next(e for e in scan_resp.json()["proposed_entries"] if e["key"] == "price_range")
    assert "EUR 45" in price_obs["value"]
    assert "$" not in price_obs["value"]
    assert price_obs["source_url"] == "https://euroatelier.example/prints/alpine-STUDY"
    assert price_obs["product_key"] == "Alpine Study"
    assert price_obs["destination"] == "website"

    # Two-product, two-destination, and ignore_entry_ids vs ignored_entry_ids before defaults
    entries = [
        SellerMemoryEntry(
            id="obs-euro-website",
            key="price_range",
            label="Website price",
            value="Prints start at EUR 45",
            kind="observation",
            scope="product",
            product_key="Alpine Study",
            destination="website",
            source="shop_scan",
            status="accepted",
        ),
        SellerMemoryEntry(
            id="obs-usd-etsy",
            key="price_range",
            label="Etsy price",
            value="Prints start at $28",
            kind="observation",
            scope="product",
            product_key="Meadow Mug",
            destination="etsy",
            source="shop_scan",
            status="accepted",
        ),
        SellerMemoryEntry(
            id="obs-alpine-etsy",
            key="price_range",
            label="Alpine Study Etsy price",
            value="Prints start at $39",
            kind="observation",
            scope="product",
            product_key="Alpine Study",
            destination="etsy",
            source="shop_scan",
            status="accepted",
        ),
        SellerMemoryEntry(
            id="pref-goal",
            key="goal",
            label="Goal",
            value="more studio visits",
            kind="goal",
            scope="shop_default",
            source="user_input",
            status="accepted",
        ),
        SellerMemoryEntry(
            id="pref-min",
            key="minutes_per_week",
            label="Weekly time budget",
            value="60 minutes / week",
            kind="preference",
            scope="shop_default",
            source="user_input",
            status="accepted",
        ),
        SellerMemoryEntry(
            id="pref-avoid",
            key="subjects_to_avoid",
            label="Avoid",
            value="flashy, urgent",
            kind="preference",
            scope="shop_default",
            source="user_input",
            status="accepted",
        ),
    ]
    pref = SellerPreferences(
        goal="default shop goal",
        access=AccessPreferences(minutes_per_week=30, channels=["instagram", "facebook"]),
        memory_entries=entries,
    )

    # Scoped to Alpine Study on website -> EUR 45 (never USD or Meadow Mug's $28)
    rec_eur = client.post(
        "/api/v1/seller-memory/recommend",
        json={
            "business_name": "Euro Atelier",
            "product_name": "Alpine Study",
            "preferences": pref.model_dump(mode="json"),
            "draft_override": {
                "active": True,
                "product_name": "Alpine Study",
                "destination": "website",
            },
            "competitor_entries": [
                CompetitorEntry(
                    name="Price Peer",
                    url="https://pricepeer.example",
                    role="price_reference",
                    selected=True,
                ).model_dump(mode="json")
            ],
        },
    ).json()
    assert rec_eur["editor_defaults"]["price_claim"] == "EUR 45"
    assert "EUR 45" in rec_eur["recommendations"][0]["title"]
    # Non-top recommendation carries its own distinct editor_defaults
    rec0_def = rec_eur["recommendations"][0]["editor_defaults"]
    rec1_def = rec_eur["recommendations"][1]["editor_defaults"]
    assert rec0_def["recommendation_id"] != rec1_def["recommendation_id"]
    assert rec0_def["recommendation_title"] != rec1_def["recommendation_title"]

    # Scoped to Meadow Mug on etsy -> $28 (never EUR 45)
    rec_usd = client.post(
        "/api/v1/seller-memory/recommend",
        json={
            "business_name": "Euro Atelier",
            "product_name": "Meadow Mug",
            "preferences": pref.model_dump(mode="json"),
            "draft_override": {"active": True, "product_name": "Meadow Mug", "destination": "etsy"},
        },
    ).json()
    assert rec_usd["editor_defaults"]["price_claim"] == "$28"

    # Unscoped query when 2 distinct product/destination facts exist must NOT guess either one!
    rec_unscoped = client.post(
        "/api/v1/seller-memory/recommend",
        json={
            "business_name": "Euro Atelier",
            "preferences": pref.model_dump(mode="json"),
        },
    ).json()
    assert rec_unscoped["editor_defaults"]["price_claim"] == ""

    # Same product (Alpine Study) WITHOUT destination when 2 destinations exist stays unknown!
    rec_ambig_dest = client.post(
        "/api/v1/seller-memory/recommend",
        json={
            "business_name": "Euro Atelier",
            "product_name": "Alpine Study",
            "preferences": pref.model_dump(mode="json"),
        },
    ).json()
    assert rec_ambig_dest["editor_defaults"]["price_claim"] == ""

    # Both ignore_entry_ids AND ignored_entry_ids exclude entries BEFORE deriving defaults
    for key_name in ("ignore_entry_ids", "ignored_entry_ids"):
        rec_ignored = client.post(
            "/api/v1/seller-memory/recommend",
            json={
                "business_name": "Euro Atelier",
                "product_name": "Alpine Study",
                "preferences": pref.model_dump(mode="json"),
                "draft_override": {
                    "active": True,
                    "product_name": "Alpine Study",
                    "destination": "website",
                    key_name: ["pref-min", "pref-goal", "obs-euro-website", "pref-avoid"],
                },
            },
        ).json()
        assert rec_ignored["editor_defaults"]["minutes_per_week"] == 30
        assert rec_ignored["editor_defaults"]["context_summary"] == ""
        assert rec_ignored["editor_defaults"]["price_claim"] == ""
        assert rec_ignored["editor_defaults"]["words_to_avoid"] == []
        used_ids = {u["id"] for r in rec_ignored["recommendations"] for u in r["used_entries"]}
        assert not (used_ids & {"pref-min", "pref-goal", "obs-euro-website", "pref-avoid"})

    # All channels excluded must NEVER reintroduce "website" -> empty moves + missing_info_prompt
    rec_no_ch = client.post(
        "/api/v1/seller-memory/recommend",
        json={
            "business_name": "Euro Atelier",
            "preferences": pref.model_dump(mode="json"),
            "draft_override": {
                "active": True,
                "excluded_channels": ["instagram", "facebook"],
            },
        },
    ).json()
    assert rec_no_ch["all_channels_excluded"] is True
    assert rec_no_ch["recommendations"] == []
    assert rec_no_ch["editor_defaults"]["channel"] is None
    assert "excluded" in rec_no_ch["missing_info_prompt"].lower()
