# Gemini Checkpoint — Personal Digest Preview & Saved Draft Preferences (Batch 2A)

- **Worktree:** `/tmp/muse-digest-preview`
- **Branch:** `digest-preview` (branched cleanly from `268efee`, `shop-images`)
- **Frozen Hermes worktree:** `/tmp/muse-shop-images` was left untouched.
- **Assignment & Review:** [`.tasks/gemini-digest-preview.txt`](../../.tasks/gemini-digest-preview.txt), [`.tasks/gemini-digest-preview-fixes.txt`](../../.tasks/gemini-digest-preview-fixes.txt), [`docs/launch/DIGEST_PLAN_REVIEW.md`](DIGEST_PLAN_REVIEW.md), [`docs/launch/DIGEST_PREVIEW_REVIEW.md`](DIGEST_PREVIEW_REVIEW.md)
- **Status:** Batch 2A + focused race/state-isolation/truthfulness fixes complete; ready for Codex review (**ownership explicitly released**)

## Implemented Behavior

1. **Personal digest preview & schedule service (`src/services/digest_preview.py`)**
   - Supports canonical cadences (`weekly`, `biweekly`, `monthly`, `paused`), canonical topics (`listing_changes`, `pricing`, `suggested_moves` with backwards-compatible aliases `listings`, `prices`, `ideas`), and IANA timezone validation (`zoneinfo.ZoneInfo`).
   - Deterministic `compute_next_send_window(...)`: computes proposed delivery windows with explicit DST wall-clock handling, stable 14-day `biweekly` anchors, month-end clamping (`31st -> Feb 28 / Feb 29 leap year / Apr 30`), and `None` when `paused`.
   - Workspace persistence (`load_digest_draft`, `save_digest_draft`) in dedicated `digest_draft_preferences` namespace using `load_workspace` / `save_workspace` (owner derived server-side, `verify_workspace_owner`, `expected_version` optimistic concurrency, unknown workspace fields preserved).
   - Zero-cost personal preview (`build_personal_digest_preview`): uses ONLY the signed-in seller's approved memory (`_extract_profile_parts` + `rank_seller_recommendations`) and already-saved snapshots (`SnapshotStore.get`, no silent local disk fallback when Supabase is configured; never triggers crawls, email sends, Muse calls, or run debits).
   - Truthfully distinguishes `changed`, `unchanged`, `baseline`, `never_checked`, `stale`, `failed`, and `unavailable` shop states; caps changes at `3` with safe HTTP(S) links; escapes all HTML and links workspace move to `/portal` (`Open My workspace →`).
2. **Additive authenticated API routes (`src/api/digest_email.py`)**
   - Added `GET /api/v1/digest/preferences`, `PUT /api/v1/digest/preferences`, and `POST /api/v1/digest/preview` with `Cache-Control: no-store` and owner verification.
   - Left existing `/subscription`, `/subscribe`, `/confirm`, `/unsubscribe`, `/send`, and `vercel.json` untouched.
3. **Digest Preview & Draft UI (`src/api/static/digest.html`, `digest.css`, `digest-signup.js`)**
   - Added `#digestDraftSection` visible even when Resend is unconfigured, with explicit `"Preview & draft settings only"` banner clarifying that draft `paused` / cadence choices do not subscribe, pause, or change active email deliveries.
   - Wired cadence (`weekly`/`biweekly`/`monthly`/`paused`), monthly day (`1–31`), IANA timezone selector (with browser timezone detection), canonical topic checkboxes, optimistic-concurrency save, and sandboxed `<iframe sandbox="" srcdoc="...">` mobile HTML + plain-text preview toggle.
   - **Focused review fixes (`digest-signup.js`, `src/services/digest_preview.py`):**
     - Re-checks `accountGen` & `draftOwnerId` after every `await` (`fetch`, `r.json()`, `refreshPreview`, and `finally` blocks) and uses `AbortController` + a separate monotonic `previewReqSeq` so delayed `r.json()` bodies or reversed same-owner preview completions cannot overwrite newer state.
     - Synchronously clears `#digestEmailPreviewBox`, `#digestPreviewFrame.srcdoc`, preview text/subject/window, draft inputs, `draftVersion`, and `draftLoadedForOwner` on `A -> B` owner switches and sign-out, keeping draft controls/save disabled until the active owner's `loadDraftAndPreview` succeeds.
     - Updated `_subscription_banner_info` to return `"status": "unknown"`, `"live_delivery_active": None`, and `"draft_only": True`.

## Modified & Added Files

- Added:
  - `src/services/digest_preview.py`
  - `tests/test_digest_preview.py`
  - `tests/test_digest_preview_e2e.py`
  - `docs/launch/GEMINI_DIGEST_PREVIEW.md`
- Modified:
  - `src/api/digest_email.py`
  - `src/api/static/digest.html`
  - `src/api/static/digest.css`
  - `src/api/static/digest-signup.js`

## Exact Observed Verification Results (Post-Final-Edit)

- `node --check src/api/static/digest-signup.js`: exit `0`
- `.venv/bin/ruff check .`: `All checks passed!`
- `.venv/bin/ruff format --check .`: `227 files already formatted`
- `.venv/bin/pytest -q tests/test_digest_preview.py tests/test_digest_preview_e2e.py`: `5 passed in 26.36s` (with `DEMO_MODE=true META_MODEL_API_KEY= DEMO_KEY=`, covering delayed `r.json()` during `A -> B` switch, HTTP `503` failed B load, sign-out clearing, reversed `weekly`/`paused` preview completion, and `subscription_state.status == "unknown"` / `live_delivery_active is None`).
- `DEMO_MODE=true META_MODEL_API_KEY= DEMO_KEY= make check`: `554 passed, 2 skipped, 4 failed, 1 warning in 632.68s` (2 pre-existing skips in `test_billing.py` & `test_digest_email.py`; 4 unrelated Playwright timing flakes under full-suite load in `test_seller_memory_e2e.py`, `test_signup_followup_e2e.py`, `test_steer_voice_progress.py`, and `test_workspace_modes_e2e.py`, all of which passed on direct re-run: `8 passed in 73.27s` for `test_seller_memory_e2e.py` + `test_steer_voice_progress.py`, and `9 passed in 103.46s` for `test_signup_followup_e2e.py` + `test_workspace_modes_e2e.py`).

## Remaining Gaps / Out-of-Scope (Batch 2B)

- Live Resend delivery ledger, scheduled slot claims, cron frequency changes, and email-to-editor account-bound recommendation handoff remain out of scope for Batch 2A and deferred to Batch 2B after Codex review.
- Ownership of branch `digest-preview` in `/tmp/muse-digest-preview` is **released** for Codex review. No merge, push, deploy, email send, or paid call was made.
