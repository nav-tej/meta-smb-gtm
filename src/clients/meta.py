"""Meta Model API client (Muse Spark, Muse Image, SAM 3.1).

The single place that talks to api.meta.ai. Uses the OpenAI-compatible SDK with base_url
overridden. Services must call this module rather than instantiating OpenAI clients directly.
"""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Sequence
from typing import Any, TypeVar

import httpx
from openai import APIError, AsyncOpenAI, OpenAIError
from openai.types.chat import ChatCompletionMessageParam
from pydantic import BaseModel, ValidationError

from src.config import Settings, get_settings

logger = logging.getLogger(__name__)

ModelT = TypeVar("ModelT", bound=BaseModel)

DEFAULT_TIMEOUT = httpx.Timeout(60.0, connect=10.0)
_CODE_FENCE_RE = re.compile(r"^\s*```(?:json)?\s*(.*?)\s*```\s*$", re.DOTALL | re.IGNORECASE)


class MetaAPIError(Exception):
    """Raised when a Meta Model API request or structured-output parse fails."""


def _strip_code_fences(raw_text: str) -> str:
    """Extract inner JSON if the model wrapped its JSON output in markdown fences."""
    stripped = raw_text.strip()
    match = _CODE_FENCE_RE.match(stripped)
    return match.group(1).strip() if match else stripped


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
        http_client: httpx.AsyncClient | None = None,
        openai_client: AsyncOpenAI | None = None,
    ) -> None:
        cfg = settings or get_settings()
        self._api_key = (api_key if api_key is not None else cfg.meta_model_api_key).strip()
        self._base_url = (base_url if base_url is not None else cfg.meta_model_api_base_url).strip()
        self._spark_model = (
            spark_model if spark_model is not None else cfg.muse_spark_model
        ).strip()
        self._owns_http_client = http_client is None and openai_client is None
        self._http_client = http_client or httpx.AsyncClient(timeout=DEFAULT_TIMEOUT)
        self._openai: AsyncOpenAI | None = openai_client

    @property
    def spark_model(self) -> str:
        return self._spark_model

    def _get_openai(self) -> AsyncOpenAI:
        if self._openai is not None:
            return self._openai
        if not self._api_key:
            raise MetaAPIError(
                "META_MODEL_API_KEY is missing. Set it in your environment or .env file."
            )
        self._openai = AsyncOpenAI(
            api_key=self._api_key,
            base_url=self._base_url,
            http_client=self._http_client,
            max_retries=1,
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

    async def _create_chat_completion(
        self,
        *,
        client: AsyncOpenAI,
        model: str,
        messages: list[ChatCompletionMessageParam],
        temperature: float,
    ) -> str:
        try:
            completion = await client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=temperature,
                response_format={"type": "json_object"},
            )
        except APIError as err:
            raise MetaAPIError(
                f"Meta Model API error (status={getattr(err, 'status_code', 'unknown')}): "
                f"{err.message}"
            ) from err
        except (OpenAIError, httpx.HTTPError) as err:
            raise MetaAPIError(f"Meta Model API transport failure: {type(err).__name__}") from err

        if not completion.choices:
            raise MetaAPIError("Meta Model API returned no completion choices.")
        content: Any = completion.choices[0].message.content
        if not isinstance(content, str) or not content.strip():
            raise MetaAPIError("Meta Model API returned an empty message content.")
        return content

    async def generate_image(
        self, prompt: str, reference_image: bytes | None = None
    ) -> bytes:  # pragma: no cover - Flow 2 stub
        """Generate an ad creative image via Muse Image (implemented in Flow 2)."""
        raise NotImplementedError("generate_image is part of Flow 2 (ad_creative).")

    async def segment(
        self, image: bytes, prompt: str | None = None
    ) -> bytes:  # pragma: no cover - Flow 2 stub
        """Segment a product cutout via SAM 3.1 (implemented in Flow 2)."""
        raise NotImplementedError("segment is part of Flow 2 (ad_creative).")


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
