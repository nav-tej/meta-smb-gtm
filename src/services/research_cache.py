"""Track E: Content-addressed research cache.

Caches Flow 1 competitor intel crawls, daily briefs, and ad previews.
Ensures identical queries within the TTL cost 0 runs and show honest refresh labels.

TTLs:
- competitor_crawl: 7 days
- daily_brief: 24 hours
- ad_previews: no expiry
"""

from __future__ import annotations

import hashlib
import json
import logging
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, TypeVar

from pydantic import BaseModel

logger = logging.getLogger(__name__)

T = TypeVar("T")

NAMESPACE_COMPETITOR_CRAWL = "competitor_crawl"
NAMESPACE_DAILY_BRIEF = "daily_brief"
NAMESPACE_AD_PREVIEWS = "ad_previews"

TTL_SECONDS: dict[str, int | None] = {
    NAMESPACE_COMPETITOR_CRAWL: 7 * 86400,  # 7 days
    NAMESPACE_DAILY_BRIEF: 24 * 3600,  # 24 hours
    NAMESPACE_AD_PREVIEWS: None,  # no expiry
}

REPO_ROOT = Path(__file__).resolve().parents[2]
_custom_cache_dir: Path | None = None


def get_research_cache_dir() -> Path:
    """Return the filesystem directory used for local durable research cache entries."""
    if _custom_cache_dir is not None:
        return _custom_cache_dir
    d = REPO_ROOT / "data" / "research" / "cache"
    d.mkdir(parents=True, exist_ok=True)
    return d


def set_research_cache_dir(path: Path | None) -> None:
    """Override cache directory (primarily for isolated test fixtures)."""
    global _custom_cache_dir
    _custom_cache_dir = path
    if path is not None:
        path.mkdir(parents=True, exist_ok=True)


def compute_research_cache_key(
    namespace: str,
    account_id: str | None,
    urls: list[str] | str,
    *,
    flow: str = "flow1",
    model_id: str = "muse-spark-1.3",
    prompt_version: str = "v1",
) -> str:
    """Compute SHA-256 hash over canonical JSON of research request parameters."""
    normalized_urls = [urls] if isinstance(urls, str) else sorted(urls)
    canonical = {
        "account_id": account_id or "demo",
        "flow": flow,
        "model_id": model_id,
        "namespace": namespace,
        "prompt_version": prompt_version,
        "urls": normalized_urls,
    }
    blob = json.dumps(canonical, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


class ResearchCacheEntry(BaseModel):
    """A durable cached research result with expiration and honest status label."""

    cache_key: str
    namespace: str
    account_id: str | None = None
    url: str | None = None
    flow: str = "flow1"
    model_id: str = "muse-spark-1.3"
    prompt_version: str = "v1"
    response_json: dict[str, Any]
    created_at: str
    expires_at: str | None = None

    def is_expired(self, now: datetime | None = None) -> bool:
        if self.expires_at is None:
            return False
        current_time = now if now is not None else datetime.now(UTC)
        try:
            exp = datetime.fromisoformat(self.expires_at)
            return current_time > exp
        except Exception:
            return False

    def format_label(self) -> str:
        """Format seller-facing label: e.g. 'Last checked Nov 10 · Refresh (1 run)'."""
        try:
            created = datetime.fromisoformat(self.created_at)
            date_str = created.strftime("%b %-d")
        except Exception:
            date_str = "recently"
        return f"Last checked {date_str} · Refresh (1 run)"


def get_cached_entry(cache_key: str, now: datetime | None = None) -> ResearchCacheEntry | None:
    """Read entry from cache. Returns None if missing or expired."""
    path = get_research_cache_dir() / f"{cache_key}.json"
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        entry = ResearchCacheEntry.model_validate(data)
        if entry.is_expired(now=now):
            return None
        return entry
    except Exception as err:
        logger.debug("Failed reading cache entry %s: %s", cache_key, err)
        return None


def put_cached_entry(entry: ResearchCacheEntry) -> None:
    """Persist entry to durable cache."""
    path = get_research_cache_dir() / f"{entry.cache_key}.json"
    try:
        path.write_text(entry.model_dump_json(indent=2), encoding="utf-8")
    except Exception as err:
        logger.warning("Failed writing research cache entry %s: %s", entry.cache_key, err)


def build_cache_entry(
    namespace: str,
    account_id: str | None,
    urls: list[str] | str,
    response_data: dict[str, Any],
    *,
    flow: str = "flow1",
    model_id: str = "muse-spark-1.3",
    prompt_version: str = "v1",
    now: datetime | None = None,
) -> ResearchCacheEntry:
    """Create and timestamp a ResearchCacheEntry with the appropriate TTL."""
    current_time = now if now is not None else datetime.now(UTC)
    ttl = TTL_SECONDS.get(namespace)
    expires_at = (current_time + timedelta(seconds=ttl)).isoformat() if ttl is not None else None

    key = compute_research_cache_key(
        namespace,
        account_id,
        urls,
        flow=flow,
        model_id=model_id,
        prompt_version=prompt_version,
    )
    first_url = urls if isinstance(urls, str) else (urls[0] if urls else None)

    return ResearchCacheEntry(
        cache_key=key,
        namespace=namespace,
        account_id=account_id,
        url=first_url,
        flow=flow,
        model_id=model_id,
        prompt_version=prompt_version,
        response_json=response_data,
        created_at=current_time.isoformat(),
        expires_at=expires_at,
    )


async def cached_research(
    namespace: str,
    account_id: str | None,
    urls: list[str] | str,
    response_model: type[T],
    producer: Callable[[], Awaitable[T]],
    *,
    flow: str = "flow1",
    model_id: str = "muse-spark-1.3",
    prompt_version: str = "v1",
    force_refresh: bool = False,
    now: datetime | None = None,
) -> tuple[T, bool, str]:
    """Execute producer with research caching.

    Returns:
        (result, is_cache_hit, display_label)

    Rules:
    - If hit: is_cache_hit=True, 0 runs charged, returns cached response.
    - If miss: is_cache_hit=False, executes producer, caches response, returns fresh response.
    """
    key = compute_research_cache_key(
        namespace,
        account_id,
        urls,
        flow=flow,
        model_id=model_id,
        prompt_version=prompt_version,
    )

    if not force_refresh:
        entry = get_cached_entry(key, now=now)
        if entry is not None:
            try:
                result = response_model.model_validate(entry.response_json)  # type: ignore[attr-defined]
                return result, True, entry.format_label()
            except Exception as err:
                logger.warning("Cache deserialization failed for %s: %s", key, err)

    # Cache miss or forced refresh: execute producer
    fresh = await producer()

    # Serialize and store in cache
    response_dict = (
        fresh.model_dump(mode="json") if isinstance(fresh, BaseModel) else dict(fresh)  # type: ignore[call-overload]
    )
    new_entry = build_cache_entry(
        namespace,
        account_id,
        urls,
        response_dict,
        flow=flow,
        model_id=model_id,
        prompt_version=prompt_version,
        now=now,
    )
    put_cached_entry(new_entry)

    return fresh, False, new_entry.format_label()
