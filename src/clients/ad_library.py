"""Meta Ad Library API client for monitoring active Facebook & Instagram competitor ads.

Uses Meta's official Graph API `/ads_archive` endpoint (never scrapes behind logins, per
AGENTS.md section 10). Computes deterministic ad-longevity and placement signals in Python.
"""

from __future__ import annotations

import json
import logging
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

from src.config import Settings, get_settings
from src.models.intel import SocialAdSummary, SocialCompetitorSignals

logger = logging.getLogger(__name__)

GRAPH_API_ADS_ARCHIVE_URL = "https://graph.facebook.com/v21.0/ads_archive"
DEFAULT_TIMEOUT = httpx.Timeout(20.0, connect=5.0)


class AdLibraryError(Exception):
    """Raised when querying or parsing the Meta Ad Library API fails."""


def _parse_start_time(raw: str | None) -> datetime | None:
    if not raw or not raw.strip():
        return None
    cleaned = raw.strip()
    if cleaned.endswith("Z"):
        cleaned = cleaned[:-1] + "+00:00"
    # Graph API often emits +0000 without colon
    if len(cleaned) >= 5 and cleaned[-5] in {"+", "-"} and cleaned[-4:].isdigit():
        cleaned = f"{cleaned[:-2]}:{cleaned[-2:]}"
    try:
        dt = datetime.fromisoformat(cleaned)
    except ValueError:
        return None
    return dt.replace(tzinfo=UTC) if dt.tzinfo is None else dt.astimezone(UTC)


def summarize_ad_library_records(
    records: list[dict[str, Any]],
    *,
    query: str,
    now: datetime | None = None,
) -> SocialCompetitorSignals:
    """Compute deterministic longevity and placement metrics from raw Ad Library records."""
    ref_now = (now or datetime.now(tz=UTC)).astimezone(UTC)
    platform_counter: Counter[str] = Counter()
    summaries: list[SocialAdSummary] = []
    proven_30d = 0

    for item in records:
        ad_id = str(item.get("id") or "")
        page_name = str(item.get("page_name") or "Unknown Page")
        platforms = [str(p).lower() for p in (item.get("publisher_platforms") or []) if p]
        for plat in platforms:
            platform_counter[plat] += 1

        started = _parse_start_time(item.get("ad_delivery_start_time"))
        days_running = max(0, (ref_now - started).days) if started else 0
        if days_running >= 30:
            proven_30d += 1

        titles = item.get("ad_creative_link_titles") or []
        bodies = item.get("ad_creative_bodies") or []
        headline = str(titles[0]).strip()[:160] if titles else ""
        body_excerpt = " ".join(str(bodies[0]).split())[:240] if bodies else ""

        summaries.append(
            SocialAdSummary(
                ad_id=ad_id,
                page_name=page_name,
                platforms=platforms,
                days_running=days_running,
                headline=headline,
                body_excerpt=body_excerpt,
            )
        )

    ranked = sorted(summaries, key=lambda s: s.days_running, reverse=True)
    return SocialCompetitorSignals(
        query=query,
        total_active_ads=len(summaries),
        proven_30d_winners_count=proven_30d,
        platform_counts=dict(platform_counter),
        top_longevity_ads=ranked[:10],
    )


def load_sample_ad_library_signals(
    sample_path: Path,
    *,
    query: str = "Sikh heritage & South Asian wall art",
    now: datetime | None = None,
) -> SocialCompetitorSignals:
    """Load recorded Ad Library records from a JSON fixture for offline demos/tests."""
    payload = json.loads(sample_path.read_text(encoding="utf-8"))
    rows = payload.get("data", []) if isinstance(payload, dict) else payload
    if not isinstance(rows, list):
        raise AdLibraryError(f"Expected 'data' list in {sample_path}")
    return summarize_ad_library_records(rows, query=query, now=now)


class MetaAdLibraryClient:
    """Async client for Meta's public Ad Library `/ads_archive` endpoint."""

    def __init__(
        self,
        *,
        settings: Settings | None = None,
        access_token: str | None = None,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        cfg = settings or get_settings()
        self._token = (
            access_token if access_token is not None else cfg.meta_ads_access_token
        ).strip()
        self._owns_client = http_client is None
        self._http_client = http_client or httpx.AsyncClient(timeout=DEFAULT_TIMEOUT)

    async def aclose(self) -> None:
        if self._owns_client:
            await self._http_client.aclose()

    async def search_active_ads(
        self,
        search_terms: str,
        *,
        countries: tuple[str, ...] = ("US", "CA", "GB"),
        limit: int = 25,
        now: datetime | None = None,
    ) -> SocialCompetitorSignals:
        """Query active IG/FB competitor ads matching `search_terms` and compute signals."""
        if not self._token:
            raise AdLibraryError(
                "META_ADS_ACCESS_TOKEN is required for live Meta Ad Library queries."
            )

        params = {
            "search_terms": search_terms,
            "ad_active_status": "ACTIVE",
            "ad_type": "ALL",
            "ad_reached_countries": json.dumps(list(countries)),
            "fields": (
                "id,page_name,ad_delivery_start_time,publisher_platforms,"
                "ad_creative_bodies,ad_creative_link_titles"
            ),
            "limit": str(min(max(limit, 1), 100)),
            "access_token": self._token,
        }
        try:
            response = await self._http_client.get(GRAPH_API_ADS_ARCHIVE_URL, params=params)
        except httpx.HTTPError as err:
            raise AdLibraryError(f"Ad Library HTTP failure: {type(err).__name__}") from err

        if response.status_code != 200:
            raise AdLibraryError(f"Meta Ad Library error (HTTP {response.status_code}).")

        data = response.json()
        records = data.get("data", []) if isinstance(data, dict) else []
        return summarize_ad_library_records(records, query=search_terms, now=now)
