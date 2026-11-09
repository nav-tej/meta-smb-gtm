"""Keep the competitor monitor's files across Vercel instances.

The monitor reads and writes plain JSON files under MONITOR_DIR, which is /tmp on Vercel and
disappears with each function instance. When Supabase is configured, routes call
`hydrate_monitor()` before reading (at most once a minute per instance) and `flush_monitor()`
after a check, which mirror those files to the private `muse-state` bucket. Everything is best
effort: on a storage failure the monitor keeps working from the local files, as before.
"""

from __future__ import annotations

import logging
import time
from pathlib import Path

from src.clients.supabase import SupabaseError, configured, get_supabase_client
from src.config import get_settings
from src.services import competitor_monitor

logger = logging.getLogger(__name__)

BUCKET = "muse-state"
PREFIX = "monitor"
HYDRATE_EVERY_SECONDS = 60
_last_hydrated = 0.0


def enabled() -> bool:
    """Only hosted deployments need this; a local server keeps its files on disk."""
    return bool(get_settings().hosted_environment) and configured()


def _local_files() -> list[Path]:
    root = competitor_monitor.monitor_dir()
    files = [root / "changelog.json"]
    files += sorted((root / "snapshots").glob("*.json")) if (root / "snapshots").is_dir() else []
    return [path for path in files if path.is_file()]


def _remote_name(path: Path) -> str:
    return f"{PREFIX}/{path.relative_to(competitor_monitor.monitor_dir()).as_posix()}"


async def hydrate_monitor(*, force: bool = False) -> bool:
    """Download the stored change log and snapshots into MONITOR_DIR. True if it ran."""
    global _last_hydrated
    if not enabled() or (not force and time.monotonic() - _last_hydrated < HYDRATE_EVERY_SECONDS):
        return False
    client = get_supabase_client()
    root = competitor_monitor.monitor_dir()
    try:
        names = await client.list_objects(BUCKET, PREFIX)
        names += await client.list_objects(BUCKET, f"{PREFIX}/snapshots")
        for name in names:
            if not name.endswith(".json"):
                continue
            data = await client.get_object(BUCKET, name)
            if data is None:
                continue
            target = root / name.removeprefix(f"{PREFIX}/")
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
    except (SupabaseError, OSError, ValueError) as err:
        logger.warning("Monitor state hydrate skipped: %s", type(err).__name__)
        return False
    _last_hydrated = time.monotonic()
    return True


async def flush_monitor() -> int:
    """Upload the local change log and snapshots. Returns how many files were stored."""
    if not enabled():
        return 0
    client = get_supabase_client()
    stored = 0
    for path in _local_files():
        try:
            await client.put_object(
                BUCKET, _remote_name(path), path.read_bytes(), "application/json", upsert=True
            )
            stored += 1
        except (SupabaseError, OSError) as err:
            logger.warning("Monitor state flush skipped for %s: %s", path.name, type(err).__name__)
    return stored


def reset() -> None:
    """Tests: forget the hydrate timestamp."""
    global _last_hydrated
    _last_hydrated = 0.0
