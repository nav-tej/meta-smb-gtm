# Antigravity brief: the seller's YouTube videos from links they paste (Nov 23)

Coordinator: Claude. Report: `docs/launch/ANTIGRAVITY_YOUTUBE_LINKS_NOV23.md`.
Base: `origin/claude/ux-gap-ad-loop-nov17` (the commit that adds this brief, or later).
Branch: `gemini/youtube-links-nov23`. Worktree: `/Users/nav/muse-worktrees/youtube-links`.
Commit and push at every checkpoint. Read `AGENTS.md` first.

## Why this replaces item 2 of `antigravity-own-sources-nov23.md`

Your channel-feed version (`5ca48b6` on `gemini/own-sources-nov23`) was built to the brief and well
tested, but the brief was wrong: YouTube's robots.txt has `Disallow: /feeds/videos.xml` for
`User-agent: *`, and this app honors robots.txt (AGENTS.md section 10). Do not fetch
`/feeds/videos.xml`, channel pages or `/youtubei/`. Nav chose the route in this brief by pasting it.

## What to build

The seller pastes up to 5 links to their own videos. Muse reads each video's title and channel name
from YouTube's public oEmbed endpoint (`https://www.youtube.com/oembed?url=<watch url>&format=json`).
robots.txt allows `/oembed`; no API key. Muse stores them so suggested posts can say "share your
video <title>".

1. `src/services/youtube_feed.py` becomes `src/services/youtube_videos.py` (reuse what fits from
   `5ca48b6`):
   - `parse_video_id(raw)`: accepts `youtube.com/watch?v=ID`, `youtu.be/ID`, `youtube.com/shorts/ID`
     (with or without `www.`/`m.`), `https` or `http` only, no userinfo or port; ID must match
     `^[A-Za-z0-9_-]{11}$`. Anything else: "That isn't a YouTube video link."
   - `fetch_video_info(video_id)`: check `RobotsPolicy` for the oEmbed URL first (refuse if
     disallowed), then one GET through `_fetch_bytes_guarded` (SSRF, redirects re-checked, small byte
     cap such as 64 KB) inside `scan_guard.crawl`. Parse JSON with `json.loads`; keep `title`
     (plain text, 140 chars) and `author_name` (80 chars) only. Rebuild the watch URL and thumbnail
     from the ID; never store or render URLs from the response. 401/403/404 from oEmbed: "YouTube
     didn't share this video (it may be private or removed)."
2. Route `POST /api/v1/seller-memory/sources/youtube` (keep your auth, owner, `expected_version`
   409-before-fetch, `reserve_scan_crawls` before any fetch with one entry per new video, plain
   errors, `Cache-Control: no-store`). Body `{urls: [...], expected_version}` replaces the list;
   `{remove: true, expected_version}` clears it. Saves `preferences.content_sources.youtube` as
   `{videos: [{video_id, title, author_name, added_at}], updated_at}`. Videos already saved with the
   same ID are kept without a new fetch. `GET /api/v1/seller-memory` returns `content_sources`.
3. `seller-memory.js` (own workspace only; never in the sample): under "From your setup", "Your
   YouTube videos" lists saved titles linking to rebuilt watch URLs (`rel="noopener noreferrer"`),
   a textarea "Paste links to your videos (one per line, up to 5)" and "Save videos (free)", plus
   "Remove". DOM nodes and `textContent` only. Bump `seller-memory.js` to `20261124-ag1` on every
   page that loads it, including `today.html` (one-line tag change only), and update the pins.
4. Copy: say "Muse reads the title of each video you paste". Never say Muse watches the channel,
   finds new videos, or checks automatically.

## Do not touch

`muse-shell.js`, `muse-shell.css`, the home section of `index.html` (above `#tab-intel`),
`today.js`, `today.css`, `welcome.js`. Claude is reworking the own home (pass 19).

## Tests and checks

- Unit: every accepted and refused link shape; oEmbed JSON with extra fields, HTML in the title,
  a non-JSON body, 404; robots disallow refuses before the GET; no URL from the response is stored.
- Route: 401 signed out, 403 unverified, 409 stale version before any fetch, 429 with `Retry-After`
  before any fetch, remove, keeping saved IDs without a refetch, unknown preference keys preserved.
- Chromium at 375 and 1440 (local server only), sample shows no YouTube block.
- Mutation checks (report each): store the oEmbed `thumbnail_url` instead of rebuilding it; skip the
  robots check. Each must fail a test.
- Full gate, both audits, all 8 Node contracts (commands in AGENTS.md and your last report).
- No live YouTube calls in tests, no deploys, no `*.vercel.app` targets, no secrets.
