"""Keep a competitor and its latest analysis in the seller's workspace.

A finished analysis used to live only in the page: the home saved it with a request the server
refused, so a reload lost it and nothing reached the seller's strategy. This module merges one
competitor into the workspace document instead:

- The competitor is on the watchlist in both places the app reads: `onboarding.competitors` (the
  home's rows) and `preferences.competitor_entries` (seller memory and the move ranker), in the
  same order, so seller memory's row-by-position decoration stays aligned.
- With an analysis, its takeaway becomes the competitor's note (`rationale`, which the ranker
  cites in "why this fits") unless the seller wrote their own note. The seller can edit it on the
  competitor card like any note. The full brief is kept under `briefs[<url>]` for "View analysis".

Pure functions over a document copy; the route in src/api/intel.py loads and saves.
"""

from __future__ import annotations

import json
from typing import Any
from urllib.parse import urlsplit

from src.models.intel import CompetitorBrief
from src.services.competitor_checks import MAX_COMPETITORS_PER_CHECK, normalize_competitor_url

MAX_SAVED_BRIEFS = 12
MAX_BRIEF_JSON_BYTES = 150_000
NOTE_MAX_CHARS = 280
SUMMARY_MAX_CHARS = 600
ADDED_REASON = "Added by you"
# Notes setup wrote for the seller, which an analysis may replace. Anything else is the seller's.
_SETUP_NOTES = {"example", "watched competitor", "added by you"}


def analysis_takeaway(brief: CompetitorBrief) -> str:
    """The brief's summary, cut at a sentence end to fit a 280-character note."""
    text = " ".join(str(brief.summary or "").split())
    if len(text) <= NOTE_MAX_CHARS:
        return text
    cut = text[:NOTE_MAX_CHARS]
    end = max(cut.rfind(". "), cut.rfind("! "), cut.rfind("? "))
    if end >= 80:
        return cut[: end + 1]
    return cut[: NOTE_MAX_CHARS - 1].rstrip() + "…"


def _is_setup_note(entry: dict[str, Any]) -> bool:
    note = str(entry.get("rationale") or "").strip()
    if not note:
        return True
    if note == str(entry.get("reason") or "").strip():
        return True
    if note.lower() in _SETUP_NOTES:
        return True
    # A takeaway from an earlier analysis may be refreshed by a newer one.
    return note == str(entry.get("analysis_takeaway") or "").strip()


def _display_name(name: str, url: str) -> str:
    clean = " ".join(str(name or "").split())[:140]
    if clean:
        return clean
    host = (urlsplit(url).hostname or url).lower()
    return host[4:] if host.startswith("www.") else host


def _brief_json(brief: CompetitorBrief) -> dict[str, Any] | None:
    data = brief.model_dump(mode="json")
    if len(json.dumps(data)) <= MAX_BRIEF_JSON_BYTES:
        return data
    data.pop("research_brief", None)
    return data if len(json.dumps(data)) <= MAX_BRIEF_JSON_BYTES else None


def merge_saved_competitor(
    document: dict[str, Any],
    *,
    url: str,
    name: str = "",
    brief: CompetitorBrief | None = None,
    now_iso: str,
) -> tuple[dict[str, Any], dict[str, Any], bool]:
    """Return `(new_document, competitor_entry, added)` with the competitor saved.

    Raises ValueError when the address is not a website the watchlist can hold.
    """
    raw = str(url or "").strip()
    parts = urlsplit(raw)
    host = parts.hostname or ""
    norm = normalize_competitor_url(raw)
    if parts.scheme not in ("http", "https") or "." not in host or any(c.isspace() for c in raw):
        norm = ""
    if not norm:
        raise ValueError("Use the competitor's website address, like https://their-site.com.")
    doc = dict(document or {})
    onboarding_raw = doc.get("onboarding")
    onboarding = dict(onboarding_raw) if isinstance(onboarding_raw, dict) else None
    prefs_raw = doc.get("preferences")
    prefs = dict(prefs_raw) if isinstance(prefs_raw, dict) else {}

    onb_raw = onboarding.get("competitors") if onboarding is not None else None
    onb_list = (
        [dict(c) for c in onb_raw if isinstance(c, dict)] if isinstance(onb_raw, list) else []
    )
    entries_raw = prefs.get("competitor_entries")
    entries = (
        [dict(e) for e in entries_raw if isinstance(e, dict)]
        if isinstance(entries_raw, list)
        else []
    )
    if not entries and onb_list:
        # Seller memory falls back to setup's list; seed from it so both lists line up.
        for c in onb_list:
            reason = str(c.get("reason") or "")[:280]
            entries.append(
                {
                    "name": str(c.get("name") or "")[:140],
                    "url": str(c.get("url") or "")[:500],
                    "role": "similar_audience",
                    "rationale": reason,
                    "reason": reason,
                    "selected": c.get("selected", True) is not False,
                }
            )

    def same(item: dict[str, Any]) -> bool:
        return normalize_competitor_url(str(item.get("url") or "")) == norm

    added = False
    entry = next((e for e in entries if same(e)), None)
    if entry is None:
        watched = sum(1 for e in entries if e.get("selected", True) is not False)
        entry = {
            "name": _display_name(name, url),
            "url": url.strip()[:500],
            "role": "similar_audience",
            "rationale": "",
            "reason": ADDED_REASON,
            "selected": watched < MAX_COMPETITORS_PER_CHECK,
        }
        entries.append(entry)
        added = True
    if onboarding is not None and not any(same(c) for c in onb_list):
        onb_list.append(
            {
                "name": entry["name"],
                "url": entry["url"],
                "reason": str(entry.get("reason") or ADDED_REASON),
                "selected": entry.get("selected", True) is not False,
            }
        )

    if brief is not None:
        takeaway = analysis_takeaway(brief)
        if takeaway:
            if _is_setup_note(entry):
                entry["rationale"] = takeaway
            entry["analysis_takeaway"] = takeaway
            entry["analysis_summary"] = " ".join(str(brief.summary or "").split())[
                :SUMMARY_MAX_CHARS
            ]
            entry["analyzed_at"] = now_iso
        stored = _brief_json(brief)
        if stored is not None:
            briefs_raw = doc.get("briefs")
            briefs = dict(briefs_raw) if isinstance(briefs_raw, dict) else {}
            briefs.pop(url, None)
            briefs[url] = stored
            while len(briefs) > MAX_SAVED_BRIEFS:
                briefs.pop(next(iter(briefs)))
            doc["briefs"] = briefs

    prefs["competitor_entries"] = entries
    doc["preferences"] = prefs
    if onboarding is not None:
        onboarding["competitors"] = onb_list
        doc["onboarding"] = onboarding
    return doc, entry, added
