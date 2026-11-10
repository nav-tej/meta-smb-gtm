"""Track D: Seller preferences and signals synchronization & deterministic ranking endpoints."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Header, Request, Response
from pydantic import BaseModel, Field

from src.models.intel import ActionableInsight
from src.models.seller import DismissSignal, SellerPreferences
from src.services.accounts import (
    load_workspace,
    resolve_account,
    save_workspace,
    verify_workspace_owner,
)
from src.services.preference_ranker import rank_ideas_deterministically

router = APIRouter(prefix="/preferences", tags=["preferences"])


class SyncSignalsRequest(BaseModel):
    actions: dict[str, Any] = Field(default_factory=dict)
    dismiss_signals: list[DismissSignal] = Field(default_factory=list)


class RankRequest(BaseModel):
    ideas: list[ActionableInsight]
    preferences: SellerPreferences | None = None
    dismiss_signals: list[DismissSignal] = Field(default_factory=list)


@router.get("", response_model=SellerPreferences)
async def get_preferences(
    request: Request,
    response: Response,
    x_muse_owner: str | None = Header(default=None),
) -> SellerPreferences:
    """Retrieve seller preferences from workspace or return defaults."""
    account = await resolve_account(request, response, require_verified=False)
    if not account:
        return SellerPreferences()

    verify_workspace_owner(account, x_muse_owner)
    try:
        ws = await load_workspace(account)
        doc = ws.get("document") or {}
        pref_data = doc.get("preferences")
        if pref_data and isinstance(pref_data, dict):
            return SellerPreferences.model_validate(pref_data)
    except Exception:
        pass
    return SellerPreferences()


@router.put("", response_model=SellerPreferences)
async def update_preferences(
    body: SellerPreferences,
    request: Request,
    response: Response,
    x_muse_owner: str | None = Header(default=None),
) -> SellerPreferences:
    """Persist updated seller preferences into the verified account workspace."""
    account = await resolve_account(request, response, require_verified=True)
    assert account is not None
    verify_workspace_owner(account, x_muse_owner, require_binding=True)

    ws = await load_workspace(account)
    doc = dict(ws.get("document") or {})
    doc["preferences"] = body.model_dump(mode="json")

    await save_workspace(
        account,
        doc,
        expected_version=ws.get("version"),
        expected_owner=account.user_id,
    )
    return body


@router.post("/signals")
async def sync_signals(
    body: SyncSignalsRequest,
    request: Request,
    response: Response,
    x_muse_owner: str | None = Header(default=None),
) -> dict[str, Any]:
    """Sync muse.actions and muse.dismiss_signals to the signed-in account workspace."""
    account = await resolve_account(request, response, require_verified=True)
    assert account is not None
    verify_workspace_owner(account, x_muse_owner, require_binding=True)

    ws = await load_workspace(account)
    doc = dict(ws.get("document") or {})

    # Merge actions safely
    existing_actions = dict(doc.get("actions") or {})
    existing_actions.update(body.actions)
    doc["actions"] = existing_actions

    # Append dismiss signals without duplicates
    existing_signals = list(doc.get("dismiss_signals") or [])
    seen = {
        (s.get("id"), s.get("reason"), s.get("at")) for s in existing_signals if isinstance(s, dict)
    }
    for s in body.dismiss_signals:
        sig_dict = s.model_dump(mode="json")
        key = (sig_dict.get("id"), sig_dict.get("reason"), sig_dict.get("at"))
        if key not in seen:
            existing_signals.append(sig_dict)
            seen.add(key)
    doc["dismiss_signals"] = existing_signals

    saved = await save_workspace(
        account,
        doc,
        expected_version=ws.get("version"),
        expected_owner=account.user_id,
    )
    return {
        "success": True,
        "actions_count": len(existing_actions),
        "signals_count": len(existing_signals),
        "version": saved.get("version"),
    }


@router.post("/rank", response_model=list[ActionableInsight])
async def rank_ideas_endpoint(
    body: RankRequest,
    request: Request,
    response: Response,
) -> list[ActionableInsight]:
    """Deterministically rank and filter ideas based on preferences and dismiss signals."""
    # If preferences not explicitly provided, attempt to load from session
    pref = body.preferences
    signals = list(body.dismiss_signals)

    if pref is None:
        account = await resolve_account(request, response, require_verified=False)
        if account:
            try:
                ws = await load_workspace(account)
                doc = ws.get("document") or {}
                if doc.get("preferences"):
                    pref = SellerPreferences.model_validate(doc["preferences"])
                if not signals and doc.get("dismiss_signals"):
                    signals = [
                        DismissSignal.model_validate(s)
                        for s in doc["dismiss_signals"]
                        if isinstance(s, dict)
                    ]
            except Exception:
                pass

    return rank_ideas_deterministically(
        body.ideas,
        preferences=pref,
        dismiss_signals=signals,
    )
