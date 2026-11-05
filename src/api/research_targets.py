"""Explicit live, guarded competitor discovery and refinement."""

from pathlib import Path

from fastapi import APIRouter, HTTPException, Request, Response

from src.api.demo import LiveMode
from src.services import result_cache
from src.services.research_targets import ResearchTargets, ResearchTargetsRequest, discover_targets

router = APIRouter(tags=["research"])


@router.post("/research-targets", response_model=ResearchTargets)
async def research_targets(
    body: ResearchTargetsRequest, request: Request, live: LiveMode, response: Response
) -> ResearchTargets:
    if not live or request.query_params.get("live", "").lower() not in {"true", "1"}:
        raise HTTPException(
            403, "Personalized discovery needs a live session. Saved research remains available."
        )
    return await result_cache.cached(
        "research-targets", body, ResearchTargets, lambda: discover_targets(body), response
    )


@router.get("/research-example", response_model=ResearchTargets)
def research_example() -> ResearchTargets:
    """Return the saved nplusalpha.com rehearsal without crawling or spending credits."""
    path = Path(__file__).resolve().parents[2] / "data/samples/nplusalpha_research_live.json"
    result = ResearchTargets.model_validate_json(path.read_text())
    result.provenance = "Saved live Muse rehearsal for nplusalpha.com. No new research or API call."
    return result
