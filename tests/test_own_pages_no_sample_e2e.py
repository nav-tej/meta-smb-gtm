"""Every seller-owned page stays free of the sample shop at 375 and 1440 px.

Covers /today, /create, /digest, /first-ad, /progress and /welcome?edit=1 across four
own accounts (services, products, saved competitor checks + YouTube video, empty
post-setup), plus one check per page that ?workspace=sample still renders its sample
content. Real local FastAPI server, fake accounts, no live crawls, no Muse calls.
"""

from __future__ import annotations

import importlib
import json
import socket
import subprocess
import threading
import time
from typing import Any

import pytest
import uvicorn
from fastapi import HTTPException

from src.api.main import app
from src.services.accounts import AccountSession
from tests.test_api_calls_per_page_e2e import _find_playwright_python


def _make_doc(
    name: str,
    business_type: str,
    goal: str,
    channels: list[str],
    *,
    competitors: list[dict[str, str]] | None = None,
    checks: dict[str, Any] | None = None,
    youtube: dict[str, Any] | None = None,
) -> dict[str, Any]:
    slug = name.split()[0].lower()
    doc: dict[str, Any] = {
        "onboarding": {
            "business_name": name,
            "business_type": business_type,
            "website_url": f"https://{slug}.test",
            "shop_urls": [f"https://{slug}.test"],
            "completed_at": "2026-11-10T10:00:00Z",
            "competitors": competitors
            if competitors is not None
            else [
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
        "preferences": {
            "goal": goal,
            "access": {"minutes_per_week": 30, "channels": channels},
        },
    }
    if checks is not None:
        doc["preferences"]["competitor_checks"] = checks
    if youtube is not None:
        doc["preferences"]["content_sources"] = {"youtube": youtube}
    return doc


USERS: dict[str, dict[str, Any]] = {
    "svc": _make_doc(
        "North Star Advisory",
        "services",
        "More client inquiries",
        ["linkedin", "website"],
    ),
    "prod": _make_doc(
        "Wild Meadow Goods",
        "products",
        "More sales",
        ["instagram"],
    ),
    "rich": _make_doc(
        "Harbor Studio Co",
        "services",
        "More client inquiries",
        ["linkedin", "youtube"],
        checks={
            "https://brightpath.test": {
                "url": "https://brightpath.test",
                "name": "Brightpath Consulting",
                "checked_at": "2026-11-24T15:00:00Z",
                "status": "changed",
                "total_pages": 12,
                "counts": {"new_listing": 1, "price_change": 0, "removed_listing": 0},
                "new_pages": [
                    {"loc": "https://brightpath.test/new-guide", "lastmod": "2026-11-24"}
                ],
                "removed_pages": [],
                "partial": False,
                "error": None,
            }
        },
        youtube={
            "videos": [
                {
                    "video_id": "dQw4w9WgXcQ",
                    "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
                    "title": "How We Scope a 30-Day Audit",
                    "author_name": "Harbor Studio Co",
                    "thumbnail_url": "https://i.ytimg.com/vi/dQw4w9WgXcQ/hqdefault.jpg",
                    "added_at": "2026-11-24T12:00:00Z",
                }
            ]
        },
    ),
    "empty": {
        "onboarding": {
            "business_name": "Cedar Creek Co",
            "business_type": "products",
            "website_url": "https://cedarcreek.test",
            "shop_urls": ["https://cedarcreek.test"],
            "completed_at": "2026-11-20T10:00:00Z",
            "competitors": [],
        },
        "preferences": {},
    },
}


@pytest.fixture
def own_pages_server(monkeypatch: pytest.MonkeyPatch):
    stores = {uid: {"document": doc, "version": 1, "owner_id": uid} for uid, doc in USERS.items()}
    sessions = {
        uid: AccountSession(
            user_id=uid,
            email=f"{uid}@audit.test",
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
        return {
            "configured": True,
            "user": {"id": session.user_id, "email": session.email, "email_verified": True},
            "usage": {"plan": "starter", "used": 0, "limit": 3, "remaining": 3},
            "runs_remaining": 3,
            "live_available": False,
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
        "src.services.outcomes",
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


def test_own_pages_never_show_sample_shop_and_sample_mode_keeps_sample_e2e(
    own_pages_server: str,
) -> None:
    python_bin = _find_playwright_python()
    if not python_bin:
        pytest.skip("Playwright runtime not installed")

    script = f"""
import json
from playwright.sync_api import sync_playwright

BASE = {own_pages_server!r}
PAGES = ["/today", "/create", "/digest", "/first-ad", "/progress", "/welcome?edit=1"]
ACCOUNTS = ["svc", "prod", "rich", "empty"]

SAMPLE_TERMS = [
    "sarabjit", "sikhiart", "sikh", "golden temple", "ek onkar",
    "pixels", "fine art america", "fineartamerica", "saatchi",
    "gurinderpreet", "manjot", "gurdish", "empowering women",
    "mai bhago", "$59.99", "gift buyers",
    "retargeting - site visitors", "retargeting – site visitors",
    "artist’s saved research", "artist's saved research",
    "handmade studio work",
]

def check_no_sample(label, text):
    low = (text or "").lower()
    for term in SAMPLE_TERMS:
        assert term not in low, f"{{label}} leaked sample term {{term!r}}: {{text[:300]!r}}"

with sync_playwright() as p:
    browser = p.chromium.launch()
    try:
        for uid in ACCOUNTS:
            for width in (375, 1440):
                ctx = browser.new_context(viewport={{"width": width, "height": 900}})
                ctx.add_cookies([{{"name": "muse_e2e_user", "value": uid, "url": BASE}}])
                page = ctx.new_page()
                # Prevent auto-import crawl on first visit (guarded for sandboxed iframes)
                init_js = (
                    "try {{ localStorage.setItem('muse.autoimport.tried.v1:"
                    + uid
                    + "', '1'); }} catch (_) {{}}"
                )
                page.add_init_script(init_js)
                for path in PAGES:
                    errors = []
                    page.on("pageerror", lambda e, errs=errors: errs.append(str(e)))
                    page.goto(BASE + path, wait_until="networkidle", timeout=20000)
                    page.wait_for_timeout(400)

                    # Expand <details> panels so hidden-until-opened leaks are caught
                    page.evaluate(
                        "document.querySelectorAll('details').forEach(d => d.open = true)"
                    )
                    page.wait_for_timeout(150)

                    tag = f"{{uid}}@{{width}} {{path}}"
                    body = page.evaluate("document.body.innerText || ''")
                    check_no_sample(tag + " body", body)

                    # Check visible inputs, textareas, placeholders, and select options
                    inputs_blob = page.evaluate('''() => {{
                        const parts = [];
                        document.querySelectorAll('input, textarea, select').forEach(el => {{
                            const r = el.getBoundingClientRect();
                            if (r.width === 0 && r.height === 0) return;
                            if (el.tagName === 'SELECT') {{
                                const opts = Array.from(el.options).map(o => o.textContent);
                                parts.push(opts.join(' '));
                            }} else {{
                                parts.push((el.value || '') + ' ' + (el.placeholder || ''));
                            }}
                        }});
                        return parts.join(' | ');
                    }}''')
                    check_no_sample(tag + " inputs", inputs_blob)

                    # Check visible images for sample paths
                    img_blob = page.evaluate('''() => {{
                        const imgs = Array.from(document.querySelectorAll('img')).filter(el => {{
                            const r = el.getBoundingClientRect();
                            return r.width > 0 && r.height > 0;
                        }});
                        return imgs.map(
                            el => (el.getAttribute('src') || '') + ' ' + (el.alt || '')
                        ).join(' | ');
                    }}''')
                    check_no_sample(tag + " imgs", img_blob)
                    assert "/samples/" not in img_blob.lower(), f"{{tag}} sample img: {{img_blob}}"

                    # Page-specific deep checks (modals, datalists, wizard steps)
                    if path == "/create":
                        assert not page.locator("#artistChannels").is_visible(), (
                            f"{{tag}} #artistChannels leaked"
                        )
                        dl_vals = page.evaluate(
                            "Array.from(document.querySelectorAll('#collectionSuggestions option'))"
                            ".map(o => o.value)"
                        )
                        assert "Empowering Women" not in dl_vals, (
                            f"{{tag}} datalist leaked: {{dl_vals}}"
                        )
                    elif path == "/first-ad":
                        page.click("[data-fa-step='3']")
                        page.wait_for_timeout(100)
                        aud = page.locator("#faAudience").input_value()
                        check_no_sample(tag + " step3 audience", aud)
                        page.click("[data-fa-step='4']")
                        page.wait_for_timeout(100)
                        summary = page.locator("#faHandoffSummary").inner_text()
                        check_no_sample(tag + " step4 summary", summary)
                        page.click("[data-fa-step='1']")
                    elif path == "/today":
                        page.click("#openSetup")
                        page.wait_for_timeout(100)
                        modal_text = page.locator("#setup").inner_text()
                        check_no_sample(tag + " setup modal", modal_text)
                        if uid in ("svc", "rich"):
                            assert "Use this listing" not in modal_text, (
                                f"{{tag}} services modal said Use this listing"
                            )
                            assert "Shop or product link" not in modal_text, (
                                f"{{tag}} services modal said Shop or product link"
                            )
                        page.click("#closeSetup")
                    elif path == "/welcome?edit=1":
                        focus_ph = page.locator("#wkPrefFocus").get_attribute("placeholder") or ""
                        check_no_sample(tag + " wkPrefFocus placeholder", focus_ph)
                        assert "prints" not in focus_ph.lower(), (
                            f"{{tag}} wkPrefFocus placeholder mentioned prints"
                        )
                    elif path == "/digest":
                        signup_lede = (
                            page.locator("#digestSignup .dg-sub-lede").text_content() or ""
                        )
                        check_no_sample(tag + " digestSignup lede", signup_lede)

                    if width == 375:
                        sw, iw = page.evaluate(
                            "[document.documentElement.scrollWidth, window.innerWidth]"
                        )
                        assert sw <= iw + 1, (
                            f"{{tag}} overflow: scrollWidth={{sw}} > innerWidth={{iw}}"
                        )
                    assert not errors, f"{{tag}} page errors: {{errors}}"
                ctx.close()

        # Sample shop checks: verify ?workspace=sample keeps its sample content
        sctx = browser.new_context(viewport={{"width": 1440, "height": 900}})
        spage = sctx.new_page()

        spage.goto(BASE + "/today?workspace=sample", wait_until="networkidle", timeout=20000)
        spage.wait_for_timeout(500)
        stxt = spage.evaluate("document.body.innerText")
        assert any(k in stxt for k in ("Ek Onkar", "Sarabjit", "SikhiArt", "Pixels")), stxt[:400]

        spage.goto(BASE + "/create?workspace=sample", wait_until="networkidle", timeout=20000)
        spage.wait_for_timeout(500)
        spage.evaluate("document.querySelectorAll('details').forEach(d => d.open = true)")
        stxt = spage.evaluate("document.body.innerText")
        assert "Ek Onkar" in stxt and "Pixels" in stxt, stxt[:400]
        assert spage.locator("#artistChannels").is_visible()

        spage.goto(BASE + "/digest?workspace=sample", wait_until="networkidle", timeout=20000)
        spage.wait_for_timeout(500)
        stxt = spage.evaluate("document.body.innerText")
        assert "SikhiArt.com" in stxt and "Gurinderpreet" in stxt, stxt[:400]

        spage.goto(BASE + "/first-ad?workspace=sample", wait_until="networkidle", timeout=20000)
        spage.wait_for_timeout(500)
        stxt = spage.evaluate("document.body.innerText")
        assert "Art of Sarabjit Singh" in stxt, stxt[:400]

        spage.goto(BASE + "/progress?workspace=sample", wait_until="networkidle", timeout=20000)
        spage.wait_for_timeout(400)
        stxt = spage.evaluate("document.body.innerText")
        assert "Progress & ROI Tracker" in stxt, stxt[:400]
        assert spage.evaluate("window.museModes?.isSampleMode?.()") is True

        spage.goto(BASE + "/welcome?workspace=sample", wait_until="networkidle", timeout=20000)
        spage.wait_for_timeout(400)
        stxt = spage.evaluate("document.body.innerText")
        assert "Explore Sample shop instead" in stxt, stxt[:400]

        sctx.close()
    finally:
        browser.close()
print("ALL_OWN_PAGES_OK")
"""
    proc = subprocess.run(
        [python_bin, "-c", script],
        capture_output=True,
        text=True,
        timeout=240,
        check=False,
    )
    assert proc.returncode == 0, f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
    assert "ALL_OWN_PAGES_OK" in proc.stdout
