"""Guards for the public website scans (POST /ingest-storefront and /seller-memory/scan).

The scans need no sign-in, because setup and both editors use them before an account exists. One
request can name up to 21 websites, and the function runs for as long as the crawl takes. Two
guards, both off unless configured (Nav decides the values):

- SCAN_CACHE_SECONDS: a successful crawl of one website is reused for this long. A crawl keeps
  the first N addresses it finds, so one made with a bigger page cap also answers a smaller one
  (its first N entries); a bigger cap than the cached crawl's is crawled again. Setup (25),
  /today (20) and /create (30) each scan the seller's site on a first visit; with the cache on,
  that is at most two crawls. Failed crawls are never cached, so a seller who fixes their site can
  try again at once.
- SCANS_PER_VISITOR_PER_10_MIN: how many fresh crawls (cache misses) one visitor, the hashed
  client IP, may start in 10 minutes. A request that needs more than what is left is refused as
  a whole with 429 and Retry-After. Cached websites never count.

Both live in memory, so on serverless hosts they apply per running instance, as the live-call cap
in src/api/demo.py does. They cut duplicate crawls and runaway loops; they are not a global
quota, and a refused request still runs the function. Only a platform rule (a firewall rate
limit) keeps requests from reaching the function at all.
"""

from __future__ import annotations

import math
import time
from collections import OrderedDict, deque
from collections.abc import Awaitable, Callable
from urllib.parse import urlsplit, urlunsplit

from src.config import get_settings
from src.models.intel import SitemapEntry

WINDOW_SECONDS = 600
MAX_CACHED_SITES = 256
MAX_VISITORS = 4096

# website -> (stored at, page cap it was crawled with, entries, sitemaps)
_cache: OrderedDict[str, tuple[float, int, list[dict], list[str]]] = OrderedDict()
_visits: OrderedDict[str, deque[float]] = OrderedDict()


def _now() -> float:
    return time.monotonic()


def _key(url: str) -> str:
    """The scheme and host are case-insensitive and a trailing slash is the same page; paths
    keep their case."""
    parts = urlsplit(url.strip())
    path = parts.path.rstrip("/")
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), path, parts.query, ""))


def cached_crawl(url: str, max_urls: int) -> tuple[list[SitemapEntry], list[str]] | None:
    """A fresh cached crawl of this website, or None (cache off, missing or expired)."""
    ttl = get_settings().scan_cache_seconds
    if ttl <= 0:
        return None
    key = _key(url)
    hit = _cache.get(key)
    if hit is None:
        return None
    stored_at, stored_cap, entries, sitemaps = hit
    if _now() - stored_at > ttl:
        _cache.pop(key, None)
        return None
    if stored_cap < max_urls:
        return None
    _cache.move_to_end(key)
    return [SitemapEntry.model_validate(entry) for entry in entries[:max_urls]], list(sitemaps)


def remember_crawl(
    url: str, max_urls: int, entries: list[SitemapEntry], sitemaps: list[str]
) -> None:
    """Keep a successful crawl for SCAN_CACHE_SECONDS. Failures are never passed in."""
    if get_settings().scan_cache_seconds <= 0:
        return
    key = _key(url)
    _cache[key] = (
        _now(),
        max_urls,
        [entry.model_dump(mode="json") for entry in entries],
        list(sitemaps),
    )
    _cache.move_to_end(key)
    while len(_cache) > MAX_CACHED_SITES:
        _cache.popitem(last=False)


def reserve_scans(visitor: str, count: int) -> int | None:
    """Reserve `count` fresh crawls for this visitor.

    Returns None when they may start (or the limit is off), otherwise the whole seconds until
    enough earlier crawls leave the 10-minute window. Nothing is reserved on a refusal.
    """
    limit = get_settings().scans_per_visitor_per_10_min
    if limit <= 0 or count <= 0:
        return None
    now = _now()
    times = _visits.pop(visitor, None) or deque()
    while times and now - times[0] >= WINDOW_SECONDS:
        times.popleft()
    if len(times) + count > limit:
        if count > limit:
            wait = float(WINDOW_SECONDS)
        else:
            oldest_needed = times[len(times) + count - limit - 1]
            wait = WINDOW_SECONDS - (now - oldest_needed)
        if times:
            _visits[visitor] = times
        return max(1, math.ceil(wait))
    times.extend([now] * count)
    _visits[visitor] = times
    while len(_visits) > MAX_VISITORS:
        _visits.popitem(last=False)
    return None


def fresh_count(urls: list[str], max_urls: int) -> int:
    """How many of these websites a scan would crawl now (not served from the cache)."""
    return sum(1 for url in urls if cached_crawl(url, max_urls) is None)


async def crawl(
    url: str,
    max_urls: int,
    fetch: Callable[[], Awaitable[tuple[list[SitemapEntry], list[str]]]],
) -> tuple[list[SitemapEntry], list[str]]:
    """The cached crawl of this website when fresh, otherwise `fetch()` (kept on success)."""
    cached = cached_crawl(url, max_urls)
    if cached is not None:
        return cached
    entries, sitemaps = await fetch()
    remember_crawl(url, max_urls, entries, sitemaps)
    return entries, sitemaps


def refusal_message(retry_after: int) -> str:
    minutes = max(1, math.ceil(retry_after / 60))
    unit = "minute" if minutes == 1 else "minutes"
    return (
        "Muse has checked a lot of websites from your connection in the last few minutes. "
        f"Try again in {minutes} {unit}, or enter the details yourself."
    )


def reset() -> None:
    """Forget every cached crawl and visitor count (tests)."""
    _cache.clear()
    _visits.clear()
