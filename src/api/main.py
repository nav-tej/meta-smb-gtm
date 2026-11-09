"""FastAPI app entry point. All feature routers are mounted under /api/v1."""

import logging
import mimetypes
from pathlib import Path

from fastapi import APIRouter, FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from src.api import (
    accounts,
    analytics,
    bids,
    billing,
    content_plan,
    creative,
    credits,
    daily_brief,
    digest_email,
    intel,
    media,
    monitor,
    product_reference,
    research_targets,
)
from src.clients.comfyui import ComfyUIError
from src.clients.meta import MetaAPIError
from src.clients.supabase import SupabaseError
from src.config import get_settings
from src.services.credits import CreditsExhaustedError, CreditsUnavailableError
from src.services.usage_meter import UsageLimitError
from src.utils.sitemap import SitemapError

# Ensure .webp files are served with image/webp Content-Type on serverless environments
mimetypes.add_type("image/webp", ".webp")

logging.basicConfig(
    level=get_settings().log_level.upper(),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

API_PREFIX = "/api/v1"
# Pages must revalidate on every visit; otherwise browsers can keep old HTML that points at
# old script versions after a deploy. Static assets are versioned with ?v= instead.
PAGE_HEADERS = {"Cache-Control": "no-cache"}
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
async def readiness() -> dict[str, str | bool | int]:
    """Report configuration only; this check never calls a billed provider."""
    settings = get_settings()
    guarded = settings.demo_mode or settings.hosted_environment
    from src.clients.supabase import configured as accounts_configured

    return {
        "default_mode": "saved" if guarded else "live",
        "live_unlock_configured": bool(settings.demo_key.strip()),
        "provider_key_configured": bool(settings.meta_model_api_key.strip()),
        "provider_verified": False,
        "accounts_required": settings.accounts_required,
        "accounts_configured": accounts_configured(),
        "trial_runs": settings.trial_runs,
    }


@app.get("/create", include_in_schema=False)
async def creator_studio() -> FileResponse:
    """Serve the guided product-to-post creator journey."""
    return FileResponse(STATIC_DIR / "creator.html", headers=PAGE_HEADERS)


@app.get("/today", include_in_schema=False)
async def daily_studio() -> FileResponse:
    """Serve the compact item-to-post daily workspace."""
    return FileResponse(STATIC_DIR / "today.html", headers=PAGE_HEADERS)


@app.get("/digest", include_in_schema=False)
async def weekly_digest_page() -> FileResponse:
    """Serve the weekly market digest; it reads /api/v1/weekly-digest in the browser."""
    return FileResponse(STATIC_DIR / "digest.html", headers=PAGE_HEADERS)


@app.get("/", include_in_schema=False)
@app.get("/portal", include_in_schema=False)
async def customer_portal() -> FileResponse:
    """Serve the Lovable-style SMB Customer Growth Portal."""
    return FileResponse(STATIC_DIR / "index.html", headers=PAGE_HEADERS)


@app.get("/account", include_in_schema=False)
async def account_landing() -> FileResponse:
    """Land email-confirmation links; the account dialog completes sign-in."""
    return FileResponse(STATIC_DIR / "index.html", headers=PAGE_HEADERS)


MUSE_UNAVAILABLE = (
    "Muse couldn't finish this request right now. Your inputs are safe and saved demo results "
    "still work. Please try again in a minute."
)
# MetaAPIError messages that are written for the seller (input limits), safe to show as-is.
_USER_FACING_PREFIXES = (
    "Use ",
    "Choose ",
    "Upload ",
    "This request has too much text",
    "This image request exceeds",
    "This trial supports",
    "Uploaded image exceeds",
    "Image exceeds",
    "Unsupported image format",
    "At least one image",
    "Muse returned a channel",
)


def public_meta_error(exc: MetaAPIError) -> tuple[int, str]:
    """(status, message) for a Muse failure, never exposing upstream or validation details."""
    message = str(exc)
    if message.startswith(_USER_FACING_PREFIXES) and len(message) <= 240:
        return status.HTTP_422_UNPROCESSABLE_CONTENT, message
    if "META_MODEL_API_KEY" in message:
        return status.HTTP_503_SERVICE_UNAVAILABLE, (
            "Live Muse is not configured on this server. Saved demo results still work."
        )
    return status.HTTP_502_BAD_GATEWAY, MUSE_UNAVAILABLE


@app.exception_handler(MetaAPIError)
async def meta_api_error_handler(request: Request, exc: MetaAPIError) -> JSONResponse:
    logger.error("Meta Model API failure on %s: %s", request.url.path, exc)
    code, message = public_meta_error(exc)
    return JSONResponse(status_code=code, content={"detail": message, "code": "muse_unavailable"})


@app.exception_handler(ComfyUIError)
async def comfyui_error_handler(request: Request, exc: ComfyUIError) -> JSONResponse:
    logger.error("ComfyUI failure on %s: %s", request.url.path, exc)
    return JSONResponse(
        status_code=status.HTTP_502_BAD_GATEWAY,
        content={
            "detail": "The image variant workflow is unavailable right now. Try again later.",
            "code": "workflow_unavailable",
        },
    )


@app.exception_handler(CreditsExhaustedError)
async def credits_exhausted_handler(request: Request, exc: CreditsExhaustedError) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_402_PAYMENT_REQUIRED,
        content={
            "detail": (
                "You're out of runs. Saved results are still free to view. "
                "Pick a plan to add more runs."
            ),
            "code": "credits_exhausted",
            "balance": exc.balance,
        },
    )


@app.exception_handler(CreditsUnavailableError)
async def credits_unavailable_handler(
    request: Request, exc: CreditsUnavailableError
) -> JSONResponse:
    logger.error("Credit ledger unavailable on %s: %s", request.url.path, exc)
    return JSONResponse(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        content={
            "detail": "Run credits can't be checked right now, so live runs are paused. "
            "Saved demo results still work.",
            "code": "credits_unavailable",
        },
    )


@app.exception_handler(RequestValidationError)
async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    fields = sorted(
        {".".join(str(p) for p in err.get("loc", ())[1:]) or "request" for err in exc.errors()}
    )
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        content={
            "detail": "Some details need fixing: " + ", ".join(fields[:5])[:200] + ".",
            "code": "invalid_request",
            "fields": fields[:20],
        },
    )


@app.exception_handler(Exception)
async def unexpected_error_handler(request: Request, exc: Exception) -> JSONResponse:
    if isinstance(exc, HTTPException):  # pragma: no cover - handled by FastAPI first
        raise exc
    logger.exception("Unhandled error on %s", request.url.path)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "detail": "Something went wrong on our side. Your work is safe; please try again.",
            "code": "server_error",
        },
    )


@app.exception_handler(SitemapError)
async def sitemap_error_handler(request: Request, exc: SitemapError) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        content={"detail": f"Could not read competitor site: {exc}"},
    )


@app.exception_handler(UsageLimitError)
async def usage_limit_handler(request: Request, exc: UsageLimitError) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})


@app.exception_handler(SupabaseError)
async def supabase_error_handler(request: Request, exc: SupabaseError) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})


app.include_router(health_router)
app.include_router(health_router, prefix=API_PREFIX)
app.include_router(accounts.router, prefix=API_PREFIX)
app.include_router(media.router, prefix=API_PREFIX)
app.include_router(analytics.router, prefix=API_PREFIX)
app.include_router(billing.router, prefix=API_PREFIX)
app.include_router(intel.router, prefix=API_PREFIX)
app.include_router(creative.router, prefix=API_PREFIX)
app.include_router(bids.router, prefix=API_PREFIX)
app.include_router(content_plan.router, prefix=API_PREFIX)
app.include_router(product_reference.router, prefix=API_PREFIX)
app.include_router(research_targets.router, prefix=API_PREFIX)
app.include_router(daily_brief.router, prefix=API_PREFIX)
app.include_router(credits.router, prefix=API_PREFIX)
app.include_router(monitor.router, prefix=API_PREFIX)
app.include_router(digest_email.router, prefix=API_PREFIX)
# Short aliases: /api/credits, /api/monitor, /api/weekly-digest
app.include_router(credits.router, prefix="/api", include_in_schema=False)
app.include_router(monitor.router, prefix="/api", include_in_schema=False)

if SAMPLES_DIR.is_dir():
    app.mount("/samples", StaticFiles(directory=str(SAMPLES_DIR)), name="samples")
if OUTPUTS_DIR.is_dir():
    app.mount("/outputs", StaticFiles(directory=str(OUTPUTS_DIR)), name="outputs")
if STATIC_DIR.is_dir():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
