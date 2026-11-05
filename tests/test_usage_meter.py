"""Offline contracts for durable usage authorization and pre-provider reservations."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any
from uuid import UUID, uuid4

import pytest

from src.services import usage_meter

USER_ID = "8be7949c-d9cd-4b4b-a098-32d8cc5a8dd4"
OPERATION_ID = "5736f30f-bfac-4bd7-aa0d-5f49ce84a783"
IP_HASH = "a" * 64


@pytest.fixture(autouse=True)
def _clean_context(monkeypatch: pytest.MonkeyPatch) -> None:
    usage_meter.clear_request_context()
    monkeypatch.setattr(
        usage_meter, "get_settings", lambda: SimpleNamespace(accounts_required=True)
    )


@pytest.mark.asyncio
async def test_missing_context_blocks_before_provider_or_rpc(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def forbidden_rpc(name: str, params: dict[str, Any]) -> dict[str, Any]:
        pytest.fail("A missing identity must be rejected before any RPC.")

    monkeypatch.setattr(usage_meter, "_rpc", forbidden_rpc)
    with pytest.raises(usage_meter.UsageLimitError) as error:
        await usage_meter.reserve_provider("spark", "muse-spark-1.3", 150_000)
    assert error.value.status_code == 401


@pytest.mark.asyncio
async def test_legacy_offline_mode_does_not_call_accounting(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        usage_meter, "get_settings", lambda: SimpleNamespace(accounts_required=False)
    )
    assert await usage_meter.authorize_operation(USER_ID, IP_HASH, str(uuid4())) == ""
    assert await usage_meter.reserve_provider("spark", "muse-spark-1.3", 150_000) is None


@pytest.mark.asyncio
async def test_each_attempt_is_reserved_with_distinct_id(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[str, dict[str, Any]]] = []

    async def fake_rpc(name: str, params: dict[str, Any]) -> dict[str, Any]:
        calls.append((name, params))
        if name == "muse_begin_operation":
            return {"allowed": True, "operation_id": OPERATION_ID}
        return {"allowed": True, "reservation_id": str(uuid4())}

    monkeypatch.setattr(usage_meter, "_rpc", fake_rpc)
    session = str(uuid4())
    assert (
        await usage_meter.authorize_operation(USER_ID, IP_HASH, str(uuid4()), session)
        == OPERATION_ID
    )
    await usage_meter.reserve_provider("spark", "muse-spark-1.3", 150_000)
    await usage_meter.reserve_provider("spark", "muse-spark-1.3", 150_000)
    await usage_meter.finish_operation("failed")
    assert [name for name, _ in calls] == [
        "muse_begin_operation",
        "muse_reserve_provider",
        "muse_reserve_provider",
        "muse_finish_operation",
    ]
    assert calls[0][1]["p_session_id"] == session
    first = calls[1][1]
    second = calls[2][1]
    assert first["p_amount_micros"] == 150_000
    assert first["p_operation_id"] == second["p_operation_id"] == OPERATION_ID
    assert UUID(first["p_call_id"]) != UUID(second["p_call_id"])
    assert calls[-1][1]["p_status"] == "failed"
    assert usage_meter.current_operation_id() is None


@pytest.mark.asyncio
async def test_rejected_authorization_clears_any_stale_identity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def accepted(name: str, params: dict[str, Any]) -> dict[str, Any]:
        return {"allowed": True, "operation_id": OPERATION_ID}

    monkeypatch.setattr(usage_meter, "_rpc", accepted)
    await usage_meter.authorize_operation(USER_ID, IP_HASH, str(uuid4()))

    async def rejected(name: str, params: dict[str, Any]) -> dict[str, Any]:
        raise usage_meter.UsageLimitError(429, "Daily limit reached.")

    monkeypatch.setattr(usage_meter, "_rpc", rejected)
    with pytest.raises(usage_meter.UsageLimitError, match="Daily limit"):
        await usage_meter.authorize_operation(USER_ID, IP_HASH, str(uuid4()))
    assert usage_meter.current_operation_id() is None


@pytest.mark.asyncio
async def test_finishing_failure_always_cleans_identity(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_rpc(name: str, params: dict[str, Any]) -> dict[str, Any]:
        if name == "muse_begin_operation":
            return {"allowed": True, "operation_id": OPERATION_ID}
        raise usage_meter.UsageLimitError(503, "Accounting unavailable.")

    monkeypatch.setattr(usage_meter, "_rpc", fake_rpc)
    await usage_meter.authorize_operation(USER_ID, IP_HASH, str(uuid4()))
    with pytest.raises(usage_meter.UsageLimitError):
        await usage_meter.finish_operation()
    assert usage_meter.current_operation_id() is None


@pytest.mark.asyncio
@pytest.mark.parametrize("operation_id", [None, "not-a-uuid"])
async def test_malformed_operation_response_fails_closed(
    monkeypatch: pytest.MonkeyPatch, operation_id: str | None
) -> None:
    async def fake_rpc(name: str, params: dict[str, Any]) -> dict[str, Any]:
        return {"allowed": True, "operation_id": operation_id}

    monkeypatch.setattr(usage_meter, "_rpc", fake_rpc)
    with pytest.raises(usage_meter.UsageLimitError) as error:
        await usage_meter.authorize_operation(USER_ID, IP_HASH, str(uuid4()))
    assert error.value.status_code == 503
    assert usage_meter.current_operation_id() is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("kind", "model", "amount"),
    [
        ("spark", "muse-wonder-1.0", 150_000),
        ("image", "muse-spark-1.3", 150_000),
        ("spark", "muse-spark-1.3", 0),
        ("spark", "muse-spark-1.3", 20_000_001),
        ("spark", "muse-spark-1.3", True),
    ],
)
async def test_bad_model_or_amount_never_reaches_reservation_rpc(
    monkeypatch: pytest.MonkeyPatch, kind: str, model: str, amount: int
) -> None:
    async def fake_rpc(name: str, params: dict[str, Any]) -> dict[str, Any]:
        assert name == "muse_begin_operation"
        return {"allowed": True, "operation_id": OPERATION_ID}

    monkeypatch.setattr(usage_meter, "_rpc", fake_rpc)
    await usage_meter.authorize_operation(USER_ID, IP_HASH, str(uuid4()))
    with pytest.raises(usage_meter.UsageLimitError) as error:
        await usage_meter.reserve_provider(kind, model, amount)
    assert error.value.status_code == 400


@pytest.mark.asyncio
async def test_contexts_are_isolated_between_concurrent_tasks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_rpc(name: str, params: dict[str, Any]) -> dict[str, Any]:
        await asyncio.sleep(0)
        return {"allowed": True, "operation_id": params["p_request_id"]}

    monkeypatch.setattr(usage_meter, "_rpc", fake_rpc)

    async def request(operation_id: str) -> str | None:
        await usage_meter.authorize_operation(USER_ID, IP_HASH, operation_id)
        await asyncio.sleep(0)
        return usage_meter.current_operation_id()

    ids = [str(uuid4()), str(uuid4())]
    assert await asyncio.gather(*(request(value) for value in ids)) == ids
    assert usage_meter.current_operation_id() is None


def test_schema_keeps_global_accounting_private_and_non_refunding() -> None:
    """Source review guard; parent verifies these functions on the real Supabase project."""
    sql = (Path(__file__).resolve().parents[1] / "supabase/muse_schema.sql").read_text()
    assert "security definer" not in sql.lower()
    assert "security invoker set search_path = ''" in sql.lower()
    assert "cap_micros bigint not null default 100000000" in sql
    assert "reserved_micros = reserved_micros + p_amount_micros" in sql
    assert "reserved_micros = reserved_micros -" not in sql
    assert "muse_private.credit_pool where id = 'trial' for update" in sql
    assert "from public, anon, authenticated" in sql
    assert "with check ((select auth.uid()) = user_id)" in sql


def install_fake_client(monkeypatch: pytest.MonkeyPatch, response: Any) -> None:
    """Supply the parent-owned client boundary without reading any real backend settings."""

    class FakeClient:
        async def rpc(self, name: str, params: dict[str, Any]) -> Any:
            if isinstance(response, Exception):
                raise response
            return response

    module = ModuleType("src.clients.supabase")
    module.get_supabase_client = lambda: FakeClient()  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "src.clients.supabase", module)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("response", "expected_status"),
    [
        ({"allowed": False, "status_code": 429, "message": "Daily limit."}, 429),
        ({"allowed": False, "status_code": 200, "message": "Bad response."}, 503),
        ({"allowed": "true"}, 503),
        ([], 503),
        (RuntimeError("Do not expose backend details or credentials"), 503),
    ],
)
async def test_rpc_failures_and_rejections_block_live_work(
    monkeypatch: pytest.MonkeyPatch, response: Any, expected_status: int
) -> None:
    install_fake_client(monkeypatch, response)
    with pytest.raises(usage_meter.UsageLimitError) as error:
        await usage_meter.authorize_operation(USER_ID, IP_HASH, str(uuid4()))
    assert error.value.status_code == expected_status
    assert "credentials" not in error.value.detail
    assert usage_meter.current_operation_id() is None


@pytest.mark.asyncio
async def test_single_row_rpc_result_and_explicit_completion(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_fake_client(monkeypatch, [{"allowed": True, "operation_id": OPERATION_ID}])
    assert await usage_meter.authorize_operation(USER_ID, IP_HASH, str(uuid4())) == OPERATION_ID
    usage_meter.clear_request_context()
    calls = []

    async def fake_rpc(name: str, params: dict[str, Any]) -> dict[str, Any]:
        calls.append((name, params))
        return {"allowed": True, "status": "completed"}

    monkeypatch.setattr(usage_meter, "_rpc", fake_rpc)
    await usage_meter.finish_operation(operation_id=OPERATION_ID)
    assert calls == [
        (
            "muse_finish_operation",
            {"p_operation_id": OPERATION_ID, "p_status": "completed"},
        )
    ]
