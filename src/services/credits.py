"""Server-side run credits: checked before every live Muse call, never trusted from the browser.

1 credit = 1 live action (an analysis, ad set, bid review, content plan, transcription...). The
live gate (`src/api/demo.py`) reserves a credit *before* any billed call and refunds it when the
request made no billable call (a cache hit), failed, or was answered by a cached/demo fallback.

Holders:
- `presenter`: requests carrying a valid `X-Demo-Key` (starts at PRESENTER_CREDITS).
- `anon:<hash>`: a browser, identified by a random HttpOnly `muse_credit_id` cookie. The cookie
  value is never stored; only its SHA-256 is. Starts at TRIAL_RUNS.
Verified Supabase accounts (ACCOUNTS_REQUIRED) keep using the durable Supabase quota instead.

Storage is one JSON ledger file guarded by an exclusive file lock and replaced atomically.
Known limit on Vercel: the ledger lives in /tmp, which is per function instance and is wiped on a
cold start, so a balance can reset there. On a hosted deployment live calls also need a valid
`X-Demo-Key` or a verified account, so a reset never unlocks billed calls for the public; the
hourly live cap still applies. Durable credits need Supabase accounts or a shared store.
"""

from __future__ import annotations

import fcntl
import hashlib
import json
import logging
import os
import re
import secrets
import tempfile
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from src.config import get_settings

logger = logging.getLogger(__name__)

COOKIE_NAME = "muse_credit_id"
COOKIE_MAX_AGE = 365 * 86400
PRESENTER = "presenter"
REPO_ROOT = Path(__file__).resolve().parents[2]
_COOKIE_RE = re.compile(r"^[A-Za-z0-9_-]{32,64}$")
# Demo checkout plans (nothing is charged); arbitrary top-ups need the admin key.
DEMO_PLAN_RUNS = {"starter": 10, "growth": 50, "unlimited": 999}
HISTORY_LIMIT = 25


class CreditsExhaustedError(Exception):
    """The holder has no credits left for a live action."""

    def __init__(self, balance: int = 0) -> None:
        self.balance = balance
        super().__init__("No credits left")


class CreditsUnavailableError(Exception):
    """The ledger could not be read or written; live calls fail closed."""


@dataclass(frozen=True)
class Holder:
    id: str
    kind: str  # "presenter" | "anon"
    new_cookie: str | None = None  # set when a browser needs a fresh credit cookie


@dataclass
class Hold:
    """One reserved credit for an in-flight live request."""

    holder_id: str
    label: str
    settled: bool = False


def ledger_dir() -> Path:
    configured = Path(get_settings().credits_dir)
    return configured if configured.is_absolute() else REPO_ROOT / configured


def persistent() -> bool:
    """False on serverless hosts, where the ledger only lasts for one function instance."""
    return not get_settings().hosted_environment


def holder_for(cookie_value: str | None, *, presenter: bool = False) -> Holder:
    if presenter:
        return Holder(PRESENTER, "presenter")
    if cookie_value and _COOKIE_RE.match(cookie_value):
        digest = hashlib.sha256(cookie_value.encode()).hexdigest()[:32]
        return Holder(f"anon:{digest}", "anon")
    fresh = secrets.token_urlsafe(24)
    digest = hashlib.sha256(fresh.encode()).hexdigest()[:32]
    return Holder(f"anon:{digest}", "anon", new_cookie=fresh)


def starting_balance(holder_id: str) -> int:
    settings = get_settings()
    return settings.presenter_credits if holder_id == PRESENTER else settings.trial_runs


@contextmanager
def _locked_ledger() -> Iterator[dict[str, Any]]:
    """Read-modify-write the ledger under an exclusive lock; writes are atomic replaces."""
    directory = ledger_dir()
    try:
        directory.mkdir(parents=True, exist_ok=True)
        lock = open(directory / ".lock", "a+")  # noqa: SIM115 - held for the block below
    except OSError as err:
        raise CreditsUnavailableError("credit ledger unavailable") from err
    with lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        path = directory / "ledger.json"
        try:
            data = json.loads(path.read_text()) if path.exists() else {}
        except (OSError, ValueError):
            logger.error("Credit ledger unreadable; refusing live calls until it is repaired")
            raise CreditsUnavailableError("credit ledger unreadable") from None
        holders = data.setdefault("holders", {})
        if not isinstance(holders, dict):
            raise CreditsUnavailableError("credit ledger malformed")
        before = json.dumps(data, sort_keys=True)
        yield data
        if json.dumps(data, sort_keys=True) == before:
            return
        try:
            fd, tmp = tempfile.mkstemp(dir=directory, prefix=".ledger-", suffix=".json")
            with os.fdopen(fd, "w") as handle:
                json.dump(data, handle, separators=(",", ":"))
            os.replace(tmp, path)
        except OSError as err:
            raise CreditsUnavailableError("credit ledger write failed") from err


def _account(data: dict[str, Any], holder_id: str) -> dict[str, Any]:
    holders: dict[str, Any] = data["holders"]
    account = holders.get(holder_id)
    if not isinstance(account, dict) or not isinstance(account.get("balance"), int):
        account = {"balance": starting_balance(holder_id), "spent": 0, "added": 0, "history": []}
        holders[holder_id] = account
    return account


def _log(account: dict[str, Any], event: str, amount: int, label: str) -> None:
    history = account.setdefault("history", [])
    history.append({"at": int(time.time()), "event": event, "amount": amount, "label": label[:80]})
    del history[:-HISTORY_LIMIT]


def balance(holder_id: str) -> int:
    """Current balance; an unknown holder has its starting balance (nothing is written)."""
    with _locked_ledger() as data:
        account = data["holders"].get(holder_id)
        if isinstance(account, dict) and isinstance(account.get("balance"), int):
            return int(account["balance"])
    return starting_balance(holder_id)


def summary(holder_id: str) -> dict[str, Any]:
    with _locked_ledger() as data:
        account = data["holders"].get(holder_id)
        if not isinstance(account, dict) or not isinstance(account.get("balance"), int):
            return {"balance": starting_balance(holder_id), "spent": 0, "added": 0, "history": []}
        return {
            "balance": int(account["balance"]),
            "spent": int(account.get("spent", 0)),
            "added": int(account.get("added", 0)),
            "history": list(account.get("history", []))[-10:],
        }


def reserve(holder_id: str, label: str = "Live Muse run") -> Hold:
    """Take one credit before a live call, or raise CreditsExhaustedError at zero."""
    with _locked_ledger() as data:
        account = _account(data, holder_id)
        if account["balance"] <= 0:
            raise CreditsExhaustedError(0)
        account["balance"] -= 1
        account["spent"] = int(account.get("spent", 0)) + 1
        _log(account, "spend", -1, label)
    return Hold(holder_id=holder_id, label=label)


def refund(hold: Hold, reason: str) -> None:
    """Give a reserved credit back (no billable call happened, or the call failed)."""
    if hold.settled:
        return
    hold.settled = True
    try:
        with _locked_ledger() as data:
            account = _account(data, hold.holder_id)
            account["balance"] += 1
            account["spent"] = max(0, int(account.get("spent", 0)) - 1)
            _log(account, "refund", 1, f"{hold.label} ({reason})")
    except CreditsUnavailableError:
        logger.warning("Credit refund skipped: ledger unavailable")


def commit(hold: Hold) -> None:
    hold.settled = True


def add(holder_id: str, amount: int, label: str) -> int:
    """Add credits, capped at MAX_CREDIT_BALANCE. Returns the new balance."""
    if amount <= 0:
        raise ValueError("amount must be positive")
    cap = get_settings().max_credit_balance
    with _locked_ledger() as data:
        account = _account(data, holder_id)
        granted = max(0, min(amount, cap - account["balance"]))
        account["balance"] += granted
        account["added"] = int(account.get("added", 0)) + granted
        _log(account, "add", granted, label)
        return int(account["balance"])
