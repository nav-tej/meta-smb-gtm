# Antigravity Report: `/create` Destinations and Muse Context for Any Business

- **Date:** November 19, 2026
- **Branch:** `gemini/create-destinations-nov19`
- **Base commit:** `9b103ef` (`origin/claude/ux-gap-ad-loop-nov17`)
- **Worktree:** `/tmp/muse-create-destinations` (isolated; Mac checkout untouched)
- **Script version bump:** `creator.js?v=20261119-ag3` in `src/api/static/creator.html` (pinned in `tests/test_create_any_business.py`; Claude can update `AGENTS.md`)

## Files Changed (within exclusive write scope)
- `src/api/static/creator.js`
- `src/api/static/creator.html`
- `tests/test_create_any_business.py`
- `tests/test_create_destinations_and_context_e2e.py` (new)
- `docs/launch/ANTIGRAVITY_CREATE_DESTINATIONS_NOV19.md` (this report)

## Summary of Changes
1. **Muse payload and research context (`src/api/static/creator.js`):**
   - `productPayload()`, `researchContext()`, `promotionResearchContext()`, and `generate()` now carry the sample artist rules (`"For this artist, Etsy is closed..."`, artwork/print notes, and sample competitor brief) **only** when `!state.custom && state.workspace === 'sarabjit_singh'`.
   - In a seller's own workspace, `productPayload()` builds factual `brand_notes` from the seller's own inputs: business name (`state.product.seller` / `onboarding.business_name`), what they offer (`onboarding.business_type` from `/api/v1/account/workspace`: `Services`, `Products`, or `Products and services`, omitted if unset), goal, chosen destination label, optional series, and generic safety rules (only supplied facts; no invented scarcity, materials, reviews, prices or results).
   - `researchContext()` never pulls `state.presets` for own workspaces and populates `seller_context` from the seller's own business details only.
2. **Own-workspace destinations vs. sample destinations (`src/api/static/creator.js`, `src/api/static/creator.html`):**
   - Own workspace offers `website` (`My website`), `booking` (`Booking or contact page`), `etsy` (`Etsy shop or listing`), `shopify` (`Shopify store`), and `other` (`Other link`).
   - Sample shop keeps the exact existing list (`Pixels`, `Fine Art America`, `Saatchi Art`, `Artist website`, `My shop / inquiry page`) and destination notes.
   - `applyDocument()` normalizes legacy own-workspace drafts whose destination was `pixels`, `fineartamerica`, or `saatchi` to `other` (`Other link`) while preserving the saved link and price.
   - Static `<option>`s in `src/api/static/creator.html` now default to the own-workspace list; `syncDestinationOptions()` switches them when entering sample mode.
3. **Neutral and business-type-aware wording (`src/api/static/creator.js`, `src/api/static/creator.html`):**
   - Replaced `"Your product photo will appear here."` and `"Add a photo to create your own product layout."` with neutral wording (`"Your photo will appear here."`, `"Add a photo to create your own layout."`).
   - Made `switchDestination()`, `destinationNote()`, `postingChecklist()` (and exported `.txt`/`.json` packs), step 1 nav/intro/import hint, review checkbox text, goal cards, validation messages, and `#postingPlanNote` adapt to `onboarding.business_type === 'services'` (`"service or offer"` wording) while keeping `"product"` wording for `products`/`both` and preserving sample artist wording in the sample shop.
   - Removed em-dashes (`—`) from customer-facing error/warning strings in `creator.js`.
   - Skipped automatic storefront listing scan (`autoImportSavedShop`) for `services` workspaces while preserving the existing `test_first_visit_import_e2e.py` contract.

## Verification

### Full Offline Gate (Before and After)
Command:
```bash
DEMO_MODE=true META_MODEL_API_KEY= DEMO_KEY= make PY=/Users/nav/meta-smb-gtm/.venv/bin check
```
- **Before edits (`9b103ef`):**
  - `ruff check .`: All checks passed!
  - `ruff format --check .`: `275 files already formatted`
  - `pytest`: **651 passed, 2 skipped, 1 warning in 189.71s (0:03:09)**
- **After edits:**
  - `ruff check .`: All checks passed!
  - `ruff format --check .`: `276 files already formatted`
  - `pytest`: **652 passed, 2 skipped, 1 warning in 190.16s (0:03:10)**

### Browser Checks (`tests/test_create_destinations_and_context_e2e.py` & `tests/test_create_any_business.py`)
Verified in headless Chromium at **375×844** and **1440×844** with zero horizontal overflow and zero paid Muse calls (all `/api/v1/generate-ads` requests route-mocked):
- **Services own workspace (`n Plus Alpha Consulting`, `business_type: "services"`):**
  - Destination `<select>` shows only own-workspace options (`My website`, `Booking or contact page`, `Etsy shop or listing`, `Shopify store`, `Other link`); none of `Pixels`, `Fine Art America`, `Saatchi Art`, or `Artist website`.
  - Switching to `booking` shows services-aware notice without `"artwork"`.
  - Captured live `POST /api/v1/generate-ads?live=true` `brand_notes` includes `n Plus Alpha Consulting`, `Services`, and `Booking or contact page`, and contains none of `Etsy is closed`, `artist`, or `artwork`.
  - Step 4 posting checklist contains neither `"artwork"` nor `"product"`, and `<main>` contains zero em-dashes.
- **Products own workspace (`Cedar & Loom Goods`, `business_type: "products"`):**
  - Own-workspace destinations verified; switching to `etsy` shows product-aware notice without `"artwork"`.
  - Captured live `POST /api/v1/generate-ads?live=true` `brand_notes` includes `Cedar & Loom Goods`, `Products`, and `Etsy shop or listing`, with none of `Etsy is closed`, `artist`, or `artwork`.
- **Sample shop regression (`/create?workspace=sample`):**
  - Preserves artist destination list (`Pixels`, `Fine Art America`, `Saatchi Art`, `Artist website`, `My shop / inquiry page`).
  - Captured live `POST /api/v1/generate-ads?live=true` still sends `"For this artist, Etsy is closed."` and artwork context.
- **Legacy draft compatibility:**
  - Seeded an own-workspace schema-1 draft with `destination: "pixels"`, `link: "https://nplusalpha.test/legacy-offer"`, and `price: "$250"`. Loaded `/create` with zero page errors; `#promotionDestination` fell back to `other` (`Other link`) with `#productLink` and `#productPrice` preserved.

### Mutation Check
Temporarily re-inserted `"For this artist, Etsy is closed."` into the own-workspace `productPayload()` branch in `src/api/static/creator.js` and ran `pytest tests/test_create_destinations_and_context_e2e.py -q`. Confirmed immediate failure (`1 failed in 1.38s`):
```text
AssertionError: ('Etsy is closed', 'Business: n Plus Alpha Consulting. Offers: Services. Goal: Share what you do. Destination: Booking or contact page. Only use supplied facts. Never invent scarcity, materials, reviews, prices or results. For this artist, Etsy is closed. Do not state a price unless it is supplied for the selected destination.')
```
Reverted the mutation before running the final after-edit gate.

## What Was Not Verified
- Live paid Muse API generation against `api.meta.ai` (route-mocked per boundaries; zero paid calls made).
- Hosted Vercel preview deployment or Supabase Postgres persistence (no deploy, migration, or `.env` access).

Ownership released.
