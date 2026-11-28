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

Cache and fast-path counters live in memory. When hosted and the scan cap is enabled, the
first cache miss reserves the entire public batch through muse_reserve_public_work before any
crawl, sharing database limits across instances. That RPC requires abuse_controls.sql first.
Protected scheduled callers without a public preflight retain their own admission/lease rules.
In-flight crawls are shared and bounded even with cache settings off. A firewall rule is still
needed to stop abusive requests before the function runs.
"""

from __future__ import annotations

import asyncio
import math
import threading
import time
from collections import OrderedDict, deque
from collections.abc import Awaitable, Callable
from contextvars import ContextVar
from dataclasses import dataclass, field
from functools import wraps
from typing import ParamSpec, TypeVar
from urllib.parse import urlsplit, urlunsplit

from fastapi import HTTPException

from src.config import get_settings
from src.models.intel import SitemapEntry
from src.utils.sitemap import SitemapError

WINDOW_SECONDS = 600
MAX_CACHED_SITES = 256
MAX_VISITORS = 4096
MAX_INFLIGHT_CRAWLS = 16
MAX_CRAWL_SECONDS = 20
_LOCK = threading.RLock()
_P = ParamSpec("_P")
_R = TypeVar("_R")


def _synchronized(function: Callable[_P, _R]) -> Callable[_P, _R]:
    @wraps(function)
    def wrapped(*args: _P.args, **kwargs: _P.kwargs) -> _R:
        with _LOCK:
            return function(*args, **kwargs)

    return wrapped


@dataclass
class _ScanBatch:
    visitor: str
    count: int
    remaining: int
    admitted: bool = False
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)


_batch: ContextVar[_ScanBatch | None] = ContextVar("public_scan_batch", default=None)
_inflight: dict[tuple[asyncio.AbstractEventLoop, str, int], asyncio.Task] = {}


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


@_synchronized
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


@_synchronized
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


@_synchronized
def reserve_scans(visitor: str, count: int) -> int | None:
    """Reserve `count` fresh crawls for this visitor.

    Returns None when they may start (or the limit is off), otherwise the whole seconds until
    enough earlier crawls leave the 10-minute window. Nothing is reserved on a refusal.
    """
    limit = get_settings().scans_per_visitor_per_10_min
    _batch.set(None)
    if limit <= 0:
        return None
    if count <= 0:
        _batch.set(_ScanBatch(visitor, 0, 0))
        return None
    now = _now()
    # Do not evict live rate-limit buckets: rotating identities must not reset an earlier one.
    if visitor not in _visits and len(_visits) >= MAX_VISITORS:
        for key in [
            key for key, times in _visits.items() if not times or now - times[-1] >= WINDOW_SECONDS
        ]:
            del _visits[key]
        if len(_visits) >= MAX_VISITORS:
            return WINDOW_SECONDS
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
    _batch.set(_ScanBatch(visitor, count, count))
    return None


@_synchronized
def fresh_count(urls: list[str], max_urls: int) -> int:
    """How many of these websites a scan would crawl now (not served from the cache)."""
    return sum(1 for url in urls if cached_crawl(url, max_urls) is None)


async def _admit_public_batch() -> None:
    batch = _batch.get()
    if batch is None or not get_settings().hosted_environment:
        # Protected scheduled watchlist callers do not use public scan admission.
        return
    from src.services.usage_meter import reserve_public_work

    async with batch.lock:
        if batch.remaining <= 0:
            raise HTTPException(
                429, refusal_message(WINDOW_SECONDS), headers={"Retry-After": str(WINDOW_SECONDS)}
            )
        if not batch.admitted:
            # Reserve the entire request before the first crawl, never after partial work.
            await reserve_public_work("scan", batch.visitor, batch.count)
            batch.admitted = True
        batch.remaining -= 1


async def crawl(
    url: str,
    max_urls: int,
    fetch: Callable[[], Awaitable[tuple[list[SitemapEntry], list[str]]]],
) -> tuple[list[SitemapEntry], list[str]]:
    """Share identical in-flight crawls and reserve hosted public batches before I/O."""
    cached = cached_crawl(url, max_urls)
    if cached is not None:
        return cached
    await _admit_public_batch()
    key = (asyncio.get_running_loop(), _key(url), max_urls)

    async def load() -> tuple[list[SitemapEntry], list[str]]:
        try:
            entries, sitemaps = await asyncio.wait_for(fetch(), timeout=MAX_CRAWL_SECONDS)
        except TimeoutError as err:
            raise SitemapError(
                "Muse couldn't finish checking this website in time. "
                "Try again later, or enter the details yourself."
            ) from err
        remember_crawl(url, max_urls, entries, sitemaps)
        return entries, sitemaps

    def forget(done: asyncio.Task) -> None:
        with _LOCK:
            if _inflight.get(key) is done:
                _inflight.pop(key, None)
        if not done.cancelled():
            done.exception()  # Retrieve errors even when every waiting client disconnected.

    with _LOCK:
        task = _inflight.get(key)
        if task is None:
            if len(_inflight) >= MAX_INFLIGHT_CRAWLS:
                raise HTTPException(
                    503, "Muse is checking many websites. Please try again shortly."
                )
            task = asyncio.create_task(load())
            _inflight[key] = task
            task.add_done_callback(forget)
    # One disconnected client must not cancel work shared with another request.
    entries, sitemaps = await asyncio.shield(task)
    return [entry.model_copy(deep=True) for entry in entries], list(sitemaps)


def refusal_message(retry_after: int) -> str:
    minutes = max(1, math.ceil(retry_after / 60))
    unit = "minute" if minutes == 1 else "minutes"
    return (
        "Muse has checked a lot of websites from your connection in the last few minutes. "
        f"Try again in {minutes} {unit}, or enter the details yourself."
    )


@_synchronized
def reset() -> None:
    """Forget every cached crawl and visitor count (tests)."""
    _cache.clear()
    _visits.clear()
    _inflight.clear()
    _batch.set(None)
