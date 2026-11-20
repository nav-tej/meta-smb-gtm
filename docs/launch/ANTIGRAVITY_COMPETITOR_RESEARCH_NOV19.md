# Antigravity (Gemini) Competitor Research & E2E Reliability Report — Nov 19, 2026

- **Branch:** `gemini/competitor-research-nov19`
- **Base Commit:** `01296b6` (`origin/claude/ux-gap-ad-loop-nov17`, includes `bf32ba2`)
- **Worktree:** `/tmp/muse-competitor-research` (isolated; Mac checkout `/Users/nav/meta-smb-gtm` untouched)
- **Boundaries:** `DEMO_MODE=true`, `META_MODEL_API_KEY=` (blank), `DEMO_KEY=` (blank); zero paid Muse calls, deploys, migrations, emails, auth/settings changes, or `.env` reads.

## Gate Results (Before & After)
- **Before-Edit Baseline (`01296b6`):**
  - `DEMO_MODE=true META_MODEL_API_KEY= DEMO_KEY= make PY=/Users/nav/meta-smb-gtm/.venv/bin check`
  - `ruff check .` passed, `ruff format --check .` clean (`263 files already formatted`), `pytest`: **636 passed, 2 skipped, 1 warning in 183.31s (0:03:03)** (2 skips require `@electric-sql/pglite`).
- **Task 1 Reliability Proof (10 Runs Each Under Parallel Full-Gate Load):**
  - Ran `tests/test_seller_memory_e2e.py::test_batch1_corrections_security_merge_drafts_and_handoff_e2e` and `tests/test_state_aware_copy.py::test_four_visitor_states_and_sample_freshness_e2e` 10 times each while `make check` ran concurrently:
  - `seller_memory`: **10/10 passed**
  - `state_aware_copy`: **10/10 passed**
  - Parallel full gate: **exit code 0** (`636 passed, 2 skipped, 1 warning in 178.41s`).
- **After-Edit Full Offline Gate (Tasks 1 + 2):**
  - `DEMO_MODE=true META_MODEL_API_KEY= DEMO_KEY= make PY=/Users/nav/meta-smb-gtm/.venv/bin check`
  - `ruff check .` passed, `ruff format --check .` clean (`264 files already formatted`), `pytest`: **640 passed, 2 skipped, 1 warning in 184.28s (0:03:04)**.

## Files Changed (Exclusive Write Scope)
- **Task 1 (Flaky E2E Stabilization):**
  - `tests/test_seller_memory_e2e.py`: Replaced fixed `wait_for_timeout` calls in `test_batch1_corrections_security_merge_drafts_and_handoff_e2e` with explicit `expect_response("/api/v1/seller-memory/recommend")` / `expect_response("/api/v1/seller-memory")`, merged-state `wait_for_function`, handoff `idea_id` waits, modal hidden wait, `ownerId === 'user-b'` wait, and route-hold polling. No assertions removed or weakened.
  - `tests/test_state_aware_copy.py`: Replaced `wait_for_timeout(300)` with `expect_response("**/api/v1/monitor**")`, `window.museModes?.isSampleMode?.() === true`, `#competitorSnapshotsNote` text check, and chip-set text `wait_for_function` conditions.
- **Task 2 (Services-Aware Competitor Research & Honest Ad Status):**
  - `src/models/intel.py`: Added `"services"` and `"case_studies"` to `UrlBucket`, added `BusinessType = Literal["products", "services", "both"]`, and added optional `business_type: BusinessType | None = None` on `CompetitorIntelRequest`.
  - `src/utils/sitemap.py`: Updated `classify_url_bucket` to classify `/services/`, `/consulting/`, `/advisory/`, `/solutions/`, `/offerings/`, `/capabilities/`, `/practices/` as `"services"` and `/case-studies/`, `/case-study/`, `/client-stories/`, `/customer-stories/`, `/success-stories/` as `"case_studies"`, without misfiling shop paths or artist `/portfolio/` pages.
  - `src/services/competitor_intel.py`: Added `"services"` and `"case_studies"` to `_PRIORITY_BUCKETS`, added `SERVICES_BATCH_ANALYSIS_SYSTEM_PROMPT`, `SERVICES_BRIEF_SYNTHESIS_SYSTEM_PROMPT`, `BOTH_BATCH_ANALYSIS_SYSTEM_PROMPT`, and `BOTH_BRIEF_SYNTHESIS_SYSTEM_PROMPT`, and threaded `business_type` through `CompetitorIntelService.analyze` -> `analyze_competitor` -> `build_brief` -> `analyze_url_batches`. When `business_type` is `None`, the exact original prompts are used unchanged and the response schema field names are preserved.
  - `src/api/static/index.html`:
    - Sends `business_type` alongside `seller_context` in live `POST /api/v1/analyze-competitors?live=true` requests from a seller's own workspace.
    - Updated `renderDiagnosticsAndAds()` so own workspaces never render hard-coded `artofsarabjitsingh.com` / `72 Artworks` / `FineArtAmerica` sample diagnostics.
    - Added `loadOwnCompetitorAdSignals()` and `formatAdStatusSummary()` to query `GET /api/v1/competitors/ads` per competitor in own workspace, lead with the public Meta Ad Library search link, display plain EU commercial API coverage wording (zero em-dashes), and show honest API status (`no_token`, signed out, `error`, `zero`, or `live` count + longest-running days) in `#metaAdsContainer` and `#sellerList`.
  - `tests/test_competitor_research_any_business.py`: Unit tests for service/shop URL bucketing, signal ranking, `business_type` prompt selection (`None` vs `"services"`), plus real Chromium E2E checks at `375×844` and `1440×844` for own services workspace (`"n Plus Alpha Consulting"`) and sample shop.

## Meta Ad Library API Coverage Finding (Confirmed & Cited)
- **Official Meta Documentation:** Meta Graph API Ad Library (`/ads_archive`) documentation ([developers.facebook.com/docs/graph-api/reference/ads_archive/](https://developers.facebook.com/docs/graph-api/reference/ads_archive/) and [facebook.com/ads/library/api/](https://www.facebook.com/ads/library/api/)) states for `ad_reached_countries`:
  > *"Search ALL or by ISO country code to return ads that reached specific countries or locations. Note: Ads that did not reach any location in the EU will only return if they are about social issues, elections or politics."*
- **Implication for `src/clients/ad_library.py` (reported, not modified):** `MetaAdLibraryClient.search_active_ads()` defaults `countries` to `("US", "CA", "GB")`. Non-political commercial ads that only targeted US/CA/GB do not return via Meta's `/ads_archive` API (they are visible only in the public Meta Ad Library web interface). The own-workspace UI now states this plainly and leads with the public Meta Ad Library link.

## Browser Verification (`375×844` and `1440×844`, Real Headless Chromium)
- **Own workspace (`"n Plus Alpha Consulting"`, `business_type: "services"`, competitor `"Acme Advisory"`):** Verified `#diagnosticsContainer` has zero `artofsarabjitsingh.com` / `72 Artworks` / `FineArtAmerica`, `#metaAdsContainer` shows the EU commercial coverage note + public Ad Library link + live API status (`1 active ad (API)`, `42d`) with zero em-dashes, live analyze POST sends `"business_type": "services"`, and zero horizontal overflow at `375px` and `1440px`.
- **Sample shop (`/?workspace=sample`):** Verified sample diagnostics and `[sample]` ad hooks remain intact with zero horizontal overflow at `375px` and `1440px`.

## Proposed Next Bounded Live Check (Requires Nav Approval)
- Run 1 live Muse Spark competitor analysis (`POST /api/v1/analyze-competitors?live=true`, `business_type="services"`) against one real `nplusalpha.com` consulting competitor after merging and deploying to Preview, to verify live prompt output quality and citation grounding on a real services sitemap (1 run).

## Not Verified
- Live paid Muse Spark calls, hosted Vercel preview deployment, live Meta Ad Library API responses with a configured `META_ADS_ACCESS_TOKEN`.

Ownership released
