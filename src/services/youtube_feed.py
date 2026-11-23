"""Public YouTube channel Atom/RSS feed reader (no YouTube Data API, no API key).

Accepts a channel URL (`youtube.com/@handle`, `/channel/UC...`, `/c/...`, `/user/...`),
discovers the public Atom feed URL if needed through the SSRF-guarded crawler client,
`RobotsPolicy`, and `scan_guard`, parses the XML exclusively with `defusedxml`, and
rebuilds every video watch and thumbnail URL strictly from the validated 11-character
video ID.
"""

from __future__ import annotations

import html
import re
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlsplit
from xml.etree import ElementTree as StdET

import httpx
from defusedxml import DefusedXmlException
from defusedxml import ElementTree as SafeET

from src.models.intel import SitemapEntry
from src.services import scan_guard
from src.utils.sitemap import (
    _ATTR_RE,
    DEFAULT_REQUEST_TIMEOUT,
    MAX_SITEMAP_BYTES,
    ResolverFn,
    SitemapError,
    _fetch_bytes_guarded,
    fetch_robots_policy,
)

YOUTUBE_HOSTS = frozenset({"youtube.com", "www.youtube.com", "m.youtube.com"})
CHANNEL_ID_RE = re.compile(r"^UC[A-Za-z0-9_-]{22}$")
FEED_URL_RE = re.compile(
    r"^https://www\.youtube\.com/feeds/videos\.xml\?channel_id=(UC[A-Za-z0-9_-]{22})$"
)
VIDEO_ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")
_HANDLE_RE = re.compile(r"^@[A-Za-z0-9._-]{1,100}$")
_SLUG_RE = re.compile(r"^[A-Za-z0-9._%-]{1,100}$")
_LINK_TAG_RE = re.compile(r"<link\s+([^>]+)>", re.IGNORECASE)
_HTML_TAG_RE = re.compile(r"<[^>]+>")
_WHITESPACE_RE = re.compile(r"\s+")

MAX_VIDEOS = 10
MAX_TITLE_CHARS = 140
MAX_DESCRIPTION_CHARS = 300

ERR_INVALID_URL = "That isn't a YouTube channel address."
ERR_NO_FEED = "YouTube didn't share this channel's video list."
ERR_TIMEOUT = "YouTube took too long to answer. Try again shortly."

_ATOM_NS = "{http://www.w3.org/2005/Atom}"
_YT_NS = "{http://www.youtube.com/xml/schemas/2015}"
_MEDIA_NS = "{http://search.yahoo.com/mrss/}"


class YouTubeFeedError(Exception):
    """Plain, seller-safe error raised when reading a YouTube channel feed fails."""

    def __init__(self, user_message: str, *, status_code: int = 400) -> None:
        super().__init__(user_message)
        self.user_message = user_message
        self.status_code = status_code


def parse_youtube_channel_url(raw_url: str) -> tuple[str, str | None]:
    """Validate a YouTube channel URL and return `(canonical_channel_url, direct_feed_url)`.

    `direct_feed_url` is populated only for `/channel/UC...` URLs; handle, `/c/`, and
    `/user/` URLs return `None` and require one channel-page GET to discover the feed URL.
    """
    cleaned = (raw_url or "").strip()
    if not cleaned:
        raise YouTubeFeedError(ERR_INVALID_URL, status_code=400)

    if re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*:", cleaned) and not cleaned.lower().startswith(
        ("http://", "https://")
    ):
        raise YouTubeFeedError(ERR_INVALID_URL, status_code=400)

    if "://" not in cleaned:
        cleaned = f"https://{cleaned}"

    parsed = urlsplit(cleaned)
    scheme = (parsed.scheme or "").lower()
    if scheme not in {"http", "https"}:
        raise YouTubeFeedError(ERR_INVALID_URL, status_code=400)

    try:
        port = parsed.port
    except ValueError as err:
        raise YouTubeFeedError(ERR_INVALID_URL, status_code=400) from err
    if parsed.username or parsed.password or port is not None:
        raise YouTubeFeedError(ERR_INVALID_URL, status_code=400)

    host = (parsed.hostname or "").lower().rstrip(".")
    if host not in YOUTUBE_HOSTS:
        raise YouTubeFeedError(ERR_INVALID_URL, status_code=400)

    segments = [seg for seg in parsed.path.split("/") if seg]
    if not segments:
        raise YouTubeFeedError(ERR_INVALID_URL, status_code=400)

    first = segments[0]
    first_lower = first.lower()

    if first.startswith("@"):
        if not _HANDLE_RE.match(first):
            raise YouTubeFeedError(ERR_INVALID_URL, status_code=400)
        return f"https://www.youtube.com/{first}", None

    if first_lower == "channel":
        if len(segments) < 2 or not CHANNEL_ID_RE.match(segments[1]):
            raise YouTubeFeedError(ERR_INVALID_URL, status_code=400)
        channel_id = segments[1]
        return (
            f"https://www.youtube.com/channel/{channel_id}",
            f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}",
        )

    if first_lower in {"c", "user"}:
        if len(segments) < 2 or not _SLUG_RE.match(segments[1]):
            raise YouTubeFeedError(ERR_INVALID_URL, status_code=400)
        return f"https://www.youtube.com/{first_lower}/{segments[1]}", None

    raise YouTubeFeedError(ERR_INVALID_URL, status_code=400)


def extract_youtube_social_url(onboarding: Any) -> str:
    """Return a canonical YouTube channel URL from `onboarding.socials`, or empty string."""
    if not isinstance(onboarding, dict):
        return ""
    socials = onboarding.get("socials")
    if not isinstance(socials, list):
        return ""
    for item in socials:
        if not isinstance(item, dict):
            continue
        if str(item.get("platform") or "").strip().lower() != "youtube":
            continue
        for candidate in (
            str(item.get("url") or "").strip(),
            f"https://youtube.com/@{str(item.get('handle') or '').strip().lstrip('@')}"
            if str(item.get("handle") or "").strip()
            else "",
        ):
            if not candidate:
                continue
            try:
                canonical, _feed = parse_youtube_channel_url(candidate)
                return canonical
            except YouTubeFeedError:
                continue
    return ""


def discover_feed_url_from_html(html_text: str) -> str | None:
    """Extract and strictly validate YouTube's RSS/Atom feed `<link>` from channel HTML."""
    if not html_text:
        return None
    for match in _LINK_TAG_RE.finditer(html_text):
        attrs: dict[str, str] = {}
        for attr_match in _ATTR_RE.finditer(match.group(1)):
            key = attr_match.group(1).lower()
            val = attr_match.group(2) or attr_match.group(3) or attr_match.group(4) or ""
            attrs[key] = html.unescape(val).strip()
        rel_tokens = {tok.lower() for tok in attrs.get("rel", "").split() if tok}
        if "alternate" not in rel_tokens:
            continue
        if attrs.get("type", "").lower() != "application/rss+xml":
            continue
        href = attrs.get("href", "")
        feed_match = FEED_URL_RE.match(href)
        if feed_match:
            return f"https://www.youtube.com/feeds/videos.xml?channel_id={feed_match.group(1)}"
    return None


def build_video_urls(video_id: str) -> tuple[str, str]:
    """Rebuild watch and thumbnail URLs strictly from a validated 11-char video ID."""
    if not VIDEO_ID_RE.match(video_id):
        raise ValueError(f"Invalid YouTube video_id: {video_id!r}")
    return (
        f"https://www.youtube.com/watch?v={video_id}",
        f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg",
    )


def _clean_plain_text(raw: str | None, max_chars: int) -> str:
    if not raw:
        return ""
    unescaped = html.unescape(raw)
    stripped = _HTML_TAG_RE.sub(" ", unescaped)
    collapsed = _WHITESPACE_RE.sub(" ", stripped).strip()
    return collapsed[:max_chars].strip()


def _parse_published_date(raw: str | None) -> str:
    if not raw:
        return ""
    text = raw.strip()
    try:
        dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
        return dt.date().isoformat()
    except ValueError:
        if len(text) >= 10:
            try:
                return datetime.strptime(text[:10], "%Y-%m-%d").date().isoformat()
            except ValueError:
                return ""
        return ""


def parse_youtube_feed_xml(xml_bytes: bytes) -> list[dict[str, str]]:
    """Parse a YouTube Atom feed with `defusedxml` and return up to 10 newest videos."""
    if not xml_bytes or not xml_bytes.strip():
        raise YouTubeFeedError(ERR_NO_FEED, status_code=502)

    try:
        root = SafeET.fromstring(
            xml_bytes,
            forbid_dtd=True,
            forbid_entities=True,
            forbid_external=True,
        )
    except (DefusedXmlException, StdET.ParseError, ValueError) as err:
        raise YouTubeFeedError(ERR_NO_FEED, status_code=502) from err

    if root.tag not in {f"{_ATOM_NS}feed", "feed"}:
        raise YouTubeFeedError(ERR_NO_FEED, status_code=502)

    videos: list[dict[str, str]] = []
    seen_ids: set[str] = set()

    for entry in root.findall(f"{_ATOM_NS}entry") + root.findall("entry"):
        raw_vid = (entry.findtext(f"{_YT_NS}videoId") or "").strip()
        if not raw_vid:
            atom_id = (entry.findtext(f"{_ATOM_NS}id") or entry.findtext("id") or "").strip()
            if atom_id.startswith("yt:video:"):
                raw_vid = atom_id.removeprefix("yt:video:").strip()
        if not VIDEO_ID_RE.match(raw_vid) or raw_vid in seen_ids:
            continue
        seen_ids.add(raw_vid)

        raw_title = (
            entry.findtext(f"{_ATOM_NS}title")
            or entry.findtext("title")
            or entry.findtext(f"{_MEDIA_NS}group/{_MEDIA_NS}title")
            or ""
        )
        title = _clean_plain_text(raw_title, MAX_TITLE_CHARS)
        if not title:
            continue

        raw_published = (
            entry.findtext(f"{_ATOM_NS}published")
            or entry.findtext("published")
            or entry.findtext(f"{_ATOM_NS}updated")
            or entry.findtext("updated")
            or ""
        )
        published = _parse_published_date(raw_published)

        raw_desc = (
            entry.findtext(f"{_MEDIA_NS}group/{_MEDIA_NS}description")
            or entry.findtext(f"{_MEDIA_NS}description")
            or ""
        )
        description = _clean_plain_text(raw_desc, MAX_DESCRIPTION_CHARS)

        watch_url, thumbnail_url = build_video_urls(raw_vid)
        videos.append(
            {
                "video_id": raw_vid,
                "title": title,
                "published": published,
                "description": description,
                "url": watch_url,
                "thumbnail_url": thumbnail_url,
            }
        )

    videos.sort(key=lambda item: item.get("published") or "", reverse=True)
    return videos[:MAX_VIDEOS]


def _is_timeout_error(err: Exception) -> bool:
    if isinstance(err, httpx.TimeoutException):
        return True
    cause = getattr(err, "__cause__", None)
    if isinstance(cause, httpx.TimeoutException):
        return True
    text = str(err).lower()
    return any(tok in text for tok in ("timeout", "timed out", "readtimeout", "connecttimeout"))


async def _discover_channel_feed_url(
    channel_url: str,
    client: httpx.AsyncClient,
    *,
    resolver: ResolverFn | None = None,
) -> str:
    """Resolve a non-/channel/UC... URL to its public YouTube Atom feed URL."""

    async def _fetch_once() -> tuple[list[SitemapEntry], list[str]]:
        policy = await fetch_robots_policy("https://www.youtube.com", client, resolver=resolver)
        if not policy.is_allowed(channel_url):
            raise YouTubeFeedError(ERR_NO_FEED, status_code=502)
        try:
            status, body, _final_url = await _fetch_bytes_guarded(
                channel_url,
                client,
                max_bytes=MAX_SITEMAP_BYTES,
                truncate_on_limit=False,
                resolver=resolver,
            )
        except SitemapError as err:
            if _is_timeout_error(err):
                raise YouTubeFeedError(ERR_TIMEOUT, status_code=504) from err
            raise YouTubeFeedError(ERR_NO_FEED, status_code=502) from err

        if status != 200 or not body:
            raise YouTubeFeedError(ERR_NO_FEED, status_code=502)

        discovered = discover_feed_url_from_html(body.decode("utf-8", errors="ignore"))
        if not discovered:
            raise YouTubeFeedError(ERR_NO_FEED, status_code=502)
        return [], [discovered]

    _entries, sitemaps = await scan_guard.crawl(channel_url, 1, _fetch_once)
    feed_url = sitemaps[0] if sitemaps else ""
    if not FEED_URL_RE.match(feed_url):
        raise YouTubeFeedError(ERR_NO_FEED, status_code=502)
    return feed_url


async def fetch_youtube_channel_videos(
    raw_url: str,
    *,
    client: httpx.AsyncClient | None = None,
    resolver: ResolverFn | None = None,
) -> dict[str, Any]:
    """Fetch and parse up to 10 recent videos from a public YouTube channel feed."""
    channel_url, feed_url = parse_youtube_channel_url(raw_url)

    owns_client = client is None
    active_client = client or httpx.AsyncClient(timeout=DEFAULT_REQUEST_TIMEOUT)
    try:
        if feed_url is None:
            feed_url = await _discover_channel_feed_url(
                channel_url, active_client, resolver=resolver
            )

        try:
            status, xml_bytes, _final_url = await _fetch_bytes_guarded(
                feed_url,
                active_client,
                max_bytes=MAX_SITEMAP_BYTES,
                truncate_on_limit=False,
                resolver=resolver,
            )
        except SitemapError as err:
            if _is_timeout_error(err):
                raise YouTubeFeedError(ERR_TIMEOUT, status_code=504) from err
            raise YouTubeFeedError(ERR_NO_FEED, status_code=502) from err

        if status != 200 or not xml_bytes:
            raise YouTubeFeedError(ERR_NO_FEED, status_code=502)

        videos = parse_youtube_feed_xml(xml_bytes)
        return {
            "channel_url": channel_url,
            "feed_url": feed_url,
            "fetched_at": datetime.now(UTC).isoformat(timespec="seconds"),
            "videos": videos,
        }
    finally:
        if owns_client:
            await active_client.aclose()
