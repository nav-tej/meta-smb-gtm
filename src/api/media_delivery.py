"""Inline delivery of freshly generated creative images.

On serverless hosts the instance that wrote an image to its local output directory may not be
the one that serves the browser's follow-up GET /outputs/..., so generated images are embedded
in the generate-ads response as base64 data URLs. Only paths produced by the service inside the
configured output directory are read; client input never chooses a path.
"""

from __future__ import annotations

import base64
import logging
from pathlib import Path

from src.config import get_settings
from src.models.creative import CreativeSet

logger = logging.getLogger(__name__)

# Vercel caps response bodies at 4.5 MB; stay well below it, JSON and base64 included.
MAX_RESPONSE_BYTES = 4_000_000

_PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
_JPEG_MAGIC = b"\xff\xd8\xff"


class MediaResponseTooLargeError(Exception):
    """The response with inline media would exceed the byte budget. The client can retry with
    fewer placements; nothing oversized has been sent."""

    def __init__(self, estimated_bytes: int, limit_bytes: int) -> None:
        self.estimated_bytes = estimated_bytes
        self.limit_bytes = limit_bytes
        super().__init__(
            f"Generated media response would be about {estimated_bytes} bytes; "
            f"the limit is {limit_bytes}."
        )


def sniff_image_mime(data: bytes) -> str | None:
    """Return the MIME type from the file's magic bytes, or None if it is not PNG/JPEG/WebP."""
    if data.startswith(_PNG_MAGIC):
        return "image/png"
    if data.startswith(_JPEG_MAGIC):
        return "image/jpeg"
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return None


def output_root() -> Path:
    """The configured output directory, resolved the same way the creative service writes to it."""
    configured = Path(get_settings().output_dir)
    if not configured.is_absolute():
        configured = Path(__file__).resolve().parents[2] / configured
    return configured.resolve()


def _resolve_inside(image_path: str, root: Path) -> Path | None:
    """Resolve symlinks and `..`; return the file only if it stays inside root."""
    try:
        candidate = Path(image_path)
        resolved = (candidate if candidate.is_absolute() else root / candidate).resolve(strict=True)
    except (OSError, RuntimeError):
        return None
    if not resolved.is_relative_to(root) or not resolved.is_file():
        return None
    return resolved


def _encoded_size(raw_size: int) -> int:
    return 4 * ((raw_size + 2) // 3)


def attach_inline_media(
    creative_set: CreativeSet,
    *,
    root: Path | None = None,
    max_response_bytes: int = MAX_RESPONSE_BYTES,
) -> CreativeSet:
    """Return a copy of creative_set with media_data_url/media_mime_type on each generated image.

    Images outside root, missing files and bytes that are not PNG/JPEG/WebP are left without
    inline media (the existing image_path still works where the instance serves it). Raises
    MediaResponseTooLargeError before anything is returned if the serialized response would
    exceed max_response_bytes.
    """
    base = (root or output_root()).resolve()
    budget = len(creative_set.model_dump_json().encode())
    if budget > max_response_bytes:
        raise MediaResponseTooLargeError(budget, max_response_bytes)

    creatives = []
    for creative in creative_set.creatives:
        if creative.media_type != "image":
            creatives.append(creative)
            continue
        path = _resolve_inside(creative.image_path, base)
        if path is None:
            logger.warning(
                "Not inlining media outside the output directory: %s", creative.image_path
            )
            creatives.append(creative)
            continue
        size = path.stat().st_size
        # Check before reading so an oversized file is never loaded or encoded.
        if budget + _encoded_size(size) > max_response_bytes:
            raise MediaResponseTooLargeError(budget + _encoded_size(size), max_response_bytes)
        data = path.read_bytes()
        mime = sniff_image_mime(data)
        if mime is None:
            logger.warning("Not inlining %s: bytes are not PNG, JPEG or WebP", path.name)
            creatives.append(creative)
            continue
        data_url = f"data:{mime};base64,{base64.b64encode(data).decode('ascii')}"
        updated = creative.model_copy(update={"media_data_url": data_url, "media_mime_type": mime})
        budget += len(updated.model_dump_json().encode()) - len(creative.model_dump_json().encode())
        creatives.append(updated)

    result = creative_set.model_copy(update={"creatives": creatives})
    final_size = len(result.model_dump_json().encode())
    if final_size > max_response_bytes:
        raise MediaResponseTooLargeError(final_size, max_response_bytes)
    return result
