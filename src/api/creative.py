"""Ad Creative Studio routes (Flow 2)."""

from typing import Annotated, Any

from fastapi import APIRouter, Depends
from pydantic import Field

from src.clients.comfyui import SUPPORTED_COMFY_WORKFLOWS, discover_comfy_cli
from src.models.creative import CreativeSet, EditableCreativeBrief, GenerateAdsRequest
from src.services.ad_creative import AdCreativeService

router = APIRouter(tags=["creative"])


def get_ad_creative_service() -> AdCreativeService:
    return AdCreativeService()


@router.get("/creative-models")
async def list_creative_models() -> dict[str, Any]:
    """Return available Meta + ComfyUI workflows (Krea 3, LTX-2.5 DFR, MiniMax H3) and CLI info."""
    return {
        "meta_models": {
            "brief_and_vision": "muse-spark-1.3",
            "segmentation": "sam-3.1 (/v1/responses)",
            "image_generation": "muse-image-1.0 (/v1/images/generations)",
            "image_edit": "muse-image-1.0 (/v1/images/edits)",
        },
        "comfyui_workflows": SUPPORTED_COMFY_WORKFLOWS,
        "comfy_cli": discover_comfy_cli(),
    }


GenerateAdsResponse = Annotated[CreativeSet | EditableCreativeBrief, Field(discriminator="kind")]


@router.post("/generate-ads", response_model=GenerateAdsResponse)
async def generate_ads(
    request: GenerateAdsRequest,
    service: Annotated[AdCreativeService, Depends(get_ad_creative_service)],
) -> CreativeSet | EditableCreativeBrief:
    """draft=true returns a brief to review (kind="draft"); send it back as `brief` to render."""
    if request.draft:
        return await service.draft(request)
    return await service.generate(request)
