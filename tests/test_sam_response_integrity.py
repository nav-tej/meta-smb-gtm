"""SAM failures must never fabricate a detection or escape as untyped parse errors."""

from __future__ import annotations

import base64

import httpx
import pytest

from src.clients.meta import MetaAPIError, MetaClient, _extract_sam_mask_from_responses

PNG = b"\x89PNG\r\n\x1a\nmask"


@pytest.mark.parametrize("output", [[], [{"content": [{"text": "No product found"}]}]])
def test_missing_detection_has_no_invented_mask(output: list[object]) -> None:
    assert _extract_sam_mask_from_responses({"output": output}) is None


def test_valid_box_still_produces_png() -> None:
    result = _extract_sam_mask_from_responses(
        {"output": [{"content": [{"text": "<|box;x1=1;y1=1;x2=6;y2=6;w=8;h=8|>"}]}]}
    )
    assert result is not None and result.startswith(b"\x89PNG\r\n\x1a\n")


@pytest.mark.parametrize(
    ("response", "message"),
    [
        (httpx.Response(200, text="not JSON"), "malformed JSON"),
        (httpx.Response(200, json={"output": []}), "did not contain mask bytes"),
        (httpx.Response(200, json={"mask_b64": "not base64!"}), "invalid base64"),
        (
            httpx.Response(200, json={"mask_b64": base64.b64encode(b"invalid").decode()}),
            "Unsupported image format",
        ),
        (
            httpx.Response(200, json={"output": [{"content": None}], "data": [None]}),
            "did not contain mask bytes",
        ),
        (
            httpx.Response(200, content=b"invalid", headers={"content-type": "image/png"}),
            "Unsupported image format",
        ),
    ],
)
async def test_bad_sam_response_is_typed(response: httpx.Response, message: str) -> None:
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda _: response)) as http:
        client = MetaClient(api_key="offline-test", http_client=http)
        with pytest.raises(MetaAPIError, match=message):
            await client.segment(PNG)


@pytest.mark.parametrize("field", ["mask_b64", "b64_json"])
async def test_explicit_valid_mask_still_works_after_no_detection(field: str) -> None:
    response = httpx.Response(200, json={"output": [], field: base64.b64encode(PNG).decode()})
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda _: response)) as http:
        client = MetaClient(api_key="offline-test", http_client=http)
        assert await client.segment(PNG) == PNG
