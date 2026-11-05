"""Execute the account UI contract (signup/signin/quota/workspace) via Node.js."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path


def test_account_ui_contract_node_runner() -> None:
    """Execute tests/account_ui_contract.cjs via Node.js VM harness."""
    node = shutil.which("node")
    if node is None:
        import pytest

        pytest.skip("Node.js is required to execute account_ui_contract.cjs")

    root = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        [node, str(root / "tests/account_ui_contract.cjs")],
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )
    assert result.returncode == 0, f"STDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
    assert "ACCOUNT UI CONTRACT PASSED" in result.stdout
