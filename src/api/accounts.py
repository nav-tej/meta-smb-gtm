"""Cookie-based signup, sign-in, and creator workspace API."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Annotated, Any, Literal
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator

from src.clients.supabase import SupabaseError, get_supabase_client
from src.config import get_settings
from src.services.accounts import (
    clear_cookies,
    complete_google_oauth,
    load_workspace,
    resolve_account,
    save_workspace,
    set_cookies,
    snapshot,
    start_google_oauth,
    trusted_mutation,
    verify_token,
    verify_workspace_owner,
)


async def account_errors() -> AsyncIterator[None]:
    """Translate only sanitized provider errors, never raw credentials or bodies."""
    try:
        yield
    except SupabaseError as err:
        raise HTTPException(err.status_code, err.detail) from err


router = APIRouter(prefix="/account", tags=["accounts"], dependencies=[Depends(account_errors)])


class EmailRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)
    email: str = Field(min_length=3, max_length=254)

    @field_validator("email")
    @classmethod
    def valid_email(cls, value: str) -> str:
        value = value.strip().lower()
        if value.count("@") != 1 or any(char.isspace() for char in value):
            raise ValueError("Enter a valid email address.")
        return value


class SigninRequest(EmailRequest):
    password: str = Field(min_length=1, max_length=128, repr=False)


class SignupRequest(EmailRequest):
    password: str = Field(min_length=12, max_length=128, repr=False)


class SessionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)
    access_token: str = Field(min_length=1, max_length=12000, repr=False)
    refresh_token: str = Field(min_length=1, max_length=12000, repr=False)


class PasswordRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)
    password: str = Field(min_length=12, max_length=128, repr=False)


class WorkspaceRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    document: dict[str, Any]
    expected_version: int | None = Field(default=None, ge=0, strict=True)
    expected_owner: str | None = Field(default=None, min_length=1, max_length=128)


class OAuthRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    provider: Literal["google"] = "google"
    next: str | None = Field(default="/account", max_length=64)


Mutation = Annotated[None, Depends(trusted_mutation)]


def callback_query() -> str:
    return urlencode({"redirect_to": get_settings().app_url.rstrip("/") + "/account"})


@router.get("/me")
async def me(request: Request, response: Response) -> dict[str, Any]:
    response.headers["Cache-Control"] = "no-store"
    account = await resolve_account(request, response)
    return await snapshot(account)


@router.post("/signup")
async def signup(body: SignupRequest, response: Response, _: Mutation) -> dict[str, Any]:
    response.headers["Cache-Control"] = "no-store"
    payload = body.model_dump()
    already_exists = False
    try:
        await get_supabase_client().auth(
            "admin/users",
            "POST",
            {"email": body.email, "password": body.password, "email_confirm": True},
            secret=True,
        )
    except SupabaseError as err:
        if err.status_code == 401:
            already_exists = True
        else:
            await get_supabase_client().auth("signup?" + callback_query(), "POST", payload)
            return {
                "message": "Check your email to confirm your account, then sign in.",
                "authenticated": False,
            }

    try:
        tokens = await get_supabase_client().auth("token?grant_type=password", "POST", payload)
    except SupabaseError as err:
        if already_exists and err.status_code == 401:
            raise HTTPException(
                409,
                "An account with this email already exists. Sign in or reset your password.",
            ) from err
        raise
    account = await verify_token(tokens.get("access_token", ""))
    result = await snapshot(account)
    set_cookies(response, tokens)
    return result


@router.post("/oauth")
async def oauth_start(
    body: OAuthRequest, request: Request, response: Response, _: Mutation
) -> dict[str, str]:
    response.headers["Cache-Control"] = "no-store"
    url = await start_google_oauth(request, response, body.next)
    return {"provider": body.provider, "url": url}


@router.get("/oauth/google")
async def oauth_google_redirect(request: Request) -> RedirectResponse:
    probe = Response()
    try:
        url = await start_google_oauth(request, probe, request.query_params.get("next"))
    except HTTPException as exc:
        err_query = urlencode({"oauth_error": str(exc.detail)})
        return RedirectResponse(
            f"/account?{err_query}", status_code=302, headers={"Cache-Control": "no-store"}
        )
    redirect = RedirectResponse(url, status_code=302, headers={"Cache-Control": "no-store"})
    for header, value in probe.raw_headers:
        if header.lower() == b"set-cookie":
            redirect.raw_headers.append((header, value))
    return redirect


@router.get("/oauth/google/callback")
async def oauth_google_callback(request: Request) -> RedirectResponse:
    target, tokens, error_msg = await complete_google_oauth(
        request,
        request.query_params.get("code"),
        request.query_params.get("state"),
        request.query_params.get("error"),
    )
    query = urlencode({"oauth_error": error_msg} if error_msg else {"oauth": "google"})
    redirect = RedirectResponse(
        f"{target}?{query}", status_code=302, headers={"Cache-Control": "no-store"}
    )
    redirect.delete_cookie("muse_oauth_state", path="/")
    if tokens is not None:
        set_cookies(redirect, tokens)
    return redirect


@router.post("/signin")
async def signin(body: SigninRequest, response: Response, _: Mutation) -> dict[str, Any]:
    tokens = await get_supabase_client().auth(
        "token?grant_type=password", "POST", body.model_dump()
    )
    account = await verify_token(tokens.get("access_token", ""))
    result = await snapshot(account)
    set_cookies(response, tokens)
    response.headers["Cache-Control"] = "no-store"
    return result


@router.post("/session")
async def session(body: SessionRequest, response: Response, _: Mutation) -> dict[str, Any]:
    account = await verify_token(body.access_token)
    result = await snapshot(account)
    set_cookies(response, body.model_dump())
    response.headers["Cache-Control"] = "no-store"
    return result


@router.post("/signout")
async def signout(request: Request, response: Response, _: Mutation) -> dict[str, str]:
    access = request.cookies.get("muse_access")
    try:
        if access:
            await get_supabase_client().auth("logout?scope=local", "POST", access_token=access)
    except SupabaseError:
        # Local credentials must be cleared even if upstream revocation is unavailable.
        pass
    finally:
        clear_cookies(response)
    response.headers["Cache-Control"] = "no-store"
    return {"message": "Signed out."}


@router.post("/recover")
async def recover(body: EmailRequest, _: Mutation) -> dict[str, str]:
    try:
        await get_supabase_client().auth("recover?" + callback_query(), "POST", body.model_dump())
    except SupabaseError as err:
        if err.status_code not in {401}:
            raise
    return {"message": "If that account exists, check your email for a password reset link."}


@router.post("/password")
async def password(
    body: PasswordRequest, request: Request, response: Response, _: Mutation
) -> dict[str, str]:
    account = await resolve_account(request, response, require_verified=True)
    assert account is not None
    await get_supabase_client().auth(
        "user", "PUT", body.model_dump(), access_token=account.access_token
    )
    return {"message": "Password updated."}


@router.get("/workspace")
async def workspace(request: Request, response: Response) -> dict[str, Any]:
    account = await resolve_account(request, response, require_verified=True)
    assert account is not None
    verify_workspace_owner(account, request.headers.get("x-muse-owner"))
    response.headers["Cache-Control"] = "no-store"
    return await load_workspace(account)


@router.put("/workspace")
async def update_workspace(
    body: WorkspaceRequest, request: Request, response: Response, _: Mutation
) -> dict[str, Any]:
    account = await resolve_account(request, response, require_verified=True)
    assert account is not None
    verify_workspace_owner(
        account,
        request.headers.get("x-muse-owner"),
        body.expected_owner,
        require_binding=True,
    )
    response.headers["Cache-Control"] = "no-store"
    return await save_workspace(account, body.document, body.expected_version, body.expected_owner)
