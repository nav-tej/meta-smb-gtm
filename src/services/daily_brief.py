"""Daily growth brief for /today, built at most once a day from saved and monitored data.

No model is called here, so reading the brief never spends Muse API credit. It combines:

- Watchlist: each competitor from its saved public snapshot, a fresh live Muse analysis already
  in the result cache (24-hour TTL), or the latest competitor-monitor check.
- Overnight changes: new listings, price updates and ad changes the monitor logged in the last
  24 hours (src/services/competitor_monitor.py).
- Performance trends: deterministic metrics from the sample campaign export (synthetic data,
  labelled as such), computed in Python by the Bid Advisor.
- Top 3 actions and a focus of the day, ranked from those signals.

Own briefs read only the account workspace and are never cached. The sample is cached per UTC
day. `refresh=True` rebuilds the sample only when its inputs changed (a new monitor run or fresh
analysis), so it still regenerates at most once per day for the same data.
Each section falls back to saved data on its own, so one bad input never breaks the brief.
"""

from __future__ import annotations

import json
import logging
import time
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any, Literal

from fastapi import Response
from pydantic import (
    BaseModel,
    Field,
    SerializerFunctionWrapHandler,
    TypeAdapter,
    ValidationError,
    model_serializer,
)

from src.config import get_settings
from src.models.outcome import Outcome
from src.services import competitor_monitor, result_cache
from src.services.accounts import AccountSession, load_workspace
from src.services.competitor_checks import _format_short_date, normalize_competitor_url
from src.services.demo import demo_competitor_brief, snapshot_competitor_brief
from src.services.seller_memory import _extract_profile_parts, rank_seller_recommendations

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
    status: Literal["new", "first", "fresh", "changed", "unchecked", "unchanged", "failed"]
    note: str
    checked_at: str | None = None

    @model_serializer(mode="wrap")
    def serialize_watch_item(self, handler: SerializerFunctionWrapHandler) -> dict[str, Any]:
        data = handler(self)
        if self.checked_at is None:
            data.pop("checked_at", None)
        return data


class DailyMove(BaseModel):
    title: str
    reason: str
    href: str
    impact: Literal["high", "medium", "low"] = "high"
    source: str = ""
    over_budget: bool = False
    recommendation: dict[str, Any] | None = None

    @model_serializer(mode="wrap")
    def serialize_move(self, handler: SerializerFunctionWrapHandler) -> dict[str, Any]:
        data = handler(self)
        if self.recommendation is None:
            data.pop("recommendation", None)
            if not self.over_budget:
                data.pop("over_budget", None)
        return data


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

    business_name: str | None = None
    outcomes: list[Outcome] = Field(default_factory=list)
    results_note: str = ""

    @model_serializer(mode="wrap")
    def serialize_brief(self, handler: SerializerFunctionWrapHandler) -> dict[str, Any]:
        data = handler(self)
        # The sample's public JSON contract predates own-workspace fields.
        if self.business_name is None:
            for key in ("business_name", "outcomes", "results_note"):
                data.pop(key, None)
        return data


class SetupIncompleteError(ValueError):
    """The account has not completed its own workspace setup."""


# "fresh" is the sample brief's "Fresh Muse brief" chip; a saved own check is never a brief and may
# be days old, so it gets its own chips ("No change", "Couldn't check" in muse-shell.js).
_SAVED_CHECK_STATUS_MAP: dict[str, Literal["first", "changed", "unchanged", "failed"]] = {
    "first_check": "first",
    "changed": "changed",
    "unchanged": "unchanged",
    "error": "failed",
}

_UNCHECKED_WATCH_NOTE = "Not checked yet. Check now (free) on your digest."
_OWN_OVERNIGHT_NOTE = "Muse checks your watchlist when you press Check now (free) on your digest."


def _parse_iso_timestamp(raw: Any) -> datetime | None:
    if not isinstance(raw, str) or not raw.strip():
        return None
    try:
        dt = datetime.fromisoformat(raw.strip().replace("Z", "+00:00"))
        return dt if dt.tzinfo is not None else dt.replace(tzinfo=UTC)
    except ValueError:
        return None


def _own_watch_items(
    workspace: dict[str, Any], competitors: list[Any]
) -> tuple[list[WatchItem], str]:
    raw_prefs = workspace.get("preferences")
    saved_checks = (
        raw_prefs.get("competitor_checks")
        if isinstance(raw_prefs, dict) and isinstance(raw_prefs.get("competitor_checks"), dict)
        else {}
    )
    items: list[WatchItem] = []
    latest_dt: datetime | None = None
    latest_iso = ""
    for c in competitors:
        if not c.selected:
            continue
        norm_url = normalize_competitor_url(c.url)
        saved = saved_checks.get(norm_url) if norm_url else None
        if not isinstance(saved, dict):
            items.append(
                WatchItem(
                    name=c.name or c.url,
                    url=c.url,
                    where="Website",
                    status="unchecked",
                    note=_UNCHECKED_WATCH_NOTE,
                )
            )
            continue
        raw_status = str(saved.get("status") or "").strip()
        mapped_status = _SAVED_CHECK_STATUS_MAP.get(raw_status, "unchecked")
        if raw_status == "error":
            note = str(saved.get("error") or "").strip() or "This site could not be read right now."
        elif raw_status in ("first_check", "changed", "unchanged"):
            note = str(saved.get("summary") or "").strip() or _UNCHECKED_WATCH_NOTE
        else:
            note = _UNCHECKED_WATCH_NOTE
        raw_checked_at = str(saved.get("checked_at") or "").strip() or None
        parsed_dt = _parse_iso_timestamp(raw_checked_at)
        if parsed_dt is not None and (latest_dt is None or parsed_dt > latest_dt):
            latest_dt = parsed_dt
            latest_iso = raw_checked_at or ""
        items.append(
            WatchItem(
                name=c.name or c.url,
                url=c.url,
                where="Website",
                status=mapped_status,
                note=note,
                checked_at=raw_checked_at,
            )
        )
    short_date = _format_short_date(latest_iso) if latest_iso else ""
    overnight_note = (
        f"{_OWN_OVERNIGHT_NOTE} Last check: {short_date}." if short_date else _OWN_OVERNIGHT_NOTE
    )
    return items, overnight_note


def _own_brief(workspace: dict[str, Any], today: date, now: datetime) -> DailyBrief:
    onboarding = workspace.get("onboarding")
    if not isinstance(onboarding, dict) or not onboarding.get("completed_at"):
        raise SetupIncompleteError("Finish setup first")
    business_name = str(onboarding.get("business_name") or "Your business")
    business_type = onboarding.get("business_type")
    if business_type not in {"products", "services", "both"}:
        business_type = None
    pref, voice, competitors, signals = _extract_profile_parts(workspace)
    ranked = rank_seller_recommendations(
        business_name=business_name,
        business_type=business_type,
        preferences=pref,
        voice_profile=voice,
        competitor_entries=competitors,
        dismiss_signals=signals,
    )
    moves = [
        DailyMove(
            title=rec["title"],
            reason=rec["why_this_fits"],
            href="/create?workspace=own",
            impact=rec["priority"],
            source="Your saved setup",
            over_budget=rec["over_budget"],
            recommendation=rec,
        )
        for rec in ranked["recommendations"][:3]
    ]
    # No channel may be available after dismiss signals. Do not invent a ranked move.
    focus = moves[0] if moves else None
    fallback = DailyMove(
        title="Choose a posting channel",
        reason="Update your context to choose where you want to post.",
        href="/today?workspace=own#smStudioContextBar",
        impact="low",
        source="Your saved setup",
    )
    outcomes: list[Outcome] = []
    raw_outcomes = workspace.get("outcomes")
    for item in raw_outcomes if isinstance(raw_outcomes, list) else []:
        if not isinstance(item, dict):
            continue
        try:
            outcomes.append(Outcome.model_validate(item))
        except ValidationError:
            logger.warning("Skipping invalid outcome in own daily brief")
    watch_items, overnight_note = _own_watch_items(workspace, competitors)
    return DailyBrief(
        date=today.isoformat(),
        generated_at=now.isoformat(timespec="seconds"),
        source=f"Built from {business_name}'s saved setup. No runs used.",
        business_name=business_name,
        items=watch_items,
        move=focus or fallback,
        focus=focus,
        action_items=moves,
        overnight_note=overnight_note,
        trends_source="Your logged results",
        outcomes=outcomes,
        results_note=(
            "Results you logged. These are not measured automatically."
            if outcomes
            else "After posting, log a result to see it here."
        ),
        inputs=f"account:{business_name}",
    )


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
    reason="SikhiArt has warrior and saint groups but none for women; catalog gap.",
    href="/create",
    impact="high",
    source="Saved Muse Spark brief (Nov 3)",
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
                    href=(
                        "/create?idea=idea-3-gift-ready"
                        if "gift" in ad_set.ad_set_name.lower()
                        else "/create?idea=idea-2-starter-prints"
                    ),
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


def build_daily_brief(
    today: date | None = None,
    now: datetime | None = None,
    account_workspace: dict[str, Any] | None = None,
) -> DailyBrief:
    now = now or datetime.now(UTC)
    today = today or now.date()

    if account_workspace is not None:
        return _own_brief(account_workspace, today, now)

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


async def daily_brief(
    *,
    refresh: bool = False,
    response: Response | None = None,
    account: AccountSession | None = None,
) -> DailyBrief:
    """Read own context fresh, or reuse the sample brief until its inputs change.

    Every read compares the cached brief's input fingerprint (latest monitor run, fresh cached
    analyses) with the current one, so a new competitor check shows up without regenerating the
    brief for unchanged data. `refresh` is kept for the Re-check button and behaves the same.
    """
    today = datetime.now(UTC).date()
    if account is not None:
        ws = await load_workspace(account)
        return build_daily_brief(today, account_workspace=ws.get("document") or {})

    key = {"date": today.isoformat(), "v": BRIEF_VERSION, "account_id": "demo"}
    adapter: TypeAdapter[DailyBrief] = TypeAdapter(DailyBrief)
    current = result_cache.load("daily-brief", key, adapter)
    expected_inputs = _guard("inputs", _inputs_fingerprint, "")
    if current is not None and current.inputs == expected_inputs:
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
