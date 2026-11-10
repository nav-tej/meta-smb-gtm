"""Deterministic humanizer linter and text cleaner for seller content.

Adheres to https://github.com/blader/humanizer guidelines:
1. No em dashes (—); replace with comma or dash.
2. No stock AI fluff words (delve, tapestry, embark, testament, nestled, unleash, etc.).
3. No rule-of-three padding ("X, Y, and Z" abstract trios).
4. No inflated ungrounded claims (award-winning, revolutionary, #1, world-renowned).
5. Short, plain, authentic sentences.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

BANNED_AI_WORDS = {
    "delve",
    "delving",
    "tapestry",
    "embark",
    "testament",
    "nestled",
    "unleash",
    "unleashing",
    "elevate",
    "elevating",
    "beacon",
    "game-changer",
    "gamechanger",
    "symphony",
    "plethora",
    "pinnacle",
    "foster",
    "intertwined",
    "bespoke",
}

INFLATED_CLAIMS = {
    "award-winning",
    "revolutionary",
    "world-renowned",
    "unrivaled",
    "peerless",
    "miraculous",
}

# Regex matching em dashes with or without spaces
EM_DASH_RE = re.compile(r"\s*—\s*")

# Regex for rule-of-three: "word, word, and word"
RULE_OF_THREE_RE = re.compile(r"\b([a-z]+),\s+([a-z]+),\s+and\s+([a-z]+)\b", re.IGNORECASE)


@dataclass
class HumanizerReport:
    passed: bool
    violations: list[str] = field(default_factory=list)
    cleaned_text: str = ""


def lint_text(text: str) -> HumanizerReport:
    """Audit text against the humanizer pattern list and return violations."""
    violations: list[str] = []

    if "—" in text:
        violations.append("Contains em dash (—); use commas, parentheses, or periods instead.")

    lower_text = text.lower()
    for word in sorted(BANNED_AI_WORDS):
        if re.search(rf"\b{re.escape(word)}\b", lower_text):
            violations.append(f"Contains stock AI buzzword: '{word}'.")

    for claim in sorted(INFLATED_CLAIMS):
        if re.search(rf"\b{re.escape(claim)}\b", lower_text):
            violations.append(f"Contains inflated claim: '{claim}'.")

    matches = RULE_OF_THREE_RE.findall(text)
    if matches:
        for m in matches:
            trio = f"{m[0]}, {m[1]}, and {m[2]}"
            violations.append(f"Contains suspected rule-of-three padding: '{trio}'.")

    # Flag sentences exceeding 28 words
    sentences = re.split(r"[.!?]+", text)
    for s in sentences:
        words = s.strip().split()
        if len(words) > 28:
            violations.append(f"Sentence is too long ({len(words)} words): '{s[:40]}...'.")

    cleaned = clean_text(text)
    return HumanizerReport(
        passed=len(violations) == 0,
        violations=violations,
        cleaned_text=cleaned,
    )


def clean_text(text: str) -> str:
    """Deterministically clean up text to pass the humanizer lint."""
    # 1. Replace em dashes with comma or hyphen
    cleaned = EM_DASH_RE.sub(", ", text)

    # 2. Replace stock AI words with plain alternatives
    replacements = {
        r"\bdelve into\b": "explore",
        r"\bdelve\b": "look",
        r"\ba tapestry of\b": "a collection of",
        r"\btapestry\b": "blend",
        r"\bembark on\b": "start",
        r"\bstands as a testament to\b": "reflects",
        r"\ba testament to\b": "a reflection of",
        r"\bnestled in\b": "in",
        r"\bunleash your\b": "discover your",
        r"\bunleash\b": "share",
        r"\belevate your\b": "improve your",
        r"\belevate\b": "lift",
        r"\ba beacon of\b": "a symbol of",
        r"\ba game-changer for\b": "a big help for",
        r"\ba plethora of\b": "many",
        r"\bbespoke\b": "custom",
    }
    for pat, rep in replacements.items():
        cleaned = re.sub(pat, rep, cleaned, flags=re.IGNORECASE)

    # 3. Strip inflated claims
    for claim in INFLATED_CLAIMS:
        cleaned = re.sub(rf"\b{re.escape(claim)}\b\s*", "", cleaned, flags=re.IGNORECASE)

    # 4. Clean up any double spaces or awkward comma spacing
    cleaned = re.sub(r"\s+", " ", cleaned)
    cleaned = re.sub(r"\s+,", ",", cleaned)
    cleaned = re.sub(r",\s*,", ",", cleaned)

    return cleaned.strip()
