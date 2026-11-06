"""Explicit-opt-in content plans; ordinary visits never make billed provider requests."""

from __future__ import annotations

import contextlib
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, Response

from src.api.demo import live_mode
from src.models.content_plan import ContentPlan, ContentPlanRequest
from src.services import result_cache
from src.services.content_plan import ContentPlanService, starter_plan

router = APIRouter(tags=["content"])


def get_content_plan_service() -> ContentPlanService:
    return ContentPlanService()


@router.post("/content-plan", response_model=ContentPlan)
async def content_plan(
    body: ContentPlanRequest,
    request: Request,
    response: Response,
    service: Annotated[ContentPlanService, Depends(get_content_plan_service)],
    live: Annotated[bool, Query()] = False,
    x_demo_key: Annotated[str | None, Header()] = None,
) -> ContentPlan:
    if body.use_muse != live:
        raise HTTPException(
            422,
            "A Muse plan needs both use_muse=true and ?live=true; use neither for a starter plan.",
        )
    if not body.use_muse:
        return starter_plan(body)
    live_request = live_mode(request, response, live=True, x_demo_key=x_demo_key)
    await live_request.__anext__()
    try:
        plan = await result_cache.cached(
            "content-plan",
            body,
            ContentPlan,
            lambda: service.generate(body),
            response,
            fallback=lambda: starter_plan(body),
        )
    except BaseException as err:
        with contextlib.suppress(StopAsyncIteration):
            await live_request.athrow(err)
        raise
    with contextlib.suppress(StopAsyncIteration):
        await live_request.__anext__()
    return plan
