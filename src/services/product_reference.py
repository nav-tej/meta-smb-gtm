"""Read one public product page and its advertised preview image, without Muse calls."""

from __future__ import annotations

import base64
import io
import json
import re
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse

import httpx
from PIL import Image, UnidentifiedImageError
from pydantic import BaseModel, Field

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
MAX_IMAGE_CANDIDATES = 6
MAX_IMAGE_PIXELS = 25_000_000
MIN_CANDIDATE_DIMENSION = 120
LOW_RES_MIN_EDGE = 600
LOW_RES_MAX_EDGE = 800
_RATE_LIMITER = HostRateLimiter()

_SKIP_IMAGE_TOKEN_RE = re.compile(
    r"(logo|favicon|icon|avatar|badge|spinner|sprite|pixel|tracking|analytics|spacer|1x1|blank|placeholder)",
    re.IGNORECASE,
)
_SKIP_EXT_RE = re.compile(r"\.(svg|gif|ico)(?:[?#]|$)", re.IGNORECASE)
_PRODUCT_LD_TYPES = {
    "product",
    "visualartwork",
    "painting",
    "artwork",
    "creativework",
    "photograph",
    "sculpture",
}


class ProductReferenceError(Exception):
    """The product page cannot be read safely or does not allow this crawler."""


class ProductImageCandidate(BaseModel):
    """One verified, export-safe image candidate discovered on a seller page."""

    id: str
    image_data_url: str
    source_url: str
    image_url: str
    title: str
    alt: str = ""
    width: int | None = None
    height: int | None = None
    is_low_res: bool = False
    provenance: str = "website"


class ProductReference(BaseModel):
    """Imported facts remain hints for the seller to review before posting."""

    url: str
    title: str
    description: str
    price_hint: str | None = None
    image_data_url: str | None = None
    image_width: int | None = None
    image_height: int | None = None
    is_low_res: bool = False
    image_candidates: list[ProductImageCandidate] = Field(default_factory=list)
    source_note: str


def _parse_html_dim(raw: str | None) -> int | None:
    if not raw:
        return None
    m = re.match(r"^\s*(\d+)", str(raw))
    if not m:
        return None
    val = int(m.group(1))
    return val if val > 0 else None


def _is_relevant_image_url(url: str, *, alt: str = "", cls: str = "", elem_id: str = "") -> bool:
    clean = (url or "").strip()
    if not clean or clean.lower().startswith("data:"):
        return False
    if _SKIP_EXT_RE.search(clean):
        return False
    combined = f"{clean} {cls} {elem_id}".strip()
    if _SKIP_IMAGE_TOKEN_RE.search(combined):
        return False
    return not (alt and _SKIP_IMAGE_TOKEN_RE.search(alt) and "artwork" not in alt.lower())


def _extract_ld_images(node: object, out: list[tuple[str, str]]) -> None:
    if isinstance(node, list):
        for item in node:
            _extract_ld_images(item, out)
        return
    if not isinstance(node, dict):
        return
    raw_type = node.get("@type")
    types = [raw_type] if isinstance(raw_type, str) else list(raw_type or [])
    type_names = {str(t).split("/")[-1].lower() for t in types}
    if type_names & _PRODUCT_LD_TYPES:
        title = str(node.get("name") or "").strip()
        imgs = node.get("image")
        if isinstance(imgs, str):
            out.append((imgs.strip(), title))
        elif isinstance(imgs, list):
            for im in imgs:
                if isinstance(im, str):
                    out.append((im.strip(), title))
                elif isinstance(im, dict):
                    u = str(im.get("url") or im.get("contentUrl") or "").strip()
                    if u:
                        out.append((u, str(im.get("caption") or title).strip()))
        elif isinstance(imgs, dict):
            u = str(imgs.get("url") or imgs.get("contentUrl") or "").strip()
            if u:
                out.append((u, str(imgs.get("caption") or title).strip()))
    if "@graph" in node:
        _extract_ld_images(node["@graph"], out)


class _PreviewImageParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.images: dict[str, str] = {}
        self.ld_candidates: list[tuple[str, str]] = []
        self.img_candidates: list[tuple[str, str]] = []
        self._in_ld_json = False
        self._ld_chunks: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag_l = tag.lower()
        values = {key.lower(): value or "" for key, value in attrs}
        if tag_l == "script" and "ld+json" in values.get("type", "").lower():
            self._in_ld_json = True
            self._ld_chunks = []
            return
        if tag_l == "meta":
            prop = (values.get("property") or values.get("name") or "").lower()
            content = values.get("content", "").strip()
            if (
                prop in {"og:image", "og:image:secure_url", "twitter:image", "twitter:image:src"}
                and content
            ):
                self.images.setdefault(prop, content)
            return
        if tag_l == "img":
            src = (
                values.get("data-src") or values.get("data-lazy-src") or values.get("src") or ""
            ).strip()
            if not src and values.get("srcset"):
                first_part = values["srcset"].split(",")[0].strip()
                src = first_part.split()[0].strip() if first_part else ""
            alt = values.get("alt", "").strip()
            cls = values.get("class", "")
            elem_id = values.get("id", "")
            w = _parse_html_dim(values.get("width"))
            h = _parse_html_dim(values.get("height"))
            if (w is not None and w <= 80) or (h is not None and h <= 80):
                return
            if w and h and max(w / h, h / w) > 4.0:
                return
            if _is_relevant_image_url(src, alt=alt, cls=cls, elem_id=elem_id):
                self.img_candidates.append((src, alt))

    def handle_data(self, data: str) -> None:
        if self._in_ld_json:
            self._ld_chunks.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "script" and self._in_ld_json:
            self._in_ld_json = False
            raw = "".join(self._ld_chunks).strip()
            self._ld_chunks = []
            if raw:
                try:
                    parsed = json.loads(raw)
                    _extract_ld_images(parsed, self.ld_candidates)
                except (ValueError, TypeError):
                    pass

    def image_url(self) -> str | None:
        return next(
            (
                self.images[key]
                for key in (
                    "og:image",
                    "og:image:secure_url",
                    "twitter:image",
                    "twitter:image:src",
                )
                if key in self.images
            ),
            None,
        )

    def ordered_candidates(self, base_url: str, fallback_title: str) -> list[tuple[str, str]]:
        seen: set[str] = set()
        ordered: list[tuple[str, str]] = []

        def _add(raw_src: str, label: str) -> None:
            if not raw_src or raw_src.lower().startswith("data:"):
                return
            resolved = urljoin(base_url, raw_src)
            if urlparse(resolved).scheme.lower() not in {"http", "https"}:
                return
            if _SKIP_EXT_RE.search(resolved):
                return
            if resolved in seen:
                return
            seen.add(resolved)
            ordered.append((resolved, label.strip() or fallback_title))

        for src, label in self.ld_candidates:
            if _is_relevant_image_url(src, alt=label):
                _add(src, label)
        for key in ("og:image", "og:image:secure_url", "twitter:image", "twitter:image:src"):
            if key in self.images:
                _add(self.images[key], fallback_title)
        for src, alt in self.img_candidates:
            _add(src, alt or fallback_title)
        return ordered[:MAX_CANDIDATES_TO_FETCH]


MAX_CANDIDATES_TO_FETCH = MAX_IMAGE_CANDIDATES


def _inspect_image_dimensions(data: bytes) -> tuple[int | None, int | None, bool]:
    """Decode JPEG/PNG/WebP dimensions safely, rejecting decompression bombs."""
    previous_max = Image.MAX_IMAGE_PIXELS
    Image.MAX_IMAGE_PIXELS = MAX_IMAGE_PIXELS
    try:
        with Image.open(io.BytesIO(data)) as img:
            w, h = img.size
            if w * h > MAX_IMAGE_PIXELS:
                return None, None, True
            return int(w), int(h), False
    except Image.DecompressionBombError:
        return None, None, True
    except (UnidentifiedImageError, OSError, ValueError, SyntaxError, EOFError):
        return None, None, False
    finally:
        Image.MAX_IMAGE_PIXELS = previous_max


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
            candidate_urls = parser.ordered_candidates(final_url, result.title)
            if not candidate_urls:
                return result
            candidates: list[ProductImageCandidate] = []
            blocked_or_failed = False
            for idx, (image_url, label) in enumerate(candidate_urls):
                try:
                    image_status, image, final_img_url = await _fetch_bytes_guarded(
                        image_url,
                        client,
                        max_bytes=MAX_IMAGE_BYTES,
                        resolver=self._resolver,
                        rate_limiter=_RATE_LIMITER,
                    )
                    mime = _image_mime(image) if image_status == 200 else None
                    if mime is None:
                        blocked_or_failed = True
                        continue
                    w, h, too_many_pixels = _inspect_image_dimensions(image)
                    if too_many_pixels:
                        blocked_or_failed = True
                        continue
                    if (
                        w is not None
                        and h is not None
                        and (w < MIN_CANDIDATE_DIMENSION or h < MIN_CANDIDATE_DIMENSION)
                    ):
                        continue
                    is_low_res = bool(
                        w is not None
                        and h is not None
                        and (min(w, h) < LOW_RES_MIN_EDGE or max(w, h) < LOW_RES_MAX_EDGE)
                    )
                    encoded = base64.b64encode(image).decode("ascii")
                    data_url = f"data:{mime};base64,{encoded}"
                    candidates.append(
                        ProductImageCandidate(
                            id=f"web-{idx + 1}",
                            image_data_url=data_url,
                            source_url=final_url,
                            image_url=final_img_url or image_url,
                            title=label[:160],
                            alt=label[:160],
                            width=w,
                            height=h,
                            is_low_res=is_low_res,
                            provenance="website",
                        )
                    )
                except (SitemapError, httpx.InvalidURL, ValueError):
                    blocked_or_failed = True
                    continue

            if candidates:
                first = candidates[0]
                result.image_data_url = first.image_data_url
                result.image_width = first.width
                result.image_height = first.height
                result.is_low_res = first.is_low_res
                result.image_candidates = candidates
                result.source_note = (
                    "Photo and details imported from the public listing. "
                    "Check they match the item and current offer."
                )
            elif blocked_or_failed:
                result.source_note = (
                    "Listing details imported. Its photo could not be imported safely; add a photo."
                )
            return result
