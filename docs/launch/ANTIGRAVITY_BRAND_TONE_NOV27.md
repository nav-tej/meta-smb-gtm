# Antigravity Report: Brand Tone for Any Business & Draft Integration (Nov 27)

- **Branch:** `gemini/brand-tone-nov27`
- **Base:** `origin/claude/ux-gap-ad-loop-nov17` (`1566341`)
- **Worktree:** `/Users/nav/muse-worktrees/brand-tone`
- **Brief:** `docs/launch/antigravity-brand-tone-nov27.md`
- **Status:** Complete · Ownership released

## Changes (`fbf18de`)

### Part 1: Business-agnostic brand tone options in setup
- **`src/api/static/welcome.html`:** Replaced `#wkPrefTone` options with the four recommended options (`warm_story` "Warm & story-led" default, `expert_clear` "Expert & clear", `polished_premium` "Polished & premium", `direct_offer` "Direct & offer-led") and added the help line `"Shapes the wording of your starter posts and drafts."` underneath.
- **`src/api/static/welcome.js` (tone load/save lines only):** Added `LEGACY_TONE_MAP` (`collector_gallery` → `polished_premium`, `direct_gift` → `direct_offer`) next to the tone load (`hydrateStep4`) and save (`collectStep4Preferences`) lines. Legacy saved values display as their mapped option and write the mapped value only when the seller saves setup.

### Part 2: Brand tone reaches `/today` and `/create` drafts (own workspaces only)
- **`src/services/brand_tone.py` (new):** Single source of truth for `BRAND_TONES` (labels + one-line writing guides), `LEGACY_TONE_MAP`, `normalize_tone(value)` (ignores voice-profile tones `casual`/`formal`/`neutral` and unknown values), and `tone_prompt_line(value)`.
- **`src/models/content_plan.py`:** Added `tone: str | None = Field(default=None, max_length=40)` to `ContentPlanRequest`. Unknown values are accepted without 422 and ignored.
- **`src/services/content_plan.py`:**
  - `starter_plan()` adapts hooks (`_tone_hooks`) and CTAs (`_cta`) by tone for `products`, `services`, and `both` using only supplied facts, with no em-dashes and no invented scarcity/discounts/reviews/superlatives, keeping X posts within 230 characters.
  - `ContentPlanService.generate()` adds `brand_tone` (`Tone: <label>. <guide>`) to `<trusted_guidance>` when `business_type` is not `None` and the tone is known.
  - Sample shop (`business_type is None`) ignores `tone` completely; output is unchanged byte for byte.
- **`src/api/static/today.js`:** Reads `preferences.taste.tone` from the already-loaded workspace document (next to `ownBusinessType`, zero new API calls) and sends `tone` in `planPayload()` for own workspaces only (`undefined` in sample mode).
- **`src/api/static/creator.js`:** Mirrors `BRAND_TONES` and `LEGACY_TONE_MAP` (verified by parity test against `src/services/brand_tone.py`), reads `preferences.taste.tone` from the already-loaded workspace document and `handoff.tone` (when known) from recommendation handoffs, and appends `Tone: <label>. <guide>` to own-workspace `productPayload().brand_notes` (capped at 1000 chars). Sample artist `brand_notes` stay unchanged byte for byte.

### Tests Added
- **`tests/test_brand_tone.py`:** Unit tests for `normalize_tone` (canonical, legacy, voice-profile `casual`/`formal`/`neutral`, unknown), `ContentPlanRequest` non-422 unknown-tone handling, `starter_plan` distinct hooks/CTAs and wording rules across all 4 tones × 3 business types, X 230-char ceiling, byte-for-byte sample invariance (`business_type=None`), `ContentPlanService.generate` prompt inclusion/omission, and `creator.js` / `welcome.html` parity with `src/services/brand_tone.py`.
- **`tests/test_brand_tone_e2e.py`:** Local `127.0.0.1` Playwright E2E at `375px` and `1440px` (zero sideways scroll, zero page errors, zero live calls/runs): setup 4 labels + no Gallery/collector/gift + `collector_gallery` load/save as `polished_premium`, `/today` sending `expert_clear` and rendering tone-shaped hooks, `/create` draft request carrying `Tone: Expert & clear...` in `brand_notes` (route-mocked canned response), and unchanged sample `/today` and `/create`.

## Script Version Bumps (`20261127-ag1`)

- `src/api/static/today.js?v=20261127-ag1` — updated in `src/api/static/today.html`
- `src/api/static/creator.js?v=20261127-ag1` — updated in `src/api/static/creator.html` and pinned in `tests/test_create_any_business.py`
- `src/api/static/welcome.js?v=20261127-ag1` — updated in `src/api/static/welcome.html` and pinned for `welcome_html` in `tests/test_ad_loop_links.py`
  - **Note for merge:** `src/api/static/index.html` is in the Do-Not-Touch list (Claude pass 19b), so `index.html` and the `index_html` pin on line 124 of `tests/test_ad_loop_links.py` remain at `20261125-uxgap24` for Claude to bump at merge alongside `AGENTS.md`.

## Mutation Checks

Each mutation was applied temporarily, tested, confirmed to fail, and restored cleanly (`git diff --exit-code` = 0):

1. **`today.js` stops sending the tone** (`tone: isEffectiveSample() ? undefined : (ownTone || undefined),` → `tone: undefined,`):
   - Command: `DEMO_MODE=true META_MODEL_API_KEY= DEMO_KEY= .venv/bin/pytest -q tests/test_brand_tone_e2e.py`
   - Result: **FAIL (`rc=1`)** — `FAILED tests/test_brand_tone_e2e.py::test_brand_tone_setup_today_create_and_sample_e2e` (`AssertionError` on `/api/v1/content-plan` tone payload).
2. **`collector_gallery` loads as the default** (removed `collector_gallery: 'polished_premium'` from `LEGACY_TONE_MAP` in `src/api/static/welcome.js`):
   - Command: `DEMO_MODE=true META_MODEL_API_KEY= DEMO_KEY= .venv/bin/pytest -q tests/test_brand_tone_e2e.py`
   - Result: **FAIL (`rc=1`)** — `FAILED tests/test_brand_tone_e2e.py::test_brand_tone_setup_today_create_and_sample_e2e` (`AssertionError` on `#wkPrefTone` value).
3. **`starter_plan` applies the tone when `business_type` is `None`** (`if request.business_type is None:` → `if False and request.business_type is None:` in `src/services/content_plan.py`):
   - Command: `DEMO_MODE=true META_MODEL_API_KEY= DEMO_KEY= .venv/bin/pytest -q tests/test_brand_tone.py`
   - Result: **FAIL (`rc=1`)** — `FAILED tests/test_brand_tone.py::test_sample_business_type_none_ignores_tone_byte_for_byte`.

## Verification Gate Results

- **All 10 standalone Node contracts:** 10/10 passed (`account_ui_contract.cjs`, `creator_artist_feedback.cjs`, `creator_import_sprint.cjs`, `creator_journey_smoke.cjs`, `creator_studio_contract.cjs src/api/static/creator.js`, `editor_drafts_contract.cjs`, `muse_shell_resilience.cjs`, `shared_get_contract.cjs`, `today_studio_contract.cjs`, `ui_polish_contract.cjs`).
- **Full offline gate (`DEMO_MODE=true META_MODEL_API_KEY= DEMO_KEY= make PY=/Users/nav/meta-smb-gtm/.venv/bin check`):**
  - `ruff check .` → `All checks passed!`
  - `ruff format --check .` → `348 files already formatted`
  - `pytest` → **868 passed, 3 skipped, 0 failed** in 415.09s (including `tests/test_api_calls_per_page_e2e.py`).
- **Launch account audit (`DEMO_MODE=true META_MODEL_API_KEY= DEMO_KEY= /usr/bin/python3 tests/launch_account_audit.py`):** **27 passed, 0 failed**.
- **Launch browser audit (`DEMO_MODE=true META_MODEL_API_KEY= DEMO_KEY= /usr/bin/python3 tests/launch_browser_audit.py`):** **20 passed, 0 failed**.

## Ownership

Ownership released. All Do-Not-Touch boundaries respected. Ready for Claude review and integration.
