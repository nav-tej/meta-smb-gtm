"""Home, /today, /progress and /digest fit a services business, and home stops contradicting itself.

Pass 17 walked the app as a consultancy ("North Star Advisory", services, LinkedIn, 30 minutes a
week, 3 runs left while live Muse was off). Home said "Who sells similar art", offered "Gift
ideas", printed "Linkedin", clipped the watch-role menus at the card edge, said "No runs remaining"
under a header that said "3 of 3 runs left", and said "Nothing saved yet" above a move that cited
the saved goal. /today's context bar showed the editor's goal key ("Goal: story") and "Apply
defaults to editor". A products seller keeps "Your shop" and "Gift ideas".
Real app, fixture accounts (every module that reads the account is patched), no live Muse calls.
"""

from __future__ import annotations

import importlib
import json
import socket
import subprocess
import threading
import time
from pathlib import Path
from typing import Any

import pytest
import uvicorn
from fastapi import HTTPException

from src.api.main import app
from src.services.accounts import AccountSession
from src.services.seller_memory import _channel_name, rank_seller_recommendations
from tests.test_api_calls_per_page_e2e import _find_playwright_python


def _document(name: str, business_type: str, goal: str, channels: list[str]) -> dict[str, Any]:
    return {
        "onboarding": {
            "business_name": name,
            "business_type": business_type,
            "website_url": f"https://{name.split()[0].lower()}.test",
            "shop_urls": [f"https://{name.split()[0].lower()}.test"],
            "completed_at": "2026-11-10T10:00:00Z",
            "competitors": [
                {
                    "name": "Brightpath Consulting",
                    "url": "https://brightpath.test",
                    "reason": "Same clients",
                },
                {
                    "name": "Summit Growth",
                    "url": "https://summitgrowth.test",
                    "reason": "Similar offer",
                },
            ],
        },
        "preferences": {"goal": goal, "access": {"minutes_per_week": 30, "channels": channels}},
    }


def _old_example_document() -> dict[str, Any]:
    """An account that saved the n+α example competitors during setup (before pass 9)."""
    doc = _document(
        "n Plus Alpha Ventures", "services", "More client inquiries", ["linkedin", "youtube"]
    )
    doc["onboarding"]["competitors"] = [
        {
            "name": "Clutch B2B Marketing Directory",
            "url": "https://clutch.co/",
            "reason": "Example",
        },
        {
            "name": "Upwork Fractional Marketing Talent",
            "url": "https://www.upwork.com/",
            "reason": "Example",
        },
        {
            "name": "Toptal Marketing Talent Network",
            "url": "https://www.toptal.com/",
            "reason": "Example",
        },
    ]
    doc["preferences"]["competitor_entries"] = [
        {**c, "role": "similar_audience", "rationale": "Example", "selected": True}
        for c in doc["onboarding"]["competitors"]
    ]
    return doc


def _malformed_document() -> dict[str, Any]:
    """A workspace whose socials is an object and whose competitors hold a stray string."""
    doc = _document("Kiln Row Studio", "products", "More sales", ["instagram"])
    doc["onboarding"]["socials"] = {"instagram": "kilnrow"}
    doc["onboarding"]["competitors"].insert(0, "not-an-entry")
    return doc


def _old_example_plus_real_document() -> dict[str, Any]:
    """The old example competitors next to one the seller added and wrote a note on."""
    doc = _old_example_document()
    real = {"name": "Demand Curve", "url": "https://demandcurve.test", "reason": "Added by you"}
    doc["onboarding"]["competitors"].append(dict(real))
    doc["preferences"]["competitor_entries"].append(
        {**real, "role": "inspiration", "rationale": "Their founder newsletter", "selected": True}
    )
    doc["preferences"]["watch"] = {
        "competitor_urls": [c["url"] for c in doc["onboarding"]["competitors"]]
    }
    return doc


def _saved_context_document() -> dict[str, Any]:
    """A finished setup, then a linked Ad Library page, an analysis, a note and a role on the home,
    a competitor added in seller memory only, and an hour a week set after setup."""
    doc = _document("Ridge Line Advisory", "services", "More client inquiries", ["linkedin"])
    onb = doc["onboarding"]
    onb["competitors"][0]["ad_library_page_id"] = "104958162837"
    onb["preferences"] = {"access": {"minutes_per_week": 30, "channels": ["linkedin"]}}
    doc["preferences"]["access"]["minutes_per_week"] = 60
    doc["preferences"]["competitor_entries"] = [
        {
            **onb["competitors"][0],
            "role": "price_reference",
            "rationale": "They undercut us on retainers",
            "selected": True,
            "analysis_takeaway": "They lead with a free growth audit.",
            "analysis_summary": "They lead with a free growth audit and publish case studies.",
            "analyzed_at": "2026-11-25T08:00:00Z",
        },
        {**onb["competitors"][1], "role": "similar_audience", "rationale": "Similar offer",
         "selected": True},
        {"name": "Lumen Labs", "url": "https://lumenlabs.test", "role": "inspiration",
         "rationale": "Great webinars", "reason": "Added by you", "selected": True},
    ]  # fmt: skip
    return doc


USERS = {
    "svc": _document(
        "North Star Advisory", "services", "More client inquiries", ["linkedin", "website"]
    ),
    "prod": _document("Wild Meadow Prints", "products", "More sales", ["instagram", "website"]),
    "oldex": _old_example_document(),
    "bad": _malformed_document(),
    "live": _document("Northwind Growth", "services", "More client inquiries", ["linkedin"]),
    "oldrm": _old_example_plus_real_document(),
    "keep": _saved_context_document(),
}


@pytest.fixture
def any_business_server(monkeypatch: pytest.MonkeyPatch):
    stores = {uid: {"document": doc, "version": 1, "owner_id": uid} for uid, doc in USERS.items()}
    sessions = {
        uid: AccountSession(
            user_id=uid,
            email=f"{uid}@walk.test",
            email_verified=True,
            access_token="tok",
            session_id=None,
        )
        for uid in USERS
    }

    async def fake_resolve(request: Any, _response: Any = None, require_verified: bool = False):
        uid = request.cookies.get("muse_e2e_user")
        if uid in sessions:
            return sessions[uid]
        if require_verified:
            raise HTTPException(401, "Sign in required")
        return None

    async def fake_load(session: AccountSession) -> dict[str, Any]:
        return json.loads(json.dumps(stores[session.user_id]))

    async def fake_save(session, doc, expected_version=None, expected_owner=None):
        slot = stores[session.user_id]
        slot["document"] = json.loads(json.dumps(doc))
        slot["version"] = int(slot["version"]) + 1
        return json.loads(json.dumps(slot))

    async def fake_snapshot(session: AccountSession | None) -> dict[str, Any]:
        if session is None:
            return {"configured": True, "user": None, "usage": None, "live_available": False}
        # Runs are left, but live Muse is off: the state that used to read "No runs remaining".
        return {
            "configured": True,
            "user": {"id": session.user_id, "email": session.email, "email_verified": True},
            "usage": {"plan": "starter", "used": 0, "limit": 3, "remaining": 3},
            "runs_remaining": 3,
            # "live" can run an analysis (the page is told so); Muse itself is faked in the page.
            "live_available": session.user_id == "live",
        }

    async def no_crawl(*_args: Any, **_kwargs: Any) -> tuple[list[Any], list[str]]:
        return [], []

    def no_muse(*_args: Any, **_kwargs: Any) -> Any:
        raise AssertionError("no live Muse calls in this test")

    monkeypatch.setenv("DEMO_MODE", "true")
    monkeypatch.setenv("ACCOUNTS_REQUIRED", "true")
    monkeypatch.setenv("META_MODEL_API_KEY", "")
    monkeypatch.setenv("DEMO_KEY", "")
    fakes = {
        "resolve_account": fake_resolve,
        "load_workspace": fake_load,
        "save_workspace": fake_save,
        "snapshot": fake_snapshot,
    }
    for name in (
        "src.api.accounts",
        "src.api.onboarding",
        "src.api.preferences",
        "src.api.seller_memory",
        "src.api.daily_brief",
        "src.api.outcomes",
        "src.api.intel",
        "src.api.media",
        "src.services.accounts",
    ):
        module = importlib.import_module(name)
        for attr, fake in fakes.items():
            if hasattr(module, attr):
                monkeypatch.setattr(module, attr, fake)
    monkeypatch.setattr("src.api.intel.collect_entries", no_crawl)
    monkeypatch.setattr("src.api.seller_memory.collect_entries", no_crawl)
    monkeypatch.setattr("src.clients.meta.get_meta_client", no_muse)

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    for _ in range(80):
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.1):
                break
        except OSError:
            time.sleep(0.05)
    yield f"http://127.0.0.1:{port}"
    server.should_exit = True
    thread.join(timeout=5)


def test_channel_names_keep_brand_casing() -> None:
    assert [_channel_name(c) for c in ("linkedin", "tiktok", "x", "instagram", "website")] == [
        "LinkedIn",
        "TikTok",
        "X",
        "Instagram",
        "Website",
    ]
    result = rank_seller_recommendations(
        business_name="North Star Advisory",
        business_type="services",
        preferences=None,
    )
    text = json.dumps(result)
    assert "Linkedin" not in text and "Tiktok" not in text


def test_home_today_progress_and_digest_fit_a_services_business_e2e(
    any_business_server: str,
) -> None:
    python_bin = _find_playwright_python()
    if not python_bin:
        pytest.skip("Playwright runtime not installed")
    script = f"""
import json
from playwright.sync_api import sync_playwright

BASE = {any_business_server!r}

def text(page):
    return page.evaluate("document.body.innerText")

with sync_playwright() as p:
    browser = p.chromium.launch()
    for width in (1440, 375):
        ctx = browser.new_context(viewport={{"width": width, "height": 900}})
        ctx.add_cookies([{{"name": "muse_e2e_user", "value": "svc", "url": BASE}}])
        page = ctx.new_page()
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))

        page.goto(BASE + "/", wait_until="domcontentloaded")
        page.wait_for_function(
            "document.querySelector('#smHomeContextPanel .sm-sub, .sm-card .sm-sub')"
            " && document.body.innerText.includes('your 30 minutes a week')"
            " && document.body.innerText.includes('Top next move')",
            timeout=20000,
        )
        # The sample shop's "Ask Muse" card is not part of an own workspace.
        assert not page.locator("#jrSteerResearch").is_visible()
        body = text(page)
        # The saved goal and minutes, not "Nothing saved yet".
        assert "your goal (more client inquiries) and your 30 minutes a week" in body, body
        assert "Nothing saved yet" not in body
        assert page.locator("#smExpandContextBtn").inner_text().strip() == "Change your goal"
        # Runs are left; live Muse is off. Say that, not "No runs remaining".
        cost = page.locator("#addCompetitorCost").inner_text()
        assert "Live analysis is unavailable right now" in cost, cost
        assert "No runs remaining" not in body
        assert page.locator("#addCompetitorBtn").inner_text().strip() == "Add competitor"
        # Words for a consultancy.
        for wrong in ("similar art", "Gift ideas", "Gifts under", "Linkedin", "Analyze seller",
                      "Your shop is set up", "shop pages scanned", "[live]"):
            assert wrong not in body, (wrong, width)
        assert "LinkedIn" in body
        assert "Your workspace is set up. Get your first result." in body
        kicker = page.locator("#activeWorkspaceKicker").inner_text().strip().lower()
        assert kicker == "your business", kicker
        assert "Many service businesses quote on request" in body
        # The watch-role menus sit inside their competitor row (opened with "Edit").
        page.evaluate(
            "document.querySelectorAll('#sellerList .sm-comp-edit').forEach((b) => b.click())"
        )
        clipped = page.evaluate('''() => Array.from(document.querySelectorAll(
            '#sellerList .jr-seller > .sm-comp-role-wrap select')).map((s) => {{
              const row = s.closest('.jr-seller').getBoundingClientRect();
              const box = s.getBoundingClientRect();
              return box.right > row.right + 1 || box.left < row.left - 1;
            }})''')
        assert clipped and not any(clipped), clipped
        assert not page.evaluate("document.documentElement.scrollWidth > window.innerWidth")

        page.goto(BASE + "/today", wait_until="domcontentloaded")
        page.wait_for_selector("#smStudioContextBar .sm-badge-goal", timeout=20000)
        goal = page.locator("#smStudioContextBar .sm-badge-goal").inner_text()
        assert goal == "Goal: Share what you do", goal
        assert page.locator("#smStudioApplyBtn").inner_text() == "Use this move in my post"
        body = text(page)
        assert "Put your link in your profile" in body, body
        assert "Back to making" not in body and "BACK TO MAKING" not in body
        assert "similar sellers" not in body

        page.goto(BASE + "/progress", wait_until="domcontentloaded")
        options = page.locator("#pgFormChannel option").all_inner_texts()
        assert "LinkedIn" in options and "Website or direct" in options, options
        assert "Online Shop / Direct" not in options

        page.goto(BASE + "/digest", wait_until="domcontentloaded")
        body = text(page)
        assert "What changed at the competitors you watch" in body, body
        assert "your shop website" not in body
        assert not errors, errors
        ctx.close()

    # A products seller keeps the shop words.
    ctx = browser.new_context(viewport={{"width": 1440, "height": 900}})
    ctx.add_cookies([{{"name": "muse_e2e_user", "value": "prod", "url": BASE}}])
    page = ctx.new_page()
    page.goto(BASE + "/", wait_until="domcontentloaded")
    page.wait_for_function(
        "(document.getElementById('activeWorkspaceKicker')?.textContent || '')"
        ".trim().toLowerCase() === 'your shop'",
        timeout=20000,
    )
    assert page.locator("#activeWorkspaceKicker").inner_text().strip().lower() == "your shop"
    page.goto(BASE + "/today", wait_until="domcontentloaded")
    page.wait_for_selector("#smStudioContextBar .sm-badge-goal", timeout=20000)
    goal = page.locator("#smStudioContextBar .sm-badge-goal").inner_text()
    assert goal.startswith("Goal: "), goal
    assert goal not in ("Goal: story", "Goal: visits", "Goal: gift"), goal
    browser.close()
print("ANY_BUSINESS_OK")
"""
    proc = subprocess.run(
        [python_bin, "-c", script], capture_output=True, text=True, timeout=240, check=False
    )
    assert proc.returncode == 0 and "ANY_BUSINESS_OK" in proc.stdout, (
        f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
    )


def test_own_workspace_shows_no_sample_shop_and_flags_old_example_e2e(
    any_business_server: str,
) -> None:
    """Pass 18 (Nov 22): Nav's own nplusalpha.com workspace showed the sample artist.

    Opening "Full workspace" showed the "Interactive demo" note, the artist's KPIs (14-day ROAS,
    POD prices, checkout fix), a Step 0 form filled with artofsarabjitsingh.com, Saatchi and
    FineArtAmerica, and "Gift buyers" chips. "What Muse remembers" was empty and offered a sample
    watercolor voice note. "See their ads on Meta" searched "Upwork Fractional Marketing Talent",
    which no ad contains. Clutch, Upwork and Toptal (the old setup example) were never flagged.
    The sample shop keeps all of its demo blocks.
    """
    python_bin = _find_playwright_python()
    if not python_bin:
        pytest.skip("Playwright runtime not installed")
    script = f"""
import json, re
from urllib.parse import urlparse, parse_qs
from playwright.sync_api import sync_playwright

BASE = {any_business_server!r}
SAMPLE_TERMS = re.compile(
    r"(?i)ek onkar|sarabjit|sikhiart|fineartamerica|saatchi|gift buyers|14-day ad roas|"
    r"interactive demo|watercolor|catalog indexed|checkout fix|local tools"
)

with sync_playwright() as p:
    browser = p.chromium.launch()
    for width in (1440, 375):
        ctx = browser.new_context(viewport={{"width": width, "height": 900}})
        ctx.add_cookies([{{"name": "muse_e2e_user", "value": "oldex", "url": BASE}}])
        page = ctx.new_page()
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto(BASE + "/", wait_until="domcontentloaded")
        page.wait_for_selector("#oldExampleCompetitorsNote", state="visible", timeout=20000)
        note = page.locator("#oldExampleCompetitorsNote")
        assert "Clutch, Upwork and Toptal came from an example" in note.inner_text()
        assert note.locator("a").get_attribute("href") == "/welcome?step=3"
        # The note sits outside the list: seller memory still decorates exactly three rows.
        page.wait_for_function(
            "document.querySelectorAll('#sellerList .sm-comp-role-wrap').length === 3",
            timeout=10000,
        )
        page.locator("#toggleWorkspace").click()
        page.wait_for_function(
            "document.querySelectorAll('#metaAdsContainer .jr-meta-ad-link').length > 0",
            timeout=15000,
        )
        body = page.evaluate("document.body.innerText")
        found = sorted({{m.group(0).lower() for m in SAMPLE_TERMS.finditer(body)}})
        assert not found, (width, found)
        queries = page.evaluate(
            "Array.from(document.querySelectorAll('#sellerList a.jr-meta-ad-link'))"
            ".map((a) => a.href)"
        )
        assert [parse_qs(urlparse(u).query)["q"][0] for u in queries] == [
            "Clutch", "Upwork", "Toptal"
        ], queries
        tabs = page.evaluate(
            "Array.from(document.querySelectorAll('.step-tab')).filter((t) => t.offsetParent)"
            ".map((t) => t.dataset.tab)"
        )
        assert tabs == ["tab-intel", "tab-bids"], tabs
        assert not page.evaluate("document.documentElement.scrollWidth > window.innerWidth")

        page.get_by_text("What Muse remembers", exact=True).first.click()
        facts = page.locator("#smSetupFacts")
        facts.wait_for(state="visible", timeout=10000)
        text = facts.inner_text()
        for want in ("n Plus Alpha Ventures", "Services", "More client inquiries",
                     "30 minutes a week", "LinkedIn, YouTube", "Clutch B2B Marketing Directory"):
            assert want in text, (want, text)
        assert page.evaluate(
            "getComputedStyle(document.getElementById('smUseVoiceFixtureBtn')).display"
        ) == "none"
        assert not errors, errors
        ctx.close()

    # The sample shop keeps its demo blocks and its own competitor names.
    ctx = browser.new_context(viewport={{"width": 1440, "height": 900}})
    ctx.add_cookies([{{"name": "muse_e2e_user", "value": "oldex", "url": BASE}}])
    page = ctx.new_page()
    page.goto(BASE + "/?workspace=sample", wait_until="domcontentloaded")
    page.wait_for_function("document.documentElement.dataset.museMode === 'account_sample'",
                           timeout=20000)
    page.locator("#toggleWorkspace").click()
    page.wait_for_timeout(800)
    body = page.evaluate("document.body.innerText")
    assert "Interactive demo" in body and "Local tools" in body
    assert not page.locator("#oldExampleCompetitorsNote").is_visible()
    browser.close()
print("OWN_NO_SAMPLE_OK")
"""
    proc = subprocess.run(
        [python_bin, "-c", script], capture_output=True, text=True, timeout=240, check=False
    )
    assert proc.returncode == 0 and "OWN_NO_SAMPLE_OK" in proc.stdout, (
        f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
    )


def test_malformed_setup_fields_still_render_the_own_home_e2e(any_business_server: str) -> None:
    """One malformed field used to stop welcome.js mid-render and leave the sample shop showing."""
    python_bin = _find_playwright_python()
    if not python_bin:
        pytest.skip("Playwright runtime not installed")
    script = f"""
from playwright.sync_api import sync_playwright

BASE = {any_business_server!r}
with sync_playwright() as p:
    browser = p.chromium.launch()
    for width in (1440, 375):
        ctx = browser.new_context(viewport={{"width": width, "height": 900}})
        ctx.add_cookies([{{"name": "muse_e2e_user", "value": "bad", "url": BASE}}])
        page = ctx.new_page()
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto(BASE + "/", wait_until="domcontentloaded")
        page.wait_for_function(
            "(document.getElementById('journeyTitle')?.textContent || '')"
            " === 'Your week at Kiln Row Studio'",
            timeout=20000,
        )
        page.wait_for_timeout(800)
        label = page.locator("#activeWorkspaceLabel").inner_text()
        assert label == "Kiln Row Studio", label
        rows = page.locator("#sellerList").inner_text()
        assert "Brightpath Consulting" in rows and "SikhiArt" not in rows, rows
        assert not page.locator(".jr-estimate").is_visible()
        assert not errors, errors
        ctx.close()
    browser.close()
print("MALFORMED_OK")
"""
    proc = subprocess.run(
        [python_bin, "-c", script], capture_output=True, text=True, timeout=180, check=False
    )
    assert proc.returncode == 0 and "MALFORMED_OK" in proc.stdout, (
        f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
    )


def test_a_finished_analysis_is_saved_and_becomes_the_competitor_note_e2e(
    any_business_server: str,
) -> None:
    """Nov 25: the home saved analyses with a request the server refused (405), so a reload lost
    them and nothing reached the seller's notes. Now it is saved and editable."""
    python_bin = _find_playwright_python()
    if not python_bin:
        pytest.skip("Playwright runtime not installed")
    brief = json.loads((Path(__file__).parent / "fixtures" / "competitor_brief.json").read_text())
    brief["summary"] = "Brightpath sells fixed-fee growth audits to B2B founders."
    brief["competitor_url"] = "https://brightpath.test"
    script = f"""
from playwright.sync_api import sync_playwright

BASE = {any_business_server!r}
BRIEF = {json.dumps(brief)!r}
TAKEAWAY = "Brightpath sells fixed-fee growth audits to B2B founders."
ROW_HAS = (
    "(want) => [...document.querySelectorAll('#sellerList .jr-seller')].some((li) =>"
    " li.textContent.includes('Brightpath') && (li.querySelector('.js-live-brief')?.textContent"
    " || '').includes(want))"
)
with sync_playwright() as p:
    browser = p.chromium.launch()
    ctx = browser.new_context(viewport={{"width": 1440, "height": 900}})
    ctx.add_cookies([{{"name": "muse_e2e_user", "value": "live", "url": BASE}}])
    page = ctx.new_page()
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.route(
        "**/api/v1/analyze-competitors**",
        lambda r: r.fulfill(status=200, content_type="application/json", body=BRIEF),
    )
    page.goto(BASE + "/", wait_until="domcontentloaded")
    page.wait_for_function(ROW_HAS, arg="Request analysis", timeout=20000)
    btn = page.locator("#sellerList .jr-seller", has_text="Brightpath").locator(".js-live-brief")
    with page.expect_response(
        lambda r: r.url.endswith("/api/v1/competitors/saved") and r.request.method == "PUT",
        timeout=30000,
    ) as saved:
        btn.click()
    assert saved.value.status == 200, saved.value.text()
    page.wait_for_function(
        "document.body.innerText.includes('Analysis saved to your workspace')", timeout=10000
    )
    # The competitor card's note shows the takeaway right away, before any reload.
    page.wait_for_function(
        "(t) => [...document.querySelectorAll('#sellerList .sm-comp-rationale')]"
        ".some((i) => i.value === t)",
        arg=TAKEAWAY,
        timeout=15000,
    )
    # The card shows it as one line, and the seller can change it.
    note_line = page.locator("#sellerList .jr-seller", has_text="Brightpath").locator(
        ".sm-comp-note-text"
    )
    assert note_line.inner_text() == "Your note: " + TAKEAWAY, note_line.inner_text()
    row = page.locator("#sellerList .jr-seller", has_text="Brightpath")
    row.locator(".sm-comp-edit").click()
    row.locator(".sm-comp-rationale").fill("They win on fixed fees; we win on speed")
    row.locator(".sm-comp-rationale").dispatch_event("change")
    page.wait_for_function(
        "() => [...document.querySelectorAll('#sellerList .sm-comp-note-text')].some((n) =>"
        " n.textContent === 'Your note: They win on fixed fees; we win on speed')",
        timeout=15000,
    )
    row.locator(".sm-comp-rationale").fill(TAKEAWAY)
    row.locator(".sm-comp-rationale").dispatch_event("change")
    page.wait_for_function(
        "(t) => [...document.querySelectorAll('#sellerList .sm-comp-note-text')]"
        ".some((n) => n.textContent === 'Your note: ' + t)",
        arg=TAKEAWAY,
        timeout=15000,
    )
    # A reload keeps it: "View analysis" (free), and the takeaway is the competitor's note.
    page.goto(BASE + "/", wait_until="domcontentloaded")
    page.wait_for_function(ROW_HAS, arg="View analysis", timeout=20000)
    page.wait_for_function(
        "(t) => [...document.querySelectorAll('#sellerList .sm-comp-rationale')]"
        ".some((i) => i.value === t)",
        arg=TAKEAWAY,
        timeout=20000,
    )
    assert not errors, errors
    browser.close()
print("ANALYSIS_SAVED_OK")
"""
    proc = subprocess.run(
        [python_bin, "-c", script], capture_output=True, text=True, timeout=180, check=False
    )
    assert proc.returncode == 0 and "ANALYSIS_SAVED_OK" in proc.stdout, (
        f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
    )


def test_a_competitor_row_links_their_exact_meta_ad_library_page_e2e(
    any_business_server: str,
) -> None:
    """Nov 25: "See their ads" was a keyword search (every advertiser saying the name). Pasting
    the advertiser's Ad Library page links their own ads, and it stays after a reload."""
    python_bin = _find_playwright_python()
    if not python_bin:
        pytest.skip("Playwright runtime not installed")
    script = f"""
from playwright.sync_api import sync_playwright

BASE = {any_business_server!r}
PAGE = ("https://www.facebook.com/ads/library/?active_status=active&ad_type=all&country=ALL"
        "&view_all_page_id=104958162837&search_type=page&media_type=all")
KEYWORD = ("https://www.facebook.com/ads/library/?active_status=active&ad_type=all&country=ALL"
           "&q=Brightpath&search_type=keyword_unordered&media_type=all")
with sync_playwright() as p:
    browser = p.chromium.launch()
    for width in (375, 1440):
        ctx = browser.new_context(viewport={{"width": width, "height": 900}})
        ctx.add_cookies([{{"name": "muse_e2e_user", "value": "svc", "url": BASE}}])
        page = ctx.new_page()
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.route(lambda u: not u.startswith(BASE) and not u.startswith("data:"),
                   lambda r: r.abort())
        page.goto(BASE + "/", wait_until="domcontentloaded")
        row = page.locator("#sellerList .jr-seller", has_text="Brightpath Consulting").first
        link = row.locator(".jr-meta-ad-link").first
        link.wait_for(state="visible", timeout=20000)
        if width == 375:
            assert "(all advertisers)" in link.inner_text(), link.inner_text()
            assert "q=Brightpath" in (link.get_attribute("href") or "")
            row.get_by_role("button", name="Link their exact page").click()
            row.locator(".jr-ad-link-form input").fill(KEYWORD)
            row.get_by_role("button", name="Save link").click()
            row.locator(".jr-ad-link-status", has_text="keyword search").wait_for(timeout=10000)
            row.locator(".jr-ad-link-form input").fill(PAGE)
            row.get_by_role("button", name="Save link").click()
            page.wait_for_function(
                "() => [...document.querySelectorAll('#sellerList .jr-meta-ad-link')].some((a) =>"
                " a.href.includes('view_all_page_id=104958162837'))",
                timeout=10000,
            )
            assert not page.evaluate("document.documentElement.scrollWidth > window.innerWidth")
        else:
            # A new visit (the saved link is in the workspace now).
            page.wait_for_function(
                "() => [...document.querySelectorAll('#sellerList .jr-meta-ad-link')].some((a) =>"
                " a.href.includes('view_all_page_id=104958162837')"
                " && a.textContent.startsWith('See their ads on Meta'))",
                timeout=20000,
            )
        assert not errors, errors
        ctx.close()
    browser.close()
print("AD_LIBRARY_LINK_OK")
"""
    proc = subprocess.run(
        [python_bin, "-c", script], capture_output=True, text=True, timeout=180, check=False
    )
    assert proc.returncode == 0 and "AD_LIBRARY_LINK_OK" in proc.stdout, (
        f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
    )


def test_old_example_competitors_are_removed_in_one_click_e2e(any_business_server: str) -> None:
    """Nov 28: the note on Clutch, Upwork and Toptal only linked to setup. One button now takes
    every example off both lists; the seller's own competitor and its note stay."""
    python_bin = _find_playwright_python()
    if not python_bin:
        pytest.skip("Playwright runtime not installed")
    script = f"""
import json
from playwright.sync_api import sync_playwright

BASE = {any_business_server!r}
with sync_playwright() as p:
    browser = p.chromium.launch()
    ctx = browser.new_context(viewport={{"width": 375, "height": 900}})
    ctx.add_cookies([{{"name": "muse_e2e_user", "value": "oldrm", "url": BASE}}])
    page = ctx.new_page()
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.route(lambda u: not u.startswith(BASE) and not u.startswith("data:"), lambda r: r.abort())
    page.goto(BASE + "/", wait_until="domcontentloaded")
    note = page.locator("#oldExampleCompetitorsNote")
    note.wait_for(state="visible", timeout=20000)
    button = note.get_by_role("button", name="Remove these 3 examples")
    assert button.is_visible()
    assert note.locator("a").get_attribute("href") == "/welcome?step=3"
    assert not page.evaluate("document.documentElement.scrollWidth > window.innerWidth")
    page.wait_for_function(
        "document.querySelectorAll('#sellerList .sm-comp-role-wrap').length === 4", timeout=10000
    )
    button.click()
    note.wait_for(state="detached", timeout=10000)
    page.wait_for_function(
        "document.querySelectorAll('#sellerList .jr-seller').length === 1", timeout=10000
    )
    toast = page.locator(".ms-toast", has_text="from your watchlist").first
    toast.wait_for(timeout=5000)
    assert "Clutch B2B Marketing Directory, Upwork Fractional Marketing Talent and Toptal" in (
        toast.inner_text()), toast.inner_text()
    assert "Demand Curve" in page.locator("#sellerList").inner_text()
    assert "1 competitor on your watchlist" in page.locator("#loop-research .jr-watch").inner_text()

    # Saved: a new visit shows no note and one row, still with the seller's note.
    page.reload(wait_until="domcontentloaded")
    page.wait_for_function(
        "document.querySelectorAll('#sellerList .sm-comp-role-wrap').length === 1", timeout=20000
    )
    assert not page.locator("#oldExampleCompetitorsNote").count()
    assert "Their founder newsletter" in page.locator("#sellerList").inner_text()
    ws = page.evaluate("fetch('/api/v1/account/workspace', {{credentials: 'same-origin'}})"
                       ".then((r) => r.json())")
    doc = ws["workspace"]["document"] if "workspace" in ws else ws["document"]
    assert [c["url"] for c in doc["onboarding"]["competitors"]] == ["https://demandcurve.test"]
    entries = doc["preferences"]["competitor_entries"]
    assert [(e["url"], e["rationale"]) for e in entries] == [
        ("https://demandcurve.test", "Their founder newsletter")], entries
    assert doc["preferences"]["watch"]["competitor_urls"] == ["https://demandcurve.test"]
    assert not errors, errors
    browser.close()
print("REMOVE_EXAMPLES_OK")
"""
    proc = subprocess.run(
        [python_bin, "-c", script], capture_output=True, text=True, timeout=180, check=False
    )
    assert proc.returncode == 0 and "REMOVE_EXAMPLES_OK" in proc.stdout, (
        f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
    )


def test_editing_setup_keeps_what_the_home_saved_on_each_competitor_e2e(
    any_business_server: str,
) -> None:
    """Nov 28: saving setup rebuilt the watchlist from setup's own copy. A kept competitor lost its
    linked Ad Library page, its saved analysis, the seller's note and role; a competitor added in
    seller memory disappeared; and step 4 put back the weekly time from the first setup."""
    python_bin = _find_playwright_python()
    if not python_bin:
        pytest.skip("Playwright runtime not installed")
    script = f"""
from playwright.sync_api import sync_playwright

BASE = {any_business_server!r}
with sync_playwright() as p:
    browser = p.chromium.launch()
    ctx = browser.new_context(viewport={{"width": 1440, "height": 900}})
    ctx.add_cookies([{{"name": "muse_e2e_user", "value": "keep", "url": BASE}}])
    page = ctx.new_page()
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.route(lambda u: not u.startswith(BASE) and not u.startswith("data:"), lambda r: r.abort())
    page.goto(BASE + "/welcome?step=3", wait_until="domcontentloaded")
    page.wait_for_selector("#wkStep3:not([hidden])", timeout=20000)
    notes = page.locator("#wkStep3 .sm-comp-rationale")
    page.wait_for_function(
        "document.querySelectorAll('#wkStep3 .sm-comp-rationale').length === 3", timeout=10000
    )
    assert [notes.nth(i).input_value() for i in range(3)] == [
        "They undercut us on retainers", "Similar offer", "Great webinars"]
    assert page.locator("#wkStep3 .sm-comp-role").first.input_value() == "price_reference"
    page.click("#wkStep3NextBtn")
    page.wait_for_selector("#wkStep4:not([hidden])", timeout=10000)
    assert page.locator("#wkPrefMinutes").input_value() == "60"
    page.click("#wkStep4FinishBtn")
    page.wait_for_selector("#wkStepDone:not([hidden])", timeout=10000)
    ws = page.evaluate("fetch('/api/v1/account/workspace', {{credentials: 'same-origin'}})"
                       ".then((r) => r.json())")
    doc = ws["workspace"]["document"] if "workspace" in ws else ws["document"]
    entries = {{e["url"]: e for e in doc["preferences"]["competitor_entries"]}}
    first = entries["https://brightpath.test"]
    assert first["ad_library_page_id"] == "104958162837", first
    assert first["analysis_takeaway"] == "They lead with a free growth audit.", first
    assert first["analyzed_at"] == "2026-11-25T08:00:00Z", first
    assert (first["role"], first["rationale"]) == (
        "price_reference", "They undercut us on retainers"), first
    assert entries["https://lumenlabs.test"]["rationale"] == "Great webinars"
    assert doc["preferences"]["access"]["minutes_per_week"] == 60
    assert not errors, errors
    browser.close()
print("SETUP_KEEPS_CONTEXT_OK")
"""
    proc = subprocess.run(
        [python_bin, "-c", script], capture_output=True, text=True, timeout=180, check=False
    )
    assert proc.returncode == 0 and "SETUP_KEEPS_CONTEXT_OK" in proc.stdout, (
        f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
    )
