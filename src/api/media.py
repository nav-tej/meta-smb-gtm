"""Owner-only access to durable generated images (see src/services/media_store.py)."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, Response

from src.clients.supabase import SupabaseError
from src.services import media_store
from src.services.accounts import resolve_account

router = APIRouter(tags=["account"])


@router.get("/account/media/{asset}", response_class=Response)
async def account_media(asset: str, request: Request, response: Response) -> Response:
    """Serve one of the signed-in owner's stored images, same-origin (safe for canvas export)."""
    if not media_store.ASSET_RE.fullmatch(asset):
        raise HTTPException(404, "Image not found.")
    account = await resolve_account(request, response)
    if account is None:
        raise HTTPException(401, "Sign in to see your saved images.")
    try:
        found = await media_store.read_asset(account.user_id, asset)
    except SupabaseError as err:
        raise HTTPException(
            503, "Saved images are unavailable right now. Try again shortly."
        ) from err
    if found is None:
        # Another account's image looks exactly like a missing one.
        raise HTTPException(404, "Image not found.")
    data, mime = found
    headers = {"Cache-Control": "private, max-age=86400", "X-Content-Type-Options": "nosniff"}
    out = Response(content=data, media_type=mime, headers=headers)
    # Keep any refreshed session cookies set while resolving the account.
    out.raw_headers.extend(item for item in response.raw_headers if item[0] == b"set-cookie")
    return out
