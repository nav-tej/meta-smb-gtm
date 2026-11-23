"""Own-workspace competitor watchlist checks and snapshot diffing.

Crawls up to 6 selected competitors from a seller's workspace using the guarded
public sitemap crawler (`scan_guard.crawl` + `collect_entries`), compares each
site against the seller's previous saved snapshot, and returns honest, capped
diff summaries. Zero Muse calls and zero runs used.
"""

from __future__ import annotations

import re
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any, Literal
from urllib.parse import urlsplit, urlunsplit

from src.models.intel import SitemapEntry
from src.services import scan_guard

MAX_COMPETITORS_PER_CHECK = 6
MAX_PAGES_PER_COMPETITOR = 30
MAX_STORED_PAGES_PER_COMPETITOR = 30
MAX_CHANGES_PER_KIND = 15
MAX_TITLE_LENGTH = 140
MAX_PRICE_HINT_LENGTH = 40
MAX_URL_LENGTH = 500


def normalize_competitor_url(raw_url: str) -> str:
    """Normalize a competitor URL to a stable key (lowercase scheme/host, no trailing slash)."""
    cleaned = (raw_url or "").strip()
    if not cleaned:
        return ""
    if "://" not in cleaned:
        cleaned = f"https://{cleaned.lstrip('@')}"
    parts = urlsplit(cleaned)
    scheme = (parts.scheme or "https").lower()
    netloc = parts.netloc.lower()
    path = parts.path.rstrip("/")
    return urlunsplit((scheme, netloc, path, parts.query, ""))[:MAX_URL_LENGTH]


def _title_from_url(url: str) -> str:
    parts = urlsplit(url)
    segments = [seg for seg in parts.path.split("/") if seg]
    if not segments:
        return (parts.hostname or url)[:MAX_TITLE_LENGTH]
    slug = re.sub(r"\.[a-z0-9]{2,5}$", "", segments[-1], flags=re.IGNORECASE)
    words = re.sub(r"[-_]+", " ", slug).strip()
    if not words:
        return (parts.hostname or url)[:MAX_TITLE_LENGTH]
    return words[:MAX_TITLE_LENGTH].strip().title()


def extract_selected_competitors(doc: dict[str, Any]) -> list[dict[str, str]]:
    """Extract up to 6 selected competitors from workspace preferences (or onboarding fallback)."""
    prefs = doc.get("preferences") if isinstance(doc.get("preferences"), dict) else {}
    onb = doc.get("onboarding") if isinstance(doc.get("onboarding"), dict) else {}

    raw_list: list[Any] = []
    pref_entries = prefs.get("competitor_entries")
    if isinstance(pref_entries, list) and pref_entries:
        raw_list = pref_entries
    elif isinstance(onb.get("competitors"), list):
        raw_list = onb.get("competitors") or []

    seen: set[str] = set()
    selected: list[dict[str, str]] = []
    for item in raw_list:
        if isinstance(item, str):
            raw_url = item.strip()
            name = ""
            is_selected = True
        elif isinstance(item, dict):
            is_selected = item.get("selected", True) is not False
            raw_url = str(item.get("url") or "").strip()
            name = str(item.get("name") or "").strip()
        else:
            continue
        if not is_selected or not raw_url:
            continue
        norm = normalize_competitor_url(raw_url)
        if not norm or norm in seen:
            continue
        seen.add(norm)
        host = (urlsplit(norm).hostname or norm).removeprefix("www.")
        selected.append(
            {
                "name": (name or host)[:MAX_TITLE_LENGTH],
                "url": norm,
            }
        )
        if len(selected) >= MAX_COMPETITORS_PER_CHECK:
            break
    return selected


def entries_to_snapshot_pages(entries: list[SitemapEntry]) -> list[dict[str, str]]:
    """Convert crawled SitemapEntry objects into a capped, compact snapshot list."""
    pages: list[dict[str, str]] = []
    seen_locs: set[str] = set()
    for entry in entries:
        loc = normalize_competitor_url(str(getattr(entry, "loc", "") or ""))
        if not loc or loc in seen_locs:
            continue
        seen_locs.add(loc)
        raw_title = str(getattr(entry, "title", "") or "").strip()
        title = (raw_title or _title_from_url(loc))[:MAX_TITLE_LENGTH]
        raw_price = str(getattr(entry, "price_hint", "") or "").strip()
        price_hint = raw_price[:MAX_PRICE_HINT_LENGTH]
        lastmod = getattr(entry, "lastmod", None)
        pages.append(
            {
                "loc": loc,
                "title": title,
                "price_hint": price_hint,
                # Date only: on a site bigger than the window it is the only proof a page is new.
                "lastmod": lastmod.date().isoformat() if isinstance(lastmod, datetime) else "",
            }
        )
        if len(pages) >= MAX_STORED_PAGES_PER_COMPETITOR:
            break
    return pages


def classify_check_error(err: Exception | str, *, blocked_host: bool = False) -> tuple[str, str]:
    """Return `(error_kind, plain_seller_message)` for a failed competitor crawl."""
    if blocked_host:
        return ("blocked", "This site blocks automated reading.")
    text = str(err or "").lower()
    if any(tok in text for tok in ("timeout", "timed out", "readtimeout", "connecttimeout")):
        return ("timeout", "This site took too long to respond.")
    if any(tok in text for tok in ("403", "401", "forbidden", "blocked", "cloudflare", "captcha")):
        return ("blocked", "This site blocks automated reading.")
    if any(tok in text for tok in ("no sitemap", "not found", "404", "no urls", "empty")):
        return ("no_sitemap", "No public sitemap or readable pages were found.")
    return ("unreachable", "This site could not be read right now.")


def _format_short_date(iso_str: str) -> str:
    try:
        dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        return dt.strftime("%b %d").replace(" 0", " ")
    except Exception:
        return ""


def diff_competitor_pages(
    previous_snapshot: dict[str, Any] | None,
    current_pages: list[dict[str, str]],
    *,
    name: str,
    url: str,
    checked_at: str,
    truncated: bool = False,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Diff `current_pages` against `previous_snapshot`.

    `truncated` means the crawl stopped at the page cap, so the site is bigger than what Muse
    read. Then the window can shift between checks: a page missing from it may still exist and
    a page entering it may be old. Such a check never counts removed pages and counts a page as
    new only when the sitemap dates it on or after the previous check (`partial` in the result).

    Returns `(result_item, stored_snapshot)` where:
    - `result_item` is shaped for both `/digest` and `muse-shell.js`'s `competitorStatus()`
      (`name`, `url`, `status`, `checked_at`, `compared_with`, `counts`, `new_pages`,
      `removed_pages`, `price_changes`, `page_count`, `summary`, `error`, `error_kind`).
    - `stored_snapshot` is the compact dict persisted under `preferences.competitor_checks[url]`.
    """
    prev_pages_raw = (
        previous_snapshot.get("pages")
        if isinstance(previous_snapshot, dict) and isinstance(previous_snapshot.get("pages"), list)
        else None
    )
    prev_checked_at = (
        str(previous_snapshot.get("checked_at") or "")
        if isinstance(previous_snapshot, dict)
        else ""
    )

    # First check: no prior baseline pages stored yet.
    if prev_pages_raw is None:
        page_count = len(current_pages)
        known = (
            f"Muse saved {page_count} of their pages (they have more)"
            if truncated
            else f"Muse now knows {page_count} of their pages"
        )
        summary = f"First check: {known}. Changes show from the next check."
        counts = {"new_listing": 0, "removed_listing": 0, "price_change": 0}
        result_item = {
            "name": name,
            "url": url,
            "status": "first_check",
            "checked_at": checked_at,
            "compared_with": "",
            "counts": counts,
            "new_pages": [],
            "removed_pages": [],
            "price_changes": [],
            "page_count": page_count,
            "partial": truncated,
            "summary": summary,
            "error": "",
            "error_kind": "",
        }
        stored_snapshot = {
            "name": name,
            "url": url,
            "checked_at": checked_at,
            "compared_with": "",
            "status": "first_check",
            "partial": truncated,
            "page_count": page_count,
            "counts": counts,
            "new_pages": [],
            "removed_pages": [],
            "price_changes": [],
            "summary": summary,
            "error": "",
            "error_kind": "",
            "pages": current_pages[:MAX_STORED_PAGES_PER_COMPETITOR],
        }
        return result_item, stored_snapshot

    prev_by_loc: dict[str, dict[str, str]] = {}
    for p in prev_pages_raw:
        if not isinstance(p, dict):
            continue
        loc = normalize_competitor_url(str(p.get("loc") or ""))
        if loc:
            prev_by_loc[loc] = {
                "loc": loc,
                "title": str(p.get("title") or "")[:MAX_TITLE_LENGTH],
                "price_hint": str(p.get("price_hint") or "")[:MAX_PRICE_HINT_LENGTH],
            }

    curr_by_loc: dict[str, dict[str, str]] = {p["loc"]: p for p in current_pages if p.get("loc")}

    # A full previous window (an older snapshot has no `partial` flag) means the site was
    # bigger than the window then too.
    partial = truncated or len(prev_by_loc) >= MAX_STORED_PAGES_PER_COMPETITOR
    since_day = prev_checked_at[:10]

    def _counts_as_new(page: dict[str, str]) -> bool:
        if not partial:
            return True
        lastmod = str(page.get("lastmod") or "")
        return bool(lastmod and since_day and lastmod >= since_day)

    all_new: list[dict[str, str]] = [
        {
            "loc": loc,
            "title": curr["title"],
            "price_hint": curr["price_hint"],
        }
        for loc, curr in curr_by_loc.items()
        if loc not in prev_by_loc and _counts_as_new(curr)
    ]
    all_removed: list[dict[str, str]] = (
        []
        if partial
        else [
            {
                "loc": loc,
                "title": prev["title"],
                "price_hint": prev["price_hint"],
            }
            for loc, prev in prev_by_loc.items()
            if loc not in curr_by_loc
        ]
    )
    all_price_changes: list[dict[str, str]] = []
    for loc, curr in curr_by_loc.items():
        if loc not in prev_by_loc:
            continue
        old_price = prev_by_loc[loc].get("price_hint", "").strip()
        new_price = curr.get("price_hint", "").strip()
        # A price Muse could not read this time is not a change (same rule as the monitor's
        # diff_snapshots): both checks must show a price, and spacing or case alone is no change.
        if not old_price or not new_price:
            continue
        if re.sub(r"\s+", "", old_price).lower() != re.sub(r"\s+", "", new_price).lower():
            all_price_changes.append(
                {
                    "loc": loc,
                    "title": curr["title"] or prev_by_loc[loc]["title"],
                    "old_price": old_price,
                    "new_price": new_price,
                }
            )

    counts = {
        "new_listing": len(all_new),
        "removed_listing": len(all_removed),
        "price_change": len(all_price_changes),
    }
    total_changes = counts["new_listing"] + counts["removed_listing"] + counts["price_change"]
    status = "changed" if total_changes > 0 else "unchanged"

    parts: list[str] = []
    if counts["new_listing"]:
        n = counts["new_listing"]
        new_word = "new or updated" if partial else "new"
        parts.append(f"{n} {new_word} {'page' if n == 1 else 'pages'}")
    if counts["price_change"]:
        n = counts["price_change"]
        parts.append(f"{n} price {'change' if n == 1 else 'changes'}")
    if counts["removed_listing"]:
        n = counts["removed_listing"]
        parts.append(f"{n} removed {'page' if n == 1 else 'pages'}")

    since = _format_short_date(prev_checked_at)
    if parts:
        summary = f"Found {', '.join(parts)}" + (f" since {since}." if since else ".")
    else:
        summary = f"No changes since {since}." if since else "No changes since the last check."
    if partial:
        summary += (
            f" They have more than {MAX_STORED_PAGES_PER_COMPETITOR} pages, so Muse counts only "
            "pages dated since your last check and does not report removed pages."
        )

    new_capped = all_new[:MAX_CHANGES_PER_KIND]
    removed_capped = all_removed[:MAX_CHANGES_PER_KIND]
    price_capped = all_price_changes[:MAX_CHANGES_PER_KIND]

    result_item = {
        "name": name,
        "url": url,
        "status": status,
        "checked_at": checked_at,
        "compared_with": prev_checked_at,
        "counts": counts,
        "new_pages": new_capped,
        "removed_pages": removed_capped,
        "price_changes": price_capped,
        "page_count": len(current_pages),
        "partial": partial,
        "summary": summary,
        "error": "",
        "error_kind": "",
    }
    stored_snapshot = {
        "name": name,
        "url": url,
        "checked_at": checked_at,
        "compared_with": prev_checked_at,
        "status": status,
        "partial": partial,
        "page_count": len(current_pages),
        "counts": counts,
        "new_pages": new_capped,
        "removed_pages": removed_capped,
        "price_changes": price_capped,
        "summary": summary,
        "error": "",
        "error_kind": "",
        "pages": current_pages[:MAX_STORED_PAGES_PER_COMPETITOR],
    }
    return result_item, stored_snapshot


def error_competitor_result(
    previous_snapshot: dict[str, Any] | None,
    *,
    name: str,
    url: str,
    checked_at: str,
    error_kind: str,
    error_message: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Build an error result while preserving any prior baseline `pages` snapshot."""
    counts = {"new_listing": 0, "removed_listing": 0, "price_change": 0}
    result_item = {
        "name": name,
        "url": url,
        "status": "error",
        "checked_at": checked_at,
        "compared_with": (
            str(previous_snapshot.get("checked_at") or "")
            if isinstance(previous_snapshot, dict)
            else ""
        ),
        "counts": counts,
        "new_pages": [],
        "removed_pages": [],
        "price_changes": [],
        "page_count": (
            int(previous_snapshot.get("page_count") or 0)
            if isinstance(previous_snapshot, dict)
            else 0
        ),
        "summary": error_message,
        "error": error_message,
        "error_kind": error_kind,
    }
    stored_snapshot: dict[str, Any] = {
        "name": name,
        "url": url,
        "checked_at": checked_at,
        "compared_with": result_item["compared_with"],
        "status": "error",
        "page_count": result_item["page_count"],
        "counts": counts,
        "new_pages": [],
        "removed_pages": [],
        "price_changes": [],
        "summary": error_message,
        "error": error_message,
        "error_kind": error_kind,
    }
    if isinstance(previous_snapshot, dict) and isinstance(previous_snapshot.get("pages"), list):
        stored_snapshot["pages"] = previous_snapshot["pages"][:MAX_STORED_PAGES_PER_COMPETITOR]
    return result_item, stored_snapshot


def compute_top_insight(competitors: list[dict[str, Any]], checked_at: str) -> dict[str, str]:
    """Summarize the biggest real change across checked competitors (never 'Watching N')."""
    best_item: dict[str, Any] | None = None
    best_total = 0
    for item in competitors:
        counts = item.get("counts") or {}
        total = (
            int(counts.get("new_listing") or 0)
            + int(counts.get("price_change") or 0)
            + int(counts.get("removed_listing") or 0)
        )
        if total > best_total:
            best_total = total
            best_item = item

    if best_item is not None and best_total > 0:
        name = str(best_item.get("name") or "A competitor")
        counts = best_item.get("counts") or {}
        n_new = int(counts.get("new_listing") or 0)
        n_price = int(counts.get("price_change") or 0)
        n_rem = int(counts.get("removed_listing") or 0)
        if n_new >= n_price and n_new >= n_rem and n_new > 0 and best_item.get("partial"):
            title = f"{name} has {n_new} new or updated {'page' if n_new == 1 else 'pages'}"
        elif n_new >= n_price and n_new >= n_rem and n_new > 0:
            title = f"{name} added {n_new} {'page' if n_new == 1 else 'pages'}"
        elif n_price >= n_rem and n_price > 0:
            title = f"{name} updated {n_price} {'price' if n_price == 1 else 'prices'}"
        else:
            title = f"{name} removed {n_rem} {'page' if n_rem == 1 else 'pages'}"
        return {
            "kind": "change",
            "title": title,
            "body": str(best_item.get("summary") or ""),
        }

    first_checks = [c for c in competitors if c.get("status") == "first_check"]
    unchanged = [c for c in competitors if c.get("status") == "unchanged"]
    if unchanged:
        since_iso = next((c.get("compared_with") for c in unchanged if c.get("compared_with")), "")
        since = _format_short_date(str(since_iso or checked_at))
        title = (
            f"No changes at the competitors you watch since {since}"
            if since
            else "No changes at the competitors you watch since your last check"
        )
        return {
            "kind": "unchanged",
            "title": title,
            "body": "Muse checked their public pages and found no new, removed, or repriced pages.",
        }
    if first_checks:
        total_pages = sum(int(c.get("page_count") or 0) for c in first_checks)
        n_fc = len(first_checks)
        label = "competitor" if n_fc == 1 else "competitors"
        return {
            "kind": "first_check",
            "title": f"Baseline saved for {n_fc} {label}",
            "body": (
                f"Muse now knows {total_pages} public pages across your watchlist. "
                "Changes show from the next check."
            ),
        }
    return {
        "kind": "error",
        "title": "Could not read your watched competitors right now",
        "body": "Check each card below for details, or try again later.",
    }


def now_iso_utc() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


async def run_watchlist_checks(
    selected: list[dict[str, str]],
    existing_checks: dict[str, Any],
    *,
    checked_at: str,
    scan_url_fn: Callable[[str], tuple[str, str, bool]],
    collect_entries_fn: Callable[..., Awaitable[tuple[list[SitemapEntry], list[str]]]],
    source: Literal["manual", "auto"] = "manual",
) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]], int]:
    """Check up to 6 selected competitors through scan_guard + collect_entries and diff snapshots.

    Shared by both the manual button (`POST /api/v1/competitors/check`) and the scheduled
    weekly run (`GET /api/v1/watchlist/run`). Zero Muse calls.
    Returns `(results, stored_by_url, total_pages_fetched)`.
    """
    capped = selected[:MAX_COMPETITORS_PER_CHECK]
    targets = [(item["name"], item["url"], *scan_url_fn(item["url"])) for item in capped]

    results: list[dict[str, Any]] = []
    stored_by_url: dict[str, dict[str, Any]] = {}
    total_pages_fetched = 0

    for name, raw_url, normalized, _host, blocked in targets:
        key = normalize_competitor_url(normalized or raw_url)
        prev = existing_checks.get(key) if isinstance(existing_checks.get(key), dict) else None
        if blocked:
            err_kind, err_msg = classify_check_error("", blocked_host=True)
            item_res, stored = error_competitor_result(
                prev,
                name=name,
                url=key,
                checked_at=checked_at,
                error_kind=err_kind,
                error_message=err_msg,
            )
            item_res["source"] = source
            stored["source"] = source
            stored_by_url[key] = stored
            results.append(item_res)
            continue

        try:
            entries, _sitemaps = await scan_guard.crawl(
                normalized,
                MAX_PAGES_PER_COMPETITOR,
                lambda target=normalized: collect_entries_fn(
                    target, max_urls=MAX_PAGES_PER_COMPETITOR
                ),
            )
            total_pages_fetched += len(entries)
            pages = entries_to_snapshot_pages(entries)
            if not pages:
                err_kind, err_msg = classify_check_error("no urls found")
                item_res, stored = error_competitor_result(
                    prev,
                    name=name,
                    url=key,
                    checked_at=checked_at,
                    error_kind=err_kind,
                    error_message=err_msg,
                )
            else:
                item_res, stored = diff_competitor_pages(
                    prev,
                    pages,
                    name=name,
                    url=key,
                    checked_at=checked_at,
                    # The crawl stops at the cap, so a full window means a bigger site.
                    truncated=len(entries) >= MAX_PAGES_PER_COMPETITOR,
                )
        except Exception as err:
            err_kind, err_msg = classify_check_error(err)
            item_res, stored = error_competitor_result(
                prev,
                name=name,
                url=key,
                checked_at=checked_at,
                error_kind=err_kind,
                error_message=err_msg,
            )

        item_res["source"] = source
        stored["source"] = source
        stored_by_url[key] = stored
        results.append(item_res)

    return results, stored_by_url, total_pages_fetched
