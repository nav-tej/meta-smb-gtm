from __future__ import annotations

import json
from collections.abc import AsyncIterator
from datetime import date

import httpx
import pytest
import respx
from pydantic import ValidationError

from src.clients.meta import MetaAPIError, MetaClient
from src.config import Settings
from src.models.bids import AdSetDailyPerformance, BidAdviceRequest, CampaignPerformance
from src.models.intel import CompetitorBrief, Evidence, ResearchFinding
from src.services.bid_advisor import BidAdvisorService, compute_metrics
from tests.conftest import (
    INTEREST,
    META_BASE_URL,
    PROSPECTING,
    RETARGETING,
    chat_completion,
)

CHAT_URL = f"{META_BASE_URL}/chat/completions"


@pytest.fixture
async def meta_client(test_settings: Settings) -> AsyncIterator[MetaClient]:
    async with httpx.AsyncClient() as http_client:
        yield MetaClient(settings=test_settings, http_client=http_client)


@pytest.fixture
def request_model(
    campaign: CampaignPerformance, competitor_brief: CompetitorBrief
) -> BidAdviceRequest:
    return BidAdviceRequest(
        campaign=campaign, competitor_brief=competitor_brief, seller_goal="More holiday sales."
    )


def test_row_derives_missing_ratios() -> None:
    row = AdSetDailyPerformance(
        day=date(2026, 10, 1),
        campaign_name="C",
        ad_set_name="A",
        impressions=1000,
        clicks=20,
        conversions=2,
        spend=10.0,
        roas=3.0,
    )
    assert row.ctr == 2.0
    assert row.cpc == 0.5
    assert row.cpm == 10.0
    assert row.conversion_value == 30.0


def test_row_rejects_more_clicks_than_impressions() -> None:
    with pytest.raises(ValidationError, match="clicks cannot exceed impressions"):
        AdSetDailyPerformance(
            day=date(2026, 10, 1),
            campaign_name="C",
            ad_set_name="A",
            impressions=10,
            clicks=11,
            conversions=0,
            spend=1.0,
        )


def test_campaign_requires_rows() -> None:
    with pytest.raises(ValidationError):
        CampaignPerformance(rows=[])


def test_compute_metrics_aggregates_from_counts(campaign: CampaignPerformance) -> None:
    metrics = compute_metrics(campaign)
    account = metrics.account_totals

    assert metrics.currency == "USD"
    assert (metrics.start_date, metrics.end_date, metrics.days) == (
        date(2026, 10, 1),
        date(2026, 10, 8),
        8,
    )
    assert account.spend == 696.0
    assert account.conversions == 45
    assert account.conversion_value == 2025.0
    assert account.roas == round(2025 / 696, 4)
    # CTR is total clicks / total impressions, not an average of daily CTRs
    assert account.ctr == round(account.clicks / account.impressions * 100, 4)
    assert [m.ad_set_name for m in metrics.ad_sets] == [PROSPECTING, INTEREST, RETARGETING]
    assert sum(m.spend_share for m in metrics.ad_sets) == pytest.approx(1.0, abs=1e-3)


def test_compute_metrics_flags(campaign: CampaignPerformance) -> None:
    by_name = {m.ad_set_name: m for m in compute_metrics(campaign).ad_sets}

    retargeting = by_name[RETARGETING]
    assert retargeting.spend_pacing == 1.0
    assert "high_roas" in retargeting.flags
    assert "budget_limited_winner" in retargeting.flags

    interest = by_name[INTEREST]
    assert interest.ctr_trend_pct is not None and interest.ctr_trend_pct < -40
    assert interest.frequency_trend_pct is not None and interest.frequency_trend_pct > 0
    assert "creative_fatigue" in interest.flags
    assert "low_roas_material_spend" in interest.flags

    assert by_name[PROSPECTING].flags == []


def test_compute_metrics_target_flags(campaign: CampaignPerformance) -> None:
    by_name = {
        m.ad_set_name: m
        for m in compute_metrics(campaign, target_roas=3.0, target_cpa=15.0).ad_sets
    }
    assert "below_target_roas" in by_name[INTEREST].flags
    assert "above_target_cpa" in by_name[PROSPECTING].flags
    assert "below_target_roas" not in by_name[RETARGETING].flags


def test_trends_need_enough_days(campaign: CampaignPerformance) -> None:
    short = CampaignPerformance(rows=[r for r in campaign.rows if r.day < date(2026, 10, 4)])
    for ad_set in compute_metrics(short).ad_sets:
        assert ad_set.ctr_trend_pct is None
        assert ad_set.roas_trend_pct is None


def test_no_conversion_value_means_no_roas() -> None:
    rows = [
        AdSetDailyPerformance(
            day=date(2026, 10, d),
            campaign_name="C",
            ad_set_name="A",
            impressions=1000,
            clicks=10,
            conversions=0,
            spend=25.0,
        )
        for d in range(1, 3)
    ]
    metrics = compute_metrics(CampaignPerformance(rows=rows))
    ad_set = metrics.ad_sets[0]
    assert metrics.account_totals.roas is None
    assert ad_set.roas_vs_account is None
    assert "spend_without_conversions" in ad_set.flags
    assert "low_volume" in ad_set.flags


@respx.mock
async def test_advise_happy_path(
    meta_client: MetaClient, request_model: BidAdviceRequest, spark_bid_content: str
) -> None:
    route = respx.post(CHAT_URL).mock(
        return_value=httpx.Response(200, json=chat_completion(spark_bid_content))
    )

    result = await BidAdvisorService(meta_client=meta_client).advise(request_model)

    assert route.call_count == 1
    assert result.model == "muse-spark-1.3"
    assert result.competitor_domain == "example-prints.com"
    assert result.currency == "USD"
    # The hallucinated "Lookalike - Purchasers 1%" adjustment is dropped
    assert [a.ad_set_name for a in result.bid_adjustments] == [RETARGETING, INTEREST]
    shift = result.budget_reallocations[0]
    # 20% of the interest ad set's $29.00 average daily spend, computed in Python
    assert shift.daily_amount == 5.8
    assert shift.currency == "USD"
    assert result.pause_candidates[0].ad_set_name == INTEREST
    assert result.audience_suggestions[0].competitor_gap.startswith("No small")
    assert len(result.metrics.ad_sets) == 3


@respx.mock
async def test_advise_prompt_delimits_untrusted_input(
    meta_client: MetaClient, request_model: BidAdviceRequest, spark_bid_content: str
) -> None:
    route = respx.post(CHAT_URL).mock(
        return_value=httpx.Response(200, json=chat_completion(spark_bid_content))
    )

    await BidAdvisorService(meta_client=meta_client).advise(request_model)

    body = json.loads(route.calls[0].request.content)
    assert body["model"] == "muse-spark-1.3"
    system, user = body["messages"][0]["content"], body["messages"][1]["content"]
    assert "untrusted" in system.lower()
    assert "ARITHMETIC RULE" in system
    untrusted = user.split("<untrusted_competitor_data>")[1].split("</untrusted_competitor_data>")[
        0
    ]
    assert "IGNORE PREVIOUS INSTRUCTIONS" in untrusted
    assert user.count("IGNORE PREVIOUS INSTRUCTIONS") == 1
    assert "<computed_metrics>" in user


@respx.mock
async def test_advise_retries_once_on_malformed_json(
    meta_client: MetaClient, request_model: BidAdviceRequest, spark_bid_content: str
) -> None:
    route = respx.post(CHAT_URL).mock(
        side_effect=[
            httpx.Response(200, json=chat_completion('{"performance_summary": "cut off')),
            httpx.Response(200, json=chat_completion(spark_bid_content)),
        ]
    )

    result = await BidAdvisorService(meta_client=meta_client).advise(request_model)

    assert route.call_count == 2
    retry_messages = json.loads(route.calls[1].request.content)["messages"]
    assert "did not validate" in retry_messages[-1]["content"]
    assert result.next_steps


@respx.mock
async def test_advise_raises_after_second_malformed_response(
    meta_client: MetaClient, request_model: BidAdviceRequest
) -> None:
    bad = json.dumps({"performance_summary": "ok", "bid_adjustments": [{"action": "yolo"}]})
    respx.post(CHAT_URL).mock(return_value=httpx.Response(200, json=chat_completion(bad)))

    with pytest.raises(MetaAPIError, match="BidRecommendationLLMOutput"):
        await BidAdvisorService(meta_client=meta_client).advise(request_model)


@respx.mock
async def test_advise_surfaces_api_errors(
    meta_client: MetaClient, request_model: BidAdviceRequest
) -> None:
    respx.post(CHAT_URL).mock(
        return_value=httpx.Response(400, json={"error": {"message": "unknown model"}})
    )

    with pytest.raises(MetaAPIError, match="status=400"):
        await BidAdvisorService(meta_client=meta_client).advise(request_model)


@respx.mock
async def test_advise_traces_audiences_to_research_findings(
    meta_client: MetaClient, request_model: BidAdviceRequest, spark_bid_content: str
) -> None:
    evidence = Evidence(
        source_url="https://example-prints.com/products/sunset-pier",
        detail="Cheapest framed print",
        product_name="Sunset Pier Framed Print",
        price="$120.00",
    )
    request_model.competitor_brief.research_brief = [
        ResearchFinding(
            id="F1",
            finding="No unframed prints under $50",
            evidence=[evidence],
            confidence="low",
            recommendation="Launch an under-$50 print collection.",
        )
    ]
    llm_output = json.loads(spark_bid_content)
    llm_output["audience_suggestions"][0]["finding_ids"] = ["F1", "F9"]
    route = respx.post(CHAT_URL).mock(
        return_value=httpx.Response(200, json=chat_completion(json.dumps(llm_output)))
    )

    result = await BidAdvisorService(meta_client=meta_client).advise(request_model)

    user = json.loads(route.calls[0].request.content)["messages"][1]["content"]
    untrusted = user.split("<untrusted_competitor_data>")[1]
    assert '"id": "F1"' in untrusted
    assert "https://example-prints.com/products/sunset-pier" in untrusted
    assert result.audience_suggestions[0].finding_ids == ["F1"]
    assert result.research_brief[0].evidence[0].price == "$120.00"
