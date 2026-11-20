# Batch 1 Review Corrections Checkpoint (`batch1-corrections`)

**Branch / Worktree:** `batch1-corrections` at `/tmp/muse-batch1-corrections` (based on `70d148a`)  
**Status:** Completed, verified, committed, and **ownership released** for Codex integration/review.

---

## 1. Baseline Reproductions (Before Fixes)

1. **Voice demo gate discrepancy (`503` vs `403`):**
   - Running with `tests/conftest.py:91` (`DEMO_MODE=false`) and no `META_MODEL_API_KEY` routed `POST /api/v1/seller-memory/voice/transcribe` directly to `transcribe_audio`, producing `503`.
   - Running with explicit `DEMO_MODE=true` returned `403` (`demo_unavailable`).
2. **Draft ignore / scoping leaks:**
   - Mismatched `ignored_entry_ids` vs `ignore_entry_ids` keys and default resolution ordering allowed ignored entries (`60 min/wk`) and cross-product prices (`EUR 45` vs `$18`) to leak into recommendations.
3. **Recommendation → Editor handoff fallback:**
   - Passing `?idea=<TITLE>` to `/create` failed to match a sample idea ID, causing personalized recommendation cards to fall back to the Sarabjit (`#artistExample`) sample template.

---

## 2. Completed Fixes (Slices 1–5)

- **Slice 1 — Workspace / Account Isolation & XSS Hardening (`seller-memory.js`, `models/seller.py`, `services/seller_memory.py`):**
  - Added generation/owner guards on async `/recommend` and `PUT /api/v1/seller-memory` queues so account switches or sign-outs (`A -> signout -> B`) abort stale queued mutations and ignore late responses without reloading.
  - Updated `clearPrivateMemoryUI()` to synchronously clear modal/panel DOM and `onboardingEntries`, `onboardingScanDiff`, `onboardingScanWarnings`, `onboardingScanUrl`, and `onboardingScanDate`.
  - Validated `source_url` strictly for `http://`/`https://` schemes; hostile schemes (e.g., `javascript:alert(1)`) render as inert text, never clickable `<a href>`.
  - Fixed `apiJson()` header spreading so `X-Muse-Owner` no longer clobbers `Content-Type: application/json`.
- **Slice 2 — Schema Preservation, Optimistic Concurrency & 3-Way Merge (`models/seller.py`, `api/seller_memory.py`, `seller-memory.js`):**
  - Enabled `ConfigDict(extra="allow")` across root and nested Seller Memory models so unknown server/client fields survive `PUT`, `DELETE`, and suggestion evaluate/respond mutations.
  - Enforced explicit `expected_version` on `PUT /api/v1/seller-memory` (`409` conflict when omitted or mismatched).
  - Implemented 3-way conflict merge (`#smConflictMergeBtn`) and fixed `saveDefaultBtn` + aligned entries so server-concurrent edits (e.g., `goal`), `voiceProfile`, and unknown extras are preserved when merging non-conflicting local changes.
- **Slice 3 — Context Truth, Scoping & Channel Exclusions (`services/seller_memory.py`, `seller-memory.js`):**
  - Normalized `ignore_entry_ids` / `ignored_entry_ids` resolution before deriving defaults.
  - Enforced strict product + destination scoping with currency preservation (`EUR 45` vs `$18`), refusing to guess when unscoped or ambiguous across multiple products/destinations.
  - Scoped draft overrides per `(account, mode, draftId)` slot.
  - Rendered `#smMissingInfoBanner` and returned zero moves when all posting channels are excluded.
- **Slice 4 — Voice Consent & Demo Gate (`models/voice.py`, `api/seller_memory.py`):**
  - Enforced `consent_confirmed=true` (`400` on missing consent) and explicit `DEMO_MODE=true` / `live=true` / `X-Demo-Key` gating before any billing (`authorize_operation` / `_spend_credit`) or `get_meta_client().transcribe_audio` provider call.
- **Slice 5 — Owner-Bound Recommendation Handoff to `/create` & `/today` (`services/seller_memory.py`, `api/seller_memory.py`, `seller-memory.js`, `creator.js`, `today.js`):**
  - Replaced title-based `?idea=` handoffs with owner-bound opaque `?sm_handoff=<id>&draft=<draft_id>` tokens carrying the **selected** recommendation (including non-top ranked moves), uploaded photo, product, channel, goal, price claim, and CTA into `/create` and `/today`.
  - Stripped sample Sarabjit/Art-of-Sarabjit links and copy (`stripSampleOffersAndLink()` in `creator.js`, destination guard in `today.js`) in signed-in own workspaces, and ensured unrecognized `?idea=` values do not block own-workspace initialization.

---

## 3. Modified Files

- `src/models/seller.py`
- `src/models/voice.py`
- `src/services/seller_memory.py`
- `src/api/seller_memory.py`
- `src/api/static/seller-memory.js`
- `src/api/static/creator.js`
- `src/api/static/today.js`
- `tests/test_seller_memory.py`
- `tests/test_seller_memory_e2e.py`
- `docs/launch/GEMINI_BATCH1_CORRECTIONS.md`

---

## 4. Exact Verification Results (Run After Final Code Edit)

1. **JS Syntax Checks:**
   - `node --check src/api/static/seller-memory.js && node --check src/api/static/creator.js && node --check src/api/static/today.js` → **exited 0**.
2. **Full Repository Check (`make check`):**
   - `DEMO_MODE=true META_MODEL_API_KEY= DEMO_KEY= make check` → **exited 0**
   - `.venv/bin/ruff check .`: `All checks passed!`
   - `.venv/bin/ruff format --check .`: `218 files already formatted`
   - `.venv/bin/pytest`: **`538 passed, 2 skipped in 48.28s`** (the 2 skips are pre-existing environment-gated skips in `tests/test_billing.py` and `tests/test_digest_email.py`).
3. **Targeted Seller Memory & E2E Playwright Suite (1440px Desktop & 375px Mobile Chromium):**
   - `DEMO_MODE=true META_MODEL_API_KEY= DEMO_KEY= .venv/bin/pytest tests/test_seller_memory.py tests/test_seller_memory_e2e.py tests/test_editor_idea_handoff.py -v` → **`14 passed in 15.11s`**:
     - `tests/test_seller_memory.py`: 7 passed (`test_shop_scan_separates_observations_from_interpretations_and_no_invented_prices`, `test_rescan_diff_preserves_seller_edited_observation`, `test_voice_fixture_consent_gate_and_conflict_detection`, `test_competitor_role_change_shifts_top_recommendation_and_draft_override_stays_temporary`, `test_conflict_409_forget_entry_feedback_suggestions_and_owner_isolation`, `test_put_requires_explicit_expected_version_and_preserves_unknown_extras`, `test_context_truth_currency_product_destination_ignore_and_all_channels_excluded`).
     - `tests/test_seller_memory_e2e.py`: 2 passed (`test_seller_memory_full_mobile_multi_browser_workflow`, `test_batch1_corrections_security_merge_drafts_and_handoff_e2e` — covers 1440px desktop & 375px mobile, hostile `source_url`, 2-draft isolation, real ignore button, 3-way conflict merge, non-top `?sm_handoff=` through PNG export in `/create` and `/today`, unrecognized `?idea=`, `#smMissingInfoBanner`, and no-reload `A -> signout -> B` stale `/recommend` + queued `PUT` abort).
     - `tests/test_editor_idea_handoff.py`: 5 passed.

---

## 5. Remaining Gaps & Environment Boundaries

- All tests ran offline with `DEMO_MODE=true META_MODEL_API_KEY= DEMO_KEY=`. Live Meta Whisper transcription (`transcribe_audio`) and usage metering were verified using mocked provider/billing spies (`monkeypatch`), not against live Meta APIs.
- Browser E2E and conflict/concurrency tests ran against the stateful in-memory `e2e_server` and `TestClient`, not against a live hosted Supabase database.

---

## 6. Ownership Release

Ownership of `/tmp/muse-batch1-corrections` (`batch1-corrections`) and Batch 1 review corrections is **explicitly released**. No further edits will be made on this branch.
