from __future__ import annotations

import json

import httpx
import pytest
import respx

import src.clients.meta as meta_module
from scripts.demo_flow import main
from src.config import get_settings
from tests.conftest import FIXTURES, META_BASE_URL, chat_completion

BRIEF_OUTPUT = {
    "summary": "She paints Sikh heroines and sells prints from about $18.",
    "new_product_frequency": "A batch of uploads in April; nothing since.",
    "doubling_down_on": ["Portraits of Sikh women"],
    "competitor_gaps": ["No Gurpurab gift collection"],
    "research_brief": [
        {
            "finding": "No Gurpurab gift collection",
            "evidence": [{"source_url": "computed_signals", "detail": "No seasonal themes"}],
            "recommendation": "Bundle 3 prints as a Gurpurab gift set.",
        }
    ],
    "actionable_insights": [
        {
            "title": "Gurpurab gift set",
            "action": "Bundle 3 prints.",
            "why": "No one offers it.",
            "evidence": [{"source_url": "computed_signals", "detail": "No seasonal themes"}],
        }
    ],
}


@pytest.fixture
def no_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("META_MODEL_API_KEY", "")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("META_MODEL_API_KEY", "test-key")
    monkeypatch.setenv("META_MODEL_API_BASE_URL", META_BASE_URL)
    monkeypatch.setattr(meta_module, "_shared_client", None)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.mark.usefixtures("no_api_key")
def test_demo_runs_offline_without_key(capsys: pytest.CaptureFixture[str]) -> None:
    assert main([]) == 0
    out = capsys.readouterr().out
    assert "SELLER: ART OF SARABJIT SINGH" in out
    assert "gurinderpreet-kaur" in out
    assert "Golden Temple - Gift Buyers" in out
    assert "creative_fatigue" in out
    assert out.count("[skipped]") == 2


@respx.mock
@pytest.mark.usefixtures("api_key")
def test_demo_full_flow_with_muse_spark(capsys: pytest.CaptureFixture[str]) -> None:
    bid_output = (FIXTURES / "muse_spark_bid_response.json").read_text()
    route = respx.post(f"{META_BASE_URL}/chat/completions").mock(
        side_effect=[
            httpx.Response(200, json=chat_completion(json.dumps(BRIEF_OUTPUT))),
            httpx.Response(200, json=chat_completion(bid_output)),
        ]
    )

    assert main([]) == 0

    out = capsys.readouterr().out
    assert route.call_count == 2
    assert "[skipped]" not in out
    assert "No Gurpurab gift collection" in out
    assert "F1 [low confidence] No Gurpurab gift collection" in out
    assert "Next steps" in out
