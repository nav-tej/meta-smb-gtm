"""Unit tests for the Meta Model API client (`src.clients.meta`)."""

from __future__ import annotations

import base64
import json

import httpx
import pytest
import respx
from pydantic import BaseModel, Field

from src.clients.meta import MetaAPIError, MetaClient


class _SampleOutput(BaseModel):
    headline: str = Field(min_length=1)
    tags: list[str]


def _completion_payload(content: str) -> dict[str, object]:
    return {
        "id": "chatcmpl-test-123",
        "object": "chat.completion",
        "created": 1762000000,
        "model": "muse-spark-1.3",
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": content},
                "finish_reason": "stop",
            }
        ],
    }


@respx.mock
async def test_chat_structured_parses_valid_json_and_trims_credentials() -> None:
    fenced_json = '```json\n{"headline": "Seasonal Push", "tags": ["art", "prints"]}\n```'
    route = respx.post("https://api.meta.ai/v1/chat/completions").mock(
        return_value=httpx.Response(200, json=_completion_payload(fenced_json))
    )

    async with httpx.AsyncClient() as http_client:
        client = MetaClient(
            api_key="  test-meta-key\n",
            base_url="https://api.meta.ai/v1  ",
            spark_model=" muse-spark-1.3 ",
            http_client=http_client,
        )
        result = await client.chat_structured(
            messages=[{"role": "user", "content": "Analyze sample."}],
            response_model=_SampleOutput,
        )

    assert result == _SampleOutput(headline="Seasonal Push", tags=["art", "prints"])
    assert route.called
    sent_request = route.calls[0].request
    assert sent_request.headers["authorization"] == "Bearer test-meta-key"
    body = json.loads(sent_request.content.decode("utf-8"))
    assert body["model"] == "muse-spark-1.3"


@respx.mock
async def test_chat_structured_retries_once_on_malformed_llm_json() -> None:
    route = respx.post("https://api.meta.ai/v1/chat/completions").mock(
        side_effect=[
            httpx.Response(200, json=_completion_payload('{"headline": "", "tags": "not-a-list"}')),
            httpx.Response(
                200,
                json=_completion_payload('{"headline": "Recovered", "tags": ["canvas"]}'),
            ),
        ]
    )

    async with httpx.AsyncClient() as http_client:
        client = MetaClient(api_key="test-key", http_client=http_client)
        result = await client.chat_structured(
            messages=[{"role": "user", "content": "Produce output."}],
            response_model=_SampleOutput,
        )

    assert result.headline == "Recovered"
    assert route.call_count == 2
    retry_body = json.loads(route.calls[1].request.content.decode("utf-8"))
    assert "Validation errors" in retry_body["messages"][-1]["content"]


@respx.mock
async def test_chat_structured_raises_after_second_validation_failure() -> None:
    respx.post("https://api.meta.ai/v1/chat/completions").mock(
        return_value=httpx.Response(200, json=_completion_payload("not valid json at all"))
    )

    async with httpx.AsyncClient() as http_client:
        client = MetaClient(api_key="test-key", http_client=http_client)
        with pytest.raises(MetaAPIError, match="failed _SampleOutput validation after retry"):
            await client.chat_structured(
                messages=[{"role": "user", "content": "Produce output."}],
                response_model=_SampleOutput,
            )


@respx.mock
async def test_chat_structured_wraps_http_api_errors() -> None:
    respx.post("https://api.meta.ai/v1/chat/completions").mock(
        return_value=httpx.Response(500, json={"error": {"message": "Upstream Spark unavailable"}})
    )

    async with httpx.AsyncClient() as http_client:
        client = MetaClient(api_key="secret-token-xyz", http_client=http_client)
        with pytest.raises(MetaAPIError) as exc_info:
            await client.chat_structured(
                messages=[{"role": "user", "content": "Hello"}],
                response_model=_SampleOutput,
            )
        assert "secret-token-xyz" not in str(exc_info.value)


async def test_missing_api_key_raises_meta_api_error() -> None:
    async with httpx.AsyncClient() as http_client:
        client = MetaClient(api_key="   ", http_client=http_client)
        with pytest.raises(MetaAPIError, match="META_MODEL_API_KEY is missing"):
            await client.chat_structured(
                messages=[{"role": "user", "content": "Hello"}],
                response_model=_SampleOutput,
            )


@respx.mock
async def test_generate_image_workflow_returns_bytes_and_reasoning_summary() -> None:
    fake_img = b"\x89PNG\r\n\x1a\nmuse-diptych"
    route = respx.post("https://api.meta.ai/v1/responses").mock(
        return_value=httpx.Response(
            200,
            json={
                "id": "resp-123",
                "output": [
                    {
                        "type": "reasoning",
                        "summary": [
                            {
                                "type": "summary_text",
                                "text": "Balanced 2-piece diptych over walnut console.",
                            }
                        ],
                    },
                    {
                        "type": "image_generation_call",
                        "result": base64.b64encode(fake_img).decode("ascii"),
                    },
                ],
            },
        )
    )

    async with httpx.AsyncClient() as http_client:
        client = MetaClient(api_key="test-key", http_client=http_client)
        img_bytes, summary = await client.generate_image_workflow(
            prompt="Combine these two paintings side by side.",
            reference_images=[b"\x89PNG\r\n\x1a\nAAA", b"\x89PNG\r\n\x1a\nBBB"],
            reasoning_effort="high",
        )

    assert img_bytes == fake_img
    assert summary == "Balanced 2-piece diptych over walnut console."
    assert route.called
    req_body = json.loads(route.calls[0].request.content.decode("utf-8"))
    assert req_body["model"] == "muse-image-1.0"
    assert req_body["reasoning"] == {"effort": "high"}
    content_blocks = req_body["input"][0]["content"]
    assert len(content_blocks) == 3
    assert content_blocks[1]["type"] == "input_image"
    assert content_blocks[2]["type"] == "input_image"


@respx.mock
async def test_transcribe_audio_returns_text() -> None:
    route = respx.post("https://api.meta.ai/v1/audio/transcriptions").mock(
        return_value=httpx.Response(
            200,
            json={"text": "Promote our Diwali diptych bundle to Bay Area collectors."},
        )
    )

    async with httpx.AsyncClient() as http_client:
        client = MetaClient(api_key="test-key", http_client=http_client)
        transcript = await client.transcribe_audio(
            audio_bytes=b"RIFF....WAVEfmt ",
            filename="brief.wav",
        )

    assert transcript == "Promote our Diwali diptych bundle to Bay Area collectors."
    assert route.called
