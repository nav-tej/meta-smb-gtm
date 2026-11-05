"""Personalized discovery is guarded and never fabricates crawl evidence."""

from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from src.api.main import app
from src.models.intel import SitemapEntry
from src.services.research_targets import ResearchTargets, ResearchTargetsRequest, discover_targets
from src.utils.sitemap import SitemapError


def test_discovery_requires_explicit_live_authorization(monkeypatch: pytest.MonkeyPatch) -> None:
    service = AsyncMock(side_effect=AssertionError("Must not crawl or call Muse"))
    monkeypatch.setattr("src.api.research_targets.discover_targets", service)
    response = TestClient(app).post("/api/v1/research-targets", json={"website": "nplusalpha.com"})
    assert response.status_code == 403
    service.assert_not_awaited()


async def test_discovery_uses_current_business_and_server_evidence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    crawl = AsyncMock(
        return_value=([SitemapEntry(loc="https://nplusalpha.com/work", title="Design")], [])
    )
    monkeypatch.setattr("src.services.research_targets.collect_entries", crawl)
    client = AsyncMock()
    client.chat_structured.return_value = ResearchTargets(
        business_summary="A design studio",
        targets=[{"name": "Candidate", "url": "https://example.com", "reason": "Similar buyers"}],
        next_move="Review the candidate",
        evidence_urls=["https://invented.example"],
    )
    monkeypatch.setattr("src.services.research_targets.get_meta_client", lambda: client)
    result = await discover_targets(
        ResearchTargetsRequest(website="nplusalpha.com", direction="Smaller studios")
    )
    assert result.evidence_urls == ["https://nplusalpha.com/work"]
    assert "unverified" in result.provenance
    prompt = client.chat_structured.call_args.kwargs["messages"][1]["content"]
    assert "Smaller studios" in prompt and "nplusalpha.com" in prompt
    assert "Sarabjit" not in prompt


async def test_failed_crawl_makes_no_model_call(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "src.services.research_targets.collect_entries",
        AsyncMock(side_effect=SitemapError("Blocked")),
    )
    client = AsyncMock()
    monkeypatch.setattr("src.services.research_targets.get_meta_client", lambda: client)
    with pytest.raises(SitemapError):
        await discover_targets(ResearchTargetsRequest(website="example.com"))
    client.chat_structured.assert_not_awaited()
