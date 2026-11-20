"""Voice transcripts stay out of the reusable Muse call cache."""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest

import src.clients.meta as meta
from src.clients.meta import MetaClient
from src.config import get_settings


async def test_transcription_bypasses_cache_and_keeps_call_metering(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    monkeypatch.setenv("RESULT_CACHE_ENABLED", "true")
    monkeypatch.setenv("RESULT_CACHE_DIR", str(tmp_path / "cache"))
    get_settings.cache_clear()
    monkeypatch.setattr(meta, "_shared_client", None)

    cache_operations: list[tuple[str, str]] = []
    original_get = meta._call_cache_get
    original_put = meta._call_cache_put

    def record_get(endpoint: str, payload: object) -> object | None:
        cache_operations.append(("read", endpoint))
        return original_get(endpoint, payload)

    def record_put(endpoint: str, payload: object, value: object) -> None:
        cache_operations.append(("write", endpoint))
        original_put(endpoint, payload, value)

    monkeypatch.setattr(meta, "_call_cache_get", record_get)
    monkeypatch.setattr(meta, "_call_cache_put", record_put)

    reservations: list[tuple[str, str, int]] = []

    async def reserve(kind: str, model: str, amount: int) -> None:
        reservations.append((kind, model, amount))

    monkeypatch.setattr(meta, "_reserve_provider", reserve)

    audio = b"RAW_AUDIO_SENTINEL: seller private note"
    transcript = "PRIVATE_TRANSCRIPT_SENTINEL: launch the new print"
    provider_calls = 0

    def respond(request: httpx.Request) -> httpx.Response:
        nonlocal provider_calls
        provider_calls += 1
        assert request.url.path == "/v1/audio/transcriptions"
        assert b"RAW_AUDIO_SENTINEL" in request.content
        return httpx.Response(200, json={"text": transcript})

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as http:
        client = MetaClient(api_key="fake-test-key", http_client=http)
        call_log = meta.track_provider_calls()
        assert await client.transcribe_audio(audio) == transcript
        assert await client.transcribe_audio(audio) == transcript

    assert provider_calls == 2
    assert cache_operations == []
    assert not list((tmp_path / "cache").glob("*.json"))
    assert reservations == [
        ("voice", "muse-voice-transcribe-1.0", meta.VOICE_RESERVATION_MICROS),
        ("voice", "muse-voice-transcribe-1.0", meta.VOICE_RESERVATION_MICROS),
    ]
    assert call_log["calls"] == ["voice", "voice"]
    assert call_log["hits"] == []
    assert "RAW_AUDIO_SENTINEL" not in caplog.text
    assert "PRIVATE_TRANSCRIPT_SENTINEL" not in caplog.text
