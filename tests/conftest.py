from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import pytest

from src.config import Settings
from src.models.bids import AdSetDailyPerformance, CampaignPerformance
from src.models.intel import CompetitorBrief

FIXTURES = Path(__file__).parent / "fixtures"
META_BASE_URL = "https://api.meta.ai/v1"
START = date(2026, 10, 1)

RETARGETING = "Retargeting - Site Visitors"
PROSPECTING = "Prospecting - Broad"
INTEREST = "Interest - Wall Art Lovers"


def _row(day: int, ad_set: str, **values: Any) -> AdSetDailyPerformance:
    return AdSetDailyPerformance(
        day=START + timedelta(days=day),
        campaign_name="Holiday Prints",
        ad_set_name=ad_set,
        **values,
    )


def build_campaign() -> CampaignPerformance:
    """8 days, 3 ad sets: a budget-limited winner, a steady middle, and a fatiguing loser."""
    interest_clicks = [100, 95, 90, 80, 60, 50, 45, 40]
    interest_conversions = [1, 1, 1, 1, 0, 1, 0, 0]
    rows: list[AdSetDailyPerformance] = []
    for d in range(8):
        rows.append(
            _row(d, RETARGETING, impressions=2000, clicks=60, conversions=3, spend=20.0,
                 conversion_value=135.0, frequency=2.0, daily_budget=20.0)
        )  # fmt: skip
        rows.append(
            _row(d, PROSPECTING, impressions=8000, clicks=120, conversions=2, spend=38.0,
                 conversion_value=90.0, frequency=1.3, daily_budget=40.0)
        )  # fmt: skip
        rows.append(
            _row(d, INTEREST, impressions=5000, clicks=interest_clicks[d],
                 conversions=interest_conversions[d], spend=29.0,
                 conversion_value=45.0 * interest_conversions[d],
                 frequency=1.5 + 0.25 * d, daily_budget=30.0)
        )  # fmt: skip
    return CampaignPerformance(account_name="Coastal Prints Co", currency="usd", rows=rows)


def chat_completion(content: str) -> dict[str, Any]:
    return {
        "id": "chatcmpl-test",
        "object": "chat.completion",
        "created": 0,
        "model": "muse-spark-1.3",
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": content},
                "finish_reason": "stop",
            }
        ],
    }


@pytest.fixture
def campaign() -> CampaignPerformance:
    return build_campaign()


@pytest.fixture
def competitor_brief() -> CompetitorBrief:
    return CompetitorBrief.model_validate_json((FIXTURES / "competitor_brief.json").read_text())


@pytest.fixture
def spark_bid_content() -> str:
    return (FIXTURES / "muse_spark_bid_response.json").read_text()


@pytest.fixture
def test_settings() -> Settings:
    return Settings(meta_model_api_key="test-key", meta_model_api_base_url=META_BASE_URL)


@pytest.fixture
def brief_json() -> dict[str, Any]:
    return json.loads((FIXTURES / "competitor_brief.json").read_text())
