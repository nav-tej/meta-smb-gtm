"""A saved competitor ad count says when it was checked; it never reads as today's.

`/api/v1/competitors/ads` serves Ad Library counts from the research cache, which keeps them with
no expiry, and marks those with `is_cached` and a `cache_label` ("Last checked Nov 10 · ...").
Codex found (CODEX_PREVIEW_E_REVIEW_NOV20.md) that the page ignored both, so a weeks-old count read
"3 active ads in the EU" exactly like a fresh one. This runs the page's own `formatAdStatusSummary`.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

INDEX = Path(__file__).resolve().parents[1] / "src" / "api" / "static" / "index.html"


def _function_source(name: str) -> str:
    html = INDEX.read_text(encoding="utf-8")
    start = html.index(f"function {name}(")
    depth, i = 0, html.index("{", start)
    while True:
        if html[i] == "{":
            depth += 1
        elif html[i] == "}":
            depth -= 1
            if depth == 0:
                return html[start : i + 1]
        i += 1


def _run(cases: dict[str, dict]) -> dict[str, dict]:
    node = shutil.which("node")
    if not node:
        pytest.skip("node not installed")
    script = (
        _function_source("formatAdStatusSummary")
        + f"\nconst cases = {json.dumps(cases)};\n"
        + "const out = {}; for (const [k, v] of Object.entries(cases)) out[k] = "
        + "formatAdStatusSummary(v);\nprocess.stdout.write(JSON.stringify(out));"
    )
    proc = subprocess.run([node, "-e", script], capture_output=True, text=True, check=True)
    return json.loads(proc.stdout)


def test_saved_ad_counts_show_their_date_and_fresh_counts_are_unchanged() -> None:
    label = "Last checked Nov 3 · Refresh (1 run)"
    ads = [{"days_running": 40, "headline": "Gift prints"}]
    out = _run(
        {
            "fresh_live": {"status": "live", "total_active_ads": 3, "ads": ads, "is_cached": False},
            "saved_live": {
                "status": "live",
                "total_active_ads": 3,
                "ads": ads,
                "is_cached": True,
                "cache_label": label,
            },
            "saved_zero": {"status": "zero", "is_cached": True, "cache_label": label},
            "saved_no_date": {"status": "zero", "is_cached": True, "cache_label": None},
            "fresh_zero": {"status": "zero", "is_cached": False},
        }
    )
    # Fresh counts read exactly as before.
    assert out["fresh_live"]["badge"] == "3 active ads in the EU"
    assert out["fresh_live"]["tone"] == "green"
    assert out["fresh_live"]["detail"].startswith("Counted from Meta's Ad Library.")
    assert out["fresh_zero"]["badge"] == "None in the EU"
    # Saved counts carry the day they were checked, in the badge and the detail.
    assert out["saved_live"]["badge"] == "3 active ads in the EU · Nov 3"
    assert out["saved_live"]["tone"] == "gold"
    assert out["saved_live"]["detail"].startswith(
        "Saved count from Nov 3; it may have changed since."
    )
    assert out["saved_zero"]["badge"] == "None in the EU · Nov 3"
    assert "Saved count from Nov 3" in out["saved_zero"]["detail"]
    assert out["saved_no_date"]["badge"] == "None in the EU · saved"
    for key, value in out.items():
        text = value["badge"] + " " + value["detail"]
        assert "run)" not in text and "Refresh" not in text, (key, text)
        assert "—" not in text, (key, text)
