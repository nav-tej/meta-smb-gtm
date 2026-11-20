# Antigravity Report: Weekly Time-Budget Ranking for Suggested Moves

- **Date:** November 20, 2026
- **Branch:** `gemini/time-budget-nov20`
- **Base commit:** `f35431e` (`origin/claude/ux-gap-ad-loop-nov17`)
- **Worktree:** `/tmp/muse-time-budget` (isolated; Mac checkout untouched)

## Files Changed (within exclusive write scope)
- `src/services/seller_memory.py` (time-budget check and all-over-budget sort in `rank_seller_recommendations`)
- `tests/test_time_budget_ranking.py` (new unit tests; `tests/test_seller_memory.py` unchanged)
- `docs/launch/ANTIGRAVITY_TIME_BUDGET_NOV20.md` (this report)

## Summary of Changes
1. **Universal weekly time-budget enforcement (`src/services/seller_memory.py`):**
   - Replaced the `effective_minutes <= 15`-only guard in `rank_seller_recommendations()` so every weekly budget compares `estimated_minutes` against `effective_minutes`.
   - For budgets `<= 15`, kept the exact existing `+24.0` bonus (when `estimated_minutes <= effective_minutes`) and `-75.0` penalty (when `estimated_minutes > effective_minutes`) so budget-15 rankings and scores match the pre-change baseline identically.
   - For budgets `> 15`, moves with `estimated_minutes > effective_minutes` now receive a `-500.0` penalty (larger than the maximum possible score gap between any over-budget move and any fitting move, even after `already_tried` or fixed-price penalties), ensuring any fitting move always ranks above an over-budget move.
   - Updated seller-facing time reasons to plain English with `"minutes"` (not `"min"`) and zero em-dashes:
     - Over budget: `"Takes about N minutes, more than your M minutes this week"`
     - Fitting (`<= 15` budget): `"Fits your M minutes this week"`
2. **All-over-budget fallback (`src/services/seller_memory.py`):**
   - When every candidate move exceeds `effective_minutes` (for example, a 5-minute budget when the shortest move is 10 minutes), `rank_seller_recommendations()` still returns all moves (never an empty list), each carrying the over-budget reason, sorted shortest first (`(estimated_minutes, -score)`).
   - No new moves were invented and no move's `estimated_minutes` was changed.

## What `/today` and the Digest Do With Over-Budget Moves (Read-Only Audit)
- **`/today` and home (`src/api/static/seller-memory.js`, `src/api/static/today.js`, untouched):**
  - `seller-memory.js` renders `Why this fits: ${rec.why_this_fits || ''}` on home cards (lines 1967, 2036) and passes `why_this_fits` into the `/today` handoff (`today.js` line 466). Because `rank_seller_recommendations()` always returns a non-empty list, neither home nor `/today` breaks when every move is over budget.
  - Minor copy note for future UI work: when every move is over budget, the home card prefix `"Why this fits: "` will precede `"Takes about N minutes, more than your M minutes this week"`, which is accurate and safe but reads slightly oddly next to `"Why this fits:"`.
- **Weekly digest preview (`src/services/digest_preview.py`, lines 553–575, untouched):**
  - Picks `top = items[0]`, reads `id`, `title`, and `reason` (note: `rank_seller_recommendations()` returns `why_this_fits`, not `reason`, so `recommendation["reason"]` is already `""`), and sets `fit_note = f"Sized for ~{minutes} min/week"`.
  - Because `items` is non-empty, the digest does not break; however, if every move exceeds `minutes` (e.g., `minutes = 5` while the shortest move is 10 minutes), the digest still displays `"Sized for ~5 min/week"` without checking `top["estimated_minutes"]` or surfacing `top["why_this_fits"]`.

## Verification

### Full Offline Gate (Before and After)
Command:
```bash
DEMO_MODE=true META_MODEL_API_KEY= DEMO_KEY= make PY=/Users/nav/meta-smb-gtm/.venv/bin check
```
- **Before edits (`f35431e`):**
  - `ruff check .`: All checks passed!
  - `ruff format --check .`: `283 files already formatted`
  - `pytest`: **662 passed, 2 skipped, 1 failed, 1 warning in 191.20s (0:03:11)** (1 unrelated Playwright flake in `tests/test_competitor_signup_loop_e2e.py::test_signup_loop_and_real_suggestions_e2e`, which passed on subsequent runs).
- **After edits (final clean run):**
  - `ruff check .`: All checks passed!
  - `ruff format --check .`: `284 files already formatted`
  - `pytest`: **676 passed, 2 skipped, 1 warning in 193.95s (0:03:13)** (note: first after-edit run hit 1 unrelated Playwright 30s timeout in `tests/test_competitor_research_any_business.py`; immediate re-run passed all 676 tests with 0 failures).
  - `tests/test_time_budget_ranking.py`: **13 passed** covering budget 30 (`products`, `services`, `both`), budget 60 (`products`, `services`, `both`), budget 15 exact score/order regression guard (`None`, `products`, `services`, `both`), and budget 5 all-over-budget shortest-first ordering (`products`, `services`, `both`).
  - `tests/test_seller_memory.py`: **7 passed** unchanged.

### Mutation Check
Temporarily restored the `if effective_minutes <= 15:` guard around the time-budget check in `src/services/seller_memory.py` and ran `pytest tests/test_time_budget_ranking.py -q`. Confirmed immediate failure across all three budget-30 tests (`3 failed, 10 passed in 0.15s`):
```text
FAILED tests/test_time_budget_ranking.py::test_budget_30_demotes_40_minute_moves_even_when_shorter_moves_tried[products] - assert 40 <= 30
FAILED tests/test_time_budget_ranking.py::test_budget_30_demotes_40_minute_moves_even_when_shorter_moves_tried[services] - assert 40 <= 30
FAILED tests/test_time_budget_ranking.py::test_budget_30_demotes_40_minute_moves_even_when_shorter_moves_tried[both] - assert 40 <= 30
```
Reverted the mutation before running the final after-edit gate.

## What Was Not Verified
- Live paid Muse API calls, hosted Vercel preview deployments, or Postgres migrations (out of scope; zero paid calls or deploys made).
- UI changes in `seller-memory.js`, `today.js`, or `digest_preview.py` (outside exclusive write scope).

Ownership released.
