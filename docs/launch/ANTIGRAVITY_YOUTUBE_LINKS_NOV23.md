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

---

## Part B: Handoff from Argon (Nov 23 Evening)

- **Merged base:** `origin/claude/ux-gap-ad-loop-nov17` at `7e4cabf` (merge commit `2d2f79e`).
- **Checkpoints:**
  - `a9cd4ba`: Part A ports (`m.youtu.be`, post-redirect host/robots check, `youtube_handle` from `onboarding.socials`) + Part B ranker (`move-share-video`), `/api/v1/seller-memory/recommend` + `_own_brief` wiring, and unit/route/ranker/brief tests.
  - `201b814`: Part B frontend handoff (`seller-memory.js?v=20261124-ag2`, `creator.js?v=20261124-ag1`), version pins (`index.html`, `today.html`, `welcome.html`, `creator.html`, `tests/test_ad_loop_links.py`, `tests/test_create_any_business.py`, `AGENTS.md`), and extended 375px/1440px Chromium E2E.
  - This commit: final Part B report update.

### What Was Ported from Argon (`0b92018` + uncommitted Part B diff in `/Users/nav/muse-worktrees/youtube-videos`)

- **Part A additions:**
  - `m.youtu.be` added to `YOUTUBE_SHORT_HOSTS` in `src/services/youtube_videos.py`.
  - Post-redirect `final_url` host check (`final_host in YOUTUBE_WATCH_HOSTS` and `policy.is_allowed(final_url)`) in `fetch_video_info`.
  - `extract_youtube_social_handle(onboarding)` returning `youtube_handle` on `GET /api/v1/seller-memory`, surfaced in `seller-memory.js` as `"Paste links from your channel (@handle)."` (never fetching the channel).
- **Part B (`move-share-video`):**
  - `rank_seller_recommendations` (`src/services/seller_memory.py`): takes optional `content_videos`; for non-sample workspaces (`business_type is not None`) with saved videos, adds `move-share-video` (`"Share your video “<title>” as a post"`) using the newest undismissed video, ranking with existing scoring and `over_budget` rules, and carrying the video title (`product_name`) and rebuilt watch URL (`destination_url`, `product_link`) through `_build_editor_defaults_for_move`.
  - Passed saved videos from both `POST /api/v1/seller-memory/recommend` (`src/api/seller_memory.py`) and `_own_brief` (`src/services/daily_brief.py`, leaving `_own_watch_items` untouched).
  - Forwarded `content_videos`, `destination_url`, and `product_link` through `seller-memory.js` and `creator.js`.

### What Was Dropped / Fixed vs. Argon's Diff (and Why)

1. **Dropped `_dump_preserving_workspace_extras` on `GET /api/v1/seller-memory`:** kept `pref.model_dump(mode="json")` so `GET /api/v1/seller-memory` never adds unknown preference extras (such as up-to-64 KB `competitor_checks` snapshots) to every memory load.
2. **Dropped substring dismissal rule in `_select_undismissed_video`:** removed `title_lower in sig_title` so a short video title like `"Art"` cannot be hidden by an unrelated dismissed move containing `"art"`. Matches only exact move title, shell `actionId` of that title, `move-share-video:<video_id>`, or generic `move-share-video` without a conflicting title.
3. **Scoped `creator.js` handoff link strictly to `move-share-video`:** `offers[state.product.destination]` and `state.product.link` are only set when `(handoff.recommendation_id || handoff.id) === 'move-share-video'`, preventing other handoffs from clobbering the seller's saved offer link.
4. **Protected seller-edited fields in `seller-memory.js` `applyEditorDefaults`:** `isVideoMoveOverride` checks `node.dataset.smUserEdited !== '1'` and `def.recommendation_id === 'move-share-video'`, so it never overwrites fields the seller edited.
5. **Shortened `move-share-video` action copy for 375 px:** action sentence says `"link to the video"` instead of printing the raw watch URL inline, while keeping the full rebuilt watch URL in `editor_defaults` (`destination_url` and `product_link`).
6. **Left Argon's worktree (`/Users/nav/muse-worktrees/youtube-videos`) completely untouched** (read-only inspection only).

### Mutation Check 3 (Part B — Sample Artist Isolation)

- **Offer `move-share-video` to the sample artist (`src/services/seller_memory.py`):** temporarily removed `business_type is not None` from the `move-share-video` guard in `rank_seller_recommendations`.
  - Command: `DEMO_MODE=true META_MODEL_API_KEY= DEMO_KEY= .venv/bin/pytest -q tests/test_youtube_videos.py`
  - Result: **1 failed, 52 passed** — caught by `test_ranker_never_offers_video_move_to_sample_or_without_videos`. Restored immediately.
- (Mutation Checks 1 and 2 — storing oEmbed `thumbnail_url` and skipping the robots check — were already verified and recorded above.)

### Part B Verification Results (Sequential, Offline)

1. **Node contracts (10/10 standalone + `portal_demo_smoke.cjs` via pytest):** all **PASS** (`account_ui_contract`, `creator_artist_feedback`, `creator_import_sprint`, `creator_journey_smoke`, `creator_studio_contract`, `editor_drafts_contract`, `muse_shell_resilience`, `shared_get_contract`, `today_studio_contract`, `ui_polish_contract`).
2. **Full offline gate:**
   - Command: `DEMO_MODE=true META_MODEL_API_KEY= DEMO_KEY= make PY=/Users/nav/meta-smb-gtm/.venv/bin check`
   - Result: `ruff check .` passed; `ruff format --check .` (329 files formatted); **`816 passed, 2 skipped, 0 failed`** (5m 12s), including `tests/test_youtube_videos.py` (53/53) and extended `tests/test_youtube_videos_e2e.py` (375px & 1440px: paste 2 links with `@northstaradvisory` hint → `/today?workspace=own` shows video move → `/create?workspace=own` pre-fills title + watch URL → Remove clears → sample shows none).
3. **Launch account audit:**
   - Command: `DEMO_MODE=true META_MODEL_API_KEY= DEMO_KEY= /usr/bin/python3 tests/launch_account_audit.py`
   - Result: **`27 passed, 0 failed`**.
4. **Launch browser audit:**
   - Command: `DEMO_MODE=true META_MODEL_API_KEY= DEMO_KEY= /usr/bin/python3 tests/launch_browser_audit.py`
   - Result: **`20 passed, 0 failed`**.

---

## Review fixes (Nov 24)

- **Merged base:** `origin/claude/ux-gap-ad-loop-nov17` at `5ebc99c` (merge commit `b434bc9`).
- **Fixes (`b928c96`):**
  1. **`_js_action_id` UTF-16 parity (`src/services/seller_memory.py`):** encodes cleaned title to `utf-16-le`, slices the first 120 UTF-16 code units, walks code points (advancing 2 units on surrogate pairs, 1 unit on BMP/lone surrogates), and adds the first UTF-16 code unit — matching `muse-shell.js`'s `actionId(itemTitle(item))` identically. Verified by `test_js_action_id_matches_muse_shell_js_via_node`, which parses `actionId` directly from `src/api/static/muse-shell.js` and compares Python vs Node on plain titles, emoji titles (`"Glaze day 🔥 new mugs"` → `a17tqlor`), >120 UTF-16 units with an emoji across the cut, repeated whitespace, and curly quotes, plus end-to-end dismissal with `{id, title: ""}`.
  2. **Video move destination `"other"` + offer preservation (`src/services/seller_memory.py`, `src/api/static/creator.js`):** `_build_editor_defaults_for_move` sets `destination: "other"` for `move-share-video`. In `creator.js`, any handoff that sets `destination` first preserves the current offer if needed and loads `offers[destKey]` (`price` and `link`), then applies the video watch URL only for `move-share-video`. Verified by `test_video_move_uses_other_destination_and_preserves_website_offer_link` (website link survives opening `move-share-video` then another `website` move).
  3. **`RecommendRequest.content_videos` cap (`src/api/seller_memory.py`):** capped at `max_length=5` (`422` on 6 videos, `200` on 5). Verified by `test_recommend_route_caps_content_videos_at_five`.
- **Mutation checks (all 3 confirmed failing, then restored):**
  1. Revert `_js_action_id` to `ord(ch)` on `cleaned[:120]` → `pytest -q tests/test_youtube_videos.py -k "action_id"` failed (`'a1fb6n8z' != 'a17tqlor'`).
  2. Remove `offers[destKey]` reload in `creator.js` → `pytest -q tests/test_youtube_videos.py -k "preserves_website_offer_link"` failed (`'https://www.youtube.com/watch?v=AbCdEfGh123' !== 'https://northstar.test/services'`).
  3. Remove `max_length=5` on `RecommendRequest.content_videos` → `pytest -q tests/test_youtube_videos.py -k "caps_content_videos"` failed (`assert 200 == 422`).
- **Verification results (Nov 24):**
  - Node contracts: **10/10 passed** (plus `portal_demo_smoke.cjs` via pytest).
  - Full gate (`make check`): `ruff check .` passed; `ruff format --check .` (331 files formatted); **832 passed, 2 skipped** on the full run with 1 transient Playwright timeout in `tests/test_today_destinations_e2e.py[1440]` (`#postCaption` fill), which passed **2/2** on immediate re-run (`31.53s`), including all 56 tests in `tests/test_youtube_videos.py` and `tests/test_youtube_videos_e2e.py`.
  - `tests/launch_account_audit.py`: **27 passed, 0 failed**.
  - `tests/launch_browser_audit.py`: **20 passed, 0 failed**.

Ownership released.
