#!/usr/bin/env python3
"""Check release surfaces without signing in, following redirects, or using AI runs."""

from __future__ import annotations

import argparse
import json
import subprocess
from dataclasses import asdict, dataclass
from html.parser import HTMLParser
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlencode, urljoin, urlsplit, urlunsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

PAGES = (
    "/",
    "/today",
    "/create",
    "/digest",
    "/welcome",
    "/first-ad",
    "/account",
    "/progress",
    "/portal",
    "/static/legal/privacy.html",
    "/static/legal/terms.html",
    "/static/legal/refunds.html",
    "/api/v1/health",
)
SOCIAL_REFUSAL = (
    "That is a Facebook or Instagram link. Muse can't read those pages, so use the "
    "competitor's own website instead. No run was used."
)
MAX_BYTES = 5_000_000


@dataclass
class Check:
    name: str
    ok: bool
    detail: str


@dataclass
class Reply:
    status: int
    headers: dict[str, str]
    body: bytes

    def data(self) -> object:
        return json.loads(self.body)


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args: object, **kwargs: object) -> None:
        return None


class References(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[str] = []
        self.assets: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        if tag == "a" and values.get("href"):
            self.links.append(values["href"] or "")
        if tag == "script" and values.get("src"):
            self.assets.append(values["src"] or "")
        if tag == "link" and "stylesheet" in (values.get("rel") or "").split():
            self.assets.append(values.get("href") or "")


def parse_http(raw: bytes) -> Reply:
    """Parse curl's included headers, including proxy/interim header blocks."""
    while True:
        header, separator, body = raw.partition(b"\r\n\r\n")
        if not separator:
            raise ValueError("Missing HTTP headers")
        lines = header.decode("iso-8859-1").splitlines()
        status = int(lines[0].split()[1])
        headers = dict(
            (key.strip().lower(), value.strip())
            for line in lines[1:]
            if ":" in line
            for key, value in [line.split(":", 1)]
        )
        if body.startswith(b"HTTP/"):
            raw = body
            continue
        return Reply(status, headers, body)


class Transport:
    def __init__(self, base: str, mode: str) -> None:
        self.base, self.mode = base, mode
        self.opener = build_opener(ProxyHandler({}), NoRedirect())

    def request(self, path: str, method: str = "GET", data: object = None) -> Reply:
        if not path.startswith("/") or path.startswith("//"):
            raise ValueError("Only same-origin paths are allowed")
        body = json.dumps(data).encode() if data is not None else None
        if self.mode == "vercel":
            command = [
                "vercel",
                "curl",
                path,
                "--deployment",
                self.base,
                "--",
                "--request",
                method,
                "--include",
                "--max-redirs",
                "0",
                "--max-time",
                "20",
                "--silent",
            ]
            if body is not None:
                command += ["--header", "Content-Type: application/json", "--data", body.decode()]
            result = subprocess.run(command, capture_output=True, timeout=30, check=False)
            if result.returncode:
                raise ValueError("Vercel transport failed")
            return parse_http(result.stdout)
        request = Request(
            self.base + path,
            data=body,
            method=method,
            headers={"Content-Type": "application/json"} if body is not None else {},
        )
        try:
            response = self.opener.open(request, timeout=20)
        except HTTPError as error:
            response = error
        with response:
            content = response.read(MAX_BYTES + 1)
            if len(content) > MAX_BYTES:
                raise ValueError("Response exceeds check limit")
            return Reply(
                response.code, {k.lower(): v for k, v in response.headers.items()}, content
            )


def local_reference(base: str, page: str, value: str) -> str | None:
    if not value or value.startswith("#"):
        return None
    target = urlsplit(urljoin(base + page, value))
    if (target.scheme, target.netloc) != (urlsplit(base).scheme, urlsplit(base).netloc):
        return None
    # Query strings/fragments cannot select additional routes and are never printed.
    return target.path or "/"


def check_surfaces(transport: Transport) -> list[Check]:
    pending = list(PAGES)
    seen: set[str] = set()
    failures: list[str] = []
    assets: set[str] = set()
    versions: dict[str, set[tuple[str, ...]]] = {}
    while pending:
        page = pending.pop(0)
        if page in seen:
            continue
        seen.add(page)
        if len(seen) > 100:
            failures.append("Page discovery limit exceeded")
            break
        try:
            reply = transport.request(page)
            if reply.status != 200:
                failures.append(f"{page}: HTTP {reply.status}")
                continue
            if "text/html" not in reply.headers.get("content-type", ""):
                continue
            refs = References()
            refs.feed(reply.body.decode("utf-8"))
            for link in refs.links:
                target = local_reference(transport.base, page, link)
                if (
                    target
                    and not target.startswith(("/api/", "/static/", "/samples/"))
                    or target
                    and target.endswith(".html")
                ):
                    pending.append(target)
            for asset in refs.assets:
                path = local_reference(transport.base, page, asset)
                if path and path.startswith("/static/"):
                    query = urlsplit(urljoin(transport.base + page, asset)).query
                    assets.add(path + ("?" + query if query else ""))
                    if path.endswith(".js"):
                        versions.setdefault(path, set()).add(tuple(parse_qs(query).get("v", [])))
        except Exception:
            failures.append(f"{page}: request or page parsing failed")
    broken_assets = []
    for asset in sorted(assets):
        try:
            status = transport.request(asset).status
            if status != 200:
                broken_assets.append(f"{urlsplit(asset).path}: HTTP {status}")
        except Exception:
            broken_assets.append(f"{urlsplit(asset).path}: request failed")
    inconsistent = [path for path, values in versions.items() if len(values) > 1]
    return [
        Check("pages", not failures, "; ".join(failures) or f"{len(seen)} routes returned 200"),
        Check(
            "assets",
            not broken_assets and bool(assets),
            "; ".join(broken_assets) or f"{len(assets)} script/stylesheet references returned 200",
        ),
        Check(
            "versions", not inconsistent, "; ".join(inconsistent) or "Shared script versions agree"
        ),
    ]


def check_oauth(transport: Transport) -> Check:
    reply = transport.request("/api/v1/account/oauth/google")
    location = urlsplit(reply.headers.get("location", ""))
    query = parse_qs(location.query)
    callback = transport.base + "/api/v1/account/oauth/google/callback"
    valid = (
        reply.status == 302
        and location.scheme == "https"
        and location.netloc == "accounts.google.com"
        and query.get("redirect_uri") == [callback]
    )
    # Allowlist output fields: unknown query values can also contain credentials.
    safe = (
        urlunsplit(
            (
                "https",
                "accounts.google.com",
                location.path,
                urlencode({"redirect_uri": callback}),
                "",
            )
        )
        if valid
        else ""
    )
    return Check("oauth", valid, safe if valid else "Google redirect or callback did not match")


def check_api(transport: Transport, watchlist: str, skip_oauth: bool) -> list[Check]:
    checks = []
    for name in ("account", "oauth", "ad_library", "watchlist", "saved_competitor"):
        try:
            if name == "account":
                reply = transport.request("/api/v1/account/me")
                data = reply.data()
                ok = (
                    reply.status == 200
                    and isinstance(data, dict)
                    and data.get("configured") is True
                    and "user" in data
                    and data["user"] is None
                )
                check = Check(
                    name, ok, "Configured and signed out" if ok else "Account state mismatch"
                )
            elif name == "oauth":
                check = (
                    Check(name, True, "Skipped for local development")
                    if skip_oauth
                    else check_oauth(transport)
                )
            elif name == "ad_library":
                reply = transport.request(
                    "/api/v1/analyze-competitors",
                    "POST",
                    {
                        "competitor_url": "https://www.facebook.com/ads/library/?view_all_page_id=123",
                        "seller_description": "Local release check",
                    },
                )
                ok = reply.status == 422 and reply.data() == {"detail": SOCIAL_REFUSAL}
                check = Check(
                    name,
                    ok,
                    f"HTTP {reply.status}; social-link refusal "
                    + ("matched" if ok else "did not match"),
                )
            elif name == "watchlist":
                expected = 401 if watchlist == "on" else 404
                status = transport.request("/api/v1/watchlist/run").status
                check = Check(
                    name, status == expected, f"HTTP {status}; expected {expected} ({watchlist})"
                )
            else:
                status = transport.request(
                    "/api/v1/competitors/saved",
                    "PUT",
                    {
                        "competitor_url": "https://example.com",
                        "name": "Example",
                    },
                ).status
                check = Check(name, status == 401, f"HTTP {status}; expected signed-out 401")
        except Exception:
            check = Check(name, False, "Request failed or response was invalid")
        checks.append(check)
    return checks


def check_logs() -> Check:
    """Read CLI JSON internally; emit only a method and pathname for server errors."""
    try:
        result = subprocess.run(
            [
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
            ],
            capture_output=True,
            text=True,
            timeout=45,
            check=False,
        )
        if result.returncode:
            raise ValueError("Log command failed")
        try:
            parsed = json.loads(result.stdout)
        except ValueError:
            parsed = [json.loads(line) for line in result.stdout.splitlines() if line.strip()]
        if isinstance(parsed, dict):
            parsed = parsed.get("logs", parsed.get("requests", [parsed]))
        if not isinstance(parsed, list):
            raise ValueError("Unknown log schema")
        failures = []
        for item in parsed:
            if not isinstance(item, dict):
                raise ValueError("Unknown log entry")
            if item.get("type") == "summary":
                if item.get("pagination", {}).get("hasMore") or item.get("excludedIntervals"):
                    raise ValueError("Log window incomplete")
                continue
            if "type" in item:
                if item["type"] != "request" or not isinstance(item.get("data"), dict):
                    raise ValueError("Unknown record type or incomplete logs")
                item = item["data"]
            status = item.get(
                "httpStatus",
                item.get("statusCode", item.get("status", item.get("responseStatusCode"))),
            )
            if status is None:
                raise ValueError("Missing request status")
            if 500 <= int(status) <= 599:
                method = item.get("requestMethod", item.get("method", "UNKNOWN"))
                method = (
                    method
                    if method in {"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"}
                    else "UNKNOWN"
                )
                raw_path = item.get("requestPath", item.get("path", "/"))
                path = urlsplit(str(raw_path)).path
                # Unknown/dynamic paths may contain user identities even without a query.
                known_paths = set(PAGES) | {
                    "/api/v1/account/me",
                    "/api/v1/account/oauth/google",
                    "/api/v1/analyze-competitors",
                    "/api/v1/watchlist/run",
                    "/api/v1/competitors/saved",
                }
                if path not in known_paths:
                    path = "/[redacted]"
                failures.append(f"{method} {path}")
        return Check("logs", not failures, "; ".join(failures) or "No 5xx in the last 15 minutes")
    except Exception:
        return Check("logs", False, "Request logs unavailable or schema unrecognized")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", default="https://meta-smb-gtm.vercel.app")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--logs", action="store_true")
    parser.add_argument("--skip-oauth", action="store_true")
    parser.add_argument("--watchlist", choices=("on", "off"), default="off")
    parser.add_argument("--transport", choices=("http", "vercel"), default="http")
    args = parser.parse_args()
    base = args.base.rstrip("/")
    url = urlsplit(base)
    if (
        url.scheme not in {"http", "https"}
        or not url.hostname
        or url.username
        or url.password
        or url.query
        or url.fragment
        or url.path
    ):
        parser.error(
            "--base must be an HTTP(S) origin without credentials, path, query or fragment"
        )
    if args.skip_oauth and url.hostname not in {"127.0.0.1", "localhost", "::1"}:
        parser.error("--skip-oauth is only allowed on loopback")
    transport = Transport(base, args.transport)
    checks = check_surfaces(transport) + check_api(transport, args.watchlist, args.skip_oauth)
    if args.logs:
        checks.append(check_logs())
    ok = all(check.ok for check in checks)
    if args.json:
        print(json.dumps({"ok": ok, "checks": [asdict(check) for check in checks]}))
    else:
        for check in checks:
            print(f"{'PASS' if check.ok else 'FAIL'}  {check.name:17} {check.detail}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
