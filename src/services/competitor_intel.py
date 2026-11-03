"""Flow 1: Competitor Intel.

Crawls a competitor's public sitemap(s), derives content and product signals, and asks
Muse Spark for a content strategy brief the seller can act on.

See AGENTS.md, section 4, "Flow 1".

TODO:
- discover_sitemaps(domain): robots.txt Sitemap: lines, /sitemap.xml, /sitemap_index.xml
- crawl(domain) -> list[SitemapEntry] via src.utils.sitemap (SSRF guard, size caps, robots.txt)
- derive_signals(entries) -> CompetitorSignals: path buckets, lastmod recency, cadence, seasonality
- build_brief(signals, seller_context) -> CompetitorBrief via Muse Spark structured output
"""
