"""A competitor analysis never crawls a Meta Ad Library or social link, and a site Muse cannot
read gets a plain sentence, not robots.txt rules or resolver output.

Nov 24: production sent a watched competitor's Meta Ad Library search
(`facebook.com/ads/library/?...q=Toptal%20Marketing%20Talent%20Network`) as the site to analyze,
and the seller saw "Could not read competitor site: robots.txt at https://www.facebook.com
disallows '...'". The home now reads the row's saved address (tests/test_first_move_card_e2e.py);
these tests cover the server side.
"""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

from src.api.intel import SOCIAL_LINK_REFUSAL, get_competitor_intel_service, is_social_link
from src.api.main import SITE_BLOCKS_READING, SITE_UNREADABLE, app
from src.utils.sitemap import SitemapError

AD_LIBRARY_LINK = (
    "https://www.facebook.com/ads/library/?active_status=active&AdCandidate="
    "&q=Toptal%20Marketing%20Talent%20Network&search_type=keyword_unordered&media_type=all"
)


class RecordingIntel:
    calls: list[Any] = []

    async def analyze(self, request: Any) -> Any:
        RecordingIntel.calls.append(request)
        raise AssertionError("A social link must be refused before any crawl.")


class RaisingIntel:
    error = SitemapError("")

    async def analyze(self, request: Any) -> Any:
        raise RaisingIntel.error


@pytest.fixture(autouse=True)
def _clear_overrides() -> Any:
    yield
    app.dependency_overrides.clear()
    RecordingIntel.calls = []


@pytest.mark.parametrize(
    "url",
    [
        AD_LIBRARY_LINK,
        "https://m.facebook.com/kilnrow",
        "facebook.com/kilnrow",
        "https://www.instagram.com/kilnrow/",
        "https://fb.me/kilnrow",
    ],
)
@pytest.mark.parametrize("live", [True, False])
def test_social_links_are_refused_before_any_crawl(url: str, live: bool) -> None:
    app.dependency_overrides[get_competitor_intel_service] = RecordingIntel
    path = "/api/v1/analyze-competitors" + ("?live=true" if live else "")
    response = TestClient(app).post(path, json={"competitor_url": url, "seller_context": "Mugs"})
    assert response.status_code == 422, response.text
    assert response.json()["detail"] == SOCIAL_LINK_REFUSAL
    assert RecordingIntel.calls == []


def test_only_social_hosts_count_as_social_links() -> None:
    assert is_social_link(AD_LIBRARY_LINK)
    assert not is_social_link("https://notfacebook.com/shop")
    assert not is_social_link("https://facebook.com.example/shop")
    assert not is_social_link("https://kilnrow.example")
    assert not is_social_link("")
    assert not is_social_link(None)


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (
            "robots.txt at https://shop.example disallows 'https://shop.example/p/1'. "
            "Try the seller's main profile page, or paste their listing URLs instead.",
            SITE_BLOCKS_READING,
        ),
        ("Could not resolve hostname 'shop.example': [Errno 8] nodename", SITE_UNREADABLE),
        ("SSRF guard blocked internal hostname 'shop.example'.", SITE_UNREADABLE),
    ],
)
def test_unreadable_site_gets_a_plain_sentence(error: str, expected: str) -> None:
    RaisingIntel.error = SitemapError(error)
    app.dependency_overrides[get_competitor_intel_service] = RaisingIntel
    response = TestClient(app).post(
        "/api/v1/analyze-competitors?live=true",
        json={"competitor_url": "https://shop.example", "seller_context": "Mugs"},
    )
    assert response.status_code == 422, response.text
    assert response.json() == {"detail": expected}
    for leak in ("robots.txt", "shop.example", "SSRF", "Errno", "hostname"):
        assert leak not in response.text, response.text
