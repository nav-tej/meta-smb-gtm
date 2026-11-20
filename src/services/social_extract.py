"""Pure function social-handle extractor for crawled storefront pages and markup.

Extracts confirmed, normalized social handles (Instagram, Facebook, Pinterest,
TikTok, YouTube, Twitter/X) from raw HTML (links, meta tags, JSON-LD sameAs) or
crawl data structures without any model calls or network dependencies.
"""

from __future__ import annotations

import json
import re
from typing import Any
from urllib.parse import unquote, urlparse

# Supported platforms and domain matches
PLATFORMS: dict[str, str] = {
    "instagram.com": "instagram",
    "facebook.com": "facebook",
    "fb.com": "facebook",
    "pinterest.com": "pinterest",
    "pinterest.ca": "pinterest",
    "pinterest.co.uk": "pinterest",
    "tiktok.com": "tiktok",
    "youtube.com": "youtube",
    "twitter.com": "twitter",
    "x.com": "twitter",
}

# Subpaths that indicate shares, feeds, or non-profile pages to reject
IGNORED_PATHS = {
    "p",
    "reel",
    "reels",
    "stories",
    "explore",
    "share",
    "sharer",
    "sharer.php",
    "intent",
    "pin",
    "pins",
    "dialog",
    "tr",
    "watch",
    "login",
    "signup",
    "terms",
    "privacy",
    "help",
    "hashtag",
    "tags",
}

URL_REGEX = re.compile(r"""https?://[^\s<>"'\)]+""", re.IGNORECASE)
JSON_LD_REGEX = re.compile(
    r"""<script[^>]*type=["']application/ld\+json["'][^>]*>(.*?)</script>""",
    re.IGNORECASE | re.DOTALL,
)
META_TAG_REGEX = re.compile(
    r"""<meta[^>]+(?:content|property|name)=["']([^"']+)["'][^>]*>""",
    re.IGNORECASE,
)
HREF_TAG_REGEX = re.compile(r"""<a[^>]+href=["']([^"']+)["']""", re.IGNORECASE)


def _clean_handle(raw_handle: str) -> str:
    handle = raw_handle.strip().lstrip("@")
    handle = handle.split("?")[0].split("#")[0].strip("/")
    return f"@{handle}" if handle else ""


def _canonical_url(platform: str, handle: str) -> str:
    clean = handle.lstrip("@")
    if platform == "instagram":
        return f"https://instagram.com/{clean}"
    if platform == "facebook":
        return f"https://facebook.com/{clean}"
    if platform == "pinterest":
        return f"https://pinterest.com/{clean}"
    if platform == "tiktok":
        return f"https://tiktok.com/@{clean}"
    if platform == "youtube":
        return f"https://youtube.com/@{clean}"
    if platform == "twitter":
        return f"https://x.com/{clean}"
    return f"https://{platform}.com/{clean}"


def _parse_candidate_url(raw_url: str) -> tuple[str, str, str] | None:
    """Parse a URL into (platform, handle, canonical_url) or None if invalid/non-profile."""
    trimmed = unquote(raw_url.strip())
    if not trimmed or not re.match(r"^https?://", trimmed, re.IGNORECASE):
        return None

    try:
        parsed = urlparse(trimmed)
    except Exception:
        return None

    netloc = (parsed.netloc or "").lower().replace("www.", "")
    platform: str | None = None
    for domain_pattern, name in PLATFORMS.items():
        if netloc == domain_pattern or netloc.endswith(f".{domain_pattern}"):
            platform = name
            break

    if not platform:
        return None

    # Path segments
    path_segments = [p for p in parsed.path.strip("/").split("/") if p]
    if not path_segments:
        return None

    first = path_segments[0].lower()
    if first in IGNORED_PATHS or first.startswith(("_", ".", "#")):
        return None

    # Platform-specific path parsing
    handle = ""
    if platform in ("instagram", "facebook", "pinterest"):
        handle = path_segments[0]
    elif platform == "tiktok":
        handle = path_segments[0] if path_segments[0].startswith("@") else f"@{path_segments[0]}"
    elif platform == "youtube":
        if first in ("c", "channel", "user") and len(path_segments) > 1:
            handle = path_segments[1]
        else:
            handle = path_segments[0]
    elif platform == "twitter":
        handle = path_segments[0]

    cleaned = _clean_handle(handle)
    if not cleaned or len(cleaned) <= 2:
        return None

    # Reject handles that look like system scripts, query strings, or common non-usernames
    if cleaned.lower() in ("@null", "@undefined", "@true", "@false", "@admin", "@user"):
        return None

    canonical = _canonical_url(platform, cleaned)
    return platform, cleaned, canonical


def extract_social_handles(content: str | dict[str, Any] | list[Any]) -> list[dict[str, Any]]:
    """Extract and normalize unique social handles from HTML or crawl data structures.

    Returns a list of dicts:
    [
        {
            "platform": "instagram",
            "handle": "@artofsarabjit",
            "url": "https://instagram.com/artofsarabjit",
            "confirmed": True,
            "source": "crawl",
        },
        ...
    ]
    """
    candidates: list[str] = []

    def _collect(obj: Any) -> None:
        if isinstance(obj, str):
            # Check for JSON-LD scripts
            for script_body in JSON_LD_REGEX.findall(obj):
                try:
                    data = json.loads(script_body)
                    _collect(data)
                except Exception:
                    pass

            # Extract URLs from href and meta attributes
            candidates.extend(HREF_TAG_REGEX.findall(obj))
            candidates.extend(META_TAG_REGEX.findall(obj))
            # Also raw URL regex
            candidates.extend(URL_REGEX.findall(obj))
        elif isinstance(obj, dict):
            # Inspect sameAs in JSON-LD
            same_as = obj.get("sameAs")
            if isinstance(same_as, list):
                candidates.extend(str(item) for item in same_as if item)
            elif isinstance(same_as, str):
                candidates.append(same_as)

            # Inspect common crawl keys
            for key in (
                "url",
                "loc",
                "social_urls",
                "links",
                "channels",
                "suggested_socials",
                "socials",
            ):
                val = obj.get(key)
                if val is not None:
                    _collect(val)
        elif isinstance(obj, list):
            for item in obj:
                _collect(item)

    _collect(content)

    results: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()

    for raw in candidates:
        parsed = _parse_candidate_url(raw)
        if not parsed:
            continue
        platform, handle, canonical = parsed
        key = (platform, handle.lower())
        if key in seen:
            continue
        seen.add(key)
        results.append(
            {
                "platform": platform,
                "handle": handle,
                "url": canonical,
                "confirmed": True,
                "source": "crawl",
            }
        )

    # Sort deterministically by platform then handle
    results.sort(key=lambda s: (s["platform"], s["handle"].lower()))
    return results
