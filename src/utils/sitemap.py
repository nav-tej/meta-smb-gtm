"""Sitemap discovery and parsing helpers.

Parses with defusedxml only. Handles <urlset> and <sitemapindex>, gzip sitemaps, and enforces
size, depth, and URL-count limits. Fetching goes through an SSRF-guarded httpx client.

TODO:
- SitemapError
- parse_sitemap(xml_bytes) -> list[SitemapEntry] | list[str] (index children)
- fetch_sitemap(url, client) -> bytes (with SSRF guard + size cap)
"""
