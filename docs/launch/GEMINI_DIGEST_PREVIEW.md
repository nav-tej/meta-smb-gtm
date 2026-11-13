# Gemini Checkpoint — Personal Digest Preview & Saved Draft Preferences (Batch 2A)

- **Worktree:** `/tmp/muse-digest-preview`
- **Branch:** `digest-preview` (branched cleanly from `268efee`, `shop-images`)
- **Frozen Hermes worktree:** `/tmp/muse-shop-images` was left untouched.
- **Assignment & Review:** [`.tasks/gemini-digest-preview.txt`](../../.tasks/gemini-digest-preview.txt), [`docs/launch/DIGEST_PLAN_REVIEW.md`](DIGEST_PLAN_REVIEW.md)
- **Status:** Batch 2A complete; ready for Codex review (**ownership explicitly released**)

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
- `DEMO_MODE=true META_MODEL_API_KEY= DEMO_KEY= make check`: exit `0`:
  - `.venv/bin/ruff check .`: `All checks passed!`
  - `.venv/bin/ruff format --check .`: `226 files already formatted`
  - `.venv/bin/pytest`: `557 passed, 2 skipped, 1 warning in 92.26s` (2 pre-existing skips in `test_billing.py` & `test_digest_email.py`; `tests/test_digest_preview.py` 3/3 passed; `tests/test_digest_preview_e2e.py` 1/1 passed at 375px & 1440px in real Chromium with Resend unavailable and spies asserting 0 emails, 0 crawls, 0 Muse calls).

## Remaining Gaps / Out-of-Scope (Batch 2B)

- Live Resend delivery ledger, scheduled slot claims, cron frequency changes, and email-to-editor account-bound recommendation handoff remain out of scope for Batch 2A and deferred to Batch 2B after Codex review.
- Ownership of branch `digest-preview` in `/tmp/muse-digest-preview` is **released** for Codex review. No merge, push, deploy, email send, or paid call was made.
