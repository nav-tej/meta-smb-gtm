"""Tests for pure function social handle extraction from crawl output and markup."""

from __future__ import annotations

from src.services.social_extract import extract_social_handles

HTML_SAMPLE_WITH_LINKS = """
<!DOCTYPE html>
<html>
<head>
  <title>Art of Sarabjit Singh</title>
  <meta property="og:see_also" content="https://instagram.com/artofsarabjit">
</head>
<body>
  <footer>
    <a href="https://www.instagram.com/artofsarabjit?igshid=123">Instagram</a>
    <a href="https://facebook.com/ArtofSarabjitSingh/">Facebook</a>
    <a href="https://facebook.com/sharer/sharer.php?u=https://example.com">Share on Facebook</a>
    <a href="https://pinterest.com/sarabjitart/paintings/">Pinterest</a>
    <a href="https://pinterest.com/pin/create/button/">Pin it</a>
    <a href="https://www.tiktok.com/@sarabjitcrafts?lang=en">TikTok</a>
    <a href="https://instagram.com/p/C0xyz123/">Post Link</a>
  </footer>
</body>
</html>
"""

HTML_SAMPLE_WITH_JSON_LD = """
<!DOCTYPE html>
<html>
<head>
  <script type="application/ld+json">
  {
    "@context": "https://schema.org",
    "@type": "Person",
    "name": "Sarabjit Singh",
    "sameAs": [
      "https://www.instagram.com/artofsarabjit",
      "https://facebook.com/ArtofSarabjitSingh",
      "https://pinterest.com/sarabjitart",
      "https://tiktok.com/@sarabjitcrafts"
    ]
  }
  </script>
</head>
<body>
  <h1>Welcome</h1>
</body>
</html>
"""


def test_extract_socials_from_html_links() -> None:
    results = extract_social_handles(HTML_SAMPLE_WITH_LINKS)
    platforms = {s["platform"] for s in results}
    assert platforms == {"instagram", "facebook", "pinterest", "tiktok"}

    handles = {s["handle"].lower() for s in results}
    assert "@artofsarabjit" in handles
    assert "@artofsarabjitsingh" in handles
    assert "@sarabjitart" in handles
    assert "@sarabjitcrafts" in handles

    # Verify non-profile subpaths were rejected
    urls = [s["url"] for s in results]
    assert not any("sharer" in u for u in urls)
    assert not any("/p/" in u for u in urls)
    assert not any("create" in u for u in urls)


def test_extract_socials_from_json_ld() -> None:
    results = extract_social_handles(HTML_SAMPLE_WITH_JSON_LD)
    assert len(results) == 4
    insta = next(s for s in results if s["platform"] == "instagram")
    assert insta["handle"] == "@artofsarabjit"
    assert insta["url"] == "https://instagram.com/artofsarabjit"
    assert insta["confirmed"] is True
    assert insta["source"] == "crawl"


def test_extract_socials_from_crawl_dict() -> None:
    crawl_data = {
        "business_name": "Mountain Pottery",
        "channels": [
            {"kind": "own_website", "url": "https://mountainpottery.com"},
            {"kind": "social", "url": "https://instagram.com/mountain_pottery"},
        ],
        "links": [
            "https://facebook.com/mountainpotteryca",
            "https://twitter.com/mtnpottery",
        ],
    }
    results = extract_social_handles(crawl_data)
    assert len(results) == 3
    platforms = {s["platform"] for s in results}
    assert platforms == {"instagram", "facebook", "twitter"}


def test_extract_socials_deduplication_and_invalid() -> None:
    raw_list = [
        "https://instagram.com/artist_studio",
        "https://www.instagram.com/artist_studio/",
        "https://instagram.com/artist_studio?ref=badge",
        "https://instagram.com/p/XYZ123",
        "https://facebook.com/login",
        "not-a-url",
        "https://randomsite.com/profile",
    ]
    results = extract_social_handles(raw_list)
    assert len(results) == 1
    assert results[0]["platform"] == "instagram"
    assert results[0]["handle"] == "@artist_studio"
    assert results[0]["url"] == "https://instagram.com/artist_studio"
