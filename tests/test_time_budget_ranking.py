"""Unit tests for weekly time-budget ranking in rank_seller_recommendations."""

from __future__ import annotations

import re

import pytest

from src.models.seller import AccessPreferences, DismissSignal, SellerPreferences
from src.services.seller_memory import rank_seller_recommendations


def _prefs(minutes_per_week: int, goal: str = "Grow visits") -> SellerPreferences:
    return SellerPreferences(
        goal=goal,
        access=AccessPreferences(
            minutes_per_week=minutes_per_week,
            channels=["instagram", "facebook", "website"],
        ),
    )


@pytest.mark.parametrize("business_type", ["products", "services", "both"])
def test_budget_30_demotes_40_minute_moves_even_when_shorter_moves_tried(
    business_type: str,
) -> None:
    """At 30 minutes/week, no 40-minute move may rank first even if shorter moves were tried."""
    baseline = rank_seller_recommendations(
        business_name="Test Studio",
        business_type=business_type,
        preferences=_prefs(60),
    )["recommendations"]
    shorter_signals = [
        DismissSignal(title=item["title"], reason="already_tried")
        for item in baseline
        if item["estimated_minutes"] <= 30
    ]

    ranked = rank_seller_recommendations(
        business_name="Test Studio",
        business_type=business_type,
        preferences=_prefs(30),
        dismiss_signals=shorter_signals,
    )["recommendations"]

    assert ranked
    assert ranked[0]["estimated_minutes"] <= 30

    over_budget = [item for item in ranked if item["estimated_minutes"] > 30]
    fitting = [item for item in ranked if item["estimated_minutes"] <= 30]
    assert over_budget
    assert fitting
    # Every fitting move ranks strictly above every over-budget move.
    assert max(ranked.index(item) for item in fitting) < min(
        ranked.index(item) for item in over_budget
    )
    for item in over_budget:
        why = item["why_this_fits"]
        expected = (
            f"Takes about {item['estimated_minutes']} minutes, more than your 30 minutes this week"
        )
        assert expected in why, why
        assert "—" not in why
        assert re.search(r"\bmin\b", why, re.IGNORECASE) is None


@pytest.mark.parametrize("business_type", ["products", "services", "both"])
def test_budget_60_allows_40_minute_move_to_rank_first(business_type: str) -> None:
    """At 60 minutes/week, a 40-minute move can rank first when it otherwise scores best."""
    baseline = rank_seller_recommendations(
        business_name="Test Studio",
        business_type=business_type,
        preferences=_prefs(60),
    )["recommendations"]
    shorter_signals = [
        DismissSignal(title=item["title"], reason="already_tried")
        for item in baseline
        if item["estimated_minutes"] < 40
    ]

    ranked = rank_seller_recommendations(
        business_name="Test Studio",
        business_type=business_type,
        preferences=_prefs(60),
        dismiss_signals=shorter_signals,
    )["recommendations"]

    assert ranked
    assert ranked[0]["estimated_minutes"] == 40
    assert "more than your" not in ranked[0]["why_this_fits"]


@pytest.mark.parametrize(
    ("business_type", "expected"),
    [
        (
            None,
            [
                ("move-price-positioning", 98.0, 12),
                ("move-commission-invite", 72.0, 10),
                ("move-similar-audience", 70.0, 15),
                ("move-inspiration-story", 69.0, 10),
                ("move-catalog-refresh", -23.0, 40),
            ],
        ),
        (
            "products",
            [
                ("move-price-positioning", 98.0, 12),
                ("move-commission-invite", 72.0, 10),
                ("move-similar-audience", 70.0, 15),
                ("move-inspiration-story", 69.0, 10),
                ("move-catalog-refresh", -23.0, 40),
            ],
        ),
        (
            "services",
            [
                ("move-services-offer", 98.0, 12),
                ("move-services-invite", 72.0, 10),
                ("move-services-result", 70.0, 15),
                ("move-services-process", 69.0, 10),
                ("move-services-page", -23.0, 40),
            ],
        ),
        (
            "both",
            [
                ("move-price-positioning", 98.0, 12),
                ("move-commission-invite", 72.0, 10),
                ("move-similar-audience", 70.0, 15),
                ("move-inspiration-story", 69.0, 10),
                ("move-catalog-refresh", -23.0, 40),
            ],
        ),
    ],
)
def test_budget_15_preserves_exact_order_and_scores_regression_guard(
    business_type: str | None,
    expected: list[tuple[str, float, int]],
) -> None:
    """Budget 15 keeps the exact pre-change ranked order and scores."""
    ranked = rank_seller_recommendations(
        business_name="Test Studio",
        business_type=business_type,
        preferences=_prefs(15),
    )["recommendations"]

    actual = [(item["id"], item["score"], item["estimated_minutes"]) for item in ranked]
    assert actual == expected

    for item in ranked:
        why = item["why_this_fits"]
        assert "—" not in why
        assert "-min" not in why
        if item["estimated_minutes"] <= 15:
            assert "Fits your 15 minutes this week" in why
        else:
            expected_over = (
                f"Takes about {item['estimated_minutes']} minutes, "
                "more than your 15 minutes this week"
            )
            assert expected_over in why


@pytest.mark.parametrize("business_type", ["products", "services", "both"])
def test_budget_smaller_than_every_move_returns_shortest_first(business_type: str) -> None:
    """When every move exceeds the weekly budget, return all moves shortest-first with reasons."""
    ranked = rank_seller_recommendations(
        business_name="Test Studio",
        business_type=business_type,
        preferences=_prefs(5),
    )["recommendations"]

    assert len(ranked) == 5
    minutes_order = [item["estimated_minutes"] for item in ranked]
    assert minutes_order == sorted(minutes_order)
    assert minutes_order[0] == 10

    for item in ranked:
        expected = (
            f"Takes about {item['estimated_minutes']} minutes, more than your 5 minutes this week"
        )
        assert expected in item["why_this_fits"]
        assert "—" not in item["why_this_fits"]
