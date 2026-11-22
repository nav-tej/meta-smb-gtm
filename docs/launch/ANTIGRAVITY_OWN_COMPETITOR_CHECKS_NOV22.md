# Antigravity Report: Real Competitor Checks for a Seller's Own Watchlist (Items 1–4)

- **Date:** November 22, 2026
- **Branch:** `gemini/own-competitor-checks-nov22`
- **Base commit:** `4ac4396` (`origin/claude/ux-gap-ad-loop-nov17`)
- **Worktree:** `/Users/nav/muse-worktrees/own-competitor-checks` (Mac checkout untouched)
- **Scope delivered:** Items 1–4 complete. Item 5 (home watchlist rows in `muse-shell.js`) deferred until Codex's `codex/today-own-brief-nov21` merges; `muse-shell.js` is untouched, and the check result shape already matches `competitorStatus()` (`status`, `checked_at`, `compared_with`, `counts.{new_listing,price_change,removed_listing}`, `error`).
- **Script version bumps:** `digest.js?v=20261122-ag1` and `digest-signup.js?v=20261122-ag1` in `src/api/static/digest.html` (pinned in `tests/test_own_competitor_checks.py`).

## Files Changed
- `src/services/competitor_checks.py` (new: watchlist extraction, snapshot capping, diffing, error classification, top insight)
- `src/api/intel.py` (added `POST /api/v1/competitors/check`)
- `src/api/static/digest.html` (added `"Check now (free)"` button and `#dgCheckStatus`, renamed `"Canonical preview topics"` to `"What to include"`, bumped script versions)
- `src/api/static/digest.js` (own-workspace competitor check cards, `"Check now (free)"` handler, real top insight, watchlist prefill for draft shops; sample digest unchanged)
- `src/api/static/digest-signup.js` (prefills `"Watched competitor 1 to 3"` from `window.__museWatchlistUrls` when no saved draft competitors exist)
- `tests/test_own_competitor_checks.py` (new: unit, route, contract, and Chromium E2E tests)
- `docs/launch/ANTIGRAVITY_OWN_COMPETITOR_CHECKS_NOV22.md` (this report)

## Summary of Implementation

### 1. Free Watchlist Check (`POST /api/v1/competitors/check`)
- Requires a signed-in, email-verified account (`resolve_account(..., require_verified=True)` → `401` signed out, `403` unverified).
- Reads selected competitors (`selected !== false`) from `preferences.competitor_entries` (falling back to `onboarding.competitors`), capped at **6 competitors**.
- Calls `reserve_scan_crawls()` from `src/api/intel.py` with every non-blocked URL before crawling (passing through `429` + `Retry-After` when over the scan limit), then crawls via `scan_guard.crawl()` with `collect_entries(..., max_urls=30)`. Zero Muse calls, zero runs used.

### 2. Snapshot Diffing & Document Size Caps (`src/services/competitor_checks.py`)
- Persists one compact snapshot per active competitor under `preferences.competitor_checks[<normalized_url>]` and prunes inactive keys on save.
- **Caps enforced:**
  - `MAX_COMPETITORS_PER_CHECK = 6`
  - `MAX_PAGES_PER_COMPETITOR = 30` / `MAX_STORED_PAGES_PER_COMPETITOR = 30`
  - `MAX_TITLE_LENGTH = 140` characters
  - `MAX_PRICE_HINT_LENGTH = 40` characters
  - `MAX_URL_LENGTH = 500` characters
  - `MAX_CHANGES_PER_KIND = 15` returned change entries per kind (`new_pages`, `removed_pages`, `price_changes`)
- First check returns `"First check: Muse now knows N of their pages. Changes show from the next check."` with zero invented changes.
- Subsequent checks return exact `new_pages` (`loc`, `title`, `price_hint`), `removed_pages`, `price_changes` (`loc`, `title`, `old_price`, `new_price`), and `counts` (`new_listing`, `removed_listing`, `price_change`).
- Blocked hosts, timeouts, missing sitemaps, and unreachable sites return plain seller-friendly error messages while preserving any prior baseline `pages` snapshot.

### 3. Workspace Writes & Seller Memory Version Safety
- Writes use optimistic locking (`save_workspace(..., expected_version=ws_version, expected_owner=account.user_id)`) and return the new `version`. Stale `expected_version` fails fast with `409` before crawling.
- `preferences.competitor_checks` is preserved across seller-memory saves by `_dump_preserving_workspace_extras()` in `src/api/seller_memory.py`.
- `/digest` does not mount `seller-memory.js`, so navigating to `/`, `/today`, or `/create` afterwards loads the new version cleanly from `GET /api/v1/seller-memory`. On any page where `window.museSellerMemory` is present, `runOwnWatchlistCheck()` calls `window.museSellerMemory?.reload?.()` after a check so the in-tab version stays synced and avoids spurious 409 conflict dialogs.

### 4. Own-Workspace Digest (`digest.html`, `digest.js`, `digest-signup.js`)
- Each watched competitor card shows last check date, badges, new page titles/links, price changes, first-check baseline note, or `"Not checked yet"`. Removed `"Queued for your scheduled digest updates."`.
- One `"Check now (free)"` button checks the whole watchlist and refreshes cards, stats, and top insight in place.
- `"This week's top insight"` shows the biggest real change (e.g., `"Summit Growth added 1 page"`), or `"No changes at the competitors you watch since <date>"`, or baseline/not-checked copy — never `"Watching N"`.
- Renamed `"Canonical preview topics"` to `"What to include"` and prefilled `"Watched competitor 1 to 3"` from the watchlist.
- Sample digest (`/digest?workspace=sample`) is unchanged and hides the check button.

### Out-of-Scope Note: Automatic Weekly Check Across All Accounts
Running automatic weekly checks for every opted-in seller would require a scheduled service-role worker (e.g., a Vercel cron or background queue protected by `CRON_SECRET`) that pages through workspaces with non-empty `competitor_entries` via a service-role Supabase RPC, enforces per-host crawl politeness and global timeouts (fanning out per batch so no single serverless invocation exceeds `maxDuration`), writes updated `preferences.competitor_checks` with optimistic locking, and skips/retries 409s without colliding with active seller edits.

## Verification

### Mutation Check
Temporarily broke `all_new` in `src/services/competitor_checks.py` (`all_new = []`) and ran `pytest tests/test_own_competitor_checks.py -q --tb=line`. Confirmed immediate failure across unit, route, and Chromium E2E tests (`3 failed, 2 passed in 16.41s`):
- `test_diff_first_check_new_removed_price_change_and_unchanged` (`{'new_listing': 0} != {'new_listing': 1}`)
- `test_competitors_check_route_auth_429_409_and_diff` (`{'new_listing': 0} != {'new_listing': 1}`)
- `test_own_digest_competitor_checks_e2e` (Playwright timeout waiting for `'Summit Growth added 1 page'`)
Restored the diff before running the verification suite below.

### Full Suite Results
- **8 Node contracts (`node tests/*.cjs`):** **8/8 passed** (`account_ui_contract.cjs`, `creator_artist_feedback.cjs`, `creator_import_sprint.cjs`, `creator_journey_smoke.cjs`, `creator_studio_contract.cjs`, `editor_drafts_contract.cjs`, `shared_get_contract.cjs`, `today_studio_contract.cjs`).
- **Full offline gate (`DEMO_MODE=true META_MODEL_API_KEY= DEMO_KEY= make PY=/Users/nav/meta-smb-gtm/.venv/bin check`):**
  - `ruff check .`: All checks passed!
  - `ruff format --check .`: `316 files already formatted`
  - `pytest`: **730 passed, 2 skipped, 1 warning in 274.22s (0:04:34)**
- **Account audit (`DEMO_MODE=true META_MODEL_API_KEY= DEMO_KEY= /usr/bin/python3 tests/launch_account_audit.py`):** **27 passed, 0 failed**.
- **Guest audit (`DEMO_MODE=true META_MODEL_API_KEY= DEMO_KEY= /usr/bin/python3 tests/launch_browser_audit.py`):** **20 passed, 0 failed**.

## What Was Not Verified
- Live crawls against external competitor domains on the public internet (all tests used faked `collect_entries` on a local `127.0.0.1` server).
- Item 5 home watchlist rows in `muse-shell.js` (deferred until Codex's `codex/today-own-brief-nov21` merges).
- Hosted Vercel deployment, live Supabase Postgres persistence, or emails (out of scope).

Ownership released.
