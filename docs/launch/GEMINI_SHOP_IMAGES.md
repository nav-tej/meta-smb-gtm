# Gemini Checkpoint — Shop/Artist Image Suggestions

- **Worktree:** `/tmp/muse-shop-images`
- **Branch:** `shop-images` (branched from approved starting commit `7fab453`, `codex/batch1-integration`)
- **Frozen integration worktree:** `/tmp/muse-batch1-integration` was not modified.
- **Spec:** [`docs/product/SHOP_IMAGE_SUGGESTIONS.md`](../product/SHOP_IMAGE_SUGGESTIONS.md)
- **Status:** Ready for Codex review (**ownership explicitly released**)

## Implemented Behavior

1. **Bounded website image candidate discovery (`src/services/product_reference.py`)**
   - Extended `ProductReference` with `ProductImageCandidate`, `image_candidates`, `image_width`, `image_height`, and `is_low_res`.
   - Upgraded `_PreviewImageParser` to extract up to 6 unique candidates per page, preferring JSON-LD (`Product` / `VisualArtwork`) and OpenGraph/Twitter image metadata before `<img>` tags, while filtering icons, logos, tracking pixels, SVGs, GIFs, and duplicates.
   - Added Pillow dimension extraction with `MAX_IMAGE_PIXELS = 25_000_000` bomb guard, `<120px` small-asset filtering, and low-resolution flagging (`<600px` min edge or `<800px` max edge), preserving existing SSRF/robots protections and synthetic byte compatibility.

2. **Creator (`/create`) & Today (`/today`) `"Choose an image"` picker + non-destructive framing**
   - Added `"Choose an image"` (`#imagePicker` / `#todayImagePicker`) with three explicit sources (`From your website`, `Sample artwork` strictly gated to explicit sample mode, and `Upload a photo`) in `creator.html` / `today.html` and responsive layout styles in `muse-shell.css`.
   - **Sample mode isolation:** Curated checked-in originals (`/samples/ek_onkar_original.jpg`, `/samples/naam_japo_original.jpg`, `/samples/kirat_karo_original.jpg`) are grouped separately from saved generated ad examples (`*_live.webp`), with zero crawl or Muse API calls.
   - **Own mode & explicit selection:** Lazily fetches bounded candidates via `POST /api/v1/product-reference` with `AbortController` + epoch/mode guards, displays thumbnail, title, safe `Source page ↗` link, pixel dimensions, low-resolution warnings, and explicit `"Use this image"` selection.
   - **Draft preservation & fallback:** Preserves prior photo, `imageMeta`, `imageFrame`, and edited copy across repeated scans, reloads, and blocked/empty page responses (`"We couldn’t retrieve an image from this page. Try an artwork/product link or upload a photo."`).
   - **Non-destructive framing & export:** Added `Fit/Fill` crop toggle, Horizontal/Vertical framing sliders, and reset (`#creatorFrameControls` / `#todayFrameControls`) rendered non-destructively onto Feed (`1080x1350`), Story (`1080x1920`), and Square (`1080x1080`) PNG canvas exports.

## Modified & Added Files

- Modified:
  - `src/services/product_reference.py`
  - `src/api/static/muse-shell.css`
  - `src/api/static/creator.html`
  - `src/api/static/creator.js`
  - `src/api/static/today.html`
  - `src/api/static/today.js`
  - `tests/test_product_reference.py`
- Added:
  - `tests/test_shop_image_suggestions_e2e.py`
  - `docs/launch/GEMINI_SHOP_IMAGES.md`

## Exact Observed Verification Results (Post-Final-Edit)

- `node --check src/api/static/creator.js && node --check src/api/static/today.js` → exit code `0`
- `DEMO_MODE=true META_MODEL_API_KEY= DEMO_KEY= make check` → exit code `0`:
  - `.venv/bin/ruff check .`: `All checks passed!`
  - `.venv/bin/ruff format --check .`: `222 files already formatted`
  - `.venv/bin/pytest`: `547 passed, 2 skipped in 88.00s (0:01:28)` (the 2 skips are pre-existing in `tests/test_billing.py` and `tests/test_digest_email.py`; `tests/test_product_reference.py` had 11 passed and `tests/test_shop_image_suggestions_e2e.py` had 1 passed at 375px and 1440px in real Chromium).

## Remaining Gaps / Notes

- E2E browser and unit candidate tests ran completely offline with mocked storefront HTML/images (`collect_entries` / `respx`) and mocked account cookies, and asserted `0` Muse API calls / `0` paid calls; live external storefront crawling against third-party sites was not run.
- Ownership of branch `shop-images` in `/tmp/muse-shop-images` is **released** for Codex review. No merge, push, or deploy was performed.
