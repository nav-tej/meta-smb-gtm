# PRD, Signed-In Onboarding, Insight-to-Ad Previews, and Digest Habit Progress (Antigravity Session 1)

**Branch:** `prd-research-previews`
**Owner:** Antigravity Session 1 (front end)
**Priority Order (Revision 3):** Track A → Track H → Track B → Track G
**Rules:** `DEMO_MODE=true`, zero paid model calls, no deploy, no push, no migrations applied, no secret changes.

---

## Current State Snapshot (2026-11-09 23:41 PT)

### 1. What is DONE (Committed on `prd-research-previews`)
- **Step 1 (`b79a035`):** Verified `make check` (`ruff check .`, `ruff format --check .`, `pytest` — `423 passed, 2 skipped`) and committed Claude's `reco-actions` change (`src/api/static/reco-actions.js`, `src/api/static/reco-actions.css`, `src/api/static/index.html`, `tests/test_account_ui.py`).
- **Track A (`fe2c827`):**
  - Wrote complete `docs/product/PRD.md` covering all 8 required sections + Tracks B–H (including Revision 2 and Revision 3 signed-in onboarding), with every claim/number labeled `[live]`, `[sample]`, or `[estimate]`, plus the Appendix 1 homepage truth table verified in Chromium.
  - Applied the 4 copy accuracy fixes in `src/api/static/index.html` (reconciled `4 competitors (6 catalog & shop pages tracked)`, reconciled `$14–$22` POD vs `$75–$900` direct signed vs `$60–$2,500` SikhiArt range, clarified `Add · 🪙 1 run (live) / 0 in demo`, marked exhibition & 550th anniversary claims as needing artist verification before publishing, and labeled the demo workspace as `Sample shop`).
- **Track H (Committed Next):**
  - Mounted `GET /welcome` in `src/api/main.py`.
  - Created `src/api/static/welcome.css`, `src/api/static/welcome.html`, and `src/api/static/welcome.js` implementing the 4-step skippable, resumable onboarding flow:
    - Step 1: Your shop (bare domain + business name + crawl proof).
    - Step 2: Your socials (auto-discovered chips + manual addition).
    - Step 3: Your competitors (free, 0 runs, suggestions from research or manual input).
    - Step 4: How you work (experience + focus + upfront 1-run disclosure on "Build my workspace", 0-run fallback when 0 runs left).
    - Step 5: Explainer completion screen detailing what Muse read, what it found, what a run is, runs left, what is cached, and Monday digest offer.
  - Privacy-safe PostHog analytics (`onboarding_started`, `onboarding_step_completed`, `onboarding_skipped`, `onboarding_run_confirmed`, `onboarding_completed`, `onboarding_explainer_viewed`) with zero URLs or social handles leaked.
  - Honest signed-in workspace rendering on `/` with zero Sarabjit sample data on real accounts unless `?workspace=sample` is explicitly selected.
  - Added `tests/test_welcome_onboarding.py` testing the full flow and contract at `375px` and `1440px` with zero model calls and fixture APIs. All 426 tests in `make check` passing.

### 2. Next Up: Track B (Insight-to-Ad Previews)
- Add `PreviewSpec` & `PreviewEvidence` models in `src/models/creative.py`.
- Add `data/demo/previews.json` fixture mapping each ranked idea to a 1:1 preview.
- Upgrade `src/api/static/reco-actions.js` and `reco-actions.css` for 1:1 preview rendering, placement switching (IG 4:5, Story 9:16, FB), copy-ready checklists for non-post ideas, compare view, and PNG export.
- Add `tests/test_insight_previews.py`.
