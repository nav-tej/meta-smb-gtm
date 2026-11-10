# Backend Real Implementation Progress

**Branch:** `backend-real` (branched from `prd-research-previews` at `8c3fa0b`)
**Owner:** Antigravity Session 2 (backend)
**Baseline:** `make check` passed (441 passed, 2 skipped in 20.76s).
**Current Suite:** `make check` passed (460 passed, 2 skipped in 34.80s).
**Status:** Review Blockers and Should-Fix Items (1–9) Completed. Continuing with `.tasks/backend-assignment.txt` Item 2.

---

## 1. Review Fixes (Completed & Verified)

- [x] **Blocker 1: Onboarding ownership and debit** (`commit 390d3ff`)
  - Pure function for social handle extraction: `src/services/social_extract.py`, `tests/test_social_extract.py`.
  - Server endpoint `POST /api/v1/onboarding/build` (`src/api/onboarding.py`):
    - Authenticates session via `resolve_account` and checks `x-muse-owner`.
    - Idempotent: charges exactly 1 run only on success, once per account (re-runs and retries cost 0 runs).
    - Failed workspace saves surface error (not masked) and refund in-flight hold.
    - Zero-run accounts can finish onboarding with crawl data for 0 runs.
  - Client state isolation in `src/api/static/welcome.js`:
    - Storage strictly scoped per user (`muse_onboarding_<id>`).
    - Pointed step 4 finish to `/api/v1/onboarding/build`.
    - Surfaced save failures directly in UI (`wkStep4Error`) without masking.
  - Post-auth routing: redirects new accounts to `/welcome` and returning accounts to `/`.
  - Full test suite in `tests/test_onboarding_server.py` and `tests/test_welcome_onboarding.py`.

- [x] **Blocker 2: Escape digest email in preview UI** (`commit b2af9e9`)
  - Escaped account email wherever rendered in the preview UI (`src/api/static/reco-actions.js`). Used DOM text nodes / `strong.textContent` rather than `innerHTML` interpolation.
  - Added E2E browser tests in `tests/test_seo_and_digest_ui.py` with email-shaped strings containing markup (`<b id='injectedMarkup'>maker</b>@example.com`), verifying that no markup elements are injected into the DOM on either `/digest` or the home page prompt.

- [x] **Blocker 3: Progress page honest labels, ownership, ROI** (`commit 5d40d06`)
  - Progress page: scoped stored outcomes to verified account owner (`muse.outcomes.<user_id>`), eliminating cross-account leakage.
  - Labeled revenue as "Logged on this device" (removed unverified `[live]` tag).
  - Fixed plan cost label to clarify starter baseline ($12/mo).
  - Enforced honest ROI math: no net return figure (`—`) without at least 1 logged result.
  - Measured logged time honestly from actual minutes logged across moves.
  - Added browser verification tests in `tests/test_steer_voice_progress.py`.

- [x] **Blocker 4: Remove/reword unkeepable promises** (`commit aeaa212`)
  - Reworded directive confirmation copy to state what actually happens: "confirmed and saved on this device (0 runs used)" (`src/api/static/reco-actions.js`).
  - Corrected onboarding disclosure to state it saves crawled shop data and competitor watchlist (`welcome.html`, `welcome.js`).
  - Added sample watchlist attribution on homepage counters (`index.html`).
  - Removed "pauses automatically" promise in digest signup UI (`digest-signup.js`, `digest.html`).

- [x] **Should Fix 5: Humanizer lint-and-suggest** (`commit c035426`)
  - Converted `src/utils/humanizer.py` into a non-destructive lint-and-suggest design.
  - Preserves original text; generates suggestions for seller review/acceptance.
  - Protected quoted text (`"..."`), artwork titles (e.g. *Revolutionary Light*, *A Tapestry of Light*), product nouns (e.g. *handwoven tapestry*), and paragraph newlines (`\n\n`).
  - Added tests in `tests/test_humanizer.py` covering Codex review sample cases 6 through 10.

- [x] **Should Fix 6: Directives syntax-only labeling** (`commit cb10737`)
  - Updated `src/models/directive.py` and `src/api/directives.py` with docstrings explicitly stating parser is syntax-only.
  - Documented that any future crawler fetching from candidate URLs must pass them through `src.utils.sitemap.validate_safe_url` at fetch time.

- [x] **Should Fix 7: SEO, noindex, sitemap, JSON-LD, llms.txt** (`commit 059deb7`)
  - Added `X-Robots-Tag: noindex, nofollow` to `/account`, `/welcome`, and `/progress` in `src/api/main.py`.
  - Removed `/progress` from `src/api/static/sitemap.xml`.
  - Added annual `$108/year` offer to Schema.org JSON-LD in `src/api/static/index.html`.
  - Reconciled statements in `src/api/static/llms.txt` with actual code reality.
  - Updated assertions in `tests/test_steer_voice_progress.py` and `tests/test_seo_and_digest_ui.py`.

- [x] **Should Fix 8: PRD.md reconciliation** (`commit aeacd9e`)
  - Labeled fixture-backed insight previews and device-local features in `docs/product/PRD.md`.
  - Fixed daily brief line: cached brief from monitor snapshots (0 runs, no charged live query).
  - Fixed pricing plan line: Starter active in UI ($9/mo annual / $12/mo monthly), Pro planned.

- [x] **Should Fix 9: Behavior tests requested by review** (`commit 1f2b149`)
  - Created `tests/test_review_behaviors.py`:
    - Failed workspace PUT returns 409 Conflict with clear detail.
    - Stale / mismatched `x-muse-owner` header returns 409 Conflict.
    - Failed onboarding save surfaces error and refunds run hold.
    - Cross-account session transitions isolate workspace and onboarding.
    - Onboarding retry / double-submit charges exactly 1 run on first call and 0 runs on retry.
    - Directives parser is syntax-only, rejects injection, and downstream candidate URLs validate against `validate_safe_url`.

---

## 2. Backend Assignment Tasks (In Progress)

- [ ] **Item 2: Digest rules (Revision 4):**
  - Server enforces signed-in account requirement for subscription (`POST /api/v1/digest/subscribe`).
  - Read entitlement/credits server-side to include runs left in preview.
  - Handle 0-run paused state: send exactly one pause notification email per zero-run period, pause further sending until runs return.
  - Unsubscribe always wins.
  - Tests in `tests/test_digest_rules.py`.

- [ ] **Item 3: Preferences and signals (Track D):**
  - `SellerPreferences` on workspace model.
  - Sync `muse.actions` and `muse.dismiss_signals` to account workspace when signed in.
  - Deterministic ranking of ideas from preferences + dismiss reasons.

- [ ] **Item 4: Outcomes and progress (Track F):**
  - `Outcome` model stored per account.
  - `/api/v1/outcomes` read/write endpoints.
  - `/progress` syncs with server when signed in.
  - Honest ROI math (only logged revenue counts).

- [ ] **Item 5: Research directives pipeline (Track I):**
  - Wire parsed `ResearchDirective` into competitor intel pipeline using typed fields only.
  - Rate limit directives per account.
  - Test fixture with competitor page containing `"ignore previous instructions"`.

- [ ] **Item 6: Cache layer (Track E):**
  - Migration file `supabase/migrations/research_cache.sql` (file only, do not apply).
  - `ResearchCache` service layer with TTLs and hash keys.
  - 0 runs charged on cache hit.

- [ ] **Item 7: Voice profile (Track J):**
  - `VoiceProfile` built from seller listings/captions.
  - Similarity check against inspired-by text.
  - Humanizer pass on all generated captions.

- [ ] **Item 8: Trial (Track K):**
  - 14-day trial entitlement model & spec.
  - Configurable trial allowances and questions for Nav in STATUS.md.
