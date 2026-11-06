"""Competitor monitor, weekly digest and the daily brief built on them (offline fake crawls)."""

from __future__ import annotations

import json
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from src.api.main import app
from src.config import get_settings
from src.models.intel import SitemapEntry
from src.services import competitor_monitor as monitor
from src.services.daily_brief import build_daily_brief

SAMPLES = Path(__file__).resolve().parents[1] / "data" / "samples"


def _sample_entries(filename: str) -> list[dict[str, Any]]:
    return json.loads((SAMPLES / filename).read_text())["entries"]


def _as_entries(rows: list[dict[str, Any]]) -> list[SitemapEntry]:
    return [SitemapEntry.model_validate(r) for r in rows]


def unchanged_fetcher():  # type: ignore[no-untyped-def]
    by_url = {url: sample for _, url, _, sample in monitor.WATCHLIST}

    async def fetch(url: str) -> list[SitemapEntry]:
        return _as_entries(_sample_entries(by_url[url]))

    return fetch


def changed_fetcher():  # type: ignore[no-untyped-def]
    """Gurdish Pannu: one new listing, one removed, one price change; others unchanged."""
    base = unchanged_fetcher()

    async def fetch(url: str) -> list[SitemapEntry]:
        entries = await base(url)
        if "gurdishpannu" in url:
            entries = entries[1:]  # first listing removed
            priced = next(i for i, e in enumerate(entries) if e.price_hint)
            entries[priced] = entries[priced].model_copy(update={"price_hint": "INR 999.00"})
            entries.append(
                SitemapEntry(
                    loc="https://www.saatchiart.com/art/Painting-New-Diwali-Lights/459918/1/view",
                    title="New Diwali Lights (Painting)",
                    price_hint="$450",
                    bucket="products",
                )
            )
        return entries

    return fetch


@pytest.fixture
def client() -> Iterator[TestClient]:
    yield TestClient(app)


# ---------- diffing ----------


def test_diff_finds_new_removed_and_price_changes() -> None:
    baseline = {
        "captured": "2026-11-03",
        "entries": [
            {"loc": "https://shop.example/a", "title": "A", "price_hint": "$20"},
            {"loc": "https://shop.example/b", "title": "B", "price_hint": "$30"},
        ],
    }
    current = [
        {"loc": "https://www.shop.example/a/", "title": "A", "price_hint": "$25"},
        {"loc": "https://shop.example/c", "title": "C", "price_hint": "$40"},
    ]
    kinds = sorted(c.kind for c in monitor.diff_snapshots(baseline, current, current_partial=False))
    assert kinds == ["new_listing", "price_change", "removed_listing"]


def test_partial_crawl_skips_removals_and_needs_a_newer_lastmod() -> None:
    baseline = {"captured": "2026-11-03", "entries": [{"loc": "https://s.example/old"}]}
    current = [
        {"loc": "https://s.example/unseen-old", "lastmod": "2025-01-01T00:00:00Z"},
        {"loc": "https://s.example/really-new", "lastmod": "2026-11-05T00:00:00Z"},
    ]
    changes = monitor.diff_snapshots(baseline, current, current_partial=True)
    assert [(c.kind, c.url) for c in changes] == [("new_listing", "https://s.example/really-new")]


def test_ad_diff_records_a_baseline_first() -> None:
    assert monitor.diff_ads(None, [{"id": "1"}]) == []
    changes = monitor.diff_ads([{"id": "1"}, {"id": "2"}], [{"id": "2"}, {"id": "3"}])
    assert sorted(c.kind for c in changes) == ["ad_new", "ad_stopped"]


# ---------- runs and storage ----------


async def test_first_run_compares_with_saved_snapshots_then_with_itself() -> None:
    first = await monitor.run_monitor(trigger="test", fetch_entries=changed_fetcher())
    pannu = next(c for c in first.competitors if c.name == "Gurdish Pannu")
    assert pannu.status == "changed"
    assert pannu.counts == {"new_listing": 1, "removed_listing": 1, "price_change": 1}
    assert pannu.compared_with.startswith("saved snapshot")
    assert not pannu.ads_checked and "not checked" in pannu.ads_note
    others = [c for c in first.competitors if c.name != "Gurdish Pannu"]
    assert all(c.status == "unchanged" for c in others)

    second = await monitor.run_monitor(trigger="test", fetch_entries=changed_fetcher())
    assert second.total_changes == 0
    assert all(c.compared_with.startswith("last check") for c in second.competitors)
    assert [r.run_id for r in monitor.load_changelog().runs] == [second.run_id, first.run_id]


async def test_one_failing_shop_does_not_stop_the_others() -> None:
    base = unchanged_fetcher()

    async def flaky(url: str) -> list[SitemapEntry]:
        if "sikhiart" in url:
            raise RuntimeError("boom")
        return await base(url)

    run = await monitor.run_monitor(trigger="test", fetch_entries=flaky)
    statuses = {c.name: c.status for c in run.competitors}
    assert statuses["SikhiArt.com"] == "error"
    assert sum(s == "unchanged" for s in statuses.values()) == 3
    failed = next(c for c in run.competitors if c.status == "error")
    assert failed.error and "boom" not in failed.error


async def test_ad_library_changes_are_tracked_when_a_fetcher_is_available() -> None:
    ads = [[{"id": "1", "headline": "Old ad"}], [{"id": "2", "headline": "Diwali sale"}]]

    async def fetch_ads(name: str) -> list[dict[str, str]]:
        return ads[0] if fetch_ads.round == 0 else ads[1]  # type: ignore[attr-defined]

    fetch_ads.round = 0  # type: ignore[attr-defined]
    first = await monitor.run_monitor(
        trigger="test", fetch_entries=unchanged_fetcher(), fetch_ads=fetch_ads
    )
    assert all(c.ads_checked and "First ad check" in c.ads_note for c in first.competitors)
    fetch_ads.round = 1  # type: ignore[attr-defined]
    second = await monitor.run_monitor(
        trigger="test", fetch_entries=unchanged_fetcher(), fetch_ads=fetch_ads
    )
    kinds = sorted(ch.kind for ch in second.competitors[0].changes)
    assert kinds == ["ad_new", "ad_stopped"]


# ---------- digest and brief ----------


async def test_weekly_digest_rolls_up_the_change_log() -> None:
    empty = monitor.weekly_digest()
    assert empty.checks == 0 and "No monitor checks" in empty.note
    await monitor.run_monitor(trigger="test", fetch_entries=changed_fetcher())
    digest = monitor.weekly_digest()
    assert digest.checks == 1
    assert digest.total_changes == 3
    assert digest.by_kind["price_change"] == 1
    assert digest.competitors[0].name == "Gurdish Pannu"
    assert digest.highlights[0].startswith("Gurdish Pannu changed the price")
    later = monitor.weekly_digest(datetime.now(UTC) + timedelta(days=8))
    assert later.checks == 0


async def test_daily_brief_uses_overnight_changes_for_actions_and_focus() -> None:
    await monitor.run_monitor(trigger="test", fetch_entries=changed_fetcher())
    brief = build_daily_brief()
    assert brief.overnight_changes and brief.overnight_changes[0].kind == "price_change"
    assert len(brief.action_items) == 3
    assert brief.focus == brief.move == brief.action_items[0]
    assert brief.focus.source == "Competitor monitor"
    assert "Gurdish Pannu" in brief.focus.title
    pannu = next(i for i in brief.items if i.name == "Gurdish Pannu")
    assert pannu.status == "changed"
    assert brief.trends and "synthetic" in brief.trends_source


def test_daily_brief_without_monitor_keeps_the_snapshot_focus() -> None:
    brief = build_daily_brief()
    assert brief.overnight_changes == []
    assert "No monitor check yet" in brief.overnight_note
    assert brief.focus.title == "Feature your Empowering Women series"
    assert [m.title for m in brief.action_items][1].startswith("Refresh the creative")


def test_daily_brief_survives_a_broken_section(monkeypatch: pytest.MonkeyPatch) -> None:
    def broken() -> None:
        raise ValueError("bad campaign file")

    monkeypatch.setattr("src.services.daily_brief._trends", broken)
    brief = build_daily_brief()
    assert brief.trends == [] and "unavailable" in brief.trends_source
    assert brief.focus is not None


async def test_brief_refresh_rebuilds_only_when_inputs_change(
    client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("RESULT_CACHE_ENABLED", "true")
    monkeypatch.setenv("RESULT_CACHE_DIR", str(tmp_path / "cache"))
    get_settings.cache_clear()
    first = client.get("/api/v1/daily-brief").json()
    same = client.get("/api/v1/daily-brief?refresh=true")
    assert same.headers["x-muse-brief"] == "unchanged"
    assert same.json()["generated_at"] == first["generated_at"]
    await monitor.run_monitor(trigger="test", fetch_entries=changed_fetcher())
    rebuilt = client.get("/api/v1/daily-brief")  # a plain read picks up the new check
    assert rebuilt.headers["x-muse-cache"] == "miss"
    assert rebuilt.json()["overnight_changes"]
    assert client.get("/api/v1/daily-brief").headers["x-muse-cache"] == "hit"


# ---------- routes ----------


def test_monitor_routes(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(monitor, "crawl_entries", changed_fetcher())
    assert client.get("/api/v1/monitor").json()["runs"] == []
    ran = client.post("/api/v1/monitor")
    assert ran.status_code == 200 and ran.headers["x-muse-monitor"] == "ran"
    assert ran.json()["total_changes"] == 3
    log = client.get("/api/monitor").json()  # short alias
    assert log["runs"][0]["run_id"] == ran.json()["run_id"]
    digest = client.get("/api/v1/weekly-digest").json()
    assert digest["total_changes"] == 3


def test_hosted_monitor_has_a_cooldown_unless_presenter(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(monitor, "crawl_entries", unchanged_fetcher())
    monkeypatch.setenv("HOSTED_ENVIRONMENT", "true")
    monkeypatch.setenv("DEMO_KEY", "presenter-key")
    get_settings.cache_clear()
    first = client.post("/api/v1/monitor")
    again = client.post("/api/v1/monitor")
    assert again.headers["x-muse-monitor"] == "cooldown"
    assert again.json()["run_id"] == first.json()["run_id"]
    forced = client.post("/api/v1/monitor", headers={"X-Demo-Key": "presenter-key"})
    assert forced.headers["x-muse-monitor"] == "ran"


def test_cron_entry_point_requires_the_secret_when_set(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(monitor, "crawl_entries", unchanged_fetcher())
    assert client.get("/api/v1/monitor/run").status_code == 403
    monkeypatch.setenv("CRON_SECRET", "s3cret")
    get_settings.cache_clear()
    assert client.get("/api/v1/monitor/run").status_code == 401
    ok = client.get("/api/v1/monitor/run", headers={"Authorization": "Bearer s3cret"})
    assert ok.status_code == 200 and ok.json()["trigger"] == "cron"
