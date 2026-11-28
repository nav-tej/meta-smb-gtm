"""Offline product-reference tests; all public HTTP and DNS are replaced."""

from __future__ import annotations

import base64
import io
import random

import pytest
import respx
from fastapi import FastAPI
from fastapi.testclient import TestClient
from PIL import Image

from src.api.product_reference import get_product_reference_service, router
from src.services.product_reference import (
    MAX_IMAGE_BYTES,
    MAX_SERIALIZED_RESPONSE_BYTES,
    ProductReferenceError,
    ProductReferenceService,
)


def _make_png_bytes(width: int, height: int, color: tuple[int, int, int] = (40, 120, 90)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (width, height), color).save(buf, format="PNG")
    return buf.getvalue()


ORIGIN = "https://shop.example"
PAGE = f"{ORIGIN}/product/blue-print"
PNG = _make_png_bytes(160, 160)


async def public_resolver(host: str) -> list[str]:
    return ["93.184.216.34"]


def html(image: str | None = "/images/blue.png") -> str:
    image_tag = f'<meta property="og:image" content="{image}">' if image else ""
    return (
        "<html><head><title>Blue print</title>"
        '<meta name="description" content="A blue abstract print.">'
        '<meta property="product:price:amount" content="42">'
        '<meta property="product:price:currency" content="USD">'
        f"{image_tag}</head></html>"
    )


def allow_robots(mock: respx.MockRouter, origin: str = ORIGIN) -> None:
    mock.get(f"{origin}/robots.txt").respond(200, text="User-agent: *\nAllow: /\n")


@pytest.mark.asyncio
@respx.mock
async def test_public_product_import_returns_inline_photo_and_exact_page_facts(
    respx_mock: respx.MockRouter,
) -> None:
    allow_robots(respx_mock)
    respx_mock.get(PAGE).respond(200, text=html())
    image = respx_mock.get(f"{ORIGIN}/images/blue.png").respond(
        200, content=PNG, headers={"content-type": "application/octet-stream"}
    )

    result = await ProductReferenceService(resolver=public_resolver).read(PAGE)

    assert result.url == PAGE
    assert result.title == "Blue print"
    assert result.description == "A blue abstract print."
    assert result.price_hint == "$42"
    assert result.image_data_url == f"data:image/png;base64,{base64.b64encode(PNG).decode()}"
    assert image.call_count == 1
    assert "Review" not in result.title


@pytest.mark.asyncio
@respx.mock
async def test_missing_image_and_price_do_not_invent_facts(respx_mock: respx.MockRouter) -> None:
    allow_robots(respx_mock)
    respx_mock.get(PAGE).respond(200, text="<html><title>Unpriced work</title></html>")

    result = await ProductReferenceService(resolver=public_resolver).read(PAGE)

    assert result.title == "Unpriced work"
    assert result.price_hint is None
    assert result.image_data_url is None
    assert "add its photo" in result.source_note


@pytest.mark.asyncio
@respx.mock(assert_all_called=False)
async def test_robots_disallowed_redirect_never_fetches_destination(
    respx_mock: respx.MockRouter,
) -> None:
    respx_mock.get(f"{ORIGIN}/robots.txt").respond(200, text="User-agent: *\nDisallow: /private/\n")
    respx_mock.get(PAGE).respond(302, headers={"location": "/private/listing"})
    forbidden = respx_mock.get(f"{ORIGIN}/private/listing").respond(200, text=html())

    with pytest.raises(ProductReferenceError, match="robots.txt"):
        await ProductReferenceService(resolver=public_resolver).read(PAGE)

    assert forbidden.call_count == 0


@pytest.mark.asyncio
@respx.mock(assert_all_called=False)
async def test_private_image_url_keeps_page_but_never_fetches_image(
    respx_mock: respx.MockRouter,
) -> None:
    allow_robots(respx_mock)
    respx_mock.get(PAGE).respond(200, text=html("http://127.0.0.1/private.png"))
    private = respx_mock.get("http://127.0.0.1/private.png").respond(200, content=PNG)

    result = await ProductReferenceService(resolver=public_resolver).read(PAGE)

    assert result.title == "Blue print"
    assert result.image_data_url is None
    assert "add a photo" in result.source_note
    assert private.call_count == 0


@pytest.mark.asyncio
@respx.mock
async def test_image_cdn_robots_are_respected(respx_mock: respx.MockRouter) -> None:
    allow_robots(respx_mock)
    respx_mock.get(PAGE).respond(200, text=html("https://cdn.example/image.jpg"))
    respx_mock.get("https://cdn.example/robots.txt").respond(
        200, text="User-agent: *\nDisallow: /\n"
    )

    result = await ProductReferenceService(resolver=public_resolver).read(PAGE)

    assert result.image_data_url is None
    assert result.price_hint == "$42"


@pytest.mark.parametrize(
    "image_body",
    [PNG + b"x" * MAX_IMAGE_BYTES, b"<svg><script>alert(1)</script></svg>"],
    ids=["oversized", "unsupported-image"],
)
@pytest.mark.asyncio
@respx.mock
async def test_unsafe_or_large_image_is_optional(
    respx_mock: respx.MockRouter, image_body: bytes
) -> None:
    allow_robots(respx_mock)
    respx_mock.get(PAGE).respond(200, text=html())
    respx_mock.get(f"{ORIGIN}/images/blue.png").respond(200, content=image_body)

    result = await ProductReferenceService(resolver=public_resolver).read(PAGE)

    assert result.image_data_url is None
    assert result.title == "Blue print"


@pytest.mark.asyncio
@respx.mock
async def test_robot_rules_denied_blocks_page(respx_mock: respx.MockRouter) -> None:
    respx_mock.get(f"{ORIGIN}/robots.txt").respond(403)

    with pytest.raises(ProductReferenceError, match="crawler rules"):
        await ProductReferenceService(resolver=public_resolver).read(PAGE)


@pytest.mark.asyncio
@respx.mock
async def test_private_product_page_is_blocked_without_network() -> None:
    with pytest.raises(ProductReferenceError, match="SSRF"):
        await ProductReferenceService(resolver=public_resolver).read("http://127.0.0.1/item")


@respx.mock
def test_route_returns_validated_reference_and_typed_page_failure(
    respx_mock: respx.MockRouter,
) -> None:
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    app.dependency_overrides[get_product_reference_service] = lambda: ProductReferenceService(
        resolver=public_resolver
    )
    allow_robots(respx_mock)
    respx_mock.get(PAGE).respond(200, text=html(None))
    respx_mock.get(f"{ORIGIN}/missing").respond(404)
    with TestClient(app) as client:
        response = client.post("/api/v1/product-reference", json={"url": PAGE})
        assert response.status_code == 200
        assert response.json()["title"] == "Blue print"
        assert response.json()["image_data_url"] is None
        failure = client.post("/api/v1/product-reference", json={"url": f"{ORIGIN}/missing"})
        assert failure.status_code == 422
        assert failure.json()["detail"] == (
            "That product page couldn't be found. Check the address, try another product page, "
            "or add the details and upload its photo yourself."
        )
        assert client.post("/api/v1/product-reference", json={"url": ""}).status_code == 422
        assert (
            client.post(
                "/api/v1/product-reference", json={"url": "https://shop.example:notaport/item"}
            ).status_code
            == 422
        )


def _make_png_bytes(width: int, height: int, color: tuple[int, int, int] = (40, 120, 90)) -> bytes:
    import io

    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (width, height), color).save(buf, format="PNG")
    return buf.getvalue()


@pytest.mark.asyncio
@respx.mock
async def test_bounded_candidates_prefer_ld_json_filter_icons_and_flag_low_res(
    respx_mock: respx.MockRouter,
) -> None:
    """Candidate discovery prefers JSON-LD/og:image, filters icons/SVGs, flags low-res."""
    allow_robots(respx_mock)
    page_html = """
    <html><head>
      <title>Alpine Linocut Print</title>
      <meta property="og:image" content="/art/og-view.png">
      <script type="application/ld+json">
        {"@context": "https://schema.org", "@type": "VisualArtwork",
         "name": "Alpine Linocut Primary",
         "image": ["/art/ld-hero.png", "/art/og-view.png"]}
      </script>
    </head><body>
      <img src="/assets/site-logo.png" alt="Shop Logo" width="200" height="60">
      <img src="/assets/tracking-1x1.png" alt="" width="1" height="1">
      <img src="/assets/icon.svg" alt="Cart">
      <img src="/art/tiny-thumb.png" alt="Tiny thumbnail">
      <img src="/art/studio-detail.png" alt="Linen paper detail">
    </body></html>
    """
    respx_mock.get(PAGE).respond(200, text=page_html)
    respx_mock.get(f"{ORIGIN}/art/ld-hero.png").respond(
        200, content=_make_png_bytes(1200, 900, (30, 80, 60))
    )
    respx_mock.get(f"{ORIGIN}/art/og-view.png").respond(
        200, content=_make_png_bytes(1000, 800, (80, 40, 60))
    )
    respx_mock.get(f"{ORIGIN}/art/tiny-thumb.png").respond(
        200, content=_make_png_bytes(48, 48, (10, 10, 10))
    )
    respx_mock.get(f"{ORIGIN}/art/studio-detail.png").respond(
        200, content=_make_png_bytes(400, 300, (120, 90, 40))
    )

    result = await ProductReferenceService(resolver=public_resolver).read(PAGE)

    assert len(result.image_candidates) == 3
    ids_titles = [(c.title, c.width, c.height, c.is_low_res) for c in result.image_candidates]
    assert ids_titles[0] == ("Alpine Linocut Primary", 1200, 900, False)
    assert ids_titles[1] == ("Alpine Linocut Primary", 1000, 800, False)
    assert ids_titles[2] == ("Linen paper detail", 400, 300, True)
    assert result.image_data_url == result.image_candidates[0].image_data_url
    assert result.image_width == 1200
    assert result.image_height == 900
    assert result.is_low_res is False


def _make_noisy_jpeg(width: int, height: int, seed: int) -> bytes:
    """Create a realistic near-cap JPEG (~450KB-700KB) that cannot trivially shrink to 1KB."""
    rng = random.Random(seed)
    img = Image.frombytes("RGB", (width, height), rng.randbytes(width * height * 3))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=92)
    return buf.getvalue()


@respx.mock
def test_endpoint_bounds_aggregate_serialized_response_for_six_near_cap_jpegs(
    respx_mock: respx.MockRouter,
) -> None:
    """Six realistic near-cap JPEGs stay well under the 4.5MB hosting response limit."""
    allow_robots(respx_mock)
    imgs_html = "\n".join(
        f'<img src="/art/photo-{i}.jpg" alt="Gallery Print {i}">' for i in range(1, 7)
    )
    respx_mock.get(PAGE).respond(
        200,
        text=(
            "<html><head><title>Six High-Res Prints</title></head>"
            f"<body><p>Limited linocut series $48</p>{imgs_html}</body></html>"
        ),
    )
    for i in range(1, 7):
        raw_jpg = _make_noisy_jpeg(750, 750, seed=100 + i)
        assert 400_000 < len(raw_jpg) < MAX_IMAGE_BYTES
        respx_mock.get(f"{ORIGIN}/art/photo-{i}.jpg").respond(200, content=raw_jpg)

    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    app.dependency_overrides[get_product_reference_service] = lambda: ProductReferenceService(
        resolver=public_resolver
    )
    with TestClient(app) as client:
        response = client.post("/api/v1/product-reference", json={"url": PAGE})

    assert response.status_code == 200
    assert len(response.content) <= MAX_SERIALIZED_RESPONSE_BYTES
    assert len(response.content) < 4_500_000
    body = response.json()
    assert len(body["image_candidates"]) >= 1
    for cand in body["image_candidates"]:
        assert cand["width"] == 750
        assert cand["height"] == 750
        assert cand["source_url"] == PAGE
        assert cand["provenance"] == "website"


@pytest.mark.parametrize(
    "corrupt_bytes",
    [
        b"\x89PNG\r\n\x1a\nnot-a-valid-png-body",
        _make_png_bytes(220, 220)[:80],  # truncated PNG
        b"\xff\xd8\xff\xe0\x00\x10JFIF" + b"\x00" * 100,  # truncated/corrupt JPEG
        b"RIFF\x24\x00\x00\x00WEBP" + b"\x00" * 24,  # corrupt WebP
    ],
)
@pytest.mark.asyncio
@respx.mock
async def test_corrupt_or_truncated_image_bodies_are_rejected_preserving_listing(
    respx_mock: respx.MockRouter,
    corrupt_bytes: bytes,
) -> None:
    """Undecodable or truncated JPEG/PNG/WebP bodies never become candidates."""
    allow_robots(respx_mock)
    respx_mock.get(PAGE).respond(200, text=html("/art/broken.png"))
    respx_mock.get(f"{ORIGIN}/art/broken.png").respond(200, content=corrupt_bytes)

    result = await ProductReferenceService(resolver=public_resolver).read(PAGE)

    assert result.title == "Blue print"
    assert result.description == "A blue abstract print."
    assert result.price_hint == "$42"
    assert result.image_data_url is None
    assert result.image_candidates == []
    assert "could not be imported safely" in result.source_note


@pytest.mark.asyncio
@respx.mock
async def test_excessive_dimension_image_is_rejected_preserving_listing(
    respx_mock: respx.MockRouter,
) -> None:
    """Decompression-bomb dimensions above MAX_IMAGE_PIXELS are rejected cleanly."""
    allow_robots(respx_mock)
    # 6000x5000 = 30,000,000 pixels > MAX_IMAGE_PIXELS (25,000,000), tiny solid PNG bytes.
    buf = io.BytesIO()
    Image.new("1", (6000, 5000), 1).save(buf, format="PNG")
    huge_dim_png = buf.getvalue()
    assert len(huge_dim_png) < MAX_IMAGE_BYTES

    respx_mock.get(PAGE).respond(200, text=html("/art/bomb.png"))
    respx_mock.get(f"{ORIGIN}/art/bomb.png").respond(200, content=huge_dim_png)

    result = await ProductReferenceService(resolver=public_resolver).read(PAGE)

    assert result.title == "Blue print"
    assert result.description == "A blue abstract print."
    assert result.price_hint == "$42"
    assert result.image_data_url is None
    assert result.image_candidates == []
    assert "could not be imported safely" in result.source_note
