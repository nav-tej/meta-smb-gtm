#!/usr/bin/env python3
"""Run base browser audit plus bounded, memory-only account acceptance cases.

No auth service is connected. Identity changes are supplied through /account/me;
the real account adapter refreshes, emits events, and reloads the real editors.
Only workspace PUT and signout POST are intercepted; signup/payment stay denied.
"""

from __future__ import annotations

import json
from copy import deepcopy
from urllib.parse import urlsplit

from launch_browser_audit import CAPTION, HOOK, Audit, main
from playwright.sync_api import Page, expect


class AccountAudit(Audit):
    def run(self, name: str, width: int, callback: object, configured: bool = False) -> None:
        self.owner = None
        self.workspaces = {}
        self.writes = []
        self.race = None
        super().run(name, width, callback, configured)

    def route(self, route: object) -> None:
        req = route.request
        url = urlsplit(req.url)
        if (
            f"{url.scheme}://{url.netloc}" != self.origin
            or url.query
            or url.path
            not in ("/api/v1/account/me", "/api/v1/account/workspace", "/api/v1/account/signout")
        ):
            super().route(route)
            return
        record = {"method": req.method, "path": url.path, "fixture": True, "owner": self.owner}
        self.requests.append(record)
        if url.path.endswith("/me") and req.method == "GET":
            route.fulfill(
                json={
                    "configured": self.account_configured,
                    "user": {
                        "id": self.owner,
                        "email": self.owner + "@example.test",
                        "email_verified": True,
                    }
                    if self.owner
                    else None,
                    "usage": None,
                    "live_available": False,
                }
            )
        elif url.path.endswith("/signout") and req.method == "POST":
            self.owner = None
            route.fulfill(json={"ok": True})
        elif url.path.endswith("/workspace") and req.method in ("GET", "PUT"):
            if not self.owner:
                route.fulfill(status=401, json={"detail": "Fixture session expired"})
                return
            workspace = self.workspaces.setdefault(self.owner, {"version": 0, "document": {}})
            if req.method == "GET":
                route.fulfill(json=deepcopy(workspace))
                return
            payload = req.post_data_json
            self.writes.append({"owner": self.owner, **deepcopy(payload)})
            if self.race is not None:
                # Another device commits between the editor's read and conditional PUT.
                workspace.update(document=deepcopy(self.race), version=workspace["version"] + 1)
                self.race = None
            record["expected_version"] = payload.get("expected_version")
            if payload.get("expected_version") != workspace["version"]:
                record["status"] = 409
                route.fulfill(status=409, json={"detail": "Fixture workspace conflict"})
            else:
                workspace.update(
                    document=deepcopy(payload["document"]), version=workspace["version"] + 1
                )
                record["status"] = 200
                route.fulfill(json=deepcopy(workspace))
        else:
            record["blocked"] = "unexpected account operation"
            route.abort("blockedbyclient")

    def extra_cases(self) -> list:
        cases = []
        for path in ("/today", "/create"):
            for label, method in [
                ("isolation", self.isolation),
                ("conflict", self.conflict),
                ("409-race", self.save_race),
            ]:
                cases.append(
                    (
                        f"account-{path[1:]}-{label}",
                        390,
                        lambda p, path=path, method=method: method(p, path),
                        True,
                    )
                )
        cases.append(("account-editor-merge", 1440, self.editor_merge, True))
        return cases

    @staticmethod
    def namespace(path: str) -> str:
        return "daily" if path == "/today" else "creator"

    @staticmethod
    def hook(path: str) -> str:
        return "#postHook" if path == "/today" else "#headline"

    def local(self, page: Page, path: str) -> dict:
        key = f"muse-editor-v1:{self.namespace(path)}:account:{self.owner}"
        return page.evaluate("key => JSON.parse(localStorage.getItem(key))", key)

    def remote_copy(self, document: dict, path: str, text: str) -> dict:
        result = deepcopy(document)
        if path == "/create":
            result["headline"] = text
        else:
            key = f"{result['channel']}:{result['selected']}:{result['format']}"
            result["edits"][key]["hook"] = text
        return result

    def status(self, page: Page, text: str) -> None:
        expect(page.locator("#draftStatus")).to_contain_text(text)

    def save(self, page: Page) -> None:
        page.locator("#saveAccountDraft").click()
        self.status(page, "Saved to your account")

    def switch_owner(self, page: Page, owner: str) -> None:
        self.owner = owner
        # Real UI refresh; no artificial account-change event or storage mutation.
        page.locator(".ma-account-button").click()
        with page.expect_navigation(wait_until="networkidle"):
            page.locator(".ma-refresh").click()
        expect(page.locator("main")).to_be_visible()
        page.wait_for_function("window.museAccount.getSnapshot().user?.id === " + json.dumps(owner))

    def isolation(self, page: Page, path: str) -> None:
        self.owner = "qa-a"
        self.setup(page, path)
        self.save(page)
        a_cloud = deepcopy(self.workspaces["qa-a"])
        a_local = self.local(page, path)
        with page.expect_navigation(wait_until="networkidle"):
            page.locator(".ma-signout").click()
        expect(page.locator(self.hook(path))).not_to_have_value(HOOK)
        assert not self.owner
        assert not page.evaluate(
            "Object.keys(localStorage).filter(k=>k.endsWith(':guest'))"
            ".some(k=>(localStorage.getItem(k)||'').includes('QA 742'))"
        ), "Private draft leaked to guest storage"
        self.switch_owner(page, "qa-b")
        expect(page.locator(self.hook(path))).not_to_have_value(HOOK)
        page.locator("#loadAccountDraft").click()
        self.status(page, "No account draft")
        page.locator("#postHook" if path == "/today" else "#productName").fill("B private draft")
        self.save(page)
        assert "QA 742" not in json.dumps(self.workspaces["qa-b"]), (
            "A content transferred into B workspace"
        )
        assert self.workspaces["qa-a"] == a_cloud, "Switching account altered A cloud draft"
        self.switch_owner(page, "qa-a")
        expect(page.locator(self.hook(path))).to_have_value(HOOK)
        assert self.local(page, path) == a_local, "A device draft changed across account switch"
        page.locator("#loadAccountDraft").click()
        self.status(page, "Account draft loaded")
        expect(page.locator(self.hook(path))).to_have_value(HOOK)

    def conflict(self, page: Page, path: str) -> None:
        self.owner = "qa-a"
        self.setup(page, path)
        local = self.local(page, path)
        namespace = self.namespace(path)
        remote = self.remote_copy(local, path, "Remote first revision")
        sibling = {"schema": 1, "sentinel": "other-editor-must-survive"}
        other = "creator" if namespace == "daily" else "daily"
        document = {"documents": {namespace: remote, other: sibling}, "unknown": {"keep": 42}}
        self.workspaces[self.owner] = {"version": 7, "document": deepcopy(document)}
        page.locator("#saveAccountDraft").click()
        self.status(page, "A different account draft exists")
        expect(page.locator("#replaceAccountDraft")).to_be_visible()
        assert not self.writes, "Conflict silently overwrote the server"
        expect(page.locator(self.hook(path))).to_have_value(HOOK)
        backup = json.loads(
            self.download(page, "#downloadDraft", "local-before-conflict.json").read_text()
        )
        assert backup == local
        # Replacement consent must be tied to the revision the user saw.
        newer = self.remote_copy(local, path, "Remote second revision")
        document["documents"][namespace] = newer
        self.workspaces[self.owner] = {"version": 8, "document": deepcopy(document)}
        page.locator("#replaceAccountDraft").click()
        self.status(page, "A different account draft exists")
        assert not self.writes, "Replacement overwrote a newer unseen revision"
        page.locator("#loadAccountDraft").click()
        self.status(page, "Account draft loaded")
        expect(page.locator(self.hook(path))).to_have_value("Remote second revision")
        page.locator("#recoverDraft").click()
        expect(page.locator(self.hook(path))).to_have_value(HOOK)
        self.save(page)
        saved = self.workspaces[self.owner]["document"]
        assert saved["documents"][namespace] == local
        assert saved["documents"][other] == sibling and saved["unknown"] == {"keep": 42}
        assert self.writes[-1]["expected_version"] == 8

    def save_race(self, page: Page, path: str) -> None:
        self.owner = "qa-a"
        self.setup(page, path)
        self.save(page)
        namespace = self.namespace(path)
        original = deepcopy(self.workspaces[self.owner]["document"])
        remote = self.remote_copy(original["documents"][namespace], path, "Concurrent device wins")
        self.race = {"documents": {namespace: remote}, "unrelated": "retain-me"}
        page.locator(self.hook(path)).fill("Unsaved after race")
        local = self.local(page, path)
        page.locator("#saveAccountDraft").click()
        self.status(page, "Save conflict: another device saved first")
        expect(page.locator(self.hook(path))).to_have_value("Unsaved after race")
        expect(page.locator("#replaceAccountDraft")).not_to_be_visible()
        assert self.workspaces[self.owner]["document"]["documents"][namespace] == remote
        assert len(self.writes) == 2, "409 retried a write automatically"
        assert self.writes[-1]["expected_version"] == 1
        backup = json.loads(
            self.download(page, "#downloadDraft", "local-after-409.json").read_text()
        )
        assert backup == local
        page.locator("#saveAccountDraft").click()
        self.status(page, "A different account draft exists")
        assert len(self.writes) == 2
        page.locator("#replaceAccountDraft").click()
        self.status(page, "Saved to your account")
        assert self.writes[-1]["expected_version"] == 2
        assert self.workspaces[self.owner]["document"]["documents"][namespace] == local
        assert self.workspaces[self.owner]["document"]["unrelated"] == "retain-me"

    def editor_merge(self, page: Page) -> None:
        self.owner = "qa-a"
        self.setup(page, "/today")
        self.save(page)
        daily = deepcopy(self.workspaces[self.owner]["document"]["documents"]["daily"])
        self.setup(page, "/create")
        self.save(page)
        saved = self.workspaces[self.owner]["document"]
        assert saved["documents"]["daily"] == daily
        assert saved["documents"]["creator"]["headline"] == HOOK
        assert [w["expected_version"] for w in self.writes] == [0, 1]
        # Separate browser context with empty device storage: account-load contract.
        fresh = page.context.browser.new_context(service_workers="block")
        fresh.route("**/*", self.route)
        try:
            device = fresh.new_page()
            for path in ("/today", "/create"):
                self.goto(device, path)
                expect(device.locator(self.hook(path))).not_to_have_value(HOOK)
                device.locator("#loadAccountDraft").click()
                self.status(device, "Account draft loaded")
                expect(device.locator(self.hook(path))).to_have_value(HOOK)
                expect(
                    device.locator("#postCaption" if path == "/today" else "#caption")
                ).to_have_value(CAPTION)
                device.screenshot(path=str(self.case_dir / f"fresh-{path[1:]}.png"), full_page=True)
            assert len(self.writes) == 2, "Loading on another device wrote a workspace"
        finally:
            fresh.close()


if __name__ == "__main__":
    raise SystemExit(main(AccountAudit))
