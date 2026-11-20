"""Read-only Meta Marketing API (Graph API v21.0) adapter using httpx.

Strictly read-only: lists accessible ad accounts, campaign summaries, and daily ad-set / campaign
insights with cursor pagination. Contains zero write or mutation methods. Never executes requests
when `AD_CONNECT_ENABLED` is false.
"""

from __future__ import annotations

import json
import logging
from datetime import date
from typing import Any, Literal
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import httpx

from src.clients.ad_networks.base import (
    AdAccountSummary,
    AdCampaignSummary,
    AdInsightRow,
    AdNetworkAuthError,
    AdNetworkDisabledError,
    AdNetworkError,
    AdNetworkId,
    AdNetworkPermissionError,
    AdNetworkRateLimitError,
)
from src.config import Settings, get_settings

logger = logging.getLogger(__name__)

META_GRAPH_BASE_URL = "https://graph.facebook.com/v21.0"
ALLOWED_GRAPH_HOSTS = frozenset({"graph.facebook.com"})
DEFAULT_TIMEOUT = httpx.Timeout(20.0, connect=5.0)
MAX_PAGINATION_PAGES = 25

# Meta numeric account_status codes (Marketing API AdAccount reference)
_ACCOUNT_STATUS_MAP: dict[int, str] = {
    1: "ACTIVE",
    2: "DISABLED",
    3: "UNSETTLED",
    7: "PENDING_RISK_REVIEW",
    8: "PENDING_SETTLEMENT",
    9: "IN_GRACE_PERIOD",
    100: "PENDING_CLOSURE",
    101: "CLOSED",
}

# Priority-ordered conversion action_type keys in Meta Insights `actions` / `action_values` arrays.
# Selecting the highest-priority key present avoids double-counting when Meta emits both
# `omni_purchase` and `offsite_conversion.fb_pixel_purchase` for the same order.
_CONVERSION_ACTION_PRIORITY: tuple[str, ...] = (
    "omni_purchase",
    "purchase",
    "offsite_conversion.fb_pixel_purchase",
    "onsite_conversion.purchase",
    "lead",
    "offsite_conversion.fb_pixel_lead",
)

_AUTH_ERROR_CODES = frozenset({102, 190, 2500})
_RATE_LIMIT_ERROR_CODES = frozenset({4, 17, 32, 613, 80000, 80004})
_PERMISSION_ERROR_CODES = frozenset({10, 200, 294})


def normalize_meta_account_id(account_id: str) -> str:
    """Normalize a Meta ad account identifier to `act_<id>` format."""
    cleaned = account_id.strip()
    if not cleaned:
        raise ValueError("Meta ad account_id must not be empty.")
    raw = cleaned[4:] if cleaned.startswith("act_") else cleaned
    if not raw or not raw.replace("_", "").isalnum():
        raise ValueError(f"Invalid Meta ad account_id: {account_id!r}")
    return f"act_{raw}"


def _sanitize_next_url(next_url: str) -> str:
    """Validate that a Graph API `paging.next` URL targets graph.facebook.com and strip tokens."""
    parts = urlsplit(next_url.strip())
    if parts.scheme != "https" or parts.hostname not in ALLOWED_GRAPH_HOSTS:
        raise AdNetworkError(
            f"Refusing pagination redirect to untrusted host: {parts.hostname!r}",
            network="meta",
        )
    filtered_query = [
        (k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True) if k != "access_token"
    ]
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(filtered_query), ""))


def _extract_action_metric(
    items: Any,
    *,
    as_float: bool,
) -> float | int | None:
    """Extract the primary conversion count or value from Meta `actions` / `action_values`."""
    if not isinstance(items, list):
        return None
    by_type: dict[str, float] = {}
    for entry in items:
        if not isinstance(entry, dict):
            continue
        action_type = str(entry.get("action_type") or "").strip().lower()
        raw_val = entry.get("value")
        if not action_type or raw_val is None:
            continue
        try:
            by_type[action_type] = float(raw_val)
        except (TypeError, ValueError):
            continue

    for candidate in _CONVERSION_ACTION_PRIORITY:
        if candidate in by_type:
            val = max(0.0, by_type[candidate])
            return round(val, 2) if as_float else int(round(val))
    return None


def _parse_retry_after(response: httpx.Response) -> int | None:
    raw = response.headers.get("Retry-After")
    if raw and raw.strip().isdigit():
        return int(raw.strip())
    return None


def _classify_and_raise(response: httpx.Response) -> None:
    """Translate a non-200 Meta Graph API response into a narrow AdNetworkError subclass."""
    status = response.status_code
    error_obj: dict[str, Any] = {}
    try:
        payload = response.json()
        if isinstance(payload, dict) and isinstance(payload.get("error"), dict):
            error_obj = payload["error"]
    except ValueError:
        error_obj = {}

    raw_code = error_obj.get("code")
    code: int | None = int(raw_code) if isinstance(raw_code, int) else None
    raw_subcode = error_obj.get("error_subcode")
    subcode: int | None = int(raw_subcode) if isinstance(raw_subcode, int) else None
    msg = str(error_obj.get("message") or f"Meta Marketing API error (HTTP {status}).").strip()

    if status == 401 or code in _AUTH_ERROR_CODES:
        raise AdNetworkAuthError(
            f"Meta access token is expired or invalid: {msg}",
            network="meta",
            status_code=status,
            error_code=code,
            error_subcode=subcode,
        )

    if status == 429 or code in _RATE_LIMIT_ERROR_CODES:
        raise AdNetworkRateLimitError(
            f"Meta Marketing API rate limit reached: {msg}",
            network="meta",
            status_code=status,
            error_code=code,
            error_subcode=subcode,
            retry_after_seconds=_parse_retry_after(response),
        )

    if (
        status == 403
        or code in _PERMISSION_ERROR_CODES
        or (code is not None and 200 <= code <= 299)
    ):
        raise AdNetworkPermissionError(
            f"Meta Marketing API permission denied: {msg}",
            network="meta",
            status_code=status,
            error_code=code,
            error_subcode=subcode,
        )

    raise AdNetworkError(
        f"Meta Marketing API request failed (HTTP {status}): {msg}",
        network="meta",
        status_code=status,
        error_code=code,
        error_subcode=subcode,
    )


class MetaAdsReadClient:
    """Read-only client for the Meta Marketing API (Graph API v21.0)."""

    network: AdNetworkId = "meta"

    def __init__(
        self,
        *,
        access_token: str | None = None,
        settings: Settings | None = None,
        http_client: httpx.AsyncClient | None = None,
        base_url: str = META_GRAPH_BASE_URL,
        max_pages: int = MAX_PAGINATION_PAGES,
    ) -> None:
        self._settings = settings or get_settings()
        raw_token = (
            access_token if access_token is not None else self._settings.meta_ads_access_token
        )
        self._token = raw_token.strip()
        self._base_url = base_url.rstrip("/")
        self._max_pages = max(1, max_pages)
        self._owns_client = http_client is None
        self._http_client = http_client or httpx.AsyncClient(timeout=DEFAULT_TIMEOUT)

    async def aclose(self) -> None:
        if self._owns_client:
            await self._http_client.aclose()

    def _check_enabled_and_authenticated(self) -> None:
        if not self._settings.ad_connect_enabled:
            raise AdNetworkDisabledError(
                "Ad account connections are disabled (AD_CONNECT_ENABLED=false).",
                network="meta",
            )
        if not self._token:
            raise AdNetworkAuthError(
                "Meta Marketing API access token is required.",
                network="meta",
            )

    async def _get_paginated(
        self,
        path: str,
        *,
        params: dict[str, str],
    ) -> list[dict[str, Any]]:
        """Fetch all pages of a Graph API list edge up to `self._max_pages`."""
        self._check_enabled_and_authenticated()
        url = f"{self._base_url}/{path.lstrip('/')}"
        headers = {"Authorization": f"Bearer {self._token}"}
        current_params: dict[str, str] | None = dict(params)
        collected: list[dict[str, Any]] = []

        for _ in range(self._max_pages):
            try:
                response = await self._http_client.get(
                    url,
                    params=current_params,
                    headers=headers,
                )
            except httpx.HTTPError as err:
                raise AdNetworkError(
                    f"Meta Marketing API network error: {type(err).__name__}",
                    network="meta",
                ) from err

            if response.status_code != 200:
                _classify_and_raise(response)

            try:
                payload = response.json()
            except ValueError as err:
                raise AdNetworkError(
                    "Meta Marketing API returned invalid JSON.",
                    network="meta",
                    status_code=response.status_code,
                ) from err

            if isinstance(payload, dict) and isinstance(payload.get("error"), dict):
                _classify_and_raise(response)

            rows = payload.get("data", []) if isinstance(payload, dict) else []
            if not isinstance(rows, list):
                raise AdNetworkError(
                    "Meta Marketing API response missing 'data' list.",
                    network="meta",
                    status_code=response.status_code,
                )
            for item in rows:
                if isinstance(item, dict):
                    collected.append(item)

            paging = payload.get("paging") if isinstance(payload, dict) else None
            next_url = paging.get("next") if isinstance(paging, dict) else None
            if not next_url or not isinstance(next_url, str):
                break
            url = _sanitize_next_url(next_url)
            current_params = None

        return collected

    async def list_ad_accounts(self, *, limit: int = 50) -> list[AdAccountSummary]:
        """List Meta ad accounts accessible to the user token (`GET /me/adaccounts`)."""
        records = await self._get_paginated(
            "me/adaccounts",
            params={
                "fields": "id,account_id,name,currency,timezone_name,account_status",
                "limit": str(min(max(limit, 1), 200)),
            },
        )
        accounts: list[AdAccountSummary] = []
        for item in records:
            raw_id = str(item.get("id") or item.get("account_id") or "").strip()
            if not raw_id:
                continue
            raw_status = item.get("account_status")
            if isinstance(raw_status, int):
                status_label = _ACCOUNT_STATUS_MAP.get(raw_status, f"STATUS_{raw_status}")
            else:
                status_label = str(raw_status or "ACTIVE").upper()
            currency = str(item.get("currency") or "USD").strip().upper()
            if len(currency) != 3:
                currency = "USD"
            accounts.append(
                AdAccountSummary(
                    network="meta",
                    account_id=normalize_meta_account_id(raw_id),
                    name=str(item.get("name") or "").strip(),
                    currency=currency,
                    timezone_name=str(item.get("timezone_name") or "UTC").strip() or "UTC",
                    account_status=status_label,
                )
            )
        return accounts

    async def list_campaigns(
        self,
        account_id: str,
        *,
        limit: int = 100,
    ) -> list[AdCampaignSummary]:
        """List campaigns under a Meta ad account (`GET /act_{id}/campaigns`)."""
        act_id = normalize_meta_account_id(account_id)
        records = await self._get_paginated(
            f"{act_id}/campaigns",
            params={
                "fields": "id,name,status,effective_status,objective,daily_budget",
                "limit": str(min(max(limit, 1), 200)),
            },
        )
        campaigns: list[AdCampaignSummary] = []
        for item in records:
            camp_id = str(item.get("id") or "").strip()
            name = str(item.get("name") or "").strip()
            if not camp_id or not name:
                continue
            daily_budget: float | None = None
            raw_budget = item.get("daily_budget")
            if raw_budget is not None and str(raw_budget).strip() != "":
                try:
                    # Meta returns campaign/adset daily_budget in minor currency units (cents).
                    daily_budget = round(float(raw_budget) / 100.0, 2)
                except (TypeError, ValueError):
                    daily_budget = None
            campaigns.append(
                AdCampaignSummary(
                    network="meta",
                    campaign_id=camp_id,
                    name=name,
                    status=str(item.get("status") or "PAUSED").upper(),
                    effective_status=(
                        str(item["effective_status"]).upper()
                        if item.get("effective_status")
                        else None
                    ),
                    objective=str(item["objective"]) if item.get("objective") else None,
                    daily_budget=daily_budget,
                )
            )
        return campaigns

    async def fetch_campaign_insights(
        self,
        account_id: str,
        *,
        start_date: date,
        end_date: date,
        level: Literal["adset", "campaign"] = "adset",
        limit: int = 100,
    ) -> list[AdInsightRow]:
        """Fetch daily insights (`time_increment=1`) for an ad account over a date range."""
        if end_date < start_date:
            raise ValueError("end_date must be on or after start_date.")
        act_id = normalize_meta_account_id(account_id)
        records = await self._get_paginated(
            f"{act_id}/insights",
            params={
                "level": level,
                "time_increment": "1",
                "time_range": json.dumps(
                    {
                        "since": start_date.isoformat(),
                        "until": end_date.isoformat(),
                    }
                ),
                "fields": (
                    "campaign_id,campaign_name,adset_id,adset_name,date_start,date_stop,"
                    "impressions,clicks,spend,frequency,actions,action_values,account_currency"
                ),
                "limit": str(min(max(limit, 1), 500)),
            },
        )
        rows: list[AdInsightRow] = []
        for item in records:
            day_raw = str(item.get("date_start") or "").strip()
            campaign_name = str(item.get("campaign_name") or "").strip()
            ad_set_name = str(item.get("adset_name") or campaign_name).strip()
            if not day_raw or not campaign_name or not ad_set_name:
                continue

            impressions = max(0, int(float(item.get("impressions") or 0)))
            clicks = min(impressions, max(0, int(float(item.get("clicks") or 0))))
            spend = max(0.0, round(float(item.get("spend") or 0.0), 2))

            conversions_from_actions = _extract_action_metric(
                item.get("actions"),
                as_float=False,
            )
            if conversions_from_actions is not None:
                conversions = int(conversions_from_actions)
            elif item.get("conversions") is not None:
                conversions = max(0, int(float(item["conversions"])))
            else:
                conversions = 0

            value_from_actions = _extract_action_metric(
                item.get("action_values"),
                as_float=True,
            )
            if value_from_actions is not None:
                conversion_value: float | None = float(value_from_actions)
            elif item.get("conversion_value") is not None:
                conversion_value = max(0.0, round(float(item["conversion_value"]), 2))
            else:
                conversion_value = None

            frequency: float | None = None
            if item.get("frequency") is not None and str(item["frequency"]).strip() != "":
                frequency = max(0.0, round(float(item["frequency"]), 4))

            daily_budget: float | None = None
            if item.get("daily_budget") is not None and str(item["daily_budget"]).strip() != "":
                daily_budget = max(0.0, round(float(item["daily_budget"]), 2))

            currency = str(item.get("account_currency") or "USD").strip().upper()
            if len(currency) != 3:
                currency = "USD"

            rows.append(
                AdInsightRow(
                    network="meta",
                    day=date.fromisoformat(day_raw[:10]),
                    campaign_id=str(item.get("campaign_id") or "").strip(),
                    campaign_name=campaign_name,
                    ad_set_id=str(item.get("adset_id") or "").strip(),
                    ad_set_name=ad_set_name,
                    impressions=impressions,
                    clicks=clicks,
                    conversions=conversions,
                    spend=spend,
                    conversion_value=conversion_value,
                    frequency=frequency,
                    daily_budget=daily_budget,
                    currency=currency,
                )
            )
        return rows
