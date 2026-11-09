"""Verify seller identity footer and legal policy pages required for live payments."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from src.api.main import app

client = TestClient(app)


@pytest.mark.parametrize(
    ("path", "expected_heading", "expected_terms"),
    [
        (
            "/static/legal/terms.html",
            "Terms of Service",
            (
                "Last updated November 9, 2026",
                "n Plus Alpha LLC",
                "help@nplusalpha.com",
                "NPLUSALPHA.COM",
                "$12/month",
                "$108/year",
                "20 Muse runs per month",
                "State of California",
            ),
        ),
        (
            "/static/legal/privacy.html",
            "Privacy Policy",
            (
                "Last updated November 9, 2026",
                "n Plus Alpha LLC",
                "help@nplusalpha.com",
                "Supabase",
                "Stripe",
                "Meta’s Muse Model API",
                "never sees or stores your full credit card number",
                "within 30 days",
            ),
        ),
        (
            "/static/legal/refunds.html",
            "Cancellation &amp; Refund Policy",
            (
                "Last updated November 9, 2026",
                "n Plus Alpha LLC",
                "help@nplusalpha.com",
                "NPLUSALPHA.COM",
                "$12/month",
                "$108/year",
                "free trial of 3 Muse runs",
                "14 days of an annual payment",
            ),
        ),
    ],
)
def test_legal_pages_return_200_and_contain_required_disclosures(
    path: str, expected_heading: str, expected_terms: tuple[str, ...]
) -> None:
    response = client.get(path)
    assert response.status_code == 200
    body = response.text
    assert expected_heading in body
    for term in expected_terms:
        assert term in body, f"Missing {term!r} in {path}"


def test_legal_stylesheet_served() -> None:
    response = client.get("/static/legal/legal.css")
    assert response.status_code == 200
    assert ".draft-banner" in response.text


@pytest.mark.parametrize("route", ["/", "/today", "/create", "/digest"])
def test_seller_footer_and_legal_links_present_on_all_four_pages(route: str) -> None:
    response = client.get(route)
    assert response.status_code == 200
    html = response.text
    assert "Muse Growth Studio is operated by n Plus Alpha LLC" in html
    assert 'href="mailto:help@nplusalpha.com"' in html
    assert 'href="/static/legal/terms.html"' in html
    assert 'href="/static/legal/privacy.html"' in html
    assert 'href="/static/legal/refunds.html"' in html


def test_legal_pages_have_no_draft_placeholders() -> None:
    for name in ("terms", "privacy", "refunds"):
        html = client.get(f"/static/legal/{name}.html").text
        assert "NAV TO CONFIRM" not in html and "Draft" not in html, name
        # No billing portal exists in the app yet, so cancellation goes through support.
        assert "billing portal" not in html, name
