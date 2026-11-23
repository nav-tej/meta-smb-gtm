"""Unit and route tests for pasted YouTube video links via public oEmbed."""

from __future__ import annotations

import json
from copy import deepcopy
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi import HTTPException, Request, Response
from fastapi.testclient import TestClient

from src.api import seller_memory as memory_api
from src.api.main import app
from src.config import get_settings
from src.services import scan_guard
from src.services import youtube_videos as yv
from src.services.accounts import AccountSession

VID_1 = "AbCdEfGh123"
VID_2 = "XyZ_987-654"
VID_3 = "MnOpQrSt456"


@pytest.mark.parametrize(
    "raw_url, expected_id",
    [
        (f"https://youtube.com/watch?v={VID_1}", VID_1),
        (f"https://www.youtube.com/watch?v={VID_1}&t=42s", VID_1),
        (f"https://m.youtube.com/watch?v={VID_1}", VID_1),
        (f"http://youtube.com/watch?v={VID_1}", VID_1),
        (f"youtube.com/watch?v={VID_1}", VID_1),
        (f"https://youtu.be/{VID_2}", VID_2),
        (f"https://www.youtu.be/{VID_2}?si=share123", VID_2),
        (f"youtu.be/{VID_2}", VID_2),
        (f"https://youtube.com/shorts/{VID_3}", VID_3),
        (f"https://www.youtube.com/shorts/{VID_3}?feature=share", VID_3),
        (f"https://m.youtube.com/shorts/{VID_3}", VID_3),
    ],
)
def test_parse_video_id_accepts_valid_links(raw_url: str, expected_id: str) -> None:
    assert yv.parse_video_id(raw_url) == expected_id


@pytest.mark.parametrize(
    "bad_url",
    [
        "",
        "   ",
        "not-a-link",
        "https://vimeo.com/123456789",
        "https://evil-youtube.com/watch?v=AbCdEfGh123",
        "javascript:alert(1)",
        "ftp://youtube.com/watch?v=AbCdEfGh123",
        "file:///etc/passwd",
        f"https://user:pass@youtube.com/watch?v={VID_1}",
        f"https://youtube.com:8443/watch?v={VID_1}",
        "https://youtube.com/@northstar",
        "https://youtube.com/channel/UC1234567890abcdefABCD12",
        "https://www.youtube.com/feeds/videos.xml?channel_id=UC1234567890abcdefABCD12",
        "https://youtube.com/watch?v=short",
        "https://youtube.com/watch?v=waytoolong12345",
        "https://youtube.com/watch?v=bad!char123",
        f"https://youtu.be/{VID_1}/extra",
        f"https://youtube.com/shorts/{VID_1}/extra",
        "https://youtube.com/watch",
    ],
)
def test_parse_video_id_refuses_invalid_links(bad_url: str) -> None:
    with pytest.raises(yv.YouTubeVideoError) as exc_info:
        yv.parse_video_id(bad_url)
    assert exc_info.value.user_message == yv.ERR_INVALID_LINK


def test_parse_oembed_payload_strips_html_caps_and_rebuilds_urls() -> None:
    payload = json.dumps(
        {
            "title": "<b>Q4 Advisory</b> " + ("T" * 200),
            "author_name": "<script>alert(1)</script>Northstar " + ("A" * 120),
            "author_url": "https://evil.example/channel",
            "provider_url": "https://evil.example/",
            "thumbnail_url": "https://evil.example/thumb.jpg",
            "html": "<iframe src='https://evil.example/embed'></iframe>",
            "type": "video",
        }
    ).encode()

    info = yv.parse_oembed_payload(payload, VID_1)
    assert info["video_id"] == VID_1
    assert len(info["title"]) <= yv.MAX_TITLE_CHARS
    assert "<b>" not in info["title"]
    assert info["title"].startswith("Q4 Advisory")
    assert len(info["author_name"]) <= yv.MAX_AUTHOR_CHARS
    assert "<script>" not in info["author_name"]
    assert info["url"] == f"https://www.youtube.com/watch?v={VID_1}"
    assert info["thumbnail_url"] == f"https://i.ytimg.com/vi/{VID_1}/hqdefault.jpg"
    assert "evil.example" not in json.dumps(info)
    assert set(info.keys()) == {"video_id", "title", "author_name", "url", "thumbnail_url"}


@pytest.mark.parametrize("raw_body", [b"", b"not json at all", b"[]", b'{"author_name": "Only"}'])
def test_parse_oembed_payload_rejects_bad_bodies(raw_body: bytes) -> None:
    with pytest.raises(yv.YouTubeVideoError) as exc_info:
        yv.parse_oembed_payload(raw_body, VID_1)
    assert exc_info.value.user_message == yv.ERR_UNAVAILABLE


@pytest.mark.asyncio
async def test_fetch_video_info_checks_robots_and_rebuilds_urls() -> None:
    scan_guard.reset()
    requested: list[str] = []
    oembed_url = yv.oembed_url_for_video(VID_1)

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        requested.append(url)
        if url.endswith("/robots.txt"):
            return httpx.Response(
                200,
                text="User-agent: *\nDisallow: /feeds/videos.xml\nAllow: /oembed\n",
            )
        if url == oembed_url:
            return httpx.Response(
                200,
                json={
                    "title": "How we scope retainers",
                    "author_name": "Northstar Advisory",
                    "thumbnail_url": "https://evil.example/fake.jpg",
                    "author_url": "javascript:alert(1)",
                },
            )
        return httpx.Response(404)

    async def fake_resolver(_host: str) -> list[str]:
        return ["93.184.216.34"]

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        info = await yv.fetch_video_info(VID_1, client=client, resolver=fake_resolver)

    assert any(u.endswith("/robots.txt") for u in requested)
    assert oembed_url in requested
    assert info["title"] == "How we scope retainers"
    assert info["author_name"] == "Northstar Advisory"
    assert info["url"] == f"https://www.youtube.com/watch?v={VID_1}"
    assert info["thumbnail_url"] == f"https://i.ytimg.com/vi/{VID_1}/hqdefault.jpg"


@pytest.mark.asyncio
async def test_fetch_video_info_robots_disallow_refuses_before_get() -> None:
    scan_guard.reset()
    requested: list[str] = []
    oembed_url = yv.oembed_url_for_video(VID_1)

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        requested.append(url)
        if url.endswith("/robots.txt"):
            return httpx.Response(200, text="User-agent: *\nDisallow: /oembed\n")
        return httpx.Response(200, json={"title": "Should never be fetched"})

    async def fake_resolver(_host: str) -> list[str]:
        return ["93.184.216.34"]

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(yv.YouTubeVideoError) as exc_info:
            await yv.fetch_video_info(VID_1, client=client, resolver=fake_resolver)
        assert exc_info.value.user_message == yv.ERR_UNAVAILABLE

    assert oembed_url not in requested


@pytest.mark.asyncio
@pytest.mark.parametrize("status_code", [401, 403, 404])
async def test_fetch_video_info_maps_401_403_404_to_plain_error(status_code: int) -> None:
    scan_guard.reset()

    def handler(request: httpx.Request) -> httpx.Response:
        if str(request.url).endswith("/robots.txt"):
            return httpx.Response(200, text="User-agent: *\nAllow: /\n")
        return httpx.Response(status_code, text="Not found")

    async def fake_resolver(_host: str) -> list[str]:
        return ["93.184.216.34"]

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(yv.YouTubeVideoError) as exc_info:
            await yv.fetch_video_info(VID_1, client=client, resolver=fake_resolver)
        assert exc_info.value.user_message == yv.ERR_UNAVAILABLE


@pytest.mark.asyncio
async def test_fetch_video_info_maps_timeout_to_plain_error() -> None:
    scan_guard.reset()

    def handler(request: httpx.Request) -> httpx.Response:
        if str(request.url).endswith("/robots.txt"):
            return httpx.Response(200, text="User-agent: *\nAllow: /\n")
        raise httpx.ReadTimeout("timed out", request=request)

    async def fake_resolver(_host: str) -> list[str]:
        return ["93.184.216.34"]

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(yv.YouTubeVideoError) as exc_info:
            await yv.fetch_video_info(VID_1, client=client, resolver=fake_resolver)
        assert exc_info.value.user_message == yv.ERR_TIMEOUT
        assert exc_info.value.status_code == 504


# ---------------------------------------------------------------------------
# Route tests: POST /api/v1/seller-memory/sources/youtube & GET /seller-memory
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
                "competitors": [{"name": "Rival One", "url": "https://rival-one.example"}],
            },
            "preferences": {
                "goal": "Grow inquiries",
                "custom_flag": "keep-me",
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

    async def fake_fetch_video_info(video_id: str) -> dict[str, str]:
        titles = {
            VID_1: ("Q4 Pipeline Audit", "Northstar Advisory"),
            VID_2: ("Retainer Pricing Breakdown", "Northstar Advisory"),
            VID_3: ("Discovery Call Checklist", "Northstar Advisory"),
        }
        title, author = titles.get(video_id, (f"Video {video_id}", "Northstar Advisory"))
        url, thumb = yv.build_video_urls(video_id)
        return {
            "video_id": video_id,
            "title": title,
            "author_name": author,
            "url": url,
            "thumbnail_url": thumb,
        }

    fetch_mock = AsyncMock(side_effect=fake_fetch_video_info)
    monkeypatch.setattr(memory_api, "resolve_account", fake_resolve)
    monkeypatch.setattr(memory_api, "load_workspace", fake_load)
    monkeypatch.setattr(memory_api, "save_workspace", fake_save)
    monkeypatch.setattr(memory_api, "fetch_video_info", fetch_mock)
    return SimpleNamespace(client=TestClient(app), state=state, fetch_mock=fetch_mock)


def test_youtube_route_auth_401_403_409_429_before_fetch(
    yt_route_harness: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    # 401 signed out
    r401 = yt_route_harness.client.post(
        "/api/v1/seller-memory/sources/youtube",
        json={"urls": [f"https://youtu.be/{VID_1}"], "expected_version": 3},
    )
    assert r401.status_code == 401
    yt_route_harness.fetch_mock.assert_not_awaited()

    # 403 unverified
    r403 = yt_route_harness.client.post(
        "/api/v1/seller-memory/sources/youtube",
        headers={"X-Test-Auth": "unverified"},
        json={"urls": [f"https://youtu.be/{VID_1}"], "expected_version": 3},
    )
    assert r403.status_code == 403
    yt_route_harness.fetch_mock.assert_not_awaited()

    # 409 stale expected_version (before fetching)
    r409 = yt_route_harness.client.post(
        "/api/v1/seller-memory/sources/youtube",
        headers={"X-Test-Auth": "verified"},
        json={"urls": [f"https://youtu.be/{VID_1}"], "expected_version": 1},
    )
    assert r409.status_code == 409
    yt_route_harness.fetch_mock.assert_not_awaited()

    # 429 rate limit with Retry-After before any fetch (2 new videos > limit of 1)
    monkeypatch.setenv("SCANS_PER_VISITOR_PER_10_MIN", "1")
    get_settings.cache_clear()
    r429 = yt_route_harness.client.post(
        "/api/v1/seller-memory/sources/youtube",
        headers={"X-Test-Auth": "verified"},
        json={
            "urls": [f"https://youtu.be/{VID_1}", f"https://youtu.be/{VID_2}"],
            "expected_version": 3,
        },
    )
    assert r429.status_code == 429
    assert int(r429.headers["Retry-After"]) >= 1
    yt_route_harness.fetch_mock.assert_not_awaited()
    get_settings.cache_clear()


def test_youtube_route_save_keeps_existing_ids_without_refetch_preserves_extras_and_removes(
    yt_route_harness: SimpleNamespace,
) -> None:
    # 1. Save initial video
    first = yt_route_harness.client.post(
        "/api/v1/seller-memory/sources/youtube",
        headers={"X-Test-Auth": "verified"},
        json={"urls": [f"https://www.youtube.com/watch?v={VID_1}"], "expected_version": 3},
    )
    assert first.status_code == 200
    assert "no-store" in first.headers["cache-control"]
    assert first.json()["version"] == 4
    yt_route_harness.fetch_mock.assert_awaited_once_with(VID_1)
    stored_videos = yt_route_harness.state["doc"]["preferences"]["content_sources"]["youtube"][
        "videos"
    ]
    assert len(stored_videos) == 1
    assert set(stored_videos[0].keys()) == {"video_id", "title", "author_name", "added_at"}

    # 2. Save list containing VID_1 (already saved) + VID_2 (new) -> only VID_2 is fetched
    yt_route_harness.fetch_mock.reset_mock()
    second = yt_route_harness.client.post(
        "/api/v1/seller-memory/sources/youtube",
        headers={"X-Test-Auth": "verified"},
        json={
            "urls": [f"https://youtu.be/{VID_1}", f"https://youtube.com/shorts/{VID_2}"],
            "expected_version": 4,
        },
    )
    assert second.status_code == 200
    assert second.json()["version"] == 5
    yt_route_harness.fetch_mock.assert_awaited_once_with(VID_2)
    assert [v["video_id"] for v in second.json()["youtube"]["videos"]] == [VID_1, VID_2]

    # 3. GET /api/v1/seller-memory returns content_sources
    got = yt_route_harness.client.get("/api/v1/seller-memory", headers={"X-Test-Auth": "verified"})
    assert got.status_code == 200
    assert [v["video_id"] for v in got.json()["content_sources"]["youtube"]["videos"]] == [
        VID_1,
        VID_2,
    ]

    # 4. Normal PUT /api/v1/seller-memory preserves content_sources, competitor_checks & custom keys
    put_res = yt_route_harness.client.put(
        "/api/v1/seller-memory",
        headers={"X-Test-Auth": "verified", "X-Muse-Owner": "yt-owner-1"},
        json={
            "expected_version": 5,
            "expected_owner": "yt-owner-1",
            "preferences": {"goal": "Book 5 advisory calls this month"},
        },
    )
    assert put_res.status_code == 200
    assert put_res.json()["version"] == 6
    saved_prefs = yt_route_harness.state["doc"]["preferences"]
    assert saved_prefs["goal"] == "Book 5 advisory calls this month"
    assert saved_prefs["custom_flag"] == "keep-me"
    assert [v["video_id"] for v in saved_prefs["content_sources"]["youtube"]["videos"]] == [
        VID_1,
        VID_2,
    ]
    assert saved_prefs["competitor_checks"]["https://rival-one.example"]["status"] == "first_check"

    # 5. Remove clears content_sources.youtube
    rem = yt_route_harness.client.post(
        "/api/v1/seller-memory/sources/youtube",
        headers={"X-Test-Auth": "verified"},
        json={"remove": True, "expected_version": 6},
    )
    assert rem.status_code == 200
    assert rem.json()["version"] == 7
    assert rem.json()["youtube"] is None
    assert "youtube" not in yt_route_harness.state["doc"]["preferences"]["content_sources"]


def test_youtube_route_plain_errors_and_five_link_cap(
    yt_route_harness: SimpleNamespace,
) -> None:
    bad = yt_route_harness.client.post(
        "/api/v1/seller-memory/sources/youtube",
        headers={"X-Test-Auth": "verified"},
        json={"urls": ["https://youtube.com/@northstar"], "expected_version": 3},
    )
    assert bad.status_code == 400
    assert bad.json()["detail"] == yv.ERR_INVALID_LINK

    too_many = yt_route_harness.client.post(
        "/api/v1/seller-memory/sources/youtube",
        headers={"X-Test-Auth": "verified"},
        json={
            "urls": [f"https://youtu.be/Vid0000000{i}" for i in range(6)],
            "expected_version": 3,
        },
    )
    assert too_many.status_code == 400
    assert too_many.json()["detail"] == yv.ERR_TOO_MANY

    yt_route_harness.fetch_mock.side_effect = yv.YouTubeVideoError(
        yv.ERR_UNAVAILABLE, status_code=502
    )
    unavail = yt_route_harness.client.post(
        "/api/v1/seller-memory/sources/youtube",
        headers={"X-Test-Auth": "verified"},
        json={"urls": [f"https://youtu.be/{VID_1}"], "expected_version": 3},
    )
    assert unavail.status_code == 502
    assert unavail.json()["detail"] == yv.ERR_UNAVAILABLE
