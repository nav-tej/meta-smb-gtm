"""FastAPI app entry point. Routers for /intel, /creative, and /bids get registered here."""

from fastapi import FastAPI

app = FastAPI(
    title="Meta SMB GTM",
    description="AI growth-ops copilot for SMB sellers, built on Meta's Muse models.",
    version="0.1.0",
)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
