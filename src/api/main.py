"""FastAPI app entry point. All feature routers are mounted under /api/v1."""

import logging
import mimetypes
from pathlib import Path

from fastapi import APIRouter, FastAPI, Request, status
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from src.api import bids, creative, intel
from src.clients.comfyui import ComfyUIError
from src.clients.meta import MetaAPIError
from src.config import get_settings
from src.utils.sitemap import SitemapError

# Ensure .webp files are served with image/webp Content-Type on serverless environments
mimetypes.add_type("image/webp", ".webp")

logging.basicConfig(
    level=get_settings().log_level.upper(),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

API_PREFIX = "/api/v1"
REPO_ROOT = Path(__file__).resolve().parents[2]
STATIC_DIR = Path(__file__).resolve().parent / "static"
SAMPLES_DIR = REPO_ROOT / "data" / "samples"
OUTPUTS_DIR = Path(get_settings().output_dir)
if not OUTPUTS_DIR.is_absolute():
    OUTPUTS_DIR = REPO_ROOT / OUTPUTS_DIR
try:
    OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
except OSError as err:  # read-only filesystems (serverless) without OUTPUT_DIR=/tmp/...
    logging.getLogger(__name__).warning("Generated outputs disabled: %s", err)

app = FastAPI(
    title="Meta SMB GTM",
    description="AI growth-ops copilot for SMB sellers, built on Meta's Muse models.",
    version="0.1.0",
)

health_router = APIRouter(tags=["health"])


@health_router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@health_router.get("/readiness")
async def readiness() -> dict[str, str | bool]:
    """Report configuration only; this check never calls a billed provider."""
    settings = get_settings()
    guarded = settings.demo_mode or settings.hosted_environment
    return {
        "default_mode": "saved" if guarded else "live",
        "live_unlock_configured": bool(settings.demo_key.strip()),
        "provider_key_configured": bool(settings.meta_model_api_key.strip()),
        "provider_verified": False,
    }


@app.get("/create", include_in_schema=False)
async def creator_studio() -> FileResponse:
    """Serve the guided product-to-post creator journey."""
    return FileResponse(STATIC_DIR / "creator.html")


@app.get("/", include_in_schema=False)
@app.get("/portal", include_in_schema=False)
async def customer_portal() -> FileResponse:
    """Serve the Lovable-style SMB Customer Growth Portal."""
    return FileResponse(STATIC_DIR / "index.html")


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

if SAMPLES_DIR.is_dir():
    app.mount("/samples", StaticFiles(directory=str(SAMPLES_DIR)), name="samples")
if OUTPUTS_DIR.is_dir():
    app.mount("/outputs", StaticFiles(directory=str(OUTPUTS_DIR)), name="outputs")
if STATIC_DIR.is_dir():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
