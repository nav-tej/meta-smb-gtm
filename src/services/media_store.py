"""Durable copies of generated images in the signed-in owner's private storage.

Vercel's /tmp disappears with each function instance, and inline data URLs are too large for
the 3 MB account workspace. After a live generation in account mode, each inline image is also
stored at muse-media/<user_id>/<asset>.<ext> and the creative gets a same-origin
media_asset_url. Storage is best effort: if it fails the customer still gets the inline image.
"""

from __future__ import annotations

import base64
import binascii
import logging
import re
from uuid import UUID, uuid4

from src.api.media_delivery import sniff_image_mime
from src.clients.supabase import SupabaseError, get_supabase_client
from src.models.creative import CreativeSet

logger = logging.getLogger(__name__)

BUCKET = "muse-media"
MEDIA_ROUTE = "/api/v1/account/media/"
MAX_BYTES = 5 * 1024 * 1024
EXTENSIONS = {"image/png": "png", "image/jpeg": "jpg", "image/webp": "webp"}
MIME_BY_EXTENSION = {ext: mime for mime, ext in EXTENSIONS.items()}
ASSET_RE = re.compile(r"^[0-9a-f]{32}\.(png|jpg|webp)$")
_DATA_URL_RE = re.compile(r"^data:image/(?:png|jpeg|webp);base64,([A-Za-z0-9+/=]+)$")


def _owner_folder(user_id: str) -> str:
    return str(UUID(user_id))  # normalises and rejects anything that is not a UUID


def object_name(user_id: str, asset: str) -> str:
    if not ASSET_RE.fullmatch(asset):
        raise ValueError("Invalid media asset name.")
    return f"{_owner_folder(user_id)}/{asset}"


def _decode(data_url: str | None) -> tuple[bytes, str] | None:
    match = _DATA_URL_RE.fullmatch(data_url or "")
    if not match:
        return None
    try:
        data = base64.b64decode(match.group(1), validate=True)
    except (binascii.Error, ValueError):
        return None
    mime = sniff_image_mime(data)
    if mime is None or len(data) > MAX_BYTES:
        return None
    return data, mime


async def store_creatives(creative_set: CreativeSet, user_id: str) -> CreativeSet:
    """Return a copy with media_asset_url on every inline image stored for this owner."""
    folder = _owner_folder(user_id)
    client = get_supabase_client()
    creatives = []
    for creative in creative_set.creatives:
        decoded = _decode(creative.media_data_url)
        if decoded is None:
            creatives.append(creative)
            continue
        data, mime = decoded
        asset = f"{uuid4().hex}.{EXTENSIONS[mime]}"
        try:
            await client.put_object(BUCKET, f"{folder}/{asset}", data, mime)
        except SupabaseError:
            logger.warning("Durable media copy failed; the inline image is still delivered.")
            creatives.append(creative)
            continue
        creatives.append(creative.model_copy(update={"media_asset_url": MEDIA_ROUTE + asset}))
    return creative_set.model_copy(update={"creatives": creatives})


async def read_asset(user_id: str, asset: str) -> tuple[bytes, str] | None:
    """The owner's stored image and its MIME type, or None if it is not theirs or is gone."""
    data = await get_supabase_client().get_object(BUCKET, object_name(user_id, asset))
    if data is None:
        return None
    mime = sniff_image_mime(data)
    if mime is None or mime != MIME_BY_EXTENSION[asset.rsplit(".", 1)[1]]:
        return None
    return data, mime


async def delete_owner_media(user_id: str) -> int:
    """Delete every stored image for an account (data-deletion requests). Returns the count."""
    client = get_supabase_client()
    folder = _owner_folder(user_id)
    deleted = 0
    while names := await client.list_objects(BUCKET, folder):
        await client.delete_objects(BUCKET, names)
        deleted += len(names)
        if len(names) < 1000:
            break
    return deleted
