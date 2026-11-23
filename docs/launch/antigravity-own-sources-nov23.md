# Antigravity brief: saved competitor checks in the own brief, and the seller's YouTube videos (Nov 23)

Nav's complaint (Nov 22, production screenshots of their own nplusalpha.com workspace): nothing in
the workspace was relevant "to the brand url i input or the youtube channel for it", and the
watchlist never showed what changed. Your competitor checks (merged, `1891499` plus Claude's
`1d589f7` for sites bigger than the 30-page window) now save real results. This brief puts those
results into the own `/today` brief and teaches Muse the seller's recent YouTube videos.

- Base: `origin/claude/ux-gap-ad-loop-nov17` at the tip named in Nav's prompt (it includes Codex's
  own `/today` brief). Branch `gemini/own-sources-nov23`, worktree under `/Users/nav/muse-worktrees/`.
- Report: `docs/launch/ANTIGRAVITY_OWN_SOURCES_NOV23.md`. Commit and push at every checkpoint.
- Rules: no live Muse calls, no paid calls, no API keys, no deploys, no Vercel or Supabase changes,
  never read `.env`. Tests fake every outbound request. Sample data and its timestamps stay as they
  are (the sample brief JSON must stay byte-identical; `tests/test_daily_brief_own.py` checks it).
- Do not touch `muse-shell.js`, the home section of `index.html`, `today.html` or `today.js`:
  Claude is simplifying the own home (pass 19) and reads your data from the API.

## 1. The own `/today` brief shows saved checks (read only)

`_own_brief()` in `src/services/daily_brief.py` lists every watched competitor as
`status="unchecked"`, "Not checked yet". Read `preferences.competitor_checks[normalize_competitor_url(url)]`
(helpers in `src/services/competitor_checks.py`) instead:

| Saved `status` | WatchItem `status` | `note` |
|---|---|---|
| none saved | `unchecked` | "Not checked yet. Check now (free) on your digest." |
| `first_check` | `first` | the saved `summary` |
| `changed` | `changed` | the saved `summary` |
| `unchanged` | `fresh` | the saved `summary` |
| `error` | `unchecked` | the saved `error` |

- Keep the saved `checked_at` on the item if `WatchItem` has room for it; otherwise put the short
  date in the note ("Checked Nov 23: ...").
- `overnight_note`: "Muse checks your watchlist when you press Check now (free) on your digest."
  plus "Last check: <short date>." when any check exists. Never claim an automatic check.
- The route still reads the workspace once and never crawls. No shared cache reads.

## 2. The seller's recent YouTube videos

Where the channel comes from: `onboarding.socials` entries with `platform == "youtube"` (shape
`{platform, handle, ...}`; setup saves the ones the seller confirmed, and
`social_extract.py` turns a handle into `https://youtube.com/@handle`), or a channel address the seller types in "What Muse remembers". Accept
`youtube.com/@handle`, `/channel/UC...`, `/c/...` and `/user/...` (with or without `www.`/`m.`).

New `src/services/youtube_feed.py`:
- `/channel/UC...` maps straight to `https://www.youtube.com/feeds/videos.xml?channel_id=UC...`.
- Any other form: one GET of the channel page through the existing crawler client, `RobotsPolicy`
  and `scan_guard` (size cap as for sitemap pages), then read the page's
  `<link rel="alternate" type="application/rss+xml" href="...">`. Accept only
  `https://www.youtube.com/feeds/videos.xml?channel_id=UC` followed by 22 characters of `[A-Za-z0-9_-]`.
- Parse the feed with `defusedxml` only (see `src/utils/sitemap.py`). Keep the 10 newest entries:
  `title` (140 characters), `published` (date), `video_id` (11 characters of `[A-Za-z0-9_-]`),
  `description` (300 characters, plain text). Rebuild the links yourself from `video_id`
  (`https://www.youtube.com/watch?v=<id>`, thumbnail `https://i.ytimg.com/vi/<id>/hqdefault.jpg`);
  never store or render an href from the feed.
- No YouTube Data API, no key, no transcripts, no video analysis.

New route `POST /api/v1/seller-memory/sources/youtube` with `{url, expected_version}`
(`{remove: true}` clears it):
- Signed in and verified (401/403), `reserve_scan_crawls` before any fetch (429 with Retry-After),
  stale `expected_version` returns 409 before fetching.
- Saves `preferences.content_sources.youtube = {channel_url, feed_url, fetched_at, videos: [...]}`
  with `save_workspace(..., expected_version=...)` and returns the new `version`.
- Plain errors: "That isn't a YouTube channel address.", "YouTube didn't share this channel's
  video list.", "YouTube took too long to answer. Try again shortly."
- `GET /api/v1/seller-memory` returns the saved `content_sources`. Prove a normal seller-memory save
  keeps `content_sources` and `competitor_checks` (test both).

UI, own workspace only (never in the sample), in "What Muse remembers" under "From your setup"
(`renderSetupFacts` in `seller-memory.js`):
- Saved: "Your recent YouTube videos": the 3 newest titles with dates, each linking to the rebuilt
  watch URL (`target="_blank" rel="noopener noreferrer"`), plus "Refresh (free)" and "Remove".
- Not saved but setup has a YouTube social: "Read my recent videos (free)".
- Neither: one input "Your YouTube channel" and "Read videos (free)".
- Render with `textContent`/DOM nodes, never `innerHTML` with feed text. After a save, reload seller
  memory so the version stays in step (as `runOwnWatchlistCheck()` does).
- Bump `seller-memory.js` to `20261123-ag1` on every page that loads it and update the pins
  (`tests/test_ad_loop_links.py`, AGENTS.md version line).

## Tests (required)

- Unit: each URL form; feed autodiscovery rejects any other href; hostile XML (entity expansion,
  external entities) is refused; caps; links rebuilt from ids; `javascript:` and non-YouTube links
  never appear.
- Route: 401, 403, 409, 429, remove, plain errors, no outbound request outside the fake.
- Brief: each saved check status maps as in the table; no check saved keeps today's wording; the
  sample brief JSON is unchanged.
- Chromium at 375 and 1440 px through the real routes (fixture user with a YouTube social): the
  memory modal shows three videos, Refresh and Remove work, no horizontal overflow, no sample terms
  ("Sarabjit", "Ek Onkar") in the own workspace, and the sample never shows the block.
- Mutation checks: break the href rebuild and the status mapping; each must fail a test. Record them.
- Full gate, both audits (27/27 and 20/20), all 8 Node contracts, run one after another.
