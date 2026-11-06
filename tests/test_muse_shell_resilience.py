"""Run the muse-shell resilience contract (retries, friendly errors, server credits) in Node."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest


def test_muse_shell_resilience_contract() -> None:
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is required to execute muse_shell_resilience.cjs")
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        [node, str(root / "tests/muse_shell_resilience.cjs")],
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )
    assert result.returncode == 0, f"STDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
    assert "MUSE SHELL RESILIENCE CONTRACT PASSED" in result.stdout
