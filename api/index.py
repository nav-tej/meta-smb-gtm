"""Vercel serverless entry point: exposes the FastAPI app as an ASGI `app`."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.api.main import app  # noqa: E402

__all__ = ["app"]
