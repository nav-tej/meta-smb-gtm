"""Meta Model API client (Muse Spark, Muse Image, SAM 3.1).

The single place that talks to api.meta.ai. Uses the OpenAI-compatible SDK with base_url
overridden. Services must call this module rather than instantiating OpenAI clients directly.
"""

from __future__ import annotations

import base64
import binascii
import json
import logging
import re
import struct
import time
import zlib
from collections.abc import Sequence
from typing import Any, TypeVar

import httpx
from openai import APIError, AsyncOpenAI, OpenAIError
from openai.types.chat import ChatCompletionMessageParam
from pydantic import BaseModel, ValidationError

from src.config import Settings, get_settings

logger = logging.getLogger(__name__)

ModelT = TypeVar("ModelT", bound=BaseModel)

# Generous read timeout: a timed-out call may still be billed, and we never auto-retry it
DEFAULT_TIMEOUT = httpx.Timeout(120.0, connect=10.0)
_CODE_FENCE_RE = re.compile(r"^\s*```(?:json)?\s*(.*?)\s*```\s*$", re.DOTALL | re.IGNORECASE)


class MetaAPIError(Exception):
    """Raised when a Meta Model API request or structured-output parse fails."""


def _strip_code_fences(raw_text: str) -> str:
    """Extract inner JSON if the model wrapped its JSON output in markdown fences."""
    stripped = raw_text.strip()
    match = _CODE_FENCE_RE.match(stripped)
    return match.group(1).strip() if match else stripped


def _detect_image_mime(image_bytes: bytes) -> str:
    """Detect PNG/JPEG/WEBP MIME type from header magic bytes (AGENTS.md section 10)."""
    if image_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if image_bytes.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if len(image_bytes) >= 12 and image_bytes[:4] == b"RIFF" and image_bytes[8:12] == b"WEBP":
        return "image/webp"
    raise MetaAPIError("Unsupported image format; expected PNG, JPEG, or WEBP bytes.")


def _to_data_uri(image_bytes: bytes) -> str:
    mime = _detect_image_mime(image_bytes)
    encoded = base64.b64encode(image_bytes).decode("ascii")
    return f"data:{mime};base64,{encoded}"


_SAM_BOX_RE = re.compile(r"<\|box;x1=(\d+);y1=(\d+);x2=(\d+);y2=(\d+);w=(\d+);h=(\d+)\|>")


def _render_boxes_mask_png(
    boxes: list[tuple[int, int, int, int]],
    width: int,
    height: int,
) -> bytes:
    """Render one or more `(x1, y1, x2, y2)` boxes as a binary RGB PNG mask of `width x height`."""
    w = max(1, min(width, 4096))
    h = max(1, min(height, 4096))
    rows: list[bytes] = []
    for y in range(h):
        row = bytearray([0])  # filter type 0
        for x in range(w):
            inside = any(x1 <= x <= x2 and y1 <= y <= y2 for (x1, y1, x2, y2) in boxes)
            val = 255 if inside else 0
            row.extend((val, val, val))
        rows.append(bytes(row))
    raw = b"".join(rows)

    def _chunk(tag: bytes, data: bytes) -> bytes:
        crc = zlib.crc32(tag + data) & 0xFFFFFFFF
        return struct.pack("!I", len(data)) + tag + data + struct.pack("!I", crc)

    ihdr = struct.pack("!IIBBBBB", w, h, 8, 2, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + _chunk(b"IHDR", ihdr)
        + _chunk(b"IDAT", zlib.compress(raw))
        + _chunk(b"IEND", b"")
    )


def _extract_sam_mask_from_responses(body: dict[str, Any]) -> bytes | None:
    """Parse `/v1/responses` output from `sam-3.1` (`<|box;x1=...;y1=...|>`)."""
    outputs = body.get("output")
    if not isinstance(outputs, list):
        return None

    texts: list[str] = []
    for item in outputs:
        if not isinstance(item, dict):
            continue
        content = item.get("content", [])
        if not isinstance(content, list):
            continue
        for part in content:
            if isinstance(part, dict) and isinstance(part.get("text"), str):
                texts.append(part["text"])

    combined = "\n".join(texts)
    matches = _SAM_BOX_RE.findall(combined)
    if not matches:
        return None

    boxes: list[tuple[int, int, int, int]] = []
    canvas_w = 128
    canvas_h = 128
    for x1_s, y1_s, x2_s, y2_s, w_s, h_s in matches:
        boxes.append((int(x1_s), int(y1_s), int(x2_s), int(y2_s)))
        canvas_w = int(w_s)
        canvas_h = int(h_s)
    return _render_boxes_mask_png(boxes, canvas_w, canvas_h)


def _inject_schema_instruction(
    messages: Sequence[ChatCompletionMessageParam],
    response_model: type[BaseModel],
) -> list[ChatCompletionMessageParam]:
    """Ensure the conversation instructs the model to emit JSON matching response_model."""
    schema_json = json.dumps(response_model.model_json_schema(), separators=(",", ":"))
    schema_directive = (
        "Respond ONLY with a single valid JSON object conforming to this JSON Schema "
        f"(do not include prose or markdown fences): {schema_json}"
    )
    copied: list[ChatCompletionMessageParam] = [dict(m) for m in messages]  # type: ignore[misc]
    if copied and copied[0].get("role") == "system" and isinstance(copied[0].get("content"), str):
        copied[0] = {
            "role": "system",
            "content": f"{copied[0]['content']}\n\n{schema_directive}",
        }
    else:
        copied.insert(0, {"role": "system", "content": schema_directive})
    return copied


class MetaClient:
    """Async wrapper around Meta's OpenAI-compatible Model API (`https://api.meta.ai/v1`)."""

    def __init__(
        self,
        *,
        settings: Settings | None = None,
        api_key: str | None = None,
        base_url: str | None = None,
        spark_model: str | None = None,
        image_model: str | None = None,
        sam_model: str | None = None,
        http_client: httpx.AsyncClient | None = None,
        openai_client: AsyncOpenAI | None = None,
    ) -> None:
        cfg = settings or get_settings()
        self._api_key = (api_key if api_key is not None else cfg.meta_model_api_key).strip()
        self._base_url = (
            (base_url if base_url is not None else cfg.meta_model_api_base_url).strip().rstrip("/")
        )
        self._spark_model = (
            spark_model if spark_model is not None else cfg.muse_spark_model
        ).strip()
        self._image_model = (
            image_model if image_model is not None else cfg.muse_image_model
        ).strip()
        self._sam_model = (sam_model if sam_model is not None else cfg.sam_model).strip()
        self._owns_http_client = http_client is None and openai_client is None
        self._http_client = http_client or httpx.AsyncClient(timeout=DEFAULT_TIMEOUT)
        self._openai: AsyncOpenAI | None = openai_client

    @property
    def spark_model(self) -> str:
        return self._spark_model

    @property
    def image_model(self) -> str:
        return self._image_model

    @property
    def sam_model(self) -> str:
        return self._sam_model

    def _require_api_key(self) -> str:
        if not self._api_key:
            raise MetaAPIError(
                "META_MODEL_API_KEY is missing. Set it in your environment or .env file."
            )
        return self._api_key

    def _get_openai(self) -> AsyncOpenAI:
        if self._openai is not None:
            return self._openai
        api_key = self._require_api_key()
        self._openai = AsyncOpenAI(
            api_key=api_key,
            base_url=self._base_url,
            http_client=self._http_client,
            # Every request is billed; the only retry is the deliberate validation retry below
            max_retries=0,
        )
        return self._openai

    async def aclose(self) -> None:
        """Close underlying HTTP resources if owned by this client."""
        if self._owns_http_client:
            await self._http_client.aclose()

    async def chat_structured(
        self,
        messages: Sequence[ChatCompletionMessageParam],
        response_model: type[ModelT],
        *,
        model: str | None = None,
        temperature: float = 0.2,
    ) -> ModelT:
        """Call Muse Spark and validate JSON output into `response_model`.

        Retries once with the Pydantic validation error appended if the first
        response fails `model_validate_json`, per AGENTS.md section 6.
        """
        client = self._get_openai()
        target_model = (model or self._spark_model).strip()
        conversation = _inject_schema_instruction(messages, response_model)

        last_validation_err: Exception | None = None
        for attempt in range(2):
            raw_content = await self._create_chat_completion(
                client=client,
                model=target_model,
                messages=conversation,
                temperature=temperature,
            )
            cleaned = _strip_code_fences(raw_content)
            try:
                return response_model.model_validate_json(cleaned)
            except ValidationError as err:
                last_validation_err = err
                if attempt == 0:
                    logger.warning(
                        "Muse Spark output failed %s validation on attempt 1; retrying once.",
                        response_model.__name__,
                    )
                    conversation = [
                        *conversation,
                        {"role": "assistant", "content": raw_content},
                        {
                            "role": "user",
                            "content": (
                                "Your previous JSON did not validate against the required schema. "
                                f"Validation errors:\n{err}\n"
                                "Return ONLY a corrected JSON object matching the schema."
                            ),
                        },
                    ]

        raise MetaAPIError(
            f"Muse Spark output failed {response_model.__name__} validation after retry: "
            f"{last_validation_err}"
        ) from last_validation_err

    async def chat_vision_structured(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        images: Sequence[bytes],
        response_model: type[ModelT],
        model: str | None = None,
        temperature: float = 0.2,
    ) -> ModelT:
        """Send multimodal text + images (e.g. IG/FB/Marketplace screenshots) to Muse Spark."""
        if not images:
            raise MetaAPIError("At least one image is required for vision analysis.")

        content_parts: list[dict[str, Any]] = [{"type": "text", "text": user_prompt}]
        for img_bytes in images:
            if len(img_bytes) > 10 * 1024 * 1024:
                raise MetaAPIError("Uploaded image exceeds 10 MB safety limit.")
            content_parts.append(
                {"type": "image_url", "image_url": {"url": _to_data_uri(img_bytes)}}
            )

        messages: list[ChatCompletionMessageParam] = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": content_parts},  # type: ignore[typeddict-item]
        ]
        return await self.chat_structured(
            messages=messages,
            response_model=response_model,
            model=model,
            temperature=temperature,
        )

    async def _create_chat_completion(
        self,
        *,
        client: AsyncOpenAI,
        model: str,
        messages: list[ChatCompletionMessageParam],
        temperature: float,
    ) -> str:
        started = time.monotonic()
        try:
            completion = await client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=temperature,
                response_format={"type": "json_object"},
            )
        except APIError as err:
            logger.warning(
                "Meta API call failed: chat %s in %.1fs", model, time.monotonic() - started
            )
            raise MetaAPIError(
                f"Meta Model API error (status={getattr(err, 'status_code', 'unknown')}): "
                f"{err.message}"
            ) from err
        except (OpenAIError, httpx.HTTPError) as err:
            raise MetaAPIError(f"Meta Model API transport failure: {type(err).__name__}") from err

        usage = completion.usage
        logger.info(
            "Meta API call: chat %s in %.1fs (tokens in=%s out=%s)",
            model,
            time.monotonic() - started,
            usage.prompt_tokens if usage else "?",
            usage.completion_tokens if usage else "?",
        )
        if not completion.choices:
            raise MetaAPIError("Meta Model API returned no completion choices.")
        content: Any = completion.choices[0].message.content
        if not isinstance(content, str) or not content.strip():
            raise MetaAPIError("Meta Model API returned an empty message content.")
        return content

    async def generate_image(
        self,
        prompt: str,
        reference_image: bytes | None = None,
        *,
        mask_image: bytes | None = None,
        size: str = "1024x1024",
    ) -> bytes:
        """Generate an ad creative image via Muse Image (`muse-image-1.0` on `/images/generations`).

        Note: Live `/v1/images/generations` rejects `image`/`mask` fields with HTTP 400
        (`unknown parameter 'image'`). Reference-image restaging uses `edit_image()`
        (`/v1/images/edits`). We validate `reference_image` / `mask_image` MIME if provided.
        """
        api_key = self._require_api_key()
        if reference_image is not None:
            _detect_image_mime(reference_image)
        if mask_image is not None:
            _detect_image_mime(mask_image)

        payload: dict[str, Any] = {
            "model": self._image_model,
            "prompt": prompt,
            "size": size,
            "response_format": "b64_json",
        }

        started = time.monotonic()
        try:
            response = await self._http_client.post(
                f"{self._base_url}/images/generations",
                headers={"Authorization": f"Bearer {api_key}"},
                json=payload,
            )
        except httpx.HTTPError as err:
            raise MetaAPIError(f"Muse Image transport error: {type(err).__name__}") from err
        logger.info(
            "Meta API call: image %s -> HTTP %s in %.1fs",
            self._image_model,
            response.status_code,
            time.monotonic() - started,
        )

        if response.status_code != 200:
            raise MetaAPIError(f"Muse Image error (status={response.status_code}).")

        return await self._extract_image_bytes(response.json())

    async def edit_image(
        self,
        prompt: str,
        reference_images: Sequence[bytes],
    ) -> bytes:
        """Restage or edit 1+ input images via `muse-image-1.0` on `POST /v1/images/edits`."""
        api_key = self._require_api_key()
        if not reference_images:
            raise MetaAPIError("edit_image requires at least one reference image.")

        payload: dict[str, Any] = {
            "model": self._image_model,
            "prompt": prompt,
            "images": [{"image_url": _to_data_uri(img)} for img in reference_images],
        }
        started = time.monotonic()
        try:
            response = await self._http_client.post(
                f"{self._base_url}/images/edits",
                headers={"Authorization": f"Bearer {api_key}"},
                json=payload,
            )
        except httpx.HTTPError as err:
            raise MetaAPIError(f"Muse Image edit transport error: {type(err).__name__}") from err
        logger.info(
            "Meta API call: image-edit %s -> HTTP %s in %.1fs",
            self._image_model,
            response.status_code,
            time.monotonic() - started,
        )

        if response.status_code != 200:
            raise MetaAPIError(f"Muse Image edit error (status={response.status_code}).")

        return await self._extract_image_bytes(response.json())

    async def generate_image_workflow(
        self,
        prompt: str,
        *,
        reference_images: Sequence[bytes] = (),
        reasoning_effort: str = "high",
    ) -> tuple[bytes, str]:
        """Run a reasoning-guided Muse Image 1.0 workflow on `POST /v1/responses`.

        Supports all 3 Meta Model API Playground image workflows (and mirrors ComfyUI hub graphs
        with zero Comfy Cloud subscription):
        - Product visuals (`0` or `1` reference image + scene staging prompt)
        - Restore image (`1` reference image + studio detail & lighting restoration prompt)
        - Multi-Image combine (`2+` reference images combined into a diptych or styled room)

        Returns `(image_bytes, reasoning_summary)`.
        """
        api_key = self._require_api_key()
        content_blocks: list[dict[str, str]] = [{"type": "input_text", "text": prompt}]
        for img in reference_images:
            content_blocks.append({"type": "input_image", "image_url": _to_data_uri(img)})

        payload: dict[str, Any] = {
            "model": self._image_model,
            "reasoning": {"effort": reasoning_effort},
            "input": [{"role": "user", "content": content_blocks}],
        }
        started = time.monotonic()
        try:
            response = await self._http_client.post(
                f"{self._base_url}/responses",
                headers={"Authorization": f"Bearer {api_key}"},
                json=payload,
            )
        except httpx.HTTPError as err:
            raise MetaAPIError(
                f"Muse Image workflow transport error: {type(err).__name__}"
            ) from err
        logger.info(
            "Meta API call: image-workflow %s (refs=%d, effort=%s) -> HTTP %s in %.1fs",
            self._image_model,
            len(reference_images),
            reasoning_effort,
            response.status_code,
            time.monotonic() - started,
        )

        if response.status_code != 200:
            raise MetaAPIError(f"Muse Image workflow error (status={response.status_code}).")

        body = response.json()
        output_items = body.get("output") if isinstance(body, dict) else None
        if not isinstance(output_items, list):
            raise MetaAPIError("Muse Image workflow response missing 'output' array.")

        reasoning_parts: list[str] = []
        image_b64: str | None = None
        for item in output_items:
            if not isinstance(item, dict):
                continue
            if item.get("type") == "reasoning":
                for summary_block in item.get("summary") or []:
                    if isinstance(summary_block, dict) and isinstance(
                        summary_block.get("text"), str
                    ):
                        reasoning_parts.append(summary_block["text"].strip())
            elif item.get("type") == "image_generation_call" and isinstance(
                item.get("result"), str
            ):
                image_b64 = item["result"]

        if not image_b64:
            raise MetaAPIError("Muse Image workflow response did not include an image result.")
        return base64.b64decode(image_b64), "\n".join(reasoning_parts)

    async def transcribe_audio(
        self,
        audio_bytes: bytes,
        *,
        filename: str = "voice_note.wav",
        model: str = "muse-voice-transcribe-1.0",
    ) -> str:
        """Transcribe seller voice notes via `muse-voice-transcribe-1.0`."""
        api_key = self._require_api_key()
        try:
            response = await self._http_client.post(
                f"{self._base_url}/audio/transcriptions",
                headers={"Authorization": f"Bearer {api_key}"},
                files={"file": (filename, audio_bytes, "audio/wav")},
                data={"model": model},
            )
        except httpx.HTTPError as err:
            raise MetaAPIError(
                f"Muse Voice Transcribe transport error: {type(err).__name__}"
            ) from err
        if response.status_code != 200:
            raise MetaAPIError(f"Muse Voice Transcribe error (status={response.status_code}).")
        body = response.json()
        text = body.get("text") if isinstance(body, dict) else None
        if not isinstance(text, str):
            raise MetaAPIError("Muse Voice Transcribe response missing 'text'.")
        return text.strip()

    async def _extract_image_bytes(self, body: Any) -> bytes:
        items = body.get("data") if isinstance(body, dict) else None
        if not isinstance(items, list) or not items:
            raise MetaAPIError("Muse Image returned no image data.")

        first = items[0]
        if isinstance(first, dict) and isinstance(first.get("b64_json"), str):
            return base64.b64decode(first["b64_json"])
        if isinstance(first, dict) and isinstance(first.get("url"), str):
            img_resp = await self._http_client.get(first["url"])
            if img_resp.status_code != 200:
                raise MetaAPIError("Failed to download generated Muse Image URL.")
            return img_resp.content
        raise MetaAPIError("Muse Image response missing 'b64_json' or 'url'.")

    async def segment(self, image: bytes, prompt: str | None = None) -> bytes:
        """Segment a product/artwork cutout mask via SAM 3.1 (`sam-3.1` on `POST /v1/responses`)."""
        api_key = self._require_api_key()
        if len(image) > 10 * 1024 * 1024:
            raise MetaAPIError("Image exceeds 10 MB segmentation limit.")

        data_uri = _to_data_uri(image)
        target_prompt = prompt or "artwork canvas product foreground"
        payload: dict[str, Any] = {
            "model": self._sam_model,
            "input": [
                {
                    "role": "user",
                    "content": [
                        {"type": "input_text", "text": target_prompt},
                        {"type": "input_image", "image_url": data_uri},
                    ],
                }
            ],
        }
        started = time.monotonic()
        try:
            response = await self._http_client.post(
                f"{self._base_url}/responses",
                headers={"Authorization": f"Bearer {api_key}"},
                json=payload,
            )
        except httpx.HTTPError as err:
            raise MetaAPIError(f"SAM 3.1 transport error: {type(err).__name__}") from err
        logger.info(
            "Meta API call: segment %s -> HTTP %s in %.1fs",
            self._sam_model,
            response.status_code,
            time.monotonic() - started,
        )

        if response.status_code != 200:
            raise MetaAPIError(f"SAM 3.1 segmentation error (status={response.status_code}).")

        content_type = response.headers.get("content-type", "").lower()
        if content_type.startswith("image/"):
            _detect_image_mime(response.content)
            return response.content

        try:
            body = response.json()
        except ValueError as err:
            raise MetaAPIError("SAM 3.1 returned malformed JSON.") from err
        if isinstance(body, dict):
            rendered_mask = _extract_sam_mask_from_responses(body)
            if rendered_mask is not None:
                return rendered_mask

            data = body.get("data")
            first = data[0] if isinstance(data, list) and data else None
            mask_b64 = (
                body.get("mask_b64")
                or body.get("b64_json")
                or (first.get("b64_json") if isinstance(first, dict) else None)
            )
            if isinstance(mask_b64, str) and mask_b64:
                try:
                    mask_bytes = base64.b64decode(mask_b64, validate=True)
                except (binascii.Error, ValueError) as err:
                    raise MetaAPIError("SAM 3.1 returned invalid base64 mask bytes.") from err
                _detect_image_mime(mask_bytes)
                return mask_bytes

        raise MetaAPIError("SAM 3.1 response did not contain mask bytes.")


_shared_client: MetaClient | None = None


def get_meta_client() -> MetaClient:
    """Return the shared process-wide MetaClient instance."""
    global _shared_client
    if _shared_client is None:
        _shared_client = MetaClient()
    return _shared_client


async def chat_structured(
    messages: Sequence[ChatCompletionMessageParam],
    response_model: type[ModelT],
    *,
    model: str | None = None,
    temperature: float = 0.2,
    client: MetaClient | None = None,
) -> ModelT:
    """Convenience helper that runs `MetaClient.chat_structured` on the shared client."""
    active_client = client or get_meta_client()
    return await active_client.chat_structured(
        messages=messages,
        response_model=response_model,
        model=model,
        temperature=temperature,
    )
