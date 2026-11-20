# Gemini Checkpoint — Shop/Artist Image Suggestions

- **Worktree:** `/tmp/muse-shop-images`
- **Branch:** `shop-images` (branched from approved starting commit `7fab453`, `codex/batch1-integration`)
- **Frozen integration worktree:** `/tmp/muse-batch1-integration` was not modified.
- **Spec & Review:** [`docs/product/SHOP_IMAGE_SUGGESTIONS.md`](../product/SHOP_IMAGE_SUGGESTIONS.md), [`docs/launch/SHOP_IMAGES_REVIEW.md`](SHOP_IMAGES_REVIEW.md)
- **Status:** Bounded corrections completed; ready for Codex review (**ownership explicitly released**)

## Implemented Behavior & Bounded Fixes

1. **Bounded aggregate response & verified preview compression (`src/services/product_reference.py`)**
   - Added `MAX_PREVIEW_EDGE = 1200`, `MAX_CANDIDATE_PREVIEW_BYTES = 220_000`, and `MAX_SERIALIZED_RESPONSE_BYTES = 3_500_000` (keeping serialized JSON well below the 4.5 MB hosting limit while accounting for `image_data_url` duplication of candidate 0 and metadata).
   - Oversized candidate previews are safely resized/re-encoded to optimized JPEG previews while preserving original pixel dimensions (`width`, `height`, `is_low_res`) and `source_url` provenance.
   - Added a hard post-assembly serialized byte cap (`len(result.model_dump_json().encode("utf-8")) <= MAX_SERIALIZED_RESPONSE_BYTES`) trimming trailing candidates if necessary.
   - Added endpoint regression `test_endpoint_bounds_aggregate_serialized_response_for_six_near_cap_jpegs` in `tests/test_product_reference.py` verifying 6 realistic near-cap 750x750 JPEGs return `HTTP 200` well below 4.5 MB with original dimensions and provenance preserved.

2. **Strict full pixel decode & corrupt/truncated/excessive-dimension rejection (`src/services/product_reference.py`)**
   - Replaced `_inspect_image_dimensions` with `_decode_and_prepare_preview(data, mime)`, which enforces `MAX_IMAGE_PIXELS = 25_000_000`, invokes `img.load()` to decode full pixel data (rejecting corrupt/truncated PNG/JPEG/WebP bodies rather than accepting header-only or undecodable bytes), and rejects `<120px` assets before candidate creation.
   - Replaced the synthetic invalid PNG constant in `tests/test_product_reference.py` with a valid Pillow-generated 160x160 PNG fixture and added parameterized corrupt/truncated PNG/JPEG/WebP and excessive-dimension (30M-pixel) regressions confirming listing facts (`title`, `description`, `price_hint`) are preserved while rejected images never become candidates.

3. **Genuine same-page delayed-response race isolation (`tests/test_shop_image_suggestions_e2e.py`)**
   - Replaced abort-and-reload with genuine same-page account (`window.museAccount.refresh()`) and mode (`window.museModes.enterSampleMode(...)`) transitions while `/api/v1/product-reference` responses are held in-flight and then fulfilled (`route.fulfill`), covering both `/today` (375px) and `/create` (1280px). Verified candidates, chosen image, `imageMeta`, and product/ad copy remain strictly scoped to the active owner/mode.

## Modified & Added Files (Correction Pass)

- `src/services/product_reference.py`
- `tests/test_product_reference.py`
- `tests/test_shop_image_suggestions_e2e.py`
- `docs/launch/GEMINI_SHOP_IMAGES.md`

## Exact Observed Verification Results (Post-Final-Edit)

- `DEMO_MODE=true META_MODEL_API_KEY= DEMO_KEY= make check` → exit code `0`:
  - `.venv/bin/ruff check .`: `All checks passed!`
  - `.venv/bin/ruff format --check .`: `223 files already formatted`
  - `.venv/bin/pytest`: `553 passed, 2 skipped, 1 warning in 95.63s` (the 2 skips are pre-existing in `tests/test_billing.py` and `tests/test_digest_email.py`; the warning is `DecompressionBombWarning` intentionally triggered by `test_excessive_dimension_image_is_rejected_preserving_listing`; `tests/test_product_reference.py` passed `17/17` and `tests/test_shop_image_suggestions_e2e.py` passed `1/1`).

## Remaining Gaps / Notes

- All verification ran offline with mocked storefront HTML/images (`respx` / local test server) and mocked session cookies (0 live external crawls, 0 Muse API calls, 0 paid calls).
- Ownership of branch `shop-images` in `/tmp/muse-shop-images` is **released** for Codex review. No merge, push, or deploy was performed.
