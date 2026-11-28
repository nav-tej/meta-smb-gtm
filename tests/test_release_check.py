"""Offline release-check CLI contracts against the real app, with in-memory mutations."""

from __future__ import annotations

import copy
import json
import re
import socket
import subprocess
import sys
import threading
import time
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

import httpx
import pytest
import uvicorn
from fastapi import Request, Response
from fastapi.responses import JSONResponse

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "release_check.py"
CHECKS = {
    "pages",
    "assets",
    "versions",
    "account",
    "oauth",
    "ad_library",
    "watchlist",
    "saved_competitor",
}
SECRET_STATE = "fixture-private-oauth-state"
SECRET_CHALLENGE = "fixture-private-code-challenge"

# The checker runs unchanged, but cannot accidentally follow an OAuth redirect off-host.
# This process does not import application configuration or read dotenv files.
CHILD = """
import runpy, socket, sys
original_connect = socket.socket.connect
def local_connect(sock, address):
    if not isinstance(address, tuple) or address[0] != '127.0.0.1':
        print('FORBIDDEN_EXTERNAL_CONNECTION', file=sys.stderr)
        raise AssertionError('Only the fixture server may be contacted')
    return original_connect(sock, address)
socket.socket.connect = local_connect
sys.argv = sys.argv[1:]
runpy.run_path(sys.argv[0], run_name='__main__')
"""


@pytest.fixture
def release_server(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> Iterator[Callable[..., tuple[str, list[str]]]]:
    """Serve copied app routes; no static file, global route, or durable state mutations."""
    monkeypatch.setenv("DEMO_MODE", "true")
    monkeypatch.setenv("DEMO_KEY", "")
    monkeypatch.setenv("OUTPUT_DIR", str(tmp_path / "outputs"))
    monkeypatch.setenv("WATCHLIST_AUTO_CHECK_ENABLED", "false")
    from src.api import accounts, intel
    from src.api.main import app
    from src.clients.meta import MetaClient
    from src.config import get_settings
    from src.services import competitor_intel, scan_guard

    get_settings.cache_clear()
    external_calls: list[str] = []

    async def forbidden(*args: Any, **kwargs: Any) -> Any:
        external_calls.append("provider_or_crawl")
        raise AssertionError("Release checks must not call providers or crawl")

    async def snapshot(account: Any) -> dict[str, Any]:
        return {"configured": True, "user": None}

    async def resolve_account(*args: Any, **kwargs: Any) -> None:
        return None

    monkeypatch.setattr(intel, "load_workspace", forbidden)
    monkeypatch.setattr(intel, "save_workspace", forbidden)
    monkeypatch.setattr(accounts, "snapshot", snapshot)
    monkeypatch.setattr(accounts, "resolve_account", resolve_account)
    monkeypatch.setattr(httpx.AsyncClient, "send", forbidden)
    monkeypatch.setattr(competitor_intel.CompetitorIntelService, "analyze", forbidden)
    monkeypatch.setattr(scan_guard, "crawl", forbidden)
    for name in ("chat_structured", "generate_image", "generate_image_workflow", "segment_image"):
        if hasattr(MetaClient, name):
            monkeypatch.setattr(MetaClient, name, forbidden)

    servers: list[tuple[uvicorn.Server, threading.Thread, socket.socket]] = []

    def start(
        mutation: str = "",
        *,
        oauth: str = "valid",
        watchlist_status: int | None = None,
        watchlist_on: bool = False,
    ) -> tuple[str, list[str]]:
        monkeypatch.setenv("WATCHLIST_AUTO_CHECK_ENABLED", str(watchlist_on).lower())
        get_settings.cache_clear()
        fixture_app = copy.copy(app)
        fixture_app.router = copy.copy(app.router)
        fixture_app.router.routes = list(app.router.routes)
        # A shallow-copied router retains its original bound dispatch method.
        fixture_app.router.middleware_stack = fixture_app.router.app
        fixture_app.user_middleware = list(app.user_middleware)
        fixture_app.middleware_stack = None
        if mutation == "missing_progress":
            fixture_app.router.routes = [
                route
                for route in fixture_app.router.routes
                if getattr(route, "path", None) != "/progress"
            ]

        async def start_google(request: Request, response: Response, next_path: str | None) -> str:
            callback = str(request.base_url).rstrip("/") + "/api/v1/account/oauth/google/callback"
            if oauth == "wrong_callback":
                callback = "https://wrong.example/api/v1/account/oauth/google/callback"
            host = "accounts.google.com" if oauth != "wrong_host" else "wrong.example"
            response.set_cookie("muse_oauth_state", SECRET_STATE)
            return f"https://{host}/o/oauth2/v2/auth?" + urlencode(
                {
                    "redirect_uri": callback,
                    "state": SECRET_STATE,
                    "code_challenge": SECRET_CHALLENGE,
                    "code_challenge_method": "S256",
                    "response_type": "code",
                }
            )

        monkeypatch.setattr(accounts, "start_google_oauth", start_google)
        requests: list[str] = []

        @fixture_app.middleware("http")
        async def mutate(request: Request, call_next: Any) -> Response:
            path = request.url.path
            requests.append(f"{request.method} {path}")
            if mutation.startswith("saved_") and path == "/api/v1/competitors/saved":
                assert request.method == "PUT"
                return Response(status_code=int(mutation.removeprefix("saved_")))
            if mutation == "guard_200" and path == "/api/v1/analyze-competitors":
                assert request.method == "POST"
                return JSONResponse({"unexpected_success": True})
            if mutation == "broken_asset" and path == "/static/account.js":
                return Response(status_code=404)
            if mutation == "auth_unconfigured" and path == "/api/v1/account/me":
                return JSONResponse({"configured": False, "user": None})
            if mutation == "auth_user" and path == "/api/v1/account/me":
                return JSONResponse({"configured": True, "user": {"id": "fixture-user"}})
            if watchlist_status is not None and path == "/api/v1/watchlist/run":
                return Response(status_code=watchlist_status)
            response = await call_next(request)
            if path == "/today" and mutation in {"script_version", "missing_link"}:
                body = b"".join([chunk async for chunk in response.body_iterator]).decode()
                if mutation == "script_version":
                    body, count = re.subn(
                        r'(/static/account\.js\?v=)[^"\s]+',
                        r"\g<1>fixture-stale-version",
                        body,
                        count=1,
                    )
                    assert count == 1, "Fixture must mutate an existing shared script"
                else:
                    body += '<a href="/release-fixture-missing-page">Broken page</a>'
                headers = dict(response.headers)
                headers.pop("content-length", None)
                return Response(body, status_code=response.status_code, headers=headers)
            return response

        listener = socket.socket()
        listener.bind(("127.0.0.1", 0))
        config = uvicorn.Config(fixture_app, log_level="error", lifespan="off", access_log=False)
        server = uvicorn.Server(config)
        thread = threading.Thread(target=server.run, kwargs={"sockets": [listener]}, daemon=True)
        servers.append((server, thread, listener))
        thread.start()
        deadline = time.monotonic() + 10
        while not server.started and thread.is_alive() and time.monotonic() < deadline:
            time.sleep(0.01)
        assert server.started, "Local fixture server did not start"
        return f"http://127.0.0.1:{listener.getsockname()[1]}", requests

    yield start
    for server, thread, listener in servers:
        server.should_exit = True
        thread.join(timeout=10)
        listener.close()
        assert not thread.is_alive(), "Fixture server did not stop"
    assert external_calls == [], "Checker reached a provider or crawler"


def run_check(
    base: str, *, skip_oauth: bool = True, json_output: bool = True, watchlist: str = "off"
) -> subprocess.CompletedProcess[str]:
    assert SCRIPT.is_file(), (
        "Parent must finish scripts/release_check.py before running these tests"
    )
    command = [
        sys.executable,
        "-B",
        "-c",
        CHILD,
        str(SCRIPT),
        "--base",
        base,
        "--transport",
        "http",
        "--watchlist",
        watchlist,
    ]
    if json_output:
        command.append("--json")
    if skip_oauth:
        command.append("--skip-oauth")
    result = subprocess.run(
        command,
        cwd=ROOT,
        env={
            "DEMO_MODE": "true",
            "META_MODEL_API_KEY": "",
            "DEMO_KEY": "",
            "PYTHONIOENCODING": "utf-8",
        },
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert "FORBIDDEN_EXTERNAL_CONNECTION" not in result.stderr, result.stderr
    return result


def report(result: subprocess.CompletedProcess[str]) -> dict[str, dict[str, Any]]:
    data = json.loads(result.stdout)
    assert isinstance(data["ok"], bool)
    assert isinstance(data["checks"], list)
    checks = {item["name"]: item for item in data["checks"]}
    assert set(checks) == CHECKS
    assert len(checks) == len(data["checks"])
    for item in checks.values():
        assert isinstance(item["ok"], bool)
        assert isinstance(item["detail"], str)
    assert data["ok"] == all(item["ok"] for item in checks.values())
    assert result.returncode == (0 if data["ok"] else 1), result.stderr
    return checks


def test_release_check_passes_real_app(release_server: Callable[..., Any]) -> None:
    base, requests = release_server()
    result = run_check(base)
    checks = report(result)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "skipped" in checks["oauth"]["detail"].lower()
    assert "GET /api/v1/account/oauth/google" not in requests
    assert "POST /api/v1/analyze-competitors" in requests
    assert "GET /api/v1/watchlist/run" in requests
    for page in ("/progress", "/today", "/create", "/portal", "/api/v1/health"):
        assert f"GET {page}" in requests


@pytest.mark.parametrize(
    ("mutation", "failed_check"),
    [
        ("missing_progress", "pages"),
        ("script_version", "versions"),
        ("guard_200", "ad_library"),
        ("missing_link", "pages"),
        ("broken_asset", "assets"),
        ("auth_unconfigured", "account"),
        ("auth_user", "account"),
        ("saved_200", "saved_competitor"),
        ("saved_500", "saved_competitor"),
    ],
)
def test_release_mutations_fail_correct_check(
    release_server: Callable[..., Any], mutation: str, failed_check: str
) -> None:
    base, _ = release_server(mutation)
    result = run_check(base)
    checks = report(result)
    assert result.returncode == 1, result.stdout
    assert checks[failed_check]["ok"] is False, result.stdout
    assert {name for name, check in checks.items() if not check["ok"]} == {failed_check}


@pytest.mark.parametrize("status", [200, 500])
def test_watchlist_unsafe_status_fails(release_server: Callable[..., Any], status: int) -> None:
    base, _ = release_server(watchlist_status=status)
    result = run_check(base)
    checks = report(result)
    assert result.returncode == 1, result.stdout
    assert checks["watchlist"]["ok"] is False


@pytest.mark.parametrize("oauth", ["valid", "wrong_host", "wrong_callback"])
@pytest.mark.parametrize("json_output", [True, False])
def test_oauth_validates_redirect_and_never_prints_secrets(
    release_server: Callable[..., Any], oauth: str, json_output: bool
) -> None:
    base, requests = release_server(oauth=oauth)
    result = run_check(base, skip_oauth=False, json_output=json_output)
    assert result.returncode == (0 if oauth == "valid" else 1), result.stdout + result.stderr
    if json_output:
        checks = report(result)
        assert checks["oauth"]["ok"] is (oauth == "valid")
    else:
        assert "PASS" in result.stdout
        if oauth != "valid":
            assert "FAIL" in result.stdout
    assert "GET /api/v1/account/oauth/google" in requests
    assert "GET /api/v1/account/oauth/google/callback" not in requests
    for secret in (SECRET_STATE, SECRET_CHALLENGE, "muse_oauth_state"):
        assert secret not in result.stdout + result.stderr


@pytest.mark.parametrize(("mode", "status"), [("off", 401), ("on", 404)])
def test_watchlist_wrong_mode_fails(
    release_server: Callable[..., Any], mode: str, status: int
) -> None:
    base, _ = release_server(watchlist_status=status)
    checks = report(run_check(base, watchlist=mode))
    assert checks["watchlist"]["ok"] is False


def test_watchlist_on_refuses_without_secret(release_server: Callable[..., Any]) -> None:
    base, requests = release_server(watchlist_on=True)
    result = run_check(base, watchlist="on")
    checks = report(result)
    assert result.returncode == 0, result.stdout
    assert checks["watchlist"]["ok"] is True
    assert "PUT /api/v1/competitors/saved" in requests


@pytest.fixture
def checker() -> dict[str, Any]:
    import runpy

    return runpy.run_path(str(SCRIPT), run_name="release_check_tests")


def test_vercel_transport_keeps_status_and_never_follows_redirects(
    checker: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    commands = []

    def run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[bytes]:
        commands.append(command)
        assert kwargs["capture_output"] is True
        return subprocess.CompletedProcess(
            command,
            0,
            b"HTTP/1.1 200 Connection established\r\n\r\n"
            b"HTTP/2 302 Found\r\nLocation: https://accounts.google.com/?state=private\r\n"
            b"Set-Cookie: secret=private\r\n\r\n",
        )

    monkeypatch.setattr(subprocess, "run", run)
    # This reserved local name is never resolved: the CLI process is fully mocked.
    transport = checker["Transport"]("https://preview.example.test", "vercel")
    reply = transport.request("/api/v1/account/oauth/google")
    assert reply.status == 302
    command = commands[0]
    assert command[:5] == [
        "vercel",
        "curl",
        "/api/v1/account/oauth/google",
        "--deployment",
        "https://preview.example.test",
    ]
    assert command[command.index("--max-redirs") + 1] == "0"
    assert "--location" not in command
    assert "--include" in command


@pytest.mark.parametrize("status", [401, 404, 422, 500])
def test_transport_parses_expected_http_errors(checker: dict[str, Any], status: int) -> None:
    raw = f"HTTP/2 {status} Response\r\nContent-Type: application/json\r\n\r\n{{}}".encode()
    reply = checker["parse_http"](raw)
    assert reply.status == status
    assert reply.data() == {}


@pytest.mark.parametrize(
    ("payload", "ok", "detail"),
    [
        ("[]", True, "No 5xx"),
        ('[{"statusCode":200,"path":"/"}]', True, "No 5xx"),
        ('{"statusCode":500,"method":"GET","path":"/users/alice"}', False, "GET /[redacted]"),
        ('{"statusCode":503,"method":"GET","path":"/today?token=private"}', False, "GET /today"),
        (
            '{"statusCode":500,"method":"POST","path":"/api/users/alice@example.test"}',
            False,
            "POST /[redacted]",
        ),
        ('{"email":"private@example.test"}', False, "schema unrecognized"),
        ("not json containing private", False, "schema unrecognized"),
    ],
)
def test_logs_fail_closed_and_redact(
    checker: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
    payload: str,
    ok: bool,
    detail: str,
) -> None:
    def run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        assert command == [
            "vercel",
            "logs",
            "requests",
            "-p",
            "meta-smb-gtm",
            "--scope",
            "navtejs-6321s-projects",
            "--since",
            "15m",
            "--json",
        ]
        return subprocess.CompletedProcess(command, 0, payload)

    monkeypatch.setattr(subprocess, "run", run)
    result = checker["check_logs"]()
    assert result.ok is ok
    assert detail in result.detail
    assert "private" not in result.detail
    assert "alice" not in result.detail


def test_oauth_unknown_parameters_not_echoed(checker: dict[str, Any]) -> None:
    from types import SimpleNamespace

    callback = "http://localhost/api/v1/account/oauth/google/callback"
    location = "https://accounts.google.com/o/oauth2/v2/auth?" + urlencode(
        {
            "redirect_uri": callback,
            "state": SECRET_STATE,
            "code_challenge": SECRET_CHALLENGE,
            "login_hint": "private@example.test",
            "unknown": "private-token",
        }
    )
    transport = SimpleNamespace(
        base="http://localhost",
        request=lambda path: checker["Reply"](302, {"location": location}, b""),
    )
    result = checker["check_oauth"](transport)
    assert result.ok
    for private in (SECRET_STATE, SECRET_CHALLENGE, "private", "login_hint", "state"):
        assert private not in result.detail
