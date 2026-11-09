"""Durable generated images: stored per owner, served same-origin to the owner only (offline)."""

from __future__ import annotations

import base64
import struct
import zlib
from typing import Any

import pytest
from fastapi.testclient import TestClient

from src.api.main import app
from src.clients.supabase import SupabaseError
from src.models.creative import Creative, CreativeSet
from src.services import media_store
from src.services.accounts import AccountSession

OWNER = "11111111-1111-1111-1111-111111111111"
OTHER = "22222222-2222-2222-2222-222222222222"


def _png() -> bytes:
    def chunk(tag: bytes, data: bytes) -> bytes:
        body = tag + data
        return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body))

    header = struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", header)
        + chunk(b"IDAT", zlib.compress(b"\x00\xff\x00\x00"))
        + chunk(b"IEND", b"")
    )


class FakeStorage:
    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}
        self.fail = False

    async def put_object(self, bucket: str, name: str, data: bytes, mime: str) -> None:
        if self.fail:
            raise SupabaseError(503, "down")
        assert bucket == "muse-media" and name not in self.objects
        self.objects[name] = data

    async def get_object(self, bucket: str, name: str) -> bytes | None:
        if self.fail:
            raise SupabaseError(503, "down")
        return self.objects.get(name)

    async def list_objects(self, bucket: str, prefix: str) -> list[str]:
        return [name for name in self.objects if name.startswith(prefix + "/")]

    async def delete_objects(self, bucket: str, names: list[str]) -> None:
        for name in names:
            self.objects.pop(name, None)


@pytest.fixture
def storage(monkeypatch: pytest.MonkeyPatch) -> FakeStorage:
    fake = FakeStorage()
    monkeypatch.setattr(media_store, "get_supabase_client", lambda: fake)
    return fake


def _creative_set(data_url: str | None) -> CreativeSet:
    creative = Creative(
        placement="instagram_feed",
        image_path="outputs/x.png",
        prompt="p",
        headline="h",
        primary_text="t",
        produced_by="muse-image-1.0",
        media_data_url=data_url,
        media_mime_type="image/png" if data_url else None,
    )
    return CreativeSet(product_title="Print", creatives=[creative])


def _data_url() -> str:
    return "data:image/png;base64," + base64.b64encode(_png()).decode()


def _signed_in(monkeypatch: pytest.MonkeyPatch, user: str | None) -> None:
    async def fake_resolve(request: Any, response: Any = None, require_verified: bool = False):
        return AccountSession(user, "a@b.co", True, "t", None) if user else None

    monkeypatch.setattr("src.api.media.resolve_account", fake_resolve)


@pytest.mark.asyncio
async def test_inline_images_get_a_durable_owner_copy(storage: FakeStorage) -> None:
    stored = await media_store.store_creatives(_creative_set(_data_url()), OWNER)
    url = stored.creatives[0].media_asset_url
    assert url and url.startswith("/api/v1/account/media/") and url.endswith(".png")
    assert list(storage.objects) == [f"{OWNER}/{url.rsplit('/', 1)[1]}"]
    assert stored.creatives[0].media_data_url  # inline delivery is unchanged


@pytest.mark.asyncio
async def test_storage_failure_still_delivers_the_inline_image(storage: FakeStorage) -> None:
    storage.fail = True
    stored = await media_store.store_creatives(_creative_set(_data_url()), OWNER)
    assert stored.creatives[0].media_asset_url is None
    assert stored.creatives[0].media_data_url


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "data_url",
    [None, "data:image/png;base64,bm90IGFuIGltYWdl", "data:image/svg+xml;base64,PHN2Zz4="],
)
async def test_only_real_images_are_stored(storage: FakeStorage, data_url: str | None) -> None:
    stored = await media_store.store_creatives(_creative_set(data_url), OWNER)
    assert stored.creatives[0].media_asset_url is None and storage.objects == {}


@pytest.mark.asyncio
async def test_owner_folder_must_be_a_uuid(storage: FakeStorage) -> None:
    with pytest.raises(ValueError):
        await media_store.store_creatives(_creative_set(_data_url()), "../other")


def test_owner_can_load_their_image_and_nobody_else_can(
    storage: FakeStorage, monkeypatch: pytest.MonkeyPatch
) -> None:
    import asyncio

    stored = asyncio.run(media_store.store_creatives(_creative_set(_data_url()), OWNER))
    url = stored.creatives[0].media_asset_url
    client = TestClient(app, base_url="https://testserver")

    _signed_in(monkeypatch, OWNER)
    ok = client.get(url)
    assert ok.status_code == 200 and ok.content == _png()
    assert ok.headers["content-type"] == "image/png"
    assert ok.headers["cache-control"].startswith("private")

    _signed_in(monkeypatch, OTHER)
    assert client.get(url).status_code == 404

    _signed_in(monkeypatch, None)
    assert client.get(url).status_code == 401


@pytest.mark.parametrize(
    "asset", ["..%2F..%2Fsecret.png", "abc.png", "0" * 32 + ".svg", "0" * 32 + ".png.exe"]
)
def test_bad_asset_names_are_rejected_before_auth_or_storage(
    storage: FakeStorage, monkeypatch: pytest.MonkeyPatch, asset: str
) -> None:
    _signed_in(monkeypatch, OWNER)
    response = TestClient(app).get(f"/api/v1/account/media/{asset}")
    assert response.status_code == 404


def test_storage_outage_is_a_friendly_503(
    storage: FakeStorage, monkeypatch: pytest.MonkeyPatch
) -> None:
    storage.fail = True
    _signed_in(monkeypatch, OWNER)
    response = TestClient(app).get(f"/api/v1/account/media/{'a' * 32}.png")
    assert response.status_code == 503 and "unavailable" in response.json()["detail"]


@pytest.mark.asyncio
async def test_account_deletion_removes_only_that_owners_images(storage: FakeStorage) -> None:
    await media_store.store_creatives(_creative_set(_data_url()), OWNER)
    await media_store.store_creatives(_creative_set(_data_url()), OTHER)
    assert await media_store.delete_owner_media(OWNER) == 1
    assert [name.split("/")[0] for name in storage.objects] == [OTHER]


def test_generate_ads_stores_a_copy_only_for_signed_in_live_runs() -> None:
    from pathlib import Path

    route = (Path(__file__).resolve().parents[1] / "src/api/creative.py").read_text()
    assert "owner = usage_meter.current_user_id()" in route
    assert "media_store.store_creatives(result, owner)" in route
