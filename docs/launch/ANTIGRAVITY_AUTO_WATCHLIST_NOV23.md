# Antigravity Report: Weekly Automatic Watchlist Checks (Nov 23)

- **Brief:** `docs/launch/antigravity-auto-watchlist-nov23.md`
- **Coordinator:** Claude
- **Base:** `origin/claude/ux-gap-ad-loop-nov17` at `16f768b`
- **Branch:** `gemini/auto-watchlist-nov23`
- **Worktree:** `/Users/nav/muse-worktrees/auto-watchlist`
- **Checkpoints:**
  - Checkpoint 1 (`0b9410a`): `supabase/migrations/watchlist_checks.sql`, `supabase/migrations/watchlist_checks_rollback.sql`, `tests/watchlist_sql.mjs` (tested on local PGlite 0.4.4).
  - Checkpoint 2 (`45f05c5`): `src/config.py`, `.env.example`, `vercel.json`, `src/services/watchlist_store.py`, shared `run_watchlist_checks()` in `src/services/competitor_checks.py`, `src/api/intel.py` routes (`GET /api/v1/competitors/checks`, `POST /api/v1/competitors/auto-check`, `GET /api/v1/watchlist/run`, flag-gated `POST /api/v1/competitors/check`), `src/services/daily_brief.py`, and `tests/test_auto_watchlist.py`.
  - Checkpoint 3 (`0a5c959`): `src/api/static/digest.js`, `src/api/static/digest.html` (`digest.js?v=20261124-ag1`), `AGENTS.md`, `tests/test_api_calls_per_page_e2e.py`, `tests/test_auto_watchlist_e2e.py`, strengthened paused-seller SQL check in `tests/watchlist_sql.mjs`.
  - Checkpoint 4 (this commit): updated `digest.js?v=20261124-ag1` pin in `tests/test_own_competitor_checks.py` + final verification report.

## 1. Database Migration (Tested Locally on PGlite Only — Not Applied to Supabase)

- `supabase/migrations/watchlist_checks.sql` & `supabase/migrations/watchlist_checks_rollback.sql`:
  - Wrapped in `begin; ... commit;`, tables in `muse_private` with RLS enabled and `revoke all ... from public, anon, authenticated` (`service_role` only).
  - `muse_private.watchlist_checks`: primary key `(user_id, site_url)`, cascades on `auth.users(id)` delete, enforces `length(site_url) between 8 and 300`, `status in ('first_check', 'changed', 'unchanged', 'error')`, `source in ('manual', 'auto')`, `length(summary) <= 600`, `length(error) <= 300`, `octet_length(result::text) <= 16384`, `octet_length(snapshot::text) <= 65536`.
  - `muse_private.watchlist_schedule`: primary key `user_id` (cascade), `next_check_at`, `last_auto_check_at`, `claimed_until`, `paused boolean not null default false`, partial index on `(next_check_at, user_id) where not paused`.
  - Four `public` functions with `security invoker set search_path = ''`, revoked from `public, anon, authenticated` and granted execute to `service_role` only:
    - `public.muse_watchlist_get(p_user_id uuid, p_with_snapshots boolean default false)` (omits `snapshot` for display reads)
    - `public.muse_watchlist_save(p_user_id uuid, p_source text, p_checks jsonb, p_keep_urls text[])` (upserts, prunes removed sites, clears lease, pushes `next_check_at` 7 days out, sets `last_auto_check_at` when `source = 'auto'`)
    - `public.muse_watchlist_claim_due(p_limit integer default 10, p_lease_seconds integer default 600)` (seeds completed workspaces, claims unpaused due non-leased rows oldest-first with `for update of s skip locked`, caps at 50)
    - `public.muse_watchlist_set_paused(p_user_id uuid, p_paused boolean)`
- Verified on local PGlite 0.4.4 (`BILLING_PGLITE_DIR=/Users/nav/muse-tools/pglite/node_modules/@electric-sql/pglite node tests/watchlist_sql.mjs`): **5/5 checks passed** (applies on top of `supabase/muse_schema.sql`, role denial for `anon` and `authenticated`, claim filtering/limit/lease, save upsert/prune/7-day schedule, size caps, and clean rollback).

## 2. Server & Honesty Rules

- `src/config.py`, `.env.example`, `AGENTS.md` section 9: added `WATCHLIST_AUTO_CHECK_ENABLED` (default `false`) and `WATCHLIST_AUTO_CHECK_ACCOUNTS_PER_RUN` (default `10`).
- `src/services/watchlist_store.py`: thin `service_role` RPC wrappers + read-only `is_email_confirmed` via Supabase Auth admin API (never logs response) + `merge_checks_for_display`. When the flag is off, nothing here calls Supabase.
- `src/services/competitor_checks.py`: extracted shared `run_watchlist_checks(...)` called by both the manual button and the scheduled cron runner (same `scan_guard.crawl` + `collect_entries(max_urls=30)`, robots handling, error classification, `diff_competitor_pages(..., truncated=...)`, at most 6 sites).
- `src/api/intel.py`:
  - **Flag off:** `POST /api/v1/competitors/check` behaves identically to before (writes `preferences.competitor_checks` via `save_workspace`); `GET /api/v1/watchlist/run` and `POST /api/v1/competitors/auto-check` return `404`.
  - **Flag on:** button diffs against table snapshot with read-only fallback to legacy `preferences.competitor_checks`, saves to `muse_private.watchlist_checks` with `source='manual'`, and **never** calls `save_workspace` (echoes workspace `version`).
  - `GET /api/v1/competitors/checks`: signed in + verified (`401`/`403`), `private, no-store`, returns display checks (no snapshots) + `auto_check: {enabled, paused, next_check_at, last_auto_check_at}`.
  - `POST /api/v1/competitors/auto-check`: signed in + verified, `no-store`, toggles `paused` (`404` when flag is off).
  - `GET /api/v1/watchlist/run`: `404` when flag is off; strict `CRON_SECRET` `Bearer` match via `hmac.compare_digest` (no user-agent fallback, `401` when secret is empty or mismatched); claims up to `watchlist_auto_check_accounts_per_run` sellers with 600 s lease; verifies `email_confirmed_at` before crawling (unconfirmed or 0-competitor sellers are pushed a week out without crawling); isolates per-seller exceptions; stops claiming after 200 s (`maxDuration` is 300 s); logs and returns counts only (no user IDs, names, or URLs).
- `vercel.json`: added daily cron `{"path": "/api/v1/watchlist/run", "schedule": "0 13 * * *"}`.
- `src/services/daily_brief.py`: `_own_watch_items` reads display checks from `watchlist_store.get_checks(..., with_snapshots=False)` when the flag is on (one call per brief, no snapshots, `rank_seller_recommendations` untouched). Overnight note says `"Muse checks your watchlist once a week."` (+ `" Last check: <date>."`) only when `auto_check.enabled` and not paused; otherwise keeps today's manual sentence.

## 3. Pages & `/digest` Ceiling

- `src/api/static/digest.js` (`digest.js?v=20261124-ag1` in `digest.html`, `AGENTS.md`, `tests/test_own_competitor_checks.py`):
  - Own workspace fetches `GET /api/v1/competitors/checks` once on load.
  - When `auto_check.enabled`: displays `"Muse checks your watchlist once a week. Next check: about <Weekday, Mon D>."`, checkbox `"Check my watchlist automatically each week"` calling `POST /api/v1/competitors/auto-check`, and labels each card `"Automatic check"` vs `"Checked by you"`.
  - When flag is off (`!auto_check.enabled`): hides the auto-check bar and preserves today's exact copy word for word.
- `tests/test_api_calls_per_page_e2e.py`: raised `CEILINGS["own"]["/digest"]` from `7` to `8` (+1) solely for the one `GET /api/v1/competitors/checks` call on own `/digest` load.

## Boundaries Respected

- Did **not** touch `muse-shell.js`, `muse-shell.css`, the home section of `index.html`, `today.html`, `today.js`, `today.css`, `welcome.js`, `seller-memory.js`, `src/api/seller_memory.py`, `src/services/seller_memory.py`, or `creator.js`.
- Never applied the migration to hosted Supabase, never changed env vars, never deployed, never pushed to `main`, never made live network or Muse calls.

## Mutation Checks (All 4 Confirmed Failing, Then Restored)

1. **Drop cron secret check (`src/api/intel.py`):** disabled the `CRON_SECRET` bearer guard in `run_scheduled_watchlist_checks`.
   - Command: `DEMO_MODE=true META_MODEL_API_KEY= DEMO_KEY= .venv/bin/pytest -q tests/test_auto_watchlist.py -k "not sql"`
   - Result: **1 failed, 2 passed** — caught by `test_cron_auth_strict_and_runner_handles_errors_budget_and_privacy` (`assert 503 == 401`). Restored.
2. **Show weekly copy with flag off (`src/services/daily_brief.py`):** forced `_AUTO_OVERNIGHT_NOTE` regardless of `auto_check.enabled`.
   - Command: `DEMO_MODE=true META_MODEL_API_KEY= DEMO_KEY= .venv/bin/pytest -q tests/test_auto_watchlist.py -k "not sql"`
   - Result: **2 failed, 1 passed** — caught by `test_flag_off_keeps_exact_legacy_behavior` and `test_flag_on_button_saves_to_table_without_workspace_write_and_uses_legacy_fallback`. Restored.
3. **Call `save_workspace` from the button with flag on (`src/api/intel.py`):** added `await save_workspace(...)` inside the `if use_table:` branch of `check_own_competitors`.
   - Command: `DEMO_MODE=true META_MODEL_API_KEY= DEMO_KEY= .venv/bin/pytest -q tests/test_auto_watchlist.py -k "not sql"`
   - Result: **1 failed, 2 passed** — caught by `test_flag_on_button_saves_to_table_without_workspace_write_and_uses_legacy_fallback` (`Expected mock to not have been awaited. Awaited 1 times.`). Restored.
4. **Claim paused sellers (`supabase/migrations/watchlist_checks.sql`):** removed `not s.paused` from `muse_watchlist_claim_due`.
   - Command: `BILLING_PGLITE_DIR=/Users/nav/muse-tools/pglite/node_modules/@electric-sql/pglite node tests/watchlist_sql.mjs`
   - Result: caught by `claim returns only finished setups, skips paused and not-due, respects limit and lease` (`AssertionError: 2 !== 1`; this mutation also prompted setting `next_check_at = now() - interval '1 hour'` on the paused test user so `paused` is tested independently of `next_check_at`). Restored.

## Free Plan Budget (Measured Numbers)

- **10 sellers × 6 fixture sites × 30 pages/site (1,800 pages total):**
  - Wall time (CPU + diff + DB row serialization, excluding external network latency): **5.6 ms** (production crawls are network-wait bound; 200 s claim budget leaves 100 s headroom inside Vercel's 300 s `maxDuration`).
  - Measured snapshot JSON size: **180,960 bytes** across 60 site rows → **3,016 bytes/row average** (~18 KB per 6-site seller; **~18 MB for 1,000 sellers**, under 4% of Supabase Free's 500 MB database limit).
  - Display reads (`GET /api/v1/competitors/checks`, `/today` own brief) pass `p_with_snapshots = false`, omitting `snapshot` to keep monthly Supabase egress well within 5 GB.
  - Daily Vercel Hobby cron (`0 13 * * *`) checks up to 10 sellers/day (70 sellers/week) and keeps the Supabase Free project active past the 7-day inactivity pause window.

## Verification Results (Sequential, Offline)

1. **Local PGlite SQL test:**
   - Command: `BILLING_PGLITE_DIR=/Users/nav/muse-tools/pglite/node_modules/@electric-sql/pglite node tests/watchlist_sql.mjs`
   - Result: **`5 watchlist SQL checks passed`**.
2. **Node contracts (10/10 standalone + `portal_demo_smoke.cjs` via pytest):**
   - `account_ui_contract.cjs`, `creator_artist_feedback.cjs`, `creator_import_sprint.cjs`, `creator_journey_smoke.cjs`, `creator_studio_contract.cjs src/api/static/creator.js`, `editor_drafts_contract.cjs`, `muse_shell_resilience.cjs`, `shared_get_contract.cjs`, `today_studio_contract.cjs`, `ui_polish_contract.cjs` — all **PASS**.
3. **Full offline gate (with PGlite enabled):**
   - Command: `DEMO_MODE=true META_MODEL_API_KEY= DEMO_KEY= BILLING_PGLITE_DIR=/Users/nav/muse-tools/pglite/node_modules/@electric-sql/pglite make PY=/Users/nav/meta-smb-gtm/.venv/bin check`
   - Result: `ruff check .` passed; `ruff format --check .` (328 files formatted); **`770 passed, 0 failed, 0 skipped`** (5m 28s), including `tests/test_auto_watchlist.py` (4/4 incl. PGlite wrapper), `tests/test_auto_watchlist_e2e.py` (2/2 at 375px & 1440px), `tests/test_own_competitor_checks.py` (6/6), and `tests/test_api_calls_per_page_e2e.py`.
4. **Launch account audit:**
   - Command: `DEMO_MODE=true META_MODEL_API_KEY= DEMO_KEY= /usr/bin/python3 tests/launch_account_audit.py`
   - Result: **`27 passed, 0 failed`**.
5. **Launch browser audit:**
   - Command: `DEMO_MODE=true META_MODEL_API_KEY= DEMO_KEY= /usr/bin/python3 tests/launch_browser_audit.py`
   - Result: **`20 passed, 0 failed`**.

## Not Verified

- Applying `supabase/migrations/watchlist_checks.sql` on hosted Supabase or running `GET /api/v1/watchlist/run` against live Supabase / live Vercel Cron (held for Claude's SQL review and Nav's approval per brief).

Ownership released.
