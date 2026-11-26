# Antigravity Report: Own Pages Sample-Shop Leak Audit (Nov 26)

- **Branch:** `gemini/own-pages-sample-audit-nov26`
- **Base:** `origin/claude/ux-gap-ad-loop-nov17` (`99d93a3`)
- **Worktree:** `/Users/nav/muse-worktrees/own-pages-audit`
- **Brief:** `docs/launch/antigravity-own-pages-sample-audit-nov26.md`
- **Status:** Complete · Ownership released

## Summary

Audited `/today`, `/create`, `/digest`, `/first-ad`, `/progress`, and `/welcome?edit=1` on a local `127.0.0.1` server across four fake signed-in own accounts (`svc` services business, `prod` products seller, `rich` seller with saved `competitor_checks` and one saved YouTube video, and `empty` post-setup seller) at both `375px` and `1440px`, expanding `<details>` panels, modals, and wizard steps. Fixed every leak in allowed files without changing `?workspace=sample`, added `tests/test_own_pages_no_sample_e2e.py`, verified all 5 per-page mutation checks, and ran the full offline gate, both launch audits, and all 10 standalone Node contracts.

## Leaks Found and Fixed

| Page | What leaked | Why | The fix | The commit |
|---|---|---|---|---|
| `/create` | Expanding "More details (optional)" (`#moreDetails`) showed `#artistChannels`: `"Pixels is your preferred shop. Fine Art America is also available. You promote on Instagram and your linked Facebook page. Etsy is closed and is left out of this artist setup."` Also `<datalist id="collectionSuggestions">` offered `"Empowering Women"`. | `creator.html` rendered `#artistChannels` without `hidden`, and `creator.js` `initNeutralWorkspace()` never hid `#artistChannels` or cleared `#collectionSuggestions` in own workspaces (only `resetOffers(false)` and `applyDocument()` touched `#artistChannels`). | Added `hidden` to `#artistChannels` in `src/api/static/creator.html`; in `src/api/static/creator.js` hid `#artistChannels` in `initNeutralWorkspace()` and `syncWorkspaceCopy(isOwn)` whenever `isOwn \|\| !isSampleArtist()`, and populated `#collectionSuggestions` only for the sample artist (empty in own workspaces). Sample mode (`?workspace=sample`) keeps both unchanged. | `f84f87b` |
| `/first-ad` | Step 3 (`#faAudience`) and Step 4 (`#faHandoffSummary` & exported checklist) prefilled `"Unconfirmed starting audience (edit before sharing): Buyers looking for handmade studio work"`, defaulted `businessName` to `"Your Studio"`, canvas fallback to `"Your studio work"`, and URL prerequisite copy to `"shop visits or sales"` for services accounts. | `freshState(false)` and `buildPrerequisites()` in `src/api/static/first-ad.js` hardcoded handmade/studio/shop copy for all non-sample accounts. | Updated `src/api/static/first-ad.js` own-mode defaults to `"People looking for what you offer"`, `"Your business"`, `"Your offer"`, and `"website visits or sales"` (keeping `freshState(true)` and sample copy untouched). | `f84f87b` |
| `/today` | Expanding `#researchWorkspace` showed `"Explore the artist’s saved research →"` linking to `/portal`. In `#setup` modal for services accounts, `label[for="shopUrl"]` still said `"Shop or product link"`, `#readListing` said `"Use this listing"`, and URL placeholders said `"https://your-shop.com"`. | `today.html` had a static artist-research link without an ID, and `applyOfferWording()` in `src/api/static/today.js` did not swap `#researchSavedLink`, `label[for="shopUrl"]`, `#readListing`, or the URL input placeholders. | Added `id="researchSavedLink"` in `src/api/static/today.html`; extended `applyOfferWording()` in `src/api/static/today.js` to swap `#researchSavedLink` to `"Open your full workspace →"` (`/`), and for services accounts swap `label[for="shopUrl"]` (`"Website or page link"`), `#readListing` (`"Use this page"`), and `#shopUrl`/`#quickShopUrl` placeholders (`"https://your-website.com"`). Sample mode restores original text/href. | `f84f87b` |
| `/welcome?edit=1` | Step 1 `#wkMoreShopUrls` placeholder listed `"fineartamerica.com/profiles/your-shop, saatchiart.com/your-shop"`; Step 4 `#wkPrefFocus` placeholder read `"e.g. Focus on gift buyers and entry-priced prints under $50."`. | Static sample-artist/art-marketplace placeholders in `src/api/static/welcome.html`. | Replaced placeholders in `src/api/static/welcome.html` with `"e.g. your-shop.etsy.com, your-store.myshopify.com"` and `"e.g. Focus on client inquiries, seasonal offers, or our signature product."`. | `f84f87b` |
| `/digest` | `#digestSignup .dg-sub-lede` referenced `"Fine Art America"` (`"Add up to 3 competitor shops (Shopify, Fine Art America or any public shop page)..."`). | Static sample-marketplace wording in `src/api/static/digest.html`. | Updated `#digestSignup .dg-sub-lede` in `src/api/static/digest.html` to `"Add up to 3 competitor sites (Shopify, Etsy or any public website). Each Monday we check their public pages and email you new pages, removals and price changes..."`. | `f84f87b` |
| `/progress` | No sample leaks, no page errors, no overflow at `375px` or `1440px`. | Already scoped per account (`muse.outcomes.<userId>` / `/api/v1/outcomes`) with neutral copy. | No source edit needed; covered by `tests/test_own_pages_no_sample_e2e.py`. | `f84f87b` |

## Left Alone / In Claude's Do-Not-Touch Files

- **`src/api/static/muse-shell.js` (line 1256 — DO NOT TOUCH):** On `/today` for a services business (`svc` / `rich`), the brief frame renders `"Your shop’s brief is not built yet"` via `showBriefFrame('Your shop’s brief is not built yet', ...)` when the brief is empty/unbuilt. Reported here for Claude to adjust in `muse-shell.js`. (Note: the notification bell on `99d93a3` rendered empty `"You’re all caught up."` in own mode during our audit.)
- **`src/api/static/welcome.js` (DO NOT TOUCH):** `/welcome?edit=1` static step headings and labels (`"Your shop"`, `"Choose 1 to 6 similar shops to watch for price changes and new listings"`, `"Can you change prices on your main shop?"`, `"Gallery & collector-focused"`) are shared across products and services; per-`business_type` copy adaptation on `/welcome` belongs in `welcome.js`. Left untouched so products sellers and existing welcome tests stay intact.
- **`OWN_DESTINATIONS.etsy` (`"Etsy shop or listing"`) in `creator.js` / `today.js`:** Kept intact because `tests/test_create_destinations_and_context_e2e.py` and `tests/test_today_destinations_e2e.py` explicitly assert that label.
- **`digest.html` topic label (`"New and removed listings or pages"`):** Already includes `"or pages"` for non-shop businesses; left untouched.

## Script Version Bumps (`20261126-ag1`)

- `src/api/static/creator.js?v=20261126-ag1` — updated in `src/api/static/creator.html` and pinned in `tests/test_create_any_business.py`
- `src/api/static/first-ad.js?v=20261126-ag1` — updated in `src/api/static/first-ad.html` and pinned in `tests/test_ad_loop_links.py` and `tests/test_create_any_business.py`
- `src/api/static/today.js?v=20261126-ag1` — updated in `src/api/static/today.html`
- `AGENTS.md` version line was not edited (per brief, Claude updates it at merge).

## Mutation Checks

Each changed page's fix was reverted individually against `HEAD~1`, tested with `DEMO_MODE=true META_MODEL_API_KEY= DEMO_KEY= .venv/bin/pytest -q tests/test_own_pages_no_sample_e2e.py`, confirmed to fail, and restored cleanly (`git diff --exit-code` verified `0`):

1. **`/today` (`git checkout HEAD~1 -- src/api/static/today.html src/api/static/today.js`):**
   - Result: **FAIL (`rc=1`)** — `AssertionError: svc@375 /today body leaked sample term 'artist’s saved research'`
2. **`/create` (`git checkout HEAD~1 -- src/api/static/creator.html src/api/static/creator.js`):**
   - Result: **FAIL (`rc=1`)** — `AssertionError: svc@375 /create body leaked sample term 'pixels'`
3. **`/digest` (`git checkout HEAD~1 -- src/api/static/digest.html`):**
   - Result: **FAIL (`rc=1`)** — `AssertionError: svc@375 /digest digestSignup lede leaked sample term 'fine art america'`
4. **`/first-ad` (`git checkout HEAD~1 -- src/api/static/first-ad.html src/api/static/first-ad.js`):**
   - Result: **FAIL (`rc=1`)** — `AssertionError: svc@375 /first-ad step3 audience leaked sample term 'handmade studio work'`
5. **`/welcome?edit=1` (`git checkout HEAD~1 -- src/api/static/welcome.html`):**
   - Result: **FAIL (`rc=1`)** — `AssertionError: svc@375 /welcome?edit=1 inputs leaked sample term 'fineartamerica'`

## Verification Gate Results

- **New E2E test + version pins:** `DEMO_MODE=true META_MODEL_API_KEY= DEMO_KEY= .venv/bin/pytest -q tests/test_own_pages_no_sample_e2e.py tests/test_create_any_business.py tests/test_ad_loop_links.py` → **5 passed**
- **All 10 standalone Node contracts:**
  - `node tests/account_ui_contract.cjs` → PASS
  - `node tests/creator_artist_feedback.cjs` → PASS
  - `node tests/creator_import_sprint.cjs` → PASS (5/5)
  - `node tests/creator_journey_smoke.cjs` → PASS (7/7)
  - `node tests/creator_studio_contract.cjs src/api/static/creator.js` → PASS
  - `node tests/editor_drafts_contract.cjs` → PASS
  - `node tests/muse_shell_resilience.cjs` → PASS
  - `node tests/shared_get_contract.cjs` → PASS
  - `node tests/today_studio_contract.cjs` → PASS
  - `node tests/ui_polish_contract.cjs` → PASS
- **Full offline gate:** `DEMO_MODE=true META_MODEL_API_KEY= DEMO_KEY= make PY=/Users/nav/meta-smb-gtm/.venv/bin check`
  - `ruff check .` → `All checks passed!`
  - `ruff format --check .` → `338 files already formatted`
  - `pytest` → 843 passed, 3 skipped, 1 transient timeout in `tests/test_today_own_brief_e2e.py::test_today_own_brief_e2e[own-services-1440]` (5s wait on `#handoffGuidanceBox`); immediately re-run `DEMO_MODE=true META_MODEL_API_KEY= DEMO_KEY= .venv/bin/pytest -q tests/test_today_own_brief_e2e.py` → **16 passed in 37.67s**.
- **Launch account audit:** `DEMO_MODE=true META_MODEL_API_KEY= DEMO_KEY= /usr/bin/python3 tests/launch_account_audit.py` → **27 passed, 0 failed**
- **Launch browser audit:** `DEMO_MODE=true META_MODEL_API_KEY= DEMO_KEY= /usr/bin/python3 tests/launch_browser_audit.py` → **20 passed, 0 failed**

## Ownership

Ownership released. Ready for Claude review and integration.
