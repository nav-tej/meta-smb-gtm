"""ComfyUI HTTP API client for open-weight creative variant workflows.

Loads ComfyUI API-format workflow graphs from `workflows/`, uploads reference/mask
images via `/upload/image`, fills input node parameters, submits via `POST /prompt`,
polls `/history/{prompt_id}`, and downloads rendered outputs via `/view`.
"""

from __future__ import annotations

import asyncio
import copy
import json
import logging
import re
import shutil
from pathlib import Path
from typing import Any

import httpx

from src.config import Settings, get_settings

logger = logging.getLogger(__name__)

WORKFLOWS_DIR = Path(__file__).resolve().parents[2] / "workflows"
_SAFE_NAME_RE = re.compile(r"^[a-zA-Z0-9_-]+$")
DEFAULT_TIMEOUT = httpx.Timeout(90.0, connect=5.0)

SUPPORTED_COMFY_WORKFLOWS: dict[str, dict[str, str]] = {
    "krea3_scene_edit": {
        "model": "Krea 3",
        "media_type": "image",
        "template_source": "api_krea3_image_edit",
        "description": "Targeted regional collector scene restaging & relighting + SAM 3.1 mask",
    },
    "krea2_turbo_style_ref": {
        "model": "Krea-2 Turbo Int8 (krea2_turbo_int8_convrot.safetensors)",
        "media_type": "image",
        "template_source": "image_krea2_turbo_int8_image_style_reference",
        "description": "Open-weight 8-step MMDiT style-referenced collector scene + SAM 3.1 mask",
    },
    "ideogram4_collector_card": {
        "model": "Ideogram v4 Int8 (ideogram4_int8_convrot.safetensors)",
        "media_type": "image",
        "template_source": "image_ideogram4_t2i_int8",
        "description": "Open-weight Ideogram v4 collector framing with plaque typography",
    },
    "flux_krea_scene_relight": {
        "model": "FLUX.1-Krea-dev (flux1-krea-dev.safetensors)",
        "media_type": "image",
        "template_source": "flux1_krea_dev",
        "description": "Open-weight FLUX.1-Krea-dev collector scene relighting + SAM 3.1 mask",
    },
    "placement_outpaint": {
        "model": "FLUX.1-Fill-dev (flux1-fill-dev.safetensors)",
        "media_type": "image",
        "template_source": "flux1_fill_dev",
        "description": "Aspect-ratio outpaint for 1:1, 4:5, and 9:16 Meta ad placements",
    },
    "upscale_4x": {
        "model": "4x-UltraSharp.pth",
        "media_type": "image",
        "template_source": "upscale_4x",
        "description": "4x high-DPI creative upscale",
    },
    "ltx2_5_dfr_i2v": {
        "model": (
            "LTX-2.5 DFR 22B Int8 "
            "(ltx-2.5-22b-distilled-transformer-comfy-int8-convrot.safetensors)"
        ),
        "media_type": "video",
        "template_source": "video_ltx2_5_dfr_i2v",
        "description": "Open-weight LTX-2.5 Diffusion Fidelity Rendering I2V + spatial x2 + audio",
    },
    "minimax_h3_i2v": {
        "model": "MiniMax H3 8-Step Turbo Int8 (minimax_h3_fl2va_pruned_int8_convrot.safetensors)",
        "media_type": "video",
        "template_source": "video_minimax_h3_i2v",
        "description": "Open-weight MiniMax H3 omni-modal I2V + native stereo audio in one pass",
    },
}


class ComfyUIError(Exception):
    """Raised when a ComfyUI workflow submission, poll, or output fetch fails."""


def load_workflow_template(
    name: str, *, workflows_dir: Path | None = None
) -> dict[str, dict[str, Any]]:
    """Load and return a deep copy of `workflows/{name}.json`."""
    clean_name = name.removesuffix(".json").strip()
    if not _SAFE_NAME_RE.match(clean_name):
        raise ComfyUIError(f"Invalid workflow name '{name}'.")

    base_dir = workflows_dir or WORKFLOWS_DIR
    path = base_dir / f"{clean_name}.json"
    if not path.is_file():
        raise ComfyUIError(f"Workflow file not found: {path}")

    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as err:
        raise ComfyUIError(f"Invalid JSON in workflow '{clean_name}': {err}") from err

    if not isinstance(raw, dict):
        raise ComfyUIError(f"Workflow '{clean_name}' root must be a JSON object.")
    return copy.deepcopy(raw)


def apply_node_inputs(
    workflow: dict[str, dict[str, Any]],
    node_inputs: dict[str, dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    """Return a copy of `workflow` with `node_inputs[node_id]` merged into each node's `inputs`."""
    graph = copy.deepcopy(workflow)
    for node_id, overrides in node_inputs.items():
        if node_id not in graph:
            raise ComfyUIError(f"Node '{node_id}' does not exist in workflow.")
        target_inputs = graph[node_id].setdefault("inputs", {})
        if not isinstance(target_inputs, dict):
            raise ComfyUIError(f"Node '{node_id}' has malformed 'inputs'.")
        target_inputs.update(overrides)
    return graph


class ComfyUIClient:
    """Async HTTP wrapper around local or hosted ComfyUI servers."""

    def __init__(
        self,
        *,
        settings: Settings | None = None,
        base_url: str | None = None,
        api_key: str | None = None,
        http_client: httpx.AsyncClient | None = None,
        workflows_dir: Path | None = None,
        poll_interval_seconds: float = 0.5,
        max_poll_attempts: int = 120,
    ) -> None:
        cfg = settings or get_settings()
        self._base_url = (
            (base_url if base_url is not None else cfg.comfyui_base_url).strip().rstrip("/")
        )
        self._api_key = (api_key if api_key is not None else cfg.comfyui_api_key).strip()
        self._owns_client = http_client is None
        self._http_client = http_client or httpx.AsyncClient(timeout=DEFAULT_TIMEOUT)
        self._workflows_dir = workflows_dir or WORKFLOWS_DIR
        self._poll_interval = poll_interval_seconds
        self._max_polls = max_poll_attempts

    def _headers(self) -> dict[str, str]:
        if self._api_key:
            return {"Authorization": f"Bearer {self._api_key}"}
        return {}

    async def aclose(self) -> None:
        if self._owns_client:
            await self._http_client.aclose()

    async def is_reachable(self) -> bool:
        """Quick check whether ComfyUI `/system_stats` responds with HTTP 200."""
        try:
            resp = await self._http_client.get(
                f"{self._base_url}/system_stats",
                headers=self._headers(),
                timeout=2.0,
            )
            return resp.status_code == 200
        except httpx.HTTPError:
            return False

    async def upload_image(self, image_bytes: bytes, filename: str = "input.png") -> str:
        """Upload an image to ComfyUI's input directory and return the stored filename."""
        try:
            resp = await self._http_client.post(
                f"{self._base_url}/upload/image",
                headers=self._headers(),
                files={"image": (filename, image_bytes, "image/png")},
                data={"overwrite": "true"},
            )
        except httpx.HTTPError as err:
            raise ComfyUIError(f"ComfyUI image upload failed: {type(err).__name__}") from err

        if resp.status_code != 200:
            raise ComfyUIError(f"ComfyUI image upload returned HTTP {resp.status_code}.")
        payload = resp.json()
        stored_name = payload.get("name") if isinstance(payload, dict) else None
        if not isinstance(stored_name, str) or not stored_name:
            raise ComfyUIError("ComfyUI upload response missing image 'name'.")
        return stored_name

    async def run_workflow(
        self,
        name: str,
        inputs: dict[str, dict[str, Any]],
    ) -> list[bytes]:
        """Load `workflows/{name}.json`, apply `inputs`, execute, and return output image bytes."""
        template = load_workflow_template(name, workflows_dir=self._workflows_dir)
        filled_graph = apply_node_inputs(template, inputs)

        try:
            submit_resp = await self._http_client.post(
                f"{self._base_url}/prompt",
                headers=self._headers(),
                json={"prompt": filled_graph},
            )
        except httpx.HTTPError as err:
            raise ComfyUIError(f"ComfyUI /prompt request failed: {type(err).__name__}") from err

        if submit_resp.status_code != 200:
            raise ComfyUIError(
                f"ComfyUI /prompt rejected workflow (HTTP {submit_resp.status_code})."
            )

        submit_body = submit_resp.json()
        prompt_id = submit_body.get("prompt_id") if isinstance(submit_body, dict) else None
        if not isinstance(prompt_id, str) or not prompt_id:
            raise ComfyUIError("ComfyUI /prompt response missing 'prompt_id'.")

        outputs_meta = await self._poll_history(prompt_id)
        return await self._download_outputs(outputs_meta)

    async def _poll_history(self, prompt_id: str) -> dict[str, Any]:
        for _ in range(self._max_polls):
            try:
                hist_resp = await self._http_client.get(
                    f"{self._base_url}/history/{prompt_id}",
                    headers=self._headers(),
                )
            except httpx.HTTPError as err:
                raise ComfyUIError(f"ComfyUI /history poll failed: {type(err).__name__}") from err

            if hist_resp.status_code == 200:
                body = hist_resp.json()
                if isinstance(body, dict) and prompt_id in body:
                    entry = body[prompt_id]
                    if isinstance(entry, dict) and isinstance(entry.get("outputs"), dict):
                        return entry["outputs"]
            if self._poll_interval > 0:
                await asyncio.sleep(self._poll_interval)

        raise ComfyUIError(f"ComfyUI workflow '{prompt_id}' timed out waiting for outputs.")

    async def _download_outputs(self, outputs_meta: dict[str, Any]) -> list[bytes]:
        rendered: list[bytes] = []
        for node_output in outputs_meta.values():
            if not isinstance(node_output, dict):
                continue
            media_items: list[Any] = []
            for key in ("images", "videos", "gifs"):
                bucket = node_output.get(key)
                if isinstance(bucket, list):
                    media_items.extend(bucket)

            for media_ref in media_items:
                if not isinstance(media_ref, dict) or not media_ref.get("filename"):
                    continue
                params = {
                    "filename": str(media_ref["filename"]),
                    "subfolder": str(media_ref.get("subfolder", "")),
                    "type": str(media_ref.get("type", "output")),
                }
                try:
                    view_resp = await self._http_client.get(
                        f"{self._base_url}/view",
                        headers=self._headers(),
                        params=params,
                    )
                except httpx.HTTPError as err:
                    raise ComfyUIError(f"ComfyUI /view fetch failed: {type(err).__name__}") from err

                if view_resp.status_code != 200:
                    raise ComfyUIError(f"ComfyUI /view returned HTTP {view_resp.status_code}.")
                rendered.append(view_resp.content)

        if not rendered:
            raise ComfyUIError("ComfyUI workflow completed but produced zero output artifacts.")
        return rendered


def discover_comfy_cli() -> dict[str, Any]:
    """Inspect local `comfy` CLI binary and installed `.claude/skills/comfy*` skills."""
    comfy_bin = shutil.which("comfy") or (
        str(Path.home() / ".local" / "bin" / "comfy")
        if (Path.home() / ".local" / "bin" / "comfy").is_file()
        else None
    )
    project_skills_dir = WORKFLOWS_DIR.parent / ".claude" / "skills"
    installed_skills = sorted(p.parent.name for p in project_skills_dir.glob("comfy*/SKILL.md"))
    gallery_dir = WORKFLOWS_DIR / "gallery"
    gallery_templates = (
        sorted(p.stem for p in gallery_dir.glob("*.json")) if gallery_dir.is_dir() else []
    )
    return {
        "comfy_cli_available": comfy_bin is not None,
        "comfy_cli_path": comfy_bin,
        "installed_skills": installed_skills,
        "workflows_supported": list(SUPPORTED_COMFY_WORKFLOWS.keys()),
        "gallery_templates_cached": gallery_templates,
    }


_shared_comfy_client: ComfyUIClient | None = None


def get_comfyui_client() -> ComfyUIClient:
    """Return the shared process-wide ComfyUIClient."""
    global _shared_comfy_client
    if _shared_comfy_client is None:
        _shared_comfy_client = ComfyUIClient()
    return _shared_comfy_client


async def run_workflow(
    name: str,
    inputs: dict[str, dict[str, Any]],
    *,
    client: ComfyUIClient | None = None,
) -> list[bytes]:
    """Convenience helper matching `src/clients/comfyui.py` contract."""
    active = client or get_comfyui_client()
    return await active.run_workflow(name, inputs)
