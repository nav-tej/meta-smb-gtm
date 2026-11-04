"""Offline product-reference tests; all public HTTP and DNS are replaced."""

from __future__ import annotations

import base64

import pytest
import respx
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.product_reference import get_product_reference_service, router
from src.services.product_reference import (
    MAX_IMAGE_BYTES,
    ProductReferenceError,
    ProductReferenceService,
)

ORIGIN = "https://shop.example"
PAGE = f"{ORIGIN}/product/blue-print"
PNG = b"\x89PNG\r\n\x1a\n" + b"sample-preview"


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
        assert "404" in failure.json()["detail"]
        assert client.post("/api/v1/product-reference", json={"url": ""}).status_code == 422
        assert (
            client.post(
                "/api/v1/product-reference", json={"url": "https://shop.example:notaport/item"}
            ).status_code
            == 422
        )
