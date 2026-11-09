"""Monitor history mirrored to private storage so it survives new server instances (offline)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.clients.supabase import SupabaseError
from src.config import get_settings
from src.services import competitor_monitor, durable_state


class FakeBucket:
    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}
        self.fail = False

    async def put_object(
        self, bucket: str, name: str, data: bytes, mime: str, *, upsert: bool = False
    ) -> None:
        if self.fail:
            raise SupabaseError(503, "down")
        assert bucket == "muse-state" and mime == "application/json" and upsert
        self.objects[name] = data

    async def get_object(self, bucket: str, name: str) -> bytes | None:
        return self.objects.get(name)

    async def list_objects(self, bucket: str, prefix: str) -> list[str]:
        if self.fail:
            raise SupabaseError(503, "down")
        return [n for n in self.objects if n.rsplit("/", 1)[0] == prefix]


@pytest.fixture
def bucket(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> FakeBucket:
    monkeypatch.setenv("MONITOR_DIR", str(tmp_path / "instance-a"))
    get_settings.cache_clear()
    fake = FakeBucket()
    monkeypatch.setattr(durable_state, "get_supabase_client", lambda: fake)
    monkeypatch.setattr(durable_state, "enabled", lambda: True)
    yield fake
    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_history_survives_a_new_instance(
    bucket: FakeBucket, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = competitor_monitor.monitor_dir()
    (root / "snapshots").mkdir(parents=True)
    (root / "changelog.json").write_text(json.dumps({"runs": []}))
    (root / "snapshots" / "shop.json").write_text(json.dumps({"entries": []}))
    assert await durable_state.flush_monitor() == 2
    assert set(bucket.objects) == {"monitor/changelog.json", "monitor/snapshots/shop.json"}

    # A cold start: empty /tmp on a different instance.
    monkeypatch.setenv("MONITOR_DIR", str(tmp_path / "instance-b"))
    get_settings.cache_clear()
    assert await durable_state.hydrate_monitor(force=True)
    fresh = competitor_monitor.monitor_dir()
    assert json.loads((fresh / "changelog.json").read_text()) == {"runs": []}
    assert (fresh / "snapshots" / "shop.json").is_file()


@pytest.mark.asyncio
async def test_hydrate_is_throttled_and_storage_failure_is_harmless(bucket: FakeBucket) -> None:
    assert await durable_state.hydrate_monitor()
    assert not await durable_state.hydrate_monitor()  # within a minute: local files are used
    bucket.fail = True
    assert not await durable_state.hydrate_monitor(force=True)
    assert await durable_state.flush_monitor() == 0


def test_only_hosted_deployments_sync(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.undo()  # drop the conftest guard for this check
    monkeypatch.setenv("HOSTED_ENVIRONMENT", "")
    get_settings.cache_clear()
    assert durable_state.enabled() is False
    get_settings.cache_clear()
