"""Deterministic idea ranking engine incorporating seller preferences and dismiss signals (Track D).

Enforces:
1. Access constraints: sellers without price control never see pricing moves as do-it-now.
2. Experience constraints: new sellers never see complex ad reallocation first.
3. Dismiss signals:
   - "no_access" on a channel hides that channel's recommendations.
   - 2+ "too_advanced" dismissals lowers difficulty and deprioritizes advanced moves.
   - "already_tried" filters or strongly demotes that specific idea.
"""

from __future__ import annotations

import re
from typing import Any

from src.models.intel import ActionableInsight
from src.models.seller import DismissSignal, SellerPreferences

ADVANCED_KEYWORDS = (
    "reallocate",
    "ad budget",
    "budget reallocation",
    "meta ads",
    "roas",
    "cpa",
    "ad set",
    "retargeting",
    "pixel event",
    "campaign structure",
)

PRICING_KEYWORDS = (
    "price",
    "pricing",
    "starter print",
    "entry price",
    "$",
    "discount",
    "price band",
    "tier",
)

CHANNEL_KEYWORDS = {
    "etsy": ("etsy",),
    "instagram": ("instagram", "ig", "reels", "feed", "stories"),
    "facebook": ("facebook", "fb"),
    "pixels": ("pixels", "fine art america", "faa"),
    "shopify": ("shopify", "own site", "storefront", "website"),
    "saatchi": ("saatchi",),
    "meta_ads": ("meta ads", "ads manager", "ad budget"),
}


def _detect_channel(text: str) -> str | None:
    lower = text.lower()
    for ch, patterns in CHANNEL_KEYWORDS.items():
        if any(re.search(rf"\b{re.escape(p)}\b", lower) for p in patterns):
            return ch
    return None


def _is_pricing_move(idea: ActionableInsight) -> bool:
    combined = f"{idea.title} {idea.action} {idea.why}".lower()
    return any(k in combined for k in PRICING_KEYWORDS)


def _is_advanced_move(idea: ActionableInsight) -> bool:
    combined = f"{idea.title} {idea.action} {idea.why}".lower()
    return any(k in combined for k in ADVANCED_KEYWORDS)


def rank_ideas_deterministically(
    ideas: list[ActionableInsight],
    preferences: SellerPreferences | None = None,
    dismiss_signals: list[DismissSignal] | list[dict[str, Any]] | None = None,
    *,
    filter_hidden: bool = True,
) -> list[ActionableInsight]:
    """Deterministically filter and rank ActionableInsight ideas.

    Returns ideas sorted from best fit to lowest fit according to seller profile.
    """
    if not ideas:
        return []

    pref = preferences or SellerPreferences()
    signals: list[DismissSignal] = []
    if dismiss_signals:
        for s in dismiss_signals:
            if isinstance(s, DismissSignal):
                signals.append(s)
            elif isinstance(s, dict):
                signals.append(DismissSignal.model_validate(s))

    # 1. Discover hidden channels from "no_access" / "wrong_channel" signals and access preferences
    hidden_channels: set[str] = set()
    for sig in signals:
        if sig.reason in {"no_access", "wrong_channel"}:
            detected = sig.channel or _detect_channel(f"{sig.title} {sig.id}")
            if detected:
                hidden_channels.add(detected)

    # Also honor explicit channel exclusions saved in seller memory
    for entry in pref.memory_entries:
        if entry.status == "accepted" and entry.key == "excluded_channels":
            for ch in CHANNEL_KEYWORDS:
                if ch in entry.value.lower():
                    hidden_channels.add(ch)

    # If seller specified explicit accessible channels, any other channel is hidden
    if pref.access.channels:
        allowed = {c.lower() for c in pref.access.channels}
        # If user explicitly has channels, channels outside allowed are treated as no-access
        for ch in CHANNEL_KEYWORDS:
            if ch not in allowed and not any(a in ch for a in allowed):
                hidden_channels.add(ch)

    # 2. Count "too_advanced" and "too_much_time" signals
    too_advanced_count = sum(1 for s in signals if s.reason == "too_advanced")
    too_much_time_count = sum(1 for s in signals if s.reason == "too_much_time")
    is_low_experience = pref.experience == "new" or too_advanced_count >= 2
    prefers_quick_moves = (
        pref.access.minutes_per_week is not None and pref.access.minutes_per_week <= 15
    ) or too_much_time_count >= 2

    # 3. Collect already_tried idea identifiers or titles
    already_tried_titles = {
        s.title.lower().strip() for s in signals if s.reason == "already_tried" and s.title
    }
    already_tried_ids = {
        s.id.lower().strip() for s in signals if s.reason == "already_tried" and s.id
    }

    # 4. Score each idea
    scored: list[tuple[float, int, ActionableInsight]] = []

    priority_base = {"high": 100.0, "medium": 50.0, "low": 20.0}

    for idx, idea in enumerate(ideas):
        score = priority_base.get(idea.priority, 50.0)
        idea_channel = _detect_channel(f"{idea.title} {idea.action}")
        is_pricing = _is_pricing_move(idea)
        is_advanced = _is_advanced_move(idea)

        # Check hidden channels
        if idea_channel and idea_channel in hidden_channels:
            if filter_hidden:
                continue
            score -= 200.0

        # Check price control
        if is_pricing and not pref.access.can_change_prices:
            # A seller with no price control never sees pricing moves as do-it-now
            score -= 70.0

        # Check experience & too_advanced
        if is_advanced:
            if is_low_experience:
                score -= 60.0
            elif pref.experience == "runs_ads":
                score += 25.0

        # Check already tried
        idea_title_lower = idea.title.lower().strip()
        if (
            idea_title_lower in already_tried_titles
            or any(t in idea_title_lower for t in already_tried_titles if t)
            or any(i in idea_title_lower for i in already_tried_ids if i)
        ):
            if filter_hidden:
                continue
            score -= 150.0

        # Check taste: subjects to avoid
        if pref.taste.subjects_to_avoid:
            combined = f"{idea.title} {idea.action}".lower()
            if any(bad.lower() in combined for bad in pref.taste.subjects_to_avoid):
                score -= 100.0

        # Check research focus and goal keyword match
        focus_parts = [p for p in (pref.research_focus, pref.goal) if p]
        if focus_parts:
            focus_words = [
                w.lower() for w in re.findall(r"\w+", " ".join(focus_parts)) if len(w) > 3
            ]
            combined = f"{idea.title} {idea.action} {idea.why}".lower()
            if any(w in combined for w in focus_words):
                score += 30.0

        # Prefer quick wins if weekly time limit is tight
        if prefers_quick_moves:
            combined = f"{idea.title} {idea.action}".lower()
            if any(k in combined for k in ("series", "holiday gift sets", "audit", "campaign")):
                score -= 35.0
            elif any(k in combined for k in ("quick", "short", "story", "15", "one")):
                score += 25.0

        scored.append((score, idx, idea))

    # Sort descending by score; break ties with original index ascending (stable)
    scored.sort(key=lambda item: (-item[0], item[1]))
    return [item[2] for item in scored]
