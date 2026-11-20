# Antigravity (Gemini) Ad-Loop Assignment Report — Nov 16/17, 2026

- **Branch:** `gemini/ad-loop-nov16`
- **Base Commit:** `e7d3094` (`origin/claude/ux-gap-nov16`)
- **Worktree:** `/tmp/muse-ad-loop` (isolated; Mac checkout `/Users/nav/meta-smb-gtm` untouched)
- **Boundaries:** `DEMO_MODE=true`, `META_MODEL_API_KEY=` (blank), `DEMO_KEY=` (blank); zero paid calls, emails, charges, deployments, or auth changes.

## Step 0 Baseline (Read-Only on `e7d3094`, Before Any Edit)
1. **Full offline gate:**
   - Command: `DEMO_MODE=true META_MODEL_API_KEY= DEMO_KEY= make PY=/Users/nav/meta-smb-gtm/.venv/bin check`
   - Result: `ruff check .` passed, `ruff format --check .` clean (`246 files already formatted`), `pytest`: **616 passed, 2 skipped, 1 warning in 133.34s (0:02:13)** (`0` failures; 2 skips require local `@electric-sql/pglite`).
2. **Real-browser `/create` Step 4 ("Ready to share") check at `375px` and `1440px`:**
   - **Sample workspace (`/create?workspace=sample`):** At both `375px` and `1440px`, the `"Prepare your first ad"` offer is visible, has zero horizontal overflow, and lands on `/first-ad?workspace=sample`.
   - **Own workspace (signed-in fixture account with uploaded `tests/fixtures/product_photo.png`):** At both `375px` and `1440px`, the `"Prepare your first ad"` offer is visible, has zero horizontal overflow, and lands on `/first-ad`.

## Files Changed (Exclusive Write Scope)
- `src/api/static/index.html`:
  - Added `"No ad running yet? Prepare your first ad →"` (`#improveFirstAdLink`, `#iterateFirstAdLink`, `#bidsFirstAdLink`) with `href="/first-ad" data-mode-link="/first-ad"` in `#loop-improve`, `#loop-iterate`, and `#tab-bids`.
  - Added `openTabFromHash` (`window?.location?.hash === '#tab-bids'`) so `/#tab-bids` and `/?workspace=sample#tab-bids` open `#tab-bids` reliably without affecting Node VM smoke tests (`tests/portal_demo.py`).
  - Bumped `welcome.js?v=20261117-adloop1`.
- `src/api/static/welcome.html`: Bumped `welcome.js?v=20261117-adloop1`.
- `src/api/static/welcome.js`: In `renderSignedInHomeWorkspace` part 7 (`#adGallery` Create stage and `#loop-improve ol.jr-recos` Improve empty state), added `"Prepare your first ad →"` using `window.museModes.ownHref('/first-ad')`.
- `src/api/static/first-ad.html` and `src/api/static/first-ad.js`:
  - On Step 4 (`#faPanel4`), added `#faBidLoopNote` telling the seller that after their ad has run for a few days they can export results from Meta Ads Manager and upload the CSV on the `#faBidAdviceLink` (`"home bid advice tab"`), with no em-dashes and no invented metrics/auto-publish claims.
  - Updated `syncUiFromState()` in `first-ad.js` so `#faBidAdviceLink` points to `/?workspace=sample#tab-bids` in sample mode and `/#tab-bids` in own mode.
  - Bumped `first-ad.js?v=20261117-adloop1`.
- `tests/test_ad_loop_links.py`: Contract and real headless Chromium E2E tests covering all added links at `375px` and `1440px` in both `own` and `sample` workspaces.
- **Do NOT touch list:** Verified untouched (`today.js`, `today.html`, `creator.js`, `creator.html`, `workspace-modes.js`, `progress.html`, `account.js`, `account.css`, `muse-shell.js`, `src/api/accounts.py`, `tests/test_first_ad_entry_points.py`, `tests/test_first_visit_import_e2e.py`, `tests/test_setup_demo_state_e2e.py`, `AGENTS.md`, `docs/launch/CLAUDE_UX_GAP_NOV16.md`, billing/auth/`supabase/`).

## Post-Change Verification (`DEMO_MODE=true META_MODEL_API_KEY= DEMO_KEY=`)
- **Targeted E2E & Contract Test:** `.venv/bin/pytest tests/test_ad_loop_links.py -v` -> **2 passed in 11.66s**.
- **Full Offline Gate:** `DEMO_MODE=true META_MODEL_API_KEY= DEMO_KEY= make PY=/Users/nav/meta-smb-gtm/.venv/bin check` -> `ruff check .` passed, `ruff format --check .` clean (`247 files already formatted`), `pytest`: **618 passed, 2 skipped, 1 warning in 142.76s (0:02:22)** (`0` failures).
- **Browser Checks (real headless Chromium at `375×844` and `1440×844`):**
  - Sample workspace (`/?workspace=sample`): verified `#improveFirstAdLink` and `#iterateFirstAdLink` point to `/first-ad?workspace=sample` with zero horizontal overflow; clicked `#improveFirstAdLink` to `/first-ad?workspace=sample`, opened Step 4, verified `#faBidLoopNote` (zero em-dashes) and `#faBidAdviceLink` (`/?workspace=sample#tab-bids`), clicked `#faBidAdviceLink` to open `#tab-bids` (`#csvUploadLabel` and `#bidsFirstAdLink` visible, zero overflow).
  - Own workspace (signed-in, onboarded fixture account): verified `welcome.js` part 7 renders `"Prepare your first ad →"` in `#adGallery` and `#improveFirstAdLink` / `#iterateFirstAdLink` point to `/first-ad` with zero horizontal overflow; clicked to `/first-ad`, opened Step 4, verified `#faBidAdviceLink` (`/#tab-bids`), clicked `#faBidAdviceLink` to open `#tab-bids` (`#csvUploadLabel` and `#bidsFirstAdLink` visible, zero overflow).
- **Not Verified:** Hosted Vercel preview deployment, real Supabase Auth/workspace persistence, and real Meta Ads Manager CSV uploads against live accounts.

Ownership released
