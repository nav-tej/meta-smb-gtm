"""Profile-page and URL-list ingestion for Competitor Intel, plus RFC 9309 robots matching."""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest
import respx
from pydantic import ValidationError

from src.models.intel import CompetitorIntelRequest
from src.services.competitor_intel import SitemapError, collect_entries
from src.utils.sitemap import HostRateLimiter, extract_page_metadata, parse_robots_txt

FIXTURES = Path(__file__).parent / "fixtures"
FAA = "https://fineartamerica.com"
UA = "MetaSMBGTM/0.1 (+https://github.com/nav-tej/meta-smb-gtm)"
FAA_ROBOTS = """\
User-agent: *
Disallow: /profiles/*/art/*
Allow: /profiles/*/art/paintings$
Disallow: /profiles/*/shop/*/*
Disallow: /profiles/*?tab=blogs
Sitemap: https://fineartamerica.com/sitemap.xml
"""


async def _public_resolver(_host: str) -> list[str]:
    return ["93.184.216.34"]


def _page(title: str, description: str) -> httpx.Response:
    return httpx.Response(
        200,
        text=f"<html><head><title>{title}</title>"
        f'<meta name="description" content="{description}"></head></html>',
    )


def test_robots_wildcards_and_longest_match() -> None:
    policy = parse_robots_txt(FAA_ROBOTS, UA)
    assert policy.sitemap_urls == [f"{FAA}/sitemap.xml"]
    assert policy.is_allowed(f"{FAA}/profiles/jane-doe/art/paintings")
    assert not policy.is_allowed(f"{FAA}/profiles/jane-doe/art/paintings?page=2")
    assert not policy.is_allowed(f"{FAA}/profiles/jane-doe/art/drawings")
    assert not policy.is_allowed(f"{FAA}/profiles/jane-doe/shop/cards/x")
    assert not policy.is_allowed(f"{FAA}/profiles/jane-doe?tab=blogs")
    assert policy.is_allowed(f"{FAA}/profiles/jane-doe")
    assert policy.is_allowed(f"{FAA}/featured/harvest-festival-jane-doe.html")


def test_robots_prefers_group_for_our_user_agent() -> None:
    text = "User-agent: *\nDisallow: /\n\nUser-agent: MetaSMBGTM\nDisallow: /private/\n"
    policy = parse_robots_txt(text, UA)
    assert policy.is_allowed("https://x.test/products/a")
    assert not policy.is_allowed("https://x.test/private/a")


def test_extract_page_metadata_reads_description() -> None:
    meta = extract_page_metadata(
        '<title>Golden Temple by Jane</title><meta name="description" content="Acrylic  '
        'painting of the &amp; temple">'
    )
    assert meta.title == "Golden Temple by Jane"
    assert meta.description == "Acrylic painting of the & temple"


def test_extract_page_metadata_ignores_zero_price() -> None:
    meta = extract_page_metadata(
        '<title>Utopia</title><meta property="og:price:amount" content="0.00">'
    )
    assert meta.price_hint is None


@respx.mock
async def test_profile_url_keeps_only_the_artists_links() -> None:
    respx.get(f"{FAA}/robots.txt").mock(return_value=httpx.Response(200, text=FAA_ROBOTS))
    sitemap_route = respx.get(f"{FAA}/sitemap.xml")
    respx.get(f"{FAA}/profiles/jane-doe/art/paintings").mock(
        return_value=httpx.Response(
            200, text=(FIXTURES / "marketplace_profile_page.html").read_text()
        )
    )

    async with httpx.AsyncClient() as client:
        entries, sitemaps = await collect_entries(
            f"{FAA}/profiles/jane-doe/art/paintings",
            fetch_titles=False,
            http_client=client,
            resolver=_public_resolver,
        )

    assert not sitemap_route.called
    assert sitemaps == []
    assert [e.loc for e in entries] == [
        f"{FAA}/profiles/jane-doe/collections/florals",
        f"{FAA}/featured/harvest-festival-jane-doe.html",
        f"{FAA}/featured/river-at-dawn-jane-doe.html",
    ]


@respx.mock
async def test_profile_url_disallowed_by_robots_raises() -> None:
    respx.get(f"{FAA}/robots.txt").mock(return_value=httpx.Response(200, text=FAA_ROBOTS))
    page_route = respx.get(f"{FAA}/profiles/jane-doe/art/drawings")

    async with httpx.AsyncClient() as client:
        with pytest.raises(SitemapError, match="disallows"):
            await collect_entries(
                f"{FAA}/profiles/jane-doe/art/drawings",
                http_client=client,
                resolver=_public_resolver,
            )
    assert not page_route.called


@respx.mock
async def test_url_list_only_honors_robots_and_fetches_descriptions() -> None:
    robots_route = respx.get(f"{FAA}/robots.txt").mock(
        return_value=httpx.Response(200, text=FAA_ROBOTS)
    )
    respx.get(f"{FAA}/featured/harvest-festival-jane-doe.html").mock(
        return_value=_page("Harvest Festival by Jane Doe", "Bhangra dancers at harvest time.")
    )
    respx.get("https://janedoe.example.com/robots.txt").mock(return_value=httpx.Response(404))
    respx.get("https://janedoe.example.com/gallery.html").mock(
        return_value=_page("Gallery", "Original paintings from $900.")
    )
    blocked_route = respx.get(f"{FAA}/profiles/jane-doe/art/drawings")

    async with httpx.AsyncClient() as client:
        entries, _ = await collect_entries(
            None,
            pasted_urls=[
                f"{FAA}/featured/harvest-festival-jane-doe.html",
                f"{FAA}/profiles/jane-doe/art/drawings",
                "janedoe.example.com/gallery.html",
                f"{FAA}/featured/harvest-festival-jane-doe.html",
            ],
            http_client=client,
            resolver=_public_resolver,
            rate_limiter=HostRateLimiter(0),
        )

    assert robots_route.call_count == 1
    assert not blocked_route.called
    assert [e.title for e in entries] == ["Harvest Festival by Jane Doe", "Gallery"]
    assert entries[0].description == "Bhangra dancers at harvest time."


@respx.mock
async def test_url_list_with_everything_disallowed_raises() -> None:
    respx.get(f"{FAA}/robots.txt").mock(return_value=httpx.Response(200, text=FAA_ROBOTS))

    async with httpx.AsyncClient() as client:
        with pytest.raises(SitemapError, match="the pasted URLs"):
            await collect_entries(
                None,
                pasted_urls=[f"{FAA}/profiles/jane-doe/art/drawings"],
                http_client=client,
                resolver=_public_resolver,
            )


def test_request_accepts_urls_alias_and_requires_a_source() -> None:
    request = CompetitorIntelRequest.model_validate({"urls": [f"{FAA}/featured/a.html"]})
    assert request.competitor_url is None
    assert request.pasted_urls == [f"{FAA}/featured/a.html"]

    with pytest.raises(ValidationError, match="Provide competitor_url"):
        CompetitorIntelRequest.model_validate({"urls": ["  "]})


@respx.mock
async def test_profile_redirect_to_directory_is_an_error() -> None:
    respx.get(f"{FAA}/robots.txt").mock(return_value=httpx.Response(200, text=FAA_ROBOTS))
    respx.get(f"{FAA}/profiles/wrong-slug/art/paintings").mock(
        return_value=httpx.Response(302, headers={"location": f"{FAA}/artistdirectory"})
    )
    respx.get(f"{FAA}/artistdirectory").mock(
        return_value=httpx.Response(200, text='<a href="/art/paintings/landscape">Landscape</a>')
    )

    async with httpx.AsyncClient() as client:
        with pytest.raises(SitemapError, match="redirect elsewhere"):
            await collect_entries(
                f"{FAA}/profiles/wrong-slug/art/paintings",
                http_client=client,
                resolver=_public_resolver,
            )


@respx.mock
async def test_profile_slug_matches_artwork_urls_ignoring_hyphens() -> None:
    respx.get(f"{FAA}/robots.txt").mock(return_value=httpx.Response(200, text=FAA_ROBOTS))
    respx.get(f"{FAA}/profiles/janedoe-smith/art/paintings").mock(
        return_value=httpx.Response(
            200,
            text='<a href="/art/paintings/landscape">Landscape Paintings</a>'
            '<a href="/featured/lotus-jane-doe-smith.html"><img alt="Lotus"></a>',
        )
    )

    async with httpx.AsyncClient() as client:
        entries, _ = await collect_entries(
            f"{FAA}/profiles/janedoe-smith/art/paintings",
            fetch_titles=False,
            http_client=client,
            resolver=_public_resolver,
        )

    assert [e.loc for e in entries] == [f"{FAA}/featured/lotus-jane-doe-smith.html"]
