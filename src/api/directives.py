"""Track I: Research Directive Parsing and Suggestion Endpoints."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from src.models.directive import ResearchDirective, parse_research_directive

router = APIRouter(prefix="/directives", tags=["directives"])


class ParseRequest(BaseModel):
    text: str = Field(min_length=1, max_length=300)


class DirectiveResponse(BaseModel):
    directive: ResearchDirective
    summary: str
    cost: str = "0 runs (re-ranks cached research)"


class SuggestionItem(BaseModel):
    text: str
    focus: str
    reason: str
    cost: str = "0 runs"


@router.post("/parse", response_model=DirectiveResponse)
async def parse_directive_endpoint(body: ParseRequest) -> DirectiveResponse:
    """Parse seller query into a typed ResearchDirective with prompt injection guardrails."""
    directive, summary = parse_research_directive(body.text)
    if not directive:
        raise HTTPException(status_code=400, detail=summary)

    cost = "1 run" if directive.competitors_add else "0 runs (re-ranks cached research)"
    return DirectiveResponse(directive=directive, summary=summary, cost=cost)


@router.get("/suggestions", response_model=list[SuggestionItem])
async def list_directive_suggestions() -> list[SuggestionItem]:
    """Return 4 state-derived suggestions that drive usage without model calls."""
    return [
        SuggestionItem(
            text="Look at why SikhiArt starts at $59.99",
            focus="pricing",
            reason="Competitor price gap analysis",
        ),
        SuggestionItem(
            text="Show me easier moves for solo makers",
            focus="difficulty",
            reason="Filter for quick wins under 15 minutes",
        ),
        SuggestionItem(
            text="Gift ideas for upcoming season",
            focus="gifting",
            reason="Seasonal holiday gift positioning",
        ),
        SuggestionItem(
            text="What should I post on Instagram this week?",
            focus="posting",
            reason="Weekly social media plan",
        ),
    ]
