"""Sitemap discovery, SSRF-guarded fetching, and safe XML/HTML parsing helpers.

Parses XML exclusively with `defusedxml` (never `xml.etree` on untrusted bytes).
Handles `<urlset>`, `<sitemapindex>`, gzipped sitemaps, `robots.txt` rules, and HTML
`<title>` / listing fallback extraction while enforcing SSRF, redirect, and size guards.
"""

from __future__ import annotations

import asyncio
import html
import ipaddress
import logging
import re
import socket
import time
import zlib
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Literal
from urllib.parse import urljoin, urlparse, urlunparse
from xml.etree.ElementTree import Element  # Type annotation only; parsing uses defusedxml

import httpx
from defusedxml import DefusedXmlException
from defusedxml import ElementTree as SafeET

from src.config import get_settings
from src.models.intel import SitemapEntry, UrlBucket

logger = logging.getLogger(__name__)

MAX_SITEMAP_BYTES = 10 * 1024 * 1024  # 10 MB cap (raw and gzip-decompressed)
MAX_HTML_HEAD_BYTES = 64 * 1024  # 64 KB cap when reading <head>/<title>
MAX_LISTING_FALLBACK_BYTES = 256 * 1024  # 256 KB cap for no-sitemap shop page fallback
MAX_REDIRECTS = 5
DEFAULT_REQUEST_TIMEOUT = httpx.Timeout(15.0, connect=5.0)

ResolverFn = Callable[[str], Awaitable[list[str]]]

_BLOCKED_HOSTNAMES = frozenset(
    {
        "localhost",
        "localhost.localdomain",
        "metadata",
        "metadata.google.internal",
        "instance-data",
    }
)
_CGNAT_NETWORK = ipaddress.ip_network("100.64.0.0/10")

_TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)
_META_TAG_RE = re.compile(r"<meta\s+([^>]+)>", re.IGNORECASE)
_ATTR_RE = re.compile(r"""([a-zA-Z0-9_:-]+)\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s"'>]+))""")
_ANCHOR_RE = re.compile(
    r"""<a\s+[^>]*href\s*=\s*(?:"([^"]+)"|'([^']+)')[^>]*>(.*?)</a>""",
    re.IGNORECASE | re.DOTALL,
)
_HTML_TAG_RE = re.compile(r"<[^>]+>")
_PRICE_TEXT_RE = re.compile(r"(?:USD\s*\$|\$|£|€)\s?\d{1,5}(?:,\d{3})*(?:\.\d{2})?")


class SitemapError(Exception):
    """Raised when sitemap discovery, SSRF validation, fetching, or XML parsing fails."""


@dataclass(slots=True)
class ParsedSitemap:
    """Discriminated result from parsing a sitemap XML document."""

    kind: Literal["index", "urlset"]
    child_sitemaps: list[str] = field(default_factory=list)
    entries: list[SitemapEntry] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class RobotsRule:
    allow: bool
    pattern: re.Pattern[str]
    length: int


@dataclass(slots=True)
class RobotsPolicy:
    """Parsed `robots.txt` directives for a competitor origin.

    Matching follows RFC 9309 (`*` and `$` wildcards, longest match wins, Allow wins ties).
    `urllib.robotparser` treats `*` literally, so rules like `/profiles/*/art/*` would be ignored.
    """

    sitemap_urls: list[str] = field(default_factory=list)
    rules: list[RobotsRule] = field(default_factory=list)
    user_agent: str = "*"

    def is_allowed(self, url: str) -> bool:
        parsed = urlparse(url)
        target = (parsed.path or "/") + (f"?{parsed.query}" if parsed.query else "")
        best: RobotsRule | None = None
        for rule in self.rules:
            if not rule.pattern.match(target):
                continue
            if best is None or (rule.length, rule.allow) > (best.length, best.allow):
                best = rule
        return best is None or best.allow


def _compile_robots_pattern(path_pattern: str) -> re.Pattern[str]:
    anchored = path_pattern.endswith("$")
    body = path_pattern[:-1] if anchored else path_pattern
    regex = ".*".join(re.escape(part) for part in body.split("*"))
    return re.compile(regex + ("$" if anchored else ""))


def parse_robots_txt(text: str, user_agent: str) -> RobotsPolicy:
    """Parse robots.txt, applying the group for our product token if present, else `*`."""
    token = user_agent.split("/", 1)[0].strip().lower()
    groups: list[tuple[list[str], list[RobotsRule]]] = []
    sitemap_urls: list[str] = []
    agents: list[str] = []
    rules: list[RobotsRule] = []
    in_rules = False

    for raw_line in text.splitlines():
        line = raw_line.split("#", 1)[0].strip()
        if ":" not in line:
            continue
        key, value = (part.strip() for part in line.split(":", 1))
        key = key.lower()
        if key == "sitemap":
            if value.startswith(("http://", "https://")) and value not in sitemap_urls:
                sitemap_urls.append(value)
        elif key == "user-agent":
            if in_rules:
                groups.append((agents, rules))
                agents, rules, in_rules = [], [], False
            agents.append(value.lower())
        elif key in {"allow", "disallow"}:
            in_rules = True
            if agents and value:
                rules.append(RobotsRule(key == "allow", _compile_robots_pattern(value), len(value)))
    if agents:
        groups.append((agents, rules))

    specific = [rs for names, rs in groups if token in names]
    chosen = specific or [rs for names, rs in groups if "*" in names]
    return RobotsPolicy(
        sitemap_urls=sitemap_urls,
        rules=[rule for rs in chosen for rule in rs],
        user_agent=user_agent,
    )


class HostRateLimiter:
    """Simple per-host async rate limiter for polite crawling."""

    def __init__(self, min_interval_seconds: float = 0.05) -> None:
        self._min_interval = min_interval_seconds
        self._locks: dict[str, asyncio.Lock] = {}
        self._last_request_at: dict[str, float] = {}

    async def wait(self, host: str) -> None:
        if self._min_interval <= 0:
            return
        key = host.lower()
        lock = self._locks.setdefault(key, asyncio.Lock())
        async with lock:
            now = time.monotonic()
            last = self._last_request_at.get(key)
            if last is not None:
                elapsed = now - last
                if elapsed < self._min_interval:
                    await asyncio.sleep(self._min_interval - elapsed)
            self._last_request_at[key] = time.monotonic()


def normalize_competitor_url(raw_url: str) -> str:
    """Normalize a bare domain or URL (e.g. `fineartamerica.com`) into a full `https://` URL."""
    cleaned = raw_url.strip()
    if not cleaned:
        raise SitemapError("Competitor URL must not be empty.")
    if "://" not in cleaned:
        cleaned = f"https://{cleaned}"
    parsed = urlparse(cleaned)
    if parsed.scheme.lower() not in {"http", "https"}:
        raise SitemapError(f"Unsupported URL scheme '{parsed.scheme}'. Only http/https allowed.")
    if not parsed.hostname:
        raise SitemapError(f"Invalid URL '{raw_url}': missing hostname.")
    normalized_path = parsed.path or "/"
    return urlunparse(
        (
            parsed.scheme.lower(),
            parsed.netloc.lower(),
            normalized_path,
            "",
            parsed.query,
            "",
        )
    )


def extract_origin(url: str) -> str:
    """Return `scheme://netloc` for a normalized URL."""
    parsed = urlparse(normalize_competitor_url(url))
    return f"{parsed.scheme}://{parsed.netloc}"


def _is_disallowed_ip(raw_ip: str) -> bool:
    """Return True if an IP falls in private, loopback, link-local, metadata, or reserved space."""
    # Strip IPv6 zone IDs if any (e.g. fe80::1%lo0)
    ip_part = raw_ip.split("%", 1)[0]
    addr = ipaddress.ip_address(ip_part)
    if (
        addr.is_private
        or addr.is_loopback
        or addr.is_link_local
        or addr.is_multicast
        or addr.is_reserved
        or addr.is_unspecified
        or not addr.is_global
    ):
        return True
    return isinstance(addr, ipaddress.IPv4Address) and addr in _CGNAT_NETWORK


async def default_resolve_host(hostname: str) -> list[str]:
    """Resolve `hostname` via the event loop's non-blocking `getaddrinfo`."""
    loop = asyncio.get_running_loop()
    try:
        infos = await loop.getaddrinfo(hostname, None, type=socket.SOCK_STREAM)
    except socket.gaierror as err:
        raise SitemapError(f"Could not resolve hostname '{hostname}': {err}") from err
    ips = [str(info[4][0]) for info in infos if info[4]]
    if not ips:
        raise SitemapError(f"Hostname '{hostname}' resolved to zero IP addresses.")
    return ips


async def validate_safe_url(url: str, *, resolver: ResolverFn | None = None) -> str:
    """Validate scheme, hostname, and resolved IPs against SSRF rules."""
    parsed = urlparse(url.strip())
    scheme = parsed.scheme.lower()
    if scheme not in {"http", "https"}:
        raise SitemapError(f"SSRF guard blocked non-HTTP scheme '{scheme}'.")

    hostname = (parsed.hostname or "").strip().lower().rstrip(".")
    if not hostname:
        raise SitemapError("SSRF guard blocked URL with empty hostname.")

    if (
        hostname in _BLOCKED_HOSTNAMES
        or hostname.endswith(".localhost")
        or hostname.endswith(".local")
        or hostname.endswith(".internal")
    ):
        raise SitemapError(f"SSRF guard blocked internal hostname '{hostname}'.")

    # Check IP literals directly without DNS
    try:
        ipaddress.ip_address(hostname)
        is_ip_literal = True
    except ValueError:
        is_ip_literal = False

    if is_ip_literal:
        if _is_disallowed_ip(hostname):
            raise SitemapError(f"SSRF guard blocked disallowed IP address '{hostname}'.")
        return url

    resolve = resolver or default_resolve_host
    resolved_ips = await resolve(hostname)
    if not resolved_ips:
        raise SitemapError(f"Hostname '{hostname}' returned no IP addresses.")

    for ip_str in resolved_ips:
        try:
            disallowed = _is_disallowed_ip(ip_str)
        except ValueError as err:
            raise SitemapError(f"Invalid IP '{ip_str}' resolved for '{hostname}'.") from err
        if disallowed:
            raise SitemapError(
                f"SSRF guard blocked '{hostname}' resolving to non-public IP '{ip_str}'."
            )

    return url


def _is_gzip_payload(url: str, raw_bytes: bytes) -> bool:
    path = urlparse(url).path.lower()
    return path.endswith(".gz") or raw_bytes[:2] == b"\x1f\x8b"


def _decompress_gzip_bounded(compressed: bytes, max_bytes: int) -> bytes:
    """Decompress gzip payload while strictly capping decompressed output size."""
    decompressor = zlib.decompressobj(16 + zlib.MAX_WBITS)
    try:
        output = decompressor.decompress(compressed, max_length=max_bytes + 1)
        if not decompressor.unconsumed_tail:
            output += decompressor.flush(max_bytes + 1 - len(output))
    except zlib.error as err:
        raise SitemapError(f"Invalid gzip sitemap payload: {err}") from err

    if len(output) > max_bytes or decompressor.unconsumed_tail:
        raise SitemapError(f"Decompressed gzip sitemap exceeded {max_bytes} byte safety limit.")
    return output


async def _fetch_bytes_guarded(
    url: str,
    client: httpx.AsyncClient,
    *,
    max_bytes: int,
    truncate_on_limit: bool = False,
    resolver: ResolverFn | None = None,
    rate_limiter: HostRateLimiter | None = None,
    user_agent: str | None = None,
) -> tuple[int, bytes, str]:
    """Fetch `url` with SSRF validation on initial hop and every redirect.

    Returns `(status_code, body_bytes, final_url)`.
    """
    ua = user_agent or get_settings().crawler_user_agent
    current_url = await validate_safe_url(url, resolver=resolver)

    for _hop in range(MAX_REDIRECTS + 1):
        host = urlparse(current_url).hostname or ""
        if rate_limiter is not None and host:
            await rate_limiter.wait(host)

        try:
            async with client.stream(
                "GET",
                current_url,
                headers={"User-Agent": ua, "Accept-Encoding": "identity"},
                follow_redirects=False,
            ) as response:
                if response.is_redirect:
                    location = response.headers.get("location")
                    if not location:
                        raise SitemapError(f"Redirect from '{current_url}' missing Location.")
                    next_url = urljoin(current_url, location.strip())
                    current_url = await validate_safe_url(next_url, resolver=resolver)
                    continue

                status = response.status_code
                if status >= 400:
                    return status, b"", current_url

                content_length = response.headers.get("content-length")
                if (
                    not truncate_on_limit
                    and content_length
                    and content_length.isdigit()
                    and int(content_length) > max_bytes
                ):
                    raise SitemapError(
                        f"Response at '{current_url}' declared {content_length} bytes "
                        f"(exceeds {max_bytes} limit)."
                    )

                chunks: list[bytes] = []
                total = 0
                async for chunk in response.aiter_bytes(chunk_size=16_384):
                    total += len(chunk)
                    if total > max_bytes:
                        if truncate_on_limit:
                            overflow = total - max_bytes
                            keep = chunk[:-overflow] if overflow < len(chunk) else b""
                            if keep:
                                chunks.append(keep)
                            break
                        raise SitemapError(
                            f"Response from '{current_url}' exceeded {max_bytes} byte limit."
                        )
                    chunks.append(chunk)

                return status, b"".join(chunks), current_url
        except httpx.HTTPError as err:
            raise SitemapError(f"HTTP error fetching '{current_url}': {err}") from err

    raise SitemapError(f"Exceeded maximum redirects ({MAX_REDIRECTS}) fetching '{url}'.")


async def fetch_sitemap(
    url: str,
    client: httpx.AsyncClient,
    *,
    max_bytes: int = MAX_SITEMAP_BYTES,
    resolver: ResolverFn | None = None,
    rate_limiter: HostRateLimiter | None = None,
) -> bytes:
    """Fetch a sitemap URL with SSRF guard, redirect re-validation, size cap, and gunzip."""
    status, raw_bytes, final_url = await _fetch_bytes_guarded(
        url,
        client,
        max_bytes=max_bytes,
        truncate_on_limit=False,
        resolver=resolver,
        rate_limiter=rate_limiter,
    )
    if status != 200:
        raise SitemapError(f"Failed to fetch sitemap '{url}' (HTTP {status}).")

    if _is_gzip_payload(final_url, raw_bytes):
        return _decompress_gzip_bounded(raw_bytes, max_bytes=max_bytes)
    return raw_bytes


async def fetch_robots_policy(
    origin: str,
    client: httpx.AsyncClient,
    *,
    resolver: ResolverFn | None = None,
    rate_limiter: HostRateLimiter | None = None,
) -> RobotsPolicy:
    """Fetch and parse `/robots.txt` for `origin`, extracting `Sitemap:` URLs and disallow rules."""
    ua = get_settings().crawler_user_agent
    robots_url = f"{origin.rstrip('/')}/robots.txt"
    try:
        status, body, _ = await _fetch_bytes_guarded(
            robots_url,
            client,
            max_bytes=512 * 1024,
            truncate_on_limit=True,
            resolver=resolver,
            rate_limiter=rate_limiter,
            user_agent=ua,
        )
    except SitemapError as err:
        logger.debug("Could not fetch robots.txt at %s: %s", robots_url, err)
        return RobotsPolicy(user_agent=ua)

    if status != 200 or not body:
        return RobotsPolicy(user_agent=ua)

    return parse_robots_txt(body.decode("utf-8", errors="replace"), ua)


def _local_name(tag: str) -> str:
    """Strip `{namespace}` prefix from an ElementTree tag."""
    if "}" in tag:
        return tag.rsplit("}", 1)[1].lower()
    return tag.lower()


def _parse_lastmod(raw_value: str | None) -> datetime | None:
    """Parse common ISO-8601 sitemap `<lastmod>` formats into a UTC-aware datetime."""
    if not raw_value:
        return None
    cleaned = raw_value.strip()
    if not cleaned:
        return None
    normalized = cleaned[:-1] + "+00:00" if cleaned.endswith("Z") else cleaned
    try:
        dt = datetime.fromisoformat(normalized)
    except ValueError:
        # Handle YYYY-MM-DD prefix if trailing garbage exists
        try:
            dt = datetime.strptime(cleaned[:10], "%Y-%m-%d")
        except ValueError:
            return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def classify_url_bucket(url: str) -> UrlBucket:
    """Classify a URL path into an e-commerce / content bucket."""
    path = urlparse(url).path.lower()
    segments = [seg for seg in path.split("/") if seg]
    if not segments:
        return "other"

    first = segments[0]
    # Etsy listings
    if first in {"listing", "listings"} or "/listing/" in path:
        return "listings"
    # Shopify, WooCommerce, FineArtAmerica (/featured/, /products/, /art/, /prints/)
    if first in {"products", "product", "featured", "art", "prints", "item", "items", "merch"} or (
        "/products/" in path
    ):
        return "products"
    if first in {
        "collections",
        "collection",
        "category",
        "categories",
        "product-category",
        "shop",
        "profiles",
        "galleries",
    }:
        return "collections"
    if first in {"blogs", "blog", "news", "journal", "articles", "article", "posts", "guides"}:
        return "blogs"
    if first in {"pages", "page", "about", "contact", "faq", "shipping", "pricing", "policies"}:
        return "pages"
    return "other"


def slug_to_title(url: str) -> str | None:
    """Derive a clean readable title fallback from the last meaningful URL path segment."""
    path = urlparse(url).path.rstrip("/")
    if not path or path == "/":
        return None
    slug = path.rsplit("/", 1)[-1]
    for ext in (".html", ".htm", ".php", ".aspx"):
        if slug.lower().endswith(ext):
            slug = slug[: -len(ext)]
            break
    cleaned = re.sub(r"[-_+]+", " ", slug).strip()
    if not cleaned or cleaned.isdigit():
        return None
    return cleaned.title()[:160]


def _extract_nested_title(url_elem: Element) -> str | None:
    """Extract `<image:title>` or `<news:title>` from a `<url>` element when present."""
    for child in url_elem:
        child_name = _local_name(child.tag)
        if child_name in {"image", "news"}:
            for sub in child:
                if _local_name(sub.tag) == "title" and sub.text and sub.text.strip():
                    return " ".join(html.unescape(sub.text).split())[:200]
    return None


def parse_sitemap_document(xml_bytes: bytes, *, max_urls: int | None = None) -> ParsedSitemap:
    """Safely parse a `<sitemapindex>` or `<urlset>` XML payload using `defusedxml`."""
    cap = max_urls if max_urls is not None else get_settings().crawler_max_urls
    if not xml_bytes or not xml_bytes.strip():
        raise SitemapError("Sitemap XML payload is empty.")

    try:
        root: Element = SafeET.fromstring(xml_bytes.lstrip())
    except (DefusedXmlException, SafeET.ParseError) as err:
        raise SitemapError(f"Failed to parse sitemap XML safely: {err}") from err

    root_name = _local_name(root.tag)
    if root_name == "sitemapindex":
        children: list[str] = []
        seen_children: set[str] = set()
        for child in root:
            if _local_name(child.tag) != "sitemap":
                continue
            loc_text: str | None = None
            for sub in child:
                if _local_name(sub.tag) == "loc" and sub.text:
                    loc_text = sub.text.strip()
                    break
            if (
                loc_text
                and loc_text.startswith(("http://", "https://"))
                and loc_text not in seen_children
            ):
                seen_children.add(loc_text)
                children.append(loc_text)
                if len(children) >= cap:
                    break
        return ParsedSitemap(kind="index", child_sitemaps=children)

    if root_name == "urlset":
        entries: list[SitemapEntry] = []
        seen_locs: set[str] = set()
        for url_elem in root:
            if _local_name(url_elem.tag) != "url":
                continue
            loc: str | None = None
            lastmod_raw: str | None = None
            changefreq: str | None = None
            priority: float | None = None

            for sub in url_elem:
                sub_name = _local_name(sub.tag)
                text = sub.text.strip() if sub.text else ""
                if not text:
                    continue
                if sub_name == "loc":
                    loc = text
                elif sub_name == "lastmod":
                    lastmod_raw = text
                elif sub_name == "changefreq":
                    changefreq = text.lower()
                elif sub_name == "priority":
                    try:
                        priority = float(text)
                    except ValueError:
                        priority = None

            if not loc or not loc.startswith(("http://", "https://")) or loc in seen_locs:
                continue

            seen_locs.add(loc)
            embedded_title = _extract_nested_title(url_elem) or slug_to_title(loc)
            entries.append(
                SitemapEntry(
                    loc=loc,
                    lastmod=_parse_lastmod(lastmod_raw),
                    changefreq=changefreq,
                    priority=priority,
                    title=embedded_title,
                    bucket=classify_url_bucket(loc),
                )
            )
            if len(entries) >= cap:
                break
        return ParsedSitemap(kind="urlset", entries=entries)

    raise SitemapError(
        f"Unrecognized sitemap root element '<{root_name}>' (expected urlset or sitemapindex)."
    )


def parse_sitemap(
    xml_bytes: bytes, *, max_urls: int | None = None
) -> list[SitemapEntry] | list[str]:
    """Parse sitemap XML into `list[str]` (for `<sitemapindex>`) or `list[SitemapEntry]`."""
    doc = parse_sitemap_document(xml_bytes, max_urls=max_urls)
    if doc.kind == "index":
        return doc.child_sitemaps
    return doc.entries


@dataclass(slots=True)
class PageMetadata:
    title: str | None = None
    price_hint: str | None = None
    description: str | None = None


def extract_html_metadata(html_text: str) -> tuple[str | None, str | None]:
    """Extract `(page_title, price_hint)` from an HTML `<head>` / top-of-page snippet."""
    metadata = extract_page_metadata(html_text)
    return metadata.title, metadata.price_hint


def extract_page_metadata(html_text: str) -> PageMetadata:
    """Extract title, price hint, and meta description from an HTML `<head>` snippet."""
    title: str | None = None
    title_match = _TITLE_RE.search(html_text)
    if title_match:
        collapsed = " ".join(html.unescape(title_match.group(1)).split())
        if collapsed:
            title = collapsed[:200]

    meta_amount: str | None = None
    meta_currency: str | None = None
    og_title: str | None = None
    meta_desc: str | None = None
    og_desc: str | None = None

    for tag_match in _META_TAG_RE.finditer(html_text):
        attrs: dict[str, str] = {}
        for attr_match in _ATTR_RE.finditer(tag_match.group(1)):
            key = attr_match.group(1).lower()
            val = attr_match.group(2) or attr_match.group(3) or attr_match.group(4) or ""
            attrs[key] = html.unescape(val).strip()

        prop = (attrs.get("property") or attrs.get("name") or "").lower()
        content = attrs.get("content", "")
        if not content:
            continue
        if prop in {"product:price:amount", "og:price:amount"} and not meta_amount:
            # Marketplaces publish 0.00 for works that aren't for sale in that format
            if re.fullmatch(r"0+(?:\.0+)?", content.replace(",", "")) is None:
                meta_amount = content
        elif prop in {"product:price:currency", "og:price:currency"} and not meta_currency:
            meta_currency = content.upper()
        elif prop == "og:title" and not og_title:
            og_title = " ".join(content.split())[:200]
        elif prop == "description" and not meta_desc:
            meta_desc = " ".join(content.split())[:300]
        elif prop == "og:description" and not og_desc:
            og_desc = " ".join(content.split())[:300]

    final_title = title or og_title
    price_hint: str | None = None
    if meta_amount:
        symbol = "$" if meta_currency in {None, "", "USD"} else f"{meta_currency} "
        price_hint = f"{symbol}{meta_amount}".strip()
    else:
        haystack = " ".join(part for part in (final_title, meta_desc) if part)
        price_match = _PRICE_TEXT_RE.search(haystack)
        if price_match:
            price_hint = price_match.group(0).strip()

    return PageMetadata(title=final_title, price_hint=price_hint, description=meta_desc or og_desc)


async def fetch_page_metadata(
    url: str,
    client: httpx.AsyncClient,
    *,
    resolver: ResolverFn | None = None,
    rate_limiter: HostRateLimiter | None = None,
) -> PageMetadata:
    """Politely fetch the first 64 KB of `url` and return its title, price hint, and description."""
    try:
        status, snippet_bytes, _ = await _fetch_bytes_guarded(
            url,
            client,
            max_bytes=MAX_HTML_HEAD_BYTES,
            truncate_on_limit=True,
            resolver=resolver,
            rate_limiter=rate_limiter,
        )
    except SitemapError as err:
        logger.debug("Skipping metadata fetch for %s: %s", url, err)
        return PageMetadata()

    if status != 200 or not snippet_bytes:
        return PageMetadata()

    return extract_page_metadata(snippet_bytes.decode("utf-8", errors="replace"))


async def crawl_listing_page_fallback(
    shop_url: str,
    client: httpx.AsyncClient,
    *,
    robots: RobotsPolicy | None = None,
    max_urls: int = 200,
    resolver: ResolverFn | None = None,
    rate_limiter: HostRateLimiter | None = None,
    require_path_prefix: str | None = None,
) -> list[SitemapEntry]:
    """Fallback for Etsy/FineArtAmerica shop pages without a dedicated per-shop sitemap.

    With `require_path_prefix`, returns nothing if the page redirected elsewhere (marketplaces
    send unknown profiles to a directory page whose links would be mistaken for the seller's).
    """
    if robots is not None and not robots.is_allowed(shop_url):
        return []

    status, raw_bytes, final_url = await _fetch_bytes_guarded(
        shop_url,
        client,
        max_bytes=MAX_LISTING_FALLBACK_BYTES,
        truncate_on_limit=True,
        resolver=resolver,
        rate_limiter=rate_limiter,
    )
    if status != 200 or not raw_bytes:
        return []
    if require_path_prefix and not urlparse(final_url).path.startswith(require_path_prefix):
        logger.info("%s redirected to %s; ignoring its links", shop_url, final_url)
        return []

    html_text = raw_bytes.decode("utf-8", errors="replace")
    base_host = (urlparse(final_url).hostname or "").lower()
    entries: list[SitemapEntry] = []
    seen: set[str] = set()

    for match in _ANCHOR_RE.finditer(html_text):
        raw_href = (match.group(1) or match.group(2) or "").strip()
        if not raw_href or raw_href.startswith(("#", "javascript:", "mailto:", "tel:")):
            continue
        resolved = urljoin(final_url, html.unescape(raw_href))
        parsed = urlparse(resolved)
        if parsed.scheme.lower() not in {"http", "https"}:
            continue
        link_host = (parsed.hostname or "").lower()
        if link_host != base_host and not link_host.endswith(f".{base_host}"):
            continue

        clean_loc = urlunparse(
            (parsed.scheme.lower(), parsed.netloc.lower(), parsed.path or "/", "", "", "")
        )
        if clean_loc in seen or clean_loc.rstrip("/") == final_url.rstrip("/"):
            continue
        if robots is not None and not robots.is_allowed(clean_loc):
            continue

        seen.add(clean_loc)
        anchor_text = " ".join(html.unescape(_HTML_TAG_RE.sub(" ", match.group(3))).split())
        price_match = _PRICE_TEXT_RE.search(anchor_text)
        price_hint = price_match.group(0).strip() if price_match else None
        title = anchor_text[:160] if anchor_text else slug_to_title(clean_loc)

        entries.append(
            SitemapEntry(
                loc=clean_loc,
                title=title,
                price_hint=price_hint,
                bucket=classify_url_bucket(clean_loc),
            )
        )
        if len(entries) >= max_urls:
            break

    return entries
