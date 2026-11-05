"""Offline checks that every model attempt is bounded and reserved before upstream work."""

from __future__ import annotations

import base64
import io
import json
import wave
from types import SimpleNamespace
from typing import Any

import httpx
import pytest
from openai import AsyncOpenAI
from pydantic import BaseModel, Field

import src.clients.meta as meta
import src.services.usage_meter as usage
from src.clients.meta import MetaAPIError, MetaClient
from src.services.usage_meter import UsageLimitError

PNG = b"\x89PNG\r\n\x1a\nimage"


class Reply(BaseModel):
    headline: str = Field(min_length=1)


def completion(text: str = '{"headline":"A clear next post"}') -> dict[str, Any]:
    return {
        "id": "offline-completion",
        "object": "chat.completion",
        "created": 0,
        "model": "muse-spark-1.3",
        "choices": [{"index": 0, "message": {"role": "assistant", "content": text}}],
    }


@pytest.fixture
def reservations(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, str, int]]:
    """Enable public bounds while replacing the real budget RPC with a recording fake."""
    recorded: list[tuple[str, str, int]] = []

    async def reserve(kind: str, model: str, amount_micros: int) -> None:
        recorded.append((kind, model, amount_micros))

    monkeypatch.setattr(meta, "_metering_enabled", lambda: True)
    monkeypatch.setattr(meta, "_reserve_provider", reserve)
    return recorded


async def test_text_reserves_before_each_attempt_and_caps_output(
    reservations: list[tuple[str, str, int]],
) -> None:
    sent = []

    def respond(request: httpx.Request) -> httpx.Response:
        sent.append(json.loads(request.content))
        assert len(reservations) == len(sent)
        text = "malformed JSON" if len(sent) == 1 else '{"headline":"Repaired"}'
        return httpx.Response(200, json=completion(text))

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as http:
        result = await MetaClient(api_key="offline-key", http_client=http).chat_structured(
            [{"role": "user", "content": "Write a post."}], Reply
        )
    assert result.headline == "Repaired"
    assert reservations == [("text", "muse-spark-1.3", 250_000)] * 2
    assert all(body["max_completion_tokens"] == 4096 for body in sent)
    assert "Validation errors" in sent[1]["messages"][-1]["content"]


async def test_missing_context_blocks_before_any_upstream_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = MetaClient(api_key="offline-key")
    settings = SimpleNamespace(accounts_required=True)
    monkeypatch.setattr(meta, "get_settings", lambda: settings)
    monkeypatch.setattr(usage, "get_settings", lambda: settings)
    usage.clear_request_context()

    def no_network(request: httpx.Request) -> httpx.Response:
        pytest.fail(f"An unauthenticated request reached {request.url.path}")

    async with httpx.AsyncClient(transport=httpx.MockTransport(no_network)) as http:
        client._http_client = http
        with pytest.raises(UsageLimitError, match="sign in"):
            await client.chat_structured([{"role": "user", "content": "Write a post."}], Reply)


async def test_exhausted_budget_makes_no_provider_call(
    monkeypatch: pytest.MonkeyPatch,
    reservations: list[tuple[str, str, int]],
) -> None:
    async def reject(kind: str, model: str, amount_micros: int) -> None:
        raise UsageLimitError(429, "Trial generation limit reached.")

    monkeypatch.setattr(meta, "_reserve_provider", reject)

    def no_network(request: httpx.Request) -> httpx.Response:
        pytest.fail(f"A quota rejection reached {request.url.path}")

    async with httpx.AsyncClient(transport=httpx.MockTransport(no_network)) as http:
        with pytest.raises(UsageLimitError, match="limit reached"):
            await MetaClient(api_key="offline-key", http_client=http).generate_image("A room")
    assert reservations == []


async def test_size_bound_includes_the_injected_json_schema(
    reservations: list[tuple[str, str, int]],
) -> None:
    class LargeSchema(BaseModel):
        headline: str = Field(description="x" * 100_001)

    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda _: pytest.fail())) as http:
        with pytest.raises(MetaAPIError, match="too much text"):
            await MetaClient(api_key="offline-key", http_client=http).chat_structured(
                [{"role": "user", "content": "Small user input"}], LargeSchema
            )
    assert reservations == []


@pytest.mark.parametrize("model", ["muse-wonder-1.0", "muse-spark-1.3-contributor", "unknown"])
async def test_unpriced_or_unapproved_text_models_do_not_reach_provider(
    model: str,
    reservations: list[tuple[str, str, int]],
) -> None:
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda _: pytest.fail())) as http:
        with pytest.raises(MetaAPIError, match="not enabled"):
            await MetaClient(api_key="offline-key", http_client=http).chat_structured(
                [{"role": "user", "content": "Hello"}], Reply, model=model
            )
    assert reservations == []


async def test_injected_sdk_retries_are_disabled_for_metered_requests(
    reservations: list[tuple[str, str, int]],
) -> None:
    calls = []

    def fail_once(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(500, json={"error": {"message": "offline failure"}})

    async with httpx.AsyncClient(transport=httpx.MockTransport(fail_once)) as http:
        sdk = AsyncOpenAI(
            api_key="offline-key",
            base_url="https://api.meta.ai/v1",
            http_client=http,
            max_retries=2,
        )
        client = MetaClient(api_key="offline-key", http_client=http, openai_client=sdk)
        with pytest.raises(MetaAPIError):
            await client.chat_structured([{"role": "user", "content": "Hello"}], Reply)
    assert len(calls) == 1
    assert len(reservations) == 1


async def test_vision_uses_multimodal_preflight_before_inference(
    reservations: list[tuple[str, str, int]],
) -> None:
    paths = []

    def respond(request: httpx.Request) -> httpx.Response:
        paths.append(request.url.path)
        assert reservations == [("text", "muse-spark-1.3", 250_000)]
        body = json.loads(request.content)
        if request.url.path.endswith("input_tokens"):
            assert body["model"] == "muse-spark-1.3"
            parts = body["input"][1]["content"]
            assert parts[0] == {"type": "input_text", "text": "Describe this product"}
            assert parts[1]["type"] == "input_image"
            assert parts[1]["image_url"].startswith("data:image/png;base64,")
            assert "tools" not in body
            return httpx.Response(200, json={"input_tokens": 1200})
        assert body["max_completion_tokens"] == 4096
        assert "tools" not in body
        return httpx.Response(200, json=completion())

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as http:
        result = await MetaClient(api_key="offline-key", http_client=http).chat_vision_structured(
            system_prompt="Use only visible facts.",
            user_prompt="Describe this product",
            images=[PNG],
            response_model=Reply,
        )
    assert result.headline == "A clear next post"
    assert paths == ["/v1/responses/input_tokens", "/v1/chat/completions"]


@pytest.mark.parametrize("tokens", [None, True, "2000", 0, 100_001])
async def test_invalid_or_excessive_vision_count_fails_closed(
    tokens: object,
    reservations: list[tuple[str, str, int]],
) -> None:
    paths = []

    def respond(request: httpx.Request) -> httpx.Response:
        paths.append(request.url.path)
        assert request.url.path.endswith("input_tokens")
        return httpx.Response(200, json={"input_tokens": tokens})

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as http:
        with pytest.raises(MetaAPIError, match="trial input limit"):
            await MetaClient(api_key="offline-key", http_client=http).chat_vision_structured(
                system_prompt="Visible facts only",
                user_prompt="Describe",
                images=[PNG],
                response_model=Reply,
            )
    assert paths == ["/v1/responses/input_tokens"]
    assert len(reservations) == 1  # No automatic refund of a conservative reservation.


@pytest.mark.parametrize("method", ["generate_image", "edit_image", "generate_image_workflow"])
async def test_each_image_endpoint_reserves_once_before_the_post(
    method: str,
    reservations: list[tuple[str, str, int]],
) -> None:
    def respond(request: httpx.Request) -> httpx.Response:
        assert reservations == [("image", "muse-image-1.0", 50_000)]
        body = json.loads(request.content)
        encoded = base64.b64encode(PNG).decode()
        if request.url.path.endswith("responses"):
            assert body["reasoning"] == {"effort": "low"}
            tool = body["tools"][0]
            assert tool["output_format"] == "webp"
            assert not any(
                tool[name] for name in ("enable_web_search", "enable_image_search", "enable_shell")
            )
            return httpx.Response(
                200, json={"output": [{"type": "image_generation_call", "result": encoded}]}
            )
        assert body["n"] == 1
        return httpx.Response(200, json={"data": [{"b64_json": encoded}]})

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as http:
        client = MetaClient(api_key="offline-key", http_client=http)
        if method == "generate_image":
            assert await client.generate_image("A simple room") == PNG
        elif method == "edit_image":
            assert await client.edit_image("A simple room", [PNG]) == PNG
        else:
            image, _ = await client.generate_image_workflow("A simple room", reference_images=[PNG])
            assert image == PNG


async def test_segmentation_reserves_before_its_single_image_request(
    reservations: list[tuple[str, str, int]],
) -> None:
    def respond(request: httpx.Request) -> httpx.Response:
        assert reservations == [("sam", "sam-3.1", 10_000)]
        assert json.loads(request.content)["model"] == "sam-3.1"
        return httpx.Response(200, content=PNG, headers={"content-type": "image/png"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as http:
        assert await MetaClient(api_key="offline-key", http_client=http).segment(PNG) == PNG


def wav_bytes(seconds: int) -> bytes:
    output = io.BytesIO()
    with wave.open(output, "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(1)
        audio.setframerate(8000)
        audio.writeframes(b"\x80" * (8000 * seconds))
    return output.getvalue()


async def test_voice_reserves_a_bounded_wav_only(
    reservations: list[tuple[str, str, int]],
) -> None:
    def respond(request: httpx.Request) -> httpx.Response:
        assert reservations == [("voice", "muse-voice-transcribe-1.0", 10_000)]
        return httpx.Response(200, json={"text": "My next post"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as http:
        assert (
            await MetaClient(api_key="offline-key", http_client=http).transcribe_audio(
                wav_bytes(1), filename="brief.wav"
            )
            == "My next post"
        )


@pytest.mark.parametrize(
    "audio", [b"compressed audio is not bounded", wav_bytes(121), wav_bytes(1)[:-100]]
)
async def test_unbounded_voice_is_rejected_before_reservation_or_provider(
    audio: bytes,
    reservations: list[tuple[str, str, int]],
) -> None:
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda _: pytest.fail())) as http:
        with pytest.raises(MetaAPIError, match="WAV voice note"):
            await MetaClient(api_key="offline-key", http_client=http).transcribe_audio(audio)
    assert reservations == []
