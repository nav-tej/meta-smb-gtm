"""Seller Memory & Scan-to-Recommendation routes (PRD Section 12, Batch 1)."""

from __future__ import annotations

import base64
import binascii
from datetime import UTC, datetime
from typing import Annotated, Any, Literal
from urllib.parse import urlparse

from fastapi import APIRouter, Header, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from src.api.demo import LiveMode, demo_unavailable
from src.clients.meta import MetaAPIError, get_meta_client
from src.models.seller import (
    CompetitorEntry,
    DismissSignal,
    SellerMemoryEntry,
    SellerPreferences,
)
from src.models.voice import VoiceProfile
from src.services.accounts import (
    AccountSession,
    load_workspace,
    resolve_account,
    save_workspace,
    verify_workspace_owner,
)
from src.services.competitor_intel import collect_entries
from src.services.seller_memory import (
    DEMO_VOICE_FIXTURES,
    compute_rescan_diff,
    extract_scan_proposals,
    forget_memory_entry,
    merge_entries_into_preferences,
    parse_context_to_proposals,
    rank_seller_recommendations,
    respond_to_suggestion,
    suggest_memory_updates,
)
from src.services.social_extract import extract_social_handles
from src.utils.sitemap import SitemapError

router = APIRouter(prefix="/seller-memory", tags=["seller-memory"])


class ScanShopRequest(BaseModel):
    business_name: str = Field(default="Your Shop", max_length=160)
    website_url: str = Field(default="", max_length=500)
    extra_urls: list[str] = Field(default_factory=list, max_length=10)
    max_urls_per_source: int = Field(default=25, ge=5, le=100)
    existing_entries: list[SellerMemoryEntry] = Field(default_factory=list)
    snapshot_items: list[dict[str, Any]] = Field(default_factory=list, max_length=30)


class InterpretContextRequest(BaseModel):
    text: str = Field(default="", max_length=2000)
    source_type: Literal["typed", "voice_demo_fixture", "voice_approved_transcript"] = "typed"
    fixture_id: str | None = Field(default=None, max_length=80)
    existing_entries: list[SellerMemoryEntry] = Field(default_factory=list)
    product_key: str | None = Field(default=None, max_length=120)
    destination: str | None = Field(default=None, max_length=80)


class SaveSellerMemoryRequest(BaseModel):
    expected_version: int | None = None
    expected_owner: str | None = None
    preferences: SellerPreferences | None = None
    voice_profile: VoiceProfile | None = None
    memory_entries: list[SellerMemoryEntry] | None = None
    competitor_entries: list[CompetitorEntry] | None = None


class RecommendRequest(BaseModel):
    business_name: str = Field(default="Your Studio", max_length=160)
    product_name: str | None = Field(default=None, max_length=180)
    preferences: SellerPreferences | None = None
    voice_profile: VoiceProfile | None = None
    competitor_entries: list[CompetitorEntry] | None = None
    draft_override: dict[str, Any] | None = None
    dismiss_signals: list[DismissSignal] = Field(default_factory=list)
    previous_top_id: str | None = Field(default=None, max_length=120)


class SuggestionRespondRequest(BaseModel):
    decision: Literal["approve", "dismiss"]
    expected_owner: str | None = None


class VoiceTranscribeRequest(BaseModel):
    audio_base64: str = Field(min_length=4)
    filename: str = Field(default="voice_note.webm", max_length=120)
    consent_confirmed: bool = False


def _extract_profile_parts(
    doc: dict[str, Any],
) -> tuple[SellerPreferences, VoiceProfile, list[CompetitorEntry], list[DismissSignal]]:
    raw_pref = doc.get("preferences")
    pref = (
        SellerPreferences.model_validate(raw_pref)
        if isinstance(raw_pref, dict)
        else SellerPreferences()
    )
    raw_voice = doc.get("voice_profile")
    voice = (
        VoiceProfile.model_validate(raw_voice) if isinstance(raw_voice, dict) else VoiceProfile()
    )

    comps: list[CompetitorEntry] = list(pref.competitor_entries)
    if not comps:
        onb = doc.get("onboarding")
        raw_comps = onb.get("competitors") if isinstance(onb, dict) else None
        if isinstance(raw_comps, list):
            for c in raw_comps:
                if isinstance(c, dict) and c.get("url"):
                    role = c.get("role")
                    if role not in {"similar_audience", "price_reference", "inspiration"}:
                        role = "similar_audience"
                    comps.append(
                        CompetitorEntry(
                            name=str(c.get("name") or "")[:140],
                            url=str(c.get("url"))[:500],
                            role=role,
                            rationale=str(c.get("rationale") or c.get("reason") or "")[:280],
                            reason=str(c.get("reason") or c.get("rationale") or "")[:280],
                            selected=c.get("selected", True) is not False,
                        )
                    )

    raw_signals = doc.get("dismiss_signals") or []
    signals: list[DismissSignal] = []
    if isinstance(raw_signals, list):
        for s in raw_signals:
            if isinstance(s, dict):
                try:
                    signals.append(DismissSignal.model_validate(s))
                except Exception:
                    continue
    return pref, voice, comps, signals


async def _load_account_state(
    account: AccountSession,
) -> tuple[
    dict[str, Any],
    SellerPreferences,
    VoiceProfile,
    list[CompetitorEntry],
    list[DismissSignal],
]:
    ws = await load_workspace(account)
    doc = dict(ws.get("document") or {})
    pref, voice, comps, signals = _extract_profile_parts(doc)
    return ws, pref, voice, comps, signals


@router.get("")
async def get_seller_memory(
    request: Request,
    response: Response,
    x_muse_owner: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    """Return owner-bound seller memory, voice profile, competitors, and pending suggestions."""
    response.headers["Cache-Control"] = "no-store"
    account = await resolve_account(request, response, require_verified=False)
    if account is None:
        return {
            "authenticated": False,
            "owner_id": None,
            "version": 0,
            "business_name": "",
            "preferences": SellerPreferences().model_dump(mode="json"),
            "voice_profile": VoiceProfile().model_dump(mode="json"),
            "memory_entries": [],
            "competitor_entries": [],
            "suggested_updates": [],
            "dismiss_signals": [],
        }

    verify_workspace_owner(account, x_muse_owner)
    ws, pref, voice, comps, signals = await _load_account_state(account)
    doc = ws.get("document") or {}
    onb = doc.get("onboarding") if isinstance(doc, dict) else None
    biz_name = str(onb.get("business_name") or "") if isinstance(onb, dict) else ""

    suggestions = suggest_memory_updates(
        preferences=pref, voice_profile=voice, dismiss_signals=signals
    )
    pref.suggested_updates = suggestions

    return {
        "authenticated": True,
        "owner_id": account.user_id,
        "version": int(ws.get("version") or 0),
        "business_name": biz_name,
        "preferences": pref.model_dump(mode="json"),
        "voice_profile": voice.model_dump(mode="json"),
        "memory_entries": [e.model_dump(mode="json") for e in pref.memory_entries],
        "competitor_entries": [c.model_dump(mode="json") for c in comps],
        "suggested_updates": [
            s.model_dump(mode="json") for s in suggestions if s.status == "pending"
        ],
        "dismiss_signals": [s.model_dump(mode="json") for s in signals],
    }


@router.put("")
async def save_seller_memory(
    body: SaveSellerMemoryRequest,
    request: Request,
    response: Response,
    x_muse_owner: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    """Persist reviewed seller memory, voice profile, and competitor roles safely."""
    response.headers["Cache-Control"] = "no-store"
    account = await resolve_account(request, response, require_verified=True)
    assert account is not None
    verify_workspace_owner(account, x_muse_owner, body.expected_owner, require_binding=True)

    ws, cur_pref, cur_voice, cur_comps, signals = await _load_account_state(account)
    ws_version = int(ws.get("version") or 0)

    if body.expected_version is not None and body.expected_version != ws_version:
        return JSONResponse(
            status_code=409,
            content={
                "detail": (
                    "Your seller memory was updated in another browser or tab. "
                    "Review both versions before saving."
                ),
                "server_version": ws_version,
                "server_preferences": cur_pref.model_dump(mode="json"),
                "server_voice_profile": cur_voice.model_dump(mode="json"),
                "server_memory_entries": [
                    e.model_dump(mode="json") for e in cur_pref.memory_entries
                ],
                "server_competitor_entries": [c.model_dump(mode="json") for c in cur_comps],
            },
        )

    next_pref = body.preferences.model_copy(deep=True) if body.preferences else cur_pref
    next_voice = body.voice_profile.model_copy(deep=True) if body.voice_profile else cur_voice

    if body.memory_entries is not None:
        # Replace accepted entries explicitly reviewed while keeping dismissed filter clean
        next_pref.memory_entries = []
        next_pref, next_voice = merge_entries_into_preferences(
            next_pref, body.memory_entries, next_voice
        )

    if body.competitor_entries is not None:
        next_pref.competitor_entries = body.competitor_entries
        next_pref.watch = [c.url for c in body.competitor_entries if c.selected]
    elif not next_pref.competitor_entries and cur_comps:
        next_pref.competitor_entries = cur_comps

    doc = dict(ws.get("document") or {})
    doc["preferences"] = next_pref.model_dump(mode="json")
    doc["voice_profile"] = next_voice.model_dump(mode="json")

    if isinstance(doc.get("onboarding"), dict) and body.competitor_entries is not None:
        onb_copy = dict(doc["onboarding"])
        onb_copy["competitors"] = [c.model_dump(mode="json") for c in body.competitor_entries]
        doc["onboarding"] = onb_copy

    saved = await save_workspace(
        account,
        doc,
        expected_version=ws.get("version"),
        expected_owner=account.user_id,
    )
    return {
        "success": True,
        "owner_id": account.user_id,
        "version": int(saved.get("version") or ws_version + 1),
        "preferences": next_pref.model_dump(mode="json"),
        "voice_profile": next_voice.model_dump(mode="json"),
        "memory_entries": [e.model_dump(mode="json") for e in next_pref.memory_entries],
        "competitor_entries": [c.model_dump(mode="json") for c in next_pref.competitor_entries],
        "suggested_updates": [
            s.model_dump(mode="json")
            for s in suggest_memory_updates(
                preferences=next_pref, voice_profile=next_voice, dismiss_signals=signals
            )
            if s.status == "pending"
        ],
    }


@router.delete("/entries/{entry_id}")
async def delete_memory_entry(
    entry_id: str,
    request: Request,
    response: Response,
    x_muse_owner: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    """Forget/delete one memory entry so it stops shaping future recommendations."""
    response.headers["Cache-Control"] = "no-store"
    account = await resolve_account(request, response, require_verified=True)
    assert account is not None
    verify_workspace_owner(account, x_muse_owner, require_binding=True)

    ws, cur_pref, cur_voice, cur_comps, _signals = await _load_account_state(account)
    next_pref, next_voice, removed = forget_memory_entry(cur_pref, cur_voice, entry_id)
    if not removed:
        raise HTTPException(404, f"Memory entry '{entry_id}' was not found.")

    doc = dict(ws.get("document") or {})
    doc["preferences"] = next_pref.model_dump(mode="json")
    doc["voice_profile"] = next_voice.model_dump(mode="json")

    saved = await save_workspace(
        account,
        doc,
        expected_version=ws.get("version"),
        expected_owner=account.user_id,
    )
    return {
        "success": True,
        "deleted_entry_id": entry_id,
        "version": int(saved.get("version") or 0),
        "preferences": next_pref.model_dump(mode="json"),
        "voice_profile": next_voice.model_dump(mode="json"),
        "memory_entries": [e.model_dump(mode="json") for e in next_pref.memory_entries],
        "competitor_entries": [c.model_dump(mode="json") for c in cur_comps],
    }


@router.post("/scan")
async def scan_shop_baseline(
    body: ScanShopRequest,
    request: Request,
    response: Response,
    x_muse_owner: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    """Scan public storefront/portfolio/product pages or snapshot into a reviewable baseline."""
    response.headers["Cache-Control"] = "no-store"
    sources: list[tuple[str, str]] = []
    if body.website_url.strip():
        sources.append(("storefront", body.website_url.strip()))
    for extra in body.extra_urls:
        if extra.strip():
            sources.append(("extra", extra.strip()))

    channel_results: list[dict[str, Any]] = []
    discovered_items: list[dict[str, Any]] = []
    price_hints: list[str] = []

    if body.snapshot_items:
        for item in body.snapshot_items:
            if not isinstance(item, dict):
                continue
            title = str(item.get("title") or "").strip()
            url = str(item.get("url") or body.website_url or "").strip()
            hint = str(item.get("price_hint") or "").strip()
            if hint and hint not in price_hints:
                price_hints.append(hint)
            discovered_items.append(
                {
                    "url": url,
                    "title": title,
                    "bucket": str(item.get("bucket") or "products"),
                    "price_hint": hint or None,
                }
            )
        if body.website_url.strip():
            channel_results.append(
                {
                    "kind": "snapshot",
                    "url": body.website_url.strip(),
                    "host": (urlparse(body.website_url.strip()).hostname or "").lower(),
                    "status": "fetched",
                    "pages_found": len(discovered_items),
                    "note": "Loaded from saved public shop snapshot (0 runs).",
                }
            )
    else:
        for kind, raw_url in sources:
            normalized = raw_url if "://" in raw_url else f"https://{raw_url.lstrip('@')}"
            host = (urlparse(normalized).hostname or "").lower()
            if any(
                blocked in host
                for blocked in ("instagram.com", "facebook.com", "saatchiart.com", "etsy.com")
            ):
                channel_results.append(
                    {
                        "kind": kind,
                        "url": normalized,
                        "host": host,
                        "status": "vision_or_manual",
                        "pages_found": 0,
                        "note": (
                            f"{host} blocks automated crawlers. Enter your details manually or "
                            "paste another public page."
                        ),
                    }
                )
                continue

            try:
                entries, _sitemaps = await collect_entries(
                    normalized,
                    fetch_titles=True,
                    max_urls=body.max_urls_per_source,
                    max_title_fetches=12,
                )
                channel_results.append(
                    {
                        "kind": kind,
                        "url": normalized,
                        "host": host,
                        "status": "fetched",
                        "pages_found": len(entries),
                        "note": f"Scanned {len(entries)} public page(s) on {host}.",
                    }
                )
                for entry in entries[:15]:
                    if entry.price_hint and entry.price_hint not in price_hints:
                        price_hints.append(entry.price_hint)
                    discovered_items.append(
                        {
                            "url": entry.loc,
                            "title": entry.title or entry.loc.rsplit("/", 1)[-1],
                            "bucket": entry.bucket,
                            "price_hint": entry.price_hint,
                        }
                    )
            except SitemapError as err:
                channel_results.append(
                    {
                        "kind": kind,
                        "url": normalized,
                        "host": host,
                        "status": "vision_or_manual",
                        "pages_found": 0,
                        "note": str(err),
                    }
                )

    suggested_socials = extract_social_handles(
        {"social_urls": [], "channels": channel_results, "items": discovered_items}
    )
    scan_result = extract_scan_proposals(
        business_name=body.business_name,
        primary_url=body.website_url.strip(),
        channel_results=channel_results,
        discovered_items=discovered_items,
        detected_price_hints=price_hints,
        suggested_socials=suggested_socials,
    )

    existing_entries = list(body.existing_entries)
    account = await resolve_account(request, response, require_verified=False)
    if account is not None and not existing_entries:
        verify_workspace_owner(account, x_muse_owner)
        try:
            _ws, pref, _v, _c, _s = await _load_account_state(account)
            existing_entries = pref.memory_entries
        except Exception:
            pass

    diff_data = (
        compute_rescan_diff(existing_entries, scan_result["proposed_entries"])
        if existing_entries
        else {"diff": [], "preserved_edits_count": 0}
    )

    return {
        "business_name": scan_result["business_name"],
        "scan_date": scan_result["scan_date"],
        "source_url": scan_result["source_url"],
        "channels": channel_results,
        "discovered_catalog_items": discovered_items[:24],
        "detected_price_hints": price_hints,
        "suggested_socials": suggested_socials,
        "partial_warnings": scan_result["partial_warnings"],
        "proposed_entries": [e.model_dump(mode="json") for e in scan_result["proposed_entries"]],
        "missing_questions": scan_result["missing_questions"],
        "diff": [d.model_dump(mode="json") for d in diff_data["diff"]],
        "preserved_edits_count": diff_data["preserved_edits_count"],
        "runs_used": 0,
    }


@router.get("/voice-fixtures")
async def list_voice_fixtures() -> dict[str, Any]:
    """Return clearly labeled demo voice transcripts (0 model calls, 0 runs)."""
    return {"fixtures": list(DEMO_VOICE_FIXTURES.values())}


@router.post("/voice/transcribe")
async def transcribe_consented_voice(
    body: VoiceTranscribeRequest, live: LiveMode
) -> dict[str, str]:
    """Consent-gated voice transcription returning an unapproved transcript for review only."""
    if not body.consent_confirmed:
        raise HTTPException(
            400,
            "Explicit consent is required before sending your voice recording for transcription.",
        )
    if not live:
        raise demo_unavailable("Live voice transcription")
    raw = body.audio_base64.strip()
    if "," in raw and raw.startswith("data:"):
        raw = raw.split(",", 1)[1]
    try:
        audio_bytes = base64.b64decode(raw, validate=True)
    except binascii.Error as err:
        raise MetaAPIError("Upload the voice note again: the audio data was not valid.") from err
    transcript = await get_meta_client().transcribe_audio(audio_bytes, filename=body.filename)
    return {
        "transcript": transcript,
        "model": "muse-voice-transcribe-1.0",
        "saved_to_memory": "false",
    }


@router.post("/interpret")
async def interpret_context(
    body: InterpretContextRequest,
    request: Request,
    response: Response,
    x_muse_owner: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    """Turn free text or an approved/fixture voice transcript into reviewable memory items."""
    response.headers["Cache-Control"] = "no-store"
    existing_entries = list(body.existing_entries)
    pref: SellerPreferences | None = None

    account = await resolve_account(request, response, require_verified=False)
    if account is not None:
        verify_workspace_owner(account, x_muse_owner)
        try:
            _ws, pref, _v, _c, _s = await _load_account_state(account)
            if not existing_entries:
                existing_entries = pref.memory_entries
        except Exception:
            pass

    parsed = parse_context_to_proposals(
        body.text,
        source_type=body.source_type,
        fixture_id=body.fixture_id,
        existing_entries=existing_entries,
        preferences=pref,
        product_key=body.product_key,
        destination=body.destination,
    )
    return {
        "transcript": parsed["transcript"],
        "source_type": parsed["source_type"],
        "fixture": parsed["fixture"],
        "proposed_entries": [e.model_dump(mode="json") for e in parsed["proposed_entries"]],
        "conflicts": parsed["conflicts"],
        "unclear": parsed["unclear"],
        "runs_used": 0,
    }


@router.post("/suggestions/evaluate")
async def evaluate_suggestions(
    request: Request,
    response: Response,
    x_muse_owner: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    """Evaluate repeated dismiss/feedback signals without auto-modifying accepted memory."""
    response.headers["Cache-Control"] = "no-store"
    account = await resolve_account(request, response, require_verified=True)
    assert account is not None
    verify_workspace_owner(account, x_muse_owner)

    ws, pref, voice, _comps, signals = await _load_account_state(account)
    suggestions = suggest_memory_updates(
        preferences=pref, voice_profile=voice, dismiss_signals=signals
    )
    if [s.model_dump(mode="json") for s in suggestions] != [
        s.model_dump(mode="json") for s in pref.suggested_updates
    ]:
        pref.suggested_updates = suggestions
        doc = dict(ws.get("document") or {})
        doc["preferences"] = pref.model_dump(mode="json")
        await save_workspace(
            account,
            doc,
            expected_version=ws.get("version"),
            expected_owner=account.user_id,
        )
    pending = [s.model_dump(mode="json") for s in suggestions if s.status == "pending"]
    return {"suggested_updates": pending, "pending_count": len(pending)}


@router.post("/suggestions/{suggestion_id}/respond")
async def respond_suggestion(
    suggestion_id: str,
    body: SuggestionRespondRequest,
    request: Request,
    response: Response,
    x_muse_owner: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    """Explicitly approve or dismiss a suggested memory update."""
    response.headers["Cache-Control"] = "no-store"
    account = await resolve_account(request, response, require_verified=True)
    assert account is not None
    verify_workspace_owner(account, x_muse_owner, body.expected_owner, require_binding=True)

    ws, cur_pref, cur_voice, cur_comps, signals = await _load_account_state(account)
    cur_pref.suggested_updates = suggest_memory_updates(
        preferences=cur_pref, voice_profile=cur_voice, dismiss_signals=signals
    )
    next_pref, next_voice, handled = respond_to_suggestion(
        preferences=cur_pref,
        voice_profile=cur_voice,
        suggestion_id=suggestion_id,
        decision=body.decision,
    )
    if handled is None:
        raise HTTPException(404, f"Suggested update '{suggestion_id}' was not found.")

    doc = dict(ws.get("document") or {})
    doc["preferences"] = next_pref.model_dump(mode="json")
    doc["voice_profile"] = next_voice.model_dump(mode="json")
    saved = await save_workspace(
        account,
        doc,
        expected_version=ws.get("version"),
        expected_owner=account.user_id,
    )
    return {
        "success": True,
        "decision": body.decision,
        "suggestion": handled.model_dump(mode="json"),
        "version": int(saved.get("version") or 0),
        "preferences": next_pref.model_dump(mode="json"),
        "voice_profile": next_voice.model_dump(mode="json"),
        "memory_entries": [e.model_dump(mode="json") for e in next_pref.memory_entries],
        "competitor_entries": [c.model_dump(mode="json") for c in cur_comps],
        "suggested_updates": [
            s.model_dump(mode="json") for s in next_pref.suggested_updates if s.status == "pending"
        ],
    }


@router.post("/recommend")
async def recommend_for_context(
    body: RecommendRequest,
    request: Request,
    response: Response,
    x_muse_owner: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    """Zero-run deterministic recommendation ranker honoring competitor roles & context."""
    response.headers["Cache-Control"] = "no-store"
    pref = body.preferences
    voice = body.voice_profile
    comps = body.competitor_entries
    signals = list(body.dismiss_signals)
    biz_name = body.business_name

    if pref is None or comps is None:
        account = await resolve_account(request, response, require_verified=False)
        if account is not None:
            verify_workspace_owner(account, x_muse_owner)
            try:
                ws, ws_pref, ws_voice, ws_comps, ws_signals = await _load_account_state(account)
                if pref is None:
                    pref = ws_pref
                if voice is None:
                    voice = ws_voice
                if comps is None:
                    comps = ws_comps
                if not signals:
                    signals = ws_signals
                onb = (ws.get("document") or {}).get("onboarding")
                if isinstance(onb, dict) and onb.get("business_name") and biz_name == "Your Studio":
                    biz_name = str(onb["business_name"])
            except Exception:
                pass

    return {
        **rank_seller_recommendations(
            business_name=biz_name,
            product_name=body.product_name,
            preferences=pref,
            voice_profile=voice,
            competitor_entries=comps,
            draft_override=body.draft_override,
            dismiss_signals=signals,
            previous_top_id=body.previous_top_id,
        ),
        "generated_at": datetime.now(UTC).isoformat(),
        "runs_used": 0,
    }
