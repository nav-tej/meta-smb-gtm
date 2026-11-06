"""File-based cache for live Muse results, so repeating a demo does not spend API credit.

Each entry is one JSON file named by a hash of the route namespace and the full request, holding
the validated response and the time it was stored. Entries older than the TTL (24 hours by
default) are ignored. Only successful live results are stored. The cache never holds credentials:
keys are built from request bodies, and request bodies never carry the API key.

Two layers use this module:

- Route level (`cached`): a whole live response (competitor brief, ad set, bid advice...).
- Call level (`get_raw` / `put_raw`): every Muse request in `src/clients/meta.py` (chat, image
  generation and edits, SAM, voice) is keyed by endpoint + a hash of its exact parameters and
  checked here before any billed call is made.

When a live call fails, `cached(..., fallback=...)` serves the newest stored result for the same
request even past its TTL (`X-Muse-Cache: stale`), then the saved demo result, so a provider
outage never shows a user a raw error.

Known limit on Vercel: the cache directory is /tmp, which is per function instance and is
emptied on a cold start. A hit there is a bonus, not a guarantee; repeated demos on a fresh
instance can miss and call Muse again (still bounded by credits and the hourly cap). A durable
shared cache would need Vercel Blob/Redis or Supabase storage.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import tempfile
import time
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any, TypeVar

from fastapi import Response
from pydantic import BaseModel, TypeAdapter, ValidationError

from src.config import get_settings
from src.services import live_quota

logger = logging.getLogger(__name__)

T = TypeVar("T")
CACHE_HEADER = "X-Muse-Cache"
FALLBACK_HEADER = "X-Muse-Fallback"
# Call-level entries hold base64 media; skip writing anything unreasonably large.
MAX_ENTRY_BYTES = 15 * 1024 * 1024
REPO_ROOT = Path(__file__).resolve().parents[2]


def cache_dir() -> Path:
    configured = Path(get_settings().result_cache_dir)
    return configured if configured.is_absolute() else REPO_ROOT / configured


def cache_key(namespace: str, payload: Any) -> str:
    """Stable key for a request: the namespace plus a SHA-256 of its canonical JSON."""
    data = payload.model_dump(mode="json") if isinstance(payload, BaseModel) else payload
    blob = json.dumps(
        {"ns": namespace, "data": data}, sort_keys=True, separators=(",", ":"), default=str
    )
    digest = hashlib.sha256(blob.encode()).hexdigest()[:40]
    safe_ns = "".join(ch if ch.isalnum() or ch in "-_" else "-" for ch in namespace)
    return f"{safe_ns}-{digest}"


def _path(namespace: str, payload: Any) -> Path:
    return cache_dir() / f"{cache_key(namespace, payload)}.json"


def _read_entry(namespace: str, payload: Any, *, allow_stale: bool = False) -> Any | None:
    """The stored JSON value, or None when caching is off, missing, expired or unreadable."""
    settings = get_settings()
    if not settings.result_cache_enabled:
        return None
    try:
        entry = json.loads(_path(namespace, payload).read_text())
    except (OSError, ValueError):
        return None
    if not isinstance(entry, dict):
        return None
    stored_at = entry.get("stored_at")
    if not isinstance(stored_at, (int, float)):
        return None
    if not allow_stale and time.time() - stored_at > settings.result_cache_ttl_seconds:
        return None
    return entry.get("value")


def _write_entry(namespace: str, payload: Any, value: Any) -> None:
    if not get_settings().result_cache_enabled:
        return
    path = _path(namespace, payload)
    entry = {"namespace": namespace, "stored_at": time.time(), "value": value}
    try:
        blob = json.dumps(entry, separators=(",", ":"))
    except (TypeError, ValueError):
        logger.warning("Result cache write skipped for %s: value is not JSON", namespace)
        return
    if len(blob) > MAX_ENTRY_BYTES:
        logger.info("Result cache write skipped for %s: entry too large", namespace)
        return
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".tmp-", suffix=".json")
        with os.fdopen(fd, "w") as handle:
            handle.write(blob)
        os.replace(tmp, path)
    except OSError as err:
        logger.warning("Result cache write skipped for %s: %s", namespace, type(err).__name__)


def load(
    namespace: str, payload: Any, adapter: TypeAdapter[T], *, allow_stale: bool = False
) -> T | None:
    """Return a fresh cached value, or None when caching is off, missing, stale or invalid.

    `allow_stale=True` ignores the TTL; it is only used as a fallback when a live call failed.
    """
    raw = _read_entry(namespace, payload, allow_stale=allow_stale)
    if raw is None:
        return None
    try:
        return adapter.validate_python(raw)
    except ValidationError:
        logger.warning("Ignoring an invalid result-cache entry for %s", namespace)
        return None


def store(namespace: str, payload: Any, value: Any, adapter: TypeAdapter[Any]) -> None:
    """Write a result atomically. A read-only or full disk only skips caching."""
    if not get_settings().result_cache_enabled:
        return
    _write_entry(namespace, payload, adapter.dump_python(value, mode="json"))


def get_raw(namespace: str, payload: Any) -> Any | None:
    """Call-level lookup: the fresh JSON value stored for this exact Muse request, if any."""
    return _read_entry(namespace, payload)


def put_raw(namespace: str, payload: Any, value: Any) -> None:
    """Call-level store of a successful Muse response (plain JSON: text, base64 media)."""
    _write_entry(namespace, payload, value)


def mark_fallback(kind: str, response: Response | None = None) -> None:
    """Record that this request was answered without a successful live call."""
    from src.clients.meta import note_fallback

    note_fallback(kind)
    if response is not None:
        response.headers[FALLBACK_HEADER] = kind


def _is_provider_failure(err: Exception) -> bool:
    """Upstream failures that deserve a cached/demo fallback (not quota or input errors)."""
    import httpx

    from src.clients.comfyui import ComfyUIError
    from src.clients.meta import MetaAPIError

    return isinstance(err, (MetaAPIError, ComfyUIError, httpx.HTTPError, TimeoutError))


async def cached(
    namespace: str,
    payload: Any,
    response_type: Any,
    produce: Callable[[], Awaitable[T]],
    response: Response | None = None,
    *,
    refresh: bool = False,
    fallback: Callable[[], T] | None = None,
) -> T:
    """Serve a fresh cached result, otherwise run `produce` (the live call) and cache it.

    `refresh=True` skips the read but still stores the new result. Sets `X-Muse-Cache` to
    `hit` or `miss` on the response when one is passed. If the live call fails upstream, the
    newest stored result for the same request is served (`stale`), then `fallback()` (the saved
    demo result, `X-Muse-Fallback: demo`). Without either, the original error propagates.
    """
    adapter: TypeAdapter[Any] = TypeAdapter(response_type)
    if not refresh:
        hit = load(namespace, payload, adapter)
        if hit is not None:
            # No Muse call happens on a hit, so give back any presenter live-call slot.
            live_quota.release_reserved()
            from src.clients.meta import note_cache_hit

            note_cache_hit(namespace)
            if response is not None:
                response.headers[CACHE_HEADER] = "hit"
            return hit
    try:
        value = await produce()
    except Exception as err:
        if not _is_provider_failure(err):
            raise
        logger.warning(
            "Live %s failed (%s); trying cached/demo fallback", namespace, type(err).__name__
        )
        stale = load(namespace, payload, adapter, allow_stale=True)
        if stale is not None:
            mark_fallback("stale-cache", response)
            if response is not None:
                response.headers[CACHE_HEADER] = "stale"
            return stale
        if fallback is not None:
            mark_fallback("demo", response)
            return fallback()
        raise
    store(namespace, payload, value, adapter)
    if response is not None:
        response.headers[CACHE_HEADER] = "miss"
    return value
