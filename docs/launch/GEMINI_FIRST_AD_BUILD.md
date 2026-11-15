# Gemini First-Ad Workflow Build & Verification Report

- **Date:** 2026-11-15
- **Worktree:** `/tmp/muse-first-ad`
- **Branch:** `codex/first-ad` (branched from `fa3a439`)
- **Owner:** Gemini (build & offline verification) -> **Ownership released to Codex for review**
- **Mode:** `DEMO_MODE=true META_MODEL_API_KEY= DEMO_KEY=` (zero paid calls, zero ad spend, zero remote mutations, zero deployment)

## Scope & Files Owned

- `src/api/main.py`: Added `GET /first-ad` (`include_in_schema=False`) serving `first-ad.html` with `NOINDEX_PAGE_HEADERS`.
- `src/api/static/first-ad.html`: Bounded 4-step guided workflow UI (`1. Outcome`, `2. Creative & destination`, `3. Audience, budget & dates`, `4. Review & handoff`) with `Not published · Draft only` and provenance badges (`Suggested starting approach` / `Artist example`).
- `src/api/static/first-ad.css`: Responsive layout for desktop (`1440px`) and mobile (`375px`) with `>= 44px` touch targets and zero horizontal overflow.
- `src/api/static/first-ad.js`:
  - Read-only reuse of `/api/v1/seller-memory` and `/create` draft state plus `/api/v1/product-reference` image import.
  - Per-account persistence (`muse-first-ad-v1:account:<id>`) separated from sample mode (`muse-first-ad-v1:sample`, `?workspace=sample`).
  - Client-side validation for destination URL, daily/lifetime budget (`> 0`), and date range (`endDate >= startDate`).
  - Missing prerequisites checklist (`Manual Meta setup required` — Business Portfolio / Page / Ad Account / payment method / pixel) and explicit `"Not published"` status.
  - No password fields in the workflow (`main input[type="password"]` count = `0`) and no live Meta campaign writes.
  - Actual exports: `1080 × 1350` PNG (and `1080 × 1080` square option) plus `.txt` manual Ads Manager handoff checklist (`STATUS: NOT PUBLISHED`).
- `docs/product/META_MARKETING_API_REQUIREMENTS.md`: Separate documentation of official Meta Marketing API integration requirements (OAuth 2.0, `ads_read`/`ads_management`/`business_management`, Business Verification + App Review `Advanced Access`, Development vs Full Access tiers, Ad Account/asset ownership & System Users, `status="PAUSED"` creation, explicit activation gate, client idempotency + check-before-retry, and error code recovery).
- `tests/test_first_ad_e2e.py`: Real headless Chromium E2E test at `1440×900` and `375×844`.

## Verification Results

- `node --check src/api/static/first-ad.js`: exited `0`.
- `ruff check .`: `All checks passed!`
- `ruff format --check .`: `233 files already formatted`
- `.venv/bin/pytest tests/test_first_ad_e2e.py -v` (`DEMO_MODE=true META_MODEL_API_KEY= DEMO_KEY=`): **1 passed** (verified desktop `1440px` & mobile `375px`, `0` password fields in `main`, `0` live Muse calls, budget `0` & `endDate < startDate` validation blocks, reload persistence, `user-a`/`user-b`/sample isolation, `1080 × 1350` PNG exports, and `.txt` checklist containing `STATUS: NOT PUBLISHED`).
- Full offline gate `make PY=/Users/nav/meta-smb-gtm/.venv/bin check` (`DEMO_MODE=true META_MODEL_API_KEY= DEMO_KEY=`):
  - `ruff check .` passed, `ruff format --check .` passed.
  - `pytest`: **558 passed, 2 skipped, 6 failed** (exit code `2`).
  - `tests/test_first_ad_e2e.py` **passed** inside the full run.
  - The **6 failures** were all in pre-existing Playwright E2E tests outside this task's scope:
    - `tests/test_editor_idea_handoff.py::test_all_5_demo_ideas_in_creator_e2e[375]`
    - `tests/test_editor_idea_handoff.py::test_today_idea_handoff_e2e`
    - `tests/test_seller_memory_e2e.py::test_seller_memory_full_mobile_multi_browser_workflow`
    - `tests/test_seller_memory_e2e.py::test_batch1_corrections_security_merge_drafts_and_handoff_e2e`
    - `tests/test_steer_voice_progress.py::test_steer_voice_progress_ui`
    - `tests/test_workspace_modes_e2e.py::test_signed_in_workspace_modes_isolation_import_and_auth_safety_e2e[1440]`

## Saved E2E Artifacts

- `/Users/nav/.gemini/antigravity/brain/45550847-bc70-4498-b227-06554decc39e/scratch/fa-review-1440.png`
- `/Users/nav/.gemini/antigravity/brain/45550847-bc70-4498-b227-06554decc39e/scratch/fa-exported-1440.png` (`1080 × 1350`)
- `/Users/nav/.gemini/antigravity/brain/45550847-bc70-4498-b227-06554decc39e/scratch/fa-checklist.txt`
- `/Users/nav/.gemini/antigravity/brain/45550847-bc70-4498-b227-06554decc39e/scratch/fa-step1-375.png`
- `/Users/nav/.gemini/antigravity/brain/45550847-bc70-4498-b227-06554decc39e/scratch/fa-sample-exported.png` (`1080 × 1350`)

## Ownership Release

Gemini's build, offline E2E verification, and Meta Marketing API requirements documentation are complete in `/tmp/muse-first-ad` on branch `codex/first-ad`. Ownership is hereby released to Codex for review.
