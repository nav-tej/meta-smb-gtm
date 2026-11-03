"""Ad Creative Studio routes (Flow 2)."""

from fastapi import APIRouter, HTTPException, status

from src.models.creative import CreativeSet, GenerateAdsRequest
from src.services import ad_creative

router = APIRouter(tags=["creative"])


@router.post("/generate-ads", response_model=CreativeSet)
async def generate_ads(request: GenerateAdsRequest) -> CreativeSet:
    try:
        return await ad_creative.generate_ads(request)
    except NotImplementedError as err:
        raise HTTPException(status.HTTP_501_NOT_IMPLEMENTED, detail=str(err)) from err
