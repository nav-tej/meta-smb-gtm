"""Offline tests for the read-only Meta Marketing API slice and CampaignPerformance mapping.

Uses respx with response payloads shaped from Meta's official Graph API v21.0 Marketing API
documentation (adaccounts, campaigns, insights, cursor pagination, and OAuth/rate-limit errors).
Never hits the network.
"""

from __future__ import annotations

from datetime import date

import httpx
import pytest
import respx

from src.clients.ad_networks.base import (
    AdNetworkAuthError,
    AdNetworkDisabledError,
    AdNetworkError,
    AdNetworkPermissionError,
    AdNetworkRateLimitError,
    AdNetworkReadAdapter,
)
from src.clients.ad_networks.meta import (
    META_GRAPH_BASE_URL,
    MetaAdsReadClient,
    normalize_meta_account_id,
)
from src.config import Settings
from src.services.ad_insights import (
    fetch_meta_campaign_performance,
    insights_to_campaign_performance,
)
from src.services.bid_advisor import compute_metrics

# Response fixtures shaped from Meta Marketing API docs:
# - https://developers.facebook.com/docs/marketing-api/reference/ad-account
# - https://developers.facebook.com/docs/marketing-api/insights
AD_ACCOUNTS_FIXTURE = {
    "data": [
        {
            "id": "act_1092837465",
            "account_id": "1092837465",
            "name": "Sarabjit Singh Studio Ads",
            "currency": "USD",
            "timezone_name": "America/Los_Angeles",
            "account_status": 1,
        },
        {
            "id": "act_9988776655",
            "account_id": "9988776655",
            "name": "Archived Test Account",
            "currency": "CAD",
            "timezone_name": "America/Toronto",
            "account_status": 2,
        },
    ],
    "paging": {"cursors": {"before": "MAZDZD", "after": "MQZDZD"}},
}

CAMPAIGNS_FIXTURE = {
    "data": [
        {
            "id": "1202100001",
            "name": "Heritage Prints — Prospecting",
            "status": "ACTIVE",
            "effective_status": "ACTIVE",
            "objective": "OUTCOME_SALES",
            "daily_budget": "3500",
        },
        {
            "id": "1202100002",
            "name": "Studio Collectors — Retargeting",
            "status": "PAUSED",
            "effective_status": "PAUSED",
            "objective": "OUTCOME_SALES",
        },
    ]
}

INSIGHTS_PAGE_1_FIXTURE = {
    "data": [
        {
            "campaign_id": "1202100001",
            "campaign_name": "Heritage Prints — Prospecting",
            "adset_id": "2303100001",
            "adset_name": "Sikh Heritage Wall Art — Broad US",
            "date_start": "2026-11-15",
            "date_stop": "2026-11-15",
            "impressions": "4200",
            "clicks": "84",
            "spend": "28.50",
            "frequency": "1.25",
            "account_currency": "USD",
            "actions": [
                {"action_type": "link_click", "value": "71"},
                {"action_type": "omni_purchase", "value": "3"},
                {"action_type": "offsite_conversion.fb_pixel_purchase", "value": "3"},
            ],
            "action_values": [
                {"action_type": "omni_purchase", "value": "144.00"},
                {"action_type": "offsite_conversion.fb_pixel_purchase", "value": "144.00"},
            ],
        },
        {
            "campaign_id": "1202100001",
            "campaign_name": "Heritage Prints — Prospecting",
            "adset_id": "2303100001",
            "adset_name": "Sikh Heritage Wall Art — Broad US",
            "date_start": "2026-11-16",
            "date_stop": "2026-11-16",
            "impressions": "4600",
            "clicks": "92",
            "spend": "31.00",
            "frequency": "1.30",
            "account_currency": "USD",
            "actions": [
                {"action_type": "purchase", "value": "4"},
            ],
            "action_values": [
                {"action_type": "purchase", "value": "192.00"},
            ],
        },
    ],
    "paging": {
        "cursors": {"before": "MAZDZD", "after": "MjMZD"},
        "next": (
            f"{META_GRAPH_BASE_URL}/act_1092837465/insights"
            "?after=MjMZD&level=adset&time_increment=1&access_token=SHOULD_BE_STRIPPED"
        ),
    },
}

INSIGHTS_PAGE_2_FIXTURE = {
    "data": [
        {
            "campaign_id": "1202100002",
            "campaign_name": "Studio Collectors — Retargeting",
            "adset_id": "2303100002",
            "adset_name": "Site Visitors 30d",
            "date_start": "2026-11-15",
            "date_stop": "2026-11-15",
            "impressions": "1100",
            "clicks": "11",
            "spend": "14.00",
            "frequency": "2.40",
            "account_currency": "USD",
            "actions": [
                {"action_type": "link_click", "value": "9"},
            ],
            "action_values": [],
        },
        {
            "campaign_id": "1202100002",
            "campaign_name": "Studio Collectors — Retargeting",
            "adset_id": "2303100002",
            "adset_name": "Site Visitors 30d",
            "date_start": "2026-11-16",
            "date_stop": "2026-11-16",
            "impressions": "1250",
            "clicks": "15",
            "spend": "15.50",
            "frequency": "2.55",
            "account_currency": "USD",
            "actions": [
                {"action_type": "omni_purchase", "value": "1"},
            ],
            "action_values": [
                {"action_type": "omni_purchase", "value": "48.00"},
            ],
        },
    ],
    "paging": {"cursors": {"before": "MjMZD", "after": "NDQZD"}},
}


def _enabled_settings() -> Settings:
    return Settings(
        ad_connect_enabled=True,
        meta_ads_access_token="test-meta-token-do-not-log",
    )


def test_default_flag_is_off_and_blocks_calls() -> None:
    default_cfg = Settings()
    assert default_cfg.ad_connect_enabled is False

    client = MetaAdsReadClient(
        access_token="token-present-but-flag-off",
        settings=default_cfg,
    )
    assert isinstance(client, AdNetworkReadAdapter)


@pytest.mark.asyncio
async def test_disabled_flag_prevents_any_http_call() -> None:
    client = MetaAdsReadClient(
        access_token="token-present",
        settings=Settings(ad_connect_enabled=False),
    )
    with respx.mock(assert_all_called=False) as router:
        route = router.get(f"{META_GRAPH_BASE_URL}/me/adaccounts").mock(
            return_value=httpx.Response(200, json=AD_ACCOUNTS_FIXTURE)
        )
        with pytest.raises(AdNetworkDisabledError, match="AD_CONNECT_ENABLED=false"):
            await client.list_ad_accounts()
        assert not route.called
    await client.aclose()


@pytest.mark.asyncio
async def test_list_ad_accounts_and_campaigns_happy_path() -> None:
    client = MetaAdsReadClient(settings=_enabled_settings())
    with respx.mock as router:
        acc_route = router.get(f"{META_GRAPH_BASE_URL}/me/adaccounts").mock(
            return_value=httpx.Response(200, json=AD_ACCOUNTS_FIXTURE)
        )
        camp_route = router.get(f"{META_GRAPH_BASE_URL}/act_1092837465/campaigns").mock(
            return_value=httpx.Response(200, json=CAMPAIGNS_FIXTURE)
        )

        accounts = await client.list_ad_accounts()
        campaigns = await client.list_campaigns("1092837465")

    await client.aclose()

    assert acc_route.called
    assert camp_route.called
    sent_auth = acc_route.calls[0].request.headers.get("Authorization")
    assert sent_auth == "Bearer test-meta-token-do-not-log"

    assert len(accounts) == 2
    assert accounts[0].account_id == "act_1092837465"
    assert accounts[0].name == "Sarabjit Singh Studio Ads"
    assert accounts[0].currency == "USD"
    assert accounts[0].account_status == "ACTIVE"
    assert accounts[1].account_status == "DISABLED"

    assert len(campaigns) == 2
    assert campaigns[0].campaign_id == "1202100001"
    assert campaigns[0].daily_budget == 35.0
    assert campaigns[1].daily_budget is None


@pytest.mark.asyncio
async def test_fetch_campaign_insights_pagination_and_action_dedup() -> None:
    client = MetaAdsReadClient(settings=_enabled_settings())
    calls: list[httpx.Request] = []

    def _insights_handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if "after=MjMZD" in str(request.url):
            return httpx.Response(200, json=INSIGHTS_PAGE_2_FIXTURE)
        return httpx.Response(200, json=INSIGHTS_PAGE_1_FIXTURE)

    with respx.mock as router:
        router.get(f"{META_GRAPH_BASE_URL}/act_1092837465/insights").mock(
            side_effect=_insights_handler
        )
        rows = await client.fetch_campaign_insights(
            "act_1092837465",
            start_date=date(2026, 11, 15),
            end_date=date(2026, 11, 16),
        )

    await client.aclose()

    assert len(calls) == 2
    # Verify access_token was stripped from paging.next query params and sent via header instead.
    assert "access_token" not in str(calls[1].url)
    assert calls[1].headers.get("Authorization") == "Bearer test-meta-token-do-not-log"

    assert len(rows) == 4
    # First row had both omni_purchase=3 and fb_pixel_purchase=3; must not double-count to 6.
    assert rows[0].conversions == 3
    assert rows[0].conversion_value == 144.0
    assert rows[2].conversions == 0
    assert rows[2].conversion_value is None


@pytest.mark.asyncio
async def test_empty_account_returns_empty_list_and_mapping_raises_value_error() -> None:
    client = MetaAdsReadClient(settings=_enabled_settings())
    with respx.mock as router:
        router.get(f"{META_GRAPH_BASE_URL}/act_1092837465/insights").mock(
            return_value=httpx.Response(200, json={"data": []})
        )
        rows = await client.fetch_campaign_insights(
            "act_1092837465",
            start_date=date(2026, 11, 15),
            end_date=date(2026, 11, 16),
        )
    await client.aclose()

    assert rows == []
    with pytest.raises(ValueError, match="no daily insights rows"):
        insights_to_campaign_performance(rows)


@pytest.mark.asyncio
async def test_expired_token_raises_typed_auth_error() -> None:
    client = MetaAdsReadClient(settings=_enabled_settings())
    expired_payload = {
        "error": {
            "message": "Error validating access token: Session has expired on Nov 18, 2026.",
            "type": "OAuthException",
            "code": 190,
            "error_subcode": 463,
            "fbtrace_id": "AbCdEf123456",
        }
    }
    with respx.mock as router:
        router.get(f"{META_GRAPH_BASE_URL}/me/adaccounts").mock(
            return_value=httpx.Response(401, json=expired_payload)
        )
        with pytest.raises(AdNetworkAuthError) as exc_info:
            await client.list_ad_accounts()

    await client.aclose()
    err = exc_info.value
    assert err.network == "meta"
    assert err.status_code == 401
    assert err.error_code == 190
    assert err.error_subcode == 463
    assert "test-meta-token-do-not-log" not in str(err)


@pytest.mark.asyncio
async def test_rate_limit_raises_typed_rate_limit_error() -> None:
    client = MetaAdsReadClient(settings=_enabled_settings())
    rate_limit_payload = {
        "error": {
            "message": "(#80004) There have been too many calls to this ad-account.",
            "type": "OAuthException",
            "code": 80004,
            "fbtrace_id": "RateTrace987",
        }
    }
    with respx.mock as router:
        router.get(f"{META_GRAPH_BASE_URL}/act_1092837465/insights").mock(
            return_value=httpx.Response(
                429,
                json=rate_limit_payload,
                headers={"Retry-After": "120"},
            )
        )
        with pytest.raises(AdNetworkRateLimitError) as exc_info:
            await client.fetch_campaign_insights(
                "act_1092837465",
                start_date=date(2026, 11, 15),
                end_date=date(2026, 11, 16),
            )

    await client.aclose()
    err = exc_info.value
    assert err.error_code == 80004
    assert err.retry_after_seconds == 120


@pytest.mark.asyncio
async def test_permission_denied_raises_typed_permission_error() -> None:
    client = MetaAdsReadClient(settings=_enabled_settings())
    perm_payload = {
        "error": {
            "message": "(#200) Ads API access requires ads_read permission.",
            "type": "OAuthException",
            "code": 200,
        }
    }
    with respx.mock as router:
        router.get(f"{META_GRAPH_BASE_URL}/act_1092837465/campaigns").mock(
            return_value=httpx.Response(403, json=perm_payload)
        )
        with pytest.raises(AdNetworkPermissionError) as exc_info:
            await client.list_campaigns("act_1092837465")

    await client.aclose()
    assert exc_info.value.error_code == 200
    assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_untrusted_pagination_host_is_refused() -> None:
    client = MetaAdsReadClient(settings=_enabled_settings())
    malicious_page = {
        "data": INSIGHTS_PAGE_1_FIXTURE["data"],
        "paging": {"next": "https://evil.example.com/v21.0/act_1092837465/insights"},
    }
    with respx.mock as router:
        router.get(f"{META_GRAPH_BASE_URL}/act_1092837465/insights").mock(
            return_value=httpx.Response(200, json=malicious_page)
        )
        with pytest.raises(AdNetworkError, match="untrusted host"):
            await client.fetch_campaign_insights(
                "act_1092837465",
                start_date=date(2026, 11, 15),
                end_date=date(2026, 11, 16),
            )
    await client.aclose()


@pytest.mark.asyncio
async def test_mapping_into_campaign_performance_and_bid_advisor_metrics() -> None:
    client = MetaAdsReadClient(settings=_enabled_settings())

    def _insights_handler(request: httpx.Request) -> httpx.Response:
        if "after=MjMZD" in str(request.url):
            return httpx.Response(200, json=INSIGHTS_PAGE_2_FIXTURE)
        return httpx.Response(200, json=INSIGHTS_PAGE_1_FIXTURE)

    with respx.mock as router:
        router.get(f"{META_GRAPH_BASE_URL}/act_1092837465/insights").mock(
            side_effect=_insights_handler
        )
        campaign_perf = await fetch_meta_campaign_performance(
            "1092837465",
            start_date=date(2026, 11, 15),
            end_date=date(2026, 11, 16),
            account_name="Sarabjit Singh Studio Ads",
            client=client,
        )

    await client.aclose()

    assert campaign_perf.account_name == "Sarabjit Singh Studio Ads"
    assert campaign_perf.currency == "USD"
    assert len(campaign_perf.rows) == 4
    # Derived ratios on AdSetDailyPerformance are automatically populated by Pydantic validator.
    assert campaign_perf.rows[0].ctr == 2.0
    assert campaign_perf.rows[0].roas == round(144.0 / 28.5, 4)

    # Verify the resulting CampaignPerformance plugs directly into bid_advisor.compute_metrics().
    metrics = compute_metrics(campaign_perf)
    assert metrics.account_name == "Sarabjit Singh Studio Ads"
    assert metrics.days == 2
    assert metrics.account_totals.spend == 89.0
    assert metrics.account_totals.conversions == 8
    assert len(metrics.ad_sets) == 2
    assert metrics.ad_sets[0].ad_set_name == "Sikh Heritage Wall Art — Broad US"
    assert metrics.ad_sets[0].totals.conversions == 7


def test_normalize_meta_account_id_validation() -> None:
    assert normalize_meta_account_id("123456") == "act_123456"
    assert normalize_meta_account_id("  act_123456  ") == "act_123456"
    with pytest.raises(ValueError):
        normalize_meta_account_id("")
    with pytest.raises(ValueError):
        normalize_meta_account_id("act_../etc/passwd")
