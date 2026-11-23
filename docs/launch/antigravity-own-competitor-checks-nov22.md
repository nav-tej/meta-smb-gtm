# Antigravity (Neon): real competitor changes for a seller's own watchlist (Nov 22)

Branch `gemini/own-competitor-checks-nov22` from `origin/claude/ux-gap-ad-loop-nov17` at the commit
named in Nav's prompt or later. Worktree under `/Users/nav/muse-worktrees/`. Report
`docs/launch/ANTIGRAVITY_OWN_COMPETITOR_CHECKS_NOV22.md`. Push at every checkpoint (macOS deletes
old files in `/tmp` overnight).

## Why
Nav set up his own business (nplusalpha.com) and found the weekly digest useless: every watched
competitor says "Queued for your scheduled digest updates", the top insight is "Watching 3
competitors", and the home watchlist says "Not checked yet" forever. The competitor monitor
(`src/api/monitor.py`, `src/services/monitor.py`) only watches the sample shop's fixed list, the same
for everyone. Nothing ever checks a seller's own watchlist.

## What to build
1. **A free check of the seller's own watchlist.** New `POST /api/v1/competitors/check`
   (signed in, verified email; 401/403 otherwise). For each selected competitor in the workspace
   (`preferences.competitor_entries` with `selected` not false, at most 6) crawl its public pages
   the same way the scans do: call `reserve_scan_crawls()` from `src/api/intel.py` with every address
   first, then fetch through `scan_guard.crawl()` (read `src/services/scan_guard.py` and the
   "Public website scans are guarded" rule in AGENTS.md). Cap pages per competitor (30). No Muse
   call, no run used.
2. **Compare with the last check.** Keep one small snapshot per competitor in the workspace
   document (for example `preferences.competitor_checks[<normalized url>] =
   {checked_at, pages: [{loc, title, price_hint}], ...}`), capped so the document stays small
   (cap pages and title length; say the cap in the report). Return per competitor: checked_at,
   new pages (title and link), removed pages, pages whose `price_hint` changed, and a plain
   status when the site could not be read (blocked, no sitemap, timeout). The first check says
   "First check: Muse now knows N of their pages. Changes show from the next check." Never
   invent a change.
3. **Workspace writes.** Save with the expected version like every other workspace write
   (`save_workspace(..., expected_version=...)`), return the new version, and make sure seller
   memory does not open its conflict dialog after a check (it compares versions; read
   `seller-memory.js` `persistToServer` and the 409 path). If you cannot avoid that, stop and
   report instead of working around it.
4. **Digest, own workspace** (`digest.js`, `digest.html`):
   - Each watched competitor card shows the last check (date, new pages with titles, price
     changes) or "Not checked yet", and one "Check now (free)" button for the whole watchlist.
   - "This week's top insight" is the biggest real change ("Summit Growth added 3 service
     pages"), else "No changes at the competitors you watch since <date>". Never "Watching N".
   - Remove "Queued for your scheduled digest updates" and "Canonical preview topics" (call it
     "What to include"). Prefill "Watched competitor 1 to 3" from the watchlist.
   - Sample digest unchanged.
5. **Home watchlist rows.** `competitorStatus()` in `muse-shell.js` already words a monitor run
   (`run.competitors[]` with `status` and `counts` of `new_listing`, `price_change`,
   `removed_listing`) as "Checked <date>" with change badges, and falls back to "Not checked yet".
   Shape each competitor in your check result the same way so it can reuse that. `muse-shell.js`
   belongs to Codex's open branch (`codex/today-own-brief-nov21`) until it merges: do items 1 to 4
   first, then do item 5 only after Nav or Claude says Codex's branch is merged, rebased on that
   tip. The rows read the saved checks from the workspace read the page already makes (no new call
   on load; check the ceilings in `tests/test_api_calls_per_page_e2e.py`).

Not in scope: an automatic weekly check across all accounts (needs a service-role job; describe
what it would take in the report), emails, Muse calls, Ad Library changes.

## Tests (all local, never `*.vercel.app`)
- Unit tests for the diff (new, removed, price change, blocked site, first check, caps) with
  `collect_entries` faked.
- Route tests: signed out 401, unverified 403, scan guard 429 passes through with `Retry-After`,
  version conflict 409.
- A Chromium test on real routes with fixture accounts (copy the fixture pattern in
  `tests/test_any_business_home_e2e.py`): own digest shows a real change after two checks with
  different fake pages; no "Queued"; sample digest unchanged; 375 and 1440, no horizontal scroll.
- Mutation check: break the diff and show the test fails; restore.
- Full gate, both audits (`tests/launch_account_audit.py`, `tests/launch_browser_audit.py`), the
  eight Node contracts. Bump versions of changed scripts on every page that loads them and the
  pins in tests (AGENTS.md lists them).

## Rules
No live Muse calls, paid calls, emails, deploys, env or settings changes, `.env` reads or hosted
migrations. Nothing under the sample shop changes. Report exact commands and results, what you did
not verify, and release ownership at the end.
