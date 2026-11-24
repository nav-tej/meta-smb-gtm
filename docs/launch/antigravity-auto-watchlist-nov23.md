# Antigravity brief: Muse checks each seller's watchlist once a week (Nov 23)

Coordinator: Claude. Nav assigned this to Antigravity (Neon/Gemini) on Nov 23 and asked that it stay
on Supabase's free plan. Report: `docs/launch/ANTIGRAVITY_AUTO_WATCHLIST_NOV23.md`.
Base: `origin/claude/ux-gap-ad-loop-nov17` (the commit that adds this brief, or later).
Branch: `gemini/auto-watchlist-nov23`. Worktree: `/Users/nav/muse-worktrees/auto-watchlist` (never
`/tmp`; see AGENTS.md section 11). Commit and push at every checkpoint. Every push builds a protected
Vercel preview automatically; never push to `main` (a push to `main` deploys production).
Read `AGENTS.md` first, especially "Own competitor checks" and "Own `/today` watchlist".

## The problem

`POST /api/v1/competitors/check` ("Check now (free)" on `/digest`) is the only thing that checks a
seller's watchlist, and it saves results into the workspace document
(`preferences.competitor_checks`). That has two costs:
1. Nothing happens unless the seller presses the button, so `/today` and `/digest` say "Not checked
   yet" for most sellers.
2. Every check bumps the workspace version, so another open tab gets a "your workspace changed"
   conflict on its next save.

## What to build

### 1. Database (new migration, not applied by you)

`supabase/migrations/watchlist_checks.sql` and `watchlist_checks_rollback.sql`, in the style of
`digest_subscribers.sql`: `begin; ... commit;`, tables in `muse_private` with RLS on and
`revoke all ... from public, anon, authenticated`, functions in `public` with
`security invoker set search_path = ''`, `revoke all on function ... from public, anon,
authenticated` and `grant execute ... to service_role` only. The server already calls Supabase with
the secret key (`src/clients/supabase.py` `rpc()`).

- `muse_private.watchlist_checks`: one row per seller and watched site. `user_id uuid references
  auth.users(id) on delete cascade`, `site_url text` (the `normalize_competitor_url` form, 8 to 300
  chars), `status` (`first_check`, `changed`, `unchanged`, `error`), `source` (`manual`, `auto`),
  `checked_at timestamptz`, `summary` (at most 600 chars), `error` (at most 300), `partial boolean`,
  `result jsonb` (the display item `diff_competitor_pages` returns, without page lists over 30),
  `snapshot jsonb` (the stored pages; `octet_length(snapshot::text) <= 65536`), `updated_at`.
  Primary key `(user_id, site_url)`.
- `muse_private.watchlist_schedule`: `user_id` primary key (cascade), `next_check_at timestamptz`,
  `last_auto_check_at timestamptz`, `claimed_until timestamptz`, `paused boolean not null default
  false`.
- Functions (names are suggestions):
  - `muse_watchlist_get(p_user_id uuid, p_with_snapshots boolean)`: the seller's rows and schedule.
    Without snapshots for display (keeps egress down); with snapshots only for the check itself.
  - `muse_watchlist_save(p_user_id uuid, p_source text, p_checks jsonb, p_keep_urls text[])`:
    upsert the rows, delete rows whose `site_url` is not in `p_keep_urls` (the seller stopped
    watching it), and set `next_check_at = now() + interval '7 days'` (plus `last_auto_check_at` when
    `p_source = 'auto'`). Any check, manual or automatic, pushes the next automatic one a week out.
  - `muse_watchlist_claim_due(p_limit integer, p_lease_seconds integer)`: first insert a schedule
    row for every workspace whose `document->'onboarding'->>'completed_at'` is not null and has none
    yet, then claim up to `least(p_limit, 50)` rows that are not paused, are due
    (`next_check_at <= now()`) and are not leased (`claimed_until is null or claimed_until <
    now()`), oldest first, with `for update skip locked`, setting `claimed_until`. Return
    `{user_id, onboarding, preferences: {competitor_entries}}` per seller so Python's
    `extract_selected_competitors` stays the single parser of the watchlist.
  - `muse_watchlist_set_paused(p_user_id uuid, p_paused boolean)`.
- Test the SQL on local PostgreSQL WASM, never a remote database. Copy `tests/digest_sql.mjs` to
  `tests/watchlist_sql.mjs`. Install PGlite once with
  `npm install --prefix /Users/nav/muse-tools/pglite --ignore-scripts @electric-sql/pglite@0.4.4`
  and run with `BILLING_PGLITE_DIR=/Users/nav/muse-tools/pglite/node_modules/@electric-sql/pglite`.
  Cover: the migration applies on top of `supabase/muse_schema.sql`; the rollback removes every
  table and function; `anon` and `authenticated` cannot read the tables or execute the functions;
  claim returns only finished setups, skips paused and not-due sellers, respects the limit, and a
  second claim inside the lease returns none of the same sellers; save upserts, prunes and sets
  `next_check_at`; the size caps refuse oversized rows. Add a pytest wrapper like
  `test_digest_sql_on_local_postgres` (skips when PGlite is not installed).

### 2. Server

- `src/config.py`: `watchlist_auto_check_enabled: bool = False` (`WATCHLIST_AUTO_CHECK_ENABLED`)
  and `watchlist_auto_check_accounts_per_run: int = 10`. Add both to `.env.example` and AGENTS.md
  section 9.
- `src/services/watchlist_store.py`: thin wrappers over the four functions. When the flag is off,
  nothing here is called.
- Move the per-site loop out of `check_own_competitors` in `src/api/intel.py` into one service
  function (in `competitor_checks.py`) that both the button and the scheduled run call: same
  `scan_guard.crawl` + `collect_entries(max_urls=30)`, robots handling, error classification and
  `diff_competitor_pages(..., truncated=...)` rules, at most 6 sites.
- **Flag off: everything behaves exactly as today.** Existing tests must pass unchanged.
- **Flag on, the button:** previous snapshot comes from the table, else from the legacy
  `preferences.competitor_checks[url]` (read only), so the first check after switching on diffs
  against the seller's last manual check. Results are saved with `source = 'manual'` and the
  workspace is **not** written (no version bump). Keep the request and response shapes;
  `version` echoes the current workspace version. Keep `reserve_scan_crawls` and the 409 for a
  stale `expected_version`.
- **Flag on, the scheduled run:** `GET /api/v1/watchlist/run` (Vercel Cron sends GET).
  - 404 when the flag is off.
  - 401 unless `CRON_SECRET` is set and `Authorization` matches `Bearer <secret>` with
    `hmac.compare_digest` (stricter than `/monitor/run`: no user-agent fallback, because this
    route crawls).
  - Claim up to `watchlist_auto_check_accounts_per_run` sellers with a 600 s lease. For each:
    read the workspace with the secret client, check their sites, save with `source = 'auto'`. A
    seller with no selected competitors is saved with an empty keep-list, which also pushes them a
    week out.
  - Only crawl for sellers with a confirmed email (the button already requires
    `require_verified=True`). Check `email_confirmed_at` through the Supabase Auth admin API with
    the secret key (read only, never log the response); otherwise skip and push them a week out.
  - One seller's failure must not stop the others. Stop claiming after 200 s (`maxDuration` is
    300); unfinished leases simply expire.
  - Response and logs carry counts only (sellers checked, sites checked, errors). No user IDs,
    names or URLs.
- `GET /api/v1/competitors/checks` (signed in and verified, `never_cache`): the seller's saved
  checks for display (table first, legacy fallback) plus
  `auto_check: {enabled, paused, next_check_at, last_auto_check_at}`. `enabled` is true only when the
  flag is on and the table answered.
- `POST /api/v1/competitors/auto-check` `{paused: bool}` (signed in and verified, `no-store`):
  calls `muse_watchlist_set_paused`. 404 when the flag is off.
- `vercel.json`: add `{"path": "/api/v1/watchlist/run", "schedule": "0 13 * * *"}`. Daily is the
  most Vercel's free plan allows (once a day, within the hour). With 10 sellers per run that is
  up to 70 seller checks a week. Crons only run on production deployments.

### 3. Pages

- `/digest` (`digest.js`, own workspace): load checks from `GET /api/v1/competitors/checks`
  instead of the workspace's `preferences.competitor_checks` when the flag is on (the response says
  so); one extra call on `/digest` only. Raise the `/digest` ceiling in
  `tests/test_api_calls_per_page_e2e.py` by one and say why in your report.
  - With `auto_check.enabled`: "Muse checks your watchlist once a week. Next check: about Mon, Nov
    30." and each card's line says whether its last check was automatic or one the seller ran. A
    checkbox "Check my watchlist automatically each week" calls the pause route.
  - Otherwise: today's copy, word for word.
  - Bump `digest.js` to `20261124-ag1` on `digest.html` and in AGENTS.md's version line.
- `/today` own brief (`_own_watch_items` in `src/services/daily_brief.py`; leave `_own_brief`'s
  `rank_seller_recommendations(...)` call alone, Argon may edit it): read the same checks
  (one Supabase call per brief load, no snapshots). The overnight note says "Muse checks your
  watchlist once a week." plus "Last check: <date>." only when `auto_check.enabled`; otherwise
  today's sentence. Keep the chips from `9c2b38e` ("No change", "Couldn't check").

## Honesty rules (these are what review will check first)

- Say "automatic" or "once a week" only when the server says `auto_check.enabled`. With the flag
  off, AGENTS.md's "Nothing checks automatically; never say it does" still holds. Update that
  bullet to say exactly this.
- Never show a check that did not happen: dates come from `checked_at`, and "Next check" from
  `next_check_at`, both from the database.
- No emails, no Muse runs, no new crawl path (everything through `scan_guard.crawl` and
  `collect_entries`, 30 pages and 6 sites at most, robots.txt honored as today).

## Do not touch

`muse-shell.js`, `muse-shell.css`, the home section of `index.html` (above `#tab-intel`),
`today.html`, `today.js`, `today.css`, `welcome.js` (Claude, pass 19), and `seller-memory.js`,
`src/api/seller_memory.py`, `src/services/seller_memory.py`, `creator.js` (Argon). If you need a
change there, write it in your report instead.

## Tests, mutation checks and the full gate

- Unit and route tests (no network, Supabase faked as in `tests/test_own_competitor_checks.py`):
  flag off is byte-for-byte today's behavior; flag on, the button saves to the table and never calls
  `save_workspace`; legacy fallback; cron 404 when off, 401 without or with a wrong secret and when
  `CRON_SECRET` is empty; per-run limit; one failing seller does not stop the rest; the time budget
  stops claiming; responses and logs contain no seller URLs or IDs; `GET /competitors/checks` is
  `private, no-store` and 401 signed out; the pause route.
- Chromium at 375 and 1440 on a local server only: `/digest` with the flag on (automatic copy,
  checkbox) and off (today's copy); `/today` overnight note both ways.
- Mutation checks, each must fail a test (report the command and result): drop the cron secret
  check; show the weekly copy with the flag off; call `save_workspace` from the button with the flag
  on; claim paused sellers (SQL test).
- Full gate: `DEMO_MODE=true META_MODEL_API_KEY= DEMO_KEY= make PY=/Users/nav/meta-smb-gtm/.venv/bin
  check`, both audits (`/usr/bin/python3 tests/launch_account_audit.py` and
  `tests/launch_browser_audit.py`), all 8 Node contracts, and `node tests/watchlist_sql.mjs`.

## Free plan budget (put the real numbers in your report)

- Supabase Free: 500 MB database, 5 GB egress a month, pauses after 7 days without activity. A row
  holds at most 30 pages (about 6 KB), so about 36 KB per seller with 6 sites: 1,000 sellers is about
  36 MB. Display reads skip snapshots. The daily run also keeps the project from pausing.
- Vercel free (Hobby): crons at most once a day. Crawls mostly wait on the network; report the
  wall time and pages fetched for a run of 10 sellers with fixture sites.

## After you (not your job, listed so nobody does it early)

Claude reviews the SQL line by line. Nav approves applying it in the Supabase SQL editor, then a
deploy with the flag off, then setting `WATCHLIST_AUTO_CHECK_ENABLED=true` for Production. No
hosted migration, env change or deploy from this branch.
