# Antigravity Report: Saved Competitor Checks in Own `/today` Brief & Seller YouTube Videos (Nov 23)

> **Claude review, Nov 23 (coordinator).** Item 1 is merged into `claude/ux-gap-ad-loop-nov17`
> (cherry-picked `aaa5c56`, `dd5e32a`, `2461b39`), with one change: a saved `unchanged` check
> showed the sample brief's "Fresh Muse brief" chip, and a failed check showed "Not checked yet".
> They now read "No change" and "Couldn't check" (`muse-shell.js` `20261123-uxgap22`).
> **Item 2 (YouTube) is not merged.** YouTube's robots.txt (checked Nov 23) has
> `Disallow: /feeds/videos.xml` for `User-agent: *`, and AGENTS.md says to honor robots.txt. The
> code checked robots for the channel page but not for the feed it then fetched. That was a flaw
> in Claude's brief, not in the implementation. Item 2 stays on `gemini/own-sources-nov23` at
> `5ca48b6` until Nav picks a sanctioned route. Everything below is Antigravity's report as written.

- **Brief:** `docs/launch/antigravity-own-sources-nov23.md`
- **Base:** `origin/claude/ux-gap-ad-loop-nov17` at `1e8e0a7`
- **Branch:** `gemini/own-sources-nov23`
- **Worktree:** `/Users/nav/muse-worktrees/own-sources`
- **Checkpoints:**
  - Checkpoint 1 (`aaa5c56`): Item 1 — saved competitor checks in own `/today` brief + unit/brief tests.
  - Checkpoint 2 (`5ca48b6`): Item 2 — public YouTube Atom/RSS feed reader, `POST /api/v1/seller-memory/sources/youtube`, `GET /api/v1/seller-memory` `content_sources`, `seller-memory.js` UI + version bump + unit/route/Chromium E2E tests.
  - Checkpoint 3 (this commit): updated `tests/test_today_own_brief_e2e.py` for the new `overnight_note` wording + full verification results and report.

## 1. Own `/today` brief shows saved competitor checks (read-only)

- Updated `src/services/daily_brief.py`:
  - Added optional `checked_at: str | None = None` to `WatchItem`, with a `@model_serializer(mode="wrap")` that omits `"checked_at"` when `None` so the sample brief JSON remains **byte-identical** (`SAMPLE_SHA256 = 0effdbdc3d0017f98f8e86f7f1f50f8386d5824f3f0e1ac7b2a7d04ec8e78615`).
  - `_own_brief()` reads `preferences.competitor_checks[normalize_competitor_url(url)]` (no crawling, no shared cache reads, single workspace load) and maps saved status as specified:
    - none saved → `unchecked` / `"Not checked yet. Check now (free) on your digest."`
    - `first_check` → `first` / saved `summary`
    - `changed` → `changed` / saved `summary`
    - `unchanged` → `fresh` / saved `summary`
    - `error` → `unchecked` / saved `error`
  - `overnight_note` is `"Muse checks your watchlist when you press Check now (free) on your digest."`, plus `" Last check: <short date>."` using the latest saved `checked_at` when any check exists. Never claims an automatic check.
- Updated `tests/test_daily_brief_own.py` and `tests/test_today_own_brief_e2e.py` to match the updated `overnight_note` wording.

## 2. Seller's recent YouTube videos (public Atom/RSS feed, no API key)

- Created `src/services/youtube_feed.py`:
  - Accepts `youtube.com/@handle`, `/channel/UC...`, `/c/...`, and `/user/...` (with or without `www.`/`m.`). Rejects non-YouTube hosts, `javascript:` and non-HTTP(S) schemes, userinfo/ports, and invalid paths/channel IDs with `"That isn't a YouTube channel address."`.
  - `/channel/UC...` maps directly to `https://www.youtube.com/feeds/videos.xml?channel_id=UC...`.
  - Other channel URLs perform one GET of the channel page through `_fetch_bytes_guarded` (SSRF + redirect + `MAX_SITEMAP_BYTES` cap), `fetch_robots_policy` (`RobotsPolicy`), and `scan_guard.crawl`, then read `<link rel="alternate" type="application/rss+xml" href="...">` accepting **only** `https://www.youtube.com/feeds/videos.xml?channel_id=UC` followed by 22 chars of `[A-Za-z0-9_-]`.
  - Parses Atom XML exclusively with `defusedxml.ElementTree.fromstring(..., forbid_dtd=True, forbid_entities=True, forbid_external=True)`.
  - Keeps up to 10 newest videos (`title` ≤ 140 chars, `published` ISO date, `video_id` 11 chars of `[A-Za-z0-9_-]`, `description` ≤ 300 chars plain text). Rebuilds `url` (`https://www.youtube.com/watch?v=<id>`) and `thumbnail_url` (`https://i.ytimg.com/vi/<id>/hqdefault.jpg`) strictly from `video_id`; feed `href`s are never stored or rendered.
- Updated `src/api/seller_memory.py`:
  - Added `POST /api/v1/seller-memory/sources/youtube` (`{url, expected_version}` or `{remove: true, expected_version}`): enforces verified sign-in (`401`/`403`), stale `expected_version` (`409` before fetching), `reserve_scan_crawls` (`429` with `Retry-After` before fetching), plain error messages, and saves `preferences.content_sources.youtube` via `save_workspace(..., expected_version=...)`.
  - `GET /api/v1/seller-memory` returns `content_sources` and `youtube_social_url` (derived from `onboarding.socials` where `platform == "youtube"`).
  - Verified normal `PUT /api/v1/seller-memory` preserves both `preferences.content_sources` and `preferences.competitor_checks`.
- Updated `src/api/static/seller-memory.js`:
  - Added YouTube block inside `renderSetupFacts()` under "From your setup" in "What Muse remembers" (own workspace only, never rendered in sample):
    - Saved: `"Your recent YouTube videos"` with 3 newest titles + dates linking to client-rebuilt watch URLs (`target="_blank" rel="noopener noreferrer"`), plus `"Refresh (free)"` and `"Remove"`.
    - Not saved, YouTube social in setup: `"Read my recent videos (free)"`.
    - Neither: `"Your YouTube channel"` input + `"Read videos (free)"`.
  - Rendered strictly with DOM nodes and `textContent` (never `innerHTML`). Reloads seller memory via `loadServerMemory(true)` after save/remove so `state.version` stays in step.
  - Bumped `seller-memory.js?v=20261123-ag1` on `index.html` (script tag at bottom only), `welcome.html`, `creator.html`, `tests/test_ad_loop_links.py`, and `AGENTS.md`.

## Boundaries Respected

- Did **not** touch `muse-shell.js`, the home section of `index.html`, `today.html`, or `today.js` (per pass 19 boundary). Note: `today.html` still references `seller-memory.js?v=20261122-cx1` and should be bumped to `20261123-ag1` when merged with Claude's pass 19 changes.
- Zero live Muse calls, zero paid calls, zero API keys, zero `.env` reads, zero deploys, zero `*.vercel.app` targets.

## Mutation Checks

1. **Break href rebuild (`src/services/youtube_feed.py`):** temporarily overwrote `watch_url` with raw `<link href>` from the feed XML in `parse_youtube_feed_xml`.
   - Command: `DEMO_MODE=true META_MODEL_API_KEY= DEMO_KEY= .venv/bin/pytest -q tests/test_own_sources.py`
   - Result: **2 failed, 27 passed** — caught by `test_parse_youtube_feed_caps_and_rebuilds_links_from_video_id` and `test_fetch_youtube_channel_videos_direct_and_autodiscovery` (`AssertionError: assert 'https://evil.example/phish' == 'https://www.youtube.com/watch?v=VidID000011'`). Restored immediately.
2. **Break status mapping (`src/services/daily_brief.py`):** temporarily changed `"unchanged": "fresh"` to `"unchanged": "unchecked"` in `_SAVED_CHECK_STATUS_MAP`.
   - Command: `DEMO_MODE=true META_MODEL_API_KEY= DEMO_KEY= .venv/bin/pytest -q tests/test_own_sources.py`
   - Result: **1 failed, 28 passed** — caught by `test_own_brief_maps_every_saved_competitor_check_status` (`AssertionError: assert 'unchecked' == 'fresh'`). Restored immediately.

## Verification Results (Sequential, Offline)

1. **Node contracts (10/10 passed):**
   - `node tests/account_ui_contract.cjs` — PASS
   - `node tests/creator_artist_feedback.cjs` — PASS
   - `node tests/creator_import_sprint.cjs` — PASS
   - `node tests/creator_journey_smoke.cjs` — PASS
   - `node tests/creator_studio_contract.cjs src/api/static/creator.js` — PASS
   - `node tests/editor_drafts_contract.cjs` — PASS
   - `node tests/muse_shell_resilience.cjs` — PASS
   - `node tests/shared_get_contract.cjs` — PASS
   - `node tests/today_studio_contract.cjs` — PASS
   - `node tests/ui_polish_contract.cjs` — PASS
   - (`tests/portal_demo_smoke.cjs` also ran and passed inside `tests/test_portal_demo.py` during `make check`.)
2. **Full offline gate:**
   - Command: `DEMO_MODE=true META_MODEL_API_KEY= DEMO_KEY= make PY=/Users/nav/meta-smb-gtm/.venv/bin check`
   - Result: `ruff check .` passed; `ruff format --check .` (324 files formatted); **`789 passed, 2 skipped, 0 failed`** (5m 25s), including all 29 tests in `tests/test_own_sources.py`, the 375px/1440px Chromium E2E test in `tests/test_own_sources_e2e.py`, `tests/test_daily_brief_own.py` (12/12), and `tests/test_today_own_brief_e2e.py` (16/16).
3. **Launch account audit:**
   - Command: `DEMO_MODE=true META_MODEL_API_KEY= DEMO_KEY= /usr/bin/python3 tests/launch_account_audit.py`
   - Result: **`27 passed, 0 failed`**.
4. **Launch browser audit:**
   - Command: `DEMO_MODE=true META_MODEL_API_KEY= DEMO_KEY= /usr/bin/python3 tests/launch_browser_audit.py`
   - Result: **`20 passed, 0 failed`**.

## Not Verified

- Live network fetches against `www.youtube.com` (all unit, route, and E2E tests use local fakes per offline rules).
- Preview/production deployment or live Supabase persistence.
- `today.html`'s `seller-memory.js?v=` cache-bust bump (intentionally deferred to avoid colliding with Claude's pass 19 changes to `today.html`).

Ownership released.
