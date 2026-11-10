# Backend Real Implementation Progress

**Branch:** `backend-real` (branched from `prd-research-previews` at `8c3fa0b`)
**Owner:** Antigravity Session 2 (backend)
**Baseline:** `make check` passed (441 passed, 2 skipped in 20.76s).
**Current Suite:** `make check` passed (516 passed, 2 skipped in 43.00s; ruff check clean, ruff format clean across 230 files).
**Status:** Gate 1 Reached. Items 10, 11, and Step 4b Completed & Verified. Ready for Gemini REVIEW (Gate 1).

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

- [x] **Item 7: Voice profile (Track J):**
  - Created `VoiceProfile` model in `src/models/voice.py` storing stylistic traits (avg sentence words, formality, emoji usage, hashtags, recurring words, words to avoid, sample lines, adjustments).
  - Implemented `src/services/voice_profile.py`:
    - `build_voice_profile`: extracts traits from seller's crawled content. Inspiration sources shape style parameters only and their sentences are never stored.
    - `check_inspiration_similarity`: sentence-level token overlap guardrail preventing plagiarism of inspired-by texts.
    - `adjust_voice_profile`: applies seller feedback (`casual`, `formal`, `shorter`).
    - `humanize_generated_caption`: applies deterministic humanizer cleaning (`clean_text`) to strip em dashes, AI buzzwords, and inflated claims.
  - Applied humanizer cleaning to generated ad copy in `src/services/ad_creative.py` (`headline` and `primary_text`).
  - Added endpoints in `src/api/voice.py` (`GET /api/v1/voice/profile`, `POST /api/v1/voice/tune`), mounted in `src/api/main.py`.
  - Comprehensive test suite in `tests/test_voice_profile.py` (6 tests passing).

- [x] **Item 8: Trial (Track K):**
  - Implemented 14-day trial entitlement models in `src/models/trial.py` (`TrialEntitlement`, `BaselineMetrics`, `TrialActivity`, `TwoWeekSummary`).
  - Strict truth rule enforced: day-12 summary carries strictly real counts of seller actions and logged results, never projected or modeled lift.
  - Configurable trial allowances: added `trial_duration_days = 14` and `trial_requires_card = False` to `src/config.py`.
  - Comprehensive specification written in `docs/launch/TRIAL_SPEC.md` documenting the 14-day seller lifecycle, Weekly Active Seller (WAS) north-star definition, and open questions for Nav.
  - Comprehensive unit test suite in `tests/test_trial.py` (5 tests passing).

- [x] **Item 10: Recommendation to Editor Handoff (`commit 59df473`):**
  - Fixed preview dialog, ranked list, snapshot move, and digest links to pass `?idea=<insight_id>` instead of rejected `?goal=<insight_id>`.
  - Added full demo `DEFAULT_PREVIEWS` spec definitions (headline, caption, cta, image_ref, placement, mapped_goal, why_this) in `/create` (`src/api/static/creator.js`) and `/today` (`src/api/static/today.js`).
  - Implemented `applyIdea(spec)` in both creator and today editors; unknown or missing `?idea` IDs safely fall back to default behavior without error.
  - Preserved requested idea against asynchronous device drafts in `recoverDevice()`.
  - Rendered "Why this" evidence dynamically in the editor (`#ideaReason` in creator, `#dailyReason` in today).
  - Export tracking: on download/export, marks idea `done` in `muse.actions` and reveals `#exportDoneOffer` / `#logResultLink` offering "Log result →" pointing to `/progress`.
  - Fired telemetry event `post_started { idea_id, source }`.
  - Zero paid model calls in demo mode.
  - Comprehensive E2E browser and unit test suite in `tests/test_editor_idea_handoff.py` (5 tests passing across 375px and 1440px viewports).

- [x] **Item 11: Ad Library Signals & Public Links (`commit e85548e`):**
  - **Meta Ad Library API Documentation Research (Item 11d):**
    - Official Graph API `/ads_archive` endpoint with `ad_type=ALL` returns ordinary commercial ads *only* when targeted to European Union (EU) member states or the United Kingdom (UK) due to statutory transparency mandates under the EU Digital Services Act (DSA).
    - For the United States (and other non-EU countries), the official API programmatically filters out commercial product/service ads, returning strictly political and social-issue ads.
    - Standard commercial ads for US independent artists cannot be retrieved programmatically via Meta's public API for US targeting.
  - **Implementation (Items 11a, 11b, 11c):**
    - **(11a) Public Search Link-Out:** Added "See their ads on Meta ↗" external links per competitor in `#sellerList` and dynamic competitor creation pointing to `https://www.facebook.com/ads/library/?active_status=active&AdCandidate=&q=<encoded_name>&search_type=keyword_unordered&media_type=all` with `target="_blank" rel="noopener noreferrer"`.
    - **(11b) Sample Shop Truth Isolation:** Sample hooks are shown *only* inside the demo shop (`sarabjit_singh` and `etsy_ceramics`), explicitly labeled with `[sample]`. Real accounts see strictly zero fabricated rows.
    - **(11c) Server API & Cache:** Implemented `GET /api/v1/competitors/ads` with Track E caching (`NAMESPACE_AD_PREVIEWS`).
      - Without token: returns `status="no_token"`, public search URL, and zero fabricated rows (`ads=[]`).
      - With token configured: queries `MetaAdLibraryClient`, caches response, and distinguishes API zero (`status="zero"`, `"No ads found via the Meta API."`) from API failure (`status="error"`, graceful failure note).
      - Live records include `library_url` (`https://www.facebook.com/ads/library/?id=<id>`) and `start_date`.
  - Comprehensive unit test suite in `tests/test_ad_library_signals.py` (6 tests passing).

- [x] **Step 4b: Non-Sample Artist Workspace Isolation (`commit e85548e`):**
  - **Nav's Correction (Nov 10):** Persona is any independent or small artist selling on marketplaces and social. Sikh art, Gurpurab occasions, and the four watchlist competitors belong strictly to the sample shop demo.
  - **PRD Persona Reconciliation:** Updated `docs/product/PRD.md` Section 1.2 to define primary persona as independent/small artists, explicitly framing the Sarabjit Singh shop as a demo showcase.
  - **General Prompts & Endpoints:**
    - `src/services/seller_audit.py`: Replaced niche-specific Gurpurab references with general cultural and seasonal moments applicable to any artist.
    - `src/api/directives.py`: `/suggestions` endpoint dynamically derives pricing suggestions from the signed-in seller's own competitors and medium, falling back to universal artist suggestions.
  - **Client Workspace Scrubbing (`src/api/static/welcome.js` & `index.html`):**
    - Dynamic substitution of steer input placeholder, chips, refine buttons, and playbook title (`Actionable Playbook for ${shopName}`) when viewing a signed-in workspace.
  - **Verification:** Added `tests/test_non_sample_artist.py` verifying that a watercolor studio account ("Elena Vance Watercolor Studio") completes onboarding and has ZERO sample-shop terms leaked into its workspace, suggestions, or outcomes (all passing).

- [x] **Gate 1 Fix Round (Review 3 HOLD Resolution):**
  - **Blocker 1 & 2: Authoritative Idempotent Free Onboarding & Same-Browser Account Isolation:**
    - Added atomic server-side onboarding completion endpoint `POST /api/v1/onboarding/complete-free` returning `used_run=False` and remaining allowance intact.
    - Scoped onboarding and workspace state strictly to account session on the server; eliminated cross-account leakage across Account A and Account B on the same browser instance.
    - Verified in `tests/test_review_behaviors.py` and `tests/test_welcome_onboarding.py`.
  - **Blocker 3: Progress Page & Actual-Plan ROI:**
    - Corrected dynamic actual-plan cost in `src/api/outcomes.py` and `src/api/static/progress.html`.
    - Returns honest `net_roi_usd=None` when zero moves are logged; computes net return against actual plan cost ($12 starter, $29 unlimited).
    - Honest UI label: "Logged on this device" without live claim until server storage is connected.
  - **Blocker 4: Honest Directive & Digest Copy:**
    - Replaced inaccurate "applied" and "1 run" claims with `"0 runs (saved to workspace)"` across `DirectiveResponse`, `/api/v1/directives/parse`, and `/api/v1/directives/confirm`.
    - Updated `src/api/static/llms.txt` to state: "Onboarding is free (0 runs). Weekly market digest reading is free (0 runs). Research directives save to workspace at 0 runs."
  - **Item 5: Humanizer Preservation:**
    - Stopped automatic mutation of creative ad copy (`clean_text`) in `src/services/ad_creative.py` (`_run_comfyui_krea_variant` and `to_editable_brief`).
    - Original headline, primary text, titles, and proper nouns are preserved untouched while humanizer lint suggestions remain available for seller review.
  - **Item 10: Exact Placement Parity in Creator & Today Studios:**
    - Bound placement state in `creator.js` and `today.js` to idea specs:
      - Idea 4 bound to `facebook_feed` (1080×1080 square canvas, dynamic button label `Download Facebook feed image 1080 × 1080 PNG`).
      - Ideas 1, 2, 3, 5 bound to `instagram_feed` (1080×1350 canvas, `Download feed image 1080 × 1350 PNG`).
    - Verified placement state, canvas dimensions via `window.museDrawLayout`, export action storage, and telemetry.
  - **Item 11: Ad Library Signals & Session Binding:**
    - Enforced verified account session requirement on `GET /api/v1/competitors/ads` via `resolve_account`; unauthenticated callers receive `status="no_token"` with public search link-out.
    - Meta Ad Library DSA API documentation findings documented: commercial ads restricted to EU/UK targeting under DSA statutory mandates; commercial ads for US independent artists cannot be programmatically fetched via Meta's public API.
  - **Step 4b: Complete Non-Sample Artist Workspace Isolation:**
    - Audited and eliminated demo-specific content outside the sample shop.
    - Fixture account for a landscape watercolor artist ("Elena Vance Watercolor Studio") completes browser onboarding, verifies `/welcome`, `/today`, `/create`, `/progress`, and `/daily-brief` have zero sample terms ("Sikh", "Sarabjit", "Gurpurab", "Vaisakhi", "Ek Onkar", "SikhiArt", "Triton Museum", "Kala Sangam").
    - Same-browser account switching to a pottery studio ("Oak & Pine Ceramics") verifies zero cross-account leakage.
    - Hoisted `isSampleMode()` to top scope in `creator.js` and guarded DOM style access for headless harnesses.
  - **Track E: Research Cache Zero Debit & SQL Rollback Analysis:**
    - Verified route-level zero debit on cache hits in `tests/test_research_cache.py`: `/api/v1/daily-brief` returns `x-muse-cache: hit` and 0 spent; `/api/v1/competitors/ads` returns `is_cached: True` with 0 external API calls.
    - Verified per-account cache key isolation for competitor queries.
    - SQL Rollback Analysis: `supabase/migrations/research_cache_rollback.sql` uses `DROP TABLE IF EXISTS muse_private.research_cache CASCADE;`, which drops all cached records and dependent database objects. Migrations remain unapplied; runtime utilizes local filesystem JSON (`get_research_cache_dir()`).
  - **Full Quality Gate:**
    - `make check` passed cleanly: `523 passed, 2 skipped in 49.91s`. Zero paid model calls, zero live deployments, zero migrations applied.


