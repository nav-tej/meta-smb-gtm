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
- **Track H (`cce4f62`):**
  - Mounted `GET /welcome` in `src/api/main.py`.
  - Created `src/api/static/welcome.css`, `src/api/static/welcome.html`, and `src/api/static/welcome.js` implementing the 4-step skippable, resumable onboarding flow with 1-run charged on completion and completion explainer.
  - Added `tests/test_welcome_onboarding.py` testing the full flow and contract at `375px` and `1440px` with zero model calls and fixture APIs.
- **Track B (Insight-to-Ad Previews — Committed Next):**
  - Added `PreviewSpec`, `PreviewEvidence`, and `CompetitorAdCard` to `src/models/creative.py`.
  - Added `data/demo/previews.json` fixture mapping each of the 5 demo ideas to distinct 1:1 previews with honest copy, rationale, and evidence.
  - Added `GET /api/v1/previews` endpoint in `src/api/creative.py`.
  - Upgraded `src/api/static/reco-actions.js` and `reco-actions.css` with 1:1 thumbnails on all ranked moves, rich preview modal dialog, placement switching (Instagram 4:5, Story 9:16, Facebook feed), competitor compare view, copy-ready checklist for non-post moves, HTML5 canvas PNG export, copy caption, and instructions download.
  - Added `tests/test_insight_previews.py` testing model validation, endpoint, and browser E2E at `375px` and `1440px` with zero model calls. All 430 tests passing in `make check`.

### 2. Next Up: SEO Head Block, Front-End Events & Track G Front End
- Apply SEO head block and tags from `docs/launch/SEO_AND_EVENTS_HANDOFF.md` into `src/api/static/index.html` and other static HTML pages.
- Create 1200x630 `src/api/static/og-cover.png`.
- Wire product events from section 5 of `SEO_AND_EVENTS_HANDOFF.md`.
- Track G front end: inline digest prompt on `/` at value moments, and frequency/topic controls on `/digest` with account requirement per Revision 4.
