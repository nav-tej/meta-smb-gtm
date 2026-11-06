from __future__ import annotations

import json
from collections.abc import Iterator
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import pytest

import src.clients.meta as meta_module
import src.config as config_module
from src.config import Settings, get_settings
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


@pytest.fixture(autouse=True)
def _never_use_real_meta_key(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[None]:
    """Tests must never spend Muse credits, even with a real key in .env.

    An empty env var wins over .env (python-dotenv doesn't override set variables).
    Tests that need a key set a fake one and mock the API with respx.
    """
    monkeypatch.setenv("META_MODEL_API_KEY", "")
    # Never read .env/.env.local in tests: .env.local is loaded with override=True and could
    # restore a real key over the blank one above.
    monkeypatch.setattr(config_module, "load_dotenv", lambda *args, **kwargs: False)
    # Mocked live results must not leak between tests through the on-disk result cache.
    monkeypatch.setenv("RESULT_CACHE_ENABLED", "false")
    # Server credit ledger and monitor log go to a per-test temp dir, never the repo.
    monkeypatch.setenv("CREDITS_DIR", str(tmp_path / "credits"))
    monkeypatch.setenv("MONITOR_DIR", str(tmp_path / "monitor"))
    # Route tests exercise the full app; demo-mode tests turn this back on explicitly
    monkeypatch.setenv("DEMO_MODE", "false")
    monkeypatch.setattr(meta_module, "_shared_client", None)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


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
