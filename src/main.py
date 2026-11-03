"""Convenience entry point: `uvicorn src.main:app`. The app is defined in src/api/main.py."""

from src.api.main import app

__all__ = ["app"]
