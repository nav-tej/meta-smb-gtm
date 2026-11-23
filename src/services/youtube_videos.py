"""Public YouTube video metadata reader via oEmbed (no API key, robots.txt-compliant).

Accepts up to 5 pasted YouTube video links (`youtube.com/watch?v=ID`, `youtu.be/ID`,
`youtube.com/shorts/ID`), checks `RobotsPolicy` for `/oembed`, fetches each new video's
title and author name through `_fetch_bytes_guarded` (SSRF, redirects re-checked, 64 KB
cap) inside `scan_guard.crawl`, and rebuilds watch and thumbnail URLs strictly from the
validated 11-character video ID.
"""

from __future__ import annotations

import html
import json
import re
from urllib.parse import parse_qs, quote, urlsplit

import httpx

from src.models.intel import SitemapEntry
from src.services import scan_guard
from src.utils.sitemap import (
    DEFAULT_REQUEST_TIMEOUT,
    ResolverFn,
    SitemapError,
    _fetch_bytes_guarded,
    fetch_robots_policy,
)

YOUTUBE_WATCH_HOSTS = frozenset({"youtube.com", "www.youtube.com", "m.youtube.com"})
YOUTUBE_SHORT_HOSTS = frozenset({"youtu.be", "www.youtu.be"})
VIDEO_ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")
_HTML_TAG_RE = re.compile(r"<[^>]+>")
_WHITESPACE_RE = re.compile(r"\s+")

MAX_VIDEOS = 5
MAX_TITLE_CHARS = 140
MAX_AUTHOR_CHARS = 80
MAX_OEMBED_BYTES = 64 * 1024

ERR_INVALID_LINK = "That isn't a YouTube video link."
ERR_UNAVAILABLE = "YouTube didn't share this video (it may be private or removed)."
ERR_TIMEOUT = "YouTube took too long to answer. Try again shortly."
ERR_TOO_MANY = "Paste up to 5 YouTube video links."


class YouTubeVideoError(Exception):
    """Plain, seller-safe error raised when reading a pasted YouTube video link fails."""

    def __init__(self, user_message: str, *, status_code: int = 400) -> None:
        super().__init__(user_message)
        self.user_message = user_message
        self.status_code = status_code


def parse_video_id(raw: str) -> str:
    """Validate a pasted YouTube video URL and return its 11-character video ID.

    Accepts `youtube.com/watch?v=ID`, `youtu.be/ID`, and `youtube.com/shorts/ID`
    (with or without `www.`/`m.`), `http` or `https` only, with no userinfo or port.
    """
    cleaned = (raw or "").strip()
    if not cleaned:
        raise YouTubeVideoError(ERR_INVALID_LINK, status_code=400)

    if re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*:", cleaned) and not cleaned.lower().startswith(
        ("http://", "https://")
    ):
        raise YouTubeVideoError(ERR_INVALID_LINK, status_code=400)

    if "://" not in cleaned:
        cleaned = f"https://{cleaned}"

    parsed = urlsplit(cleaned)
    scheme = (parsed.scheme or "").lower()
    if scheme not in {"http", "https"}:
        raise YouTubeVideoError(ERR_INVALID_LINK, status_code=400)

    try:
        port = parsed.port
    except ValueError as err:
        raise YouTubeVideoError(ERR_INVALID_LINK, status_code=400) from err
    if parsed.username or parsed.password or port is not None:
        raise YouTubeVideoError(ERR_INVALID_LINK, status_code=400)

    host = (parsed.hostname or "").lower().rstrip(".")
    segments = [seg for seg in parsed.path.split("/") if seg]

    if host in YOUTUBE_SHORT_HOSTS:
        if len(segments) == 1 and VIDEO_ID_RE.match(segments[0]):
            return segments[0]
        raise YouTubeVideoError(ERR_INVALID_LINK, status_code=400)

    if host in YOUTUBE_WATCH_HOSTS:
        if len(segments) == 1 and segments[0].lower() == "watch":
            qs = parse_qs(parsed.query, keep_blank_values=False)
            values = qs.get("v") or []
            if len(values) == 1 and VIDEO_ID_RE.match(values[0]):
                return values[0]
            raise YouTubeVideoError(ERR_INVALID_LINK, status_code=400)
        if len(segments) == 2 and segments[0].lower() == "shorts":
            if VIDEO_ID_RE.match(segments[1]):
                return segments[1]
            raise YouTubeVideoError(ERR_INVALID_LINK, status_code=400)

    raise YouTubeVideoError(ERR_INVALID_LINK, status_code=400)


def build_video_urls(video_id: str) -> tuple[str, str]:
    """Rebuild watch and thumbnail URLs strictly from a validated 11-char video ID."""
    if not VIDEO_ID_RE.match(video_id):
        raise ValueError(f"Invalid YouTube video_id: {video_id!r}")
    return (
        f"https://www.youtube.com/watch?v={video_id}",
        f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg",
    )


def oembed_url_for_video(video_id: str) -> str:
    """Build the canonical YouTube oEmbed endpoint URL for a validated video ID."""
    watch_url, _thumb = build_video_urls(video_id)
    return f"https://www.youtube.com/oembed?url={quote(watch_url, safe='')}&format=json"


def _clean_plain_text(raw: object, max_chars: int) -> str:
    if not isinstance(raw, str) or not raw.strip():
        return ""
    unescaped = html.unescape(raw)
    stripped = _HTML_TAG_RE.sub(" ", unescaped)
    collapsed = _WHITESPACE_RE.sub(" ", stripped).strip()
    return collapsed[:max_chars].strip()


def parse_oembed_payload(raw_bytes: bytes, video_id: str) -> dict[str, str]:
    """Parse YouTube oEmbed JSON, keeping only plain-text title/author and rebuilt URLs."""
    if not VIDEO_ID_RE.match(video_id):
        raise YouTubeVideoError(ERR_INVALID_LINK, status_code=400)
    if not raw_bytes or not raw_bytes.strip():
        raise YouTubeVideoError(ERR_UNAVAILABLE, status_code=502)

    try:
        data = json.loads(raw_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as err:
        raise YouTubeVideoError(ERR_UNAVAILABLE, status_code=502) from err

    if not isinstance(data, dict):
        raise YouTubeVideoError(ERR_UNAVAILABLE, status_code=502)

    title = _clean_plain_text(data.get("title"), MAX_TITLE_CHARS)
    if not title:
        raise YouTubeVideoError(ERR_UNAVAILABLE, status_code=502)
    author_name = _clean_plain_text(data.get("author_name"), MAX_AUTHOR_CHARS)

    watch_url, thumbnail_url = build_video_urls(video_id)
    return {
        "video_id": video_id,
        "title": title,
        "author_name": author_name,
        "url": watch_url,
        "thumbnail_url": thumbnail_url,
    }


def _is_timeout_error(err: Exception) -> bool:
    if isinstance(err, httpx.TimeoutException):
        return True
    cause = getattr(err, "__cause__", None)
    if isinstance(cause, httpx.TimeoutException):
        return True
    text = str(err).lower()
    return any(tok in text for tok in ("timeout", "timed out", "readtimeout", "connecttimeout"))


async def fetch_video_info(
    video_id: str,
    *,
    client: httpx.AsyncClient | None = None,
    resolver: ResolverFn | None = None,
) -> dict[str, str]:
    """Fetch a video's title and author name from YouTube's public oEmbed endpoint."""
    if not VIDEO_ID_RE.match(video_id):
        raise YouTubeVideoError(ERR_INVALID_LINK, status_code=400)

    oembed_url = oembed_url_for_video(video_id)
    watch_url, thumbnail_url = build_video_urls(video_id)

    owns_client = client is None
    active_client = client or httpx.AsyncClient(timeout=DEFAULT_REQUEST_TIMEOUT)
    try:

        async def _fetch_once() -> tuple[list[SitemapEntry], list[str]]:
            policy = await fetch_robots_policy(
                "https://www.youtube.com", active_client, resolver=resolver
            )
            if not policy.is_allowed(oembed_url):
                raise YouTubeVideoError(ERR_UNAVAILABLE, status_code=502)

            try:
                status, body, _final_url = await _fetch_bytes_guarded(
                    oembed_url,
                    active_client,
                    max_bytes=MAX_OEMBED_BYTES,
                    truncate_on_limit=False,
                    resolver=resolver,
                )
            except SitemapError as err:
                if _is_timeout_error(err):
                    raise YouTubeVideoError(ERR_TIMEOUT, status_code=504) from err
                raise YouTubeVideoError(ERR_UNAVAILABLE, status_code=502) from err

            if status in {401, 403, 404} or status != 200 or not body:
                raise YouTubeVideoError(ERR_UNAVAILABLE, status_code=502)

            parsed = parse_oembed_payload(body, video_id)
            return [SitemapEntry(loc=watch_url, title=parsed["title"])], [parsed["author_name"]]

        entries, meta = await scan_guard.crawl(oembed_url, 1, _fetch_once)
        title = _clean_plain_text(entries[0].title if entries else "", MAX_TITLE_CHARS)
        author_name = _clean_plain_text(meta[0] if meta else "", MAX_AUTHOR_CHARS)
        if not title:
            raise YouTubeVideoError(ERR_UNAVAILABLE, status_code=502)
        return {
            "video_id": video_id,
            "title": title,
            "author_name": author_name,
            "url": watch_url,
            "thumbnail_url": thumbnail_url,
        }
    finally:
        if owns_client:
            await active_client.aclose()
