"""Inline delivery of generated images (src/api/media_delivery.py). Offline: no network calls."""

from __future__ import annotations

import base64
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from src.api.creative import get_ad_creative_service
from src.api.main import app
from src.api.media_delivery import (
    MAX_RESPONSE_BYTES,
    MediaResponseTooLargeError,
    attach_inline_media,
    sniff_image_mime,
)
from src.config import get_settings
from src.models.creative import Creative, CreativeSet, GenerateAdsRequest

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 32
WEBP = b"RIFF\x24\x00\x00\x00WEBPVP8 " + b"\x00" * 32


@pytest.fixture
def out_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    root = tmp_path / "outputs"
    root.mkdir()
    monkeypatch.setenv("OUTPUT_DIR", str(root))
    get_settings.cache_clear()
    yield root
    get_settings.cache_clear()


def _creative(path: Path | str, media_type: str = "image") -> Creative:
    return Creative(
        placement="facebook_feed",
        image_path=str(path),
        prompt="Collector room",
        headline="Ek Onkar",
        primary_text="Hand-painted.",
        produced_by="muse-image-1.0",
        media_type=media_type,  # type: ignore[arg-type]
    )


def _set(*creatives: Creative) -> CreativeSet:
    return CreativeSet(product_title="Ek Onkar 12x12", creatives=list(creatives))


@pytest.mark.parametrize(
    ("data", "mime"),
    [(PNG, "image/png"), (JPEG, "image/jpeg"), (WEBP, "image/webp"), (b"GIF89a", None)],
)
def test_sniff_image_mime(data: bytes, mime: str | None) -> None:
    assert sniff_image_mime(data) == mime


def test_generated_image_is_inlined(out_dir: Path) -> None:
    path = out_dir / "muse-image-abc.png"
    path.write_bytes(PNG)
    result = attach_inline_media(_set(_creative(path)))
    creative = result.creatives[0]
    assert creative.media_mime_type == "image/png"
    assert creative.media_data_url == "data:image/png;base64," + base64.b64encode(PNG).decode()
    assert creative.image_path == str(path)


def test_mime_comes_from_bytes_not_extension(out_dir: Path) -> None:
    path = out_dir / "mislabelled.png"
    path.write_bytes(WEBP)
    creative = attach_inline_media(_set(_creative(path))).creatives[0]
    assert creative.media_mime_type == "image/webp"
    assert creative.media_data_url is not None
    assert creative.media_data_url.startswith("data:image/webp;base64,")


def test_invalid_bytes_are_not_inlined(out_dir: Path) -> None:
    path = out_dir / "broken.png"
    path.write_bytes(b"<html>not an image</html>")
    creative = attach_inline_media(_set(_creative(path))).creatives[0]
    assert creative.media_data_url is None
    assert creative.media_mime_type is None


def test_paths_outside_output_root_are_not_read(out_dir: Path, tmp_path: Path) -> None:
    outside = tmp_path / "secret.png"
    outside.write_bytes(PNG)
    traversal = out_dir / ".." / "secret.png"
    link = out_dir / "link.png"
    link.symlink_to(outside)
    result = attach_inline_media(
        _set(
            _creative(outside),
            _creative(traversal),
            _creative(link),
            _creative("samples/ek_onkar_collector_room_live.webp"),
            _creative(out_dir / "missing.png"),
        )
    )
    assert all(c.media_data_url is None for c in result.creatives)


def test_videos_are_left_as_paths(out_dir: Path) -> None:
    path = out_dir / "reel.mp4"
    path.write_bytes(PNG)
    creative = attach_inline_media(_set(_creative(path, media_type="video"))).creatives[0]
    assert creative.media_data_url is None


def test_oversized_response_raises_before_reading(out_dir: Path) -> None:
    path = out_dir / "huge.png"
    path.write_bytes(PNG + b"\x00" * 3_000_000)
    with pytest.raises(MediaResponseTooLargeError) as err:
        attach_inline_media(_set(_creative(path)))
    assert err.value.limit_bytes == MAX_RESPONSE_BYTES
    assert err.value.estimated_bytes > MAX_RESPONSE_BYTES


def test_total_budget_counts_every_creative(out_dir: Path) -> None:
    paths = []
    for i in range(3):
        path = out_dir / f"img-{i}.png"
        path.write_bytes(PNG + b"\x00" * 1_000_000)
        paths.append(_creative(path))
    with pytest.raises(MediaResponseTooLargeError):
        attach_inline_media(_set(*paths))
    # Each image alone fits.
    assert attach_inline_media(_set(paths[0])).creatives[0].media_data_url


class _FakeService:
    def __init__(self, creative_set: CreativeSet) -> None:
        self.creative_set = creative_set

    async def generate(self, request: GenerateAdsRequest) -> CreativeSet:
        return self.creative_set


@pytest.fixture
def client() -> Iterator[TestClient]:
    yield TestClient(app)
    app.dependency_overrides.clear()


def _post(client: TestClient, brief_json: dict[str, Any]) -> Any:
    return client.post(
        "/api/v1/generate-ads",
        json={"product": {"title": "Ek Onkar 12x12"}, "competitor_brief": brief_json},
    )


def test_route_returns_inline_media(
    client: TestClient, out_dir: Path, brief_json: dict[str, Any]
) -> None:
    path = out_dir / "muse-image-route.jpg"
    path.write_bytes(JPEG)
    app.dependency_overrides[get_ad_creative_service] = lambda: _FakeService(_set(_creative(path)))
    response = _post(client, brief_json)
    assert response.status_code == 200
    creative = response.json()["creatives"][0]
    assert creative["image_path"] == str(path)
    assert creative["media_mime_type"] == "image/jpeg"
    assert creative["media_data_url"].startswith("data:image/jpeg;base64,")
    assert len(response.content) <= MAX_RESPONSE_BYTES


def test_route_returns_typed_413_when_oversized(
    client: TestClient, out_dir: Path, brief_json: dict[str, Any]
) -> None:
    path = out_dir / "huge.webp"
    path.write_bytes(WEBP + b"\x00" * 3_100_000)
    app.dependency_overrides[get_ad_creative_service] = lambda: _FakeService(_set(_creative(path)))
    response = _post(client, brief_json)
    assert response.status_code == 413
    detail = response.json()["detail"]
    assert detail["error"] == "media_response_too_large"
    assert detail["limit_bytes"] == MAX_RESPONSE_BYTES


def test_demo_route_responses_stay_compatible(
    client: TestClient, brief_json: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DEMO_MODE", "true")
    get_settings.cache_clear()
    response = _post(client, brief_json)
    get_settings.cache_clear()
    assert response.status_code == 200
    for creative in response.json()["creatives"]:
        assert creative["image_path"].startswith("samples/")
        assert creative["media_data_url"] is None
        assert creative["media_mime_type"] is None
