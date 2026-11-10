# PRD, Signed-In Onboarding, Insight-to-Ad Previews, and Digest Habit Progress (Antigravity Session 1)

**Branch:** `prd-research-previews`
**Owner:** Antigravity Session 1 (front end)
**Priority Order (Revision 3):** Track A → Track H → Track B → Track G
**Rules:** `DEMO_MODE=true`, zero paid model calls, no deploy, no push, no migrations applied, no secret changes.

## Checkpoints

### Checkpoint 0 — Claimed Scope & Branch Created (2026-11-09 23:22 PT)
- Read `AGENTS.md`, `docs/launch/ANTIGRAVITY_HERMES_PRD_RESEARCH.md` (including Revision 2 & Revision 3), `docs/launch/ANTIGRAVITY_CREATIVE_EDITOR.md`, and `docs/launch/STATUS.md`.
- Created branch `prd-research-previews` from `main` (`326cc22`), preserving uncommitted `src/api/static/reco-actions.js`, `src/api/static/reco-actions.css`, and `src/api/static/index.html`.
- Claimed Session 1 (`prd-research-previews`) and Session 2 (`prefs-cache-progress` in `/tmp/muse-prefs-cache-progress`) in `docs/launch/STATUS.md`.

### Checkpoint 1 — Verified & Committed `reco-actions` (`b79a035`, 2026-11-09 23:26 PT)
- Fixed test isolation in `tests/test_account_ui.py::test_google_oauth_start_and_callback_mint_verified_session` so `.env` Google OAuth credentials do not mask the Supabase fallback assertion.
- Verified `make check` (`ruff check .`, `ruff format --check .`, `pytest` -> `423 passed, 2 skipped`).
- Committed `b79a035` on `prd-research-previews`.

### Checkpoint 2 — Completed Track A: `docs/product/PRD.md` + 4 Copy Accuracy Fixes (2026-11-09 23:35 PT)
- Wrote `docs/product/PRD.md` derived from shipped codebase covering all 8 required sections + Tracks B–H (including Revision 3 signed-in onboarding), with every figure/claim labeled `[live]`, `[sample]`, or `[estimate]`, plus the Appendix 1 homepage truth table verified in Chromium.
- Applied the 4 copy accuracy fixes in `src/api/static/index.html` (reconciled `4 competitors (6 catalog & shop pages tracked)`, reconciled `$14–$22` POD vs `$75–$900` direct signed vs `$60–$2,500` SikhiArt range, clarified `Add · 🪙 1 run (live) / 0 in demo`, marked exhibition & 550th anniversary claims as needing artist verification before publishing, and labeled the demo workspace as `Sample shop`).
- Verified `pytest tests/test_ui_polish.py tests/test_portal_demo.py` (`7 passed`).
- Next executable step: **Track H (Session 1 front end)** — build `/welcome` (`src/api/static/welcome.html`, `src/api/static/welcome.js`, `src/api/static/welcome.css`, mounted at `GET /welcome` in `src/api/main.py`), wire signed-in home page sections in `index.html` / `welcome-workspace.js` to workspace data with honest empty states (no Sarabjit sample numbers on real accounts unless viewing `Sample shop`), emit PostHog onboarding funnel events, and add browser tests at `375px` and `1440px`.
