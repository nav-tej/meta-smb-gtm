# Antigravity Products Walkthrough Report (Nov 28)

- **Brief:** `docs/launch/antigravity-products-walkthrough-nov28.md`
- **Branch:** `gemini/products-walkthrough-nov28`
- **Base:** `origin/claude/ux-gap-ad-loop-nov17` (`9a1065b`, merged `6f491f1`)
- **Worktree:** `/Users/nav/muse-worktrees/products-walkthrough`
- **Fixture walked:** `"Ember & Wick Candle Co."` (`business_type: "products"`, Etsy + Shopify shop URLs, goal `"More sales"`, channels Instagram + Facebook, 30 min/wk, tone `polished_premium`, plan `trial`, 2 candle competitors with 1 saved analysis on Hearth & Wax, 1 saved `/create` account draft for `"Smoked Cedar 8oz Soy Candle"`, 1 logged outcome with `$240` revenue)
- **Viewports checked:** `375px` and `1440px` across `/today`, `/create` (steps 1–4 + saved draft load), `/first-ad` (steps 1–4), `/digest`, `/progress`, and `/account` (plus `?workspace=sample` regression checks on `/today`, `/create`, and `/first-ad`).

---

## Findings Table

### Fixed in Antigravity's files

| Page | Width | What happens | Why it's wrong | Status |
| --- | --- | --- | --- | --- |
| `/create` (Step 3) | 375 & 1440 | `#generateButton` read `"Preview a room scene"` and `#scene` defaulted to `"Warm neutral room, simple light oak console, soft daylight, clean wall and a restrained frame..."` for a candle shop (`products`). | Wall-art framing and room-scene language assumes a framed painting or print, not a tabletop product like a soy candle. | **Fixed** (`src/api/static/creator.js`: `#generateButton` reads `"Preview a product scene"` and `#scene` defaults to `"Clean, softly lit surface with natural daylight and simple modern styling. Describe only the surroundings; do not change the product."` for signed-in `products`/`both` accounts; sample artist keeps `"Preview a room scene"` and `"restrained frame"` verbatim) |
| `/create` (Step 4) | 375 & 1440 | `#exportFilesNote` read `"Downloads use your current edits. Images are social previews, not production print files. Nothing is posted automatically."` for a candle shop (`products`). | `"not production print files"` assumes the seller sells fine-art prints. | **Fixed** (`src/api/static/creator.js`: own workspaces show `"Downloads use your current edits. Nothing is posted automatically."`; sample artist keeps the print-files line) |
| `/create` (Step 1 & 4) | 375 & 1440 | `#moreDetails > summary` listed `"series"`, `label[for="productCollection"]` read `"Series or collection (optional)"`, placeholder read `"Leave blank, or add your series"`, `#saveWebsiteOnlyBtn` read `"Save website to my studio"`, `savedShopWebsiteNote` said `"Saved studio website"`, and Step 4 `#postingSteps` said `"A series label here does not change your shop collections."` | `"series"` and `"my studio"` assume a fine-art studio rather than an everyday online shop. | **Fixed** (`src/api/static/creator.js`: own workspaces use `"collection"`, `"Collection (optional)"`, `"Leave blank, or add a collection"`, `"Save website to my shop"`, `"Saved shop website"`, and `"A collection label here..."`; sample artist keeps `"Series"` and `"my studio"`) |
| `/create` (Step 1 image picker) | 375 & 1440 | Image picker status and low-res warnings in own workspaces said `"Checking this page for product & artwork images…"`, `"artwork/product link"`, and `"not a print master"`. | `"artwork"` and `"print master"` assume visual art / fine-art prints. | **Fixed** (`src/api/static/creator.js`: own workspaces use `"Checking this page for product images…"`, `"product or page link"`, and `"best for social posts."`; sample artist keeps original strings) |
| `/today` (`#setup` modal) | 375 & 1440 | Opening `"Change item or goal"` showed label `"Series (optional)"` with `<datalist id="series">` options `"Featured Collection"` and `"Abstracts"`. | `"Series"` and `"Abstracts"` are painting/art-collection concepts that make no sense for a candle shop. | **Fixed** (`src/api/static/today.html`, `src/api/static/today.js`: own workspaces swap `#collectionLabel` to `"Collection (optional)"` and clear `#series` datalist options; sample artist keeps `"Series (optional)"` and `"Abstracts"`) |
| `/today` (image picker & live scene notice) | 375 & 1440 | Image picker status/low-res warnings and live scene notice in own workspaces said `"product & artwork images"`, `"not for printing"`, and `"Compare the artwork with your original"`. | Art/print wording leaks into a non-artist product shop. | **Fixed** (`src/api/static/today.js`: own workspaces use `"Checking this page for product images…"`, `"best for social posts."`, and `"Compare the image with your original"`; sample artist unchanged) |
| `/first-ad` (Steps 1–3) | 375 & 1440 | For `business_type: "products"`, Step 1 outcomes said `"Bring visitors to your website"`, `"book a call"`, and `"book calls"`; Step 2 `#faProductName` placeholder said `"e.g., AI growth audit, consultation, or featured product"` and `#faCta` said `"Book a call"`; Step 3 `#faAudience` placeholder said `"e.g., Small business owners looking for marketing help or local buyers"`. | Consulting/agency examples confuse a candle seller trying to run a first product ad in five seconds. | **Fixed** (`src/api/static/first-ad.js`: added `prod = !sample && ownBusinessType === 'products'` branch with shop-friendly copy: `"Bring visitors to your shop"`, `"Etsy, Shopify, or website product pages"`, `"custom orders or sell via messages"`, `"e.g., Soy candle gift set, bestselling mug, or featured product"`, `"e.g., Shop now, Send message, Learn more"`, `"e.g., People looking for handmade gifts, home goods, or seasonal favorites"`; sample artist and services unchanged) |
| `/digest`, `/progress`, `/account` | 375 & 1440 | Checked all three pages for Ember & Wick Candle Co. at 375px and 1440px. | Zero sideways overflow, zero page errors, zero art/marketplace leaks in allowed files. `/digest` showed both candle competitors with `"From your analysis"` on Hearth & Wax; `/progress` showed `trial` plan as `$0/mo` (`Free account`), `1` move, `$240` logged revenue, `+$240` net return. | **Clean** (no edits needed in `digest.js` or `progress.html`) |

### Reported for Claude (Do-Not-Touch files — not modified)

| Page | Width | File & lines | What happens | Why it's wrong | Status |
| --- | --- | --- | --- | --- | --- |
| `/today` (`#msBrief` TOP 3 ACTIONS) | 375 & 1440 | `src/services/seller_memory.py` (`L1630`, `L1713`, `L1727`, `L1942`) | Move #3 for `"Ember & Wick Candle Co."` (`products`) says `"3. Share your studio story behind Ember & Wick Candle Co. featured work"` with CTA `"Read studio story"` and rationale `"Matches your studio storytelling focus"`. | `"studio story"` and `"featured work"` assume an artist's studio rather than a product shop (e.g., `"Share the story behind your bestseller at <business>"` / `"featured product"`). | **Reported for Claude** |
| `/account` (and `/` shell) | 375 & 1440 | `src/api/static/index.html` (`L6`, `L12`, `L19`) | `<title>` (and `og:title` / `twitter:title`) reads `"Muse Growth Studio \| AI marketing help for makers and artists"`. | `"makers and artists"` narrows the browser tab/meta title when signed in as a general products or services business. | **Reported for Claude** |

---

## Script Versions & Pins

- **Bumped to `20261128-ag2`:**
  - `src/api/static/creator.html` → `/static/creator.js?v=20261128-ag2`
  - `src/api/static/today.html` → `/static/today.js?v=20261128-ag2`
  - `src/api/static/first-ad.html` → `/static/first-ad.js?v=20261128-ag2`
- **Unchanged (no edits needed):**
  - `src/api/static/digest.html` → `/static/digest.js?v=20261128-ag1`
- **Updated test pins:**
  - `tests/test_create_any_business.py` (`creator.js?v=20261128-ag2`, `first-ad.js?v=20261128-ag2`)
  - `tests/test_ad_loop_links.py` (`first-ad.js?v=20261128-ag2`)
  - `tests/test_services_walkthrough_e2e.py` (updated `Wild Meadow Goods` products check on `#generateButton` to `"Preview a product scene"`; sample artist check remains `"Preview a room scene"`)
- **New E2E test:**
  - `tests/test_products_walkthrough_e2e.py` (walks `"Ember & Wick Candle Co."` at 375px & 1440px across `/today`, `/create`, `/first-ad`, `/digest`, `/progress`, `/account` + verifies `?workspace=sample` keeps every original sample artist string)

---

## Mutation Checks (1 per fix category)

All four mutations were run against `tests/test_products_walkthrough_e2e.py`, confirmed to fail (`exit 1`), and cleanly restored (`git diff --exit-code` = 0):

1. **Category 1 — `/create` Step 3 scene prompt & button (`src/api/static/creator.js`):**
   - Command: revert `previewSceneButtonLabel` non-services branch to `'Preview a room scene'`, then run `DEMO_MODE=true META_MODEL_API_KEY= DEMO_KEY= /Users/nav/meta-smb-gtm/.venv/bin/pytest -q tests/test_products_walkthrough_e2e.py -k non_artist`
   - Result: **FAILED as expected (`MUT1_EXIT=1`)** — assertion on `#generateButton` (`"Preview a product scene"`) caught `"Preview a room scene"`. Restored with `git checkout -- src/api/static/creator.js`.
2. **Category 2 — `/create` Step 1 & 4 print/series/studio copy (`src/api/static/creator.js`):**
   - Command: revert `#exportFilesNote` condition from `isOwn` back to `svc`, then run `DEMO_MODE=true META_MODEL_API_KEY= DEMO_KEY= /Users/nav/meta-smb-gtm/.venv/bin/pytest -q tests/test_products_walkthrough_e2e.py -k non_artist`
   - Result: **FAILED as expected (`MUT2_EXIT=1`)** — `AssertionError: Downloads use your current edits. Images are social previews, not production print files. Nothing is posted automatically.` Restored with `git checkout -- src/api/static/creator.js`.
3. **Category 3 — `/today` `#setup` modal `Series (optional)` / `Abstracts` (`src/api/static/today.js`):**
   - Command: comment out `swap($('collectionLabel'), 'Collection (optional)');`, then run `DEMO_MODE=true META_MODEL_API_KEY= DEMO_KEY= /Users/nav/meta-smb-gtm/.venv/bin/pytest -q tests/test_products_walkthrough_e2e.py -k non_artist`
   - Result: **FAILED as expected (`MUT3_EXIT=1`)** — `AssertionError: Series (optional)`. Restored with `git checkout -- src/api/static/today.js`.
4. **Category 4 — `/first-ad` products placeholders & outcomes (`src/api/static/first-ad.js`):**
   - Command: set `const prod = false;` in `syncFirstAdCopy`, then run `DEMO_MODE=true META_MODEL_API_KEY= DEMO_KEY= /Users/nav/meta-smb-gtm/.venv/bin/pytest -q tests/test_products_walkthrough_e2e.py -k non_artist`
   - Result: **FAILED as expected (`MUT4_EXIT=1`)** — assertion on `#faOutcomeVisitsTitle` (`"Bring visitors to your shop"`) failed. Restored with `git checkout -- src/api/static/first-ad.js`.

---

## Gate, Audits & Node Contracts

- **Full offline gate** (`DEMO_MODE=true META_MODEL_API_KEY= DEMO_KEY= make PY=/Users/nav/meta-smb-gtm/.venv/bin check`):
  - `ruff check .` — **All checks passed**
  - `ruff format --check .` — **362 files already formatted**
  - `pytest` — **973 passed, 3 skipped, 0 failed**
- **Launch audits (offline, system Python `/usr/bin/python3`):**
  - `tests/launch_account_audit.py` — **27 passed, 0 failed**
  - `tests/launch_browser_audit.py` — **20 passed, 0 failed**
- **Node contracts (10/10 passed):**
  - `node tests/account_ui_contract.cjs` — PASS
  - `node tests/creator_artist_feedback.cjs` — PASS
  - `node tests/creator_import_sprint.cjs` — PASS (5/5)
  - `node tests/creator_journey_smoke.cjs` — PASS (7/7)
  - `node tests/creator_studio_contract.cjs src/api/static/creator.js` — PASS
  - `node tests/editor_drafts_contract.cjs` — PASS
  - `node tests/muse_shell_resilience.cjs` — PASS
  - `node tests/shared_get_contract.cjs` — PASS
  - `node tests/today_studio_contract.cjs` — PASS
  - `node tests/ui_polish_contract.cjs` — PASS

---

## Ownership released

All work on `gemini/products-walkthrough-nov28` is committed, verified, and pushed. Zero Do-Not-Touch files were modified, no deploys or live Muse calls were made, and ownership of all touched files is released back to Claude.
