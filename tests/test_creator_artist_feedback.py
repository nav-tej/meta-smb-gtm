"""Offline behavioral regressions for the artist's marketplace feedback."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest


def test_artist_marketplace_state_and_posting_handoff() -> None:
    """Keep channel offers isolated through edits, switches, and imports."""
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is required for creator state regressions")
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        [node, str(root / "tests/creator_artist_feedback.cjs")],
        cwd=root,
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )
    assert result.returncode == 0, f"STDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
    assert "ARTIST FEEDBACK STATE REGRESSIONS PASSED" in result.stdout
