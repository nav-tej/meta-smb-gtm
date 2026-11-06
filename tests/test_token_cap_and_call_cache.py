"""Synthesis output cap, truncation-aware retry, and the call-level Muse cache (all offline)."""

from __future__ import annotations

import base64
import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import httpx
import pytest
from pydantic import BaseModel, Field

import src.clients.meta as meta
from src.clients.meta import (
    MAX_SPARK_OUTPUT_TOKENS,
    SYNTHESIS_OUTPUT_TOKENS,
    MetaAPIError,
    MetaClient,
)
from src.config import get_settings
from src.models.bids import BidAdviceRequest
from src.models.intel import CompetitorBrief
from src.services.bid_advisor import advise
from tests.conftest import build_campaign

PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 32


class Reply(BaseModel):
    headline: str = Field(min_length=1)


def completion(text: str, finish_reason: str = "stop") -> dict[str, Any]:
    return {
        "id": "offline",
        "object": "chat.completion",
        "created": 0,
        "model": "muse-spark-1.3",
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": text},
                "finish_reason": finish_reason,
            }
        ],
    }


@pytest.fixture
def cache_on(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    monkeypatch.setenv("RESULT_CACHE_ENABLED", "true")
    monkeypatch.setenv("RESULT_CACHE_DIR", str(tmp_path / "cache"))
    get_settings.cache_clear()
    yield tmp_path / "cache"
    get_settings.cache_clear()


def _cached_files(directory: Path) -> list[str]:
    return [p.name for p in directory.glob("*.json")]


def test_synthesis_cap_is_8192_and_default_stays_4096() -> None:
    assert SYNTHESIS_OUTPUT_TOKENS == 8192
    assert MAX_SPARK_OUTPUT_TOKENS == 4096
    assert meta._spark_reservation_micros(4096) == meta.SPARK_RESERVATION_MICROS
    assert meta._spark_reservation_micros(8192) == 2 * meta.SPARK_RESERVATION_MICROS


async def test_bid_advice_synthesis_requests_8192_tokens(spark_bid_content: str) -> None:
    sent: list[dict[str, Any]] = []

    def respond(request: httpx.Request) -> httpx.Response:
        sent.append(json.loads(request.content))
        return httpx.Response(200, json=completion(spark_bid_content))

    brief = CompetitorBrief.model_validate_json(
        (Path(__file__).parent / "fixtures" / "competitor_brief.json").read_text()
    )
    request = BidAdviceRequest(campaign=build_campaign(), competitor_brief=brief)
    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as http:
        client = MetaClient(api_key="offline-key", http_client=http)
        await advise(request, meta_client=client)
    assert [body["max_completion_tokens"] for body in sent] == [8192]


async def test_default_calls_keep_the_4096_cap() -> None:
    sent: list[dict[str, Any]] = []

    def respond(request: httpx.Request) -> httpx.Response:
        sent.append(json.loads(request.content))
        return httpx.Response(200, json=completion('{"headline":"ok"}'))

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as http:
        await MetaClient(api_key="k", http_client=http).chat_structured(
            [{"role": "user", "content": "hi"}], Reply
        )
    assert sent[0]["max_completion_tokens"] == 4096


async def test_truncated_output_retries_concisely_without_echoing_it() -> None:
    sent: list[dict[str, Any]] = []
    truncated = '{"headline": "A very long headline that was cut off'

    def respond(request: httpx.Request) -> httpx.Response:
        sent.append(json.loads(request.content))
        if len(sent) == 1:
            return httpx.Response(200, json=completion(truncated, finish_reason="length"))
        return httpx.Response(200, json=completion('{"headline":"Short"}'))

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as http:
        result = await MetaClient(api_key="k", http_client=http).chat_structured(
            [{"role": "user", "content": "hi"}], Reply, max_output_tokens=SYNTHESIS_OUTPUT_TOKENS
        )
    assert result.headline == "Short"
    assert len(sent) == 2
    retry_messages = sent[1]["messages"]
    assert all(truncated not in str(m.get("content")) for m in retry_messages)
    assert "cut off" in retry_messages[-1]["content"]
    assert sent[1]["max_completion_tokens"] == 8192


async def test_out_of_range_token_limit_is_rejected_before_any_call() -> None:
    with pytest.raises(MetaAPIError):
        await MetaClient(api_key="k").chat_structured(
            [{"role": "user", "content": "hi"}], Reply, max_output_tokens=20_000
        )


async def test_identical_chat_is_served_from_the_call_cache(cache_on: Path) -> None:
    calls = 0

    def respond(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, json=completion('{"headline":"Cached"}'))

    messages = [{"role": "user", "content": "Write a headline"}]
    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as http:
        client = MetaClient(api_key="k", http_client=http)
        first = await client.chat_structured(messages, Reply)
        second = await client.chat_structured(messages, Reply)
        other = await client.chat_structured([{"role": "user", "content": "Different"}], Reply)
    assert first == second == other
    assert calls == 2  # the repeat was a hit; a different prompt was not
    # A hit needs no API key at all (fallback-friendly).
    assert (await MetaClient(api_key="").chat_structured(messages, Reply)).headline == "Cached"
    assert all("muse-call-chat" in name for name in _cached_files(cache_on))


async def test_failed_validation_is_never_cached(cache_on: Path) -> None:
    def respond(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=completion("not json"))

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as http:
        with pytest.raises(MetaAPIError):
            await MetaClient(api_key="k", http_client=http).chat_structured(
                [{"role": "user", "content": "x"}], Reply
            )
    assert not _cached_files(cache_on)


async def test_image_sam_and_voice_calls_are_cached(cache_on: Path) -> None:
    import io
    import wave

    buf = io.BytesIO()
    with wave.open(buf, "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(8000)
        audio.writeframes(b"\x00\x00" * 8000)
    voice = buf.getvalue()
    paths: list[str] = []
    b64 = base64.b64encode(PNG).decode()

    def respond(request: httpx.Request) -> httpx.Response:
        paths.append(request.url.path)
        if request.url.path.endswith("/images/generations") or request.url.path.endswith(
            "/images/edits"
        ):
            return httpx.Response(200, json={"data": [{"b64_json": b64}]})
        if request.url.path.endswith("/audio/transcriptions"):
            return httpx.Response(200, json={"text": "hello"})
        body = json.loads(request.content)
        if body["model"] == "sam-3.1":
            text = "<|box;x1=1;y1=1;x2=4;y2=4;w=8;h=8|>"
            return httpx.Response(
                200, json={"output": [{"content": [{"type": "output_text", "text": text}]}]}
            )
        return httpx.Response(
            200,
            json={
                "output": [
                    {"type": "reasoning", "summary": [{"text": "staged"}]},
                    {"type": "image_generation_call", "result": b64},
                ]
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as http:
        client = MetaClient(api_key="k", http_client=http)
        for _ in range(2):
            assert await client.generate_image("a scene") == PNG
            assert await client.edit_image("restage", [PNG]) == PNG
            assert await client.generate_image_workflow("combine", reference_images=[PNG]) == (
                PNG,
                "staged",
            )
            assert (await client.segment(PNG)).startswith(b"\x89PNG")
            assert await client.transcribe_audio(voice) == "hello"
    assert len(paths) == 5  # second round: every call was a cache hit


async def test_cache_hits_and_calls_are_recorded_for_credit_refunds(cache_on: Path) -> None:
    def respond(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=completion('{"headline":"x"}'))

    messages = [{"role": "user", "content": "track me"}]
    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as http:
        client = MetaClient(api_key="k", http_client=http)
        log = meta.track_provider_calls()
        await client.chat_structured(messages, Reply)
        assert log["calls"] == ["chat"] and log["hits"] == []
        log = meta.track_provider_calls()
        await client.chat_structured(messages, Reply)
        assert log["calls"] == [] and log["hits"] == ["chat"]
