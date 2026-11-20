"""Seller Memory & Personalization services (PRD Section 12, Batch 1).

Handles:
1. Grounded shop-scan proposal extraction (observed facts vs interpretations, never invented).
2. Rescan diffs that preserve seller corrections until explicitly accepted.
3. Plain-language & fixture/approved voice transcript interpretation into reviewable entries.
4. Feedback/dismiss-driven update suggestions (explicit approval required).
5. Role-aware competitor & context recommendation ranking ("Why this fits" + editor defaults).
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any, Literal

from src.models.seller import (
    CompetitorEntry,
    CompetitorRole,
    DismissSignal,
    SellerMemoryDiffItem,
    SellerMemoryEntry,
    SellerPreferences,
    SuggestedMemoryUpdate,
)
from src.models.voice import VoiceProfile

DEMO_VOICE_FIXTURES: dict[str, dict[str, str]] = {
    "watercolor_studio": {
        "id": "watercolor_studio",
        "label": "Sample voice note · Watercolor landscape seller [demo · 0 runs]",
        "transcript": (
            "I run Wild Meadow Studio painting coastal and alpine watercolors. "
            "Archival prints start at $35 and framed originals are $280 on my site. "
            "I only have 15 minutes a week right now, post mostly on Instagram, want to invite "
            "more custom commissions without quoting a price up front, and keep captions short "
            "with zero discount codes."
        ),
    },
    "ceramics_studio": {
        "id": "ceramics_studio",
        "label": "Sample voice note · Handmade ceramics seller [demo · 0 runs]",
        "transcript": (
            "I make small-batch stoneware mugs starting at $42 in my own shop. "
            "I have about 30 minutes a week for Instagram and Facebook, want gift-ready "
            "bundling ideas for weekend markets, and prefer warm captions without hype words."
        ),
    },
}

_GIFT_KEYWORDS = ("gift", "print", "card", "mug", "mini", "watercolor", "landscape", "art", "set")
_COMMISSION_KEYWORDS = ("commission", "custom", "bespoke", "portrait", "made to order")
BusinessType = Literal["products", "services", "both"]
_KNOWN_CHANNELS = ("instagram", "facebook", "website", "marketplace", "etsy", "tiktok", "pinterest")

_ROLE_LABELS: dict[CompetitorRole, str] = {
    "similar_audience": "Similar audience",
    "price_reference": "Price reference",
    "inspiration": "Inspiration",
}


def _slugify(text: str, max_len: int = 40) -> str:
    cleaned = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return (cleaned[:max_len] or "entry").strip("-")


def _today_iso() -> str:
    return datetime.now(UTC).date().isoformat()


_PRICE_TOKEN_RE = re.compile(
    r"\b(EUR|GBP|USD|CAD|AUD|CHF|JPY|INR)\s*([0-9]{1,5}(?:,[0-9]{3})*(?:\.[0-9]{1,2})?)"
    r"|([$€£¥₹])\s*([0-9]{1,5}(?:,[0-9]{3})*(?:\.[0-9]{1,2})?)",
    re.IGNORECASE,
)


def _norm_scope_token(value: str | None) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip().lower())


def _format_currency_amount(prefix: str, amount: float, *, spaced: bool = False) -> str:
    num_str = f"{int(amount)}" if amount.is_integer() else f"{amount:,.2f}"
    return f"{prefix} {num_str}" if spaced else f"{prefix}{num_str}"


def _extract_price_tokens(price_hints: list[str]) -> list[tuple[str, float, str]]:
    """Extract (currency_key, numeric_value, display_str) preserving original currencies."""
    tokens: list[tuple[str, float, str]] = []
    seen_display: set[str] = set()
    for hint in price_hints:
        text = str(hint or "").strip()
        if not text:
            continue
        matched_any = False
        for m in _PRICE_TOKEN_RE.finditer(text):
            matched_any = True
            if m.group(1):
                code = m.group(1).upper()
                raw_num = m.group(2)
                spaced = True
                curr = code
            else:
                curr = m.group(3)
                raw_num = m.group(4)
                spaced = False
            try:
                num = float(raw_num.replace(",", ""))
            except ValueError:
                continue
            if num <= 0:
                continue
            display = _format_currency_amount(curr, num, spaced=spaced)
            if display not in seen_display:
                seen_display.add(display)
                tokens.append((curr, num, display))
        if not matched_any:
            # Bare numeric hints without currency must never be forced into USD "$".
            for m in re.finditer(r"(\d{1,5}(?:,\d{3})*(?:\.\d{1,2})?)", text):
                try:
                    num = float(m.group(1).replace(",", ""))
                except ValueError:
                    continue
                if num <= 0:
                    continue
                display = _format_currency_amount("", num, spaced=False)
                if display not in seen_display:
                    seen_display.add(display)
                    tokens.append(("", num, display))
    return sorted(tokens, key=lambda item: (item[0], item[1]))


def _extract_explicit_currency_prices(text: str) -> list[str]:
    found: list[str] = []
    seen: set[str] = set()
    for m in _PRICE_TOKEN_RE.finditer(str(text or "")):
        item = f"{m.group(1).upper()} {m.group(2)}" if m.group(1) else f"{m.group(3)}{m.group(4)}"
        if item not in seen:
            seen.add(item)
            found.append(item)
    return found


def _extract_short_price(price_claim: str) -> str:
    text = str(price_claim or "").strip()
    if not text:
        return ""
    explicit = _extract_explicit_currency_prices(text)
    if explicit:
        return explicit[0]
    return text[:40]


def extract_scan_proposals(
    *,
    business_name: str,
    primary_url: str,
    channel_results: list[dict[str, Any]],
    discovered_items: list[dict[str, Any]],
    detected_price_hints: list[str],
    suggested_socials: list[dict[str, Any]] | None = None,
    scan_date: str | None = None,
    product_key: str | None = None,
    destination: str | None = None,
) -> dict[str, Any]:
    """Turn a shop scan into separate observed facts, interpretations, and missing questions."""
    when = scan_date or _today_iso()
    proposals: list[SellerMemoryEntry] = []
    partial_warnings: list[str] = []

    fetched_channels = [c for c in channel_results if c.get("status") == "fetched"]
    blocked_channels = [c for c in channel_results if c.get("status") != "fetched"]
    for blocked in blocked_channels:
        partial_warnings.append(
            f"{blocked.get('host') or blocked.get('url')}: could not read automatically "
            f"({blocked.get('note') or 'partial access'}). Enter missing details manually."
        )

    source_url = primary_url.strip() or (
        fetched_channels[0].get("url") if fetched_channels else None
    )

    if business_name.strip():
        proposals.append(
            SellerMemoryEntry(
                id="obs-shop-name",
                key="business_name",
                label="Shop name",
                value=business_name.strip()[:140],
                kind="observation",
                scope="shop_default",
                source="shop_scan",
                source_url=source_url,
                scan_date=when,
                confidence="observed",
                status="proposed",
            )
        )

    titles = [
        str(item.get("title") or "").strip() for item in discovered_items if item.get("title")
    ]
    pages_found = sum(int(c.get("pages_found") or 0) for c in fetched_channels)
    if titles:
        first_item_url = str(discovered_items[0].get("url") or source_url or "") or None
        sample_summary = "; ".join(titles[:4])
        proposals.append(
            SellerMemoryEntry(
                id="obs-catalog-pages",
                key="catalog_summary",
                label="Scanned public pages",
                value=(
                    f"Read {max(pages_found, len(titles))} public page(s), "
                    f"including {sample_summary}."
                )[:320],
                kind="observation",
                scope="shop_default",
                source="shop_scan",
                source_url=first_item_url,
                scan_date=when,
                confidence="observed",
                status="proposed",
            )
        )
    elif primary_url:
        partial_warnings.append(
            "No product titles were extracted automatically. "
            "You can type a short description below."
        )

    price_tokens = _extract_price_tokens(detected_price_hints)
    lowest_price_display = ""
    price_source_url = source_url
    for item in discovered_items:
        if isinstance(item, dict) and item.get("price_hint") and item.get("url"):
            price_source_url = str(item.get("url"))
            break
    if price_tokens:
        currencies = list(dict.fromkeys(tok[0] for tok in price_tokens))
        if len(currencies) == 1:
            low = price_tokens[0][2]
            high = price_tokens[-1][2]
            lowest_price_display = low
            price_val = (
                f"Listed prices start at {low} (range {low}–{high})"
                if low != high
                else f"Listed item price: {low}"
            )
        else:
            lowest_price_display = price_tokens[0][2]
            price_val = f"Observed prices: {', '.join(tok[2] for tok in price_tokens[:4])}"
        proposals.append(
            SellerMemoryEntry(
                id="obs-price-range",
                key="price_range",
                label="Observed listing prices",
                value=price_val,
                kind="observation",
                scope="product",
                product_key=product_key,
                destination=destination,
                source="shop_scan",
                source_url=price_source_url,
                scan_date=when,
                confidence="observed",
                uncertainty=(
                    "Applies only to scanned pages; confirm destination pricing before posting."
                ),
                status="proposed",
            )
        )

    if suggested_socials:
        handles = ", ".join(
            f"{s.get('platform', 'social')}: {s.get('handle', '')}"
            for s in suggested_socials[:4]
            if s.get("handle")
        )
        if handles:
            proposals.append(
                SellerMemoryEntry(
                    id="obs-social-links",
                    key="linked_socials",
                    label="Social links found on shop",
                    value=handles[:300],
                    kind="observation",
                    scope="shop_default",
                    source="shop_scan",
                    source_url=source_url,
                    scan_date=when,
                    confidence="observed",
                    status="proposed",
                )
            )

    # Interpretations: grounded in scanned words, labeled as uncertain hypotheses.
    combined_titles = " ".join(titles).lower()
    if titles and any(k in combined_titles for k in _GIFT_KEYWORDS):
        proposals.append(
            SellerMemoryEntry(
                id="interp-gift-fit",
                key="audience_hypothesis",
                label="Possible audience angle (interpretation)",
                value=(
                    "Work on these pages may appeal to gift and home-decor buyers"
                    if not lowest_price_display
                    else (
                        f"Pieces starting around {lowest_price_display} may appeal to gift buyers"
                    )
                ),
                kind="interpretation",
                scope="shop_default",
                source="shop_scan",
                source_url=source_url,
                scan_date=when,
                confidence="inferred",
                uncertainty=(
                    "Interpretation from scanned titles only — confirm who actually buys from you."
                ),
                status="proposed",
            )
        )
    elif titles:
        proposals.append(
            SellerMemoryEntry(
                id="interp-catalog-focus",
                key="catalog_focus_hypothesis",
                label="Catalog focus (interpretation)",
                value=f"Your shop highlights {titles[0][:80]}",
                kind="interpretation",
                scope="shop_default",
                source="shop_scan",
                source_url=source_url,
                scan_date=when,
                confidence="inferred",
                uncertainty=(
                    "Inferred from scanned page titles — "
                    "edit or dismiss if your main focus differs."
                ),
                status="proposed",
            )
        )

    missing_questions = [
        {
            "key": "goal",
            "prompt": "What is your main goal right now?",
            "why_asked": "Decides whether Muse leads with commissions, gifts, or shop visits.",
        },
        {
            "key": "channels",
            "prompt": "Which channels can you post to this week?",
            "why_asked": "Hides moves for channels you don't use.",
        },
        {
            "key": "minutes_per_week",
            "prompt": "How much time do you have per week?",
            "why_asked": "Filters out multi-step shoots when you only have 15 minutes.",
        },
    ]

    return {
        "business_name": business_name.strip(),
        "scan_date": when,
        "source_url": source_url,
        "partial_warnings": partial_warnings,
        "proposed_entries": proposals,
        "missing_questions": missing_questions,
    }


def compute_rescan_diff(
    existing_entries: list[SellerMemoryEntry],
    scanned_entries: list[SellerMemoryEntry],
) -> dict[str, Any]:
    """Compare existing saved memory against a new scan without overwriting seller edits."""
    by_key: dict[tuple[str, str, str, str], SellerMemoryEntry] = {}
    for entry in existing_entries:
        if entry.status == "accepted":
            by_key[
                (
                    entry.key,
                    entry.scope,
                    _norm_scope_token(entry.product_key),
                    _norm_scope_token(entry.destination),
                )
            ] = entry

    diff_items: list[SellerMemoryDiffItem] = []
    preserved_count = 0

    for candidate in scanned_entries:
        prior = by_key.get(
            (
                candidate.key,
                candidate.scope,
                _norm_scope_token(candidate.product_key),
                _norm_scope_token(candidate.destination),
            )
        )
        if prior is None:
            diff_items.append(
                SellerMemoryDiffItem(
                    entry_id=candidate.id,
                    key=candidate.key,
                    label=candidate.label,
                    kind=candidate.kind,
                    before_value=None,
                    after_value=candidate.value,
                    source_url=candidate.source_url,
                    scan_date=candidate.scan_date,
                    change_type="added",
                    preserves_seller_edit=False,
                )
            )
            continue

        preserves_edit = bool(prior.seller_edited or prior.source == "user_input")
        if preserves_edit and prior.value != candidate.value:
            preserved_count += 1
        change_type = "unchanged" if prior.value.strip() == candidate.value.strip() else "changed"
        diff_items.append(
            SellerMemoryDiffItem(
                entry_id=candidate.id,
                key=candidate.key,
                label=candidate.label,
                kind=candidate.kind,
                before_value=prior.value,
                after_value=candidate.value,
                source_url=candidate.source_url,
                scan_date=candidate.scan_date,
                change_type=change_type,
                preserves_seller_edit=preserves_edit,
            )
        )

    return {
        "diff": diff_items,
        "preserved_edits_count": preserved_count,
    }


def parse_context_to_proposals(
    text: str,
    *,
    source_type: str = "typed",
    fixture_id: str | None = None,
    existing_entries: list[SellerMemoryEntry] | None = None,
    preferences: SellerPreferences | None = None,
    product_key: str | None = None,
    destination: str | None = None,
) -> dict[str, Any]:
    """Convert typed seller context or approved/fixture voice transcript into reviewable items."""
    transcript_text = text.strip()
    fixture_meta: dict[str, str] | None = None
    actual_source = "user_input"

    if source_type == "voice_demo_fixture":
        chosen_id = fixture_id or "watercolor_studio"
        fixture = DEMO_VOICE_FIXTURES.get(chosen_id, DEMO_VOICE_FIXTURES["watercolor_studio"])
        transcript_text = transcript_text or fixture["transcript"]
        fixture_meta = {"id": fixture["id"], "label": fixture["label"]}
        actual_source = "voice_demo_fixture"
    elif source_type == "voice_approved_transcript":
        actual_source = "voice_transcript"

    when = _today_iso()
    lower = transcript_text.lower()
    proposals: list[SellerMemoryEntry] = []
    conflicts: list[dict[str, str]] = []
    pref = preferences or SellerPreferences()

    # 1. URLs -> observation
    urls = re.findall(r"https?://[^\s,;]+", transcript_text)
    if urls:
        proposals.append(
            SellerMemoryEntry(
                id="obs-mentioned-url",
                key="shop_url",
                label="Shop URL",
                value=urls[0][:300],
                kind="observation",
                scope="shop_default",
                source=actual_source,  # type: ignore[arg-type]
                source_url=urls[0][:300],
                scan_date=when,
                confidence="confirmed",
                status="proposed",
            )
        )

    # 2. Explicit price facts (tied to product/destination scope & preserving currency)
    unique_prices = _extract_explicit_currency_prices(transcript_text)
    if unique_prices:
        proposals.append(
            SellerMemoryEntry(
                id="obs-stated-prices",
                key="price_range",
                label="Stated product prices",
                value=f"Stated price point(s): {', '.join(unique_prices[:4])}",
                kind="observation",
                scope="product",
                product_key=product_key,
                destination=destination,
                source=actual_source,  # type: ignore[arg-type]
                scan_date=when,
                confidence="confirmed",
                uncertainty="Tied to this product/destination only.",
                status="proposed",
            )
        )
        # Check price conflict ONLY within matching product/destination scope
        if existing_entries:
            norm_req_prod = _norm_scope_token(product_key)
            norm_req_dest = _norm_scope_token(destination)
            for existing in existing_entries:
                if existing.status != "accepted" or existing.key != "price_range":
                    continue
                norm_ex_prod = _norm_scope_token(existing.product_key)
                norm_ex_dest = _norm_scope_token(existing.destination)
                if norm_req_prod and norm_ex_prod and norm_req_prod != norm_ex_prod:
                    continue
                if norm_req_dest and norm_ex_dest and norm_req_dest != norm_ex_dest:
                    continue
                if unique_prices[0] not in existing.value:
                    conflicts.append(
                        {
                            "entry_id": existing.id,
                            "key": "price_range",
                            "message": (
                                f"New price note ({', '.join(unique_prices[:2])}) differs from "
                                f"saved price entry ('{existing.value}'). Review which to keep."
                            ),
                        }
                    )

    # 3. Time constraint -> preference
    min_match = re.search(r"(?:only\s+have\s+|about\s+|under\s+)?(\d{1,3})\s*min", lower)
    if min_match:
        mins = max(5, min(240, int(min_match.group(1))))
        proposals.append(
            SellerMemoryEntry(
                id="pref-minutes-per-week",
                key="minutes_per_week",
                label="Weekly time budget",
                value=f"{mins} minutes / week (prefer quick moves)",
                kind="preference",
                scope="shop_default",
                source=actual_source,  # type: ignore[arg-type]
                scan_date=when,
                confidence="confirmed",
                status="proposed",
            )
        )

    # 4. Excluded channels vs allowed channels
    excluded_channels: list[str] = []
    allowed_channels: list[str] = []
    for ch in _KNOWN_CHANNELS:
        if re.search(
            rf"(?:don'?t sell on|not on|no|skip|avoid|closed)\s+(?:my\s+)?{re.escape(ch)}\b",
            lower,
        ):
            excluded_channels.append(ch)
        elif re.search(rf"\b{re.escape(ch)}\b", lower):
            allowed_channels.append(ch)

    if excluded_channels:
        proposals.append(
            SellerMemoryEntry(
                id="pref-excluded-channels",
                key="excluded_channels",
                label="Unavailable channels",
                value=f"Exclude {', '.join(c.title() for c in excluded_channels)}",
                kind="preference",
                scope="shop_default",
                source=actual_source,  # type: ignore[arg-type]
                scan_date=when,
                confidence="confirmed",
                status="proposed",
            )
        )
    if allowed_channels:
        proposals.append(
            SellerMemoryEntry(
                id="pref-allowed-channels",
                key="channels",
                label="Active channels",
                value=", ".join(c.title() for c in allowed_channels),
                kind="preference",
                scope="shop_default",
                source=actual_source,  # type: ignore[arg-type]
                scan_date=when,
                confidence="confirmed",
                status="proposed",
            )
        )
        # Detect channel conflict with currently saved preferences or excluded list
        existing_excluded = {
            e.value.lower()
            for e in (existing_entries or [])
            if e.status == "accepted" and e.key == "excluded_channels"
        }
        for ch in allowed_channels:
            if any(ch in val for val in existing_excluded):
                conflicts.append(
                    {
                        "key": "channels",
                        "message": (
                            f"You mentioned {ch.title()}, which is currently marked as excluded. "
                            "Choose which preference should win."
                        ),
                    }
                )
        if pref.access.channels:
            missing_ch = [ch for ch in allowed_channels if ch not in pref.access.channels]
            if missing_ch and "etsy" in pref.access.channels and "etsy" in excluded_channels:
                conflicts.append(
                    {
                        "key": "excluded_channels",
                        "message": "Etsy is in your saved channels, while this note excludes it.",
                    }
                )

    # 5. Goal / campaign focus
    if any(k in lower for k in _COMMISSION_KEYWORDS):
        no_quote = "without quoting" in lower or "no commission price" in lower
        goal_val = (
            "Invite commissions without quoting an upfront price"
            if no_quote
            else "Get more custom commissions"
        )
        proposals.append(
            SellerMemoryEntry(
                id="goal-commissions",
                key="goal",
                label="Current campaign goal",
                value=goal_val,
                kind="goal",
                scope="campaign",
                source=actual_source,  # type: ignore[arg-type]
                scan_date=when,
                confidence="confirmed",
                status="proposed",
            )
        )
    elif "gift" in lower:
        proposals.append(
            SellerMemoryEntry(
                id="goal-gifts",
                key="goal",
                label="Current goal",
                value="Reach gift buyers",
                kind="goal",
                scope="campaign",
                source=actual_source,  # type: ignore[arg-type]
                scan_date=when,
                confidence="confirmed",
                status="proposed",
            )
        )

    # 6. Voice / caption constraints & avoidances
    if any(
        p in lower for p in ("short caption", "captions short", "under three sentences", "brief")
    ):
        proposals.append(
            SellerMemoryEntry(
                id="pref-short-captions",
                key="caption_length",
                label="Caption length preference",
                value="Keep captions short and focused",
                kind="preference",
                scope="shop_default",
                source=actual_source,  # type: ignore[arg-type]
                scan_date=when,
                confidence="confirmed",
                status="proposed",
            )
        )

    avoid_items: list[str] = []
    if re.search(r"(?:no|zero|without|avoid)\s+discount", lower):
        avoid_items.append("discount codes")
    if re.search(r"original\s+artwork|use\s+my\s+original", lower):
        proposals.append(
            SellerMemoryEntry(
                id="pref-original-photo",
                key="visual_rule",
                label="Photo rule",
                value="Keep original artwork photo (avoid heavy AI alteration)",
                kind="preference",
                scope="shop_default",
                source=actual_source,  # type: ignore[arg-type]
                scan_date=when,
                confidence="confirmed",
                status="proposed",
            )
        )
    if avoid_items:
        proposals.append(
            SellerMemoryEntry(
                id="pref-avoid-phrases",
                key="subjects_to_avoid",
                label="Phrases & tactics to avoid",
                value=", ".join(avoid_items),
                kind="preference",
                scope="shop_default",
                source=actual_source,  # type: ignore[arg-type]
                scan_date=when,
                confidence="confirmed",
                status="proposed",
            )
        )

    # 7. Free-text fallback context note if nothing structured matched or extra detail present
    if transcript_text and not proposals:
        proposals.append(
            SellerMemoryEntry(
                id=f"ctx-{_slugify(transcript_text, 24)}",
                key="context_note",
                label="Seller note",
                value=transcript_text[:280],
                kind="preference",
                scope="draft",
                source=actual_source,  # type: ignore[arg-type]
                scan_date=when,
                confidence="confirmed",
                uncertainty="Review whether this applies only to this draft or as a shop default.",
                status="proposed",
            )
        )

    return {
        "transcript": transcript_text,
        "source_type": actual_source,
        "fixture": fixture_meta,
        "proposed_entries": proposals,
        "conflicts": conflicts,
        "unclear": (
            "Add a channel or price point if you want recommendations filtered more tightly."
            if not proposals
            else ""
        ),
    }


def merge_entries_into_preferences(
    pref: SellerPreferences,
    accepted_entries: list[SellerMemoryEntry],
    voice: VoiceProfile | None = None,
) -> tuple[SellerPreferences, VoiceProfile]:
    """Synchronize accepted structured memory entries onto SellerPreferences & VoiceProfile."""
    next_pref = pref.model_copy(deep=True)
    next_voice = (voice or VoiceProfile()).model_copy(deep=True)

    entry_map: dict[str, SellerMemoryEntry] = {
        e.id: e for e in next_pref.memory_entries if e.status != "dismissed"
    }
    for entry in accepted_entries:
        if entry.status == "dismissed":
            entry_map.pop(entry.id, None)
            continue
        clean = entry.model_copy(update={"status": "accepted", "updated_at": _today_iso()})
        entry_map[clean.id] = clean

        if clean.key == "minutes_per_week":
            nums = re.findall(r"\d+", clean.value)
            if nums:
                next_pref.access.minutes_per_week = max(5, min(240, int(nums[0])))
        elif clean.key == "channels":
            parsed_ch = [ch.strip().lower() for ch in clean.value.split(",") if ch.strip()]
            if parsed_ch:
                next_pref.access.channels = parsed_ch
        elif clean.key == "excluded_channels":
            excl = {ch for ch in _KNOWN_CHANNELS if ch in clean.value.lower()}
            if excl and next_pref.access.channels:
                next_pref.access.channels = [
                    ch for ch in next_pref.access.channels if ch.lower() not in excl
                ]
        elif clean.key == "goal":
            next_pref.goal = clean.value[:200]
        elif clean.key == "audience" or clean.key == "audience_hypothesis":
            next_pref.audience = clean.value[:180]
        elif clean.key == "caption_length" and "short" in clean.value.lower():
            next_voice.caption_length = "short"
            if "shorter" not in next_voice.adjustments:
                next_voice.adjustments.append("shorter")
        elif clean.key == "subjects_to_avoid":
            terms = [t.strip() for t in clean.value.split(",") if t.strip()]
            for t in terms:
                if t not in next_pref.taste.subjects_to_avoid:
                    next_pref.taste.subjects_to_avoid.append(t)
                if t not in next_voice.words_to_avoid:
                    next_voice.words_to_avoid.append(t)
        elif clean.key == "context_note":
            next_pref.context_note = clean.value[:600]

    next_pref.memory_entries = list(entry_map.values())
    return next_pref, next_voice


def forget_memory_entry(
    pref: SellerPreferences,
    voice: VoiceProfile,
    entry_id: str,
) -> tuple[SellerPreferences, VoiceProfile, bool]:
    """Delete one saved entry by id and clean up any directly derived constraint."""
    next_pref = pref.model_copy(deep=True)
    next_voice = voice.model_copy(deep=True)
    target: SellerMemoryEntry | None = None
    remaining: list[SellerMemoryEntry] = []
    for entry in next_pref.memory_entries:
        if entry.id == entry_id:
            target = entry
        else:
            remaining.append(entry)

    if target is None:
        return next_pref, next_voice, False

    next_pref.memory_entries = remaining
    if target.key == "minutes_per_week":
        next_pref.access.minutes_per_week = None
    elif target.key == "goal":
        next_pref.goal = None
    elif target.key in {"audience", "audience_hypothesis"}:
        next_pref.audience = None
    elif target.key == "context_note":
        next_pref.context_note = None
    elif target.key == "caption_length":
        next_voice.caption_length = None
        next_voice.adjustments = [a for a in next_voice.adjustments if a != "shorter"]
    elif target.key == "subjects_to_avoid":
        removed_terms = {t.strip().lower() for t in target.value.split(",") if t.strip()}
        next_pref.taste.subjects_to_avoid = [
            t for t in next_pref.taste.subjects_to_avoid if t.lower() not in removed_terms
        ]
        next_voice.words_to_avoid = [
            t for t in next_voice.words_to_avoid if t.lower() not in removed_terms
        ]
    elif target.key == "channels":
        next_pref.access.channels = []
    return next_pref, next_voice, True


def suggest_memory_updates(
    *,
    preferences: SellerPreferences,
    voice_profile: VoiceProfile,
    dismiss_signals: list[DismissSignal],
) -> list[SuggestedMemoryUpdate]:
    """Derive reviewable update suggestions from repeated feedback or dismiss reasons."""
    existing = {s.id: s for s in preferences.suggested_updates}
    now = _today_iso()
    candidates: list[SuggestedMemoryUpdate] = []

    time_count = sum(1 for s in dismiss_signals if s.reason == "too_much_time")
    if time_count >= 2 and preferences.access.minutes_per_week != 15:
        candidates.append(
            SuggestedMemoryUpdate(
                id="suggest-prefer-15min",
                key="minutes_per_week",
                label="Prefer moves under 15 minutes",
                proposed_value="15 minutes / week",
                kind="preference",
                reason_signal=f"Based on {time_count} dismissals marked 'Too much time'.",
                patch={"minutes_per_week": 15},
                dismiss_count=time_count,
                created_at=now,
            )
        )

    adv_count = sum(1 for s in dismiss_signals if s.reason == "too_advanced")
    if adv_count >= 2 and preferences.experience != "new":
        candidates.append(
            SuggestedMemoryUpdate(
                id="suggest-keep-simple",
                key="experience",
                label="Keep steps beginner-friendly",
                proposed_value="Simple organic moves first (no ad-manager math)",
                kind="preference",
                reason_signal=f"Based on {adv_count} dismissals marked 'Too advanced'.",
                patch={"experience": "new"},
                dismiss_count=adv_count,
                created_at=now,
            )
        )

    for ch in _KNOWN_CHANNELS:
        ch_count = sum(
            1
            for s in dismiss_signals
            if s.reason in {"no_access", "wrong_channel"}
            and ((s.channel or "").lower() == ch or ch in f"{s.title} {s.id}".lower())
        )
        if ch_count >= 1 and (not preferences.access.channels or ch in preferences.access.channels):
            candidates.append(
                SuggestedMemoryUpdate(
                    id=f"suggest-exclude-{ch}",
                    key="excluded_channels",
                    label=f"Stop suggesting {ch.title()} moves",
                    proposed_value=f"Exclude {ch.title()} from recommendations",
                    kind="preference",
                    reason_signal=(
                        f"Based on your '{ch.title()}' unavailable/wrong-channel feedback."
                    ),
                    patch={"exclude_channel": ch},
                    dismiss_count=ch_count,
                    created_at=now,
                )
            )

    if "shorter" in voice_profile.adjustments and voice_profile.caption_length != "short":
        candidates.append(
            SuggestedMemoryUpdate(
                id="suggest-short-captions",
                key="caption_length",
                label="Save 'short captions' as your default voice",
                proposed_value="Keep captions brief (2–3 sentences)",
                kind="preference",
                reason_signal="Based on repeated 'Shorter' voice adjustments.",
                patch={"caption_length": "short"},
                dismiss_count=voice_profile.adjustments.count("shorter"),
                created_at=now,
            )
        )

    # Preserve pending/approved/dismissed statuses cleanly unless count grew after dismissal.
    result: list[SuggestedMemoryUpdate] = []
    seen_ids: set[str] = set()
    for cand in candidates:
        prior = existing.get(cand.id)
        if (
            prior
            and prior.status in {"approved", "dismissed"}
            and prior.dismiss_count >= cand.dismiss_count
        ):
            result.append(prior)
        else:
            result.append(cand)
        seen_ids.add(cand.id)

    for old_id, old_item in existing.items():
        if old_id not in seen_ids:
            result.append(old_item)

    return result


def respond_to_suggestion(
    *,
    preferences: SellerPreferences,
    voice_profile: VoiceProfile,
    suggestion_id: str,
    decision: str,
) -> tuple[SellerPreferences, VoiceProfile, SuggestedMemoryUpdate | None]:
    """Approve or dismiss a suggested memory update explicitly."""
    next_pref = preferences.model_copy(deep=True)
    next_voice = voice_profile.model_copy(deep=True)
    target: SuggestedMemoryUpdate | None = None

    for item in next_pref.suggested_updates:
        if item.id != suggestion_id:
            continue
        target = item
        if decision == "dismiss":
            item.status = "dismissed"
            break
        if decision == "approve":
            item.status = "approved"
            patch = item.patch or {}
            new_entry: SellerMemoryEntry | None = None
            if "minutes_per_week" in patch:
                mins = int(patch["minutes_per_week"])
                next_pref.access.minutes_per_week = mins
                new_entry = SellerMemoryEntry(
                    id="pref-minutes-per-week",
                    key="minutes_per_week",
                    label="Weekly time budget",
                    value=f"{mins} minutes / week (approved from feedback)",
                    kind="preference",
                    scope="shop_default",
                    source="feedback_suggestion",
                    confidence="confirmed",
                    scan_date=_today_iso(),
                )
            elif "experience" in patch:
                next_pref.experience = patch["experience"]
                new_entry = SellerMemoryEntry(
                    id="pref-experience",
                    key="experience",
                    label="Marketing comfort level",
                    value=item.proposed_value,
                    kind="preference",
                    scope="shop_default",
                    source="feedback_suggestion",
                    confidence="confirmed",
                    scan_date=_today_iso(),
                )
            elif "exclude_channel" in patch:
                ch = str(patch["exclude_channel"]).lower()
                if next_pref.access.channels:
                    next_pref.access.channels = [
                        c for c in next_pref.access.channels if c.lower() != ch
                    ]
                new_entry = SellerMemoryEntry(
                    id=f"pref-exclude-{ch}",
                    key="excluded_channels",
                    label=f"Excluded channel: {ch.title()}",
                    value=f"Exclude {ch.title()}",
                    kind="preference",
                    scope="shop_default",
                    source="feedback_suggestion",
                    confidence="confirmed",
                    scan_date=_today_iso(),
                )
            elif "caption_length" in patch:
                next_voice.caption_length = "short"
                new_entry = SellerMemoryEntry(
                    id="pref-short-captions",
                    key="caption_length",
                    label="Caption length preference",
                    value="Keep captions short and focused",
                    kind="preference",
                    scope="shop_default",
                    source="feedback_suggestion",
                    confidence="confirmed",
                    scan_date=_today_iso(),
                )

            if new_entry is not None:
                next_pref, next_voice = merge_entries_into_preferences(
                    next_pref, [new_entry], next_voice
                )
            break

    return next_pref, next_voice, target


def _competitor_display(comp: CompetitorEntry) -> str:
    return comp.name.strip() or re.sub(r"^https?://(www\.)?", "", comp.url).split("/")[0]


_SCOPE_PRIORITY = {"draft": 4, "campaign": 3, "product": 2, "shop_default": 1}


def _select_scoped_entries(
    entries: list[SellerMemoryEntry],
    *,
    effective_product: str,
    effective_destination: str,
) -> list[SellerMemoryEntry]:
    """Keep only entries matching product_key, destination, and applicable scope (never bleed)."""
    norm_req_prod = _norm_scope_token(effective_product)
    norm_req_dest = _norm_scope_token(effective_destination)

    # Group by entry.key so multi-product/destination ambiguities stay isolated per fact key.
    by_key: dict[str, list[SellerMemoryEntry]] = {}
    for entry in entries:
        by_key.setdefault(entry.key, []).append(entry)

    result: list[SellerMemoryEntry] = []
    for _key, items in by_key.items():
        # Step 1: filter by product_key
        prod_candidates: list[SellerMemoryEntry] = []
        distinct_prods = {
            _norm_scope_token(e.product_key) for e in items if _norm_scope_token(e.product_key)
        }
        has_exact_prod = bool(norm_req_prod) and norm_req_prod in distinct_prods
        for e in items:
            ep = _norm_scope_token(e.product_key)
            if norm_req_prod:
                if ep and ep != norm_req_prod:
                    continue
                if has_exact_prod and not ep and e.scope in {"product", "campaign", "draft"}:
                    continue
            else:
                if ep and len(distinct_prods) > 1:
                    continue
            prod_candidates.append(e)

        # Step 2: filter survivors by destination
        distinct_dests = {
            _norm_scope_token(e.destination)
            for e in prod_candidates
            if _norm_scope_token(e.destination)
        }
        has_exact_dest = bool(norm_req_dest) and norm_req_dest in distinct_dests
        for e in prod_candidates:
            ed = _norm_scope_token(e.destination)
            if norm_req_dest:
                if ed and ed != norm_req_dest:
                    continue
                if has_exact_dest and not ed and e.scope in {"product", "campaign", "draft"}:
                    continue
            else:
                if ed and len(distinct_dests) > 1:
                    continue
            result.append(e)

    result.sort(
        key=lambda e: (
            1 if (_norm_scope_token(e.product_key) == norm_req_prod and norm_req_prod) else 0,
            1 if (_norm_scope_token(e.destination) == norm_req_dest and norm_req_dest) else 0,
            _SCOPE_PRIORITY.get(e.scope, 0),
        ),
        reverse=True,
    )
    return result


def _parse_excluded_channels_from_text(text: str) -> set[str]:
    lower = str(text or "").lower()
    return {ch for ch in _KNOWN_CHANNELS if re.search(rf"\b{re.escape(ch)}\b", lower)}


def _build_editor_defaults_for_move(
    *,
    move: dict[str, Any] | None,
    business_name: str,
    effective_product: str,
    effective_destination: str,
    effective_goal: str,
    effective_context_note: str,
    effective_minutes: int,
    primary_channel: str | None,
    caption_length: str,
    tone: str,
    avoid_list: list[str],
    short_price: str,
    is_draft_override: bool,
) -> dict[str, Any]:
    mapped_goal = "story"
    if move is not None:
        raw_goal = str(move.get("goal") or "").lower()
        if raw_goal == "gift":
            mapped_goal = "gift"
        elif raw_goal in {"visits", "visit"}:
            mapped_goal = "visit"
        else:
            mapped_goal = "story"
    elif "gift" in effective_goal.lower():
        mapped_goal = "gift"

    raw_price = move.get("price_claim") if move else None
    move_price = str(raw_price if raw_price is not None else short_price)
    default_placement = (
        "facebook_feed"
        if (move and move.get("channel") == "facebook") or primary_channel == "facebook"
        else "instagram_feed"
    )
    return {
        "recommendation_id": move["id"] if move else None,
        "recommendation_title": move["title"] if move else "",
        "recommendation_action": move["action"] if move else "",
        "business_name": business_name,
        "product_name": effective_product or business_name,
        "destination": effective_destination or "website",
        "channel": move["channel"] if move else primary_channel,
        "goal": mapped_goal,
        "cta": move["cta"] if move else "Visit shop",
        "caption_length": caption_length,
        "tone": tone,
        "words_to_avoid": avoid_list,
        "price_claim": move_price,
        "minutes_per_week": effective_minutes,
        "context_summary": effective_context_note or effective_goal,
        "why_this_fits": move["why_this_fits"] if move else "",
        "is_draft_override": is_draft_override,
        "output_provenance": move.get("output_provenance", "suggested_starting_approach")
        if move
        else "suggested_starting_approach",
        "output_label": move.get("output_label", "Suggested starting approach")
        if move
        else "Suggested starting approach",
        "organic_first": move.get("organic_first", True) if move else True,
        "organic_guidance_note": move.get(
            "organic_guidance_note",
            "Organic post first — no paid ad spend or ad account required.",
        )
        if move
        else "Organic post first — no paid ad spend or ad account required.",
        "unconfirmed_audience": move.get("unconfirmed_audience", "") if move else "",
        "audience_confirmed": False,
        "approved_facts": list(move.get("approved_facts", [])) if move else [],
        "missing_facts": list(move.get("missing_facts", [])) if move else [],
        "placement": move.get("placement", default_placement) if move else default_placement,
        "placement_note": "App export preset (not verified Meta policy)",
    }


_SERVICES_INQUIRY_WORDS = ("lead", "client", "inquir", "enquir", "call", "book", "consult")


def _services_moves(
    *,
    business_name: str,
    subject_label: str,
    primary_channel: str,
    allowed_channels: list[str],
    destination: str,
    short_price: str,
    price_comp: CompetitorEntry | None,
    insp_comp: CompetitorEntry | None,
    any_comp: CompetitorEntry | None,
) -> list[dict[str, Any]]:
    """Moves for a business that sells a service. Same categories, so scoring still applies."""
    channel_title = primary_channel.title()

    def comp_fields(comp: CompetitorEntry | None) -> dict[str, Any]:
        return {
            "competitor_used": _competitor_display(comp) if comp else None,
            "competitor_role": comp.role if comp else None,
            "competitor_rationale": (comp.rationale or comp.reason).strip() if comp else "",
        }

    offer_comp = price_comp or any_comp
    style_comp = insp_comp or any_comp
    style_note = (
        f" (adapted in style from {_competitor_display(style_comp)}, in your own voice)"
        if style_comp
        else ""
    )
    moves: list[dict[str, Any]] = [
        {
            "id": "move-services-offer",
            "category": "price_reference",
            "title": f"Say what a first project with {business_name} includes",
            "action": (
                f"Publish one {channel_title} post that names {subject_label}, who it is for "
                "and how to start (a call, a message or a short form), and link to that page."
            ),
            "channel": primary_channel,
            "goal": "visits",
            "estimated_minutes": 12,
            "base_score": 58.0,
            **comp_fields(offer_comp),
            "price_claim": short_price,
            "cta": "See the service",
        },
        {
            "id": "move-services-result",
            "category": "similar_audience",
            "title": "Share a recent client result, with permission",
            "action": (
                f"Post on {channel_title} about one recent project: what the client needed, "
                "what changed, and only results you can show."
            ),
            "channel": primary_channel,
            "goal": "story",
            "estimated_minutes": 15,
            "base_score": 56.0,
            **comp_fields(any_comp),
            "price_claim": "",
            "cta": "Read the project",
        },
        {
            "id": "move-services-process",
            "category": "inspiration",
            "title": f"Show how {business_name} works with clients",
            "action": (
                f"Post a short {channel_title} note or clip about one step of how you work"
                f"{style_note}."
            ),
            "channel": primary_channel,
            "goal": "story",
            "estimated_minutes": 10,
            "base_score": 55.0,
            **comp_fields(style_comp),
            "price_claim": "",
            "cta": "See how it works",
        },
        {
            "id": "move-services-invite",
            "category": "commission",
            "title": f"Answer one question people ask {business_name}",
            "action": (
                f"Answer a question prospects often ask, on {channel_title}, then invite them to "
                "message you or book a call. Do not promise results."
            ),
            "channel": primary_channel,
            "goal": "story",
            "estimated_minutes": 10,
            "base_score": 48.0,
            **comp_fields(any_comp),
            "price_claim": "",
            "cta": "Book a call",
        },
    ]
    page_channel = "website" if "website" in allowed_channels else primary_channel
    moves.append(
        {
            "id": "move-services-page",
            "category": "catalog",
            "title": f"Tighten the services page on {destination or 'your website'}",
            "action": (
                "Rewrite the first lines of your main services page so they say who you help "
                "and how to start, then check the links from your profiles (about 40 minutes)."
            ),
            "channel": page_channel,
            "goal": "visits",
            "estimated_minutes": 40,
            "base_score": 52.0,
            **comp_fields(None),
            "price_claim": "",
            "cta": "Update the services page",
        }
    )
    return moves


def rank_seller_recommendations(
    *,
    business_name: str = "Your Studio",
    business_type: BusinessType | None = None,
    product_name: str | None = None,
    preferences: SellerPreferences | None = None,
    voice_profile: VoiceProfile | None = None,
    competitor_entries: list[CompetitorEntry] | None = None,
    draft_override: dict[str, Any] | None = None,
    dismiss_signals: list[DismissSignal] | None = None,
    previous_top_id: str | None = None,
) -> dict[str, Any]:
    """Compute context-aware ranked recommendations, clear explanations, and editor defaults.

    A services business (from setup) gets moves about its offer, client results and how to get
    in touch instead of the shop moves (entry prices, gifts, commissions, listing titles).
    """
    services = business_type == "services"
    pref = (preferences or SellerPreferences()).model_copy(deep=True)
    voice = voice_profile or VoiceProfile()
    override = draft_override or {}
    signals = dismiss_signals or []

    # Step 1: Resolve draft_override identity scope & ignored entries BEFORE deriving defaults.
    effective_product = str(override.get("product_name") or product_name or "").strip()
    effective_destination = str(override.get("destination") or "").strip()

    raw_ignored = (
        override.get("ignore_entry_ids")
        if override.get("ignore_entry_ids") is not None
        else override.get("ignored_entry_ids")
    )
    ignored_entry_ids = {str(x).strip() for x in (raw_ignored or []) if str(x).strip()}

    accepted_entries = [e for e in pref.memory_entries if e.status == "accepted"]
    ignored_entries = [e for e in accepted_entries if e.id in ignored_entry_ids]
    ignored_keys = {e.key for e in ignored_entries}
    unignored_entries = [e for e in accepted_entries if e.id not in ignored_entry_ids]

    # Step 2: Filter surviving accepted entries by product_key, destination, and scope.
    active_entries = _select_scoped_entries(
        unignored_entries,
        effective_product=effective_product,
        effective_destination=effective_destination,
    )

    def _first_entry(key: str) -> SellerMemoryEntry | None:
        return next((e for e in active_entries if e.key == key), None)

    # Step 3: Derive effective constraints after applying ignore_entry_ids & scope filters.
    if override.get("minutes_per_week") is not None:
        effective_minutes = int(override["minutes_per_week"])
    else:
        min_entry = _first_entry("minutes_per_week")
        if min_entry is not None:
            nums = re.findall(r"\d+", min_entry.value)
            effective_minutes = max(5, min(240, int(nums[0]))) if nums else 30
        elif "minutes_per_week" in ignored_keys:
            effective_minutes = 30
        else:
            effective_minutes = pref.access.minutes_per_week or 30

    goal_override = str(override.get("goal") or "").strip()
    if goal_override:
        effective_goal = goal_override
    else:
        goal_entry = _first_entry("goal")
        if goal_entry is not None:
            effective_goal = goal_entry.value.strip()
        elif "goal" in ignored_keys:
            effective_goal = ""
        else:
            effective_goal = str(pref.goal or "").strip()

    note_override = str(override.get("context_note") or "").strip()
    if note_override:
        effective_context_note = note_override
    else:
        note_entry = _first_entry("context_note")
        if note_entry is not None:
            effective_context_note = note_entry.value.strip()
        elif "context_note" in ignored_keys:
            effective_context_note = ""
        else:
            effective_context_note = str(pref.context_note or "").strip()

    if "channels" in override and isinstance(override["channels"], list):
        effective_channels = [
            str(c).strip().lower() for c in override["channels"] if str(c).strip()
        ]
        channels_explicit = True
    else:
        channels_explicit = False
        ch_entry = _first_entry("channels")
        if ch_entry is not None:
            effective_channels = [
                ch.strip().lower() for ch in ch_entry.value.split(",") if ch.strip()
            ]
        elif "channels" in ignored_keys:
            effective_channels = []
        else:
            effective_channels = [c.lower() for c in pref.access.channels]

    # Collect price fact strictly from active scoped entries or override (preserve currency!)
    price_entry = _first_entry("price_range")
    if price_entry and not effective_destination and _norm_scope_token(price_entry.destination):
        effective_destination = str(price_entry.destination).strip()
    price_claim = str(
        override.get("price_claim") or (price_entry.value if price_entry else "")
    ).strip()
    short_price = _extract_short_price(price_claim)

    # Gather excluded channels from active unignored entries, override, and dismiss signals.
    excluded_channels: set[str] = set()
    for ch in override.get("excluded_channels") or []:
        if str(ch).strip():
            excluded_channels.add(str(ch).strip().lower())
    for e in active_entries:
        if e.key == "excluded_channels":
            excluded_channels |= _parse_excluded_channels_from_text(e.value)
    for sig in signals:
        if sig.reason in {"no_access", "wrong_channel"}:
            detected_ch = (sig.channel or "").lower() or next(
                (ch for ch in _KNOWN_CHANNELS if ch in f"{sig.title} {sig.id}".lower()), ""
            )
            if detected_ch:
                excluded_channels.add(detected_ch)

    if channels_explicit or effective_channels:
        allowed_channels = [ch for ch in effective_channels if ch not in excluded_channels]
    else:
        allowed_channels = [
            ch for ch in ("instagram", "facebook", "website") if ch not in excluded_channels
        ]

    all_channels_excluded = len(allowed_channels) == 0
    primary_channel: str | None = allowed_channels[0] if allowed_channels else None
    active_comps = [c for c in (competitor_entries or pref.competitor_entries) if c.selected]

    comp_by_role: dict[CompetitorRole, CompetitorEntry] = {}
    for comp in active_comps:
        comp_by_role.setdefault(comp.role, comp)

    price_comp = comp_by_role.get("price_reference")
    audience_comp = comp_by_role.get("similar_audience")
    insp_comp = comp_by_role.get("inspiration")
    any_comp = active_comps[0] if active_comps else None

    subject_label = effective_product or (
        f"{business_name}'s main service" if services else f"{business_name} featured work"
    )

    # Build role-differentiated candidate moves only when at least one allowed channel remains.
    candidates: list[dict[str, Any]] = []
    if primary_channel is not None and services:
        candidates = _services_moves(
            business_name=business_name,
            subject_label=subject_label,
            primary_channel=primary_channel,
            allowed_channels=allowed_channels,
            destination=effective_destination,
            short_price=short_price,
            price_comp=price_comp,
            insp_comp=insp_comp,
            any_comp=any_comp,
        )
    elif primary_channel is not None:
        channel_title = primary_channel.title()

        # Move A: Price positioning / Entry offer (rises when competitor role == "price_reference")
        comp_a = price_comp or any_comp
        comp_a_name = _competitor_display(comp_a) if comp_a else "watched shops"
        comp_a_why = (comp_a.rationale or comp_a.reason).strip() if comp_a else ""
        price_lead_headline = (
            f"Lead with your {short_price} entry work against {comp_a_name}"
            if short_price
            else f"Clarify your entry price tier against {comp_a_name}"
        )
        candidates.append(
            {
                "id": "move-price-positioning",
                "category": "price_reference",
                "title": price_lead_headline,
                "action": (
                    f"Publish one {channel_title} post pairing {subject_label} with "
                    f"{short_price or 'a clear starting price'} and link straight to your listing."
                ),
                "channel": primary_channel,
                "goal": "visits",
                "estimated_minutes": 12,
                "base_score": 58.0,
                "competitor_used": comp_a_name if comp_a else None,
                "competitor_role": comp_a.role if comp_a else None,
                "competitor_rationale": comp_a_why,
                "price_claim": short_price,
                "cta": f"Shop {short_price}" if short_price else "See listing",
            }
        )

        # Move B: Audience & Gift Angle (rises on similar_audience or gift goal)
        comp_b = audience_comp or any_comp
        comp_b_name = _competitor_display(comp_b) if comp_b else "similar sellers"
        comp_b_why = (comp_b.rationale or comp_b.reason).strip() if comp_b else ""
        candidates.append(
            {
                "id": "move-similar-audience",
                "category": "similar_audience",
                "title": f"Reach {business_name}'s buyer audience with a ready-to-gift angle",
                "action": (
                    f"Share {subject_label} on {channel_title} showing how buyers place or "
                    f"gift it in a real home setting."
                ),
                "channel": primary_channel,
                "goal": "gift",
                "estimated_minutes": 15,
                "base_score": 56.0,
                "competitor_used": comp_b_name if comp_b else None,
                "competitor_role": comp_b.role if comp_b else None,
                "competitor_rationale": comp_b_why,
                "price_claim": short_price,
                "cta": "Explore gift option",
            }
        )

        # Move C: Creative / Process Inspiration (rises on inspiration or story goal)
        comp_c = insp_comp or any_comp
        comp_c_name = _competitor_display(comp_c) if comp_c else "inspiring studios"
        comp_c_why = (comp_c.rationale or comp_c.reason).strip() if comp_c else ""
        candidates.append(
            {
                "id": "move-inspiration-story",
                "category": "inspiration",
                "title": f"Share your studio story behind {subject_label}",
                "action": (
                    f"Post your original photo of {subject_label} with 2–3 sentences about your "
                    f"process and materials (adapted in style from {comp_c_name}, "
                    "in your own voice)."
                ),
                "channel": primary_channel,
                "goal": "story",
                "estimated_minutes": 10,
                "base_score": 55.0,
                "competitor_used": comp_c_name if comp_c else None,
                "competitor_role": comp_c.role if comp_c else None,
                "competitor_rationale": comp_c_why,
                "price_claim": "",
                "cta": "Read studio story",
            }
        )

        # Move D: Commission / Custom inquiry post (rises on commission/inquiry goal)
        candidates.append(
            {
                "id": "move-commission-invite",
                "category": "commission",
                "title": f"Invite custom commissions for {business_name}",
                "action": (
                    f"Show {subject_label} on {channel_title} and invite buyers to message "
                    "for custom sizes without quoting an upfront commission price."
                ),
                "channel": primary_channel,
                "goal": "story",
                "estimated_minutes": 10,
                "base_score": 48.0,
                "competitor_used": _competitor_display(any_comp) if any_comp else None,
                "competitor_role": any_comp.role if any_comp else None,
                "competitor_rationale": (
                    (any_comp.rationale or any_comp.reason).strip() if any_comp else ""
                ),
                "price_claim": "",
                "cta": "Message for a custom piece",
            }
        )

        # Move E: Multi-listing catalog / time-heavy update (gets penalized when time <= 15 mins)
        if "website" in allowed_channels or primary_channel:
            refresh_channel = "website" if "website" in allowed_channels else primary_channel
            candidates.append(
                {
                    "id": "move-catalog-refresh",
                    "category": "catalog",
                    "title": (
                        "Refresh titles & descriptions for up to 5 listings on "
                        f"{effective_destination or 'your shop'}"
                    ),
                    "action": (
                        "Update up to 5 shop titles with room-specific search terms and verify "
                        "cross-channel links (requires ~40 minutes)."
                    ),
                    "channel": refresh_channel,
                    "goal": "visits",
                    "estimated_minutes": 40,
                    "base_score": 52.0,
                    "competitor_used": None,
                    "competitor_role": None,
                    "competitor_rationale": "",
                    "price_claim": "",
                    "cta": "Update shop titles",
                }
            )

    already_tried = {
        s.title.lower().strip() for s in signals if s.reason == "already_tried" and s.title
    }

    ranked: list[dict[str, Any]] = []
    for move in candidates:
        if move["channel"] in excluded_channels:
            continue
        score = float(move["base_score"])
        reasons: list[str] = []
        used_entries: list[dict[str, str]] = []

        # 1. Competitor role & rationale boost
        cat = move["category"]
        if cat in {"price_reference", "similar_audience", "inspiration"}:
            role_match = comp_by_role.get(cat)  # type: ignore[arg-type]
            if role_match is not None:
                score += 55.0
                c_name = _competitor_display(role_match)
                why_text = (role_match.rationale or role_match.reason or "").strip()
                role_label = _ROLE_LABELS[role_match.role]
                reasons.append(
                    f"Prioritized by watched competitor {c_name} ({role_label})"
                    + (f": “{why_text}”" if why_text else "")
                )
                used_entries.append(
                    {
                        "id": f"comp:{c_name}",
                        "label": f"Competitor · {role_label}",
                        "value": f"{c_name}" + (f" — {why_text}" if why_text else ""),
                        "source": "competitor_watchlist",
                        "scope": "shop_default",
                    }
                )
            elif any_comp is None:
                score -= 10.0

        # 2. Price control & price fact grounding
        if cat == "price_reference":
            if not pref.access.can_change_prices and not services:
                score -= 70.0
                reasons.append("Lowered because listing prices are fixed")
            elif price_entry is not None:
                score += 18.0
                used_entries.append(
                    {
                        "id": price_entry.id,
                        "label": price_entry.label,
                        "value": price_entry.value,
                        "source": price_entry.source,
                        "scope": price_entry.scope,
                    }
                )

        # 3. Time constraint fit
        est_mins = int(move["estimated_minutes"])
        if est_mins <= effective_minutes:
            if effective_minutes <= 15:
                score += 24.0
                reasons.append(f"Fits your {effective_minutes} minutes this week")
        else:
            score -= 75.0 if effective_minutes <= 15 else 500.0
            reasons.append(
                f"Takes about {est_mins} minutes, more than your {effective_minutes} "
                "minutes this week"
            )

        # 4. Goal & plain-language context match (draft goal overrides shop defaults)
        goal_lower = effective_goal.lower()
        note_lower = effective_context_note.lower()
        combined_intent = f"{goal_lower} {note_lower}"
        draft_goal_raw = str(override.get("goal") or "").strip()
        override_goal_changed = bool(draft_goal_raw) and draft_goal_raw != (pref.goal or "").strip()
        if services and any(w in combined_intent for w in _SERVICES_INQUIRY_WORDS):
            intent_cat: str | None = "commission"
        elif "commission" in combined_intent:
            intent_cat = "commission"
        elif "story" in combined_intent:
            intent_cat = "inspiration"
        elif "gift" in combined_intent:
            intent_cat = "similar_audience"
        elif any(w in combined_intent for w in ("price", "print", "visit")):
            intent_cat = "price_reference"
        else:
            intent_cat = None

        if intent_cat == cat:
            if cat == "commission":
                score += 120.0
                reasons.append(
                    "Matches your goal of more inquiries"
                    if services
                    else "Matches your commission goal"
                )
            elif cat == "similar_audience":
                score += 115.0 if override_goal_changed else 32.0
                reasons.append("Matches your gift-buyer goal")
            elif cat == "inspiration":
                score += 115.0 if override_goal_changed else 30.0
                reasons.append(
                    "Matches your storytelling focus"
                    if services
                    else "Matches your studio storytelling focus"
                )
            elif cat == "price_reference":
                score += 115.0 if override_goal_changed else 26.0

        if move["title"].lower() in already_tried:
            score -= 120.0

        for e in active_entries:
            if e.key in {
                "goal",
                "minutes_per_week",
                "caption_length",
                "subjects_to_avoid",
                "context_note",
            }:
                used_entries.append(
                    {
                        "id": e.id,
                        "label": e.label,
                        "value": e.value,
                        "source": e.source,
                        "scope": "draft" if override else e.scope,
                    }
                )
        # De-duplicate used_entries by id
        dedup_entries = list({u["id"]: u for u in used_entries}.values())

        why_this_fits = (
            "; ".join(reasons)
            if reasons
            else (
                f"Matches {business_name}'s available {str(move['channel']).title()} channel "
                "(no fresh research ran)."
                if move.get("channel")
                else f"Prepared from {business_name}'s saved profile (no fresh research ran)."
            )
        )
        # Explicit missing-fact prompts (never fabricate price, audience, or checkout readiness)
        missing_facts: list[str] = []
        if not short_price:
            missing_facts.append(
                "Price not set — leave price blank or add your starting price before sharing."
            )
        if not effective_product:
            missing_facts.append(
                "Service not named: choose the service or offer to promote."
                if services
                else "Product not specified — choose a product or artwork."
            )
        if any(tok in combined_intent for tok in ("sale", "sales", "buy", "checkout", "order")):
            if not effective_destination:
                missing_facts.append(
                    "Sales goal selected without a verified checkout destination — "
                    "start with shop visits or buyer inquiries."
                )
            else:
                missing_facts.append(
                    "Checkout and conversion tracking are not verified — "
                    "start with organic reach or shop visits."
                )
        audience_entry = _first_entry("audience")
        raw_audience = (
            (audience_entry.value if audience_entry else "") or (pref.audience or "")
        ).strip()
        if not raw_audience:
            missing_facts.append(
                "Audience not confirmed — review and edit the starting audience hypothesis."
            )
            unconfirmed_audience = (
                f"Unconfirmed starting hypothesis (edit before sharing): "
                f"Buyers interested in {subject_label}"
            )
        else:
            unconfirmed_audience = (
                f"Unconfirmed starting hypothesis (edit before sharing): {raw_audience}"
            )
        if not active_comps:
            missing_facts.append(
                "No watched competitor yet — ranked from your saved shop profile only."
            )

        approved_facts: list[dict[str, str]] = [
            {
                "id": u["id"],
                "label": u["label"],
                "value": u["value"],
                "source": u["source"],
                "scope": u["scope"],
            }
            for u in dedup_entries
        ]
        if effective_goal:
            approved_facts.append(
                {
                    "id": "fact:goal",
                    "label": "Selected goal",
                    "value": effective_goal,
                    "source": "draft_override" if draft_goal_raw else "seller_preferences",
                    "scope": "draft" if draft_goal_raw else "shop_default",
                }
            )
        draft_price_raw = str(override.get("price_claim") or "").strip()
        if short_price:
            if draft_price_raw:
                approved_facts.append(
                    {
                        "id": "fact:draft_price",
                        "label": "Draft price (not saved)",
                        "value": short_price,
                        "source": "draft_override",
                        "scope": "draft",
                    }
                )
            elif price_entry and not any(f["id"] == price_entry.id for f in approved_facts):
                price_scope = price_entry.scope
                if price_scope == "shop_default" and price_entry.product_key:
                    price_scope = "product"
                elif price_scope == "shop_default" and price_entry.destination:
                    price_scope = "destination"
                approved_facts.append(
                    {
                        "id": price_entry.id,
                        "label": price_entry.label or "Starting price",
                        "value": short_price,
                        "source": price_entry.source,
                        "scope": price_scope,
                        "product_key": price_entry.product_key or "",
                        "destination": price_entry.destination or "",
                    }
                )

        move_placement = "facebook_feed" if move.get("channel") == "facebook" else "instagram_feed"
        ranked.append(
            {
                **move,
                "score": round(score, 1),
                "priority": "high" if score >= 85 else ("medium" if score >= 55 else "low"),
                "why_this_fits": why_this_fits,
                "used_entries": dedup_entries,
                "output_provenance": "suggested_starting_approach",
                "output_label": "Suggested starting approach",
                "organic_first": True,
                "organic_guidance_note": (
                    "Organic post first — no paid ad spend or ad account required."
                ),
                "unconfirmed_audience": unconfirmed_audience,
                "audience_confirmed": False,
                "approved_facts": approved_facts,
                "missing_facts": missing_facts,
                "placement": move_placement,
                "placement_note": "App export preset (not verified Meta policy)",
            }
        )

    all_over_budget = bool(ranked) and all(
        int(item["estimated_minutes"]) > effective_minutes for item in ranked
    )
    if all_over_budget:
        ranked.sort(key=lambda item: (item["estimated_minutes"], -item["score"]))
    else:
        ranked.sort(key=lambda item: (-item["score"], item["estimated_minutes"]))

    ignored_avoid = {
        t.strip().lower()
        for e in ignored_entries
        if e.key == "subjects_to_avoid"
        for t in e.value.split(",")
        if t.strip()
    }
    active_avoid_terms = [
        t.strip()
        for e in active_entries
        if e.key == "subjects_to_avoid"
        for t in e.value.split(",")
        if t.strip()
    ]
    base_avoid = [
        t
        for t in [*pref.taste.subjects_to_avoid, *voice.words_to_avoid]
        if t.strip().lower() not in ignored_avoid
    ]
    avoid_list = list(dict.fromkeys([*base_avoid, *active_avoid_terms]))

    caption_entry = _first_entry("caption_length")
    if override.get("caption_length"):
        eff_caption_len = str(override["caption_length"])
    elif caption_entry is not None and "short" in caption_entry.value.lower():
        eff_caption_len = "short"
    elif "caption_length" in ignored_keys:
        eff_caption_len = "medium"
    else:
        eff_caption_len = voice.caption_length or (
            "short" if "shorter" in voice.adjustments else "medium"
        )
    eff_tone = str(override.get("tone") or pref.taste.tone or voice.formality or "neutral")

    for item in ranked:
        item["editor_defaults"] = _build_editor_defaults_for_move(
            move=item,
            business_name=business_name,
            effective_product=effective_product,
            effective_destination=effective_destination,
            effective_goal=effective_goal,
            effective_context_note=effective_context_note,
            effective_minutes=effective_minutes,
            primary_channel=primary_channel,
            caption_length=eff_caption_len,
            tone=eff_tone,
            avoid_list=avoid_list,
            short_price=short_price,
            is_draft_override=bool(override),
        )

    top = ranked[0] if ranked else None
    what_changed: str | None = None
    if top and previous_top_id and top["id"] != previous_top_id:
        role_note = (
            f" ({_ROLE_LABELS[top['competitor_role']]})" if top.get("competitor_role") else ""
        )
        comp_note = (
            f" driven by {top['competitor_used']}{role_note}" if top.get("competitor_used") else ""
        )
        what_changed = f"Top recommendation changed to “{top['title']}”{comp_note}."
    elif override:
        what_changed = (
            "Ranked using temporary draft-only context (your saved shop defaults were not altered)."
        )

    editor_defaults = (
        dict(top["editor_defaults"])
        if top is not None
        else _build_editor_defaults_for_move(
            move=None,
            business_name=business_name,
            effective_product=effective_product,
            effective_destination=effective_destination,
            effective_goal=effective_goal,
            effective_context_note=effective_context_note,
            effective_minutes=effective_minutes,
            primary_channel=primary_channel,
            caption_length=eff_caption_len,
            tone=eff_tone,
            avoid_list=avoid_list,
            short_price=short_price,
            is_draft_override=bool(override),
        )
    )

    if all_channels_excluded:
        excl_names = ", ".join(c.title() for c in sorted(excluded_channels))
        missing_prompt = (
            f"All available channels are excluded ({excl_names}). "
            "Restore a posting channel in Your context or clear channel exclusions "
            "to generate moves."
        )
    elif not active_comps:
        missing_prompt = (
            "Add your primary channel or one watched competitor to sharper rank your next moves."
        )
    else:
        missing_prompt = ""

    return {
        "recommendations": ranked,
        "what_changed": what_changed,
        "editor_defaults": editor_defaults,
        "excluded_channels": sorted(excluded_channels),
        "all_channels_excluded": all_channels_excluded,
        "missing_info_prompt": missing_prompt,
    }
