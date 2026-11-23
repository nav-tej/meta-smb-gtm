# Argon brief: the seller's own videos become their next post (Nov 23)

Coordinator: Claude. Nav assigned this to Argon on Nov 23. Report:
`docs/launch/ARGON_YOUTUBE_VIDEOS_NOV23.md`.
Base: `origin/claude/ux-gap-ad-loop-nov17` (the commit that adds this brief, or later).
Branch: `argon/youtube-videos-nov23`. Worktree: `/Users/nav/muse-worktrees/youtube-videos` (never
`/tmp`; see AGENTS.md section 11). Commit and push at every checkpoint. Every push builds a protected
Vercel preview automatically; never push to `main` (a push to `main` deploys production).
Read `AGENTS.md` first, especially section 10 (security) and the "YouTube videos" bullet.

## Why this shape

Antigravity built a reader for a channel's video feed (`5ca48b6` on `gemini/own-sources-nov23`,
not merged). It was built to the brief and well tested, but the brief was wrong: YouTube's
robots.txt has `Disallow: /feeds/videos.xml` for `User-agent: *`, and this app honors robots.txt.
Do not fetch `/feeds/videos.xml`, channel pages or `/youtubei/`. Reuse what fits from `5ca48b6`
(route guards, DOM-only rendering, tests), not the feed reader.

Instead the seller pastes links to their own videos. Muse reads each video's title and channel name
from YouTube's public oEmbed endpoint
(`https://www.youtube.com/oembed?url=https://www.youtube.com/watch?v=<id>&format=json`), which
robots.txt allows and which needs no API key. Then the videos feed the seller's suggested posts.

## Part A: read and save the videos

1. `src/services/youtube_videos.py`:
   - `parse_video_id(raw)`: accepts `youtube.com/watch?v=ID`, `youtu.be/ID`,
     `youtube.com/shorts/ID` (with or without `www.`/`m.`), `http` or `https` only, no userinfo or
     port; the ID must match `^[A-Za-z0-9_-]{11}$`. Anything else: "That isn't a YouTube video link."
   - `fetch_video_info(video_id)`: check `RobotsPolicy` for the oEmbed URL first (refuse if
     disallowed), then one GET through `_fetch_bytes_guarded` (SSRF checks, redirects re-checked, a
     64 KB cap) inside `scan_guard.crawl`. Parse with `json.loads`; keep `title` (plain text, 140
     chars) and `author_name` (80 chars) only. Rebuild the watch URL and thumbnail from the ID; never
     store or render a URL from the response. 401, 403 or 404 from oEmbed: "YouTube didn't share this
     video (it may be private or removed)."
2. `POST /api/v1/seller-memory/sources/youtube` (in `src/api/seller_memory.py`): verified sign-in
   (401/403), owner check, 409 for a stale `expected_version` before any fetch,
   `reserve_scan_crawls` before any fetch (one entry per video not already saved), plain errors,
   `Cache-Control: no-store`. `{urls: [...], expected_version}` replaces the list (at most 5);
   `{remove: true, expected_version}` clears it. Saved IDs are kept without a new fetch. Saves
   `preferences.content_sources.youtube = {videos: [{video_id, title, author_name, added_at}],
   updated_at}`. `GET /api/v1/seller-memory` returns `content_sources`. A normal
   `PUT /api/v1/seller-memory` must keep `content_sources` (test it).
3. `seller-memory.js` (own workspace only, never the sample): under "From your setup", "Your
   videos" lists saved titles linking to rebuilt watch URLs (`rel="noopener noreferrer"`), a
   textarea "Paste links to your videos (one per line, up to 5)", "Save videos (free)" and "Remove".
   DOM nodes and `textContent` only. If setup saved a YouTube handle (`onboarding.socials`), say
   "Paste links from your channel" next to it; never fetch the channel.
   Copy: "Muse reads the title of each video you paste." Never say Muse watches the channel, finds
   new videos or checks automatically.

## Part B: a suggested post from the videos

4. `rank_seller_recommendations` (`src/services/seller_memory.py`) takes an optional
   `content_videos` list. When the seller saved videos, add one move (`id` `move-share-video`):
   "Share your video “<title>” as a post", with an action that fits `business_type` (products,
   services or both) and the seller's channels (`access.channels`), the same fields as the other
   moves (category, goal, minutes, why_this_fits that names the video, `over_budget` when it does not
   fit `access.minutes_per_week`). Use the newest saved video the seller has not dismissed. It must
   rank with the existing scoring, not always first: a move the seller dismissed stays dismissed
   (`dismiss_signals`). `business_type: null` (the sample artist) and sellers without videos get
   exactly today's moves (keep the sample brief JSON byte-identical; `SAMPLE_SHA256` test).
5. Pass the videos in from both callers: `/api/v1/seller-memory/recommend` and the
   `rank_seller_recommendations(...)` call inside `_own_brief` in `src/services/daily_brief.py`
   (only that call; Antigravity is editing `_own_watch_items` in the same file).
6. `/create` handoff: when the selected move is `move-share-video`, the editor defaults carry the
   video title as the post's subject and the rebuilt watch URL as the link (through
   `_build_editor_defaults_for_move`, so `/today` and `/create` both get it). `creator.js` shows it
   like any other move ("Selected move: ..."). Never put the video's thumbnail into an image slot
   or claim Muse made it.

## Do not touch

`muse-shell.js`, `muse-shell.css`, the home section of `index.html` (above `#tab-intel`),
`today.js`, `today.css`, `welcome.js` (Claude, pass 19); `src/api/intel.py`,
`src/services/competitor_checks.py`, `digest.js`, `vercel.json`, `supabase/` (Antigravity's
weekly watchlist work). If you need a change there, write it in your report.
Version bumps: `seller-memory.js` to `20261124-ar1` on every page that loads it, including a
one-line tag change in `today.html`; `creator.js` to `20261124-ar1` if you change it. Update the
pins in `tests/test_ad_loop_links.py` and `tests/test_create_any_business.py` and AGENTS.md's
version line.

## Tests, mutation checks and the full gate

- Unit: every accepted and refused link shape; oEmbed JSON with extra fields, HTML in the title, a
  non-JSON body, 404; a robots disallow refuses before any GET; no URL from the response is stored.
- Route: 401 signed out, 403 unverified, 409 stale version before any fetch, 429 with
  `Retry-After` before any fetch, remove, saved IDs kept without a refetch, unknown preference keys
  kept.
- Ranker: the video move appears only with saved videos, respects dismissals and `over_budget`,
  wording for products, services and both; the sample is unchanged.
- Chromium at 375 and 1440 on a local server only: paste two links, see the titles in memory, see
  the move on `/today`, open it in `/create` and see the title and link; the sample shows none of it.
- Mutation checks, each must fail a test (report the command and result): store the oEmbed
  `thumbnail_url` instead of rebuilding it; skip the robots check; offer the video move to the
  sample artist.
- Full gate: `DEMO_MODE=true META_MODEL_API_KEY= DEMO_KEY= make PY=/Users/nav/meta-smb-gtm/.venv/bin
  check`, both audits (`/usr/bin/python3 tests/launch_account_audit.py` and
  `tests/launch_browser_audit.py`), all 8 Node contracts.
- No live YouTube calls in tests, no deploys, no `*.vercel.app` targets, no secrets, no Muse runs.
