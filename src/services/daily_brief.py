"""Daily growth brief for /today, built at most once a day from saved and monitored data.

No model is called here, so reading the brief never spends Muse API credit. It combines:

- Watchlist: each competitor from its saved public snapshot, a fresh live Muse analysis already
  in the result cache (24-hour TTL), or the latest competitor-monitor check.
- Overnight changes: new listings, price updates and ad changes the monitor logged in the last
  24 hours (src/services/competitor_monitor.py).
- Performance trends: deterministic metrics from the sample campaign export (synthetic data,
  labelled as such), computed in Python by the Bid Advisor.
- Top 3 actions and a focus of the day, ranked from those signals.

The brief is cached per UTC day. `refresh=True` rebuilds it only when its inputs changed (a new
monitor run or fresh analysis), so it still regenerates at most once per day for the same data.
Each section falls back to saved data on its own, so one bad input never breaks the brief.
"""

from __future__ import annotations

import json
import logging
import time
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Literal

from fastapi import Response
from pydantic import BaseModel, Field, TypeAdapter

from src.config import get_settings
from src.services import competitor_monitor, result_cache
from src.services.demo import demo_competitor_brief, snapshot_competitor_brief

logger = logging.getLogger(__name__)

BRIEF_VERSION = 2
SAMPLE_CAMPAIGN = Path(__file__).resolve().parents[2] / "data/samples/sarabjit_singh_campaign.json"
WATCHLIST: list[tuple[str, str, str]] = [
    (name, url, where) for name, url, where, _ in competitor_monitor.WATCHLIST
]


class WatchItem(BaseModel):
    name: str
    url: str
    where: str
    status: Literal["new", "first", "fresh", "changed"]
    note: str


class DailyMove(BaseModel):
    title: str
    reason: str
    href: str
    impact: Literal["high", "medium", "low"] = "high"
    source: str = ""


class OvernightChange(BaseModel):
    competitor: str
    kind: str
    text: str
    url: str = ""


class TrendItem(BaseModel):
    label: str
    value: str
    direction: Literal["up", "down", "flat"]
    good: bool | None = None
    note: str = ""


class DailyBrief(BaseModel):
    date: str
    generated_at: str
    source: str
    items: list[WatchItem] = Field(default_factory=list)
    move: DailyMove
    fresh_analyses: int = 0
    focus: DailyMove | None = None
    action_items: list[DailyMove] = Field(default_factory=list)
    overnight_changes: list[OvernightChange] = Field(default_factory=list)
    overnight_note: str = ""
    trends: list[TrendItem] = Field(default_factory=list)
    trends_source: str = ""
    inputs: str = Field(default="", description="Fingerprint of the data the brief was built from.")


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


SNAPSHOT_MOVE = DailyMove(
    title="Feature your Empowering Women series",
    reason="SikhiArt keeps adding warrior and guru editions but has no group for women's stories.",
    href="/create?goal=story",
    impact="high",
    source="Competitor gap in the saved SikhiArt brief",
)


def _watch_items(today: date) -> tuple[list[WatchItem], int]:
    fresh = _fresh_live_summaries()
    saved = demo_competitor_brief()
    latest = competitor_monitor.load_changelog().runs[:1]
    monitored = {c.name: c for c in latest[0].competitors} if latest else {}
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
        check = monitored.get(name)
        if check is not None and check.status != "error":
            counts = ", ".join(
                f"{n} {competitor_monitor.KIND_LABEL.get(k, k)}{'s' if n != 1 else ''}"
                for k, n in check.counts.items()
            )
            items.append(
                WatchItem(
                    name=name,
                    url=url,
                    where=f"{platform} · {check.pages_seen} pages",
                    status="changed" if check.counts else "first",
                    note=(
                        f"Monitor check {latest[0].checked_at[:10]}: {counts}."
                        if counts
                        else f"Monitor check {latest[0].checked_at[:10]}: no changes since "
                        f"the {check.compared_with}."
                    ),
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
    return items, fresh_count


def _overnight(now: datetime) -> tuple[list[OvernightChange], str]:
    log = competitor_monitor.load_changelog()
    found = competitor_monitor.changes_since(now - timedelta(hours=24))
    priority = {"price_change": 0, "new_listing": 1, "ad_new": 2, "ad_stopped": 3}
    found.sort(key=lambda item: priority.get(item[1].kind, 4))
    changes = [
        OvernightChange(
            competitor=name,
            kind=change.kind,
            text=competitor_monitor.describe(change, name),
            url=change.url if change.url.startswith("http") else "",
        )
        for name, change, _ in found[:8]
    ]
    if changes:
        note = f"{len(found)} change(s) logged by the competitor monitor in the last 24 hours."
    elif log.last_checked_at:
        note = f"No changes in the last 24 hours. Last monitor check: {log.last_checked_at[:16]}."
    else:
        note = "No monitor check yet, so overnight changes are not tracked. Run a check."
    return changes, note


def _trends() -> tuple[list[TrendItem], list[DailyMove], str]:
    """Deterministic campaign trends (Python only) and the actions their flags suggest."""
    from src.models.bids import CampaignPerformance
    from src.services.bid_advisor import compute_metrics

    campaign = CampaignPerformance.model_validate_json(SAMPLE_CAMPAIGN.read_text())
    metrics = compute_metrics(campaign)
    totals = metrics.account_totals
    source = (
        f"Sample campaign export, {metrics.start_date:%b %-d}–{metrics.end_date:%b %-d} "
        "(synthetic numbers shaped like a Meta Ads Manager export; connect your own CSV "
        "for real trends)."
    )
    trends: list[TrendItem] = [
        TrendItem(
            label="Account return on ad spend",
            value=f"{totals.roas:.2f}x" if totals.roas is not None else "n/a",
            direction="flat",
            note=f"${totals.spend:,.0f} spend, {totals.conversions} sales over {metrics.days} days",
        )
    ]
    actions: list[DailyMove] = []
    for ad_set in metrics.ad_sets:
        if ad_set.roas_trend_pct is not None and abs(ad_set.roas_trend_pct) >= 5:
            up = ad_set.roas_trend_pct > 0
            trends.append(
                TrendItem(
                    label=f"{ad_set.ad_set_name} ROAS",
                    value=f"{ad_set.roas_trend_pct:+.0f}%",
                    direction="up" if up else "down",
                    good=up,
                    note="Second half of the period vs the first half",
                )
            )
        if "creative_fatigue" in ad_set.flags:
            ctr = ad_set.ctr_trend_pct
            fell = f"fell {abs(ctr):.0f}%" if ctr is not None and ctr < 0 else "is slipping"
            actions.append(
                DailyMove(
                    title=f"Refresh the creative on {ad_set.ad_set_name}",
                    reason=f"Click-through rate {fell} as the same people keep seeing it.",
                    href="/create?goal=gift" if "gift" in ad_set.ad_set_name.lower() else "/create",
                    impact="high",
                    source="Campaign trend",
                )
            )
        if "budget_limited_winner" in ad_set.flags and ad_set.roas_vs_account is not None:
            actions.append(
                DailyMove(
                    title=f"Consider more budget for {ad_set.ad_set_name}",
                    reason=(
                        f"It returns {ad_set.roas_vs_account:.1f}x the account average and spends "
                        "its full daily budget."
                    ),
                    href="/#loop-improve",
                    impact="medium",
                    source="Campaign trend",
                )
            )
        if "low_roas_material_spend" in ad_set.flags and ad_set.roas_vs_account is not None:
            actions.append(
                DailyMove(
                    title=f"Review {ad_set.ad_set_name} before spending more",
                    reason=(
                        f"Its return is {ad_set.roas_vs_account:.2f}x the account average on "
                        "real spend."
                    ),
                    href="/#loop-improve",
                    impact="medium",
                    source="Campaign trend",
                )
            )
    return trends[:6], actions, source


def _change_actions(changes: list[OvernightChange]) -> list[DailyMove]:
    actions: list[DailyMove] = []
    prices = [c for c in changes if c.kind == "price_change"]
    if prices:
        actions.append(
            DailyMove(
                title=f"Check your print prices against {prices[0].competitor}",
                reason=prices[0].text,
                href="/#loop-research",
                impact="high",
                source="Competitor monitor",
            )
        )
    listings = [c for c in changes if c.kind == "new_listing"]
    if listings:
        actions.append(
            DailyMove(
                title=f"See what {listings[0].competitor} just listed",
                reason=f"{len(listings)} new listing(s) overnight, e.g. {listings[0].text}.",
                href="/#loop-research",
                impact="medium",
                source="Competitor monitor",
            )
        )
    return actions


def _guard(label: str, build, default):  # type: ignore[no-untyped-def]
    try:
        return build()
    except Exception as err:  # one bad input must not break the brief
        logger.warning("Daily brief section %s fell back: %s", label, type(err).__name__)
        return default


def _inputs_fingerprint() -> str:
    runs = competitor_monitor.load_changelog().runs
    fresh = sorted(round(f[2]) for f in _fresh_live_summaries())
    return json.dumps({"run": runs[0].run_id if runs else None, "fresh": fresh})


def build_daily_brief(today: date | None = None, now: datetime | None = None) -> DailyBrief:
    now = now or datetime.now(UTC)
    today = today or now.date()
    items, fresh_count = _guard("watchlist", lambda: _watch_items(today), ([], 0))
    changes, overnight_note = _guard(
        "overnight", lambda: _overnight(now), ([], "Overnight changes are unavailable today.")
    )
    trends, trend_actions, trends_source = _guard(
        "trends", _trends, ([], [], "Campaign trends are unavailable today.")
    )
    impact_rank = {"high": 0, "medium": 1, "low": 2}
    # Real competitor evidence outranks the synthetic sample campaign at equal impact.
    source_rank = {"Competitor monitor": 0, SNAPSHOT_MOVE.source: 1}
    ranked = sorted(
        [*_change_actions(changes), *trend_actions, SNAPSHOT_MOVE],
        key=lambda move: (impact_rank[move.impact], source_rank.get(move.source, 2)),
    )
    action_items: list[DailyMove] = []
    for move in ranked:
        if all(move.title != m.title for m in action_items):
            action_items.append(move)
    action_items = action_items[:3]
    focus = action_items[0] if action_items else SNAPSHOT_MOVE
    monitored = (
        " and the competitor monitor log" if "Last monitor" in overnight_note or changes else ""
    )
    source = (
        f"Built {today.isoformat()} from saved Nov 3 snapshots{monitored}"
        + (
            f" and {fresh_count} fresh live Muse analyses from the 24-hour cache"
            if fresh_count
            else ""
        )
        + ". No new Muse call was made to build this brief."
    )
    return DailyBrief(
        date=today.isoformat(),
        generated_at=now.isoformat(timespec="seconds"),
        source=source,
        items=items,
        move=focus,
        fresh_analyses=fresh_count,
        focus=focus,
        action_items=action_items,
        overnight_changes=changes,
        overnight_note=overnight_note,
        trends=trends,
        trends_source=trends_source,
        inputs=_guard("inputs", _inputs_fingerprint, ""),
    )


async def daily_brief(*, refresh: bool = False, response: Response | None = None) -> DailyBrief:
    """Today's brief: built once per day and reused until its inputs change.

    Every read compares the cached brief's input fingerprint (latest monitor run, fresh cached
    analyses) with the current one, so a new competitor check shows up without regenerating the
    brief for unchanged data. `refresh` is kept for the Re-check button and behaves the same.
    """
    today = datetime.now(UTC).date()
    key = {"date": today.isoformat(), "v": BRIEF_VERSION}
    adapter: TypeAdapter[DailyBrief] = TypeAdapter(DailyBrief)
    current = result_cache.load("daily-brief", key, adapter)
    if current is not None and current.inputs == _guard("inputs", _inputs_fingerprint, ""):
        if response is not None:
            response.headers[result_cache.CACHE_HEADER] = "hit"
            if refresh:
                response.headers["X-Muse-Brief"] = "unchanged"
        return current

    async def produce() -> DailyBrief:
        return build_daily_brief(today)

    return await result_cache.cached(
        "daily-brief", key, DailyBrief, produce, response, refresh=True
    )
