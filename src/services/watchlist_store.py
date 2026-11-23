"""Server-only persistence for automatic weekly competitor watchlist checks.

Wraps the four `service_role` RPC functions defined in
`supabase/migrations/watchlist_checks.sql`. When `WATCHLIST_AUTO_CHECK_ENABLED`
is off, nothing here calls Supabase.
"""

from __future__ import annotations

import logging
from typing import Any, Literal

from src.clients.supabase import SupabaseError, get_supabase_client
from src.config import get_settings
from src.services.competitor_checks import MAX_STORED_PAGES_PER_COMPETITOR, normalize_competitor_url

logger = logging.getLogger(__name__)


def auto_check_enabled() -> bool:
    """Return True only when WATCHLIST_AUTO_CHECK_ENABLED is explicitly turned on."""
    return bool(get_settings().watchlist_auto_check_enabled)


def _normalize_table_checks(raw_checks: Any) -> dict[str, dict[str, Any]]:
    by_url: dict[str, dict[str, Any]] = {}
    if not isinstance(raw_checks, list):
        return by_url
    for row in raw_checks:
        if not isinstance(row, dict):
            continue
        site_url = normalize_competitor_url(str(row.get("site_url") or ""))
        if not site_url:
            continue
        result = row.get("result") if isinstance(row.get("result"), dict) else {}
        merged = dict(result)
        merged["url"] = site_url
        merged["status"] = str(row.get("status") or merged.get("status") or "")
        merged["source"] = str(row.get("source") or merged.get("source") or "manual")
        merged["checked_at"] = str(row.get("checked_at") or merged.get("checked_at") or "")
        merged["summary"] = str(row.get("summary") or merged.get("summary") or "")
        merged["error"] = str(row.get("error") or merged.get("error") or "")
        merged["partial"] = bool(row.get("partial", merged.get("partial", False)))
        snap = row.get("snapshot")
        if isinstance(snap, dict) and isinstance(snap.get("pages"), list):
            merged["pages"] = snap["pages"]
        by_url[site_url] = merged
    return by_url


async def get_checks(user_id: str, *, with_snapshots: bool = False) -> dict[str, Any] | None:
    """Read one seller's saved watchlist checks and schedule from Supabase.

    Returns None when the feature flag is off or the table is unavailable, so callers
    can fall back cleanly to legacy `preferences.competitor_checks`.
    """
    if not auto_check_enabled():
        return None
    try:
        data = await get_supabase_client().rpc(
            "muse_watchlist_get",
            {"p_user_id": user_id, "p_with_snapshots": bool(with_snapshots)},
        )
    except SupabaseError as err:
        logger.warning("Watchlist store get_checks unavailable (HTTP %s)", err.status_code)
        return None

    sched_raw = data.get("schedule") if isinstance(data.get("schedule"), dict) else {}
    return {
        "enabled": True,
        "checks": _normalize_table_checks(data.get("checks")),
        "schedule": {
            "paused": bool(sched_raw.get("paused", False)),
            "next_check_at": sched_raw.get("next_check_at"),
            "last_auto_check_at": sched_raw.get("last_auto_check_at"),
        },
    }


async def save_checks(
    user_id: str,
    *,
    source: Literal["manual", "auto"],
    checks: list[dict[str, Any]],
    keep_urls: list[str],
) -> dict[str, Any]:
    """Upsert checked sites, prune removed sites, and push next_check_at 7 days out."""
    return await get_supabase_client().rpc(
        "muse_watchlist_save",
        {
            "p_user_id": user_id,
            "p_source": source,
            "p_checks": checks,
            "p_keep_urls": keep_urls,
        },
    )


async def claim_due(*, limit: int = 10, lease_seconds: int = 600) -> list[dict[str, Any]]:
    """Claim due unpaused sellers with a lease for the scheduled automatic run."""
    data = await get_supabase_client().rpc(
        "muse_watchlist_claim_due",
        {"p_limit": int(limit), "p_lease_seconds": int(lease_seconds)},
    )
    sellers = data.get("sellers")
    return [s for s in sellers if isinstance(s, dict)] if isinstance(sellers, list) else []


async def set_paused(user_id: str, paused: bool) -> dict[str, Any]:
    """Pause or resume weekly automatic checks for one seller."""
    return await get_supabase_client().rpc(
        "muse_watchlist_set_paused",
        {"p_user_id": user_id, "p_paused": bool(paused)},
    )


async def is_email_confirmed(user_id: str) -> bool:
    """Check `email_confirmed_at` via the Supabase Auth admin API (read-only, never logged)."""
    try:
        data = await get_supabase_client().auth(f"admin/users/{user_id}", method="GET", secret=True)
    except SupabaseError:
        return False
    return bool(str(data.get("email_confirmed_at") or "").strip())


async def load_workspace_document(user_id: str) -> dict[str, Any] | None:
    """Read a seller's workspace document via the secret Supabase client."""
    try:
        rows = await get_supabase_client().workspace(user_id)
    except SupabaseError:
        return None
    if not rows or not isinstance(rows[0], dict):
        return None
    doc = rows[0].get("document")
    return doc if isinstance(doc, dict) else None


def build_db_check_rows(
    results: list[dict[str, Any]],
    stored_by_url: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    """Format checked competitor items for `muse_watchlist_save` within table size caps."""
    rows: list[dict[str, Any]] = []
    for item in results:
        site_url = normalize_competitor_url(str(item.get("url") or ""))[:300]
        if len(site_url) < 8:
            continue
        stored = stored_by_url.get(site_url) or {}
        pages = stored.get("pages") if isinstance(stored.get("pages"), list) else []
        display_result = {k: v for k, v in item.items() if k != "pages"}
        rows.append(
            {
                "site_url": site_url,
                "status": str(item.get("status") or "error"),
                "checked_at": str(item.get("checked_at") or ""),
                "summary": str(item.get("summary") or "")[:600],
                "error": str(item.get("error") or "")[:300],
                "partial": bool(item.get("partial", False)),
                "result": display_result,
                "snapshot": {
                    "pages": pages[:MAX_STORED_PAGES_PER_COMPETITOR],
                    "checked_at": str(stored.get("checked_at") or item.get("checked_at") or ""),
                    "partial": bool(stored.get("partial", item.get("partial", False))),
                },
            }
        )
    return rows


def merge_checks_for_display(
    table_data: dict[str, Any] | None,
    legacy_checks: Any,
) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    """Merge table checks (first) with legacy `preferences.competitor_checks` fallback."""
    merged: dict[str, dict[str, Any]] = {}
    if isinstance(legacy_checks, dict):
        for raw_key, val in legacy_checks.items():
            if not isinstance(val, dict):
                continue
            key = normalize_competitor_url(str(raw_key or val.get("url") or ""))
            if key:
                entry = {k: v for k, v in val.items() if k != "pages"}
                entry.setdefault("source", "manual")
                merged[key] = entry

    enabled = bool(table_data and table_data.get("enabled"))
    if enabled and isinstance(table_data, dict):
        for key, val in (table_data.get("checks") or {}).items():
            if isinstance(val, dict):
                merged[key] = {k: v for k, v in val.items() if k != "pages"}

    sched = (
        table_data.get("schedule")
        if enabled and isinstance(table_data, dict) and isinstance(table_data.get("schedule"), dict)
        else {}
    )
    auto_check = {
        "enabled": enabled,
        "paused": bool(sched.get("paused", False)) if enabled else False,
        "next_check_at": sched.get("next_check_at") if enabled else None,
        "last_auto_check_at": sched.get("last_auto_check_at") if enabled else None,
    }
    return merged, auto_check
