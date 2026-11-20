"""A Meta list that runs past the page cap fails loudly instead of returning part of the list.

Codex found (CODEX_PREVIEW_E_REVIEW_NOV20.md) that `_get_paginated` returned what it had after
`max_pages` even when Meta still reported a next page, so a large account's insights could be
treated as the full date range and skew the bid advice. Offline: httpx.MockTransport, no network.
"""

from __future__ import annotations

import asyncio

import httpx
import pytest

from src.clients.ad_networks import AdNetworkIncompleteError
from src.clients.ad_networks.meta import MetaAdsReadClient
from src.config import Settings

NEXT = "https://graph.facebook.com/v27.0/me/adaccounts?after=PAGE2"


def _account(n: int) -> dict[str, object]:
    return {
        "id": f"act_10000000{n}",
        "account_id": f"10000000{n}",
        "name": f"Account {n}",
        "currency": "USD",
        "timezone_name": "America/Los_Angeles",
        "account_status": 1,
    }


def _client(max_pages: int, seen: list[str]) -> MetaAdsReadClient:
    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        if "after=PAGE2" in str(request.url):
            return httpx.Response(200, json={"data": [_account(2)], "paging": {}})
        return httpx.Response(200, json={"data": [_account(1)], "paging": {"next": NEXT}})

    return MetaAdsReadClient(
        settings=Settings(ad_connect_enabled=True, meta_ads_access_token="offline-test-token"),
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
        max_pages=max_pages,
    )


def test_page_cap_with_more_pages_raises_instead_of_returning_part() -> None:
    seen: list[str] = []
    with pytest.raises(AdNetworkIncompleteError):
        asyncio.run(_client(1, seen).list_ad_accounts())
    assert len(seen) == 1


def test_last_page_inside_the_cap_returns_everything() -> None:
    seen: list[str] = []
    accounts = asyncio.run(_client(2, seen).list_ad_accounts())
    assert [a.account_id for a in accounts] == ["act_100000001", "act_100000002"]
    assert len(seen) == 2
