# Antigravity Report: Browser Tests Under Load

- **Date:** November 20, 2026
- **Branch:** `gemini/tests-under-load-nov20`
- **Base commit:** `46643eb` (`origin/claude/ux-gap-ad-loop-nov17`)
- **Worktree:** `/tmp/muse-tests-under-load` (isolated; Mac checkout untouched; tests and report only — zero app code edits)

## Files Changed (tests and report only)
- `tests/e2e_helpers.py` (new shared helper: `with_cpu_throttle()` / `CDP_THROTTLE_SNIPPET` for Chromium CDP `Emulation.setCPUThrottlingRate` via `MUSE_E2E_CPU_THROTTLE`)
- `tests/test_promotion_guidance_e2e.py`
- `tests/test_seller_memory_e2e.py`
- `tests/test_setup_demo_state_e2e.py`
- `tests/test_steer_voice_progress.py`
- `tests/test_competitor_research_any_business.py`
- `tests/test_ad_loop_links.py`
- `tests/test_create_destinations_and_context_e2e.py`
- `docs/launch/ANTIGRAVITY_TESTS_UNDER_LOAD_NOV20.md` (this report)

## CDP CPU Throttling Matrix (Rates 1, 4, 6 — Before vs. After)

Measured sequentially with Chromium CDP `Emulation.setCPUThrottlingRate` (zero CPU burners):

| Test | Before (1x) | Before (4x) | Before (6x) | After (1x) | After (4x) | After (6x) |
|---|---|---|---|---|---|---|
| `test_promotion_guidance_5_click_handoff_truthfulness_and_isolation_e2e` | PASS (9.2s) | PASS (11.2s) | PASS (14.9s) | PASS (5.9s) | PASS (7.8s) | PASS (9.3s) |
| `test_batch1_corrections_security_merge_drafts_and_handoff_e2e` | PASS (5.6s) | PASS (8.1s) | PASS (10.2s) | PASS (5.2s) | PASS (7.6s) | PASS (9.6s) |
| `test_dashboard_before_setup_is_an_explicit_demo_e2e` | PASS (13.5s) | PASS (19.2s) | PASS (23.5s) | PASS (11.4s) | PASS (16.6s) | PASS (20.3s) |
| `test_steer_voice_progress_ui` | PASS (8.3s) | PASS (9.7s) | PASS (11.3s) | PASS (5.0s) | PASS (7.9s) | PASS (8.4s) |
| `test_own_workspace_diagnostics_honest_ads_and_business_type_e2e` | PASS (6.9s) | PASS (9.1s) | PASS (11.6s) | PASS (6.7s) | PASS (8.6s) | PASS (11.2s) |
| `test_ad_loop_links_375_and_1440_own_and_sample_e2e` | PASS (10.4s) | PASS (12.6s) | PASS (15.2s) | PASS (12.2s) | PASS (13.2s) | PASS (13.8s) |
| `test_create_destinations_muse_context_and_legacy_draft_e2e` | PASS (5.1s) | PASS (8.3s) | PASS (10.5s) | PASS (4.7s) | PASS (7.7s) | PASS (9.9s) |

## What Each Fix Waits On (Zero Sleeps, Zero Weakened Assertions)
1. **`tests/test_promotion_guidance_e2e.py`:** Replaced all 7 `wait_until="networkidle"` navigations with `wait_until="domcontentloaded"` + explicit DOM/state waits (`#smShowImproveTabBtn` visible, `document.documentElement.dataset.museMode === 'account_own'`, `#loadAccountDraft:not([disabled])`). Replaced the hardcoded user-home scratch path with pytest `tmp_path`, wired `with_cpu_throttle()`, and gave the multi-context subprocess a 150s ceiling alongside the condition waits (cut rate-6 runtime from `14.9s` to `9.3s`).
2. **`tests/test_seller_memory_e2e.py` (`test_batch1_corrections_security_merge_drafts_and_handoff_e2e`):** Already used condition waits and `expect_response` from the Nov 19 stabilization; wired `with_cpu_throttle()` and raised the 5-context subprocess ceiling from `60s` to `150s` so heavy host load no longer triggers premature 60s subprocess timeouts.
3. **`tests/test_setup_demo_state_e2e.py` (`test_dashboard_before_setup_is_an_explicit_demo_e2e`):**
   - Replaced `page.wait_for_timeout(600)` after `window.museAccount.refresh()` with `page.expect_response("/api/v1/account/me")` + `wait_for_function` checking `museModeBanner.dataset.setup === 'pending'`.
   - Replaced `page.goto(..., wait_until="networkidle"); assert mode(page) == "guest_entry"` with `wait_until="domcontentloaded"` + `wait_for_function("() => document.documentElement.dataset.museMode === 'guest_entry'")` before asserting `mode(page) == "guest_entry"`.
   - Wrapped the sign-in `window.museAccount.refresh()` in `expect_response("/api/v1/account/me")`.
4. **`tests/test_steer_voice_progress.py` (`test_steer_voice_progress_ui`):**
   - Replaced all 4 `wait_until="networkidle"` navigations with `wait_until="domcontentloaded"` + visibility/text condition waits.
   - Removed all 3 `page.wait_for_timeout(...)` calls (`100ms`, `200ms`, `200ms`). On `#pgLogForm` submit, now waits on `page.expect_response(POST /api/v1/outcomes)` + `wait_for_function` for `#pgNetReturn === '+$38'` and `#pgMovesCount === '1'`; on account switch to `usr_prog_b`, waits on `wait_for_function` for `#pgNetReturn === '—'` and `#pgMovesCount === '0'`.
5. **`tests/test_competitor_research_any_business.py` (`test_own_workspace_diagnostics_honest_ads_and_business_type_e2e`):** Added `document.documentElement.dataset.museMode === 'account_own'` to the `pn` wait condition alongside `'Not counted yet'`, wired `with_cpu_throttle()`, and raised the subprocess ceiling from `90s` to `150s`.
6. **`tests/test_ad_loop_links.py` (`test_ad_loop_links_375_and_1440_own_and_sample_e2e`):** Added `window.museModes?.isSampleMode?.() === true` to sample-load wait, explicit `wait_for(state="visible")` / `wait_for_selector("...:visible")` before asserting visibility on stage switches (`#adGallery a`, `#improveFirstAdLink`, `#iterateFirstAdLink`), wired `with_cpu_throttle()`, and raised subprocess ceiling from `90s` to `150s`.
7. **`tests/test_create_destinations_and_context_e2e.py`:** Wired `with_cpu_throttle()` and raised subprocess ceiling from `120s` to `150s`.

## App Race Analysis (Items 3, 4, and 5)
- **Item 3 (`test_dashboard_before_setup_is_an_explicit_demo_e2e` — `mode(page) == "guest_entry"`): Test-side race, NOT an app race.** `networkidle` can resolve right as `/api/v1/account/me` finishes before `workspace-modes.js`'s `.then(...)` handler writes `document.documentElement.dataset.museMode = 'guest_entry'`. Waiting on `dataset.museMode === 'guest_entry'` fixes it cleanly.
- **Item 4 (`test_steer_voice_progress_ui` — `#pgNetReturn` expected `+$38`): Test-side race, NOT an app race.** In `src/api/static/progress.html:356-409`, the `#pgLogForm` submit handler saves locally, `await`s `POST /api/v1/outcomes` (lines 376-396), and then calls `render()` (line 408). The test previously used `page.wait_for_timeout(200)`, which raced whenever `POST /api/v1/outcomes` took > 200ms on a busy host. Waiting on `expect_response(POST /api/v1/outcomes)` + `#pgNetReturn` fixes it cleanly.
- **Item 5 (`test_own_workspace_diagnostics_honest_ads_and_business_type_e2e` — 30s timeout for `'Not counted yet'`): REAL APP RACE FOUND (untouched, for Claude to route).**
  - **Location:** `src/api/static/index.html:3786` (`activateWorkspace('sarabjit_singh')` called when `fetch('/api/v1/demo-presets')` resolves) vs. `src/api/static/index.html:2643-2678` (`loadBriefCache()` → `loadOwnCompetitorAdSignals()`).
  - **What happens:** On a signed-in own-workspace load of `/`, if `/api/v1/competitors/ads` finishes before `/api/v1/demo-presets` (which happens under load, and especially in tests where `/api/v1/competitors/ads` is route-mocked instantaneously while `/api/v1/demo-presets` hits FastAPI), `loadOwnCompetitorAdSignals()` renders `"Not counted yet"` into `#metaAdsContainer`, and then `activateWorkspace('sarabjit_singh')` runs at line 3786 and unconditionally calls `renderDiagnosticsAndAds(ws)` with the sample shop `ws`, overwriting `#diagnosticsContainer` and `#metaAdsContainer` with Sarabjit's sample diagnostics and `[sample]` hooks. `window.__museApplySignedInWorkspace()` (line 3790) re-renders `#sellerList` and `#adGallery` but does not re-render `#diagnosticsContainer` or `#metaAdsContainer`, leaving the own workspace stuck on sample diagnostics/ads until reload.
  - **How to reproduce:** Load `/` signed in as an onboarded seller with at least one competitor while delaying `/api/v1/demo-presets` by ~150ms (or under host load with mocked `/api/v1/competitors/ads`); observe `#metaAdsContainer` momentarily show `"Not counted yet"` and then get overwritten by `[sample]` hooks permanently.
  - **Suggested owner/fix (not applied here):** Guard `renderDiagnosticsAndAds(ws)` in `activateWorkspace()` (`index.html:3786`) when `!window.museModes?.isSampleMode?.()` and a signed-in user is active, or have `__museApplySignedInWorkspace` re-trigger `renderDiagnosticsAndAds` / `loadOwnCompetitorAdSignals`.

## Verification

### Before-Edit Baseline (`46643eb`)
- `DEMO_MODE=true META_MODEL_API_KEY= DEMO_KEY= make PY=/Users/nav/meta-smb-gtm/.venv/bin check`:
  - `ruff check .`: All checks passed!
  - `ruff format --check .`: `298 files already formatted`
  - `pytest`: **695 passed, 2 skipped, 1 warning in 214.02s (0:03:34)**

### After-Edit Audits
- Account audit (`DEMO_MODE=true META_MODEL_API_KEY= DEMO_KEY= /usr/bin/python3 tests/launch_account_audit.py`): **27 passed, 0 failed**.
- Guest audit (`DEMO_MODE=true META_MODEL_API_KEY= DEMO_KEY= /usr/bin/python3 tests/launch_browser_audit.py`): **20 passed, 0 failed**.

### After-Edit Full Offline Gate (3 Consecutive Runs)
Command: `DEMO_MODE=true META_MODEL_API_KEY= DEMO_KEY= make PY=/Users/nav/meta-smb-gtm/.venv/bin check`
- **Run 1:** `ruff check` + `ruff format --check` clean; pytest **695 passed, 2 skipped, 1 warning in 203.20s (0:03:23)** (`rc=0`).
- **Run 2:** `ruff check` + `ruff format --check` clean; pytest **695 passed, 2 skipped, 1 warning in 202.96s (0:03:22)** (`rc=0`).
- **Run 3:** `ruff check` + `ruff format --check` clean; pytest **695 passed, 2 skipped, 1 warning in 203.73s (0:03:23)** (`rc=0`).

Ownership released.
