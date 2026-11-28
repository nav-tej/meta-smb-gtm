# Antigravity Report: Services Business Walkthrough (Nov 28)

- **Branch:** `gemini/services-walkthrough-nov28`
- **Base:** `origin/claude/ux-gap-ad-loop-nov17` (`69b3561`)
- **Worktree:** `/Users/nav/muse-worktrees/services-walkthrough`
- **Brief:** `docs/launch/antigravity-services-walkthrough-nov28.md`
- **Status:** Complete · Ownership released

## Account Walked

Local fixture account (`n Plus Alpha Ventures`, `business_type: "services"`, `https://nplusalpha.test`, goal `"More client inquiries"`, LinkedIn + website, 60 minutes/week, tone `expert_clear`, `free` plan, 3 competitors — 1 with linked Ad Library page + saved analysis + `briefs[url]`, 1 with seller note + `price_reference`, 1 empty — 1 saved YouTube video, 2 logged outcomes on `/progress`), walked at `375px` and `1440px` across `/today`, `/create`, `/first-ad`, `/digest`, `/progress`, and `/account` with zero live calls and zero Muse runs.

## Findings Table

| Page | Width | What happens | Why it's wrong for a services business | Status |
|---|---|---|---|---|
| `/create` | 375, 1440 | Step 2 goal card 02 (`[data-goal="gift"]`) showed `"Offer a thoughtful gift — Help someone picture who they might give it to."`, even though clicking it displayed `serviceGoals.gift` (`"Highlight a client outcome"`). | Gift-giving copy assumes physical retail items and contradicted the services idea card beneath it. | Fixed in `476fa8f` (`creator.js`: services sees `"Highlight a client outcome"` / `"Explain what you help with and what working with you looks like."`; products & sample unchanged) |
| `/create` | 375, 1440 | Step 3 `#generateButton` read `"Preview a room scene"`; Step 1 `#moreDetails` had `label[for="sellerName"]` `"Your shop or name"` and `#shopUrl` placeholder `"https://your-shop.com"`; Step 3 unreviewed error said `"product details"`; Step 4 export footnote said `"Images are social previews, not production print files."`; `<title>` said `"Create Your Next Shop Post"`. | Assumes wall-art room staging, physical prints, and a product shop. | Fixed in `476fa8f` (`creator.html`, `creator.js`: services sees `"Preview an AI background"`, `"Your business name"`, `"https://your-website.com"`, `"offer details"`, print-files sentence omitted, `<title>` `"Create Your Next Post \| Muse Growth Studio"`; products & sample unchanged) |
| `/today` | 375, 1440 | `#resultsDetails` read `"From your channel insights or shop."`; `#setup` modal had `"Weekly sales target (optional)"`; `.sources` read `"A post or a sales target does not guarantee sales."`; after logging 7-day counts, `#insightTitle` showed `"12 shop clicks · 2 sales"` and `#resultsSource` showed `"weekly goal: X sales"`. | Services businesses track website/link clicks and clients/inquiries, not shop clicks and unit sales targets. | Fixed in `476fa8f` (`today.js`: `applyOfferWording()` & `render()` swap to `"website"`, `"Weekly client goal (optional)"`, `"client inquiries or sales"`, and `"link clicks · clients"` for services; products & sample unchanged) |
| `/today` | 375, 1440 | Own brief source line read `"Built from n Plus Alpha Ventures's saved setup. No runs used."`. | Awkward `'s` possessive on business names ending in `s`. | Fixed in `476fa8f` (`src/services/daily_brief.py`: renders `"n Plus Alpha Ventures' saved setup."`) |
| `/first-ad` | 375, 1440 | Step 1 `#faOutcomeInquiriesDesc` said `"sell via messages without online checkout"`; Step 2 `#faProductName` placeholder said `"featured product"`; Step 3 `#faAudience` placeholder said `"or local buyers"`; `importShopImages()` notices said `"shop or product URL"` / `"Loading shop images…"`. | Product/retail phrasing on a services business's first-ad guide. | Fixed in `476fa8f` (`first-ad.js`: reads `business_type` from the already-fetched `/api/v1/seller-memory` response — 0 new API calls — and tailors placeholders, inquiry description, and website-image notices for services; products & sample unchanged) |
| `/digest` | 375, 1440 | `<title>` read `"Weekly competitor digest for small shops \| Muse Growth Studio"` and `#digestDraftForm` topic checkbox read `"New and removed listings or pages"`. | Refers to `"small shops"` and `"listings"` for a services business. | Fixed in `476fa8f` (`digest.js`: sets `<title>` to `"Weekly competitor digest \| Muse Growth Studio"` and topic label to `"New and removed pages"` for services; restores original text for products/sample) |
| `/progress` | 375, 1440 | Free-plan account (`usage.plan == "free"`) showed `Plan Cost: $12/mo`, `"Starter monthly plan"`, and `Net Return: +$4488 (Revenue minus $12 plan cost)` on `$4500` logged revenue; `#pgRevenueSub` always said `"Logged on this device"` even when synced from `/api/v1/outcomes`; header/ROI rule said `"30-second sales result"` / `"seller-logged sales"`. | Invented a `$12/mo` plan cost on a free account (skewing Net Return by $12), misstated server-saved revenue as device-only, and assumed product sales. | Fixed in `476fa8f` (`src/api/outcomes.py`: `_get_account_plan_cost` returns `0.0` for `plan == "free"` and `29.0` for `"pro"`/`"unlimited"`; `progress.html`: updates `#pgPlanCost`, `#pgPlanCostSub`, and `#pgRevenueSub` from `serverSummary`, and uses neutral `"30-second result"` / `"Only results you log count toward ROI."`) |
| `/today` (`#msBrief`) | 375, 1440 | Under `YOUR LOGGED RESULTS`, outcomes display raw channel keys (`2026-11-20 · linkedin`, `2026-11-23 · shop_direct`) and `"1 orders"` / `"2 orders"`. | Exposes internal snake_case key `shop_direct`, lowercase `linkedin`, ungrammatical `"1 orders"`, and `"orders"` for a services business. | **For Claude** (`src/api/static/muse-shell.js`, Do Not Touch): map channel keys via a label map (`linkedin` → `LinkedIn`, `shop_direct` → `Website or direct`) and singularize/label orders vs bookings/clients (`1 booking` / `1 order`). |
| `/account` (dialog) | 375, 1440 | Account dialog primary button reads `"Edit shop setup"` (`account.js:467`) and invalid-email hint reads `"name@shop.com"` (`account.js:259`). | Says `"shop"` to a services business. | **For Claude** (`src/api/static/account.js` + `welcome.html`/`index.html` script version pins + `tests/test_setup_edit_and_offer_e2e.py:326` which asserts `"Edit shop setup"`): couldn't bump `account.js` without editing Do-Not-Touch `welcome.html` and `index.html`. Suggested fix: change to `"Edit business setup"` and `"name@example.com"`, bump `account.js` on all pages, and update `test_setup_edit_and_offer_e2e.py:326`. |
| `/account` (page) | 375, 1440 | `/account` renders `index.html` with `<title>Muse Growth Studio \| AI marketing help for makers and artists</title>`, does not auto-open the account dialog when already signed in, and shows `"Switch to Sample shop"`. | Browser tab title still says `"for makers and artists"` for a services business. | **For Claude** (`src/api/static/index.html` / `welcome.js`, Do Not Touch): update `document.title` in own services workspace (e.g., `"Muse Growth Studio \| Marketing workspace"`). |
| `/create`, `/today`, `/first-ad` | 375, 1440 | Destination dropdown includes `"Etsy shop or listing"` and `"Shopify store"` alongside `"My website"` and `"Booking or contact page"`. | Minor retail options in dropdown for a services business, though default is `"My website"`. | **Won't fix**: `tests/test_create_destinations_and_context_e2e.py` and `tests/test_today_destinations_e2e.py` explicitly assert `"Etsy shop or listing"` in the own-workspace destination list. |
| All 6 pages | 375 | Checked horizontal overflow (`scrollWidth <= innerWidth + 1`) across all pages, steps, and modals. | No sideways scroll, overlap, or unreadable text found at `375px`. | Verified clean in `tests/test_services_walkthrough_e2e.py`. |

## Script Version Bumps (`20261128-ag1`)

- `src/api/static/creator.js?v=20261128-ag1` — updated in `src/api/static/creator.html` and pinned in `tests/test_create_any_business.py`
- `src/api/static/today.js?v=20261128-ag1` — updated in `src/api/static/today.html`
- `src/api/static/first-ad.js?v=20261128-ag1` — updated in `src/api/static/first-ad.html` and pinned in `tests/test_ad_loop_links.py` and `tests/test_create_any_business.py`
- `src/api/static/digest.js?v=20261128-ag1` — updated in `src/api/static/digest.html` and pinned in `tests/test_own_competitor_checks.py`
- `AGENTS.md` version line left for Claude at merge.

## Mutation Checks (One Per Fix Category)

Each fix category was reverted against `HEAD~1`, tested with `DEMO_MODE=true META_MODEL_API_KEY= DEMO_KEY= .venv/bin/pytest -q tests/test_services_walkthrough_e2e.py`, confirmed to fail, and restored cleanly (`git diff --exit-code` = 0):

1. **`/today` services copy (`git checkout HEAD~1 -- src/api/static/today.js`):**
   - Result: **FAIL (`rc=1`)** — `FAILED tests/test_services_walkthrough_e2e.py::test_services_walkthrough_fits_any_services_business_e2e`
2. **`daily_brief.py` possessive (`git checkout HEAD~1 -- src/services/daily_brief.py`):**
   - Result: **FAIL (`rc=1`)** — `FAILED tests/test_services_walkthrough_e2e.py::test_services_walkthrough_fits_any_services_business_e2e`
3. **`/create` services goals & copy (`git checkout HEAD~1 -- src/api/static/creator.html src/api/static/creator.js`):**
   - Result: **FAIL (`rc=1`)** — `FAILED tests/test_services_walkthrough_e2e.py::test_services_walkthrough_fits_any_services_business_e2e`
4. **`/first-ad` services copy (`git checkout HEAD~1 -- src/api/static/first-ad.js`):**
   - Result: **FAIL (`rc=1`)** — `FAILED tests/test_services_walkthrough_e2e.py::test_services_walkthrough_fits_any_services_business_e2e`
5. **`/digest` services title & topic (`git checkout HEAD~1 -- src/api/static/digest.js`):**
   - Result: **FAIL (`rc=1`)** — `FAILED tests/test_services_walkthrough_e2e.py::test_services_walkthrough_fits_any_services_business_e2e`
6. **`/progress` free plan cost & copy (`git checkout HEAD~1 -- src/api/static/progress.html src/api/outcomes.py`):**
   - Result: **FAIL (`rc=1`)** — `FAILED tests/test_services_walkthrough_e2e.py::test_services_walkthrough_fits_any_services_business_e2e`

## Verification Gate Results

- **All 10 standalone Node contracts:** 10/10 passed (`account_ui_contract.cjs`, `creator_artist_feedback.cjs`, `creator_import_sprint.cjs`, `creator_journey_smoke.cjs`, `creator_studio_contract.cjs src/api/static/creator.js`, `editor_drafts_contract.cjs`, `muse_shell_resilience.cjs`, `shared_get_contract.cjs`, `today_studio_contract.cjs`, `ui_polish_contract.cjs`).
- **Full offline gate (`DEMO_MODE=true META_MODEL_API_KEY= DEMO_KEY= make PY=/Users/nav/meta-smb-gtm/.venv/bin check`):**
  - `ruff check .` → `All checks passed!`
  - `ruff format --check .` → `356 files already formatted`
  - `pytest` → **913 passed, 3 skipped, 0 failed** in 435.19s (including `tests/test_api_calls_per_page_e2e.py` and `tests/test_services_walkthrough_e2e.py`).
- **Launch account audit (`DEMO_MODE=true META_MODEL_API_KEY= DEMO_KEY= /usr/bin/python3 tests/launch_account_audit.py`):** **27 passed, 0 failed**.
- **Launch browser audit (`DEMO_MODE=true META_MODEL_API_KEY= DEMO_KEY= /usr/bin/python3 tests/launch_browser_audit.py`):** **20 passed, 0 failed**.

## Ownership

Ownership released. All Do-Not-Touch boundaries respected. Ready for Claude review and integration.
