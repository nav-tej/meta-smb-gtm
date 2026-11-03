"""Competitor Intel routes (Flow 1)."""

from typing import Annotated

from fastapi import APIRouter, Depends

from src.models.intel import CompetitorBrief, CompetitorIntelRequest
from src.services.competitor_intel import CompetitorIntelService

router = APIRouter(tags=["intel"])


def get_competitor_intel_service() -> CompetitorIntelService:
    return CompetitorIntelService()


@router.post("/analyze-competitors", response_model=CompetitorBrief)
async def analyze_competitors(
    request: CompetitorIntelRequest,
    service: Annotated[CompetitorIntelService, Depends(get_competitor_intel_service)],
) -> CompetitorBrief:
    return await service.analyze(request)
