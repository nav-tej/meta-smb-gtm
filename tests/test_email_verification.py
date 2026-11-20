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
OTHER_ID = "00000000-0000-4000-8000-000000000002"
NOT_FOUND = SupabaseError(404, "User not found")


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


def test_signup_uses_public_signup_and_never_confirms_email(
    monkeypatch: pytest.MonkeyPatch, client: TestClient
) -> None:
    fake = use(
        monkeypatch,
        FakeSupabase(
            {
                "signup": {"id": USER_ID, "email": "a@example.test"},
                "admin/users/": {"id": USER_ID, "email": "a@example.test"},  # unconfirmed
            }
        ),
    )
    res = client.post(
        "/api/v1/account/signup",
        headers=ORIGIN,
        json={"email": "a@example.test", "password": PASSWORD},
    )
    assert res.status_code == 200
    assert res.json()["authenticated"] is False
    assert res.headers["cache-control"] == "no-store"
    assert "muse_access" not in res.cookies and "muse_refresh" not in res.cookies
    assert fake.paths() == ["signup", f"admin/users/{USER_ID}", f"admin/users/{USER_ID}"]
    assert fake.calls[0]["secret"] is False  # the account is created by public signup
    assert all("email_confirm" not in (call["body"] or {}) for call in fake.calls)
    assert all("email_confirmed_at" not in (call["body"] or {}) for call in fake.calls)


def test_signup_reply_is_identical_for_existing_and_new_addresses(
    monkeypatch: pytest.MonkeyPatch, client: TestClient
) -> None:
    new_user = {"id": USER_ID, "email": "new@example.test"}
    use(monkeypatch, FakeSupabase({"signup": new_user, "admin/users/": new_user}))
    first = client.post(
        "/api/v1/account/signup",
        headers=ORIGIN,
        json={"email": "new@example.test", "password": PASSWORD},
    )
    # With confirmations on, Supabase answers a confirmed address with a random id.
    use(
        monkeypatch,
        FakeSupabase(
            {"signup": {"id": OTHER_ID, "email": "old@example.test"}, "admin/users/": NOT_FOUND}
        ),
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
    assert fake.paths() == ["token", "user", "user"]  # binding check, then verification


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


# --- signup binding: pre-registration takeover through the confirmation link -----------------


class FakeGoTrue:
    """A tiny stateful Supabase Auth, faithful to upstream signup.go on the points that matter:
    a repeat signup for an unconfirmed address keeps the FIRST password, a confirmed address
    gets an obfuscated reply with a random id, and clicking the link confirms the account."""

    def __init__(self) -> None:
        self.user: dict[str, Any] | None = None
        self.password = ""
        self.sessions: set[str] = set()
        self.fail_admin_put = False
        self.logouts: list[str] = []

    def _public(self) -> dict[str, Any]:
        assert self.user is not None
        return dict(self.user)

    def click_confirmation_link(self) -> str:
        assert self.user is not None
        self.user["email_confirmed_at"] = "2026-11-16T00:00:00Z"
        return self._new_session()

    def _new_session(self) -> str:
        token = f"tok{len(self.sessions) + 1}"
        self.sessions.add(token)
        return token

    async def auth(
        self,
        path: str,
        method: str = "GET",
        body: dict[str, Any] | None = None,
        access_token: str | None = None,
        secret: bool = False,
    ) -> dict[str, Any]:
        base = path.split("?", 1)[0]
        body = body or {}
        if base == "signup":
            if self.user is None:
                self.user = {"id": USER_ID, "email": body["email"], "app_metadata": {}}
                self.password = body["password"]
            elif self.user.get("email_confirmed_at"):
                return {"id": OTHER_ID, "email": body["email"]}
            return self._public()  # unconfirmed: password unchanged, link re-sent
        if base == f"admin/users/{USER_ID}" and secret:
            if self.user is None:
                raise NOT_FOUND
            if method == "GET":
                return self._public()
            if self.fail_admin_put:
                raise SupabaseError(503, "Auth unavailable")
            if "password" in body:
                self.password = body["password"]
            for key, value in (body.get("app_metadata") or {}).items():
                if value is None:
                    self.user["app_metadata"].pop(key, None)
                else:
                    self.user["app_metadata"][key] = value
            return self._public()
        if base.startswith("admin/users/") and secret:
            raise NOT_FOUND
        if base == "token":
            confirmed = self.user and self.user.get("email_confirmed_at")
            if not confirmed or body.get("password") != self.password:
                raise SupabaseError(401, "Invalid login credentials")
            token = self._new_session()
            return {"access_token": token, "refresh_token": "r" + token, "expires_in": 3600}
        if base == "user":
            if access_token not in self.sessions:
                raise SupabaseError(401, "Session not found")
            return self._public()
        if base == "logout":
            scope = path.split("scope=", 1)[1]
            self.logouts.append(scope)
            if scope == "global":
                self.sessions.clear()
            elif scope == "others":
                self.sessions = {access_token} if access_token in self.sessions else set()
            return {}
        raise AssertionError(f"Unexpected auth call: {method} {path}")

    async def rpc(self, name: str, params: dict[str, Any]) -> dict[str, Any]:
        return {"allowed": True, "plan": "trial", "used": 0, "limit": 3, "remaining": 3}


def browser_client() -> TestClient:
    # The binding cookie is Secure, as on the HTTPS site, so browsers here use https.
    return TestClient(app, base_url="https://testserver")


VICTIM = "victim@example.test"
ATTACKER_PASSWORD = "attacker-password-123"
VICTIM_PASSWORD = "victims-own-password-456"


@pytest.fixture
def gotrue(monkeypatch: pytest.MonkeyPatch) -> FakeGoTrue:
    fake = FakeGoTrue()
    monkeypatch.setattr("src.api.accounts.get_supabase_client", lambda: fake)
    monkeypatch.setattr(accounts_service, "get_supabase_client", lambda: fake)
    return fake


def _signup(browser: TestClient, password: str) -> None:
    res = browser.post(
        "/api/v1/account/signup", headers=ORIGIN, json={"email": VICTIM, "password": password}
    )
    assert res.status_code == 200 and res.json()["message"] == CONFIRMATION_REPLY


def _land(browser: TestClient, token: str) -> Any:
    return browser.post(
        "/api/v1/account/session",
        headers=ORIGIN,
        json={"access_token": token, "refresh_token": "r" + token},
    )


def _signin(browser: TestClient, password: str) -> Any:
    return browser.post(
        "/api/v1/account/signin", headers=ORIGIN, json={"email": VICTIM, "password": password}
    )


CONFIRMATION_REPLY = (
    "Check your inbox for a link to confirm your email, then sign in. "
    "Already have an account? Sign in or reset your password."
)


def test_squatter_password_dies_when_owner_confirms_after_signing_up(gotrue: FakeGoTrue) -> None:
    attacker, victim = browser_client(), browser_client()
    _signup(attacker, ATTACKER_PASSWORD)
    _signup(victim, VICTIM_PASSWORD)
    _signup(attacker, ATTACKER_PASSWORD)  # attacker signs up again after the victim
    landed = _land(victim, gotrue.click_confirmation_link())
    assert landed.status_code == 200
    assert landed.json()["password_reset_required"] is True
    assert landed.json()["user"]["email_verified"] is True  # the owner is signed in
    assert gotrue.password not in (ATTACKER_PASSWORD, VICTIM_PASSWORD)
    assert gotrue.logouts == ["others"]
    assert _signin(attacker, ATTACKER_PASSWORD).status_code == 401
    assert gotrue.user and gotrue.user["app_metadata"] == {}


def test_squatter_password_dies_when_owner_clicks_an_unsolicited_link(
    gotrue: FakeGoTrue,
) -> None:
    attacker, victim = browser_client(), browser_client()
    _signup(attacker, ATTACKER_PASSWORD)
    landed = _land(victim, gotrue.click_confirmation_link())
    assert landed.json()["password_reset_required"] is True
    assert _signin(attacker, ATTACKER_PASSWORD).status_code == 401


def test_owner_who_signed_up_last_keeps_their_password(gotrue: FakeGoTrue) -> None:
    attacker, victim = browser_client(), browser_client()
    _signup(attacker, ATTACKER_PASSWORD)
    _signup(victim, VICTIM_PASSWORD)  # Supabase alone would keep the attacker's password
    landed = _land(victim, gotrue.click_confirmation_link())
    assert landed.status_code == 200
    assert "password_reset_required" not in landed.json()
    assert gotrue.password == VICTIM_PASSWORD
    assert gotrue.logouts == []
    assert "muse_access" in landed.cookies
    assert _signin(attacker, ATTACKER_PASSWORD).status_code == 401
    assert _signin(browser_client(), VICTIM_PASSWORD).status_code == 200  # binding is settled


def test_confirming_on_another_device_asks_for_a_new_password(gotrue: FakeGoTrue) -> None:
    laptop, phone = browser_client(), browser_client()
    _signup(laptop, VICTIM_PASSWORD)
    landed = _land(phone, gotrue.click_confirmation_link())
    assert landed.status_code == 200
    assert landed.json()["password_reset_required"] is True
    assert "muse_access" in landed.cookies  # signed in on the phone, can set a password there


def test_password_signin_before_landing_is_refused_outside_the_signup_browser(
    gotrue: FakeGoTrue,
) -> None:
    # The link was confirmed (for example by a mail scanner) but never reached /session.
    signup_browser, other = browser_client(), browser_client()
    _signup(signup_browser, VICTIM_PASSWORD)
    gotrue.click_confirmation_link()
    refused = _signin(other, VICTIM_PASSWORD)
    assert refused.status_code == 401
    assert "set a new password" in refused.json()["detail"]
    assert "muse_access" not in refused.cookies
    assert gotrue.logouts == ["global"] and not gotrue.sessions
    assert gotrue.password != VICTIM_PASSWORD


def test_password_signin_before_landing_is_refused_even_in_the_signup_browser(
    gotrue: FakeGoTrue,
) -> None:
    # The latest signup browser might be the squatter's; only the emailed link proves the owner.
    attacker = browser_client()
    _signup(attacker, ATTACKER_PASSWORD)
    gotrue.click_confirmation_link()  # e.g. a mail scanner opened the owner's link
    refused = _signin(attacker, ATTACKER_PASSWORD)
    assert refused.status_code == 401
    assert gotrue.password != ATTACKER_PASSWORD and not gotrue.sessions
    assert gotrue.user and gotrue.user["app_metadata"] == {}


def test_signup_fails_closed_when_the_binding_cannot_be_stored(gotrue: FakeGoTrue) -> None:
    browser = browser_client()
    gotrue.fail_admin_put = True
    res = browser.post(
        "/api/v1/account/signup", headers=ORIGIN, json={"email": VICTIM, "password": PASSWORD}
    )
    assert res.status_code == 503
    assert "muse_signup" not in res.cookies


def test_landing_fails_closed_when_the_password_cannot_be_replaced(gotrue: FakeGoTrue) -> None:
    attacker, victim = browser_client(), browser_client()
    _signup(attacker, ATTACKER_PASSWORD)
    token = gotrue.click_confirmation_link()
    gotrue.fail_admin_put = True
    landed = _land(victim, token)
    assert landed.status_code == 503
    assert "muse_access" not in landed.cookies
    gotrue.fail_admin_put = False
    assert _signin(attacker, ATTACKER_PASSWORD).status_code == 401  # binding still pending


def test_accounts_without_a_binding_are_unaffected(gotrue: FakeGoTrue) -> None:
    # Accounts confirmed before this change carry no binding and sign in as before.
    gotrue.user = {
        "id": USER_ID,
        "email": VICTIM,
        "app_metadata": {},
        "email_confirmed_at": "2026-11-09T00:00:00Z",
    }
    gotrue.password = VICTIM_PASSWORD
    assert _signin(browser_client(), VICTIM_PASSWORD).status_code == 200
    assert gotrue.logouts == []
