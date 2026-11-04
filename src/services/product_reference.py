"""Read one public product page and its advertised preview image, without Muse calls."""

from __future__ import annotations

import base64
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse

import httpx
from pydantic import BaseModel

from src.config import get_settings
from src.utils.sitemap import (
    DEFAULT_REQUEST_TIMEOUT,
    MAX_PRODUCT_PAGE_BYTES,
    HostRateLimiter,
    ResolverFn,
    RobotsPolicy,
    SitemapError,
    _fetch_bytes_guarded,
    extract_origin,
    extract_page_metadata,
    normalize_competitor_url,
    parse_robots_txt,
    slug_to_title,
)

MAX_IMAGE_BYTES = 1_100_000  # Base64 plus its prefix stays below 1.5 MB.
_RATE_LIMITER = HostRateLimiter()


class ProductReferenceError(Exception):
    """The product page cannot be read safely or does not allow this crawler."""


class ProductReference(BaseModel):
    """Imported facts remain hints for the seller to review before posting."""

    url: str
    title: str
    description: str
    price_hint: str | None = None
    image_data_url: str | None = None
    source_note: str


class _PreviewImageParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.images: dict[str, str] = {}

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "meta":
            return
        values = {key.lower(): value or "" for key, value in attrs}
        prop = (values.get("property") or values.get("name") or "").lower()
        content = values.get("content", "").strip()
        if prop in {"og:image", "twitter:image", "twitter:image:src"} and content:
            self.images.setdefault(prop, content)

    def image_url(self) -> str | None:
        return next(
            (
                self.images[key]
                for key in ("og:image", "twitter:image", "twitter:image:src")
                if key in self.images
            ),
            None,
        )


def _image_mime(data: bytes) -> str | None:
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return None


class ProductReferenceService:
    """Use the crawler's redirect/SSRF/size guards for page and image delivery."""

    def __init__(self, *, resolver: ResolverFn | None = None) -> None:
        self._resolver = resolver

    async def read(self, raw_url: str) -> ProductReference:
        """Import a page and at most one declared image; image failures preserve page facts."""
        try:
            url = normalize_competitor_url(raw_url)
        except (SitemapError, ValueError) as err:
            raise ProductReferenceError(str(err)) from err

        policies: dict[str, RobotsPolicy] = {}
        loading_robots = False

        async def enforce_robots(request: httpx.Request) -> None:
            nonlocal loading_robots
            if loading_robots:
                return
            target = str(request.url)
            origin = extract_origin(target)
            if origin not in policies:
                loading_robots = True
                try:
                    status, body, _ = await _fetch_bytes_guarded(
                        f"{origin}/robots.txt",
                        client,
                        max_bytes=512 * 1024,
                        truncate_on_limit=True,
                        resolver=self._resolver,
                        rate_limiter=_RATE_LIMITER,
                    )
                    if status in {404, 410}:
                        policy = RobotsPolicy()
                    elif status == 200:
                        policy = parse_robots_txt(
                            body.decode("utf-8", errors="replace"),
                            get_settings().crawler_user_agent,
                        )
                    else:
                        raise SitemapError("This site did not allow its crawler rules to be read.")
                    policies[origin] = policy
                finally:
                    loading_robots = False
            if not policies[origin].is_allowed(target):
                raise SitemapError("This page is blocked by the site's robots.txt rules.")

        async with httpx.AsyncClient(
            timeout=DEFAULT_REQUEST_TIMEOUT,
            event_hooks={"request": [enforce_robots]},
        ) as client:
            try:
                status, body, final_url = await _fetch_bytes_guarded(
                    url,
                    client,
                    max_bytes=MAX_PRODUCT_PAGE_BYTES,
                    truncate_on_limit=True,
                    resolver=self._resolver,
                    rate_limiter=_RATE_LIMITER,
                )
                if status != 200 or not body:
                    raise SitemapError(f"The product page could not be read (HTTP {status}).")
            except (SitemapError, httpx.InvalidURL, ValueError) as err:
                raise ProductReferenceError(str(err)) from err

            page = body.decode("utf-8", errors="replace")
            metadata = extract_page_metadata(page)
            result = ProductReference(
                url=final_url,
                title=metadata.title or slug_to_title(final_url) or "Imported item",
                description=metadata.description or "",
                price_hint=metadata.price_hint,
                source_note=(
                    "Imported from the public listing. Review the item and offer; add its photo."
                ),
            )
            parser = _PreviewImageParser()
            parser.feed(page)
            advertised_image = parser.image_url()
            if not advertised_image:
                return result
            image_url = urljoin(final_url, advertised_image)
            if urlparse(image_url).scheme.lower() not in {"http", "https"}:
                return result
            try:
                image_status, image, _ = await _fetch_bytes_guarded(
                    image_url,
                    client,
                    max_bytes=MAX_IMAGE_BYTES,
                    resolver=self._resolver,
                    rate_limiter=_RATE_LIMITER,
                )
                mime = _image_mime(image) if image_status == 200 else None
                if mime is not None:
                    encoded = base64.b64encode(image).decode("ascii")
                    result.image_data_url = f"data:{mime};base64,{encoded}"
                    result.source_note = (
                        "Photo and details imported from the public listing. "
                        "Check they match the item and current offer."
                    )
            except (SitemapError, httpx.InvalidURL, ValueError):
                result.source_note = (
                    "Listing details imported. Its photo could not be imported safely; add a photo."
                )
            return result
