# Antigravity Report: Digest Saved Context & Steady Own-Brief E2E (Nov 26)

- **Branch:** `gemini/digest-saved-context-nov26`
- **Base:** `origin/claude/ux-gap-ad-loop-nov17` (`ec7bc44`)
- **Worktree:** `/Users/nav/muse-worktrees/digest-saved-context`
- **Brief:** `docs/launch/antigravity-digest-saved-context-nov26.md`
- **Status:** Complete · Ownership released

## Part 1: `/digest` Uses Saved Ad Library Pages & Analysis Notes (Own Workspace)

- **Implementation (`ddf6f34`):**
  - Updated `extractWatchlist(wsDoc)` in `src/api/static/digest.js` to read `ad_library_page_id`, note (`rationale`, else `reason`), and `analyzed_at` from the already-loaded workspace document (`preferences.competitor_entries` merged with `onboarding.competitors` by normalized URL). Zero new API calls; own `/digest` stays within the 8-call ceiling in `tests/test_api_calls_per_page_e2e.py`.
  - Validated `ad_library_page_id` strictly against `/^[0-9]{5,20}$/` before building any link.
  - On each watched competitor card in `renderOwnWorkspaceDigest()`:
    - **Linked page present:** renders `"See their ads on Meta ↗"` linking to `https://www.facebook.com/ads/library/?active_status=active&ad_type=all&country=ALL&view_all_page_id=<id>&search_type=page&media_type=all`.
    - **No linked page (or invalid ID):** renders `Search Meta ads for “<query>” (all advertisers) ↗` (using the same `adLibraryQuery` rule as `welcome.js` / `index.html`) plus `"Link their exact page"` linking to `/#loop-research`.
    - **Saved note:** renders `rationale` (else `reason`) as plain text via `document.createTextNode`.
    - **Saved analysis:** only when `analyzed_at` is set, renders `"From your analysis, <Mon D>"` (date formatted from `analyzed_at`) plus `"View analysis"` linking to `/#loop-research`. Never shows `analysis_summary` as a fresh check.
  - All DOM rendering uses `el()` (`document.createElement` / `document.createTextNode`, never `innerHTML`).
  - `?workspace=sample` (`renderSampleCompetitors()`) is untouched.
- **Script version:** `src/api/static/digest.js?v=20261126-ag2` (bumped in `src/api/static/digest.html` and pinned in `tests/test_own_competitor_checks.py`; `AGENTS.md` version line left for Claude at merge).
- **New E2E test:** `tests/test_digest_saved_context_e2e.py` verifies linked page, unlabeled/keyword fallback + `"Link their exact page"`, invalid page ID rejection, saved note + `"From your analysis, Nov 24"` + `"View analysis"`, zero horizontal overflow at `375px` and `1440px`, zero page errors, and unchanged `?workspace=sample`.

## Part 2: Steady `tests/test_today_own_brief_e2e.py` Under Load

- **Root cause:** After clicking a brief move link to `/create?workspace=own&sm_handoff=*`, the test waited only for `document.documentElement.dataset.museMode === 'account_own'`. Under CPU load, `workspace-modes.js` sets `account_own` *before* `creator.js`'s async `await window.museAccount.loadWorkspace(s.ownerId)` completes and calls `applyRecommendationHandoff(handoff)`. Clicking `#nextButton` before `applyRecommendationHandoff()` sets `state.handoffActive = true` (and updates `#nextButton` text to `"Make it yours →"`) navigated from Step 0 to Step 1 instead of Step 2, leaving `#handoffGuidanceBox` (in Step 2) hidden until timeout.
- **Fix (`ddf6f34`):** In `tests/test_today_own_brief_e2e.py`, wait on the real DOM state set by `applyRecommendationHandoff()` (`#nextButton` text is `"Make it yours →"` and `#handoffGuidanceBox` is not `hidden`) before interacting with Step 0 and clicking `#nextButton`. No timeout increases or weakened assertions.
- **5× load proof:** Ran `DEMO_MODE=true META_MODEL_API_KEY= DEMO_KEY= .venv/bin/pytest -q tests/test_today_own_brief_e2e.py` 5 times in a row while `tests/test_own_pages_no_sample_e2e.py` and `tests/test_any_business_home_e2e.py` ran concurrently in Chromium:
  - Run 1/5: `16 passed in 37.10s`
  - Run 2/5: `16 passed in 37.20s`
  - Run 3/5: `16 passed in 37.22s`
  - Run 4/5: `16 passed in 37.72s`
  - Run 5/5: `16 passed in 36.81s`

## Mutation Checks

Each mutation was applied to `src/api/static/digest.js`, tested with `DEMO_MODE=true META_MODEL_API_KEY= DEMO_KEY= .venv/bin/pytest -q tests/test_digest_saved_context_e2e.py`, confirmed to fail, and restored cleanly (`git diff --exit-code` = 0):

1. **Ignore `ad_library_page_id`** (`if (comp.ad_library_page_id)` → `if (false && comp.ad_library_page_id)`):
   - Result: **FAIL (`rc=1`)** — `AssertionError` on Card 1 (`Brightpath Consulting` showed `(all advertisers)` instead of the linked page URL).
2. **Drop `(all advertisers)` from keyword label** (`` `Search Meta ads for “${query}” (all advertisers) ↗` `` → `` `Search Meta ads for “${query}” ↗` ``):
   - Result: **FAIL (`rc=1`)** — `AssertionError` on Card 2 keyword link text assertion.
3. **Show analysis line without `analyzed_at`** (`if (comp.analyzed_at)` → `if (true || comp.analyzed_at)`):
   - Result: **FAIL (`rc=1`)** — `AssertionError` on Card 2 (`Summit Growth Partners LLC` unexpectedly rendered `"From your analysis"`).

## Verification Gate Results

- **All 10 standalone Node contracts:** 10/10 passed (`account_ui_contract.cjs`, `creator_artist_feedback.cjs`, `creator_import_sprint.cjs`, `creator_journey_smoke.cjs`, `creator_studio_contract.cjs src/api/static/creator.js`, `editor_drafts_contract.cjs`, `muse_shell_resilience.cjs`, `shared_get_contract.cjs`, `today_studio_contract.cjs`, `ui_polish_contract.cjs`).
- **Full offline gate (`DEMO_MODE=true META_MODEL_API_KEY= DEMO_KEY= make PY=/Users/nav/meta-smb-gtm/.venv/bin check`):**
  - `ruff check .` → `All checks passed!`
  - `ruff format --check .` → clean
  - `pytest` → **858 passed, 3 skipped, 0 failed** in 403.05s (including `tests/test_api_calls_per_page_e2e.py` and `tests/test_today_own_brief_e2e.py`).
- **Launch account audit (`DEMO_MODE=true META_MODEL_API_KEY= DEMO_KEY= /usr/bin/python3 tests/launch_account_audit.py`):** **27 passed, 0 failed**.
- **Launch browser audit (`DEMO_MODE=true META_MODEL_API_KEY= DEMO_KEY= /usr/bin/python3 tests/launch_browser_audit.py`):** **20 passed, 0 failed**.

## Ownership

Ownership released. No do-not-touch files were modified. Ready for Claude review and integration.
