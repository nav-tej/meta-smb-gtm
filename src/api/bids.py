"""Bid Advisor routes (Flow 3). Advisory only; nothing is written to an ad account."""

from typing import Annotated

from fastapi import APIRouter, Depends

from src.models.bids import BidAdviceRequest, BidRecommendation
from src.services.bid_advisor import BidAdvisorService

router = APIRouter(tags=["bids"])


def get_bid_advisor_service() -> BidAdvisorService:
    return BidAdvisorService()


@router.post("/bid-advice", response_model=BidRecommendation)
async def bid_advice(
    request: BidAdviceRequest,
    service: Annotated[BidAdvisorService, Depends(get_bid_advisor_service)],
) -> BidRecommendation:
    return await service.advise(request)
