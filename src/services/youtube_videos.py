"""Seller-pasted YouTube video reader via YouTube's public oEmbed endpoint.

Never fetches `/feeds/videos.xml`, channel pages, or `/youtubei/`.
Validates each pasted video link, checks `RobotsPolicy` for the oEmbed URL first,
fetches the oEmbed JSON through the SSRF-guarded crawler client (`_fetch_bytes_guarded`,
64 KB cap) inside `scan_guard.crawl`, keeps only plain-text `title` (140 chars) and
`author_name` (80 chars), and rebuilds watch and thumbnail URLs strictly from the
validated 11-character video ID.
"""

from __future__ import annotations

import html
import json
import re
from typing import Any
from urllib.parse import parse_qs, urlsplit

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

YOUTUBE_LONG_HOSTS = frozenset({"youtube.com", "www.youtube.com", "m.youtube.com"})
YOUTUBE_SHORT_HOSTS = frozenset({"youtu.be", "www.youtu.be", "m.youtu.be"})
YOUTUBE_ALL_HOSTS = YOUTUBE_LONG_HOSTS | YOUTUBE_SHORT_HOSTS

VIDEO_ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")
_SCHEME_PREFIX_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.-]*:")
_SCRIPT_STYLE_RE = re.compile(r"<(script|style)\b[^>]*>.*?</\1>", re.IGNORECASE | re.DOTALL)
_HTML_TAG_RE = re.compile(r"<[^>]+>")
_CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_WHITESPACE_RE = re.compile(r"\s+")

MAX_VIDEOS = 5
MAX_OEMBED_BYTES = 64 * 1024
MAX_TITLE_CHARS = 140
MAX_AUTHOR_CHARS = 80

ERR_INVALID_LINK = "That isn't a YouTube video link."
ERR_NOT_SHARED = "YouTube didn't share this video (it may be private or removed)."
ERR_ROBOTS_DISALLOWED = "YouTube's robots.txt blocks reading this video link."
ERR_UNAVAILABLE = "YouTube didn't share details for this video right now."
ERR_TIMEOUT = "YouTube took too long to answer. Try again shortly."


class YouTubeVideoError(ValueError):
    """Plain, seller-safe error raised when validating or reading a YouTube video link."""

    def __init__(self, user_message: str, *, status_code: int = 400) -> None:
        super().__init__(user_message)
        self.user_message = user_message
        self.status_code = status_code


def watch_url_for_video(video_id: str) -> str:
    """Rebuild the canonical YouTube watch URL strictly from a validated 11-char video ID."""
    if not isinstance(video_id, str) or not VIDEO_ID_RE.fullmatch(video_id):
        raise YouTubeVideoError(ERR_INVALID_LINK, status_code=400)
    return f"https://www.youtube.com/watch?v={video_id}"


def thumbnail_url_for_video(video_id: str) -> str:
    """Rebuild the canonical YouTube thumbnail URL strictly from a validated 11-char video ID."""
    if not isinstance(video_id, str) or not VIDEO_ID_RE.fullmatch(video_id):
        raise YouTubeVideoError(ERR_INVALID_LINK, status_code=400)
    return f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg"


def oembed_url_for_video(video_id: str) -> str:
    """Build the YouTube oEmbed endpoint URL for a validated 11-char video ID."""
    watch_url = watch_url_for_video(video_id)
    return f"https://www.youtube.com/oembed?url={watch_url}&format=json"


def parse_video_id(raw: str) -> str:
    """Parse and validate a YouTube video link and return its 11-character video ID.

    Accepts `youtube.com/watch?v=ID`, `youtu.be/ID`, and `youtube.com/shorts/ID`
    (with or without `www.`/`m.`), `http` or `https` only, with no userinfo or port.
    """
    if not isinstance(raw, str):
        raise YouTubeVideoError(ERR_INVALID_LINK, status_code=400)
    cleaned = raw.strip()
    if not cleaned or any(ch in cleaned for ch in ("\r", "\n", "\t", "\x00")):
        raise YouTubeVideoError(ERR_INVALID_LINK, status_code=400)
    if cleaned.startswith("/"):
        raise YouTubeVideoError(ERR_INVALID_LINK, status_code=400)

    if _SCHEME_PREFIX_RE.match(cleaned) and not cleaned.lower().startswith(
        ("http://", "https://")
    ):
        raise YouTubeVideoError(ERR_INVALID_LINK, status_code=400)

    if "://" not in cleaned:
        cleaned = f"https://{cleaned}"

    try:
        parsed = urlsplit(cleaned)
    except ValueError as err:
        raise YouTubeVideoError(ERR_INVALID_LINK, status_code=400) from err

    scheme = (parsed.scheme or "").lower()
    if scheme not in {"http", "https"}:
        raise YouTubeVideoError(ERR_INVALID_LINK, status_code=400)

    try:
        port = parsed.port
    except ValueError as err:
        raise YouTubeVideoError(ERR_INVALID_LINK, status_code=400) from err

    netloc = parsed.netloc or ""
    if (
        parsed.username is not None
        or parsed.password is not None
        or port is not None
        or "@" in netloc
        or ":" in netloc
    ):
        raise YouTubeVideoError(ERR_INVALID_LINK, status_code=400)

    host = (parsed.hostname or "").lower().rstrip(".")
    if not host or "//" in (parsed.path or ""):
        raise YouTubeVideoError(ERR_INVALID_LINK, status_code=400)

    segments = [seg for seg in (parsed.path or "").split("/") if seg]
    video_id = ""

    if host in YOUTUBE_LONG_HOSTS:
        if segments == ["watch"]:
            qs = parse_qs(parsed.query, keep_blank_values=True)
            v_values = qs.get("v")
            if not v_values or len(v_values) != 1:
                raise YouTubeVideoError(ERR_INVALID_LINK, status_code=400)
            video_id = v_values[0]
        elif len(segments) == 2 and segments[0] == "shorts":
            video_id = segments[1]
        else:
            raise YouTubeVideoError(ERR_INVALID_LINK, status_code=400)
    elif host in YOUTUBE_SHORT_HOSTS:
        if len(segments) != 1:
            raise YouTubeVideoError(ERR_INVALID_LINK, status_code=400)
        video_id = segments[0]
    else:
        raise YouTubeVideoError(ERR_INVALID_LINK, status_code=400)

    if not VIDEO_ID_RE.fullmatch(video_id):
        raise YouTubeVideoError(ERR_INVALID_LINK, status_code=400)

    return video_id


def _clean_plain_text(raw: Any, max_chars: int) -> str:
    if not isinstance(raw, str):
        return ""
    stripped = _SCRIPT_STYLE_RE.sub(" ", raw)
    stripped = _HTML_TAG_RE.sub(" ", stripped)
    unescaped = html.unescape(stripped)
    unescaped = _SCRIPT_STYLE_RE.sub(" ", unescaped)
    unescaped = _HTML_TAG_RE.sub(" ", unescaped)
    unescaped = _CONTROL_RE.sub(" ", unescaped)
    collapsed = _WHITESPACE_RE.sub(" ", unescaped).strip()
    return collapsed[:max_chars].strip()


def parse_oembed_payload(raw_bytes: bytes) -> tuple[str, str]:
    """Parse oEmbed JSON bytes and return plain-text `(title, author_name)` only."""
    if not raw_bytes:
        raise YouTubeVideoError(ERR_UNAVAILABLE, status_code=502)
    try:
        payload = json.loads(raw_bytes.decode("utf-8", errors="strict"))
    except (UnicodeDecodeError, json.JSONDecodeError) as err:
        raise YouTubeVideoError(ERR_UNAVAILABLE, status_code=502) from err

    if not isinstance(payload, dict):
        raise YouTubeVideoError(ERR_UNAVAILABLE, status_code=502)

    title = _clean_plain_text(payload.get("title"), MAX_TITLE_CHARS)
    if not title:
        raise YouTubeVideoError(ERR_UNAVAILABLE, status_code=502)
    author_name = _clean_plain_text(payload.get("author_name"), MAX_AUTHOR_CHARS)
    return title, author_name


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
    """Fetch a YouTube video's title and channel name via oEmbed after checking robots.txt.

    Rebuilds `watch_url` and `thumbnail_url` strictly from the validated 11-char ID;
    never stores or returns any URL from the oEmbed response.
    """
    if not isinstance(video_id, str):
        raise YouTubeVideoError(ERR_INVALID_LINK, status_code=400)
    candidate = video_id.strip()
    valid_id = candidate if VIDEO_ID_RE.fullmatch(candidate) else parse_video_id(candidate)

    watch_url = watch_url_for_video(valid_id)
    thumbnail_url = thumbnail_url_for_video(valid_id)
    oembed_url = oembed_url_for_video(valid_id)

    owns_client = client is None
    active_client = client or httpx.AsyncClient(timeout=DEFAULT_REQUEST_TIMEOUT)
    try:

        async def _fetch_once() -> tuple[list[SitemapEntry], list[str]]:
            policy = await fetch_robots_policy(
                "https://www.youtube.com",
                active_client,
                resolver=resolver,
            )
            if not policy.is_allowed(oembed_url):
                raise YouTubeVideoError(ERR_ROBOTS_DISALLOWED, status_code=422)

            try:
                status, body, final_url = await _fetch_bytes_guarded(
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

            if status in {401, 403, 404}:
                raise YouTubeVideoError(ERR_NOT_SHARED, status_code=422)
            if status != 200 or not body:
                raise YouTubeVideoError(ERR_UNAVAILABLE, status_code=502)

            final_host = (urlsplit(final_url).hostname or "").lower().rstrip(".")
            if final_host not in YOUTUBE_LONG_HOSTS or not policy.is_allowed(final_url):
                raise YouTubeVideoError(ERR_ROBOTS_DISALLOWED, status_code=422)

            title, author_name = parse_oembed_payload(body)
            return [SitemapEntry(url=watch_url, title=title)], [author_name]

        entries, sitemaps = await scan_guard.crawl(oembed_url, 1, _fetch_once)
        title = (entries[0].title if entries else "") or ""
        author_name = (sitemaps[0] if sitemaps else "") or ""
        if not title:
            raise YouTubeVideoError(ERR_UNAVAILABLE, status_code=502)

        return {
            "video_id": valid_id,
            "title": title,
            "author_name": author_name,
            "watch_url": watch_url,
            "thumbnail_url": thumbnail_url,
        }
    finally:
        if owns_client:
            await active_client.aclose()


def extract_youtube_social_handle(onboarding: Any) -> str:
    """Return a display-safe YouTube handle or channel label from `onboarding.socials`, if any.

    Never fetches the channel.
    """
    if not isinstance(onboarding, dict):
        return ""
    socials = onboarding.get("socials")
    if not isinstance(socials, list):
        return ""
    for item in socials:
        if not isinstance(item, dict):
            continue
        if item.get("confirmed") is False:
            continue
        platform = str(item.get("platform") or "").strip().lower()
        raw_url = str(item.get("url") or "").strip()
        handle = str(item.get("handle") or "").strip()
        is_yt = platform == "youtube" or "youtube.com" in raw_url.lower()
        if not is_yt:
            continue
        if handle:
            cleaned = _clean_plain_text(handle, 80)
            if cleaned:
                return cleaned if cleaned.startswith("@") else f"@{cleaned}"
        if raw_url:
            try:
                parsed = urlsplit(raw_url if "://" in raw_url else f"https://{raw_url}")
                segs = [s for s in (parsed.path or "").split("/") if s]
                if segs:
                    first = _clean_plain_text(segs[0], 80)
                    if first:
                        return first
            except ValueError:
                continue
    return ""
