"""Personal digest preview and workspace-persisted draft preferences (Batch 2A).

This module never sends email, never crawls competitor sites, never calls Muse,
and never debits runs. Draft preferences live in a dedicated workspace namespace
(`digest_draft_preferences`) and are explicitly isolated from live subscriptions.
"""

from __future__ import annotations

import calendar
import html
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Literal
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, field_validator

from src.api.seller_memory import _extract_profile_parts
from src.clients.supabase import SupabaseError, configured
from src.services.accounts import AccountSession, load_workspace, save_workspace
from src.services.digest_email import (
    LABELS,
    ShopReport,
    SnapshotStore,
    _company_line,
    _key,
    _safe_link,
    _wrap,
)
from src.services.seller_memory import rank_seller_recommendations

logger = logging.getLogger(__name__)

CadenceType = Literal["weekly", "biweekly", "monthly", "paused"]
TopicType = Literal["listing_changes", "pricing", "suggested_moves"]

CADENCES: tuple[CadenceType, ...] = ("weekly", "biweekly", "monthly", "paused")
CANONICAL_TOPICS: tuple[TopicType, ...] = ("listing_changes", "pricing", "suggested_moves")
TOPIC_ALIASES: dict[str, TopicType] = {
    "listing_changes": "listing_changes",
    "listings": "listing_changes",
    "pricing": "pricing",
    "prices": "pricing",
    "suggested_moves": "suggested_moves",
    "ideas": "suggested_moves",
}

DEFAULT_TIMEZONE = "America/Los_Angeles"
DEFAULT_DELIVERY_HOUR = 8
DELIVERY_WINDOW_HOURS = 2
MAX_PREVIEW_CHANGES = 3
STALE_SNAPSHOT_AFTER = timedelta(days=14)
DRAFT_WORKSPACE_KEY = "digest_draft_preferences"

SnapshotLoader = Callable[[str], Awaitable[dict[str, Any] | None]]


class DigestDraftError(Exception):
    def __init__(self, status_code: int, detail: str) -> None:
        self.status_code = status_code
        self.detail = detail
        super().__init__(detail)


def validate_timezone(tz_name: str) -> str:
    clean = (tz_name or "").strip()
    if not clean or len(clean) > 80:
        raise ValueError("Choose a valid IANA timezone (e.g. America/Los_Angeles).")
    try:
        ZoneInfo(clean)
    except (ZoneInfoNotFoundError, KeyError, ValueError) as err:
        raise ValueError("Choose a valid IANA timezone (e.g. America/Los_Angeles).") from err
    return clean


def normalize_topics(raw_topics: list[str] | None) -> list[TopicType]:
    if raw_topics is None:
        return list(CANONICAL_TOPICS)
    seen: list[TopicType] = []
    for raw in raw_topics:
        mapped = TOPIC_ALIASES.get(str(raw or "").strip().lower())
        if mapped and mapped not in seen:
            seen.append(mapped)
    return seen


def normalize_draft_competitors(raw_urls: list[str] | None) -> list[str]:
    shops: list[str] = []
    for raw in raw_urls or []:
        value = (raw or "").strip()
        if not value:
            continue
        if "://" not in value:
            value = "https://" + value
        parts = urlsplit(value)
        if parts.scheme not in {"http", "https"} or not parts.hostname or len(value) > 300:
            raise ValueError("Use public shop links starting with https://.")
        cleaned = f"{parts.scheme}://{parts.netloc}{parts.path}".rstrip("/") or value
        if cleaned not in shops:
            shops.append(cleaned)
        if len(shops) >= 3:
            break
    return shops


class DigestDraftPreferences(BaseModel):
    """Saved draft digest settings stored in workspace document."""

    model_config = ConfigDict(extra="ignore")

    cadence: CadenceType = "weekly"
    topics: list[TopicType] = Field(default_factory=lambda: list(CANONICAL_TOPICS))
    timezone: str = DEFAULT_TIMEZONE
    anchor_day: int | None = Field(default=None, ge=1, le=31)
    anchor_date: str | None = Field(default=None, max_length=10)
    competitors: list[str] = Field(default_factory=list, max_length=3)

    @field_validator("timezone")
    @classmethod
    def _check_tz(cls, v: str) -> str:
        return validate_timezone(v)

    @field_validator("topics", mode="before")
    @classmethod
    def _norm_topics(cls, v: Any) -> list[TopicType]:
        if isinstance(v, list):
            return normalize_topics([str(x) for x in v])
        return list(CANONICAL_TOPICS)

    @field_validator("competitors", mode="before")
    @classmethod
    def _norm_shops(cls, v: Any) -> list[str]:
        if isinstance(v, list):
            return normalize_draft_competitors([str(x) for x in v])
        return []


@dataclass(frozen=True)
class ScheduleWindow:
    next_send_at: datetime | None
    next_send_display: str
    window_end_at: datetime | None
    anchor_date: str | None
    anchor_day: int | None


def _local_8am(year: int, month: int, day: int, tz: ZoneInfo) -> datetime:
    """Construct local 08:00 wall-clock time; fold=0 picks first occurrence on fall-back."""
    return datetime(year, month, day, DEFAULT_DELIVERY_HOUR, 0, 0, tzinfo=tz, fold=0)


def compute_next_send_window(
    *,
    cadence: CadenceType,
    timezone_name: str,
    now: datetime | None = None,
    anchor_day: int | None = None,
    anchor_date: str | None = None,
) -> ScheduleWindow:
    """Compute a deterministic proposed delivery window with explicit DST & month-end rules.

    - `paused`: returns None.
    - `weekly`: next Monday 08:00–10:00 local time.
    - `biweekly`: steps in 14-day local intervals from `anchor_date` (or next Monday if unset)
      so repeated calls do not drift across execution times or DST transitions.
    - `monthly`: uses `anchor_day` (defaulting to current local day) clamped to the last day of
      each month (e.g., 31st -> Feb 28 / Feb 29 leap year / Apr 30) at 08:00–10:00 local time.
    """
    tz_clean = validate_timezone(timezone_name)
    tz = ZoneInfo(tz_clean)
    now_utc = (now or datetime.now(UTC)).astimezone(UTC)
    now_local = now_utc.astimezone(tz)

    if cadence == "paused":
        return ScheduleWindow(
            next_send_at=None,
            next_send_display=f"Draft paused — no emails scheduled ({tz_clean})",
            window_end_at=None,
            anchor_date=anchor_date,
            anchor_day=anchor_day,
        )

    if cadence == "weekly":
        days_ahead = (0 - now_local.weekday()) % 7
        target_date = now_local.date() + timedelta(days=days_ahead)
        candidate = _local_8am(target_date.year, target_date.month, target_date.day, tz)
        if candidate <= now_local:
            target_date += timedelta(days=7)
            candidate = _local_8am(target_date.year, target_date.month, target_date.day, tz)
        end_local = candidate + timedelta(hours=DELIVERY_WINDOW_HOURS)
        return ScheduleWindow(
            next_send_at=candidate.astimezone(UTC),
            next_send_display=_format_window(candidate, end_local, tz_clean),
            window_end_at=end_local.astimezone(UTC),
            anchor_date=target_date.isoformat(),
            anchor_day=anchor_day,
        )

    if cadence == "biweekly":
        base_date = None
        if anchor_date:
            try:
                base_date = datetime.fromisoformat(anchor_date).date()
            except ValueError:
                base_date = None
        if base_date is None:
            days_ahead = (0 - now_local.weekday()) % 7
            base_date = now_local.date() + timedelta(days=days_ahead)
            if _local_8am(base_date.year, base_date.month, base_date.day, tz) <= now_local:
                base_date += timedelta(days=7)
        candidate = _local_8am(base_date.year, base_date.month, base_date.day, tz)
        while candidate <= now_local:
            base_date += timedelta(days=14)
            candidate = _local_8am(base_date.year, base_date.month, base_date.day, tz)
        end_local = candidate + timedelta(hours=DELIVERY_WINDOW_HOURS)
        return ScheduleWindow(
            next_send_at=candidate.astimezone(UTC),
            next_send_display=_format_window(candidate, end_local, tz_clean),
            window_end_at=end_local.astimezone(UTC),
            anchor_date=base_date.isoformat(),
            anchor_day=anchor_day,
        )

    # cadence == "monthly"
    eff_day = anchor_day if anchor_day is not None else now_local.day
    year, month = now_local.year, now_local.month
    clamped = min(eff_day, calendar.monthrange(year, month)[1])
    candidate = _local_8am(year, month, clamped, tz)
    if candidate <= now_local:
        if month == 12:
            year += 1
            month = 1
        else:
            month += 1
        clamped = min(eff_day, calendar.monthrange(year, month)[1])
        candidate = _local_8am(year, month, clamped, tz)
    end_local = candidate + timedelta(hours=DELIVERY_WINDOW_HOURS)
    return ScheduleWindow(
        next_send_at=candidate.astimezone(UTC),
        next_send_display=_format_window(candidate, end_local, tz_clean),
        window_end_at=end_local.astimezone(UTC),
        anchor_date=anchor_date,
        anchor_day=eff_day,
    )


def _format_window(start_local: datetime, end_local: datetime, tz_name: str) -> str:
    abbr = start_local.tzname() or tz_name
    day_str = start_local.strftime("%a, %b %d, %Y")
    start_t = start_local.strftime("%I:%M %p").lstrip("0")
    end_t = end_local.strftime("%I:%M %p").lstrip("0")
    return f"Proposed window: {day_str} · {start_t}–{end_t} {abbr} ({tz_name})"


def _extract_draft_prefs(doc: dict[str, Any]) -> DigestDraftPreferences:
    raw = doc.get(DRAFT_WORKSPACE_KEY)
    if isinstance(raw, dict):
        try:
            return DigestDraftPreferences.model_validate(raw)
        except Exception:
            pass
    # Seed competitors from seller's saved onboarding/memory if no draft yet.
    seeded: list[str] = []
    onb = doc.get("onboarding")
    if isinstance(onb, dict) and isinstance(onb.get("competitors"), list):
        for item in onb["competitors"]:
            url = (
                item
                if isinstance(item, str)
                else (item.get("url") if isinstance(item, dict) else "")
            )
            if url:
                try:
                    seeded.extend(normalize_draft_competitors([str(url)]))
                except ValueError:
                    continue
    return DigestDraftPreferences(competitors=seeded[:3])


def _subscription_banner_info(doc: dict[str, Any]) -> dict[str, Any]:
    """Report draft-only semantics cleanly without falsely claiming live subscription state."""
    return {
        "status": "unknown",
        "live_delivery_active": None,
        "draft_only": True,
        "note": (
            "Draft preview settings only. Saving here updates your workspace draft and does not "
            "subscribe, pause, or change any existing email delivery. Use the unsubscribe link in "
            "any email to stop active deliveries."
        ),
    }


async def load_digest_draft(
    account: AccountSession, *, now: datetime | None = None
) -> dict[str, Any]:
    ws = await load_workspace(account)
    doc = dict(ws.get("document") or {})
    prefs = _extract_draft_prefs(doc)
    win = compute_next_send_window(
        cadence=prefs.cadence,
        timezone_name=prefs.timezone,
        now=now,
        anchor_day=prefs.anchor_day,
        anchor_date=prefs.anchor_date,
    )
    return {
        "owner_id": account.user_id,
        "version": int(ws.get("version") or 0),
        "draft_preferences": prefs.model_dump(mode="json"),
        "next_send_at": win.next_send_at.isoformat() if win.next_send_at else None,
        "next_send_display": win.next_send_display,
        "subscription_state": _subscription_banner_info(doc),
    }


async def save_digest_draft(
    account: AccountSession,
    prefs: DigestDraftPreferences,
    *,
    expected_version: int | None,
    expected_owner: str | None,
    now: datetime | None = None,
) -> dict[str, Any]:
    ws = await load_workspace(account)
    doc = dict(ws.get("document") or {})
    existing_raw = doc.get(DRAFT_WORKSPACE_KEY)
    merged_draft = dict(existing_raw) if isinstance(existing_raw, dict) else {}

    win = compute_next_send_window(
        cadence=prefs.cadence,
        timezone_name=prefs.timezone,
        now=now,
        anchor_day=prefs.anchor_day,
        anchor_date=prefs.anchor_date,
    )
    if prefs.cadence == "biweekly" and not prefs.anchor_date:
        prefs = prefs.model_copy(update={"anchor_date": win.anchor_date})
    elif prefs.cadence == "monthly" and prefs.anchor_day is None:
        prefs = prefs.model_copy(update={"anchor_day": win.anchor_day})

    merged_draft.update(prefs.model_dump(mode="json"))
    next_doc = {**doc, DRAFT_WORKSPACE_KEY: merged_draft}
    saved = await save_workspace(account, next_doc, expected_version, expected_owner)
    return {
        "owner_id": saved["owner_id"],
        "version": int(saved["version"]),
        "draft_preferences": prefs.model_dump(mode="json"),
        "next_send_at": win.next_send_at.isoformat() if win.next_send_at else None,
        "next_send_display": win.next_send_display,
        "subscription_state": _subscription_banner_info(next_doc),
    }


async def _load_saved_snapshot_only(
    url: str,
    *,
    loader: SnapshotLoader | None,
) -> tuple[dict[str, Any] | None, bool]:
    """Read ONLY already-stored snapshots; never crawl and never use filesystem in Supabase mode."""
    key = _key(url)
    if loader is not None:
        try:
            return await loader(key), False
        except Exception as err:
            logger.warning("Saved snapshot read unavailable for preview: %s", type(err).__name__)
            return None, True
    store = SnapshotStore()
    try:
        return await store.get(key), False
    except (SupabaseError, ValueError, OSError) as err:
        # Never silently fall back to local disk when Supabase is configured.
        if configured():
            logger.warning("Hosted snapshot unavailable for preview: %s", type(err).__name__)
        return None, True


def _filter_changes_for_topics(changes: list[Any], topics: list[TopicType]) -> list[dict[str, Any]]:
    allowed_kinds: set[str] = set()
    if "listing_changes" in topics:
        allowed_kinds.update({"new_listing", "removed_listing"})
    if "pricing" in topics:
        allowed_kinds.add("price_change")
    if not allowed_kinds:
        return []
    filtered: list[dict[str, Any]] = []
    for c in changes:
        kind = getattr(c, "kind", None)
        if kind not in allowed_kinds:
            continue
        link = _safe_link(getattr(c, "url", None))
        title = str(getattr(c, "title", None) or link or "Listing")
        before = getattr(c, "before", None)
        after = getattr(c, "after", None)
        summary = title
        if kind == "price_change" and before is not None and after is not None:
            summary = f"{title} — {before} → {after}"
        filtered.append(
            {
                "kind": kind,
                "label": LABELS.get(kind, kind),
                "title": title,
                "summary": summary,
                "url": link,
            }
        )
    return filtered


def _render_preview_email(
    *,
    business_name: str,
    prefs: DigestDraftPreferences,
    win: ScheduleWindow,
    recommendation: dict[str, Any] | None,
    shop_summaries: list[dict[str, Any]],
    selected_changes: list[dict[str, Any]],
) -> tuple[str, str, str]:
    """Render mobile-friendly HTML and plain-text email preview with full escaping."""
    total_changes = len(selected_changes)
    if prefs.cadence == "paused":
        subject = f"[Preview — Draft paused] Personal digest for {business_name}"
    elif recommendation:
        subject = f"[Preview] {recommendation['title']}"
    elif total_changes:
        subject = (
            f"[Preview] {total_changes} saved competitor change{'s' if total_changes != 1 else ''}"
        )
    else:
        subject = f"[Preview] Personal digest for {business_name}"

    body: list[str] = []
    text: list[str] = [subject, ""]

    body.append(
        '<div style="margin:0 0 14px;padding:10px 12px;border-radius:8px;background:#fbf5e6;'
        'border:1px solid #e6d3a7;color:#6f480c;font-size:13px">'
        "<strong>Preview only:</strong> Draft schedule settings do not send, pause, or alter any "
        "existing email subscription.</div>"
    )
    body.append(
        f'<p style="margin:0 0 14px;font-size:13px;color:#536259">'
        f"<strong>{html.escape(win.next_send_display)}</strong></p>"
    )
    text.extend([f"Preview only: {win.next_send_display}", ""])

    if "suggested_moves" in prefs.topics and recommendation:
        rec_title = html.escape(str(recommendation["title"]))
        rec_reason = html.escape(str(recommendation["reason"]))
        fit_note = html.escape(str(recommendation["fit_note"]))
        body.append(
            '<div style="margin:0 0 18px;padding:14px;border-radius:10px;background:#e8f5ee;'
            'border-left:4px solid #1b6e44">'
            '<p style="margin:0 0 4px;font-size:11px;font-weight:700;letter-spacing:0.06em;'
            'text-transform:uppercase;color:#1b6e44">Top move for your shop</p>'
            f'<h2 style="margin:0 0 6px;font-size:18px;color:#181816">{rec_title}</h2>'
            f'<p style="margin:0 0 6px;font-size:14px;color:#22312b">{rec_reason}</p>'
            f'<p style="margin:0 0 10px;font-size:12px;color:#536259">{fit_note}</p>'
            '<a href="/portal" style="display:inline-block;background:#1b6e44;color:#fff;'
            "padding:10px 14px;border-radius:8px;text-decoration:none;font-weight:600;"
            'font-size:13px">Open My workspace →</a></div>'
        )
        text.extend(
            [
                f"TOP MOVE: {recommendation['title']}",
                str(recommendation["reason"]),
                str(recommendation["fit_note"]),
                "Open My workspace: /portal",
                "",
            ]
        )

    want_competitor_section = bool({"listing_changes", "pricing"} & set(prefs.topics))
    if want_competitor_section:
        body.append('<h2 style="font-size:16px;margin:18px 0 8px">Saved competitor updates</h2>')
        text.append("SAVED COMPETITOR UPDATES")
        if selected_changes:
            body.append('<ul style="margin:0 0 14px;padding-left:18px">')
            for ch in selected_changes[:MAX_PREVIEW_CHANGES]:
                label = html.escape(ch["label"])
                summary = html.escape(ch["summary"])
                shop_host = html.escape(ch.get("shop_host") or "")
                link = _safe_link(ch.get("url"))
                prefix = f"[{shop_host} · {label}] " if shop_host else f"[{label}] "
                if link:
                    body.append(
                        f'<li style="margin:0 0 6px">{prefix}'
                        f'<a href="{html.escape(link)}" style="color:#1b6e44">{summary}</a></li>'
                    )
                    text.append(f"- {ch['summary']} ({link})")
                else:
                    body.append(f'<li style="margin:0 0 6px">{prefix}{summary}</li>')
                    text.append(f"- {ch['summary']}")
            body.append("</ul>")
        elif not shop_summaries:
            msg = "No competitor shops added yet. Add up to 3 shops to include saved updates."
            body.append(f'<p style="margin:0 0 12px;color:#536259">{html.escape(msg)}</p>')
            text.append(msg)
        else:
            body.append('<ul style="margin:0 0 14px;padding-left:18px">')
            for s in shop_summaries:
                host = html.escape(s["host"])
                note = html.escape(s["status_note"])
                body.append(f'<li style="margin:0 0 6px"><strong>{host}:</strong> {note}</li>')
                text.append(f"- {s['host']}: {s['status_note']}")
            body.append("</ul>")
        text.append("")

    if not prefs.topics:
        msg = "All digest topics are currently unchecked. Select at least one topic to preview."
        body.append(f'<p style="margin:0 0 12px;color:#536259">{html.escape(msg)}</p>')
        text.append(msg)

    footer = (
        "Preview generated from your saved Muse workspace and stored snapshots (0 runs, "
        "0 crawls, 0 emails sent). Existing subscriptions remain managed via email "
        f"confirmation/unsubscribe. · {html.escape(_company_line())}"
    )
    text.extend(["", f"Cadence: {prefs.cadence} ({prefs.timezone})", _company_line()])
    return (
        subject,
        _wrap(f"Personal digest preview · {business_name}", "".join(body), footer),
        "\n".join(text),
    )


async def build_personal_digest_preview(
    account: AccountSession,
    *,
    overrides: DigestDraftPreferences | None = None,
    now: datetime | None = None,
    snapshot_loader: SnapshotLoader | None = None,
) -> dict[str, Any]:
    """Build a truthful, zero-cost personal digest preview from memory and saved snapshots."""
    now_utc = (now or datetime.now(UTC)).astimezone(UTC)
    ws = await load_workspace(account)
    doc = dict(ws.get("document") or {})
    prefs = overrides if overrides is not None else _extract_draft_prefs(doc)

    onb = doc.get("onboarding") if isinstance(doc.get("onboarding"), dict) else {}
    business_name = str(onb.get("business_name") or "").strip() or "Your Studio"
    product_name = str(onb.get("product_name") or "").strip() or None

    pref, voice, comps, signals = _extract_profile_parts(doc)

    # Recommendation tailored to approved seller memory (goal & minutes/week).
    recommendation: dict[str, Any] | None = None
    if "suggested_moves" in prefs.topics:
        ranked = rank_seller_recommendations(
            business_name=business_name,
            product_name=product_name,
            preferences=pref,
            voice_profile=voice,
            competitor_entries=comps,
            dismiss_signals=signals,
        )
        items = ranked.get("recommendations") or []
        if items:
            top = items[0]
            minutes = int(pref.access.minutes_per_week or 30)
            goal = str(pref.goal or "").strip()
            # Say whether the top move fits this week's minutes; when none fits, it is the shortest.
            move_minutes = int(top.get("estimated_minutes") or 0)
            fit_parts = [
                f"Takes about {move_minutes} minutes, more than your {minutes} minutes a week"
                if move_minutes > minutes
                else f"Fits your {minutes} minutes a week"
            ]
            if goal:
                fit_parts.append(f"Goal: {goal}")
            recommendation = {
                "id": str(top.get("id") or ""),
                "title": str(top.get("title") or "Share a grounded shop update"),
                "reason": str(top.get("why_this_fits") or top.get("reason") or ""),
                "fit_note": " · ".join(fit_parts),
                "workspace_href": "/portal",
            }

    # Read ONLY saved snapshots for this seller's watched shops (never crawl).
    shop_urls = list(prefs.competitors)
    if not shop_urls and comps:
        for c in comps:
            if c.url and c.url not in shop_urls:
                shop_urls.append(c.url)
            if len(shop_urls) >= 3:
                break

    shop_summaries: list[dict[str, Any]] = []
    collected_changes: list[dict[str, Any]] = []
    for url in shop_urls[:3]:
        host = urlsplit(url).hostname or url
        raw_snap, unavailable = await _load_saved_snapshot_only(url, loader=snapshot_loader)
        if unavailable:
            shop_summaries.append(
                {
                    "url": url,
                    "host": host,
                    "state": "unavailable",
                    "status_note": "Saved check is temporarily unavailable.",
                }
            )
            continue
        if not raw_snap or not isinstance(raw_snap.get("report"), dict):
            shop_summaries.append(
                {
                    "url": url,
                    "host": host,
                    "state": "never_checked",
                    "status_note": "Not checked yet — previews never crawl shops automatically.",
                }
            )
            continue

        captured_raw = raw_snap.get("captured")
        is_stale = False
        if isinstance(captured_raw, str):
            try:
                cap_dt = datetime.fromisoformat(captured_raw.replace("Z", "+00:00"))
                if cap_dt.tzinfo is None:
                    cap_dt = cap_dt.replace(tzinfo=UTC)
                is_stale = (now_utc - cap_dt) > STALE_SNAPSHOT_AFTER
            except ValueError:
                is_stale = False

        report = ShopReport.from_json(raw_snap["report"])
        if report.status == "error":
            shop_summaries.append(
                {
                    "url": url,
                    "host": host,
                    "state": "failed",
                    "status_note": "Last saved check could not read this shop's public pages.",
                }
            )
        elif report.status == "first":
            shop_summaries.append(
                {
                    "url": url,
                    "host": host,
                    "state": "baseline",
                    "status_note": "Baseline saved; changes appear after the next check.",
                }
            )
        elif report.status == "unchanged":
            note = "No changes found in the last saved check."
            if is_stale:
                note = "No changes in older saved check (stale — older than 14 days)."
            shop_summaries.append(
                {
                    "url": url,
                    "host": host,
                    "state": "stale" if is_stale else "unchanged",
                    "status_note": note,
                }
            )
        else:
            filtered = _filter_changes_for_topics(report.changes, prefs.topics)
            for ch in filtered:
                ch["shop_host"] = host
                collected_changes.append(ch)
            plural_s = "s" if len(filtered) != 1 else ""
            note = (
                f"{len(filtered)} matching change{plural_s} in last saved check."
                if filtered
                else "Saved check had no changes matching your selected topics."
            )
            if is_stale:
                note += " (Saved check is older than 14 days.)"
            shop_summaries.append(
                {
                    "url": url,
                    "host": host,
                    "state": "stale" if is_stale else "changed",
                    "status_note": note,
                }
            )

    selected_changes = collected_changes[:MAX_PREVIEW_CHANGES]
    win = compute_next_send_window(
        cadence=prefs.cadence,
        timezone_name=prefs.timezone,
        now=now_utc,
        anchor_day=prefs.anchor_day,
        anchor_date=prefs.anchor_date,
    )
    subject, body_html, body_text = _render_preview_email(
        business_name=business_name,
        prefs=prefs,
        win=win,
        recommendation=recommendation,
        shop_summaries=shop_summaries,
        selected_changes=selected_changes,
    )

    return {
        "owner_id": account.user_id,
        "draft_only": True,
        "sends_triggered": 0,
        "crawls_triggered": 0,
        "runs_used": 0,
        "cadence": prefs.cadence,
        "topics": prefs.topics,
        "timezone": prefs.timezone,
        "next_send_at": win.next_send_at.isoformat() if win.next_send_at else None,
        "next_send_display": win.next_send_display,
        "subject": subject,
        "html": body_html,
        "text": body_text,
        "recommendation": recommendation,
        "changes": selected_changes,
        "shops_status": shop_summaries,
        "subscription_state": _subscription_banner_info(doc),
    }
