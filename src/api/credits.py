"""GET/POST /credits: check, spend and add server-side run credits.

The browser's credits pill reads its balance from here; the server, not localStorage, decides.
Live Muse routes spend credits through the live gate (src/api/demo.py), not this router.
"""

from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Header, HTTPException, Request, Response
from pydantic import BaseModel, Field

from src.api.demo import credit_holder, valid_demo_key
from src.config import get_settings
from src.services import credits

router = APIRouter(tags=["credits"])

PERSISTENCE_NOTE = (
    "Credits are tracked on this server. On the hosted demo they are kept per server instance "
    "and can reset after a restart; billed live calls still need the presenter key."
)


class CreditStatus(BaseModel):
    source: Literal["server", "account"] = "server"
    holder: Literal["browser", "presenter", "account"] = "browser"
    balance: int | None
    starting_balance: int
    spent: int = 0
    added: int = 0
    enforced: bool = True
    persistent: bool = True
    note: str = ""
    history: list[dict[str, object]] = Field(default_factory=list)


class SpendRequest(BaseModel):
    label: str = Field(default="Run", min_length=1, max_length=80)


class AddRequest(BaseModel):
    plan: Literal["starter", "growth", "unlimited"] | None = None
    amount: int | None = Field(default=None, ge=1, le=5000)


def _require_json(request: Request) -> None:
    # A JSON content type forces a CORS preflight, so other sites cannot post silently.
    if request.headers.get("content-type", "").split(";", 1)[0].lower() != "application/json":
        raise HTTPException(415, "Send credit requests as JSON.")


def _status(holder: credits.Holder) -> CreditStatus:
    info = credits.summary(holder.id)
    settings = get_settings()
    return CreditStatus(
        holder="presenter" if holder.kind == "presenter" else "browser",
        balance=info["balance"],
        starting_balance=credits.starting_balance(holder.id),
        spent=info["spent"],
        added=info["added"],
        enforced=settings.credits_enabled,
        persistent=credits.persistent(),
        note="" if credits.persistent() else PERSISTENCE_NOTE,
        history=info["history"],
    )


def _account_status() -> CreditStatus:
    return CreditStatus(
        source="account",
        holder="account",
        balance=None,
        starting_balance=get_settings().trial_runs,
        note="Runs are tracked on your Muse account. Sign in to see your balance.",
    )


@router.get("/credits", response_model=CreditStatus)
def get_credits(
    request: Request,
    response: Response,
    x_demo_key: Annotated[str | None, Header()] = None,
) -> CreditStatus:
    response.headers["Cache-Control"] = "no-store"
    if get_settings().accounts_required:
        return _account_status()
    return _status(credit_holder(request, response, presenter=valid_demo_key(x_demo_key)))


@router.post("/credits/spend", response_model=CreditStatus)
def spend_credit(
    body: SpendRequest,
    request: Request,
    response: Response,
    x_demo_key: Annotated[str | None, Header()] = None,
) -> CreditStatus:
    """Spend one run for an action on saved data (live calls spend through the live gate)."""
    _require_json(request)
    response.headers["Cache-Control"] = "no-store"
    if get_settings().accounts_required:
        return _account_status()
    holder = credit_holder(request, response, presenter=valid_demo_key(x_demo_key))
    credits.commit(credits.reserve(holder.id, label=body.label))
    return _status(holder)


@router.post("/credits/add", response_model=CreditStatus)
def add_credits(
    body: AddRequest,
    request: Request,
    response: Response,
    x_demo_key: Annotated[str | None, Header()] = None,
) -> CreditStatus:
    """Add runs: a labelled demo plan purchase (nothing charged) or an admin top-up."""
    _require_json(request)
    response.headers["Cache-Control"] = "no-store"
    settings = get_settings()
    if settings.accounts_required:
        raise HTTPException(409, "Runs on Muse accounts are added through checkout.")
    if (body.plan is None) == (body.amount is None):
        raise HTTPException(422, "Send either a plan or an amount.")
    admin = valid_demo_key(x_demo_key)
    holder = credit_holder(request, response, presenter=admin)
    if body.plan is not None:
        credits.add(holder.id, credits.DEMO_PLAN_RUNS[body.plan], f"Demo purchase: {body.plan}")
        return _status(holder)
    if not (admin or not settings.hosted_environment):
        raise HTTPException(403, "Adding a custom number of credits needs the presenter key.")
    assert body.amount is not None
    credits.add(holder.id, body.amount, "Admin top-up")
    return _status(holder)
