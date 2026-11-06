"""Weekly competitor monitor: diff each watched shop against its last snapshot, keep a change log.

No Muse call is made here. A check reads each competitor's public sitemap or profile page with
the same polite, SSRF-guarded crawler as Competitor Intel, compares it with the previous
snapshot (the saved Nov 3 snapshot on the first run), and records new listings, removed
listings and price updates. Ad changes are compared through the Meta Ad Library when
META_ADS_ACCESS_TOKEN is set; otherwise they are reported as not checked, never guessed.

Storage: MONITOR_DIR holds `changelog.json` (newest runs first) and `snapshots/<slug>.json`.
On Vercel this is /tmp, so the log and snapshots last per function instance and are lost on a
cold start (the next run then compares against the saved Nov 3 snapshot again).
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import tempfile
import time
from collections import Counter
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field

from src.config import get_settings
from src.models.intel import SitemapEntry

logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[2]
SAMPLES_DIR = REPO_ROOT / "data" / "samples"
MAX_RUNS_KEPT = 60
MAX_CHANGES_PER_KIND = 20
CRAWL_MAX_URLS = 300
CRAWL_TITLE_FETCHES = 8
CHECK_TIMEOUT_SECONDS = 120.0

# (name, url, where, saved snapshot file)
WATCHLIST: list[tuple[str, str, str, str]] = [
    ("SikhiArt.com", "https://www.sikhiart.com", "Own shop", "competitor_sikhiart.json"),
    (
        "Gurinderpreet Kaur",
        "https://fineartamerica.com/profiles/gurinderpreet-kaur/art/paintings",
        "Fine Art America",
        "competitor_gurinderpreet_kaur.json",
    ),
    (
        "Manjot Singh Sachdeva",
        "https://fineartamerica.com/profiles/manjot-singh-sachdeva/art/photographs",
        "Fine Art America / Pixels",
        "competitor_manjot_singh_sachdeva.json",
    ),
    (
        "Gurdish Pannu",
        "https://www.saatchiart.com/gurdishpannu",
        "Saatchi Art",
        "competitor_gurdish_pannu.json",
    ),
]

ChangeKind = Literal["new_listing", "removed_listing", "price_change", "ad_new", "ad_stopped"]
FetchEntries = Callable[[str], Awaitable[list[SitemapEntry]]]
FetchAds = Callable[[str], Awaitable[list[dict[str, str]]]]


class ListingChange(BaseModel):
    kind: ChangeKind
    url: str = ""
    title: str = ""
    before: str | None = None
    after: str | None = None


class CompetitorCheck(BaseModel):
    name: str
    url: str
    where: str
    status: Literal["changed", "unchanged", "error"]
    compared_with: str = Field(description="What this check was compared against.")
    pages_seen: int = 0
    partial: bool = Field(default=False, description="Crawl hit its URL cap; removals skipped.")
    changes: list[ListingChange] = Field(default_factory=list)
    counts: dict[str, int] = Field(default_factory=dict)
    ads_checked: bool = False
    ads_note: str = ""
    error: str | None = None


class MonitorRun(BaseModel):
    run_id: str
    checked_at: str
    trigger: Literal["manual", "cron", "test"] = "manual"
    competitors: list[CompetitorCheck] = Field(default_factory=list)
    total_changes: int = 0


class ChangeLog(BaseModel):
    runs: list[MonitorRun] = Field(default_factory=list)
    last_checked_at: str | None = None
    persistent: bool = True
    note: str = ""


class DigestCompetitor(BaseModel):
    name: str
    changes: int
    counts: dict[str, int] = Field(default_factory=dict)
    highlights: list[str] = Field(default_factory=list)


class WeeklyDigest(BaseModel):
    week_start: str
    week_end: str
    checks: int
    total_changes: int
    by_kind: dict[str, int] = Field(default_factory=dict)
    competitors: list[DigestCompetitor] = Field(default_factory=list)
    highlights: list[str] = Field(default_factory=list)
    note: str = ""


# ---------- storage ----------


def monitor_dir() -> Path:
    configured = Path(get_settings().monitor_dir)
    return configured if configured.is_absolute() else REPO_ROOT / configured


def _slug(url: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", url.lower().split("://")[-1]).strip("-")[:80]


def _atomic_write(path: Path, data: Any) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".tmp-", suffix=".json")
        with os.fdopen(fd, "w") as handle:
            json.dump(data, handle, separators=(",", ":"))
        os.replace(tmp, path)
    except OSError as err:
        logger.warning("Monitor write skipped for %s: %s", path.name, type(err).__name__)


def _read_json(path: Path) -> Any | None:
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return None


def load_changelog() -> ChangeLog:
    raw = _read_json(monitor_dir() / "changelog.json")
    runs: list[MonitorRun] = []
    if isinstance(raw, dict) and isinstance(raw.get("runs"), list):
        for item in raw["runs"]:
            try:
                runs.append(MonitorRun.model_validate(item))
            except ValueError:
                continue
    hosted = get_settings().hosted_environment
    return ChangeLog(
        runs=runs,
        last_checked_at=runs[0].checked_at if runs else None,
        persistent=not hosted,
        note=(
            "Monitor history is kept per server instance on the hosted demo and can reset."
            if hosted
            else ""
        ),
    )


def _save_run(run: MonitorRun) -> None:
    log = load_changelog()
    runs = [run, *log.runs][:MAX_RUNS_KEPT]
    _atomic_write(
        monitor_dir() / "changelog.json",
        {"runs": [r.model_dump(mode="json") for r in runs]},
    )


def seconds_since_last_run(now: float | None = None) -> float | None:
    log = load_changelog()
    if not log.last_checked_at:
        return None
    try:
        last = datetime.fromisoformat(log.last_checked_at).timestamp()
    except ValueError:
        return None
    return (now or time.time()) - last


# ---------- snapshots ----------


def _entry_dict(entry: SitemapEntry | dict[str, Any]) -> dict[str, Any]:
    if isinstance(entry, SitemapEntry):
        entry = entry.model_dump(mode="json")
    return {
        "loc": str(entry.get("loc") or ""),
        "title": entry.get("title"),
        "price_hint": entry.get("price_hint"),
        "bucket": entry.get("bucket") or "other",
        "lastmod": entry.get("lastmod"),
    }


def _baseline(url: str, sample_file: str) -> tuple[dict[str, Any], str]:
    """The previous snapshot for this competitor: the last stored run, else the saved sample."""
    stored = _read_json(monitor_dir() / "snapshots" / f"{_slug(url)}.json")
    if isinstance(stored, dict) and isinstance(stored.get("entries"), list):
        return stored, f"last check {str(stored.get('captured', ''))[:16]}"
    sample = _read_json(SAMPLES_DIR / sample_file) or {}
    entries = sample.get("entries") if isinstance(sample, dict) else None
    crawl = sample.get("crawl") if isinstance(sample, dict) else None
    max_urls = crawl.get("max_urls") if isinstance(crawl, dict) else None
    snapshot = {
        "captured": sample.get("captured", "2026-11-03") if isinstance(sample, dict) else "",
        "entries": [_entry_dict(e) for e in entries or [] if isinstance(e, dict)],
        "partial": bool(max_urls and len(entries or []) >= max_urls),
        "ads": None,
    }
    return snapshot, f"saved snapshot {snapshot['captured']}"


def _norm_loc(loc: str) -> str:
    return loc.strip().lower().split("://")[-1].removeprefix("www.").split("?")[0].rstrip("/")


def _norm_price(price: object) -> str:
    return re.sub(r"\s+", "", str(price or "")).lower()


def _parse_dt(value: object) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def _title(entry: dict[str, Any]) -> str:
    title = str(entry.get("title") or "").split("|")[0].strip()
    return title[:140] or entry.get("loc", "")


def diff_snapshots(
    baseline: dict[str, Any], current: list[dict[str, Any]], *, current_partial: bool
) -> list[ListingChange]:
    """New listings, removed listings and price updates between two snapshots."""
    before = {_norm_loc(e["loc"]): e for e in baseline.get("entries", []) if e.get("loc")}
    after = {_norm_loc(e["loc"]): e for e in current if e.get("loc")}
    captured = _parse_dt(baseline.get("captured"))
    either_partial = current_partial or bool(baseline.get("partial"))
    changes: list[ListingChange] = []

    for key, entry in after.items():
        if key in before:
            continue
        lastmod = _parse_dt(entry.get("lastmod"))
        # With a truncated crawl, an unseen URL may just be an old page outside the cap, so
        # only count it as new when its lastmod is after the previous snapshot.
        if either_partial and not (lastmod and captured and lastmod > captured):
            continue
        changes.append(
            ListingChange(
                kind="new_listing",
                url=entry["loc"],
                title=_title(entry),
                after=entry.get("price_hint"),
            )
        )
    if not either_partial:
        for key, entry in before.items():
            if key not in after:
                changes.append(
                    ListingChange(kind="removed_listing", url=entry["loc"], title=_title(entry))
                )
    for key, entry in after.items():
        old = before.get(key)
        if not old or not old.get("price_hint") or not entry.get("price_hint"):
            continue
        if _norm_price(old["price_hint"]) != _norm_price(entry["price_hint"]):
            changes.append(
                ListingChange(
                    kind="price_change",
                    url=entry["loc"],
                    title=_title(entry),
                    before=str(old["price_hint"]),
                    after=str(entry["price_hint"]),
                )
            )
    return changes


def diff_ads(previous: list[dict[str, str]] | None, current: list[dict[str, str]]):
    """Ad Library changes; the first check only records a baseline."""
    if previous is None:
        return []
    old = {a["id"]: a for a in previous if a.get("id")}
    new = {a["id"]: a for a in current if a.get("id")}
    changes = [
        ListingChange(kind="ad_new", title=a.get("headline", "") or a["id"], url=a["id"])
        for i, a in new.items()
        if i not in old
    ]
    changes += [
        ListingChange(kind="ad_stopped", title=a.get("headline", "") or a["id"], url=a["id"])
        for i, a in old.items()
        if i not in new
    ]
    return changes


def _cap_changes(changes: list[ListingChange]) -> tuple[list[ListingChange], dict[str, int]]:
    counts = Counter(c.kind for c in changes)
    kept: list[ListingChange] = []
    per_kind: Counter[str] = Counter()
    for change in changes:
        if per_kind[change.kind] < MAX_CHANGES_PER_KIND:
            kept.append(change)
            per_kind[change.kind] += 1
    return kept, dict(counts)


# ---------- live fetchers (replaced in tests) ----------


async def crawl_entries(url: str) -> list[SitemapEntry]:
    from src.services.competitor_intel import collect_entries

    entries, _ = await collect_entries(
        url,
        fetch_titles=True,
        max_urls=CRAWL_MAX_URLS,
        max_title_fetches=CRAWL_TITLE_FETCHES,
    )
    return entries


async def ad_library_ads(name: str) -> list[dict[str, str]]:
    from src.clients.ad_library import MetaAdLibraryClient

    client = MetaAdLibraryClient()
    try:
        signals = await client.search_active_ads(name, limit=25)
    finally:
        await client.aclose()
    return [{"id": ad.ad_id, "headline": ad.headline} for ad in signals.top_longevity_ads]


# ---------- run ----------


async def _check_one(
    name: str,
    url: str,
    where: str,
    sample_file: str,
    fetch_entries: FetchEntries,
    fetch_ads: FetchAds | None,
    checked_at: str,
) -> CompetitorCheck:
    baseline, compared_with = _baseline(url, sample_file)
    try:
        raw = await asyncio.wait_for(fetch_entries(url), timeout=CHECK_TIMEOUT_SECONDS)
    except Exception as err:  # one shop failing must not stop the others
        logger.warning("Monitor check failed for %s: %s", name, type(err).__name__)
        return CompetitorCheck(
            name=name,
            url=url,
            where=where,
            status="error",
            compared_with=compared_with,
            error=(
                "Could not read this shop's public pages (it may block automated checks). "
                "It will be tried again next run."
            ),
        )
    current = [_entry_dict(e) for e in raw]
    partial = len(current) >= CRAWL_MAX_URLS
    changes = diff_snapshots(baseline, current, current_partial=partial)

    ads_checked, ads_note, current_ads = False, "", None
    if fetch_ads is None:
        ads_note = "Ad changes not checked: no Meta Ad Library token is configured."
    else:
        try:
            current_ads = await fetch_ads(name)
            changes += diff_ads(baseline.get("ads"), current_ads)
            ads_checked = True
            if baseline.get("ads") is None:
                ads_note = f"First ad check: {len(current_ads)} active ads recorded."
        except Exception as err:
            logger.warning("Ad Library check failed for %s: %s", name, type(err).__name__)
            ads_note = "Ad Library check failed this run; ads will be checked next run."

    _atomic_write(
        monitor_dir() / "snapshots" / f"{_slug(url)}.json",
        {
            "captured": checked_at,
            "entries": current,
            "partial": partial,
            "ads": current_ads if current_ads is not None else baseline.get("ads"),
        },
    )
    kept, counts = _cap_changes(changes)
    return CompetitorCheck(
        name=name,
        url=url,
        where=where,
        status="changed" if changes else "unchanged",
        compared_with=compared_with,
        pages_seen=len(current),
        partial=partial,
        changes=kept,
        counts=counts,
        ads_checked=ads_checked,
        ads_note=ads_note,
    )


async def run_monitor(
    *,
    trigger: Literal["manual", "cron", "test"] = "manual",
    fetch_entries: FetchEntries | None = None,
    fetch_ads: FetchAds | None = None,
) -> MonitorRun:
    """Check every watched competitor once, store the run in the change log and return it."""
    entries_fetcher = fetch_entries or crawl_entries
    ads_fetcher = fetch_ads
    if ads_fetcher is None and get_settings().meta_ads_access_token.strip():
        ads_fetcher = ad_library_ads
    checked_at = datetime.now(UTC).isoformat(timespec="seconds")
    checks = await asyncio.gather(
        *(
            _check_one(name, url, where, sample, entries_fetcher, ads_fetcher, checked_at)
            for name, url, where, sample in WATCHLIST
        )
    )
    run = MonitorRun(
        run_id=uuid4().hex[:12],
        checked_at=checked_at,
        trigger=trigger,
        competitors=list(checks),
        total_changes=sum(sum(c.counts.values()) for c in checks),
    )
    _save_run(run)
    return run


# ---------- digests ----------

KIND_LABEL = {
    "new_listing": "new listing",
    "removed_listing": "removed listing",
    "price_change": "price update",
    "ad_new": "new ad",
    "ad_stopped": "stopped ad",
}


def describe(change: ListingChange, competitor: str) -> str:
    if change.kind == "price_change":
        return f"{competitor} changed the price of {change.title}: {change.before} → {change.after}"
    if change.kind == "new_listing":
        price = f" ({change.after})" if change.after else ""
        return f"{competitor} added {change.title}{price}"
    if change.kind == "removed_listing":
        return f"{competitor} removed {change.title}"
    if change.kind == "ad_new":
        return f"{competitor} started an ad: {change.title}"
    return f"{competitor} stopped an ad: {change.title}"


def changes_since(since: datetime) -> list[tuple[str, ListingChange, str]]:
    """(competitor, change, checked_at) from runs at or after `since`, newest first."""
    found: list[tuple[str, ListingChange, str]] = []
    for run in load_changelog().runs:
        checked = _parse_dt(run.checked_at)
        if checked is None or checked < since:
            continue
        for check in run.competitors:
            found.extend((check.name, change, run.checked_at) for change in check.changes)
    return found


def weekly_digest(now: datetime | None = None) -> WeeklyDigest:
    """Roll the last 7 days of monitor runs into one digest. No crawl, no model call."""
    end = now or datetime.now(UTC)
    start = end - timedelta(days=7)
    runs = [
        r
        for r in load_changelog().runs
        if (checked := _parse_dt(r.checked_at)) is not None and start <= checked <= end
    ]
    by_kind: Counter[str] = Counter()
    per_competitor: dict[str, DigestCompetitor] = {}
    highlights: list[str] = []
    for run in runs:
        for check in run.competitors:
            item = per_competitor.setdefault(
                check.name, DigestCompetitor(name=check.name, changes=0)
            )
            for kind, count in check.counts.items():
                by_kind[kind] += count
                item.counts[kind] = item.counts.get(kind, 0) + count
                item.changes += count
            for change in check.changes[:3]:
                line = describe(change, check.name)
                if line not in item.highlights and len(item.highlights) < 3:
                    item.highlights.append(line)
    priority = {"price_change": 0, "new_listing": 1, "ad_new": 2, "ad_stopped": 3}
    ranked = sorted(
        (
            (priority.get(c.kind, 4), describe(c, name))
            for name, c, _ in changes_since(start)
            if c.kind != "removed_listing"
        ),
        key=lambda pair: pair[0],
    )
    for _, line in ranked:
        if line not in highlights:
            highlights.append(line)
        if len(highlights) == 5:
            break
    if not runs:
        note = "No monitor checks ran in the last 7 days. Run a check to start the change log."
    elif not by_kind:
        note = f"{len(runs)} check(s) this week found no changes at the shops you watch."
    else:
        note = f"{len(runs)} check(s) this week compared each shop with its previous snapshot."
    return WeeklyDigest(
        week_start=start.date().isoformat(),
        week_end=end.date().isoformat(),
        checks=len(runs),
        total_changes=sum(by_kind.values()),
        by_kind=dict(by_kind),
        competitors=sorted(per_competitor.values(), key=lambda c: -c.changes),
        highlights=highlights,
        note=note,
    )
