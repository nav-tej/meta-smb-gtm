"""The first-ad guide must be reachable from the pages a seller actually lands on.

The guide shipped without a single inbound link, so the "prepare an ad" path looked
missing in a live walkthrough. These checks pin the entry points and the honest copy.
"""

from __future__ import annotations

import re

import pytest
from fastapi.testclient import TestClient

from src.api.main import STATIC_DIR, app

client = TestClient(app)

FIRST_AD_LINK = re.compile(r'<a[^>]*href="/first-ad"[^>]*data-mode-link="/first-ad"[^>]*>')


@pytest.mark.parametrize("path", ["/", "/today", "/create", "/progress"])
def test_page_links_to_first_ad_guide(path: str) -> None:
    response = client.get(path)
    assert response.status_code == 200
    assert FIRST_AD_LINK.search(response.text), f"{path} has no mode-aware link to /first-ad"


def test_create_offer_does_not_promise_publishing() -> None:
    html = client.get("/create").text
    offer = html[html.index('id="firstAdOffer"') :][:700]
    assert "You publish it yourself." in offer
    assert "Meta Ads Manager" in offer
    for overclaim in ("Launch campaign", "launch your campaign", "we publish", "ROAS"):
        assert overclaim not in offer


def test_mode_links_follow_the_active_workspace() -> None:
    script = (STATIC_DIR / "workspace-modes.js").read_text(encoding="utf-8")
    assert "function syncModeLinks()" in script
    assert "sample ? sampleHref(path) : ownHref(path)" in script
    # Called on first paint and on every mode change.
    assert script.count("syncModeLinks();") >= 3


@pytest.mark.parametrize(
    ("path", "location"),
    [
        ("/creator", "/create"),
        ("/creator?workspace=sample&idea=idea-1", "/create?workspace=sample&idea=idea-1"),
    ],
)
def test_creator_alias_redirects_to_create(path: str, location: str) -> None:
    response = client.get(path, follow_redirects=False)
    assert response.status_code == 307
    assert response.headers["location"] == location
