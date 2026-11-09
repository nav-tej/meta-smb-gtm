"""Weekly competitor digest by email: double opt-in, signed links, one crawl per shop per week.

Subscribers pick 1 to 3 public competitor shop links. Once a week (Vercel Cron) each watched shop
is read with the same polite, SSRF-guarded crawler as the competitor monitor and compared with
last week's snapshot: new listings, removed listings and price changes. No Muse call is made, so
the digest costs no runs. Snapshots live in the private `muse-state` bucket (local files when
Supabase is not configured). Email goes through Resend; nothing is sent without a key.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import html
import json
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import urlencode, urlsplit

from src.clients import email
from src.clients.supabase import SupabaseError, configured, get_supabase_client
from src.config import get_settings
from src.services import competitor_monitor as monitor

logger = logging.getLogger(__name__)

BUCKET = "muse-state"
SNAPSHOT_PREFIX = "digest"
RECHECK_AFTER = timedelta(days=6)
MAX_SHOPS_PER_RUN = 30
CHECK_TIMEOUT_SECONDS = 45.0  # 30 shops, 8 at a time, fits Vercel's 300 s limit
MAX_ITEMS_PER_KIND = 5
FetchEntries = Callable[[str], Awaitable[list[Any]]]


class DigestError(Exception):
    def __init__(self, status_code: int, detail: str) -> None:
        self.status_code = status_code
        self.detail = detail
        super().__init__(detail)


def available() -> bool:
    """Sign-ups open only when mail can be sent, links can be signed and subscribers stored."""
    return email.enabled() and bool(get_settings().email_token_secret) and configured()


# ---------- input and signed links ----------


def normalize_shops(urls: list[str]) -> list[str]:
    shops: list[str] = []
    for raw in urls:
        value = (raw or "").strip()
        if not value:
            continue
        if "://" not in value:
            value = "https://" + value
        parts = urlsplit(value)
        if parts.scheme not in {"http", "https"} or not parts.hostname or len(value) > 300:
            raise DigestError(422, "Use public shop links that start with https://.")
        cleaned = f"{parts.scheme}://{parts.netloc}{parts.path}".rstrip("/") or value
        if cleaned not in shops:
            shops.append(cleaned)
    if not 1 <= len(shops) <= 3:
        raise DigestError(422, "Add 1 to 3 competitor shop links.")
    return shops


def _sign(*parts: str) -> str:
    secret = get_settings().email_token_secret.encode()
    message = "\x1f".join(parts).encode()
    return hmac.new(secret, message, hashlib.sha256).hexdigest()[:40]


def _pack(shops: list[str]) -> str:
    return base64.urlsafe_b64encode(json.dumps(shops).encode()).decode().rstrip("=")


def _unpack(value: str) -> list[str]:
    padded = value + "=" * (-len(value) % 4)
    shops = json.loads(base64.urlsafe_b64decode(padded.encode()))
    if not isinstance(shops, list) or not all(isinstance(s, str) for s in shops):
        raise ValueError("bad shop list")
    return normalize_shops(shops)


def confirm_url(subscriber_id: str, shops: list[str]) -> str:
    packed = _pack(shops)
    query = urlencode(
        {"id": subscriber_id, "c": packed, "t": _sign("confirm", subscriber_id, packed)}
    )
    return f"{get_settings().app_url.rstrip('/')}/api/v1/digest/confirm?{query}"


def unsubscribe_url(subscriber_id: str) -> str:
    query = urlencode({"id": subscriber_id, "t": _sign("unsubscribe", subscriber_id)})
    return f"{get_settings().app_url.rstrip('/')}/api/v1/digest/unsubscribe?{query}"


def verify_confirm(subscriber_id: str, packed: str, token: str) -> list[str] | None:
    if not hmac.compare_digest(_sign("confirm", subscriber_id, packed), token or ""):
        return None
    try:
        return _unpack(packed)
    except (ValueError, DigestError):
        return None


def verify_unsubscribe(subscriber_id: str, token: str) -> bool:
    return hmac.compare_digest(_sign("unsubscribe", subscriber_id), token or "")


# ---------- database ----------


async def _rpc(name: str, params: dict[str, Any]) -> dict[str, Any]:
    try:
        result = await get_supabase_client().rpc(name, params)
    except SupabaseError as err:
        raise DigestError(503, "Email digests are unavailable right now. Try again later.") from err
    if result.get("allowed") is not True:
        status = (
            result.get("status_code") if result.get("status_code") in {404, 409, 422, 429} else 503
        )
        raise DigestError(status, str(result.get("message") or "Request refused.")[:200])
    return result


# ---------- emails ----------


def _wrap(title: str, body_html: str, footer_html: str) -> str:
    return (
        '<!doctype html><html><body style="margin:0;background:#faf8f5;font-family:-apple-system,'
        'Segoe UI,Roboto,Helvetica,Arial,sans-serif;color:#22312b">'
        '<div style="max-width:600px;margin:0 auto;padding:28px 20px">'
        '<p style="margin:0 0 4px;color:#1b6e44;font-weight:700">Muse Growth Studio</p>'
        f'<h1 style="font-size:22px;margin:0 0 16px">{html.escape(title)}</h1>{body_html}'
        '<hr style="border:0;border-top:1px solid #e3ddd3;margin:28px 0 12px">'
        f'<p style="font-size:12px;color:#6b776f;line-height:1.6">{footer_html}</p>'
        "</div></body></html>"
    )


def _company_line() -> str:
    address = get_settings().email_postal_address.strip()
    return "Muse Growth Studio · n Plus Alpha LLC" + (f" · {address}" if address else "")


async def send_confirmation(to: str, subscriber_id: str, shops: list[str]) -> bool:
    link = confirm_url(subscriber_id, shops)
    listed = "".join(f"<li>{html.escape(s)}</li>" for s in shops)
    body = (
        "<p>Confirm your weekly competitor digest. Each Monday we check these shops' public "
        f"pages and email you what changed:</p><ul>{listed}</ul>"
        f'<p><a href="{html.escape(link)}" style="display:inline-block;background:#1b6e44;'
        'color:#fff;padding:12px 18px;border-radius:8px;text-decoration:none;font-weight:600">'
        "Confirm my digest</a></p><p>If you did not ask for this, ignore this email; nothing "
        "will be sent.</p>"
    )
    text = (
        "Confirm your weekly competitor digest for:\n"
        + "\n".join(f"- {s}" for s in shops)
        + f"\n\nConfirm: {link}\n\nIf you did not ask for this, ignore this email."
    )
    footer = html.escape(_company_line())
    return await email.send(
        to,
        "Confirm your weekly competitor digest",
        _wrap("One click to confirm", body, footer),
        text,
    )


async def subscribe(email_address: str, shops: list[str], ip_hash: str) -> None:
    """Record a pending subscription and send the confirmation email when due."""
    if not available():
        raise DigestError(503, "Email digests open soon.")
    shops = normalize_shops(shops)
    result = await _rpc(
        "muse_digest_subscribe",
        {"p_email": email_address, "p_competitors": shops, "p_ip_hash": ip_hash},
    )
    to = email_address.strip().lower()
    if result.get("send_confirm") and not await send_confirmation(to, str(result["id"]), shops):
        raise DigestError(503, "We could not send the confirmation email. Try again later.")


async def confirm(subscriber_id: str, packed: str, token: str) -> bool:
    shops = verify_confirm(subscriber_id, packed, token)
    if shops is None:
        return False
    try:
        await _rpc(
            "muse_digest_set_status",
            {"p_id": subscriber_id, "p_status": "active", "p_competitors": shops},
        )
    except DigestError as err:
        if err.status_code in {404, 409}:
            return False
        raise
    return True


async def unsubscribe(subscriber_id: str, token: str) -> bool:
    if not verify_unsubscribe(subscriber_id, token):
        return False
    try:
        await _rpc("muse_digest_set_status", {"p_id": subscriber_id, "p_status": "unsubscribed"})
    except DigestError as err:
        if err.status_code == 404:
            return True  # already gone: unsubscribing is idempotent
        raise
    return True


# ---------- weekly check ----------


@dataclass
class ShopReport:
    url: str
    status: str  # changed | unchanged | first | error
    pages_seen: int = 0
    changes: list[monitor.ListingChange] = field(default_factory=list)
    counts: dict[str, int] = field(default_factory=dict)

    def to_json(self) -> dict[str, Any]:
        return {
            "url": self.url,
            "status": self.status,
            "pages_seen": self.pages_seen,
            "changes": [c.model_dump(mode="json") for c in self.changes],
            "counts": self.counts,
        }

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> ShopReport:
        return cls(
            url=data["url"],
            status=data["status"],
            pages_seen=int(data.get("pages_seen") or 0),
            changes=[monitor.ListingChange.model_validate(c) for c in data.get("changes") or []],
            counts=dict(data.get("counts") or {}),
        )


class SnapshotStore:
    """Private bucket when Supabase is configured, else files next to the monitor's."""

    async def get(self, key: str) -> dict[str, Any] | None:
        if configured():
            data = await get_supabase_client().get_object(BUCKET, f"{SNAPSHOT_PREFIX}/{key}.json")
            return json.loads(data) if data else None
        path = monitor.monitor_dir() / SNAPSHOT_PREFIX / f"{key}.json"
        return json.loads(path.read_text()) if path.is_file() else None

    async def put(self, key: str, value: dict[str, Any]) -> None:
        data = json.dumps(value, separators=(",", ":")).encode()
        if configured():
            await get_supabase_client().put_object(
                BUCKET, f"{SNAPSHOT_PREFIX}/{key}.json", data, "application/json", upsert=True
            )
            return
        path = monitor.monitor_dir() / SNAPSHOT_PREFIX / f"{key}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)


def _key(url: str) -> str:
    return hashlib.sha256(url.encode()).hexdigest()[:32]


async def check_shop(
    url: str, store: SnapshotStore, fetch_entries: FetchEntries, now: datetime
) -> ShopReport:
    """This week's report for one shop: reused if checked in the last 6 days, else crawled."""
    try:
        previous = await store.get(_key(url))
    except (SupabaseError, ValueError, OSError):
        previous = None
    captured = monitor._parse_dt(previous.get("captured")) if previous else None
    if previous and captured and now - captured < RECHECK_AFTER and previous.get("report"):
        return ShopReport.from_json(previous["report"])
    try:
        raw = await asyncio.wait_for(fetch_entries(url), timeout=CHECK_TIMEOUT_SECONDS)
    except Exception as err:  # one shop failing must not stop the digest
        logger.warning("Digest check failed for a shop: %s", type(err).__name__)
        return ShopReport(url=url, status="error")
    current = [monitor._entry_dict(e) for e in raw]
    partial = len(current) >= monitor.CRAWL_MAX_URLS
    if previous and isinstance(previous.get("entries"), list):
        changes = monitor.diff_snapshots(previous, current, current_partial=partial)
        kept, counts = monitor._cap_changes(changes)
        report = ShopReport(url, "changed" if changes else "unchanged", len(current), kept, counts)
    else:
        report = ShopReport(url, "first", len(current))
    try:
        await store.put(
            _key(url),
            {
                "captured": now.isoformat(timespec="seconds"),
                "entries": current,
                "partial": partial,
                "report": report.to_json(),
            },
        )
    except (SupabaseError, OSError) as err:
        logger.warning("Digest snapshot not saved: %s", type(err).__name__)
    return report


def _safe_link(url: str | None) -> str | None:
    if not url:
        return None
    parts = urlsplit(url)
    return url if parts.scheme in {"http", "https"} and parts.hostname else None


LABELS = {
    "new_listing": "New listings",
    "price_change": "Price changes",
    "removed_listing": "Removed listings",
}


def render_digest(reports: list[ShopReport], subscriber_id: str, week: str) -> tuple[str, str, str]:
    """Subject, HTML and text for one subscriber's weekly email."""
    total = sum(sum(r.counts.values()) for r in reports)
    subject = (
        f"Competitor digest: {total} change{'s' if total != 1 else ''} this week"
        if total
        else "Competitor digest: no changes at your shops this week"
    )
    body: list[str] = []
    text: list[str] = [subject, ""]
    for report in reports:
        host = urlsplit(report.url).hostname or report.url
        body.append(f'<h2 style="font-size:17px;margin:22px 0 6px">{html.escape(host)}</h2>')
        text.append(host.upper())
        if report.status == "error":
            line = (
                "We could not read this shop's public pages this week (it may block automated "
                "checks). We will try again next week."
            )
        elif report.status == "first":
            line = (
                f"We started watching this shop: {report.pages_seen} public pages recorded. "
                "Changes show up from next week."
            )
        elif report.status == "unchanged":
            line = (
                f"No new listings, removals or price changes ({report.pages_seen} pages checked)."
            )
        else:
            line = ""
        if line:
            body.append(f'<p style="margin:0;color:#536259">{html.escape(line)}</p>')
            text += [line, ""]
            continue
        for kind, label in LABELS.items():
            items = [c for c in report.changes if c.kind == kind][:MAX_ITEMS_PER_KIND]
            if not items:
                continue
            count = report.counts.get(kind, len(items))
            body.append(f'<p style="margin:10px 0 4px;font-weight:600">{label} ({count})</p><ul>')
            text.append(f"{label} ({count})")
            for change in items:
                title = html.escape(change.title or change.url or "Listing")
                if change.kind == "price_change":
                    title += (
                        f" — {html.escape(str(change.before))} → {html.escape(str(change.after))}"
                    )
                link = _safe_link(change.url)
                body.append(
                    f'<li><a href="{html.escape(link)}" style="color:#1b6e44">{title}</a></li>'
                    if link
                    else f"<li>{title}</li>"
                )
                text.append(f"- {html.unescape(title)}" + (f" {link}" if link else ""))
            body.append("</ul>")
            text.append("")
    app = get_settings().app_url.rstrip("/")
    body.append(
        f'<p style="margin-top:22px"><a href="{html.escape(app)}/create" style="color:#1b6e44;'
        'font-weight:600">Turn this into a post in Muse →</a></p>'
    )
    leave = unsubscribe_url(subscriber_id)
    footer = (
        "You get this weekly because you confirmed a competitor digest at Muse Growth Studio. "
        "We only read public pages. "
        f'<a href="{html.escape(leave)}" style="color:#6b776f">Unsubscribe</a> · '
        f"{html.escape(_company_line())}"
    )
    text += [f"Make a post: {app}/create", "", f"Unsubscribe: {leave}", _company_line()]
    return subject, _wrap(f"Your shops this week ({week})", "".join(body), footer), "\n".join(text)


async def run_weekly(
    *,
    fetch_entries: FetchEntries | None = None,
    store: SnapshotStore | None = None,
    now: datetime | None = None,
) -> dict[str, int]:
    """Check every watched shop once and email each due subscriber. Safe to repeat."""
    summary = {"due": 0, "sent": 0, "failed": 0, "shops": 0}
    if not available():
        return summary
    now = now or datetime.now(UTC)
    store = store or SnapshotStore()
    fetcher = fetch_entries or monitor.crawl_entries
    due = (await _rpc("muse_digest_due", {"p_limit": 200})).get("subscribers") or []
    summary["due"] = len(due)
    shops = list(dict.fromkeys(url for sub in due for url in sub.get("competitors") or []))
    shops = shops[:MAX_SHOPS_PER_RUN]
    summary["shops"] = len(shops)
    semaphore = asyncio.Semaphore(8)

    async def checked(url: str) -> tuple[str, ShopReport]:
        async with semaphore:
            return url, await check_shop(url, store, fetcher, now)

    reports = dict(await asyncio.gather(*(checked(url) for url in shops)))
    week = now.strftime("%b %d")
    for sub in due:
        mine = [reports[u] for u in sub.get("competitors") or [] if u in reports]
        if not mine:
            continue  # over this run's shop cap: picked up by the next run
        subject, body, text = render_digest(mine, sub["id"], week)
        leave = unsubscribe_url(sub["id"])
        ok = await email.send(
            sub["email"],
            subject,
            body,
            text,
            headers={
                "List-Unsubscribe": f"<{leave}>",
                "List-Unsubscribe-Post": "List-Unsubscribe=One-Click",
            },
            idempotency_key=f"digest-{sub['id']}-{now:%G-W%V}",
        )
        if ok:
            summary["sent"] += 1
            try:
                await _rpc("muse_digest_mark_sent", {"p_id": sub["id"]})
            except DigestError:
                logger.warning("Digest sent but not marked; the idempotency key prevents a repeat.")
        else:
            summary["failed"] += 1
    return summary
