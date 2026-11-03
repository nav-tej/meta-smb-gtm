"""Ad Creative Studio routes (Flow 2)."""

from typing import Annotated

from fastapi import APIRouter, Depends

from src.models.creative import CreativeSet, GenerateAdsRequest
from src.services.ad_creative import AdCreativeService

router = APIRouter(tags=["creative"])


def get_ad_creative_service() -> AdCreativeService:
    return AdCreativeService()


@router.post("/generate-ads", response_model=CreativeSet)
async def generate_ads(
    request: GenerateAdsRequest,
    service: Annotated[AdCreativeService, Depends(get_ad_creative_service)],
) -> CreativeSet:
    return await service.generate(request)
