"""Tests for Track K: 14-day trial entitlement models, activity tracking, and truth rules."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from src.config import get_settings
from src.models.trial import (
    BaselineMetrics,
    TrialActivity,
    TrialEntitlement,
    TwoWeekSummary,
)


def test_trial_entitlement_lifecycle() -> None:
    """Trial calculates active status, days remaining, and runs remaining."""
    t0 = datetime(2026, 11, 10, 10, 0, 0, tzinfo=UTC)
    t_exp = t0 + timedelta(days=14)

    entitlement = TrialEntitlement(
        account_id="user_trial_1",
        started_at=t0.isoformat(),
        duration_days=14,
        expires_at=t_exp.isoformat(),
        run_allowance=3,
        runs_used=1,
    )

    assert entitlement.is_active(now=t0) is True
    assert entitlement.runs_remaining == 2
    assert entitlement.days_remaining(now=t0) == 14

    # Day 7: Active with 7 days remaining
    t7 = t0 + timedelta(days=7)
    assert entitlement.is_active(now=t7) is True
    assert entitlement.days_remaining(now=t7) == 7

    # Day 15: Expired
    t15 = t0 + timedelta(days=15)
    assert entitlement.is_active(now=t15) is False
    assert entitlement.days_remaining(now=t15) == 0


def test_trial_config_values_present() -> None:
    """Config has trial runs, duration days, and card requirement as config values."""
    settings = get_settings()
    assert hasattr(settings, "trial_runs")
    assert hasattr(settings, "trial_duration_days")
    assert hasattr(settings, "trial_requires_card")
    assert settings.trial_duration_days == 14
    assert isinstance(settings.trial_requires_card, bool)


def test_baseline_metrics_optional() -> None:
    """Baseline metrics model captures initial seller state."""
    baseline = BaselineMetrics(
        posts_last_month=4,
        orders_last_month=12,
        followers_count=350,
        monthly_revenue_usd=480.0,
    )
    assert baseline.posts_last_month == 4
    assert baseline.monthly_revenue_usd == 480.0


def test_weekly_active_seller_definition() -> None:
    """A seller is weekly active only with real actions (not just visits)."""
    idle_activity = TrialActivity()
    assert idle_activity.is_weekly_active is False

    post_activity = TrialActivity(posts_exported=1)
    assert post_activity.is_weekly_active is True

    reco_activity = TrialActivity(recommendations_acted=1)
    assert reco_activity.is_weekly_active is True

    result_activity = TrialActivity(results_logged=1)
    assert result_activity.is_weekly_active is True

    directive_activity = TrialActivity(directives_steered=1)
    assert directive_activity.is_weekly_active is True


def test_two_week_summary_truth_rule() -> None:
    """Day-12 summary carries strictly real counts, never projected lift."""
    summary = TwoWeekSummary(
        recommendations_done=3,
        posts_made=2,
        results_logged=1,
        competitor_changes_caught=4,
        has_logged_revenue=True,
        logged_revenue_usd=120.0,
        is_activation_achieved=True,
    )
    assert summary.truth_rule_verified is True
    assert summary.logged_revenue_usd == 120.0
    assert summary.posts_made == 2
