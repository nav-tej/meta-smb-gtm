"""Offline regressions for owner-isolated editor persistence."""

import shutil
import subprocess
from pathlib import Path

import pytest


def test_editor_draft_recovery_and_account_boundaries() -> None:
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is needed for the editor draft contract")
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        [node, str(root / "tests/editor_drafts_contract.cjs")],
        cwd=root,
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
