# Gemini / Antigravity Status (`2026-11-03`)

## Assignment (`P0 offline route/CSV coverage and blockers`)
- Completed in `tests/test_demo_mode.py` without touching portal, `README.md`, services, or `AGENTS.md`.
- Added 5 new offline test functions/cases (bringing the suite from `95 passed` to **`100 passed in 1.95s`**, `ruff check .` & `ruff format --check .` clean):
  1. `test_demo_mode_guarded_seller_audit_screenshot_and_csv_routes`:
     - Verifies `POST /api/v1/audit-seller` falls back to free deterministic `SellerDiagnostics` (`7` platforms, `72` artworks) in `DEMO_MODE=true` without calling Muse Spark.
     - Verifies `POST /api/v1/audit-screenshot` returns HTTP `403` (`"Screenshot analysis has no saved demo result"`) in `DEMO_MODE=true`.
     - Verifies `POST /api/v1/bid-advice/csv` validates the CSV first and serves the cached `demo_bid_recommendation()` in `DEMO_MODE=true` (`0` service calls), and returns computed `PerformanceMetrics` when `deterministic_only=True`.
  2. `test_csv_validation_edge_cases_return_422_in_demo_mode` (parametrized across 3 edge cases):
     - Missing required columns / zero valid rows (`wrong_col_a,wrong_col_b`).
     - Invalid ISO date (`not-a-date`).
     - Non-numeric impressions (`not-a-number`).
  3. `test_public_portal_and_all_sample_assets_resolve`:
     - Verifies `GET /`, `GET /portal`, and all 9+ `/samples/*` image assets referenced by `DEMO_IMAGES` and both workspaces (`sarabjit_singh` and `etsy_ceramics`) in `GET /api/v1/demo-presets` return HTTP `200` with `> 1000` bytes.

## Blockers / Notes for Codex & Claude
- No bugs found in `src/api/demo.py` or `src/services/demo.py`—CSV validation runs before the demo-cache short-circuit in `src/api/bids.py`, so malformed CSV uploads properly return `422` in both demo and live modes.
- Zero paid Muse API calls were made.
