"""FastAPI app entry point. All feature routers are mounted under /api/v1."""

import logging

from fastapi import APIRouter, FastAPI, Request, status
from fastapi.responses import JSONResponse

from src.api import bids, creative, intel
from src.clients.comfyui import ComfyUIError
from src.clients.meta import MetaAPIError
from src.utils.sitemap import SitemapError

logger = logging.getLogger(__name__)

API_PREFIX = "/api/v1"

app = FastAPI(
    title="Meta SMB GTM",
    description="AI growth-ops copilot for SMB sellers, built on Meta's Muse models.",
    version="0.1.0",
)

health_router = APIRouter(tags=["health"])


@health_router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.exception_handler(MetaAPIError)
async def meta_api_error_handler(request: Request, exc: MetaAPIError) -> JSONResponse:
    logger.error("Meta Model API failure on %s: %s", request.url.path, exc)
    return JSONResponse(
        status_code=status.HTTP_502_BAD_GATEWAY,
        content={"detail": f"Muse model request failed: {exc}"},
    )


@app.exception_handler(ComfyUIError)
async def comfyui_error_handler(request: Request, exc: ComfyUIError) -> JSONResponse:
    logger.error("ComfyUI failure on %s: %s", request.url.path, exc)
    return JSONResponse(
        status_code=status.HTTP_502_BAD_GATEWAY,
        content={"detail": f"ComfyUI workflow failed: {exc}"},
    )


@app.exception_handler(SitemapError)
async def sitemap_error_handler(request: Request, exc: SitemapError) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        content={"detail": f"Could not read competitor site: {exc}"},
    )


app.include_router(health_router)
app.include_router(health_router, prefix=API_PREFIX)
app.include_router(intel.router, prefix=API_PREFIX)
app.include_router(creative.router, prefix=API_PREFIX)
app.include_router(bids.router, prefix=API_PREFIX)
