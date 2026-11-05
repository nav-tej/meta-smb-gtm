"""File-based cache for live Muse results, so repeating a demo does not spend API credit.

Each entry is one JSON file named by a hash of the route namespace and the full request, holding
the validated response and the time it was stored. Entries older than the TTL (24 hours by
default) are ignored. Only successful live results are stored. The cache never holds credentials:
keys are built from request bodies, and request bodies never carry the API key.
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

logger = logging.getLogger(__name__)

T = TypeVar("T")
CACHE_HEADER = "X-Muse-Cache"
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


def load(namespace: str, payload: Any, adapter: TypeAdapter[T]) -> T | None:
    """Return a fresh cached value, or None when caching is off, missing, stale or invalid."""
    settings = get_settings()
    if not settings.result_cache_enabled:
        return None
    path = _path(namespace, payload)
    try:
        entry = json.loads(path.read_text())
    except (OSError, ValueError):
        return None
    stored_at = entry.get("stored_at")
    if not isinstance(stored_at, (int, float)):
        return None
    if time.time() - stored_at > settings.result_cache_ttl_seconds:
        return None
    try:
        return adapter.validate_python(entry.get("value"))
    except ValidationError:
        logger.warning("Ignoring an invalid result-cache entry for %s", namespace)
        return None


def store(namespace: str, payload: Any, value: Any, adapter: TypeAdapter[Any]) -> None:
    """Write a result atomically. A read-only or full disk only skips caching."""
    if not get_settings().result_cache_enabled:
        return
    path = _path(namespace, payload)
    entry = {
        "namespace": namespace,
        "stored_at": time.time(),
        "value": adapter.dump_python(value, mode="json"),
    }
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".tmp-", suffix=".json")
        with os.fdopen(fd, "w") as handle:
            json.dump(entry, handle, separators=(",", ":"))
        os.replace(tmp, path)
    except OSError as err:
        logger.warning("Result cache write skipped for %s: %s", namespace, type(err).__name__)


async def cached(
    namespace: str,
    payload: Any,
    response_type: Any,
    produce: Callable[[], Awaitable[T]],
    response: Response | None = None,
    *,
    refresh: bool = False,
) -> T:
    """Serve a fresh cached result, otherwise run `produce` (the live call) and cache it.

    `refresh=True` skips the read but still stores the new result. Sets `X-Muse-Cache` to
    `hit` or `miss` on the response when one is passed.
    """
    adapter: TypeAdapter[Any] = TypeAdapter(response_type)
    if not refresh:
        hit = load(namespace, payload, adapter)
        if hit is not None:
            if response is not None:
                response.headers[CACHE_HEADER] = "hit"
            return hit
    value = await produce()
    store(namespace, payload, value, adapter)
    if response is not None:
        response.headers[CACHE_HEADER] = "miss"
    return value
