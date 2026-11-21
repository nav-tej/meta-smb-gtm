"""CDN caching for API responses that are the same for every visitor.

Each /api/v1 request on Vercel runs the Python function once. A response that never reads the
account, cookies or a demo key (the sample shop's presets, previews, brief, change log and
digest, and public configuration) can be answered by Vercel's CDN instead.

Two headers, so browsers and the CDN each get what they need:
- `Vercel-CDN-Cache-Control` is read only by Vercel's CDN (top priority, never sent to the
  browser): keep the response five minutes, then serve it stale while one request refreshes it.
- `Cache-Control: public, max-age=0` is what the browser sees: always ask again, never serve a
  stale copy. (With `stale-while-revalidate` in `Cache-Control`, a local server sends it straight
  to the browser, which then revalidates in the background; Playwright never sees that request
  finish, so `networkidle` waits forever.)

Never use this on a response that depends on who is asking: the CDN cache key ignores cookies,
so one visitor's answer would be served to the next. Vercel also refuses to cache a response
that sets a cookie or says `private`/`no-store`, which keeps account routes uncached.
"""

from __future__ import annotations

from fastapi import Response

SHARED_BROWSER_CACHE_CONTROL = "public, max-age=0"
SHARED_VERCEL_CDN_CACHE_CONTROL = "max-age=300, stale-while-revalidate=600"
PRIVATE_API_CACHE_CONTROL = "private, no-store"


def cache_for_everyone(response: Response) -> None:
    """Let Vercel's CDN serve this response to every visitor for five minutes."""
    response.headers["Cache-Control"] = SHARED_BROWSER_CACHE_CONTROL
    response.headers["Vercel-CDN-Cache-Control"] = SHARED_VERCEL_CDN_CACHE_CONTROL


def never_cache(response: Response) -> None:
    """This response depends on the visitor; no shared cache may keep it."""
    response.headers["Cache-Control"] = PRIVATE_API_CACHE_CONTROL
