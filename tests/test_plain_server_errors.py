"""Seller error responses keep the reason and next step without backend diagnostics."""

from __future__ import annotations

from datetime import date
from typing import Any

import httpx
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from src.api import ad_accounts, onboarding, product_reference
from src.api.main import app
from src.services.accounts import AccountSession
from src.services.product_reference import (
    PRODUCT_ADDRESS,
    PRODUCT_BLOCKED,
    PRODUCT_UNREADABLE,
    ProductReferenceError,
    ProductReferenceService,
)

# Deliberately synthetic diagnostic payload, not real credentials or user data.
RAW = (
    "RuntimeError: SELECT secret FROM tokens; "
    "https://private.test/?token=fixture robots.txt Disallow: /"
)


def assert_plain(text: str, expected: str) -> None:
    assert text == expected
    for raw in (
        RAW,
        "RuntimeError",
        "Traceback",
        "SELECT",
        "private.test",
        "token=",
        "robots.txt",
        "Disallow:",
    ):
        assert raw not in text
    assert "—" not in text


@pytest.mark.parametrize("edit", [False, True])
def test_setup_save_errors_are_plain_and_preserve_merge_logic(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture, edit: bool
) -> None:
    account = AccountSession(
        "11111111-1111-4000-8000-111111111111", "seller@example.test", True, "fixture", None
    )

    async def resolve(*args: Any, **kwargs: Any) -> AccountSession:
        return account

    async def load(*args: Any, **kwargs: Any) -> dict[str, Any]:
        return {
            "version": 1,
            "document": {"onboarding": {"completed_at": "2026-11-01"}} if edit else {},
        }

    async def snapshot(*args: Any, **kwargs: Any) -> dict[str, Any]:
        return {"usage": {"remaining": 3}}

    async def fail(*args: Any, **kwargs: Any) -> None:
        raise RuntimeError(RAW)

    monkeypatch.setattr(onboarding, "resolve_account", resolve)
    monkeypatch.setattr(onboarding, "load_workspace", load)
    monkeypatch.setattr(onboarding, "snapshot", snapshot)
    monkeypatch.setattr(onboarding, "save_workspace", fail)
    response = TestClient(app).post(
        "/api/v1/onboarding/build",
        headers={"X-Muse-Owner": account.user_id},
        json={"business_name": "Handmade", "edit": edit},
    )
    assert response.status_code == 500
    expected = (
        "Muse couldn't save your setup changes. Try saving again in a minute."
        if edit
        else "Muse couldn't finish saving your setup. Try saving again in a minute."
    )
    assert_plain(response.json()["detail"], expected)
    assert "save failed (RuntimeError)" in caplog.text
    assert RAW not in caplog.text


def test_product_error_never_echoes_diagnostic_text(
    caplog: pytest.LogCaptureFixture,
) -> None:
    class FailingImport:
        async def read(self, url: str) -> None:
            raise ProductReferenceError(RAW)

    app.dependency_overrides[product_reference.get_product_reference_service] = FailingImport
    try:
        response = TestClient(app).post(
            "/api/v1/product-reference", json={"url": "https://shop.test/item"}
        )
    finally:
        app.dependency_overrides.pop(product_reference.get_product_reference_service, None)
    assert response.status_code == 422
    assert_plain(response.json()["detail"], PRODUCT_UNREADABLE)
    assert "Product import failed (ProductReferenceError)" in caplog.text
    assert RAW not in caplog.text


@pytest.mark.parametrize(
    ("url", "robots_status", "robots_body", "expected"),
    [
        ("ftp://shop.test/item", 200, "", PRODUCT_ADDRESS),
        ("https://shop.test/item", 200, "User-agent: *\nDisallow: /", PRODUCT_BLOCKED),
        ("https://shop.test/item", 403, "", PRODUCT_UNREADABLE),
    ],
)
def test_product_import_known_reasons_are_plain(
    respx_mock: Any,
    url: str,
    robots_status: int,
    robots_body: str,
    expected: str,
) -> None:
    async def resolver(host: str) -> list[str]:
        return ["8.8.8.8"]

    respx_mock.get("https://shop.test/robots.txt").respond(robots_status, text=robots_body)
    page = respx_mock.get("https://shop.test/item").respond(200, text="never read")
    service = ProductReferenceService(resolver=resolver)
    app.dependency_overrides[product_reference.get_product_reference_service] = lambda: service
    try:
        response = TestClient(app).post("/api/v1/product-reference", json={"url": url})
    finally:
        app.dependency_overrides.pop(product_reference.get_product_reference_service, None)
    assert response.status_code == 422
    assert_plain(response.json()["detail"], expected)
    assert page.call_count == 0


def test_campaign_parser_error_does_not_expose_rows_or_exception(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    from src.api import bids

    def fail(*args: Any, **kwargs: Any) -> None:
        raise ValueError(RAW)

    monkeypatch.setattr(bids, "load_campaign_csv", fail)
    response = TestClient(app).post(
        "/api/v1/bid-advice/csv", json={"csv_text": "invalid campaign file"}
    )
    assert response.status_code == 422
    assert_plain(
        response.json()["detail"],
        "Muse couldn't read the campaign file. Export daily results from Meta Ads Manager "
        "as a CSV with dates, campaign and ad set names, impressions and spend, then try again.",
    )
    assert "Campaign import failed (ValueError)" in caplog.text
    assert RAW not in caplog.text


def test_ad_date_order_uses_plain_names() -> None:
    with pytest.raises(HTTPException) as error:
        ad_accounts._resolve_date_range(date(2026, 11, 10), date(2026, 11, 1))
    assert_plain(
        error.value.detail,
        "The end date is before the start date. Choose an end date on or after the start date.",
    )
    assert "end_date" not in error.value.detail


def test_disconnect_requires_a_selection(monkeypatch: pytest.MonkeyPatch) -> None:
    async def require(*args: Any, **kwargs: Any) -> object:
        return object()

    monkeypatch.setattr(ad_accounts, "require_verified_seller", require)
    app.dependency_overrides[ad_accounts.require_ad_connect_enabled] = lambda: None
    try:
        response = TestClient(app).post("/api/v1/ad-accounts/meta/disconnect")
    finally:
        app.dependency_overrides.pop(ad_accounts.require_ad_connect_enabled, None)
    assert response.status_code == 422
    assert_plain(response.json()["detail"], "Choose the Meta ad account you want to disconnect.")
    assert "account_id" not in response.text


def error_response(action: Any) -> httpx.Response:
    """Exercise a service failure through the app's real public exception handlers."""
    import inspect

    from fastapi import FastAPI

    from src.services.ad_connections import AdConnectionError
    from src.services.digest_email import DigestError

    isolated = FastAPI(exception_handlers=app.exception_handlers)

    @isolated.get("/")
    async def invoke() -> Any:
        try:
            result = action()
            return await result if inspect.isawaitable(result) else result
        except (AdConnectionError, DigestError) as err:
            # Same narrow translation as their API routes.
            raise HTTPException(err.status_code, err.detail) from err

    return TestClient(isolated).get("/")


@pytest.mark.parametrize("tokens", [{}, {"access_token": "", "refresh_token": ""}])
def test_invalid_auth_session_is_plain(tokens: dict[str, Any]) -> None:
    from fastapi import Response

    from src.services import accounts

    response = error_response(lambda: accounts.set_cookies(Response(), tokens))
    assert response.status_code == 503
    assert_plain(response.json()["detail"], "Muse couldn't complete sign-in. Try signing in again.")
    assert "invalid session" not in response.text


def test_invalid_signup_identity_is_plain(monkeypatch: pytest.MonkeyPatch) -> None:
    from types import SimpleNamespace

    from fastapi import Request, Response

    from src.services import accounts

    async def auth(*args: Any, **kwargs: Any) -> dict[str, Any]:
        return {
            "id": RAW,
            "email_confirmed_at": "2026-11-01",
            "app_metadata": {accounts.SIGNUP_BINDING_KEY: "fixture-binding"},
        }

    monkeypatch.setattr(accounts, "get_supabase_client", lambda: SimpleNamespace(auth=auth))
    response = error_response(
        lambda: accounts.settle_signup_binding(
            Request({"type": "http", "headers": []}), Response(), "fixture", from_link=True
        )
    )
    assert response.status_code == 503
    assert_plain(response.json()["detail"], "Muse couldn't complete sign-in. Try signing in again.")
    assert "invalid user" not in response.text


def test_account_usage_failure_is_plain(monkeypatch: pytest.MonkeyPatch) -> None:
    from types import SimpleNamespace

    from src.services import accounts

    async def rpc(*args: Any, **kwargs: Any) -> dict[str, Any]:
        return {"allowed": False, "message": RAW}

    monkeypatch.setattr(accounts, "get_supabase_client", lambda: SimpleNamespace(rpc=rpc))
    account = AccountSession(
        "11111111-1111-4000-8000-111111111111", "a@example.test", True, "fixture", None
    )
    response = error_response(lambda: accounts.snapshot(account))
    assert response.status_code == 503
    assert_plain(
        response.json()["detail"], "Muse couldn't check your remaining runs. Try again in a minute."
    )


def test_account_configuration_failure_is_plain(monkeypatch: pytest.MonkeyPatch) -> None:
    from types import SimpleNamespace

    from src.services import accounts

    monkeypatch.setattr(
        accounts,
        "get_settings",
        lambda: SimpleNamespace(supabase_secret_key="", google_client_secret=""),
    )
    response = error_response(accounts._oauth_secret)
    assert response.status_code == 503
    assert_plain(
        response.json()["detail"], "Sign-in is unavailable right now. Please try again later."
    )
    assert "configured" not in response.text


def test_invalid_google_state_is_plain(monkeypatch: pytest.MonkeyPatch) -> None:
    from src.services import accounts

    monkeypatch.setattr(accounts, "_oauth_secret", lambda: b"fixture-signing-key")
    response = error_response(lambda: accounts.verify_oauth_state(RAW, RAW))
    assert response.status_code == 400
    assert_plain(
        response.json()["detail"],
        "Muse couldn't confirm that Google sign-in request. Start sign-in again.",
    )
    assert "state" not in response.json()["detail"]


@pytest.mark.parametrize("missing_package", [False, True])
def test_payment_configuration_errors_are_plain(
    monkeypatch: pytest.MonkeyPatch,
    missing_package: bool,
) -> None:
    import builtins
    from types import SimpleNamespace

    from src.api import billing

    real_import = builtins.__import__

    def import_module(name: str, *args: Any, **kwargs: Any) -> Any:
        if name == "stripe" and missing_package:
            raise ImportError(RAW)
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", import_module)
    monkeypatch.setattr(billing, "get_settings", lambda: SimpleNamespace(stripe_secret_key=""))
    response = error_response(billing._stripe)
    assert response.status_code == 503
    assert_plain(
        response.json()["detail"], "Payments are unavailable right now. Please try again later."
    )
    assert "installed" not in response.text
    assert "configured" not in response.text


def test_unpriced_plan_stays_specific(monkeypatch: pytest.MonkeyPatch) -> None:
    from types import SimpleNamespace

    from src.api import billing

    monkeypatch.setattr(billing, "get_settings", lambda: SimpleNamespace())
    response = error_response(lambda: billing._price_id("growth"))
    assert response.status_code == 503
    assert_plain(
        response.json()["detail"], "The Growth plan isn't available to buy yet. Try again later."
    )
    assert "not priced" not in response.text


def test_research_limit_keeps_the_actual_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    from src.api import directives

    account = AccountSession(
        "11111111-1111-4000-8000-111111111111", "a@example.test", True, "fixture", None
    )

    async def resolve(*args: Any, **kwargs: Any) -> AccountSession:
        return account

    monkeypatch.setattr(directives, "resolve_account", resolve)
    monkeypatch.setattr(directives, "check_directive_rate_limit", lambda *args: False)
    response = TestClient(app).post(
        "/api/v1/directives/confirm",
        headers={"X-Muse-Owner": account.user_id},
        json={"directive": {"focus": "pricing"}},
    )
    assert response.status_code == 429
    assert_plain(
        response.json()["detail"],
        "You can save up to 10 research requests an hour. Try again in an hour.",
    )


@pytest.mark.parametrize("preview", [False, True])
def test_digest_validation_does_not_expose_pydantic_or_values(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    preview: bool,
) -> None:
    from src.api import digest_email

    account = AccountSession(
        "11111111-1111-4000-8000-111111111111", "a@example.test", True, "fixture", None
    )

    async def resolve(*args: Any, **kwargs: Any) -> AccountSession:
        return account

    async def load(*args: Any, **kwargs: Any) -> dict[str, Any]:
        return {"draft_preferences": {"cadence": "weekly", "timezone": "UTC"}}

    def fail(*args: Any, **kwargs: Any) -> None:
        raise ValueError(RAW)

    monkeypatch.setattr(digest_email, "resolve_account", resolve)
    monkeypatch.setattr(digest_email.digest_preview, "load_digest_draft", load)
    model = digest_email.digest_preview.DigestDraftPreferences
    if preview:
        monkeypatch.setattr(model, "model_validate", fail)
    else:
        monkeypatch.setattr(digest_email.digest_preview, "DigestDraftPreferences", fail)
    path = "/api/v1/digest/preview" if preview else "/api/v1/digest/preferences"
    client = TestClient(app)
    response = (
        client.post(path, json={"cadence": "weekly"}) if preview else client.put(path, json={})
    )
    assert response.status_code == 422
    assert_plain(
        response.json()["detail"],
        "Muse couldn't use those digest settings. Choose a timezone such as "
        "America/Los_Angeles and up to 3 public shop links, then try again.",
    )
    assert "ValueError" in caplog.text
    assert RAW not in caplog.text


@pytest.mark.parametrize(
    ("code", "expected"),
    [
        (
            "invalid_subscription",
            "Enter an email address and 1 to 3 public shop links, then try again.",
        ),
        ("subscribe_rate_limit", "Too many sign-ups from this network today. Try again tomorrow."),
        ("not_found", "This link is no longer valid."),
        ("unsubscribed", "This address unsubscribed. Sign up again to restart."),
        (
            "unknown",
            "Muse couldn't update your email digest. "
            "Check your settings and try again in a minute.",
        ),
    ],
)
def test_digest_storage_messages_are_vetted(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    code: str,
    expected: str,
) -> None:
    from types import SimpleNamespace

    from src.services import digest_email

    async def rpc(*args: Any, **kwargs: Any) -> dict[str, Any]:
        return {"allowed": False, "status_code": 422, "code": code, "message": RAW}

    monkeypatch.setattr(digest_email, "get_supabase_client", lambda: SimpleNamespace(rpc=rpc))
    response = error_response(lambda: digest_email._rpc("fixture", {}))
    assert response.status_code == 422
    assert_plain(response.json()["detail"], expected)
    assert RAW not in caplog.text


@pytest.mark.parametrize(
    ("code", "expected"),
    [
        (
            "invalid_connection",
            "Muse couldn't save that Meta ad account connection. Try connecting it again.",
        ),
        (
            "invalid_status",
            "Muse couldn't update that Meta ad account connection. Try again in a minute.",
        ),
        ("not_found", "That ad account is not connected to your workspace."),
        ("unknown", "Muse couldn't update that Meta ad account connection. Try again in a minute."),
    ],
)
def test_ad_storage_messages_are_vetted(
    caplog: pytest.LogCaptureFixture,
    code: str,
    expected: str,
) -> None:
    from types import SimpleNamespace

    from src.services import ad_connections

    async def rpc(*args: Any, **kwargs: Any) -> dict[str, Any]:
        return {"allowed": False, "status_code": 422, "code": code, "message": RAW}

    response = error_response(
        lambda: ad_connections._rpc("fixture", {}, supabase_client=SimpleNamespace(rpc=rpc))
    )
    assert response.status_code == 422
    assert_plain(response.json()["detail"], expected)
    assert RAW not in caplog.text


@pytest.mark.parametrize(
    ("code", "expected"),
    [
        (
            "invalid_operation",
            "Muse couldn't start that live request. Try again, or use a saved result.",
        ),
        (
            "invalid_provider_reservation",
            "Muse couldn't start that live request. Try again, or use a saved result.",
        ),
        ("invalid_status", "Muse couldn't finish recording this run. Try again in a minute."),
        ("inactive_operation", "That live request is no longer active. Start it again."),
        ("provider_call_already_reserved", "This request already started. Check its result."),
        ("operation_call_limit", "This run reached its request limit. Try a smaller request."),
        (
            "operation_not_found",
            "Muse couldn't find that run. Reload and check your saved results.",
        ),
        ("unknown", "Muse couldn't check your remaining runs. Try again in a minute."),
    ],
)
def test_usage_storage_messages_are_vetted(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    code: str,
    expected: str,
) -> None:
    from types import SimpleNamespace

    from src.clients import supabase
    from src.services import usage_meter

    async def rpc(*args: Any, **kwargs: Any) -> dict[str, Any]:
        return {"allowed": False, "status_code": 400, "code": code, "message": RAW}

    monkeypatch.setattr(supabase, "get_supabase_client", lambda: SimpleNamespace(rpc=rpc))
    response = error_response(lambda: usage_meter._rpc("fixture", {}))
    assert response.status_code == 400
    assert_plain(response.json()["detail"], expected)
    assert RAW not in caplog.text


@pytest.mark.parametrize("scenario", ["rpc_exception", "rpc_shape", "operation_id"])
def test_usage_service_invalid_responses_are_plain(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    scenario: str,
) -> None:
    from types import SimpleNamespace

    from src.clients import supabase
    from src.services import usage_meter

    async def rpc(*args: Any, **kwargs: Any) -> Any:
        if scenario == "rpc_exception":
            raise RuntimeError(RAW)
        return {"allowed": True, "operation_id": RAW} if scenario == "operation_id" else []

    monkeypatch.setattr(supabase, "get_supabase_client", lambda: SimpleNamespace(rpc=rpc))
    monkeypatch.setattr(
        usage_meter, "get_settings", lambda: SimpleNamespace(accounts_required=True)
    )
    response = error_response(
        lambda: usage_meter.authorize_operation("fixture", "fixture", "fixture")
    )
    assert response.status_code == 503
    assert_plain(
        response.json()["detail"], "Muse couldn't check your remaining runs. Try again in a minute."
    )
    assert usage_meter.current_operation_id() is None
    assert RAW not in caplog.text


@pytest.mark.parametrize("finish", [False, True])
def test_usage_service_invalid_request_is_plain(finish: bool) -> None:
    from src.services import usage_meter

    async def action() -> None:
        usage_meter._request_context.set(usage_meter.UsageContext("fixture", "fixture"))
        try:
            if finish:
                await usage_meter.finish_operation(RAW)
            else:
                await usage_meter.reserve_provider("invalid", "invalid", 0)
        finally:
            usage_meter.clear_request_context()

    response = error_response(action)
    assert response.status_code == 400
    assert_plain(
        response.json()["detail"],
        "Muse couldn't finish recording this run. Try again in a minute."
        if finish
        else "Muse couldn't start that live request. Try again, or use a saved result.",
    )


def test_invalid_saved_ad_connection_record_is_plain(monkeypatch: pytest.MonkeyPatch) -> None:
    from types import SimpleNamespace

    from src.clients.ad_networks.base import AdAccountSummary
    from src.services import ad_connections

    async def rpc(*args: Any, **kwargs: Any) -> dict[str, Any]:
        return {"allowed": True, "connection": RAW}

    monkeypatch.setattr(ad_connections, "encrypt_token", lambda *args, **kwargs: ("fixture", 1))
    response = error_response(
        lambda: ad_connections.save_meta_connection(
            "11111111-1111-4000-8000-111111111111",
            AdAccountSummary(account_id="act_12345", name="Example", currency="USD"),
            access_token="fixture",
            supabase_client=SimpleNamespace(rpc=rpc),
        )
    )
    assert response.status_code == 503
    assert_plain(
        response.json()["detail"],
        "Muse couldn't save that Meta ad account connection. Try connecting it again.",
    )


def test_missing_product_page_keeps_the_reason(respx_mock: Any) -> None:
    async def resolver(host: str) -> list[str]:
        return ["8.8.8.8"]

    respx_mock.get("https://shop.test/robots.txt").respond(404)
    respx_mock.get("https://shop.test/missing").respond(404)
    service = ProductReferenceService(resolver=resolver)
    app.dependency_overrides[product_reference.get_product_reference_service] = lambda: service
    try:
        response = TestClient(app).post(
            "/api/v1/product-reference", json={"url": "https://shop.test/missing"}
        )
    finally:
        app.dependency_overrides.pop(product_reference.get_product_reference_service, None)
    assert response.status_code == 422
    assert_plain(
        response.json()["detail"],
        "That product page couldn't be found. Check the address, try another product page, "
        "or add the details and upload its photo yourself.",
    )
    assert "HTTP 404" not in response.text


def test_demo_feature_error_does_not_teach_private_unlock_headers() -> None:
    from src.api.demo import demo_unavailable

    response = error_response(
        lambda: (_ for _ in ()).throw(demo_unavailable("Voice transcription"))
    )
    assert response.status_code == 403
    assert_plain(
        response.json()["detail"],
        "Voice transcription isn't available in the saved example. "
        "Use the example without it, or try again with live Muse access.",
    )
    for technical in ("X-Demo-Key", "live=true", "deployment"):
        assert technical not in response.text


def test_live_session_refusal_is_plain(monkeypatch: pytest.MonkeyPatch) -> None:
    from types import SimpleNamespace

    from fastapi import Request, Response

    from src.api import demo

    monkeypatch.setattr(
        demo, "get_settings", lambda: SimpleNamespace(demo_mode=True, accounts_required=False)
    )
    monkeypatch.setattr(demo, "valid_demo_key", lambda key: False)

    async def action() -> None:
        async for _ in demo.live_mode(
            Request({"type": "http", "headers": []}), Response(), live=True, x_demo_key=None
        ):
            pytest.fail("Invalid session must not be accepted")

    response = error_response(action)
    assert response.status_code == 403
    assert_plain(
        response.json()["detail"],
        "This session doesn't have access to live Muse. Use saved examples for now.",
    )
    assert "X-Demo-Key" not in response.text


def test_business_details_conflict_keeps_recovery_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    from src.api import seller_memory
    from src.models.seller import SellerPreferences
    from src.models.voice import VoiceProfile

    account = AccountSession(
        "11111111-1111-4000-8000-111111111111", "a@example.test", True, "fixture", None
    )

    async def resolve(*args: Any, **kwargs: Any) -> AccountSession:
        return account

    async def load(*args: Any, **kwargs: Any) -> Any:
        return ({"version": 2}, SellerPreferences(), VoiceProfile(), [], [])

    monkeypatch.setattr(seller_memory, "resolve_account", resolve)
    monkeypatch.setattr(seller_memory, "_load_account_state", load)
    response = TestClient(app).put(
        "/api/v1/seller-memory",
        headers={"X-Muse-Owner": account.user_id},
        json={"expected_version": 1},
    )
    assert response.status_code == 409
    assert_plain(
        response.json()["detail"],
        "Muse couldn't replace your saved business details. "
        "Reload them before saving these changes.",
    )
    assert response.json()["server_version"] == 2
    assert "server_memory_entries" in response.json()
    assert "explicit version" not in response.text
