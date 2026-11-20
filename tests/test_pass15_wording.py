"""Pass 15: suggested moves and the digest say plainly whether a move fits the seller's week.

- `rank_seller_recommendations()` marks `over_budget`, so the page can say "Heads up" instead of
  "Why this fits" over "Takes about 40 minutes, more than your 30 minutes this week".
- Seller-facing strings from the ranker carry no em-dashes and no "(no fresh research ran)".
- The digest's fit note checks the move ("Fits your 15 minutes a week" or "Takes about N minutes,
  more than your M minutes a week") instead of always "Sized for ~M min/week", and its reason is
  the ranker's `why_this_fits` (it read a `reason` key the ranker never sets, so it was empty).
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest

from src.models.seller import AccessPreferences, SellerPreferences
from src.services.seller_memory import rank_seller_recommendations

SELLER_MEMORY_JS = Path(__file__).resolve().parents[1] / "src/api/static/seller-memory.js"


def _ranked(minutes: int, business_type: str | None = "services") -> list[dict[str, Any]]:
    prefs = SellerPreferences(
        goal="Grow visits",
        access=AccessPreferences(minutes_per_week=minutes, channels=["instagram", "website"]),
    )
    return rank_seller_recommendations(
        business_name="North Star Advisory", business_type=business_type, preferences=prefs
    )["recommendations"]


def _strings(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [s for v in value.values() for s in _strings(v)]
    if isinstance(value, list):
        return [s for v in value for s in _strings(v)]
    return []


@pytest.mark.parametrize("business_type", ["products", "services", "both", None])
def test_over_budget_flag_matches_minutes(business_type: str | None) -> None:
    for minutes in (5, 15, 30, 60):
        for move in _ranked(minutes, business_type):
            assert move["over_budget"] is (move["estimated_minutes"] > minutes), (minutes, move)
    # When nothing fits (5 minutes), the top move is flagged; with an hour it is not.
    assert _ranked(5, business_type)[0]["over_budget"] is True
    assert _ranked(60, business_type)[0]["over_budget"] is False


@pytest.mark.parametrize("business_type", ["products", "services", "both", None])
def test_ranker_strings_are_plain(business_type: str | None) -> None:
    for minutes in (5, 30):
        for text in _strings(_ranked(minutes, business_type)):
            assert "—" not in text, text
            assert "no fresh research ran" not in text, text


def test_page_labels_over_budget_moves_as_a_heads_up() -> None:
    node = shutil.which("node")
    if not node:
        pytest.skip("node not installed")
    source = SELLER_MEMORY_JS.read_text(encoding="utf-8")
    start = source.index("  function whyLabel(rec)")
    helper = source[start : source.index("\n", start)]
    script = (
        helper
        + "\nprocess.stdout.write(JSON.stringify([whyLabel({over_budget: true}),"
        + " whyLabel({over_budget: false}), whyLabel({}), whyLabel(null)]));"
    )
    out = json.loads(
        subprocess.run([node, "-e", script], capture_output=True, text=True, check=True).stdout
    )
    assert out == ["Heads up", "Why this fits", "Why this fits", "Why this fits"]
    assert source.count("`Why this fits: ") == 0
    assert "min`" not in source.replace(" minutes`", "")
