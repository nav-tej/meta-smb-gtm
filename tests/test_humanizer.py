"""Tests for Humanizer lint-and-suggest, preserving titles, product names, and formatting."""

from __future__ import annotations

from src.utils.humanizer import clean_text, lint_text


def test_codex_cases_6_to_10() -> None:
    """Codex PRD branch review sample cases 6 through 10."""
    # Case 6: "tapestry" the product must not be replaced with "blend"
    case6 = "A handwoven tapestry — made in Oakland."
    res6 = clean_text(case6)
    assert res6 == "A handwoven tapestry, made in Oakland."
    assert "tapestry" in res6
    assert "blend" not in res6

    # Case 7: Quoted or explicit artwork titles must not have words like "Revolutionary" stripped
    case7 = "The title of this print is Revolutionary Light."
    res7 = clean_text(case7)
    assert res7 == "The title of this print is Revolutionary Light."

    # Case 8: Capitalization preserved when replacing stock words at start of sentence
    case8 = "Embark on a new series with us."
    res8 = clean_text(case8)
    assert res8 == "Start a new series with us."

    # Case 9: Paragraph formatting and newlines must be preserved
    case9 = "Blue, green, and gold.\n\nShips in two days."
    res9 = clean_text(case9)
    assert res9 == "Blue, green, and gold.\n\nShips in two days."
    assert "\n\n" in res9

    # Case 10: Artwork title after "titled" must be preserved verbatim
    case10 = "The artist titled this print A Tapestry of Light."
    res10 = clean_text(case10)
    assert res10 == "The artist titled this print A Tapestry of Light."


def test_quoted_titles_never_modified() -> None:
    """Quoted strings and titles are never touched by cleaner."""
    text = 'Our new print is called "A Tapestry of Revolutionary Light". Ships worldwide.'
    cleaned = clean_text(text)
    assert '"A Tapestry of Revolutionary Light"' in cleaned


def test_lint_report_keeps_original_and_suggests() -> None:
    """lint_text returns non-destructive report keeping original and providing suggestion."""
    text = "We embark on a journey — delve into our collection."
    report = lint_text(text)
    assert not report.passed
    assert report.original_text == text
    assert report.suggested_text == "We start a journey, explore our collection."
    assert "delve" in report.violations[1] or "embark" in report.violations[0]
