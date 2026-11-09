#!/usr/bin/env python3
"""Offline browser acceptance audit. Run with system Python; no app server or keys.

Serves a frozen copy of actual static UI + samples on loopback. All API requests
are fulfilled by explicit browser fixtures; external traffic and unknown writes
fail closed. API fixtures establish UI behavior, not backend/service readiness.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import shutil
import struct
import subprocess
import tempfile
import threading
import traceback
import zlib
from datetime import datetime, timezone
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

from playwright.sync_api import Page, expect, sync_playwright

ROOT = Path(__file__).resolve().parents[1]
TITLE = "Launch QA cyan tile"
HOOK = "Edited opening — QA 742"
CAPTION = "My handmade tile, edited by its maker. QA 742."
LINK = "https://shop.example.test/tile"


def photo() -> bytes:
    """Distinctive solid cyan source lets exports prove correct photo content."""

    def chunk(kind: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))
        )

    raw = (b"\0" + bytes([10, 210, 230]) * 64) * 64
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", 64, 64, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(raw))
        + chunk(b"IEND", b"")
    )


class StaticHandler(SimpleHTTPRequestHandler):
    def do_GET(self) -> None:
        path = urlsplit(self.path).path
        if path in ("/today", "/create", "/"):
            self.path = {
                "/today": "/static/today.html",
                "/create": "/static/creator.html",
                "/": "/static/index.html",
            }[path]
        elif not path.startswith(("/static/", "/samples/")):
            self.send_error(404)
            return
        super().do_GET()

    def log_message(self, *args: object) -> None:
        pass


class Audit:
    def __init__(self, browser: object, origin: str, output: Path) -> None:
        self.browser, self.origin, self.output = browser, origin, output
        self.results: list[dict] = []
        self.requests: list[dict] = []
        self.fault = ""
        self.account_configured = False

    def extra_cases(self) -> list:
        return []

    def route(self, route: object) -> None:
        req = route.request
        url = urlsplit(req.url)
        record = {"method": req.method, "path": url.path}
        self.requests.append(record)
        if url.scheme in ("data", "blob"):
            route.continue_()
            return
        if f"{url.scheme}://{url.netloc}" != self.origin:
            record["blocked"] = "external"
            route.abort("blockedbyclient")
            return
        if not url.path.startswith("/api/"):
            if req.method != "GET":
                record["blocked"] = "unexpected write"
                route.abort("blockedbyclient")
            else:
                route.continue_()
            return
        record["fixture"] = True
        payload = req.post_data_json if req.method == "POST" else {}
        if "live=true" in url.query or (payload or {}).get("use_muse"):
            record["blocked"] = "paid request"
            route.abort("blockedbyclient")
            return
        path = url.path
        if path == "/api/v1/ingest-storefront" and req.method == "POST":
            if self.fault == "abort":
                route.abort("connectionfailed")
            elif self.fault == "invalid-json":
                route.fulfill(
                    status=502, content_type="text/html", body="<h1>Gateway unavailable</h1>"
                )
            else:
                route.fulfill(
                    status=503,
                    json={"detail": "Fixture shop unavailable. Enter product details manually."},
                )
            return
        if path == "/api/v1/content-plan" and req.method == "POST":
            if self.fault == "plan-outage":
                route.fulfill(
                    status=503,
                    json={"detail": "Fixture service unavailable. Retry after reconnecting."},
                )
                return
            product = payload["product"]
            channel = payload["channels"][0]
            route.fulfill(
                json={
                    "mode": "starter",
                    "posts": [
                        {
                            "day_offset": i * 2,
                            "channel": channel,
                            "format": "image",
                            "hook": f"{product['title']} — fixture post {i + 1}",
                            "caption": product.get("description") or "Fixture starter caption",
                            "cta": "Visit my shop",
                            "visual_direction": "Use your original photo.",
                            "posting_tip": "Review then post manually.",
                        }
                        for i in range(3)
                    ],
                    "insight": {"next_action": "Share one post."},
                    "sources": [],
                }
            )
            return
        fixtures = {
            "/api/v1/readiness": {"provider_key_configured": False, "default_mode": "demo"},
            "/api/v1/account/me": {
                "configured": self.account_configured,
                "user": None,
                "usage": None,
                "live_available": False,
            },
            "/api/v1/demo-presets": {"workspaces": {}},
            "/api/v1/credits": {"balance": 3, "remaining": 3},
            "/api/v1/monitor": {"changes": []},
            "/api/v1/weekly-digest": {},
            "/api/v1/daily-brief": {},
        }
        if req.method == "GET" and path in fixtures:
            route.fulfill(json=fixtures[path])
        else:
            record["blocked"] = "unexpected API"
            route.fulfill(status=503, json={"detail": "QA deny-by-default: no backend connected."})

    def run(self, name: str, width: int, callback: object, configured: bool = False) -> None:
        self.fault, self.account_configured = "", configured
        self.requests = []
        context = self.browser.new_context(
            viewport={"width": width, "height": 900}, accept_downloads=True, service_workers="block"
        )
        context.route("**/*", self.route)
        context.tracing.start(screenshots=True, snapshots=True, sources=True)
        page = context.new_page()
        page.set_default_timeout(6000)
        errors: list[str] = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        case_dir = self.output / name
        case_dir.mkdir(parents=True, exist_ok=True)
        self.case_dir = case_dir
        result = {"name": name, "width": width, "status": "pass"}
        try:
            callback(page)
            assert not errors, f"Uncaught browser errors: {errors}"
            unexpected = [r for r in self.requests if r.get("blocked")]
            assert not unexpected, f"Blocked unexpected requests: {unexpected}"
        except Exception as exc:
            result.update(status="fail", error=str(exc), traceback=traceback.format_exc())
        finally:
            result["page_errors"] = errors
            result["requests"] = list(self.requests)
            result["url_path"] = urlsplit(page.url).path
            page.screenshot(path=str(case_dir / "final.png"), full_page=True)
            (case_dir / "dom.html").write_text(page.content())
            context.tracing.stop(path=str(case_dir / "trace.zip"))
            context.close()
        self.results.append(result)
        print(
            f"{result['status'].upper():4} {name}"
            + (f": {result['error'][:160]}" if "error" in result else ""),
            flush=True,
        )

    def goto(self, page: Page, path: str) -> None:
        page.goto(self.origin + path)
        expect(
            page.locator("#productName" if path == "/create" else "#postHook")
        ).not_to_have_value("")
        if path == "/today":
            expect(page.locator("#planCards button")).to_have_count(3)
            expect(page.locator("#openSetup")).to_be_enabled()
        else:
            expect(page.locator("#customProduct")).to_be_enabled()

    def layout(self, page: Page) -> None:
        metrics = page.evaluate("""() => ({
          width: innerWidth, scroll: document.documentElement.scrollWidth,
          offenders: [...document.querySelectorAll('body *')].filter(e => {
            const r = e.getBoundingClientRect();
            return (
              r.width > 0 &&
              r.right > innerWidth + 2 &&
              getComputedStyle(e).position !== 'fixed'
            );
          }).slice(0, 12).map(e => ({tag: e.tagName, id: e.id, class: e.className}))
        })""")
        assert metrics["scroll"] <= metrics["width"] + 2, f"Horizontal overflow: {metrics}"

    def setup(self, page: Page, path: str) -> None:
        self.goto(page, path)
        if path == "/create":
            page.locator("#customProduct").click()
            if page.locator("#moreDetails").get_attribute("open") is None:
                page.locator("#moreDetails summary").click()
            page.locator("#promotionDestination").select_option("other")
        else:
            page.locator("#openSetup").click()
            page.locator("#manualItem").click()
            page.locator("#destination").select_option("other")
        for field, value in [
            ("productName", TITLE),
            ("sellerName", "QA maker"),
            ("productDescription", "One handmade cyan tile."),
            ("productLink", LINK),
        ]:
            page.locator("#" + field).fill(value)
        page.locator("#productPrice" if path == "/create" else "#price").fill("$17")
        if path == "/today":
            page.locator("#itemForm button.primary").click()
            expect(page.locator("#itemTitle")).to_have_text(TITLE)
            expect(page.locator("#photo")).to_be_enabled()
        page.locator("#productPhoto" if path == "/create" else "#photo").set_input_files(
            {"name": "qa-cyan.png", "mimeType": "image/png", "buffer": photo()}
        )
        if path == "/create":
            expect(page.locator("#productImage")).to_have_attribute(
                "src", __import__("re").compile("^data:image/")
            )
            page.locator("#nextButton").click()
            page.locator('[data-goal="gift"]').click()
            page.locator("#nextButton").click()
        else:
            expect(page.locator("#notice")).to_contain_text("Photo ready")
            page.locator("#planCards button").nth(2).click()
        page.locator("#headline" if path == "/create" else "#postHook").fill(HOOK)
        page.locator("#caption" if path == "/create" else "#postCaption").fill(CAPTION)
        self.layout(page)

    def download(self, page: Page, selector: str, filename: str) -> Path:
        with page.expect_download() as info:
            page.locator(selector).click()
        download = info.value
        assert download.failure() is None
        target = self.case_dir / filename
        download.save_as(target)
        assert target.stat().st_size > 20
        return target

    def png(self, page: Page, path: Path, height: int) -> None:
        raw = path.read_bytes()
        assert raw[:8] == b"\x89PNG\r\n\x1a\n", "Download is not a PNG"
        assert struct.unpack(">II", raw[16:24]) == (1080, height)
        data = "data:image/png;base64," + base64.b64encode(raw).decode()
        pixel = page.evaluate(
            """async src => {const i=new Image();i.src=src;await i.decode();
            const c=document.createElement('canvas');c.width=i.width;c.height=i.height;
            const x=c.getContext('2d');x.drawImage(i,0,0);
            return [...x.getImageData(540,450,1,1).data];}""",
            data,
        )
        assert abs(pixel[0] - 10) < 15 and abs(pixel[1] - 210) < 15 and abs(pixel[2] - 230) < 15, (
            f"Wrong source photo in PNG: {pixel}"
        )

    def journey(self, page: Page, path: str) -> None:
        self.setup(page, path)
        page.locator("#reviewed").check()
        if path == "/create":
            page.locator("#nextButton").click()
            self.layout(page)
            self.png(page, self.download(page, "#downloadFeed", "feed.png"), 1350)
            self.png(page, self.download(page, "#downloadStory", "story.png"), 1920)
            pack = json.loads(self.download(page, "#downloadPack", "campaign.json").read_text())
            assert pack["headline"] == HOOK and pack["caption"] == CAPTION
            assert pack["product"]["name"] == TITLE and pack["product"]["link"] == LINK
            text = self.download(page, "#downloadInstructions", "instructions.txt").read_text()
            assert HOOK in text and CAPTION in text and LINK in text
        else:
            # Clipboard denial is deliberate: test the supported text-file fallback.
            page.evaluate(
                "Object.defineProperty(navigator, 'clipboard', "
                "{value:{writeText:()=>Promise.reject(new Error('QA denied'))}, "
                "configurable:true})"
            )
            self.png(page, self.download(page, "#getPost", "feed.png"), 1350)
            expect(page.locator("#getPost")).to_be_enabled()
            text = self.download(page, "#copyOnly", "caption.txt").read_text()
            assert HOOK in text and CAPTION in text
            plan = self.download(page, "#downloadPlan", "plan.txt").read_text()
            assert HOOK in plan and CAPTION in plan and LINK in plan

    def reload(self, page: Page, path: str) -> None:
        self.setup(page, path)
        page.reload()
        page.wait_for_load_state("networkidle")
        fields = {
            "product": page.locator("#productName").input_value(),
            "headline": page.locator(
                "#headline" if path == "/create" else "#postHook"
            ).input_value(),
            "caption": page.locator(
                "#caption" if path == "/create" else "#postCaption"
            ).input_value(),
        }
        # Daily setup fields are populated only when its dialog opens.
        if path == "/today":
            fields["product"] = page.locator("#itemTitle").inner_text()
            fields["selected"] = page.locator('#planCards button[aria-pressed="true"]').inner_text()
            assert HOOK in fields["selected"], fields
            assert page.locator("#destinationLink").get_attribute("href") == LINK
        else:
            fields["destination"] = page.locator("#productLink").input_value()
            assert fields["destination"] == LINK, fields
        assert (
            fields["product"] == TITLE
            and fields["headline"] == HOOK
            and fields["caption"] == CAPTION
        ), fields
        assert not page.locator("#reviewed").is_checked(), "Reload must require fresh review"
        if path == "/create":
            page.locator('[data-step="2"]').click()
            page.locator("#reviewed").check()
            page.locator("#nextButton").click()
            self.png(page, self.download(page, "#downloadFeed", "reloaded.png"), 1350)
        else:
            page.locator("#reviewed").check()
            self.png(page, self.download(page, "#getPost", "reloaded.png"), 1350)

    def network_failure(self, page: Page, path: str, fault: str) -> None:
        self.setup(page, path)
        self.fault = fault
        if path == "/create":
            page.locator('[data-step="0"]').click()
            page.locator("#shopUrl").fill("https://offline.example.test")
            page.locator("#importProducts").click()
            expect(page.locator("#importProducts")).to_be_enabled(timeout=15000)
            expect(page.locator("#notice")).to_be_visible()
            assert page.locator("#notice").inner_text().strip()
            page.locator('[data-step="2"]').click()
        else:
            page.locator("#openSetup").click()
            page.locator("#shopUrl").fill("https://offline.example.test")
            page.locator("#findItems").click()
            expect(page.locator("#findItems")).to_be_enabled(timeout=15000)
            expect(page.locator("#importStatus")).not_to_have_text(
                "Finding a product for your next post…"
            )
            page.locator("#closeSetup").click()
        expect(page.locator("#headline" if path == "/create" else "#postHook")).to_have_value(HOOK)
        expect(page.locator("#caption" if path == "/create" else "#postCaption")).to_have_value(
            CAPTION
        )
        page.locator("#reviewed").check()
        if path == "/create":
            page.locator("#nextButton").click()
        self.png(
            page,
            self.download(
                page, "#downloadFeed" if path == "/create" else "#getPost", "after-outage.png"
            ),
            1350,
        )

    def plan_failure(self, page: Page) -> None:
        self.setup(page, "/today")
        self.fault = "plan-outage"
        page.locator('[data-channel="facebook"]').click()
        expect(page.locator('[data-channel="facebook"]')).to_be_enabled(timeout=15000)
        expect(page.locator("#notice")).to_contain_text("unavailable")
        page.locator('[data-channel="instagram"]').click()
        page.locator("#planCards button").nth(2).click()
        expect(page.locator("#postHook")).to_have_value(HOOK)
        expect(page.locator("#postCaption")).to_have_value(CAPTION)

    def signup(self, page: Page) -> None:
        self.goto(page, "/today")
        page.locator(".ma-account-button").click()
        page.locator(".ma-tabs").get_by_role("button", name="Create account", exact=True).click()
        expect(page.locator("#ma-password")).to_have_attribute("minlength", "12")
        assert page.evaluate("document.activeElement.closest('dialog') !== null")
        for _ in range(12):
            page.keyboard.press("Tab")
            assert page.evaluate("document.activeElement.closest('dialog') !== null"), (
                "Focus escapes dialog"
            )
        page.keyboard.press("Escape")
        expect(page.locator(".ma-dialog")).not_to_be_visible()
        expect(page.locator(".ma-account-button")).to_be_focused()
        page.locator(".ma-account-button").click()
        page.locator(".ma-recover").click()
        expect(page.locator("#ma-title")).to_have_text("Reset your password.")
        expect(page.locator("#ma-password")).not_to_be_visible()
        page.keyboard.press("Escape")
        assert not [
            r
            for r in self.requests
            if r["method"] != "GET" and r["path"].startswith("/api/v1/account")
        ], "Surface-only test submitted a write"


def main(audit_class: type = Audit) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output", type=Path, default=Path(tempfile.gettempdir()) / "muse-launch-audit"
    )
    parser.add_argument("--browser", choices=["chromium", "firefox", "webkit"], default="chromium")
    parser.add_argument("--match", default="", help="Run only case names containing this text")
    args = parser.parse_args()
    args.output = args.output.resolve()
    args.output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="muse-launch-static-") as directory:
        frozen = Path(directory)
        shutil.copytree(ROOT / "src/api/static", frozen / "static")
        shutil.copytree(ROOT / "data/samples", frozen / "samples")
        fingerprints = {
            str(p.relative_to(frozen)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted((frozen / "static").rglob("*"))
            if p.is_file()
        }
        server = ThreadingHTTPServer(
            ("127.0.0.1", 0), partial(StaticHandler, directory=str(frozen))
        )
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            with sync_playwright() as pw:
                browser = getattr(pw, args.browser).launch()
                audit = audit_class(browser, f"http://127.0.0.1:{server.server_port}", args.output)
                cases = []
                for width in (375, 390, 768, 1440):
                    for path in ("/today", "/create"):
                        cases.append(
                            (
                                f"{path[1:]}-journey-{width}",
                                width,
                                lambda p, path=path: audit.journey(p, path),
                                False,
                            )
                        )
                for path in ("/today", "/create"):
                    for width in (390, 1440):
                        cases.append(
                            (
                                f"{path[1:]}-reload-{width}",
                                width,
                                lambda p, path=path: audit.reload(p, path),
                                False,
                            )
                        )
                    for fault in ("503", "invalid-json", "abort"):
                        cases.append(
                            (
                                f"{path[1:]}-network-{fault}",
                                390,
                                lambda p, path=path, fault=fault: audit.network_failure(
                                    p, path, fault
                                ),
                                False,
                            )
                        )
                cases.extend(
                    [
                        ("today-plan-outage", 390, audit.plan_failure, False),
                        ("signup-keyboard-surfaces", 390, audit.signup, True),
                    ]
                )
                cases.extend(audit.extra_cases())
                selected = [case for case in cases if args.match in case[0]]
                if not selected:
                    parser.error("--match selected no cases")
                for name, width, callback, configured in selected:
                    audit.run(name, width, callback, configured)
                report = {
                    "timestamp_utc": datetime.now(timezone.utc).isoformat(),  # noqa: UP017
                    "git_head": subprocess.check_output(
                        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
                    ).strip(),
                    "browser": args.browser,
                    "browser_version": browser.version,
                    "environment": "isolated frozen static UI; fixture APIs; no runtime server",
                    "source_sha256": fingerprints,
                    "results": audit.results,
                    "passed": sum(r["status"] == "pass" for r in audit.results),
                    "failed": sum(r["status"] == "fail" for r in audit.results),
                }
                (args.output / "report.json").write_text(json.dumps(report, indent=2))
                browser.close()
                print(
                    f"{report['passed']} passed, {report['failed']} failed; evidence: {args.output}"
                )
                return int(report["failed"] > 0)
        finally:
            server.shutdown()
            server.server_close()


if __name__ == "__main__":
    raise SystemExit(main())
