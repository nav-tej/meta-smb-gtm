"""Daily growth brief for /today, built once a day from saved data and cached live analyses.

No model is called here. Each watched competitor is described from its saved public snapshot,
or from a fresh live Muse analysis when one is already in the result cache (within the 24-hour
TTL), so reading the brief never spends Muse API credit.
"""

from __future__ import annotations

import json
import time
from datetime import UTC, date, datetime
from typing import Literal

from fastapi import Response
from pydantic import BaseModel, Field

from src.config import get_settings
from src.services import result_cache
from src.services.demo import demo_competitor_brief, snapshot_competitor_brief

BRIEF_VERSION = 1

WATCHLIST: list[tuple[str, str, str]] = [
    ("SikhiArt.com", "https://www.sikhiart.com", "Own shop"),
    (
        "Gurinderpreet Kaur",
        "https://fineartamerica.com/profiles/gurinderpreet-kaur/art/paintings",
        "Fine Art America",
    ),
    (
        "Manjot Singh Sachdeva",
        "https://fineartamerica.com/profiles/manjot-singh-sachdeva/art/photographs",
        "Fine Art America / Pixels",
    ),
    ("Gurdish Pannu", "https://www.saatchiart.com/gurdishpannu", "Saatchi Art"),
]


class WatchItem(BaseModel):
    name: str
    url: str
    where: str
    status: Literal["new", "first", "fresh"]
    note: str


class DailyMove(BaseModel):
    title: str
    reason: str
    href: str
    impact: Literal["high", "medium", "low"] = "high"


class DailyBrief(BaseModel):
    date: str
    generated_at: str
    source: str
    items: list[WatchItem] = Field(default_factory=list)
    move: DailyMove
    fresh_analyses: int = 0


def _matches(url: str, cached_url: str) -> bool:
    def norm(u: str) -> str:
        return u.lower().split("://")[-1].removeprefix("www.").rstrip("/")

    a, b = norm(url), norm(cached_url)
    return a == b or a.startswith(b) or b.startswith(a)


def _fresh_live_summaries() -> list[tuple[str, str, float]]:
    """(competitor_url, summary, stored_at) for live analyses still inside the cache TTL."""
    settings = get_settings()
    if not settings.result_cache_enabled:
        return []
    found: list[tuple[str, str, float]] = []
    now = time.time()
    try:
        paths = sorted(result_cache.cache_dir().glob("analyze-competitors-*.json"))
    except OSError:
        return []
    for path in paths:
        try:
            entry = json.loads(path.read_text())
        except (OSError, ValueError):
            continue
        stored_at = entry.get("stored_at")
        value = entry.get("value") or {}
        if (
            not isinstance(stored_at, (int, float))
            or now - stored_at > settings.result_cache_ttl_seconds
        ):
            continue
        if isinstance(value.get("competitor_url"), str) and isinstance(value.get("summary"), str):
            found.append((value["competitor_url"], value["summary"], stored_at))
    return found


def _age(seconds: float) -> str:
    hours = int(seconds // 3600)
    return "under an hour ago" if hours < 1 else f"{hours}h ago"


def build_daily_brief(today: date | None = None) -> DailyBrief:
    today = today or datetime.now(UTC).date()
    fresh = _fresh_live_summaries()
    saved = demo_competitor_brief()
    items: list[WatchItem] = []
    fresh_count = 0
    for name, url, platform in WATCHLIST:
        live = next((f for f in sorted(fresh, key=lambda f: -f[2]) if _matches(url, f[0])), None)
        if live:
            fresh_count += 1
            items.append(
                WatchItem(
                    name=name,
                    url=url,
                    where=platform,
                    status="fresh",
                    note=f"Fresh Muse brief ({_age(time.time() - live[2])}): {live[1][:180]}",
                )
            )
            continue
        if "sikhiart" in url:
            recent = saved.signals.recent_30d_count
            focus = saved.doubling_down_on[0] if saved.doubling_down_on else ""
            items.append(
                WatchItem(
                    name=name,
                    url=url,
                    where=f"{platform} · {saved.signals.total_urls} pages",
                    status="new" if recent else "first",
                    note=(
                        f"{recent} new listings in the 30 days before the Nov 3 snapshot. "
                        f"{focus}".strip()
                        if recent
                        else "No new listings in the snapshot window."
                    ),
                )
            )
            continue
        brief = snapshot_competitor_brief(url)
        if brief is None:
            continue
        price = brief.pricing_signals[0] if brief.pricing_signals else ""
        items.append(
            WatchItem(
                name=name,
                url=url,
                where=f"{platform} · {brief.signals.total_urls} pages",
                status="first",
                note=f"{price}. First check, so nothing to compare yet.".replace("..", "."),
            )
        )
    source = (
        f"Built {today.isoformat()} from saved Nov 3 snapshots"
        + (
            f" and {fresh_count} fresh live Muse analyses from the 24-hour cache"
            if fresh_count
            else ""
        )
        + ". No new Muse call was made to build this brief."
    )
    return DailyBrief(
        date=today.isoformat(),
        generated_at=datetime.now(UTC).isoformat(timespec="seconds"),
        source=source,
        items=items,
        move=DailyMove(
            title="Feature your Empowering Women series",
            reason=(
                "SikhiArt keeps adding warrior and guru editions but has no group for "
                "women's stories."
            ),
            href="/create?goal=story",
        ),
        fresh_analyses=fresh_count,
    )


async def daily_brief(*, refresh: bool = False, response: Response | None = None) -> DailyBrief:
    """Today's brief, generated once and then served from the result cache until tomorrow."""
    today = datetime.now(UTC).date()

    async def produce() -> DailyBrief:
        return build_daily_brief(today)

    return await result_cache.cached(
        "daily-brief",
        {"date": today.isoformat(), "v": BRIEF_VERSION},
        DailyBrief,
        produce,
        response,
        refresh=refresh,
    )
