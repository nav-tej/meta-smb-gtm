# Antigravity (Gemini) State-Aware Copy & Sample Freshness Report — Nov 18, 2026

- **Branch:** `gemini/state-copy-nov18`
- **Base Commit:** `b10d7e9` (`origin/claude/ux-gap-ad-loop-nov17`)
- **Worktree:** `/tmp/muse-state-copy` (isolated; Mac checkout `/Users/nav/meta-smb-gtm` untouched)
- **Boundaries:** `DEMO_MODE=true`, `META_MODEL_API_KEY=` (blank), `DEMO_KEY=` (blank); zero paid calls, emails, charges, deployments, or auth changes.

## Step 0 Baseline (Read-Only on `b10d7e9`, Before Any Edit)
- **Command:** `DEMO_MODE=true META_MODEL_API_KEY= DEMO_KEY= make PY=/Users/nav/meta-smb-gtm/.venv/bin check`
- **Result:** `ruff check .` passed, `ruff format --check .` clean (`254 files already formatted`), `pytest`: **624 passed, 2 skipped, 1 warning in 207.66s (0:03:27)** (`0` failures; 2 skips require local `@electric-sql/pglite`).

## Files Changed (Exclusive Write Scope)
- `src/api/static/index.html`:
  - Added `id="competitorSnapshotsNote"` on the note below `#addCompetitorForm` and removed `"Muse Spark brief"` from the local-demo fallback copy.
  - Added `refreshVisitorCopy()` (called by `refreshSellerButtons()` and on `muse:mode-change`) updating `#addCompetitorBtn`, `#addCompetitorCost`, and `#competitorSnapshotsNote` across all four visitor states (local demo, guest, signed-in with runs, signed-in without runs or unverified email).
  - Bumped `reco-actions.js?v=20261118-ag1` and `muse-shell.js?v=20261118-ag1`.
- `src/api/static/reco-actions.js`:
  - Added `SAMPLE_CHIPS` vs `OWN_CHIPS` (`How do my prices compare?`, `Easier moves`, `Gift ideas`, `Weekly post ideas`) and `syncSteerChips()` listening to `window.museAccount.ready()`, `muse:mode-change`, and `muse:account-change`. Sample shop (guest or signed in) and local demo keep the 4 sample chips; signed-in `own` workspace gets the 4 own-workspace chips (each parsing to a distinct focus: `pricing`, `products`, `gifting`, `posting`).
- `src/api/static/muse-shell.js`:
  - In `competitorStatus()` and `mountWatchlist()`, when `window.museModes?.isSampleMode?.()` is true, skip monitor-run error badges (`"Couldn’t check"`) and newer check timestamps so the sample watchlist stays `"Saved snapshot · Nov 3"` / `"last checked Nov 3"` without modifying sample data or timestamps.
- `src/api/static/creator.html`, `digest.html`, `first-ad.html`, `progress.html`, `today.html`: Bumped `muse-shell.js?v=20261118-ag1`.
- `tests/test_state_aware_copy.py`: Verifies `parse_research_directive` maps the 4 own-workspace chips to 4 distinct focuses (`pricing`, `products`, `gifting`, `posting`), `?v=20261118-ag1` script tags across all 6 templates, and real Chromium checks at `375px` and `1440px` across all 4 visitor states + sample freshness.
- **Do NOT touch list:** Verified untouched (`seller-memory.js`, `welcome.js`, `workspace-modes.js`, `today.js`, `creator.js`, `first-ad.js`, `account.js`, `account.css`, `src/api/accounts.py`, `src/services/`, billing/auth/`supabase/`, `AGENTS.md`, `docs/launch/CLAUDE_UX_GAP_NOV16.md`, and all existing tests).

## Post-Change Verification (`DEMO_MODE=true META_MODEL_API_KEY= DEMO_KEY=`)
- **Targeted New Test (`tests/test_state_aware_copy.py`):** **2 passed in 4.99s** (`ruff check` & `ruff format --check` clean; `node --check` on `reco-actions.js` and `muse-shell.js` exited `0`).
- **Full Offline Gate (`make PY=/Users/nav/meta-smb-gtm/.venv/bin check`):**
  - `ruff check .` passed, `ruff format --check .` clean (`255 files already formatted`).
  - `pytest`: **624 passed, 2 skipped, 2 failed, 1 warning in 262.83s (0:04:22)** (2 skips require `@electric-sql/pglite`).
  - **Failure 1 (existing test conflict with new chip requirement):** `tests/test_steer_answer_e2e.py::test_steer_card_answers_with_actionable_moves_e2e` failed at `ask(page, "Why $59.99 entry")` inside the `account_own` section because `account_own` now intentionally replaces `"Why $59.99 entry"` with `"How do my prices compare?"`. Left `test_steer_answer_e2e.py` untouched per Do NOT touch rules; needs coordinator/Claude update upon integration.
  - **Failure 2 (transient in full run):** `tests/test_seller_memory_e2e.py::test_batch1_corrections_security_merge_drafts_and_handoff_e2e` failed once during the full suite run; immediate targeted rerun `.venv/bin/pytest tests/test_seller_memory_e2e.py -v` **passed 2/2 in 17.09s**.

## Browser Checks (`375×844` and `1440×844`, Real Headless Chromium)
- **Local demo (`configured=false`):** Verified `"Add · 🪙 1 run (live) / 0 in demo"`, `"Live crawl uses 1 run. In this saved demo..."`, `"Saved public snapshots from Nov 3, 2026. Only SikhiArt.com has a saved analysis; new analyses need a live server."`, and zero horizontal overflow.
- **Guest (`configured=true`, signed out):** Verified `"Add shop"`, `"3 free runs"`, `"Create a free account to analyze shops you choose."`, sample chips kept, and zero horizontal overflow.
- **Signed in with runs (`u-runs`, own workspace):** Verified `"Add and analyze · 1 run"`, `"Muse checks the shop and compares it with yours. Uses 1 run."`, own chips (`"How do my prices compare?"`, `"Easier moves"`, `"Gift ideas"`, `"Weekly post ideas"`) with zero `$59.99`/`$50` sample facts, and zero horizontal overflow.
- **Signed in without runs (`u-empty`) & unverified email (`u-unverified`):** Verified `"Add shop"` and exact plan/confirmation guidance in `#addCompetitorCost`, zero horizontal overflow.
- **Signed in viewing sample (`/?workspace=sample`) with injected `/api/v1/monitor` error (`status: "error"`, `checked_at: "2026-11-16T14:00:00Z"`):** Verified `#sellerList` shows `"Saved snapshot · Nov 3"` and never `"Couldn’t check"` or Nov 16 check times, `#competitorSnapshotsNote` shows `"Saved public snapshots from Nov 3, 2026. New analyses use 1 run."`, sample chips kept, and zero horizontal overflow.

## Out-of-Scope Observations / Proposals
1. **`welcome.js` note overwrite in `account_own`:** `welcome.js` (`renderSignedInHomeWorkspace` line 1525, `/SikhiArt|Nov 3|her website/i`) matches `"Nov 3"` in `#competitorSnapshotsNote` and overwrites it in `account_own` with `"Workspace data for <shopName>. Switch to \"Sample shop\"..."` (safe/zero sample leakage, or Claude may exclude `#competitorSnapshotsNote` if `"New analyses use 1 run."` is desired there).
2. **`tests/test_steer_answer_e2e.py`:** Update `account_own` chip click from `"Why $59.99 entry"` to `"How do my prices compare?"` when merging `gemini/state-copy-nov18`.
3. **Nav `"Local tools"` & `/welcome` header for guests:** Left untouched per brief; flagged for Nav's product decision.

## Not Verified
- Hosted Vercel preview deployment, live Muse API calls, real Supabase Auth/email/Stripe flows.

Ownership released
