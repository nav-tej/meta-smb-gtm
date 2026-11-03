"""Unit tests for SSRF-guarded sitemap fetching, defusedxml parsing, and HTML metadata."""

from __future__ import annotations

import gzip
from pathlib import Path

import httpx
import pytest
import respx

from src.models.intel import SitemapEntry
from src.utils.sitemap import (
    SitemapError,
    extract_html_metadata,
    fetch_sitemap,
    normalize_competitor_url,
    parse_sitemap,
    validate_safe_url,
)

FIXTURES = Path(__file__).parent / "fixtures"


async def _public_resolver(_host: str) -> list[str]:
    return ["93.184.216.34"]


def test_normalize_competitor_url() -> None:
    assert normalize_competitor_url("fineartamerica.com") == "https://fineartamerica.com/"
    assert (
        normalize_competitor_url("  HTTPS://Shop.Example.com/sitemap.xml ")
        == "https://shop.example.com/sitemap.xml"
    )
    with pytest.raises(SitemapError):
        normalize_competitor_url("ftp://example.com/sitemap.xml")
    with pytest.raises(SitemapError):
        normalize_competitor_url("   ")


def test_parse_urlset_fixture_extracts_titles_and_buckets() -> None:
    xml_bytes = (FIXTURES / "fineartamerica_sitemap.xml").read_bytes()
    parsed = parse_sitemap(xml_bytes)

    assert len(parsed) == 5
    assert all(isinstance(item, SitemapEntry) for item in parsed)
    entries = [item for item in parsed if isinstance(item, SitemapEntry)]

    first = entries[0]
    assert first.loc.endswith("coastal-sunset-watercolor-jane-doe.html")
    assert first.title == "Coastal Sunset Watercolor Canvas Print by Jane Doe"
    assert first.bucket == "products"
    assert first.lastmod is not None and first.lastmod.year == 2026

    # Entry without <image:title> falls back to humanized URL slug
    blog_entry = entries[3]
    assert blog_entry.bucket == "blogs"
    assert blog_entry.title == "Holiday Wall Art Gift Guide 2026"


def test_parse_sitemap_index_fixture() -> None:
    xml_bytes = (FIXTURES / "shopify_sitemap_index.xml").read_bytes()
    parsed = parse_sitemap(xml_bytes)

    assert parsed == [
        "https://modernprintshop.example.com/sitemap_pages_1.xml",
        "https://modernprintshop.example.com/sitemap_products_1.xml",
        "https://modernprintshop.example.com/sitemap_blogs_1.xml",
    ]


def test_parse_sitemap_blocks_xml_entity_expansion() -> None:
    billion_laughs = b"""<?xml version="1.0"?>
    <!DOCTYPE lolz [
      <!ENTITY lol "lol">
      <!ENTITY lol2 "&lol;&lol;&lol;&lol;&lol;">
    ]>
    <urlset><url><loc>https://example.com/&lol2;</loc></url></urlset>
    """
    with pytest.raises(SitemapError, match="parse sitemap XML safely"):
        parse_sitemap(billion_laughs)


def test_parse_sitemap_rejects_malformed_or_empty_xml() -> None:
    with pytest.raises(SitemapError):
        parse_sitemap(b"")
    with pytest.raises(SitemapError):
        parse_sitemap(b"<not-a-sitemap><foo/></not-a-sitemap>")
    with pytest.raises(SitemapError):
        parse_sitemap(b"<urlset><broken")


@pytest.mark.parametrize(
    "unsafe_url",
    [
        "file:///etc/passwd",
        "http://127.0.0.1/sitemap.xml",
        "http://localhost/sitemap.xml",
        "http://169.254.169.254/latest/meta-data/",
        "http://10.0.0.8/sitemap.xml",
        "http://100.100.100.200/latest/meta-data/",
        "http://[::1]/sitemap.xml",
    ],
)
async def test_ssrf_guard_blocks_internal_targets(unsafe_url: str) -> None:
    with pytest.raises(SitemapError, match="SSRF guard"):
        await validate_safe_url(unsafe_url, resolver=_public_resolver)


async def test_ssrf_guard_blocks_dns_rebinding_to_private_ip() -> None:
    async def rebinding_resolver(_host: str) -> list[str]:
        return ["192.168.1.25"]

    with pytest.raises(SitemapError, match="non-public IP"):
        await validate_safe_url(
            "https://attacker.example.com/sitemap.xml",
            resolver=rebinding_resolver,
        )


@respx.mock
async def test_fetch_sitemap_rechecks_ssrf_on_redirect() -> None:
    respx.get("https://public-shop.example.com/sitemap.xml").mock(
        return_value=httpx.Response(
            302,
            headers={"Location": "http://169.254.169.254/latest/meta-data/"},
        )
    )
    async with httpx.AsyncClient() as client:
        with pytest.raises(SitemapError, match="SSRF guard"):
            await fetch_sitemap(
                "https://public-shop.example.com/sitemap.xml",
                client,
                resolver=_public_resolver,
            )


@respx.mock
async def test_fetch_sitemap_decompresses_gzip_and_enforces_decompressed_cap() -> None:
    xml_bytes = (FIXTURES / "shopify_products.xml").read_bytes()
    gz_payload = gzip.compress(xml_bytes)

    respx.get("https://modernprintshop.example.com/sitemap_products.xml.gz").mock(
        return_value=httpx.Response(200, content=gz_payload)
    )

    async with httpx.AsyncClient() as client:
        decompressed = await fetch_sitemap(
            "https://modernprintshop.example.com/sitemap_products.xml.gz",
            client,
            resolver=_public_resolver,
        )
        assert decompressed == xml_bytes

        # Enforce strict cap against gzip bombs (compressed 283 B <= 400 B, decompressed > 400 B)
        with pytest.raises(SitemapError, match="safety limit"):
            await fetch_sitemap(
                "https://modernprintshop.example.com/sitemap_products.xml.gz",
                client,
                max_bytes=400,
                resolver=_public_resolver,
            )


def test_extract_html_metadata_reads_title_and_price_tags() -> None:
    snippet = """
    <html>
      <head>
        <title>  Ocean Mist Canvas Print &amp; Frame | CoastalShop  </title>
        <meta property="product:price:amount" content="89.00" />
        <meta property="product:price:currency" content="USD" />
      </head>
    </html>
    """
    title, price = extract_html_metadata(snippet)
    assert title == "Ocean Mist Canvas Print & Frame | CoastalShop"
    assert price == "$89.00"
