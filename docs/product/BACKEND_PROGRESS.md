# Backend Real Implementation Progress

**Branch:** `backend-real` (branched from `prd-research-previews` at `8c3fa0b`)
**Owner:** Antigravity Session 2 (backend)
**Baseline:** `make check` passed (441 passed, 2 skipped in 20.76s).
**Current Suite:** `make check` passed (493 passed, 2 skipped in 35.66s).
**Status:** Items 1–6 Completed. Starting Item 7 (Voice profile - Track J).

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

- [x] **Item 2: Digest rules (Revision 4):** (`commit 9eb6c71`)
  - Server enforces signed-in account requirement for subscription (`POST /api/v1/digest/subscribe`) returning 401 when unauthenticated.
  - Subscription is strictly bound to verified account email (`account.email`), ignoring arbitrary client body emails.
  - Normal weekly digest email includes runs remaining count in HTML and text.
  - Handled 0-run paused state: sends exactly ONE pause notification email per zero-run period with link to upgrade/reset, and suppresses further emails until runs return.
  - Resumption: when runs return (>0), digest automatically clears pause state and resumes normal delivery.
  - Unsubscribe always wins: RFC 8058 `List-Unsubscribe` headers present on all emails; unsubscribing is idempotent and immediately halts delivery.
  - Added full test suite in `tests/test_digest_rules.py` (5 tests passing).

- [x] **Item 3: Preferences and signals (Track D):** (`commit f3dbc86`)
  - Added `SellerPreferences`, `AccessPreferences`, `TastePreferences`, and `DismissSignal` models in `src/models/seller.py`.
  - Implemented deterministic ranking engine `src/services/preference_ranker.py`:
    - New sellers never see complex ad budget reallocation as top move.
    - Sellers without price control never see pricing moves as do-it-now.
    - Dismiss signals with "no_access" dynamically hide that channel from recommendations.
    - 2+ "too_advanced" dismissals lowers difficulty and deprioritizes advanced moves.
    - Dismiss signals with "already_tried" filters out or demotes that specific move.
    - Preserves stable order with deterministic tie-breaking.
  - Added endpoints in `src/api/preferences.py`:
    - `GET /api/v1/preferences`: retrieves account preferences or defaults.
    - `PUT /api/v1/preferences`: persists preferences to verified account workspace.
    - `POST /api/v1/preferences/signals`: merges `muse.actions` and `muse.dismiss_signals` into account workspace without losing history.
    - `POST /api/v1/preferences/rank`: deterministically ranks candidate ideas.
  - Updated `src/api/static/muse-shell.js` to automatically sync `actions` and `dismiss_signals` to server when signed in.
  - Added comprehensive test suite in `tests/test_seller_preferences.py` (9 tests passing).

- [x] **Item 4: Outcomes and progress (Track F):**
  - Added `Outcome` and `OutcomeSummary` models in `src/models/outcome.py`.
  - Implemented outcomes persistence and honest ROI calculation in `src/services/outcomes.py`:
    - Strict truth rule: `net_roi_usd = None` (requires 1 logged result) when `moves_count == 0`; no invented negative or positive modeled revenue.
    - Honest ROI formula: strictly `total_revenue - plan_cost_usd` ($12 Starter baseline).
    - Stores outcomes in durable account workspace document.
  - Added endpoints in `src/api/outcomes.py`:
    - `GET /api/v1/outcomes`: returns outcomes list and summary (200 with empty outcomes and honest None ROI for unauthenticated callers).
    - `POST /api/v1/outcomes`: logs seller outcome to verified account workspace, enforcing `x-muse-owner` binding.
    - `GET /api/v1/outcomes/summary`: returns computed business summary.
  - Updated `src/api/main.py` to mount `/outcomes` router.
  - Updated `src/api/static/progress.html`:
    - `syncAccount()` fetches server outcomes from `/api/v1/outcomes` when signed in.
    - Form submission sends `POST /api/v1/outcomes` when signed in.
    - Preserves offline/unauthenticated local storage fallback.
  - Comprehensive unit and API test suite in `tests/test_outcomes_server.py` (7 tests passing).

- [x] **Item 5: Research directives pipeline (Track I):**
  - Wired confirmed `ResearchDirective` into `CompetitorIntelRequest` and `build_brief` / `analyze_competitor` as typed fields only (`<research_directive>` JSON block with focus, price_band, channels, timeframe, exclude_topics).
  - Explicit prompt injection security rule and directive rule enforced in `BRIEF_SYNTHESIS_SYSTEM_PROMPT`.
  - Quarantined untrusted competitor data: competitor page titles, meta descriptions, and bodies containing `"ignore previous instructions"` are isolated in `<untrusted_competitor_data>` and cannot hijack system instructions.
  - HTML pre-processing in `src/utils/sitemap.py` strips `<script>` and `<style>` blocks before extracting titles and metadata.
  - Candidate URLs in `directive.competitors_add` are validated against fetch-time SSRF boundary (`validate_safe_url`), dropping unsafe/internal IPs.
  - Implemented account-based rate limiter in `src/services/directive_limiter.py` (max 10 directive modifications per hour per account).
  - Added endpoints in `src/api/directives.py`:
    - `POST /api/v1/directives/confirm`: rate-limited, owner-bound, persists 1 active directive and history capped at 3 saved directives in workspace document. Logs typed structure (never raw text).
    - `GET /api/v1/directives/active`: retrieves current active directive and saved count.
  - Comprehensive test suite in `tests/test_directives_pipeline.py` (6 tests passing).

- [x] **Item 6: Cache layer (Track E):**
  - Created migration file `supabase/migrations/research_cache.sql` (file only, unapplied) and rollback `research_cache_rollback.sql`.
  - Implemented `src/services/research_cache.py`:
    - Content-addressed SHA-256 keys over `(namespace, account_id, normalized_urls, flow, model_id, prompt_version)`.
    - Distinct namespace TTLs: competitor crawl (7 days), daily brief (24 hours), ad previews (no expiry).
    - Cache hits return stored result, charging exactly 0 runs.
    - Format labels for seller clarity (e.g. `"Last checked Nov 10 · Refresh (1 run)"`).
    - Forced refresh bypasses cache and updates timestamp.
  - Comprehensive unit test suite in `tests/test_research_cache.py` (6 tests passing).

- [ ] **Item 7: Voice profile (Track J):**
  - `VoiceProfile` built from seller listings/captions.
  - Similarity check against inspired-by text.
  - Humanizer pass on all generated captions.

- [ ] **Item 8: Trial (Track K):**
  - 14-day trial entitlement model & spec.
  - Configurable trial allowances and questions for Nav in STATUS.md.
