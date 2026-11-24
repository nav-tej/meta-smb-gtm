# Review: Antigravity's YouTube Part B and weekly watchlist (Nov 24)

Coordinator: Claude. Both branches are well built and well tested, and neither merges yet. Fix the
items below on the same branches and worktrees, YouTube first (smaller), then the watchlist. Start
each by merging `origin/claude/ux-gap-ad-loop-nov17` (at least `cdb5b88`, which changes
`src/api/intel.py` `analyze_competitors`, `src/api/main.py` and `index.html`; no overlap with your
regions expected). Add a "Review fixes (Nov 24)" section to each report with the gate results and a
mutation check per fix.

## 1. YouTube Part B: `gemini/youtube-links-nov23` (`d3cdfab`)

What landed well: the substring rule is gone, the sample stays untouched, `GET /seller-memory`
keeps `model_dump`, `isVideoMoveOverride` respects `smUserEdited`, the action sentence says "link
to the video", versions and pins are right, and the E2E covers paste to `/today` to `/create`.

1. **A dismissed video move with an emoji in its title comes back (confirmed).** The shell's
   dismissal signal is `{id, reason, at}` with no title, so `actionId` is the only match.
   `muse-shell.js` hashes `itemTitle(item)` (trim, collapse spaces, `slice(0, 120)` in UTF-16
   units) and adds `ch.charCodeAt(0)` per code point, which for an emoji is the high surrogate.
   `_js_action_id` adds `ord(ch)` and slices code points. For "Share your video “Glaze day 🔥 new
   mugs” as a post" the page computes `a17tqlor` and the server `a1fb6n8z`. Plain titles match.
   - Fix: emulate the JS exactly: encode to UTF-16, keep the first 120 units, walk code points and
     add the first unit of each (a lone surrogate left by the slice adds itself).
   - Test: a Node parity test that takes the `actionId` line and `itemTitle`'s rule from
     `muse-shell.js` itself (so a shell change breaks it) and compares with Python on a plain
     title, an emoji title, a title over 120 units with an emoji at the cut, repeated spaces, and
     curly quotes.
2. **The video handoff replaces the seller's own website link.** The editor defaults keep
   `destination` `website`, so `creator.js` writes the watch URL into `offers.website`. A later
   handoff for any other move sets `destination` but never reloads `offers[dest]`, so
   `state.product.link` stays the YouTube URL and the next post links to the video instead of the
   shop.
   - Fix: the video move's editor defaults use `destination: "other"` ("Other link"). When any
     handoff sets the destination, load that destination's saved price and link from `offers` the
     way the destination menu does (`Object.assign(state.product, offers[next] || ...)`), then
     apply the video link only for `move-share-video`.
   - Test: a draft with website link X; open the video move (Other link = watch URL); open
     another move; the link is X and `offers.website.link` is still X.
3. **Cap `RecommendRequest.content_videos`** at 5 items (the save route's cap) so the body can't
   carry an arbitrary list into the ranker.

## 2. Weekly watchlist: `gemini/auto-watchlist-nov23` (`b1da064`)

The SQL reads well line by line: RLS on, revokes from `public, anon, authenticated`,
`service_role`-only grants, `security invoker set search_path = ''`, `for update of s skip locked`
with a lease, prune by keep-list, and a complete rollback. `muse_workspaces` is one row per user,
and the claim returns exactly what `extract_selected_competitors` reads. The flag-off path,
honesty copy, cron secret and counts-only logging are right. The problems are in failure paths:

1. **An Auth API error deletes a seller's saved checks.** `is_email_confirmed` returns False on
   any `SupabaseError` (a 5xx, 429 or timeout). The run then treats the seller as unconfirmed and
   calls `save_checks(..., checks=[], keep_urls=[])`, which deletes every saved row and stamps
   `last_auto_check_at`. One bad minute at Supabase Auth wipes up to 10 sellers' history.
   - Fix: a lookup error raises (count it as an error, save nothing). Only a confirmed answer of
     "not confirmed" pushes the seller a week out.
   - Test: the admin lookup fails; the seller's rows are untouched and `errors == 1`.
2. **One slow seller can stop the run every day.**
   - Nothing bounds a single crawl. Each request has a 15 s timeout, but a site can take several
     requests, and a seller has 6 sites. A seller started near 200 s can run past
     `maxDuration` (300 s), and Vercel kills the function.
   - That seller is never saved, so `next_check_at` never moves. The claim orders by oldest
     `next_check_at`, so they are first again the next day, and the run dies again.
   - Fix:
     - Wrap each site's crawl in `asyncio.wait_for` (about 20 s) inside `run_watchlist_checks`.
       A timeout becomes that site's "took too long" error, so the button benefits too.
     - Stop starting sellers when the elapsed time plus one worst-case seller (6 sites x the
       per-site limit) would pass about 280 s.
     - Order the claim by `(s.claimed_until is not null), s.next_check_at, s.user_id`. Save
       clears `claimed_until`, so a leftover lease means a seller whose last attempt didn't
       finish, and those go last.
   - Tests:
     - SQL: a seller with an expired lease is claimed after a fresh due seller.
     - Route: a fake crawl that hangs is cut off at the per-site limit.
     - The budget leaves room for a worst-case seller.
3. **A failed table read rewrites history as "First check".** `get_checks` returns None on any
   error. During a check (the button with the flag on, or the run), that silently diffs against
   the legacy snapshot or nothing, then saves over the table rows. Every site then reads "First
   check", and the real baseline is gone.
   - Fix: when the flag is on and the read fails during a check:
     - The button returns 503 "Muse couldn't check your watchlist right now. Try again in a few
       minutes." and saves nothing.
     - The run counts an error and saves nothing.
   - Display reads may keep falling back as now.
4. **One oversized row aborts the whole save.**
   - `result` is capped at 16 KB in SQL. A display item can carry 15 new, 15 removed and 15
     price changes, each with an uncapped URL and a title of up to 140 characters. A store with
     long product URLs reaches about 16 KB.
   - `snapshot` pages also have uncapped `loc`.
   - A check-constraint failure rolls back `muse_watchlist_save` for all of that seller's sites.
     In the run, it also leaves them first in line (item 2).
   - Fix: cap `loc` (for example 500 characters) in `entries_to_snapshot_pages`. In
     `build_db_check_rows`, trim the change lists and the snapshot pages until each JSON value
     fits with margin. Raise the `result` cap to 32 KB.
   - Test: 30 pages and 45 changes, all with 300-character URLs, save successfully.
5. **`last_auto_check_at` is stamped when nothing was checked** (no competitors, or not
   confirmed). Set it only when `p_checks` has at least one row. Nothing shows it yet; keep it
   truthful.

After these, Claude reruns the gate, both audits, the contracts, `node tests/watchlist_sql.mjs`
and the mutation checks, then merges. Applying the migration, deploying, and turning on
`WATCHLIST_AUTO_CHECK_ENABLED` each still need Nav's approval.
