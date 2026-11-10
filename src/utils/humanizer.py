"""Deterministic humanizer linter and text cleaner for seller content.

Adheres to https://github.com/blader/humanizer guidelines with lint-and-suggest design:
1. Keeps original text; generates non-destructive suggestions for seller review.
2. Never touches quoted titles, product names (e.g. woven tapestry), or proper nouns.
3. Preserves paragraph structure and formatting (newlines).
4. Replaces em dashes (—) with commas or colons.
5. Flags stock AI fluff words (delve, a tapestry of, embark, testament, nestled, unleash, etc.).
6. Flags inflated ungrounded claims (award-winning, revolutionary, #1, world-renowned).
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

# Regex matching em dashes with or without horizontal spaces
EM_DASH_RE = re.compile(r"[ \t]*—[ \t]*")

# Regex for rule-of-three: "word, word, and word"
RULE_OF_THREE_RE = re.compile(r"\b([a-z]+),\s+([a-z]+),\s+and\s+([a-z]+)\b", re.IGNORECASE)

# Patterns identifying protected titles and product names that must not be edited
QUOTED_TEXT_RE = re.compile(r'["“\'‘][^"”\'’\n]+["”\'’]')
TITLED_PHRASE_RE = re.compile(
    r"(?i:\b(?:the\s+)?title\s+(?:of\s+(?:this\s+)?[a-z]+\s+)?is\s+)([A-Z][A-Za-z0-9_\s]+?)(?=[.,;!?]|$)"
)
TITLED_VERB_RE = re.compile(
    r"(?i:\btitled\s+(?:(?:this\s+)?[a-z]+\s+)?)([A-Z][A-Za-z0-9_\s]+?)(?=[.,;!?]|$)"
)
PRODUCT_TAPESTRY_RE = re.compile(
    r"\b(?:(?:handwoven|woven|wool|cotton|wall|vintage|macrame|fiber|silk|textile)\s+)?tapestr(?:y|ies)\b(?!\s+of\b)",
    re.IGNORECASE,
)


@dataclass
class HumanizerReport:
    passed: bool
    violations: list[str] = field(default_factory=list)
    original_text: str = ""
    suggested_text: str = ""
    cleaned_text: str = ""


def _match_case(template: str, replacement: str) -> str:
    """Match the case of template (all caps, title case, or lowercase)."""
    if template.isupper():
        return replacement.upper()
    if template and template[0].isupper():
        return replacement[0].upper() + replacement[1:]
    return replacement


def _protect_spans(text: str) -> tuple[str, list[str]]:
    """Extract and mask protected entities (quotes, artwork titles, product names)."""
    protected: list[str] = []

    def save_span(match: re.Match[str]) -> str:
        val = match.group(0)
        idx = len(protected)
        protected.append(val)
        return f"__MUSE_PROT_{idx}__"

    masked = text

    # 1. Protect quoted titles/phrases
    masked = QUOTED_TEXT_RE.sub(save_span, masked)

    # 2. Protect titles following "title of this ... is X" or "titled X"
    def save_title(match: re.Match[str]) -> str:
        lead = match.group(0)[: match.start(1) - match.start(0)]
        title_val = match.group(1).rstrip()
        trailing = match.group(1)[len(title_val) :]
        idx = len(protected)
        protected.append(title_val)
        return f"{lead}__MUSE_PROT_{idx}__{trailing}"

    masked = TITLED_PHRASE_RE.sub(save_title, masked)
    masked = TITLED_VERB_RE.sub(save_title, masked)

    # 3. Protect physical product mentions of "tapestry"
    masked = PRODUCT_TAPESTRY_RE.sub(save_span, masked)

    return masked, protected


def _restore_spans(text: str, protected: list[str]) -> str:
    """Restore protected spans back into the text."""
    restored = text
    for idx, orig in enumerate(protected):
        restored = restored.replace(f"__MUSE_PROT_{idx}__", orig)
    return restored


def lint_text(text: str) -> HumanizerReport:
    """Audit text against the humanizer pattern list and return violations and suggestions."""
    violations: list[str] = []
    masked, _ = _protect_spans(text)

    if "—" in text:
        violations.append("Contains em dash (—); use commas, parentheses, or periods instead.")

    lower_masked = masked.lower()
    for word in sorted(BANNED_AI_WORDS):
        if re.search(rf"\b{re.escape(word)}\b", lower_masked):
            violations.append(f"Contains stock AI buzzword: '{word}'.")

    for claim in sorted(INFLATED_CLAIMS):
        if re.search(rf"\b{re.escape(claim)}\b", lower_masked):
            violations.append(f"Contains inflated claim: '{claim}'.")

    matches = RULE_OF_THREE_RE.findall(masked)
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

    suggestion = clean_text(text)
    return HumanizerReport(
        passed=len(violations) == 0,
        violations=violations,
        original_text=text,
        suggested_text=suggestion,
        cleaned_text=suggestion,
    )


def clean_text(text: str) -> str:
    """Generate suggested text, preserving quoted titles, product names, and formatting."""
    masked, protected = _protect_spans(text)

    # 1. Replace em dashes with comma
    cleaned = EM_DASH_RE.sub(", ", masked)

    # 2. Replace stock AI words with plain alternatives while preserving case
    replacements = [
        (r"\bdelve into\b", "explore"),
        (r"\bdelve\b", "look"),
        (r"\b(?:a|the|this)?\s*(?:[a-z]+\s+)?tapestry\s+of\b", "a collection of"),
        (r"\bembark on\b", "start"),
        (r"\bstands as a testament to\b", "reflects"),
        (r"\ba testament to\b", "a reflection of"),
        (r"\bnestled in\b", "in"),
        (r"\bunleash your\b", "discover your"),
        (r"\bunleash\b", "share"),
        (r"\belevate your\b", "improve your"),
        (r"\belevate\b", "lift"),
        (r"\ba beacon of\b", "a symbol of"),
        (r"\ba game-changer for\b", "a big help for"),
        (r"\ba plethora of\b", "many"),
        (r"\bbespoke\b", "custom"),
    ]

    for pat, rep in replacements:

        def replace_with_case(match: re.Match[str], repl: str = rep) -> str:
            return _match_case(match.group(0), repl)

        cleaned = re.sub(pat, replace_with_case, cleaned, flags=re.IGNORECASE)

    # 3. Strip inflated claims outside of proper nouns/titles (which are already masked)
    for claim in INFLATED_CLAIMS:
        cleaned = re.sub(rf"\b{re.escape(claim)}\b\s*", "", cleaned, flags=re.IGNORECASE)

    # 4. Clean up punctuation and spacing while strictly preserving newlines!
    # Normalize per-line spacing without collapsing paragraphs
    lines = cleaned.split("\n")
    cleaned_lines = []
    for line in lines:
        line_clean = re.sub(r"[ \t]+", " ", line)
        line_clean = re.sub(r"\s+,", ",", line_clean)
        line_clean = re.sub(r",\s*,", ",", line_clean)
        cleaned_lines.append(line_clean.strip())

    cleaned = "\n".join(cleaned_lines)
    return _restore_spans(cleaned, protected)
