# PRD, Signed-In Onboarding, Insight-to-Ad Previews, SEO & Events, and Digest Habit Progress

**Branch:** `prd-research-previews`
**Owner:** Antigravity Session 1 (front end) / Gemini takeover
**Priority Order (Revision 3 & 4):** Track A → Track H → Track B → SEO & Events → Track G
**Rules:** `DEMO_MODE=true`, zero paid model calls, no deploy, no push, no migrations applied, no secret changes.

---

## Current State Snapshot (2026-11-10 01:05 PT)

### 1. What is DONE (Committed on `prd-research-previews`)
- **Step 1 (`b79a035`):** Verified `make check` (`ruff check .`, `ruff format --check .`, `pytest` — `423 passed, 2 skipped`) and committed Claude's `reco-actions` change (`src/api/static/reco-actions.js`, `src/api/static/reco-actions.css`, `src/api/static/index.html`, `tests/test_account_ui.py`).
- **Track A (`fe2c827`):**
  - Wrote complete `docs/product/PRD.md` covering all 8 required sections + Tracks B–H (including Revision 2 and Revision 3 signed-in onboarding), with every claim/number labeled `[live]`, `[sample]`, or `[estimate]`, plus the Appendix 1 homepage truth table verified in Chromium.
  - Applied the 4 copy accuracy fixes in `src/api/static/index.html` (reconciled `4 competitors (6 catalog & shop pages tracked)`, reconciled `$14–$22` POD vs `$75–$900` direct signed vs `$60–$2,500` SikhiArt range, clarified `Add · 🪙 1 run (live) / 0 in demo`, marked exhibition & 550th anniversary claims as needing artist verification before publishing, and labeled the demo workspace as `Sample shop`).
- **Track H (`cce4f62`):**
  - Mounted `GET /welcome` in `src/api/main.py`.
  - Created `src/api/static/welcome.css`, `src/api/static/welcome.html`, and `src/api/static/welcome.js` implementing the 4-step skippable, resumable onboarding flow with 1-run charged on completion and completion explainer.
  - Added `tests/test_welcome_onboarding.py` testing the full flow and contract at `375px` and `1440px` with zero model calls and fixture APIs.
- **Track B (`ec8f235`):**
  - Added `PreviewSpec`, `PreviewEvidence`, and `CompetitorAdCard` to `src/models/creative.py`.
  - Added `data/demo/previews.json` fixture mapping each of the 5 demo ideas to distinct 1:1 previews with honest copy, rationale, and evidence.
  - Added `GET /api/v1/previews` endpoint in `src/api/creative.py`.
  - Upgraded `src/api/static/reco-actions.js` and `reco-actions.css` with 1:1 thumbnails on all ranked moves, rich preview modal dialog, placement switching (Instagram 4:5, Story 9:16, Facebook feed), competitor compare view, copy-ready checklist for non-post moves, HTML5 canvas PNG export, copy caption, and instructions download.
  - Added `tests/test_insight_previews.py` testing model validation, endpoint, and browser E2E at `375px` and `1440px` with zero model calls. All 430 tests passing in `make check`.
- **Track G, SEO & Product Events (Finished, Ready to Commit):**
  - Head block for `index.html`: canonical, meta description, robots (`index, follow`), OG and Twitter card tags, JSON-LD Schema.
  - Created `src/api/static/og-cover.png` (1200x630 PNG).
  - Per-page meta tags on `/today`, `/create`, `/digest`, and `noindex` on `/welcome`.
  - Product analytics events wired across static JS: `idea_accepted`, `idea_dismissed`, `idea_archived`, `idea_adjusted`, `idea_done` in `muse-shell.js`; `post_started`, `post_downloaded` in `today.js` and `creator.js`; `digest_prompt_shown`, `digest_subscribed` in `digest-signup.js` and `reco-actions.js`.
  - Track G front end on `/digest`: frequency selector (`weekly`, `biweekly`), topic checkboxes (`prices`, `listings`, `ideas`), account requirement gate `#digestAccountGate` (per Revision 4), removed free-text email input, and `#digestAccountInfo` showing email and runs remaining (pauses automatically at 0 runs).
  - Track G front end on `/`: inline digest prompt `#jrDigestPrompt` under `#loop-improve` at value moments, plus digest link inside `#jrPreviewModal`.
  - Onboarding timing hardening in `src/api/static/welcome.js` ensuring server saves persist before displaying next step.
  - Added `tests/test_seo_and_digest_ui.py` covering SEO tags, `og-cover.png` specs, digest controls, account gate, and Playwright browser E2E test at 375px and 1440px with zero model calls.
  - Full `make check` passing cleanly (`ruff check .`, `ruff format --check .`, `pytest` — 435 passed, 2 skipped in 14.64s).

---

### 2. Shipped vs Fixture-Only vs Unverified Summary
- **Shipped Code (Front End):**
  - `/welcome` 4-step onboarding flow (`welcome.html`, `welcome.js`, `welcome.css`).
  - Insight-to-ad previews with 1:1 demo creative specs, placement switcher, competitor compare view, canvas PNG export, instructions download (`reco-actions.js`, `reco-actions.css`).
  - SEO head block, OpenGraph tags, JSON-LD schema, `og-cover.png` (1200x630).
  - Product events for triage, exports, and digest habit.
  - `/digest` frequency/topics controls, account gate and runs left display; home page inline digest habit prompt.
- **Fixture-Only:**
  - `data/demo/previews.json`: 5 demo 1:1 creative preview specs with sample images.
  - `tests/test_welcome_onboarding.py`, `tests/test_insight_previews.py`, `tests/test_seo_and_digest_ui.py`: offline fixture APIs and browser E2E tests with zero paid model calls.
- **Unverified:**
  - Live Resend email sending (digest is disabled in production pending environment settings via `scripts/enable_digest.sh`).
  - Session 2 backend implementations for database research cache (`research_cache.sql`), outcome logging (`/progress`), and steerable research preferences.
