# Antigravity (Gemini) Any-Business Copy & Upload Caption Report — Nov 19, 2026

- **Branch:** `gemini/create-any-business-nov18`
- **Base Commit:** `0f25fff` (`origin/claude/ux-gap-ad-loop-nov17`)
- **Worktree:** `/tmp/muse-create-any-business` (isolated; Mac checkout `/Users/nav/meta-smb-gtm` untouched)
- **Boundaries:** `DEMO_MODE=true`, `META_MODEL_API_KEY=` (blank), `DEMO_KEY=` (blank); zero paid calls, emails, charges, deployments, or auth changes.

## Step 0 Baseline (Read-Only on `0f25fff`, Before Any Edit)
- **Command:** `DEMO_MODE=true META_MODEL_API_KEY= DEMO_KEY= make PY=/Users/nav/meta-smb-gtm/.venv/bin check`
- **Result:** `ruff check .` passed, `ruff format --check .` clean (`258 files already formatted`), `pytest`: **629 passed, 2 skipped, 1 warning in 180.62s (0:03:00)** (`0` failures; 2 skips require `@electric-sql/pglite`).

## Files Changed (Exclusive Write Scope)
- `src/api/static/creator.html` & `src/api/static/creator.js`:
  - Fixed `upload(file)` in `creator.js` so `#productImageCaption` and `#productFactNote` immediately update via `formatImageMetaNote(state.imageMeta)` (`"Uploaded photo (...) · Kept on this device."`), eliminating stale `"Ek Onkar · original artwork preview..."` captions after uploading a photo.
  - Replaced the em-dash in `formatImageMetaNote()` (`Low-res web preview (...): suitable for social preview, not a print master.`).
  - Added `syncWorkspaceCopy(isOwn)` called from `updateChoices()`:
    - **Own workspace (`isOwn`):** `"START WITH WHAT YOU OFFER"`, `"Choose a product, service or offer..."`, `"What are you promoting?"` (`placeholder="A product, service or offer"`), `"YOUR PHOTO"`, `"Confirm the price and details before publishing."`, and guards `#productImageCaption`/`#productFactNote` against any sample artist wording (`Ek Onkar`, `Sarabjit`, `SikhiArt`, `artwork preview`, `with the artist`).
    - **Sample shop (`!isOwn`):** Preserves today's exact artist wording (`"START WITH WHAT YOU MAKE"`, `"Choose an artwork..."`, `"Product name"`, `"THE WORK COMES FIRST"`).
  - Bumped `creator.js?v=20261119-ag2` in `creator.html`.
- `src/api/static/first-ad.html` & `src/api/static/first-ad.js`:
  - Added `syncFirstAdCopy(sample)` and `outcomeInfoFor(key, sample)` so:
    - **Own workspace:** Uses neutral product/services wording (`"Bring visitors to your website"`, `"Best when people should read a page, see your work, or book a call first."`, `"Test a direct offer"`, `"What are you promoting?"`, `"Your website"`, `"Etsy shop or listing"`, `"Shopify store"`, `"Load images from your website"`, neutral audience placeholder, `"photo"`/`"Image"` instead of `"product photo"`, `'Offer / item'` summary label).
    - **Sample shop:** Preserves today's artist wording (`"Bring visitors to your shop"`, `"Test a direct product offer"`, `"Product or artwork name"`, `"Studio website / product page"`, `"Load shop images"`).
  - Removed all em-dashes (`—`) from customer-facing strings in both `first-ad.html` and `first-ad.js` across both modes.
  - Preserved existing Meta objective names (`Engagement / Messages`, `Traffic`, `Sales`) without adding unverified lead-form objectives.
  - Bumped `first-ad.js?v=20261119-ag2` in `first-ad.html` (`first-ad.css` unchanged).
- `tests/test_create_any_business.py`: Verifies `?v=20261119-ag2` tags, zero em-dashes in `first-ad`, upload caption update with zero sample artist leakage, and real Chromium checks at `375×844` and `1440×844` in both own (services: `"n Plus Alpha Consulting"` / `"AI growth audit"`, no price) and sample workspaces on `/create` and `/first-ad`.
- **Do NOT touch list:** Verified untouched (`index.html`, `welcome.js`, `reco-actions.js`, `seller-memory.js`, `workspace-modes.js`, `today.js`, `digest.js`, `muse-shell.js`, `account.js`, `src/models/`, `src/services/`, `src/api/*.py`, billing/auth/`supabase/`, `AGENTS.md`, and all existing tests).

## Post-Change Verification (`DEMO_MODE=true META_MODEL_API_KEY= DEMO_KEY=`)
- **Targeted New Test (`tests/test_create_any_business.py`):** **2 passed in 3.66s** (`ruff check` / `ruff format --check` clean; `node --check` on `creator.js` and `first-ad.js` exited `0`).
- **Full Offline Gate (`make PY=/Users/nav/meta-smb-gtm/.venv/bin check`):**
  - `ruff check .` passed, `ruff format --check .` clean (`259 files already formatted`).
  - `pytest`: **629 passed, 2 skipped, 2 failed, 1 warning in 182.13s (0:03:02)** (2 skips require `@electric-sql/pglite`).
  - **Failure 1 (existing test pinning old script version):** `tests/test_ad_loop_links.py::test_ad_loop_copy_and_script_version_contracts` failed at line 125 (`assert "first-ad.js?v=20261117-adloop1" in first_ad_html`) because `first-ad.html` was bumped to `first-ad.js?v=20261119-ag2` per brief. Left `tests/test_ad_loop_links.py` untouched per Do NOT touch rules; update line 125 when merging.
  - **Failure 2 (transient race in unrelated test):** `tests/test_state_aware_copy.py::test_four_visitor_states_and_sample_freshness_e2e` failed once during the full suite run (none of its files were touched); immediate targeted rerun `.venv/bin/pytest tests/test_state_aware_copy.py -v` **passed 2/2 in 3.47s**.

## Browser Checks (`375×844` and `1440×844`, Real Headless Chromium)
- **`/create` own workspace (signed-in services fixture `"n Plus Alpha Consulting"`, `"AI growth audit"`, no price):** Verified neutral copy (`START WITH WHAT YOU OFFER`, `What are you promoting?`, `YOUR PHOTO`), uploaded `tests/fixtures/product_photo.png` and verified `#productImageCaption` updated to `"Uploaded photo (...)"` with zero `"Ek Onkar"`/`"Sarabjit"`/`"SikhiArt"`/`"artwork preview"`, walked Steps 2–4 cleanly, zero horizontal overflow.
- **`/first-ad` own workspace:** Verified neutral copy (`Bring visitors to your website`, `Test a direct offer`, `What are you promoting?`, `Your website`, `Load images from your website`), walked Steps 1–4 with `"AI growth audit"`, verified prerequisites say `"photo"`/`"Image"` (no `"product photo"`), zero em-dashes, zero horizontal overflow.
- **`/create?workspace=sample` & `/first-ad?workspace=sample`:** Verified artist wording preserved on both pages (`START WITH WHAT YOU MAKE`, `Product name`, `THE WORK COMES FIRST`, `Bring visitors to your shop`, `Test a direct product offer`, `Product or artwork name`, `Load shop images`), zero em-dashes on `/first-ad`, zero horizontal overflow.

## Not Verified
- Hosted Vercel preview deployment, live Muse API calls, real Supabase persistence/Auth.

Ownership released
