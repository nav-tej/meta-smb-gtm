"""Track I: Typed Research Directives and Injection-Safe Directive Parser.

Converts seller natural language steering inputs (<= 300 chars) into typed,
validated ResearchDirective objects. Never passes raw instructions to research models.
"""

from __future__ import annotations

import re
from typing import Literal
from urllib.parse import urlparse

from pydantic import BaseModel, Field

INJECTION_PATTERNS = [
    re.compile(r"ignore\s+(?:all\s+)?previous\s+instructions", re.IGNORECASE),
    re.compile(r"system\s*:", re.IGNORECASE),
    re.compile(r"you\s+are\s+now", re.IGNORECASE),
    re.compile(r"forget\s+everything", re.IGNORECASE),
    re.compile(r"<script[\s>]", re.IGNORECASE),
    re.compile(r"sudo\b", re.IGNORECASE),
    re.compile(r"(?:api_key|password|credit_card|secret)", re.IGNORECASE),
    re.compile(r"(?:login|log\s+in|signin|sign\s+in)\s+to", re.IGNORECASE),
]

FORBIDDEN_TOPICS = [
    "personal data",
    "private information",
    "individual names",
    "scrape login",
    "bypass",
]


class PriceBand(BaseModel):
    min: float | None = None
    max: float | None = None


FocusArea = Literal["pricing", "products", "posting", "gifting", "seo", "ads", "audience", "leads"]


class ResearchDirective(BaseModel):
    focus: FocusArea = "pricing"
    competitors_add: list[str] = Field(default_factory=list, max_length=6)
    competitors_remove: list[str] = Field(default_factory=list, max_length=6)
    price_band: PriceBand | None = None
    channels: list[str] = Field(default_factory=list, max_length=5)
    timeframe_days: Literal[7, 30, 90] = 30
    tone_note: str | None = Field(default=None, max_length=80)
    exclude_topics: list[str] = Field(default_factory=list, max_length=5)


def parse_research_directive(text: str) -> tuple[ResearchDirective | None, str]:
    """Parse raw seller text into a safe, syntax-only ResearchDirective.

    NOTE (SYNTAX-ONLY): This parser performs text pattern extraction only and does NOT
    perform network calls, DNS resolution, or SSRF boundary validation. Any future crawler
    or model component fetching from `competitors_add` MUST validate candidate URLs
    through `src.utils.sitemap.validate_safe_url` at fetch time.

    Returns:
        (directive, explanation_message)
    """
    raw = (text or "").strip()
    if not raw:
        return None, "Please enter a question or change you want Muse to research."

    if len(raw) > 300:
        return None, "Research directives are limited to 300 characters. Please shorten."

    # Guardrail 1: Check for prompt injection attempts
    for pat in INJECTION_PATTERNS:
        if pat.search(raw):
            return (
                None,
                "Muse cannot execute instructions that alter system behavior or request private "
                "data. Try asking about competitor pricing, product catalogs, or posting ideas.",
            )

    # Guardrail 2: Reject scraping behind logins or personal data
    lower_raw = raw.lower()
    for forbidden in FORBIDDEN_TOPICS:
        if forbidden in lower_raw:
            return (
                None,
                f"Muse only researches public storefront pages and cannot search for {forbidden}.",
            )

    # Determine Focus
    focus: FocusArea = "pricing"
    tone_note: str | None = None
    price_pattern = r"\b(?:price|pricing|charge|cost|cheap|undercut|discount|drop|under\s+\$\d+)\b"
    gift_pattern = r"\b(?:gift|holiday|vaisakhi|diwali|christmas|mother'?s\s+day|father'?s\s+day)\b"
    # Service businesses ask about clients, not listings: leads, inquiries, bookings, proposals,
    # or the marketplaces where buyers hire them.
    leads_pattern = (
        r"\b(?:leads?|clients?|inquir(?:y|ies)|enquir(?:y|ies)|bookings?|book\s+a\s+call|"
        r"consultations?|prospects?|pipeline|referrals?|proposals?|rfps?|"
        r"clutch|upwork|toptal|fiverr|linkedin)\b"
    )
    if re.search(gift_pattern, lower_raw):
        focus = "gifting"
    elif re.search(r"\b(?:post|posting|story|reel|instagram|facebook|caption|feed)\b", lower_raw):
        focus = "posting"
    elif re.search(leads_pattern, lower_raw):
        focus = "leads"
    elif re.search(r"\b(?:product|catalog|listing|launch|collection|series|item)\b", lower_raw):
        focus = "products"
    elif re.search(r"\b(?:seo|title|tag|search|keyword|google|visibility)\b", lower_raw):
        focus = "seo"
    elif re.search(r"\b(?:ad|ads|budget|meta\s+ad|spend|campaign|roas)\b", lower_raw):
        focus = "ads"
    elif re.search(r"\b(?:audience|buyer|customer|demographic|target)\b", lower_raw):
        focus = "audience"
    elif re.search(price_pattern, lower_raw):
        focus = "pricing"
    elif re.search(r"\b(?:easier|simpler|solo|beginner|easy)\b", lower_raw):
        focus = "products"
        tone_note = "easier moves for solo makers"

    if not tone_note and re.search(r"\b(?:easier|simpler|solo|beginner)\b", lower_raw):
        tone_note = "easier moves for solo makers"

    # Channels
    channels: list[str] = []
    for ch in ("instagram", "facebook", "pixels", "etsy", "pinterest", "saatchi"):
        if ch in lower_raw:
            channels.append(ch)

    # Parse Price Band if mentioned (e.g., "under $50", "from $20 to $100", "$14 - $60")
    price_band: PriceBand | None = None
    under_m = re.search(r"under\s+\$?(\d+(?:\.\d{1,2})?)", lower_raw)
    range_m = re.search(r"\$?(\d+(?:\.\d{1,2})?)\s*(?:to|-)\s*\$?(\d+(?:\.\d{1,2})?)", lower_raw)
    to_at_m = re.search(
        r"(?:to|at|starts\s+at|dropped\s+prints\s+to)\s+\$?(\d+(?:\.\d{1,2})?)", lower_raw
    )
    lone_dollar = re.search(r"\$(\d+(?:\.\d{1,2})?)", lower_raw)

    if range_m:
        price_band = PriceBand(min=float(range_m.group(1)), max=float(range_m.group(2)))
    elif under_m:
        price_band = PriceBand(max=float(under_m.group(1)))
    elif to_at_m:
        price_band = PriceBand(max=float(to_at_m.group(1)))
    elif lone_dollar:
        price_band = PriceBand(max=float(lone_dollar.group(1)))

    # Parse Timeframe (default 30 days)
    timeframe: Literal[7, 30, 90] = 30
    if re.search(r"\b(?:7\s*days?|week|this\s+week)\b", lower_raw):
        timeframe = 7
    elif re.search(r"\b(?:90\s*days?|quarter|three\s+months?)\b", lower_raw):
        timeframe = 90

    # Extract candidate competitor URLs (syntax-only check; real fetch-time SSRF guard
    # is enforced downstream via src.utils.sitemap.validate_safe_url)
    competitors_add: list[str] = []
    url_matches = re.findall(r"https?://[^\s<>\"']+", raw)
    blocked_hosts = ("localhost", "127.0.0.1", "0.0.0.0", "internal")
    for u in url_matches:
        parsed = urlparse(u)
        if (
            parsed.netloc
            and parsed.scheme in ("http", "https")
            and not any(b in parsed.netloc for b in blocked_hosts)
        ):
            competitors_add.append(f"{parsed.scheme}://{parsed.netloc}{parsed.path}")

    directive = ResearchDirective(
        focus=focus,
        competitors_add=competitors_add[:6],
        price_band=price_band,
        channels=channels[:5],
        timeframe_days=timeframe,
        tone_note=tone_note,
    )

    summary_parts = [f"Focus: {focus.capitalize()}"]
    if price_band:
        if price_band.min is not None and price_band.max is not None:
            summary_parts.append(f"Price band: ${price_band.min:g}–${price_band.max:g}")
        elif price_band.max is not None:
            summary_parts.append(f"Price cap: under ${price_band.max:g}")
    summary_parts.append(f"Window: last {timeframe} days")
    if competitors_add:
        url_count = len(competitors_add)
        summary_parts.append(f"Add: {url_count} shop URL{'s' if url_count > 1 else ''}")

    explanation = "Directive parsed: " + " · ".join(summary_parts)
    return directive, explanation
