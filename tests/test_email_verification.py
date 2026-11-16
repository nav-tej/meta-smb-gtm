"""Email verification: signup, resend, reset, sign-in and Google linking with a mocked Supabase."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from src.api.main import app
from src.clients.supabase import SupabaseError
from src.services import accounts as accounts_service
from src.services.accounts import AccountSession

ORIGIN = {"Origin": "http://localhost:8000"}
USER_ID = "00000000-0000-4000-8000-000000000001"
PASSWORD = "very-secure-password-123"


class FakeSupabase:
    """Records Auth calls; each path prefix maps to a reply or an exception."""

    def __init__(self, replies: dict[str, Any] | None = None) -> None:
        self.replies = replies or {}
        self.calls: list[dict[str, Any]] = []

    async def auth(
        self,
        path: str,
        method: str = "GET",
        body: dict[str, Any] | None = None,
        access_token: str | None = None,
        secret: bool = False,
    ) -> dict[str, Any]:
        self.calls.append(
            {"path": path, "method": method, "body": body, "secret": secret, "token": access_token}
        )
        for prefix, reply in self.replies.items():
            if path.startswith(prefix):
                if isinstance(reply, Exception):
                    raise reply
                return reply(body) if callable(reply) else reply
        raise AssertionError(f"Unexpected auth call: {method} {path}")

    async def rpc(self, name: str, params: dict[str, Any]) -> dict[str, Any]:
        assert name == "muse_usage_status"
        return {"allowed": True, "plan": "trial", "used": 0, "limit": 3, "remaining": 3}

    def paths(self) -> list[str]:
        return [call["path"].split("?", 1)[0] for call in self.calls]


@pytest.fixture(autouse=True)
def _fresh_throttle() -> Iterator[None]:
    accounts_service.reset_email_throttle()
    yield
    accounts_service.reset_email_throttle()


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def use(monkeypatch: pytest.MonkeyPatch, fake: FakeSupabase) -> FakeSupabase:
    monkeypatch.setattr("src.api.accounts.get_supabase_client", lambda: fake)
    monkeypatch.setattr(accounts_service, "get_supabase_client", lambda: fake)
    return fake


def confirmed_user(**extra: Any) -> dict[str, Any]:
    return {"id": USER_ID, "email": "a@example.test", **extra}


# --- signup --------------------------------------------------------------------------------


def test_signup_never_uses_admin_api_or_email_confirm(
    monkeypatch: pytest.MonkeyPatch, client: TestClient
) -> None:
    fake = use(monkeypatch, FakeSupabase({"signup": {"id": USER_ID, "email": "a@example.test"}}))
    res = client.post(
        "/api/v1/account/signup",
        headers=ORIGIN,
        json={"email": "a@example.test", "password": PASSWORD},
    )
    assert res.status_code == 200
    assert res.json()["authenticated"] is False
    assert res.headers["cache-control"] == "no-store"
    assert "set-cookie" not in res.headers
    assert fake.paths() == ["signup"]
    assert all(not call["secret"] for call in fake.calls)
    assert "email_confirm" not in (fake.calls[0]["body"] or {})


def test_signup_reply_is_identical_for_existing_and_new_addresses(
    monkeypatch: pytest.MonkeyPatch, client: TestClient
) -> None:
    # With confirmations on, Supabase answers an existing address with an obfuscated user.
    use(monkeypatch, FakeSupabase({"signup": {"id": USER_ID, "email": "x@example.test"}}))
    first = client.post(
        "/api/v1/account/signup",
        headers=ORIGIN,
        json={"email": "new@example.test", "password": PASSWORD},
    )
    second = client.post(
        "/api/v1/account/signup",
        headers=ORIGIN,
        json={"email": "old@example.test", "password": PASSWORD},
    )
    assert first.status_code == second.status_code == 200
    assert first.json() == second.json()


def test_signup_rejected_by_provider_gives_actionable_422(
    monkeypatch: pytest.MonkeyPatch, client: TestClient
) -> None:
    use(monkeypatch, FakeSupabase({"signup": SupabaseError(401, "Sign in failed.")}))
    res = client.post(
        "/api/v1/account/signup",
        headers=ORIGIN,
        json={"email": "a@example.test", "password": PASSWORD},
    )
    assert res.status_code == 422
    assert "password" in res.json()["detail"]
    assert "Sign in failed" not in res.json()["detail"]


def test_signup_provider_rate_limit_and_outage_pass_through(
    monkeypatch: pytest.MonkeyPatch, client: TestClient
) -> None:
    for status in (429, 503):
        accounts_service.reset_email_throttle()
        use(monkeypatch, FakeSupabase({"signup": SupabaseError(status, "Provider said no.")}))
        res = client.post(
            "/api/v1/account/signup",
            headers=ORIGIN,
            json={"email": "a@example.test", "password": PASSWORD},
        )
        assert res.status_code == status


def test_signup_keeps_working_if_project_auto_confirms(
    monkeypatch: pytest.MonkeyPatch, client: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    tokens = {"access_token": "acc", "refresh_token": "ref", "expires_in": 3600}
    use(
        monkeypatch,
        FakeSupabase({"signup": tokens, "user": confirmed_user(email_confirmed_at="t")}),
    )
    with caplog.at_level("WARNING"):
        res = client.post(
            "/api/v1/account/signup",
            headers=ORIGIN,
            json={"email": "a@example.test", "password": PASSWORD},
        )
    assert res.status_code == 200
    assert res.json()["user"]["email_verified"] is True
    assert "muse_access" in res.cookies
    assert "email confirmation is off" in caplog.text


def test_signup_session_for_unconfirmed_user_is_not_issued(
    monkeypatch: pytest.MonkeyPatch, client: TestClient
) -> None:
    tokens = {"access_token": "acc", "refresh_token": "ref"}
    use(monkeypatch, FakeSupabase({"signup": tokens, "user": confirmed_user()}))
    res = client.post(
        "/api/v1/account/signup",
        headers=ORIGIN,
        json={"email": "a@example.test", "password": PASSWORD},
    )
    assert res.status_code == 200
    assert res.json()["authenticated"] is False
    assert "muse_access" not in res.cookies


def test_signup_still_requires_same_origin_json(
    monkeypatch: pytest.MonkeyPatch, client: TestClient
) -> None:
    fake = use(monkeypatch, FakeSupabase())
    res = client.post(
        "/api/v1/account/signup",
        headers={"Origin": "https://evil.example"},
        json={"email": "a@example.test", "password": PASSWORD},
    )
    assert res.status_code == 403
    assert fake.calls == []


def test_signup_rejects_extra_fields_such_as_user_metadata(
    monkeypatch: pytest.MonkeyPatch, client: TestClient
) -> None:
    fake = use(monkeypatch, FakeSupabase())
    res = client.post(
        "/api/v1/account/signup",
        headers=ORIGIN,
        json={"email": "a@example.test", "password": PASSWORD, "data": {"email_verified": True}},
    )
    assert res.status_code == 422
    assert fake.calls == []


# --- resend and reset (onboarding recovery) ------------------------------------------------


def test_resend_sends_signup_confirmation_to_account_page(
    monkeypatch: pytest.MonkeyPatch, client: TestClient
) -> None:
    fake = use(monkeypatch, FakeSupabase({"resend": {}}))
    res = client.post("/api/v1/account/resend", headers=ORIGIN, json={"email": " A@Example.test "})
    assert res.status_code == 200
    call = fake.calls[0]
    assert call["path"].startswith("resend?redirect_to=") and call["path"].endswith("%2Faccount")
    assert call["body"] == {"type": "signup", "email": "a@example.test"}
    assert call["secret"] is False


def test_resend_does_not_reveal_unknown_or_confirmed_addresses(
    monkeypatch: pytest.MonkeyPatch, client: TestClient
) -> None:
    use(monkeypatch, FakeSupabase({"resend": {}}))
    ok = client.post("/api/v1/account/resend", headers=ORIGIN, json={"email": "a@example.test"})
    use(monkeypatch, FakeSupabase({"resend": SupabaseError(401, "Sign in failed.")}))
    hidden = client.post("/api/v1/account/resend", headers=ORIGIN, json={"email": "b@example.test"})
    assert ok.status_code == hidden.status_code == 200
    assert ok.json() == hidden.json()


def test_password_reset_is_unchanged_and_enumeration_safe(
    monkeypatch: pytest.MonkeyPatch, client: TestClient
) -> None:
    fake = use(monkeypatch, FakeSupabase({"recover": SupabaseError(401, "x")}))
    res = client.post("/api/v1/account/recover", headers=ORIGIN, json={"email": "a@example.test"})
    assert res.status_code == 200
    assert "reset link" in res.json()["message"]
    assert fake.calls[0]["path"].startswith("recover?redirect_to=")
    assert fake.calls[0]["body"] == {"email": "a@example.test"}


def test_password_update_from_recovery_link_still_works(
    monkeypatch: pytest.MonkeyPatch, client: TestClient
) -> None:
    fake = use(monkeypatch, FakeSupabase({"user": confirmed_user(email_confirmed_at="t")}))
    client.cookies.set("muse_access", "recovery-access")
    res = client.post("/api/v1/account/password", headers=ORIGIN, json={"password": PASSWORD})
    assert res.status_code == 200
    assert fake.calls[-1]["method"] == "PUT" and fake.calls[-1]["token"] == "recovery-access"


@pytest.mark.parametrize("route", ["signup", "resend", "recover"])
def test_email_sends_are_throttled_per_address(
    monkeypatch: pytest.MonkeyPatch, client: TestClient, route: str
) -> None:
    fake = use(monkeypatch, FakeSupabase({"signup": {}, "resend": {}, "recover": {}}))
    body: dict[str, Any] = {"email": "a@example.test"}
    if route == "signup":
        body["password"] = PASSWORD
    codes = [
        client.post(f"/api/v1/account/{route}", headers=ORIGIN, json=body).status_code
        for _ in range(accounts_service.EMAIL_SENDS_PER_ADDRESS + 1)
    ]
    assert codes[:-1] == [200] * accounts_service.EMAIL_SENDS_PER_ADDRESS
    assert codes[-1] == 429
    assert len(fake.calls) == accounts_service.EMAIL_SENDS_PER_ADDRESS


def test_email_sends_are_throttled_per_network_across_addresses(
    monkeypatch: pytest.MonkeyPatch, client: TestClient
) -> None:
    use(monkeypatch, FakeSupabase({"resend": {}}))
    headers = {**ORIGIN, "X-Forwarded-For": "203.0.113.9"}
    codes = [
        client.post(
            "/api/v1/account/resend", headers=headers, json={"email": f"u{i}@example.test"}
        ).status_code
        for i in range(accounts_service.EMAIL_SENDS_PER_IP + 1)
    ]
    assert codes[-1] == 429 and codes.count(200) == accounts_service.EMAIL_SENDS_PER_IP
    other = client.post(
        "/api/v1/account/resend",
        headers={**ORIGIN, "X-Forwarded-For": "198.51.100.4"},
        json={"email": "fresh@example.test"},
    )
    assert other.status_code == 200


def test_throttle_window_expires() -> None:
    request = type("Req", (), {"headers": {}, "client": None})()
    for _ in range(accounts_service.EMAIL_SENDS_PER_ADDRESS):
        accounts_service.throttle_email_send(request, "a@example.test", now=0)
    with pytest.raises(HTTPException) as blocked:
        accounts_service.throttle_email_send(request, "a@example.test", now=1)
    assert blocked.value.status_code == 429
    later = accounts_service.EMAIL_SEND_WINDOW_SECONDS + 2
    accounts_service.throttle_email_send(request, "a@example.test", now=later)


# --- sign-in and verification state --------------------------------------------------------


def test_existing_confirmed_account_signs_in(
    monkeypatch: pytest.MonkeyPatch, client: TestClient
) -> None:
    # Accounts created by the old admin path already carry email_confirmed_at.
    tokens = {"access_token": "acc", "refresh_token": "ref", "expires_in": 3600}
    fake = use(
        monkeypatch,
        FakeSupabase({"token": tokens, "user": confirmed_user(email_confirmed_at="2026-11-09")}),
    )
    res = client.post(
        "/api/v1/account/signin",
        headers=ORIGIN,
        json={"email": "a@example.test", "password": PASSWORD},
    )
    assert res.status_code == 200
    assert res.json()["user"]["email_verified"] is True
    assert "muse_access" in res.cookies
    assert fake.paths() == ["token", "user"]


def test_unconfirmed_signin_is_refused_with_confirmation_hint(
    monkeypatch: pytest.MonkeyPatch, client: TestClient
) -> None:
    # Supabase answers email_not_confirmed with HTTP 400, which the adapter maps to this 401.
    detail = "Sign in failed. Check your details and confirm your email."
    use(monkeypatch, FakeSupabase({"token": SupabaseError(401, detail)}))
    res = client.post(
        "/api/v1/account/signin",
        headers=ORIGIN,
        json={"email": "a@example.test", "password": PASSWORD},
    )
    assert res.status_code == 401
    assert "confirm your email" in res.json()["detail"]
    assert "muse_access" not in res.cookies


async def test_user_metadata_cannot_self_declare_verification(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    use(monkeypatch, FakeSupabase({"user": confirmed_user(user_metadata={"email_verified": True})}))
    account = await accounts_service.verify_token("acc")
    assert account.email_verified is False

    use(monkeypatch, FakeSupabase({"user": confirmed_user(email_confirmed_at="2026-11-15")}))
    assert (await accounts_service.verify_token("acc")).email_verified is True


def test_confirmation_link_session_unlocks_account(
    monkeypatch: pytest.MonkeyPatch, client: TestClient
) -> None:
    # The emailed link lands on /account#access_token=...; account.js posts it to /session.
    use(monkeypatch, FakeSupabase({"user": confirmed_user(email_confirmed_at="2026-11-15")}))
    res = client.post(
        "/api/v1/account/session",
        headers=ORIGIN,
        json={"access_token": "acc", "refresh_token": "ref"},
    )
    assert res.status_code == 200
    assert res.json()["user"]["email_verified"] is True
    assert res.json()["usage"]["remaining"] == 3


def test_unverified_session_cannot_save_workspace(
    monkeypatch: pytest.MonkeyPatch, client: TestClient
) -> None:
    use(monkeypatch, FakeSupabase({"user": confirmed_user()}))
    client.cookies.set("muse_access", "acc")
    res = client.get("/api/v1/account/workspace", headers={"X-Muse-Owner": USER_ID})
    assert res.status_code == 403
    assert "Confirm your email" in res.json()["detail"]


# --- Google sign-in onto a pre-registered address ------------------------------------------


@pytest.fixture
def google_callback(monkeypatch: pytest.MonkeyPatch) -> Iterator[Any]:
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "cid.apps.googleusercontent.com")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "google-client-secret")
    from src.config import get_settings

    get_settings.cache_clear()

    class Resp:
        is_error = False

        def __init__(self, data: dict[str, Any]) -> None:
            self.data = data

        def json(self) -> dict[str, Any]:
            return self.data

    class FakeGoogleHttp:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            pass

        async def __aenter__(self) -> FakeGoogleHttp:
            return self

        async def __aexit__(self, *args: Any) -> None:
            pass

        async def post(self, url: str, **kwargs: Any) -> Resp:
            return Resp({"access_token": "goog"})

        async def get(self, url: str, **kwargs: Any) -> Resp:
            return Resp({"email": "victim@example.test", "email_verified": True})

    monkeypatch.setattr(accounts_service.httpx, "AsyncClient", FakeGoogleHttp)

    async def fake_verify(token: str) -> AccountSession:
        return AccountSession(USER_ID, "victim@example.test", True, token, None)

    monkeypatch.setattr(accounts_service, "verify_token", fake_verify)

    async def run() -> tuple[str, dict[str, Any] | None, str | None]:
        state = accounts_service.sign_oauth_state("/create")
        request = type("Req", (), {"cookies": {"muse_oauth_state": state}, "headers": {}})()
        return await accounts_service.complete_google_oauth(request, "code", state, None)

    yield run
    get_settings.cache_clear()


TOKENS = {"access_token": "acc", "refresh_token": "ref", "expires_in": 3600}


async def test_google_replaces_unproven_password_before_confirming(
    monkeypatch: pytest.MonkeyPatch, google_callback: Any
) -> None:
    link = {"id": USER_ID, "email_confirmed_at": None, "hashed_token": "h"}
    fake = use(
        monkeypatch,
        FakeSupabase({"admin/generate_link": link, "admin/users/": {}, "verify": TOKENS}),
    )
    target, tokens, error = await google_callback()
    assert (target, error) == ("/create", None) and tokens == TOKENS
    assert fake.paths() == ["admin/generate_link", f"admin/users/{USER_ID}", "verify"]
    rotate = fake.calls[1]
    assert rotate["method"] == "PUT" and rotate["secret"] is True
    assert set(rotate["body"]) == {"password"} and len(rotate["body"]["password"]) >= 48


async def test_google_leaves_confirmed_accounts_untouched(
    monkeypatch: pytest.MonkeyPatch, google_callback: Any
) -> None:
    link = {"id": USER_ID, "email_confirmed_at": "2026-11-09T00:00:00Z", "hashed_token": "h"}
    fake = use(monkeypatch, FakeSupabase({"admin/generate_link": link, "verify": TOKENS}))
    _, tokens, error = await google_callback()
    assert error is None and tokens == TOKENS
    assert fake.paths() == ["admin/generate_link", "verify"]


async def test_google_fails_closed_if_password_cannot_be_replaced(
    monkeypatch: pytest.MonkeyPatch, google_callback: Any
) -> None:
    link = {"id": USER_ID, "email_confirmed_at": None, "hashed_token": "h"}
    fake = use(
        monkeypatch,
        FakeSupabase(
            {
                "admin/generate_link": link,
                "admin/users/": SupabaseError(503, "Account service is unavailable."),
            }
        ),
    )
    _, tokens, error = await google_callback()
    assert tokens is None and error
    assert "verify" not in fake.paths()


# --- live eligibility for unconfirmed accounts (Nov 16 review) ------------------------------


def test_unconfirmed_session_cannot_start_a_live_run(
    monkeypatch: pytest.MonkeyPatch, client: TestClient
) -> None:
    from src.config import get_settings
    from src.services import usage_meter

    monkeypatch.setenv("ACCOUNTS_REQUIRED", "true")
    get_settings.cache_clear()
    authorized: list[str] = []

    async def refuse(*args: Any, **kwargs: Any) -> str:
        authorized.append("called")
        raise AssertionError("an unconfirmed account must not reach run authorization")

    monkeypatch.setattr(usage_meter, "authorize_operation", refuse)
    fake = use(monkeypatch, FakeSupabase({"user": confirmed_user()}))  # no email_confirmed_at
    client.cookies.set("muse_access", "acc")
    try:
        res = client.post("/api/v1/bid-advice?live=true", headers=ORIGIN, json={})
        me = client.get("/api/v1/account/me").json()
    finally:
        get_settings.cache_clear()
    assert res.status_code == 403
    assert "Confirm your email" in res.json()["detail"]
    assert authorized == []
    assert me["user"]["email_verified"] is False
    assert me["usage"] is None and me["live_available"] is False
    assert all(call["path"] == "user" for call in fake.calls)
