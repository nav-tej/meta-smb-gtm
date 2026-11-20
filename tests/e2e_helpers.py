"""Shared helpers for deterministic Playwright E2E tests under CPU load."""

from __future__ import annotations

import textwrap

# Embeddable snippet for Playwright subprocess scripts: when MUSE_E2E_CPU_THROTTLE > 1
# is set in the environment, applies Chromium CDP Emulation.setCPUThrottlingRate to
# every page created from any BrowserContext or Browser.
CDP_THROTTLE_SNIPPET = """
import os as _e2e_os
_E2E_THROTTLE_RATE = float(_e2e_os.environ.get("MUSE_E2E_CPU_THROTTLE", "1") or "1")

def _apply_cdp_cpu_throttle(page):
    if _E2E_THROTTLE_RATE > 1:
        try:
            cdp = page.context.new_cdp_session(page)
            cdp.send("Emulation.setCPUThrottlingRate", {"rate": _E2E_THROTTLE_RATE})
        except Exception:
            pass
    return page

if _E2E_THROTTLE_RATE > 1:
    from playwright.sync_api import Browser as _E2EBrowser, BrowserContext as _E2EContext
    _orig_ctx_np = _E2EContext.new_page
    _orig_br_np = _E2EBrowser.new_page

    def _ctx_new_page(self, *a, **kw):
        return _apply_cdp_cpu_throttle(_orig_ctx_np(self, *a, **kw))

    def _br_new_page(self, *a, **kw):
        return _apply_cdp_cpu_throttle(_orig_br_np(self, *a, **kw))

    _E2EContext.new_page = _ctx_new_page
    _E2EBrowser.new_page = _br_new_page
"""


def with_cpu_throttle(script: str) -> str:
    """Dedent a Playwright subprocess script and prepend optional CDP CPU throttling."""
    return CDP_THROTTLE_SNIPPET + "\n" + textwrap.dedent(script)
