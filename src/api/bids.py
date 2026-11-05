"""Bid Advisor routes (Flow 3). Advisory only; nothing is written to an ad account."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, Field

from src.api.demo import LiveMode
from src.models.bids import BidAdviceRequest, BidRecommendation, PerformanceMetrics
from src.models.intel import CompetitorBrief
from src.services import demo, result_cache
from src.services.bid_advisor import BidAdvisorService, compute_metrics, load_campaign_csv

router = APIRouter(tags=["bids"])


class CsvBidAdviceRequest(BaseModel):
    csv_text: str = Field(min_length=10, description="Raw Meta Ads Manager CSV export text.")
    competitor_brief: CompetitorBrief | None = None
    account_name: str = Field(default="Art of Sarabjit Singh", max_length=120)
    currency: str = Field(default="USD", min_length=3, max_length=3)
    seller_goal: str = Field(default="More sales without raising total spend.", max_length=500)
    deterministic_only: bool = Field(
        default=False,
        description="When True, returns deterministic PerformanceMetrics without calling LLM.",
    )


def get_bid_advisor_service() -> BidAdvisorService:
    return BidAdvisorService()


@router.post("/bid-advice", response_model=BidRecommendation)
async def bid_advice(
    request: BidAdviceRequest,
    service: Annotated[BidAdvisorService, Depends(get_bid_advisor_service)],
    live: LiveMode,
    response: Response,
) -> BidRecommendation:
    if not live:
        return demo.demo_bid_recommendation()
    return await result_cache.cached(
        "bid-advice", request, BidRecommendation, lambda: service.advise(request), response
    )


@router.post("/bid-advice/csv", response_model=BidRecommendation | PerformanceMetrics)
async def bid_advice_csv(
    request: CsvBidAdviceRequest,
    service: Annotated[BidAdvisorService, Depends(get_bid_advisor_service)],
    live: LiveMode,
    response: Response,
) -> BidRecommendation | PerformanceMetrics:
    try:
        campaign = load_campaign_csv(
            request.csv_text,
            account_name=request.account_name,
            currency=request.currency,
        )
    except ValueError as err:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"Invalid campaign CSV: {err}",
        ) from err

    if request.deterministic_only or request.competitor_brief is None:
        return compute_metrics(campaign)
    if not live:
        return demo.demo_bid_recommendation()
    advice_request = BidAdviceRequest(
        campaign=campaign,
        competitor_brief=request.competitor_brief,
        seller_goal=request.seller_goal,
    )
    return await result_cache.cached(
        "bid-advice",
        advice_request,
        BidRecommendation,
        lambda: service.advise(advice_request),
        response,
    )
