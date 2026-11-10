"""Track J: Seller Voice Profile extraction, similarity checking, and humanizer cleaning."""

from __future__ import annotations

import re
from collections import Counter

from src.models.voice import FormalityLevel, VoiceAdjustment, VoiceProfile
from src.utils.humanizer import BANNED_AI_WORDS, clean_text

# Common stopwords to exclude from recurring vocabulary
_STOPWORDS = frozenset(
    {
        "the", "a", "an", "and", "or", "in", "on", "at", "to", "for", "with", "by", "from",
        "of", "is", "are", "was", "were", "it", "this", "that", "my", "your", "our", "their",
        "i", "we", "you", "me", "us", "be", "been", "have", "has", "had", "do", "does", "did",
        "but", "so", "if", "as", "about", "into", "through", "after", "over", "between", "out",
    }
)  # fmt: skip

_EMOJI_RE = re.compile(
    r"[\U00010000-\U0010ffff\u2600-\u27bf\u2300-\u23ff\u2b50\u200d\ufe0f]",
    re.UNICODE,
)
_HASHTAG_RE = re.compile(r"#\w+", re.UNICODE)


def _split_sentences(text: str) -> list[str]:
    """Split text into individual sentences, stripping excess whitespace."""
    raw = re.split(r"(?<=[.!?])\s+|\n+", text)
    return [s.strip() for s in raw if s.strip()]


def _tokenize(text: str) -> list[str]:
    """Extract lowercased word tokens."""
    return re.findall(r"\b[a-z]{3,}\b", text.lower())


def check_inspiration_similarity(
    candidate_text: str,
    inspiration_texts: list[str],
    threshold: float = 0.5,
) -> tuple[bool, str | None]:
    """Check whether candidate copy copies or closely mimics any sentence from inspiration text.

    Returns:
        (is_plagiarized, matching_inspiration_sentence_or_none)
    """
    if not candidate_text or not inspiration_texts:
        return False, None

    candidate_sentences = _split_sentences(candidate_text)
    inspiration_sentences: list[str] = []
    for insp in inspiration_texts:
        inspiration_sentences.extend(_split_sentences(insp))

    for cand_sent in candidate_sentences:
        cand_tokens = set(_tokenize(cand_sent))
        if len(cand_tokens) < 4:
            continue

        for insp_sent in inspiration_sentences:
            insp_tokens = set(_tokenize(insp_sent))
            if len(insp_tokens) < 4:
                continue

            intersection = cand_tokens.intersection(insp_tokens)
            union = cand_tokens.union(insp_tokens)
            jaccard = len(intersection) / len(union) if union else 0.0

            # Flag if Jaccard similarity >= threshold or 5+ matching tokens
            if jaccard >= threshold or len(intersection) >= 5:
                return True, insp_sent

    return False, None


def build_voice_profile(
    seller_texts: list[str],
    inspiration_texts: list[str] | None = None,
    sources: list[str] | None = None,
) -> VoiceProfile:
    """Build a VoiceProfile from the seller's crawled content.

    Inspiration texts inform style parameters only; their sentences are NEVER stored.
    """
    all_seller_text = "\n".join(seller_texts)
    sentences = _split_sentences(all_seller_text)

    # 1. Average sentence length in words
    word_counts = [len(s.split()) for s in sentences if s.split()]
    avg_words = round(sum(word_counts) / len(word_counts), 1) if word_counts else 14.0
    avg_words = max(5.0, min(avg_words, 35.0))

    # 2. Formality detection
    lower_text = all_seller_text.lower()
    contractions = len(re.findall(r"\b[a-z]+'[a-z]+\b", lower_text))
    casual_words = len(
        re.findall(r"\b(?:hey|grab|love|super|awesome|chill|vibes|sneak\s+peek)\b", lower_text)
    )
    formal_words = len(
        re.findall(
            r"\b(?:furthermore|exquisite|esteemed|curated|archival|distinguished)\b", lower_text
        )
    )

    formality: FormalityLevel = "neutral"
    if casual_words + contractions > formal_words + 2:
        formality = "casual"
    elif formal_words > casual_words + contractions + 1:
        formality = "formal"

    # 3. Emoji detection
    all_emojis = _EMOJI_RE.findall(all_seller_text)
    uses_emojis = len(all_emojis) > 0
    emoji_counts = Counter(all_emojis)
    common_emojis = [emoji for emoji, _ in emoji_counts.most_common(5)]

    # 4. Hashtags
    all_hashtags = _HASHTAG_RE.findall(all_seller_text)
    hashtag_counts = Counter(h.lower() for h in all_hashtags)
    avg_hashtags = min(round(len(all_hashtags) / max(1, len(seller_texts))), 15)
    common_hashtags = [h for h, _ in hashtag_counts.most_common(5)]

    # 5. Recurring vocabulary
    tokens = _tokenize(all_seller_text)
    filtered_tokens = [w for w in tokens if w not in _STOPWORDS]
    word_freq = Counter(filtered_tokens)
    recurring_words = [w for w, count in word_freq.most_common(8) if count >= 2]
    if not recurring_words:
        recurring_words = [w for w, _ in word_freq.most_common(8)]

    # 6. Sample lines (5 to 8 short lines, 25 to 100 chars, exclusively from seller's own text)
    sample_lines: list[str] = []
    seen_lines: set[str] = set()
    for s in sentences:
        s_clean = s.strip()
        if (
            20 <= len(s_clean) <= 90
            and s_clean not in seen_lines
            and not any(bw in s_clean.lower() for bw in BANNED_AI_WORDS)
        ):
            sample_lines.append(s_clean)
            seen_lines.add(s_clean)
            if len(sample_lines) >= 8:
                break

    # If inspiration texts provided, adjust style cues without storing inspiration text
    if inspiration_texts:
        insp_text = " ".join(inspiration_texts)
        insp_emojis = _EMOJI_RE.findall(insp_text)
        if len(insp_emojis) >= 3:
            uses_emojis = True

    return VoiceProfile(
        avg_sentence_words=avg_words,
        formality=formality,
        uses_emojis=uses_emojis,
        common_emojis=common_emojis,
        avg_hashtags=avg_hashtags,
        common_hashtags=common_hashtags,
        recurring_words=recurring_words,
        words_to_avoid=sorted(list(BANNED_AI_WORDS))[:15],
        sample_lines=sample_lines[:8],
        sources=list(sources or ["shop bio & catalog"])[:5],
    )


def adjust_voice_profile(profile: VoiceProfile, adjustment: VoiceAdjustment) -> VoiceProfile:
    """Apply seller tuning ('casual', 'formal', 'shorter') to an existing VoiceProfile."""
    updated = profile.model_copy(deep=True)
    if adjustment not in updated.adjustments:
        updated.adjustments.append(adjustment)

    if adjustment == "casual":
        updated.formality = "casual"
        updated.uses_emojis = True
        if updated.avg_sentence_words > 12.0:
            updated.avg_sentence_words = max(8.0, round(updated.avg_sentence_words * 0.85, 1))
    elif adjustment == "formal":
        updated.formality = "formal"
        if updated.avg_sentence_words < 16.0:
            updated.avg_sentence_words = min(25.0, round(updated.avg_sentence_words * 1.2, 1))
    elif adjustment == "shorter":
        updated.avg_sentence_words = max(6.0, round(updated.avg_sentence_words * 0.75, 1))

    return updated


def humanize_generated_caption(
    caption: str,
    voice_profile: VoiceProfile | None = None,
    inspiration_texts: list[str] | None = None,
) -> str:
    """Clean a generated caption with deterministic humanizer rules and inspiration check."""
    cleaned = clean_text(caption)

    # Check for inspiration plagiarism
    if inspiration_texts:
        is_plagiarized, match = check_inspiration_similarity(cleaned, inspiration_texts)
        if is_plagiarized and match:
            # Remove or replace the plagiarized sentence
            sentences = _split_sentences(cleaned)
            sanitized = [s for s in sentences if match.lower() not in s.lower()]
            cleaned = " ".join(sanitized) if sanitized else "Handcrafted original artwork."

    # If voice profile requests shorter copy, limit sentence count
    if voice_profile and "shorter" in voice_profile.adjustments:
        sentences = _split_sentences(cleaned)
        if len(sentences) > 2:
            cleaned = " ".join(sentences[:2])

    return cleaned
