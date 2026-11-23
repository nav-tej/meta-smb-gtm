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

    assert by_name["Rival Unchanged"]["status"] == "fresh"
    assert by_name["Rival Unchanged"]["note"] == "No changes since Nov 21."
    assert by_name["Rival Unchanged"]["checked_at"] == "2026-11-22T10:00:00Z"

    assert by_name["Rival Error"]["status"] == "unchecked"
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


# ---------------------------------------------------------------------------
# Item 2: YouTube public Atom/RSS feed unit tests
# ---------------------------------------------------------------------------

from fastapi import HTTPException  # noqa: E402

from src.api import seller_memory as memory_api  # noqa: E402
from src.services import scan_guard  # noqa: E402
from src.services import youtube_feed as yt  # noqa: E402

VALID_CHANNEL_ID = "UC1234567890abcdefABCD12"
VALID_FEED_URL = f"https://www.youtube.com/feeds/videos.xml?channel_id={VALID_CHANNEL_ID}"


def _make_feed_xml(entries: list[dict[str, str]]) -> bytes:
    items = []
    for item in entries:
        link_href = item.get("link_href", f"https://www.youtube.com/watch?v={item['video_id']}")
        items.append(
            f"""
            <entry>
              <id>yt:video:{item["video_id"]}</id>
              <yt:videoId>{item["video_id"]}</yt:videoId>
              <title>{item["title"]}</title>
              <link rel="alternate" href="{link_href}"/>
              <published>{item["published"]}</published>
              <media:group>
                <media:description>{item.get("description", "")}</media:description>
              </media:group>
            </entry>
            """
        )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<feed xmlns:yt="http://www.youtube.com/xml/schemas/2015"'
        ' xmlns:media="http://search.yahoo.com/mrss/"'
        ' xmlns="http://www.w3.org/2005/Atom">' + "".join(items) + "</feed>"
    ).encode("utf-8")


@pytest.mark.parametrize(
    "raw_url, expected_channel, expected_feed",
    [
        ("https://youtube.com/@northstar", "https://www.youtube.com/@northstar", None),
        ("https://www.youtube.com/@northstar/videos", "https://www.youtube.com/@northstar", None),
        ("https://m.youtube.com/@northstar", "https://www.youtube.com/@northstar", None),
        ("youtube.com/@northstar", "https://www.youtube.com/@northstar", None),
        (
            f"https://youtube.com/channel/{VALID_CHANNEL_ID}",
            f"https://www.youtube.com/channel/{VALID_CHANNEL_ID}",
            VALID_FEED_URL,
        ),
        (
            f"https://m.youtube.com/channel/{VALID_CHANNEL_ID}/videos",
            f"https://www.youtube.com/channel/{VALID_CHANNEL_ID}",
            VALID_FEED_URL,
        ),
        (
            "https://www.youtube.com/c/NorthstarStudio",
            "https://www.youtube.com/c/NorthstarStudio",
            None,
        ),
        (
            "https://youtube.com/user/NorthstarLegacy",
            "https://www.youtube.com/user/NorthstarLegacy",
            None,
        ),
    ],
)
def test_parse_youtube_channel_url_forms(
    raw_url: str, expected_channel: str, expected_feed: str | None
) -> None:
    channel_url, feed_url = yt.parse_youtube_channel_url(raw_url)
    assert channel_url == expected_channel
    assert feed_url == expected_feed


@pytest.mark.parametrize(
    "bad_url",
    [
        "",
        "not-a-channel",
        "https://vimeo.com/northstar",
        "https://evil-youtube.com/@northstar",
        "javascript:alert(1)",
        "https://youtube.com/watch?v=dQw4w9WgXcQ",
        "https://youtube.com/channel/UCshort",
        "https://youtube.com/channel/XX1234567890abcdefABCD12",
        "https://user:pass@youtube.com/@northstar",
        "https://youtube.com:8443/@northstar",
    ],
)
def test_parse_youtube_channel_url_rejects_invalid(bad_url: str) -> None:
    with pytest.raises(yt.YouTubeFeedError) as exc_info:
        yt.parse_youtube_channel_url(bad_url)
    assert exc_info.value.user_message == yt.ERR_INVALID_URL


def test_discover_feed_url_from_html_accepts_only_canonical_youtube_feed() -> None:
    good_html = (
        f'<html><head><link rel="alternate" type="application/rss+xml"'
        f' title="RSS" href="{VALID_FEED_URL}"></head></html>'
    )
    assert yt.discover_feed_url_from_html(good_html) == VALID_FEED_URL

    for bad_href in (
        f"http://www.youtube.com/feeds/videos.xml?channel_id={VALID_CHANNEL_ID}",
        f"https://evil.example/feeds/videos.xml?channel_id={VALID_CHANNEL_ID}",
        f"https://www.youtube.com/feeds/videos.xml?channel_id={VALID_CHANNEL_ID}&amp;extra=1",
        "https://www.youtube.com/feeds/videos.xml?channel_id=UCtooshort",
        "javascript:alert(1)",
    ):
        bad_html = (
            f'<html><head><link rel="alternate" type="application/rss+xml"'
            f' href="{bad_href}"></head></html>'
        )
        assert yt.discover_feed_url_from_html(bad_html) is None


def test_parse_youtube_feed_refuses_hostile_xml_entities_and_xxe() -> None:
    billion_laughs = b"""<?xml version="1.0"?>
    <!DOCTYPE lolz [
      <!ENTITY lol "lol">
      <!ENTITY lol2 "&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;">
    ]>
    <feed xmlns="http://www.w3.org/2005/Atom"><title>&lol2;</title></feed>
    """
    xxe = b"""<?xml version="1.0"?>
    <!DOCTYPE foo [<!ENTITY xxe SYSTEM "file:///etc/passwd">]>
    <feed xmlns="http://www.w3.org/2005/Atom"><title>&xxe;</title></feed>
    """
    for payload in (billion_laughs, xxe):
        with pytest.raises(yt.YouTubeFeedError) as exc_info:
            yt.parse_youtube_feed_xml(payload)
        assert exc_info.value.user_message == yt.ERR_NO_FEED


def test_parse_youtube_feed_caps_and_rebuilds_links_from_video_id() -> None:
    entries = []
    for idx in range(12):
        vid = f"VidID0000{idx:02d}"
        entries.append(
            {
                "video_id": vid,
                "title": f"Video {idx:02d} " + ("T" * 200),
                "published": f"2026-11-{10 + idx:02d}T12:00:00+00:00",
                "description": f"<p>Desc {idx:02d}</p> " + ("D" * 400),
                "link_href": (
                    "javascript:alert(1)" if idx % 2 == 0 else "https://evil.example/phish"
                ),
            }
        )
    # Also inject an invalid video_id that must be skipped
    entries.append(
        {
            "video_id": "bad",
            "title": "Should be skipped",
            "published": "2026-11-23T00:00:00Z",
            "link_href": "javascript:alert(2)",
        }
    )

    videos = yt.parse_youtube_feed_xml(_make_feed_xml(entries))
    assert len(videos) == 10
    # Newest first (idx 11 down to 2)
    assert videos[0]["video_id"] == "VidID000011"
    assert videos[-1]["video_id"] == "VidID000002"
    for item in videos:
        assert len(item["title"]) <= 140
        assert len(item["description"]) <= 300
        assert "<p>" not in item["description"]
        assert item["url"] == f"https://www.youtube.com/watch?v={item['video_id']}"
        assert item["thumbnail_url"] == f"https://i.ytimg.com/vi/{item['video_id']}/hqdefault.jpg"
        assert "javascript:" not in item["url"]
        assert "evil.example" not in item["url"]


@pytest.mark.asyncio
async def test_fetch_youtube_channel_videos_direct_and_autodiscovery(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scan_guard.reset()
    requested_urls: list[str] = []
    feed_xml = _make_feed_xml(
        [
            {
                "video_id": "AbCdEfGh123",
                "title": "How we scope advisory engagements",
                "published": "2026-11-22T15:00:00Z",
                "description": "Walkthrough for founders.",
                "link_href": "https://evil.example/redirect",
            }
        ]
    )
    channel_html = (
        f'<html><head><link rel="alternate" type="application/rss+xml"'
        f' href="{VALID_FEED_URL}"></head></html>'
    ).encode()

    def handler(request: httpx.Request) -> httpx.Response:
        url_str = str(request.url)
        requested_urls.append(url_str)
        if url_str.endswith("/robots.txt"):
            return httpx.Response(200, text="User-agent: *\nAllow: /\n")
        if url_str == "https://www.youtube.com/@northstar":
            return httpx.Response(200, content=channel_html)
        if url_str == VALID_FEED_URL:
            return httpx.Response(200, content=feed_xml)
        return httpx.Response(404)

    async def fake_resolver(_host: str) -> list[str]:
        return ["93.184.216.34"]

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        # 1. Direct /channel/UC... skips channel HTML GET
        direct = await yt.fetch_youtube_channel_videos(
            f"https://youtube.com/channel/{VALID_CHANNEL_ID}",
            client=client,
            resolver=fake_resolver,
        )
        assert requested_urls == [VALID_FEED_URL]
        assert direct["feed_url"] == VALID_FEED_URL
        assert direct["videos"][0]["url"] == "https://www.youtube.com/watch?v=AbCdEfGh123"

        # 2. /@handle does robots.txt + one channel GET + feed GET
        requested_urls.clear()
        discovered = await yt.fetch_youtube_channel_videos(
            "https://youtube.com/@northstar",
            client=client,
            resolver=fake_resolver,
        )
        assert "https://www.youtube.com/@northstar" in requested_urls
        assert VALID_FEED_URL in requested_urls
        assert discovered["channel_url"] == "https://www.youtube.com/@northstar"
        assert discovered["feed_url"] == VALID_FEED_URL
        assert len(discovered["videos"]) == 1


@pytest.mark.asyncio
async def test_fetch_youtube_channel_videos_maps_timeout_to_plain_error() -> None:
    scan_guard.reset()

    def timeout_handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timed out", request=request)

    async def fake_resolver(_host: str) -> list[str]:
        return ["93.184.216.34"]

    async with httpx.AsyncClient(transport=httpx.MockTransport(timeout_handler)) as client:
        with pytest.raises(yt.YouTubeFeedError) as exc_info:
            await yt.fetch_youtube_channel_videos(
                f"https://youtube.com/channel/{VALID_CHANNEL_ID}",
                client=client,
                resolver=fake_resolver,
            )
        assert exc_info.value.user_message == yt.ERR_TIMEOUT
        assert exc_info.value.status_code == 504


# ---------------------------------------------------------------------------
# Item 2: Route tests for POST /api/v1/seller-memory/sources/youtube
# ---------------------------------------------------------------------------


@pytest.fixture
def yt_route_harness(
    _never_use_real_meta_key: None, monkeypatch: pytest.MonkeyPatch
) -> SimpleNamespace:
    scan_guard.reset()
    monkeypatch.setenv("DEMO_MODE", "true")
    monkeypatch.setenv("META_MODEL_API_KEY", "")
    monkeypatch.setenv("DEMO_KEY", "")
    monkeypatch.setenv("SCANS_PER_VISITOR_PER_10_MIN", "0")
    get_settings.cache_clear()

    def no_network(*args: Any, **kwargs: Any) -> None:
        pytest.fail("Route attempted real outbound HTTP")

    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", no_network)
    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", no_network)

    state: dict[str, Any] = {
        "version": 3,
        "doc": {
            "onboarding": {
                "business_name": "Northstar Advisory",
                "business_type": "services",
                "completed_at": "2026-11-20T12:00:00Z",
                "socials": [{"platform": "youtube", "handle": "@northstar"}],
                "competitors": [{"name": "Rival One", "url": "https://rival-one.example"}],
            },
            "preferences": {
                "goal": "Grow inquiries",
                "competitor_checks": {
                    "https://rival-one.example": {
                        "status": "first_check",
                        "checked_at": "2026-11-22T10:00:00Z",
                        "summary": "First check: Muse now knows 5 of their pages.",
                        "error": "",
                    }
                },
            },
            "voice_profile": {},
        },
    }

    verified_user = AccountSession(
        user_id="yt-owner-1",
        email="owner@northstar.test",
        email_verified=True,
        access_token="offline",
        session_id=None,
    )
    unverified_user = AccountSession(
        user_id="yt-owner-2",
        email="unverified@northstar.test",
        email_verified=False,
        access_token="offline",
        session_id=None,
    )

    async def fake_resolve(
        request: Request, response: Response, require_verified: bool = False
    ) -> AccountSession | None:
        mode = request.headers.get("X-Test-Auth", "")
        if mode == "verified":
            return verified_user
        if mode == "unverified":
            if require_verified:
                raise HTTPException(403, "Verify your email first")
            return unverified_user
        if require_verified:
            raise HTTPException(401, "Sign in required")
        return None

    async def fake_load(account: AccountSession) -> dict[str, Any]:
        return {
            "document": deepcopy(state["doc"]),
            "version": state["version"],
            "owner_id": account.user_id,
        }

    async def fake_save(
        account: AccountSession,
        doc: dict[str, Any],
        *,
        expected_version: int | None = None,
        expected_owner: str | None = None,
    ) -> dict[str, Any]:
        if expected_version is not None and expected_version != state["version"]:
            raise HTTPException(409, "Version conflict")
        state["doc"] = deepcopy(doc)
        state["version"] += 1
        return {
            "document": deepcopy(state["doc"]),
            "version": state["version"],
            "owner_id": account.user_id,
        }

    fetch_mock = AsyncMock(
        return_value={
            "channel_url": "https://www.youtube.com/@northstar",
            "feed_url": VALID_FEED_URL,
            "fetched_at": "2026-11-23T12:00:00+00:00",
            "videos": [
                {
                    "video_id": "AbCdEfGh123",
                    "title": "Q4 B2B pipeline review",
                    "published": "2026-11-22",
                    "description": "How we run quarterly reviews.",
                    "url": "https://www.youtube.com/watch?v=AbCdEfGh123",
                    "thumbnail_url": "https://i.ytimg.com/vi/AbCdEfGh123/hqdefault.jpg",
                }
            ],
        }
    )

    monkeypatch.setattr(memory_api, "resolve_account", fake_resolve)
    monkeypatch.setattr(memory_api, "load_workspace", fake_load)
    monkeypatch.setattr(memory_api, "save_workspace", fake_save)
    monkeypatch.setattr(memory_api, "fetch_youtube_channel_videos", fetch_mock)
    return SimpleNamespace(client=TestClient(app), state=state, fetch_mock=fetch_mock)


def test_youtube_source_route_auth_401_403_409_429(
    yt_route_harness: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    # 401 signed out
    r401 = yt_route_harness.client.post(
        "/api/v1/seller-memory/sources/youtube",
        json={"url": "https://youtube.com/@northstar", "expected_version": 3},
    )
    assert r401.status_code == 401
    yt_route_harness.fetch_mock.assert_not_awaited()

    # 403 unverified
    r403 = yt_route_harness.client.post(
        "/api/v1/seller-memory/sources/youtube",
        headers={"X-Test-Auth": "unverified"},
        json={"url": "https://youtube.com/@northstar", "expected_version": 3},
    )
    assert r403.status_code == 403
    yt_route_harness.fetch_mock.assert_not_awaited()

    # 409 stale expected_version (before fetching)
    r409 = yt_route_harness.client.post(
        "/api/v1/seller-memory/sources/youtube",
        headers={"X-Test-Auth": "verified"},
        json={"url": "https://youtube.com/@northstar", "expected_version": 1},
    )
    assert r409.status_code == 409
    yt_route_harness.fetch_mock.assert_not_awaited()

    # 429 rate limit with Retry-After (before fetching)
    monkeypatch.setenv("SCANS_PER_VISITOR_PER_10_MIN", "1")
    get_settings.cache_clear()
    first = yt_route_harness.client.post(
        "/api/v1/seller-memory/sources/youtube",
        headers={"X-Test-Auth": "verified"},
        json={"url": "https://youtube.com/@northstar", "expected_version": 3},
    )
    assert first.status_code == 200
    assert first.json()["version"] == 4
    yt_route_harness.fetch_mock.assert_awaited_once()

    r429 = yt_route_harness.client.post(
        "/api/v1/seller-memory/sources/youtube",
        headers={"X-Test-Auth": "verified"},
        json={"url": "https://youtube.com/@northstar", "expected_version": 4},
    )
    assert r429.status_code == 429
    assert int(r429.headers["Retry-After"]) >= 1
    assert yt_route_harness.fetch_mock.await_count == 1
    get_settings.cache_clear()


def test_youtube_source_route_save_get_preserve_and_remove(
    yt_route_harness: SimpleNamespace,
) -> None:
    # Save YouTube source
    res = yt_route_harness.client.post(
        "/api/v1/seller-memory/sources/youtube",
        headers={"X-Test-Auth": "verified"},
        json={"url": "https://youtube.com/@northstar", "expected_version": 3},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["version"] == 4
    assert body["youtube"]["channel_url"] == "https://www.youtube.com/@northstar"
    assert len(body["youtube"]["videos"]) == 1

    # GET /api/v1/seller-memory returns content_sources and youtube_social_url
    got = yt_route_harness.client.get("/api/v1/seller-memory", headers={"X-Test-Auth": "verified"})
    assert got.status_code == 200
    got_body = got.json()
    assert got_body["youtube_social_url"] == "https://www.youtube.com/@northstar"
    assert got_body["content_sources"]["youtube"]["videos"][0]["video_id"] == "AbCdEfGh123"

    # Normal PUT /api/v1/seller-memory preserves BOTH content_sources and competitor_checks
    put_res = yt_route_harness.client.put(
        "/api/v1/seller-memory",
        headers={"X-Test-Auth": "verified", "X-Muse-Owner": "yt-owner-1"},
        json={
            "expected_version": 4,
            "expected_owner": "yt-owner-1",
            "preferences": {"goal": "Book 5 advisory calls this month"},
        },
    )
    assert put_res.status_code == 200
    assert put_res.json()["version"] == 5
    saved_prefs = yt_route_harness.state["doc"]["preferences"]
    assert saved_prefs["goal"] == "Book 5 advisory calls this month"
    assert saved_prefs["content_sources"]["youtube"]["videos"][0]["video_id"] == "AbCdEfGh123"
    assert saved_prefs["competitor_checks"]["https://rival-one.example"]["status"] == "first_check"

    # Remove clears content_sources.youtube
    rem = yt_route_harness.client.post(
        "/api/v1/seller-memory/sources/youtube",
        headers={"X-Test-Auth": "verified"},
        json={"remove": True, "expected_version": 5},
    )
    assert rem.status_code == 200
    assert rem.json()["version"] == 6
    assert rem.json()["youtube"] is None
    assert "youtube" not in yt_route_harness.state["doc"]["preferences"]["content_sources"]


def test_youtube_source_route_plain_errors(yt_route_harness: SimpleNamespace) -> None:
    bad = yt_route_harness.client.post(
        "/api/v1/seller-memory/sources/youtube",
        headers={"X-Test-Auth": "verified"},
        json={"url": "https://example.com/not-youtube", "expected_version": 3},
    )
    assert bad.status_code == 400
    assert bad.json()["detail"] == yt.ERR_INVALID_URL

    yt_route_harness.fetch_mock.side_effect = yt.YouTubeFeedError(yt.ERR_NO_FEED, status_code=502)
    no_feed = yt_route_harness.client.post(
        "/api/v1/seller-memory/sources/youtube",
        headers={"X-Test-Auth": "verified"},
        json={"url": "https://youtube.com/@northstar", "expected_version": 3},
    )
    assert no_feed.status_code == 502
    assert no_feed.json()["detail"] == yt.ERR_NO_FEED

    yt_route_harness.fetch_mock.side_effect = yt.YouTubeFeedError(yt.ERR_TIMEOUT, status_code=504)
    timeout = yt_route_harness.client.post(
        "/api/v1/seller-memory/sources/youtube",
        headers={"X-Test-Auth": "verified"},
        json={"url": "https://youtube.com/@northstar", "expected_version": 3},
    )
    assert timeout.status_code == 504
    assert timeout.json()["detail"] == yt.ERR_TIMEOUT
