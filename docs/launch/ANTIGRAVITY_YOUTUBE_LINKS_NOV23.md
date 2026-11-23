# Antigravity Report: Seller's YouTube Videos from Pasted Links via oEmbed (Nov 23)

- **Brief:** `docs/launch/antigravity-youtube-links-nov23.md`
- **Coordinator:** Claude
- **Base:** `origin/claude/ux-gap-ad-loop-nov17` at `39261f9`
- **Branch:** `gemini/youtube-links-nov23`
- **Worktree:** `/Users/nav/muse-worktrees/youtube-links`
- **Checkpoints:**
  - Checkpoint 1 (`3ca74a2`): `src/services/youtube_videos.py`, `src/api/seller_memory.py` (`POST /api/v1/seller-memory/sources/youtube` + `GET /api/v1/seller-memory` `content_sources`), and `tests/test_youtube_videos.py` (44 unit & route tests).
  - Checkpoint 2 (`f586916`): `src/api/static/seller-memory.js` UI block under "From your setup", `seller-memory.js?v=20261124-ag1` bumps on `index.html`, `today.html`, `welcome.html`, `creator.html`, pins in `tests/test_ad_loop_links.py` and `AGENTS.md`, and `tests/test_youtube_videos_e2e.py` (375px & 1440px Chromium E2E).
  - Checkpoint 3 (this commit): final verification results and report.

## What Was Built

1. **`src/services/youtube_videos.py`:**
   - `parse_video_id(raw)`: accepts `youtube.com/watch?v=ID`, `youtu.be/ID`, and `youtube.com/shorts/ID` (with or without `www.`/`m.`), `http`/`https` only, no userinfo or port, ID matching `^[A-Za-z0-9_-]{11}$`. Anything else raises `YouTubeVideoError("That isn't a YouTube video link.", status_code=400)`.
   - `fetch_video_info(video_id)`: checks `RobotsPolicy` (`fetch_robots_policy`) for `https://www.youtube.com/oembed?url=...&format=json` first and refuses before any GET if disallowed; fetches once via `_fetch_bytes_guarded` (SSRF guard, redirects re-validated, 64 KB cap) inside `scan_guard.crawl`; parses JSON with `json.loads`; strips HTML and caps `title` (140 chars) and `author_name` (80 chars); rebuilds watch and thumbnail URLs strictly from `video_id`; maps 401/403/404 to `"YouTube didn't share this video (it may be private or removed)."` and timeouts to `"YouTube took too long to answer. Try again shortly."`.
   - Never fetches `/feeds/videos.xml`, channel pages, or `/youtubei/`. No API key required.
2. **`src/api/seller_memory.py`:**
   - `POST /api/v1/seller-memory/sources/youtube`: requires verified sign-in (`401`/`403`), owner check, stale `expected_version` (`409` before any fetch), `Cache-Control: no-store`.
   - `{urls: [...], expected_version}` parses up to 5 video links, keeps already-saved IDs without a new fetch, calls `reserve_scan_crawls` with one entry per new video before any fetch (`429` with `Retry-After`), fetches only new IDs, and saves `preferences.content_sources.youtube = {videos: [{video_id, title, author_name, added_at}], updated_at}` via `save_workspace(..., expected_version=...)` (storing zero URLs from oEmbed).
   - `{remove: true, expected_version}` clears `preferences.content_sources.youtube`.
   - `GET /api/v1/seller-memory` returns `content_sources`. Normal `PUT /api/v1/seller-memory` preserves `content_sources`, `competitor_checks`, and other unknown preference keys.
3. **`src/api/static/seller-memory.js` & version pins (`20261124-ag1`):**
   - Own workspace only (never rendered in sample mode): under "From your setup" in "What Muse remembers", renders `"Your YouTube videos"`, `"Muse reads the title of each video you paste."`, saved titles linking to client-rebuilt `https://www.youtube.com/watch?v=<id>` (`target="_blank" rel="noopener noreferrer"`), textarea `"Paste links to your videos (one per line, up to 5)"`, `"Save videos (free)"`, and `"Remove"`. Rendered with DOM nodes and `textContent` only; reloads seller memory via `loadServerMemory(true)` after saves/removals.
   - Bumped `seller-memory.js?v=20261124-ag1` on `index.html` (bottom script tag only), `today.html` (one-line tag change only), `welcome.html`, `creator.html`, `tests/test_ad_loop_links.py`, and `AGENTS.md`.

## Boundaries Respected

- Did **not** touch `muse-shell.js`, `muse-shell.css`, the home section of `index.html` (above `#tab-intel`), `today.js`, `today.css`, or `welcome.js`.
- Zero live YouTube calls, zero live Muse calls, zero deploys, zero `*.vercel.app` targets, zero `.env` reads, never pushed to `main`.

## Mutation Checks

1. **Store oEmbed `thumbnail_url` instead of rebuilding it (`src/services/youtube_videos.py`):** temporarily overwrote `thumbnail_url` in `parse_oembed_payload` with `data["thumbnail_url"]`.
   - Command: `DEMO_MODE=true META_MODEL_API_KEY= DEMO_KEY= .venv/bin/pytest -q tests/test_youtube_videos.py`
   - Result: **1 failed, 43 passed** — caught by `test_parse_oembed_payload_strips_html_caps_and_rebuilds_urls` (`AssertionError: assert 'https://evil.example/thumb.jpg' == 'https://i.ytimg.com/vi/AbCdEfGh123/hqdefault.jpg'`). Restored immediately.
2. **Skip the robots check (`src/services/youtube_videos.py`):** temporarily removed `fetch_robots_policy` / `policy.is_allowed(oembed_url)` from `fetch_video_info`.
   - Command: `DEMO_MODE=true META_MODEL_API_KEY= DEMO_KEY= .venv/bin/pytest -q tests/test_youtube_videos.py`
   - Result: **2 failed, 42 passed** — caught by `test_fetch_video_info_checks_robots_and_rebuilds_urls` and `test_fetch_video_info_robots_disallow_refuses_before_get`. Restored immediately.

## Verification Results (Sequential, Offline)

1. **Node contracts (10/10 standalone + `portal_demo_smoke.cjs` via pytest):**
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
2. **Full offline gate:**
   - Command: `DEMO_MODE=true META_MODEL_API_KEY= DEMO_KEY= make PY=/Users/nav/meta-smb-gtm/.venv/bin check`
   - Result: `ruff check .` passed; `ruff format --check .` (327 files formatted); **`807 passed, 2 skipped, 0 failed`** (5m 18s), including all 44 tests in `tests/test_youtube_videos.py` and the 375px/1440px Chromium E2E test in `tests/test_youtube_videos_e2e.py`.
3. **Launch account audit:**
   - Command: `DEMO_MODE=true META_MODEL_API_KEY= DEMO_KEY= /usr/bin/python3 tests/launch_account_audit.py`
   - Result: **`27 passed, 0 failed`**.
4. **Launch browser audit:**
   - Command: `DEMO_MODE=true META_MODEL_API_KEY= DEMO_KEY= /usr/bin/python3 tests/launch_browser_audit.py`
   - Result: **`20 passed, 0 failed`**.

## Not Verified

- Live network calls to `https://www.youtube.com/oembed` or live Supabase persistence (all tests run offline with fakes).

Ownership released.
