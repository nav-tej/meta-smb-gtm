# Muse Growth Studio — Product Requirements Document (PRD)

**Status:** Derived from shipped codebase (`src/api/`, `src/services/`, `src/models/`, `data/`) + Revision 2 & Revision 3 (Tracks A–H)  
**Last Updated:** 2026-11-09  
**Evidence Labeling Rule:** Every metric, count, price, or claim in this PRD is explicitly tagged as **`[live]`** (derived from captured public web snapshots, deterministic Python calculations on those snapshots, or verified shipped code/routes), **`[sample]`** (saved demo fixtures, illustrative examples, or sample campaign rows), or **`[estimate]`** (modeled assumptions, unmeasured time savings, or unit-economics projections).

---

## 1. Problem & User Personas

### 1.1 The Problem
Small visual-product sellers—fine artists, printmakers, jewelers, ceramicists, and specialty makers—spend their working hours making physical work, fulfilling orders, and managing listings across fragmented marketplaces. Two product gaps keep existing AI and marketing tools from helping them grow:
1. **Insights do not turn into something you can see (`[live]` audit finding):** A ranked recommendation is just a line of text. The seller still has to pick an image, write the hook, format for Instagram/Facebook, and check how it compares to competitors.
2. **Signed-in users land on the demo shop instead of their own workspace (`[live]` audit finding):** After Google OAuth or email sign-up, the user lands on `/account` (`index.html`) showing the Sarabjit Singh demo workspace rather than an onboarding flow that ingests their own shop, confirms their social pages, and discovers their competitors.
3. **Research covers competitor catalogs only, without buyer voice, seller preferences, caching, or outcome ROI (`[live]` audit finding):** Recommendations cannot be tuned to a seller's experience level, channel access, or taste without spending paid runs, and sellers cannot log post results to see whether their subscription pays off.

### 1.2 Personas & Jobs-to-be-Done (JTBD)

#### Primary Persona: Solo Visual Artist / Multi-Marketplace Maker
- **Representative Anchor Seller:** **Art of Sarabjit Singh** (`artofsarabjitsingh.com` `[live]`), a San Francisco Bay Area Sikh and Punjabi heritage fine artist.
- **Active Channels (`[live]` public snapshots captured Nov 3, 2026):**
  - Own website: `https://www.artofsarabjitsingh.com/` (`24` sitemap pages indexed `[live]`).
  - Print-on-demand marketplaces: **Pixels** (`https://sarabjit-singh.pixels.com/`, preferred print storefront `[live]`) and **Fine Art America** (`https://fineartamerica.com/profiles/sarabjit-singh/art/paintings`, `72` paintings indexed across `9` curated series `[live]`, `$14–$22` print range `[live]`).
  - Originals marketplace: **Saatchi Art** (`https://www.saatchiart.com/sarabjitsingh` `[live]`).
  - Social channels: Instagram (`@artofsarabjitsingh` `[live]`) and Facebook (`facebook.com/ArtofSarabjitSingh` `[live]`).
  - Closed channel: **Etsy** (`Etsy · closed` `[live]` — recommendations must never instruct her to list on Etsy).
- **Direct Edition & Original Pricing:** `$75–$900` signed collector editions (`[sample]`); `$2,000–$4,000` original canvases (`[sample]`).
- **Core Jobs-to-be-Done:**
  1. *When I have 15 minutes between studio work and shipping*, help me see what similar artists are listing and charging (`$60–$2,500` at `SikhiArt.com` across `300` URLs `[live]`; `$14–$50` at `Gurinderpreet Kaur` across `70` FAA listings `[live]`; `$14–$24` at `Manjot Singh Sachdeva` across `105` FAA/Pixels listings `[live]`) so I know where my catalog has an opening.
  2. *When Muse suggests a growth move*, show me the exact Instagram/Facebook post it implies—staged with my artwork, my handle, and editable copy—or give me a copy-ready marketplace checklist so I can finish in one sitting.
  3. *When I log views, clicks, or orders*, show me honestly whether my posts and ad budget are paying off without inventing modeled revenue.

#### Secondary Persona: Growth-Stage Specialty Shop / Studio Manager Running Meta Ads
- **Profile:** Small home-decor, print, or heritage gift brand spending `$15–$75/day` (`[estimate]`) across 2–5 Meta Ads Manager ad sets (`[sample]` fixture: `$749.00` 14-day spend, `50` sales, `$2,848.00` revenue, `3.80x` blended ROAS `[sample]`).
- **Core Jobs-to-be-Done:**
  1. Upload a Meta Ads CSV export or connect shop URLs, detect fatigued ad sets (`7-day` ROAS drop `[live]` Python math), and reallocate daily budget to high-ROAS retargeting (`9.30x` ROAS, `$6.67` CPA in fixture `[sample]`) with zero net spend increase.
  2. Receive a Monday morning digest (`GET /digest`) summarizing competitor new listings, price changes, and one ready-to-post weekly creative.

---

## 2. The Four-Stage Growth Loop (Under 15 Minutes a Day)

| Stage | Anchor / Route | What the Seller Does | What "Done" Looks Like (< 15 min/day) | Time Budget (`[estimate]`) |
| :--- | :--- | :--- | :--- | :--- |
| **1. Research** | `/#loop-research`, `/welcome` (Step 1–3), `/digest` | Reviews watched competitors (`4` shops, `6` tracked catalog/collection pages `[live]`), price bars (`$14–$22` vs. `$60–$2,500` `[live]`), and buyer voice phrases (`Track C`). | Identifies `1` verified competitor gap or buyer question with cited URL/quote evidence. | `~3 min` `[estimate]` |
| **2. Create** | `/#loop-create`, `/today`, `/create` | Clicks **"Preview as post"** on an insight or opens `/today`; reviews staged artwork room scene (`muse-image-1.0` `[sample]`/`[live]`), tweaks headline/caption inline, switches placement (`4:5` Feed or `9:16` Story/Reel). | Downloads exact `1080×1350` or `1080×1920` PNG + copies caption, or saves to drafts. Nothing is auto-posted. | `~5 min` `[estimate]` |
| **3. Improve** | `/#loop-improve`, `#tab-intel`, `#tab-bids` | Triages the `5` ranked moves (`Accept`, `Done`, `Dismiss` with reason, `Adjust` with 140-char note) or copies a 3-title Pixels SEO checklist; optional CSV upload in Bid Advisor. | Marks `1` move **Done** in `muse.actions` (updating the `X of 5 moves done` progress strip) or dismisses misfits so Muse re-ranks immediately (`0` runs). | `~4 min` `[estimate]` |
| **4. Iterate** | `/#loop-iterate`, `/progress`, `/digest` | Logs yesterday's views, clicks, inquiries, or orders in 30 seconds (`Track F`) and subscribes to the Monday weekly digest (`Track G`). | Outcome saved to timeline; ROI card updates from logged revenue; Monday email queued with next cycle's top move. | `~2 min` `[estimate]` |

> **Estimated Time Saved Notice:** The homepage hero estimates `~12 hours` of manual competitor research and copywriting saved per full cycle (`~1.5 min` × `300` pages ≈ `7.5 h`, `~2.5 h` brief writing, `~2 h` post drafting `[estimate]`). This is explicitly labeled **`Estimated — not measured`** in both the UI and this PRD.

---

## 3. Feature & Route Inventory (Shipped Codebase)

Every route mounted in `src/api/main.py` and its feature routers (`src/api/*.py`), verified against automated tests (`423 passed, 2 skipped` `[live]`).

| Feature / Route | Method & Path | State (`live` / `sample` / `stub`) | Plan Gate | Runs Consumed | Evidence (File & Test) |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Customer Growth Portal** | `GET /`, `GET /portal`, `GET /account` | `live` UI shell + `sample` default fixtures (`data/demo/previews.json`, `presets.json`) | Demo / Free / Starter | `0` on load `[live]` | `src/api/main.py`, `src/api/static/index.html`, `tests/test_portal_demo.py`, `tests/test_ui_polish.py` |
| **Daily Growth Desk** | `GET /today`, `GET /api/v1/daily-brief` | `live` route + cached/saved brief from monitor snapshots (no model call) | Demo / Free / Starter | `0` runs (cached brief from saved snapshots) `[live]` | `src/api/daily_brief.py`, `src/api/static/today.html`, `tests/test_daily_brief.py` |
| **Guided Creator Studio** | `GET /create` | `live` 4-step studio UI backed by `/api/v1/generate-ads` | Demo (`sample`) / Free / Starter | `0` in demo; `1` run on live render `[live]` | `src/api/main.py`, `src/api/static/creator.html`, `tests/test_creator_studio.py` |
| **Weekly Market Digest Page** | `GET /digest`, `GET /api/v1/weekly-digest` | `live` snapshot diff engine over Nov 3 snapshots | Demo / Free / Starter | `0` `[live]` | `src/api/monitor.py`, `src/api/static/digest.html`, `tests/test_monitor_and_digest.py` |
| **Health & Readiness Checks** | `GET /health`, `GET /readiness`, `GET /api/v1/{health,readiness}` | `live` config introspection (never calls billed APIs) | Public | `0` `[live]` | `src/api/main.py`, `tests/test_readiness_and_budget.py` |
| **Saved Demo Presets** | `GET /api/v1/demo-presets` | `sample` workspace bundle (`data/demo/presets.json`) + `live` snapshot signals | Public | `0` `[live]` | `src/api/intel.py`, `tests/test_portal_demo.py` |
| **Competitor Intelligence Brief** | `POST /api/v1/analyze-competitors` | `sample` fixture in demo; `live` sitemap crawl + `muse-spark-1.3` when unlocked | Demo (`sample`) / Free (`3` trial runs) / Starter | `0` in demo; `1` run when `?live=true` `[live]` | `src/api/intel.py`, `src/services/competitor_intel.py`, `tests/test_competitor_intel.py` |
| **Seller Footprint Audit & Diagnostics** | `POST /api/v1/audit-seller` | `live` deterministic Python math across `72` artworks + `sample`/`live` LLM playbook | Demo / Free / Starter | `0` deterministic or demo; `1` run live LLM `[live]` | `src/api/intel.py`, `src/services/seller_audit.py`, `tests/test_portal_demo.py` |
| **Storefront & Socials Reference Crawl** | `POST /api/v1/ingest-storefront` | `live` HTTP/sitemap fetcher with SSRF & robots guardrails + saved profile fallback | Demo / Free / Starter | `0` (crawl is free `[live]`) | `src/api/intel.py`, `tests/test_portal_demo.py` |
| **Screenshot Vision Audit** | `POST /api/v1/audit-screenshot` | `sample` fixture in demo; `live` `muse-spark-1.3` vision when unlocked | Demo (`sample`) / Free / Starter | `0` in demo; `1` run when `?live=true` `[live]` | `src/api/intel.py`, `tests/test_portal_demo.py` |
| **Two-Phase Ad Creative Studio** | `POST /api/v1/generate-ads`, `GET /api/v1/creative-models`, `POST /api/v1/transcribe-voice` | `sample` cached brief & images in demo; `live` `muse-spark-1.3`, `muse-image-1.0`, `sam-3.1`, and optional local ComfyUI when unlocked | Demo (`sample`) / Free / Starter | `0` in demo; `1` run per live generation `[live]` | `src/api/creative.py`, `src/services/ad_creative.py`, `tests/test_ad_creative_and_social.py` |
| **Bid & Budget Advisor (+ CSV Upload)** | `POST /api/v1/bid-advice`, `POST /api/v1/bid-advice/csv` | `live` Python ROAS/CPA/trend anomaly math (`src/services/bid_advisor.py`) + `sample` 14-day campaign fixture | Demo / Free / Starter | `0` in demo/CSV math; `1` run with `?live=true` `[live]` | `src/api/bids.py`, `src/services/bid_advisor.py`, `tests/test_bid_advisor.py` |
| **Multi-Day Content Plan** | `POST /api/v1/content-plan` | `sample` plan in demo; `live` `muse-spark-1.3` when unlocked | Demo / Free / Starter | `0` in demo; `1` run live `[live]` | `src/api/content_plan.py`, `tests/test_content_plan.py` |
| **Product Reference Extractor** | `POST /api/v1/product-reference` | `live` HTML/meta parser + `sample` fallback | Demo / Free / Starter | `0` `[live]` | `src/api/product_reference.py`, `tests/test_product_reference.py` |
| **Competitor Target Discovery** | `POST /api/v1/research-targets`, `GET /api/v1/research-example` | `sample` targets in demo; `live` discovery when unlocked | Demo / Free / Starter | `0` in demo; `1` run live `[live]` | `src/api/research_targets.py`, `tests/test_research_targets.py` |
| **Competitor Snapshot Monitor** | `GET /api/v1/monitor`, `POST /api/v1/monitor` | `live` snapshot diffing (`data/snapshots/`) | Demo / Free / Starter | `0` `[live]` | `src/api/monitor.py`, `tests/test_monitor_and_digest.py` |
| **Digest Email Double Opt-In** | `GET /api/v1/digest/subscription`, `POST /api/v1/digest/subscribe`, `GET /api/v1/digest/confirm`, `GET/POST /api/v1/digest/unsubscribe`, `GET /api/v1/digest/send` | `live` HMAC token + Supabase storage + Resend email delivery | Public / Free / Starter | `0` `[live]` | `src/api/digest_email.py`, `tests/test_digest_email.py` |
| **Accounts, OAuth & Workspace Sync** | `GET /api/v1/account/me`, `POST /api/v1/account/{signup,signin,signout,session,oauth,recover,password}`, `GET /api/v1/account/oauth/google{/callback}`, `GET/PUT /api/v1/account/workspace` | `live` Supabase Auth + direct Google OAuth (`GOOGLE_CLIENT_ID`) + versioned workspace JSON | Free (`3` trial runs) / Starter | `0` `[live]` | `src/api/accounts.py`, `src/api/static/account.js`, `tests/test_account_ui.py`, `tests/test_accounts.py` |
| **Durable Media Storage Proxy** | `GET /api/v1/account/media/{asset}` | `live` Supabase Storage bucket proxy (`src/services/media_store.py`) | Free / Starter | `0` `[live]` | `src/api/media.py`, `tests/test_media_persistence.py` |
| **Run Credits & Usage Meter** | `GET /api/v1/credits`, `POST /api/v1/credits/{spend,add}` | `live` ledger in `src/services/credits.py` & `usage_meter.py` | Free (`3` runs) / Starter (`20`/mo) | Tracks runs `[live]` | `src/api/credits.py`, `tests/test_credits_and_pricing.py` |
| **Stripe Billing & Customer Portal** | `GET /api/v1/billing/status`, `POST /api/v1/billing/{checkout,portal,webhook}` | `live` Stripe Checkout + webhook signature verification | Starter (`$9/mo` annual, `$12/mo` monthly; Pro planned) | `0` `[live]` | `src/api/billing.py`, `tests/test_billing.py` |
| **Analytics Config & Legal Pages** | `GET /api/v1/analytics/config`, `GET /static/legal/{terms,privacy,refunds}.html` | `live` PostHog client config + static legal policies | Public | `0` `[live]` | `src/api/analytics.py`, `tests/test_analytics.py`, `tests/test_legal_pages.py` |

---

## 4. Homepage (`/`) Control-by-Control Truth Table (Appendix 1 Audit Verified in Chromium)

Every control in `src/api/static/index.html`, `src/api/static/muse-shell.js`, and `src/api/static/reco-actions.js`, plus every suspected dead/empty item from Appendix 1, verified in headless Chromium at `375px` and `1440px`.

| Control / Appendix 1 Item | Selector / Element | Target / Action | Works in Demo? | Works Signed In? | Verification Notes (`[live]` Chromium check) |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Topbar: Weekly digest** | `a.topbar-link[href="/digest"]` | Navigates to `/digest` | **Yes** (`0` runs) | **Yes** | Loads Monday digest page. |
| **Topbar: Plans & pricing** | `button[data-open-pricing]` | Opens `#musePricingModal` (`muse-shell.js`) | **Yes** (`0` runs) | **Yes** (wires to Stripe Checkout) | Shows Free (`3` runs), Starter (`$9/mo` yr / `$12/mo`; Pro planned). |
| **Topbar: Local tools** | `#openLocalEngineBtn` | Opens `#localEngineDialog.showModal()` | **Yes** (`0` runs) | **Yes** | Explains optional local ComfyUI (`127.0.0.1:8188`). |
| **Topbar: Shop / Account button** | `#openLoginBtn` + `account.js` | Opens `#loginDialog` / `#museAccountDialog` | **Yes** (`0` runs) | **Yes** | Switches demo shop (`Sample shop`) or opens Google/email sign-in. |
| **Hero: `Make today's post →`** | `#heroStartFreeBtn` | Navigates to `/today` | **Yes** (`0` runs) | **Yes** | Opens Daily Growth Desk. |
| **Hero: `See plans · from $9/mo`** | `.hero-btn-gold[data-open-pricing]` | Opens pricing dialog | **Yes** (`0` runs) | **Yes** | Same modal as topbar pricing button. |
| **Hero: `Explore the free demo ↓`** | `a.hero-btn-ghost[href="#journey"]` | Scrolls to `#journey` | **Yes** (`0` runs) | **Yes** | Smooth anchor jump. |
| **Hero: `▶ 20-second tour`** *(Appendix 1)* | `button[data-open-tour]` | Bound in `muse-shell.js` (`startTour()`) | **Yes** (`0` runs) | **Yes** | Not dead in JS: opens interactive 4-step spotlight tour across `#loop-research` → `#loop-iterate`. |
| **Research: `View full competitor research →`** *(Appendix 1)* | `#journeyResearch` | Calls `showSavedBrief()` → `openStep('tab-intel', 'compSummaryText')` | **Yes** (`0` runs) | **Yes** | Unhides `#workspaceDetail` and scrolls to brief. |
| **Research: `Re-check now`** | `#recheckBtn` | Bound in `index.html`; enabled by `refreshSellerButtons()` | **Yes** (`0` paid runs; reads saved snapshot) | **Yes** (`1` run live or cached) | Initial HTML has `disabled`, removed on `loadBriefCache()`. |
| **Research: `Analyze this seller →` (SikhiArt)** *(Appendix 1)* | `#journeyLoadBrief` | Calls `showSavedBrief()` | **Yes** (`0` runs) | **Yes** | Expands `#workspaceDetail` and highlights `SikhiArt.com` brief. |
| **Research: `Request analysis →` (x3 peer sellers)** *(Appendix 1)* | `#sellerList .js-live-brief` | Enabled by `refreshSellerButtons()`; calls `requestDemoBrief()` in demo or `requestBrief()` live | **Yes** (uses saved snapshot via `POST /api/v1/analyze-competitors`, `0` paid calls) | **Yes** (`1` run for live crawl or `0` on cache hit) | HTML starts `disabled` before JS runs; `refreshSellerButtons()` enables all 3 in demo mode. |
| **Research: `Add another competitor` form** | `#addCompetitorForm`, `#addCompetitorBtn` | Appends seller to `#sellerList` | **Yes** (`0` runs; adds to list as `Needs live server`) | **Yes** (`1` run for live crawl) | Button copy updated in Track A so demo (`0 runs`) vs. live (`1 run`) is explicit. |
| **Create: Saved Muse ad cards (`4` cards)** *(Appendix 1)* | `#adGallery .jr-ad` | Populated by `loadPresets()` → `renderAdGallery()`; opens `#adDialog` | **Yes** (`0` runs) | **Yes** | Only shows `"Loading saved Muse ads…"` before JS fetches `/api/v1/demo-presets`. |
| **Create: `Create your next post →`** | `#loop-create a[href="/create"]` | Navigates to `/create` | **Yes** (`0` runs) | **Yes** | Opens guided creator studio. |
| **Improve: 5 Ranked Ideas + `reco-actions.js`** | `#loop-improve .jr-recos > li` | Shows `Preview as post` / `Copy-ready checklist`, `Done`, `Dismiss`, plus `muse-shell.js` triage | **Yes** (`0` runs) | **Yes** (syncs to workspace) | Upgraded in Track B with 1:1 `PreviewSpec` and checklist dialog. |
| **Improve: `Do this in your Pixels shop`** *(Appendix 1)* | `.jr-reco-where` (Idea #4) | Static badge in original HTML; upgraded in Track B to open **Copy-ready checklist** | **Yes** (`0` runs) | **Yes** | Previously a non-interactive `<span class="jr-reco-where">`; Track B pairs it with a copy-ready 3-title checklist button. |
| **Improve: `Review budget strategy →`** *(Appendix 1)* | `#journeyBudget` | Calls `openStep('tab-bids', 'tab-bids')` | **Yes** (`0` runs) | **Yes** | Unhides `#workspaceDetail` and switches to Bid Advisor tab. |
| **Iterate: 3 Next-Cycle Cards** | `.jr-next-grid a` | Links to `/today`, `#loop-improve`, `#loop-research` | **Yes** (`0` runs) | **Yes** | All 3 navigate/scroll cleanly. |
| **Workspace Toggle** | `#toggleWorkspace` | Toggles `#workspaceDetail[hidden]` | **Yes** (`0` runs) | **Yes** | Expands/collapses the 4-tab full workspace. |
| **Intel: `Ingest My Shop & Socials`** | `#ingestStorefrontBtn` | `POST /api/v1/ingest-storefront` | **Yes** (`0` runs) | **Yes** (`0` runs) | Crawls public sitemap/pages and updates `#ingestResultBox`. |
| **Intel: `Audit IG / FB / Saatchi Screenshot`** *(Appendix 1)* | `label[for="screenshotFileInput"]`, `#screenshotFileInput` | `POST /api/v1/audit-screenshot` on file change | **Yes** (returns saved sample vision audit, `0` paid calls) | **Yes** (`1` run live vision) | Works on file selection; renders hooks & conversion gaps in `#ingestResultBox`. |
| **Intel: `Load Saved Competitor Brief`** *(Appendix 1)* | `#runCompBtn` | `POST /api/v1/analyze-competitors` | **Yes** (`0` runs) | **Yes** | Populates `#compSummaryText`, `#findingsContainer`, and `#insightsContainer`. |
| **Intel: `Refine` form & chips** *(Appendix 1)* | `#refineForm`, `[data-refine]` | Bound in `muse-shell.js` (`applyRefine()`) | **Yes** (`0` runs) | **Yes** (`0` runs) | Re-orders `#insightsContainer` and `.jr-recos` client-side and updates `#focusBanner` + `#memoryStrip`. |
| **Intel: `↻ Re-run` Diagnostics** *(Appendix 1)* | `#rerunDiagBtn` | Bound in `muse-shell.js` (`POST /api/v1/audit-seller`) | **Yes** (`0` runs) | **Yes** (`0` runs deterministic) | Re-computes Python storefront diagnostics across 72 artworks. |
| **Creative: `Pause Camera Glide` & `Preview Ambient Audio Hook`** *(Appendix 1)* | `#toggleReelMotionBtn`, `#playGalleryChimeBtn` | Toggles `.playing` on `#reelFrame`; synthesizes Web Audio API chord | **Yes** (`0` runs) | **Yes** (`0` runs) | Both work client-side inside `#tab-creative`. |
| **Creative: `Phase 1: Draft` & `Phase 2: Preview`** *(Appendix 1)* | `#draftBriefBtn`, `#renderCreativeBtn` | `POST /api/v1/generate-ads` (`draft=true` / `draft=false`) | **Yes** (`0` runs; reuses saved image with edited copy, explicitly stated in `#creativeStatusBanner`) | **Yes** (`1` run live) | Explicitly states on screen that Demo Phase 2 reuses an existing saved image. |
| **Bids: `Upload Meta Ads CSV` & `Review Sample Bid Advice`** | `#csvFileInput`, `#runBidsBtn` | `POST /api/v1/bid-advice/csv` & `POST /api/v1/bid-advice` | **Yes** (`0` runs) | **Yes** | Populates `#campaignTableBody`, `#reallocationsContainer`, `#audiencesContainer`. |
| **Export: Copy Weebly HTML / Download CSV / Copy JSON-LD** *(Appendix 1)* | `#copyWeeblyHtmlBtn`, `#downloadAdsCsvBtn`, `#copyJsonLdBtn` | Clipboard copy / Blob CSV download | **Yes** (`0` runs) | **Yes** | `#stripe-link-75` and `#stripe-link-125` are intentional template placeholders explained in `.card-sub`. |
| **Login Dialog: `Connect & Audit`** *(Appendix 1)* | `#connectCustomShopBtn` | Copies `#customShopUrl` to `#sellerWebsiteInput`, closes dialog, clicks `#ingestStorefrontBtn` | **Yes** (`0` runs) | **Yes** | Triggers live reference crawl and expands workspace when needed. |

---

## 5. Gaps & Requirements for Tracks H, B, D, F, E, C, G (Priority Order: A → H → B → D → F → E → C → G)

### 5.1 Track H — Signed-In Onboarding (`/welcome` + Honest Signed-In Workspace) — **P0 Priority**
- **Problem:** After Google OAuth or email sign-in, users land on `/account` (`index.html`) showing Sarabjit Singh's demo data as if it were their own shop.
- **Requirements:**
  1. **Post-Auth Routing:** After OAuth callback (`/api/v1/account/oauth/google/callback`, `/api/v1/account/oauth`) or sign-up/session, if `workspace.onboarding.completed_at` is empty, redirect to `/welcome`; otherwise redirect to `/`. Signed-in users never see Sarabjit's demo shop as if it were theirs. The Sarabjit demo remains reachable from the shop switcher explicitly labeled **"Sample shop"**.
  2. **4-Step Skippable, Resumable Flow (`/welcome` — `welcome.html`, `welcome.js`, `welcome.css`):**
     - **Step 1 — Your shop (`0` runs):** Single URL/domain field (accepts bare domain like `myshop.com`) + optional additional marketplace URLs. Calls `POST /api/v1/ingest-storefront` and displays real crawl proof only (e.g., *"Found N pages/products, prices $X to $Y"* `[live]`).
     - **Step 2 — Your socials (`0` runs):** Suggests Instagram, Facebook, Pinterest, and TikTok handles extracted strictly from the seller's crawled pages (links, meta tags, JSON-LD `sameAs`). Each handle is a chip the seller confirms, edits, or removes, plus manual add. Never asserts a handle not found on their pages.
     - **Step 3 — Your competitors (`1` run disclosed upfront, or `0` runs manual):** Suggests 4–6 competitors via `POST /api/v1/research-targets` with a one-line reason and public URL. Discloses *"Costs 1 run · X runs left"* before calling discovery/analysis. If the account has `0` runs (or declines), lets the seller type competitor URLs manually and continue for `0` runs.
     - **Step 4 — How you work (`0` runs, skippable):** Collects Track D `SellerPreferences` (`experience`, `access`, `minutes_per_week`, `taste`, `research_focus`).
     - **Completion Screen:** Shows *"Building your workspace"* progress, offers the weekly digest pre-filled with their watchlist, sets `workspace.onboarding.completed_at`, and lands on `/` with their own workspace data.
  3. **Persistent State:** `workspace.onboarding = { step, shop_urls, socials[], competitors[], preferences_version, completed_at, skipped[] }` persisted via `GET/PUT /api/v1/account/workspace` so closing the tab resumes at the exact step on any device.
  4. **Honest Empty States on `/` for Signed-In Accounts:** When a signed-in user views their own workspace on `/`, every section (`Watchlist`, `Research`, `Create`, `Improve`, `Full Workspace`) renders their ingested shop name, confirmed socials, price range, and chosen competitors—or a clean empty state with a single button to add missing data. Zero Sarabjit sample numbers appear on a real account unless the user explicitly switches to **"Sample shop"**.
  5. **PostHog Funnel Events (Privacy-Safe):** `onboarding_started`, `onboarding_step_completed {step}`, `onboarding_skipped {step}`, `onboarding_completed {has_socials, competitor_count, used_run}` (never sends raw URLs or social handles).

### 5.2 Track B — Insight-to-Ad Previews (`PreviewSpec` + Interactive Preview & Checklist Modal)
- **Requirements:**
  - Add `PreviewSpec` and `PreviewEvidence` to `src/models/creative.py`:
    `PreviewSpec { insight_id, source, placement, headline, caption, cta, image_ref, evidence: [{label, url, kind: live|sample}] }` plus checklist support (`kind: "post" | "checklist"`, `checklist_items`) and competitor comparison pattern (`competitor_pattern`).
  - Create `data/demo/previews.json` mapping 1:1 to every homepage ranked idea (`#loop-improve`), competitor brief insight (`#insightsContainer`), weekly digest item (`/digest`), and buyer insight (`Track C`) using saved Muse images (`0` model calls).
  - Replace cycled sample thumbnails with the specific `PreviewSpec` per idea. Non-post ideas (such as Idea #4 *"Add 'for your home' to three titles"*) get a **Copy-ready checklist** instead of a fake ad preview.
  - Interactive Preview Dialog: inline headline & caption editing, placement switcher (`instagram_feed` `1080×1350`, `instagram_story` `1080×1920`, `facebook_feed`), generic seller frame (`@artofsarabjitsingh`, no Meta logos), **"Why this"** evidence chip (`[live]` / `[sample]`), side-by-side **Compare view** with competitor ad pattern card (labeled `Illustrative — sample` when `data/research/ad_library_capture.json` is absent), **Edit in Studio** (`/today` or `/create` preloaded), **Download PNG** (exact `1080×1350` or `1080×1920` via client canvas + headline truncation warning), **Save to drafts**, and **Mark done**.

### 5.3 Track D — Seller Preferences ("Tell Muse how to research")
- **Requirements:**
  - `SellerPreferences` in `src/models/seller.py` (`experience`, `access`, `taste`, `research_focus` max 300 chars, `watch`, `version`), persisted in `GET/PUT /api/v1/account/workspace` (or device-local in demo).
  - Deterministic ranking & filtering (`src/services/seller_preferences.py`): new sellers never see budget reallocation first; sellers without price control never see pricing moves as do-it-now; one-tap dismiss reasons (`not_my_style`, `too_advanced`, `no_access`, `already_tried`) adapt difficulty and channel visibility; refine chips write `research_focus` and re-rank from cache with `0` runs.
  - Every idea displays a difficulty tag, time estimate (`[estimate]`), and *"Why you are seeing this"*.

### 5.4 Track F — Progress Over Time & Honest ROI (`/progress`)
- **Requirements:**
  - `Outcome` model (`src/models/progress.py`): `reco_id` / `preview_id`, `posted_at`, `channel`, `reach`, `clicks`, `orders`, `revenue`, `ad_spend`, `minutes_spent`, `source` (`manual` | `csv`).
  - 30-second **"Log result"** action on done ideas + `/progress` timeline page (`src/api/progress.py`, `src/api/static/progress.html`) + `"Your week"` block in `/digest`.
  - **Strict ROI Honesty Rule:** Only logged revenue counts. No modeled revenue. Empty state reads: **`"Log one result to see ROI"`**.

### 5.5 Track E — Content-Addressed Research Cache (`src/services/research_cache.py`)
- **Requirements:**
  - `supabase/migrations/research_cache.sql` (migration file only, not applied remotely) + `src/services/research_cache.py` (`sha256` key over account/demo, normalized URLs, flow, model ID, prompt version).
  - TTLs: competitor crawl `7 days`, daily brief `24 hours`, ad previews `no expiry`. Cache hits cost `0` runs and display *"Last checked Nov 3 · Refresh (1 run)"*.

### 5.6 Track C — Buyer Research Module (`BuyerInsight` + `data/research/buyer_voice.json`)
- **Requirements:**
  - `BuyerInsight { segment, motivation, occasion, price_band, phrases[], sources[] }` in `src/models/intel.py`.
  - Reads `data/research/buyer_voice.json` (with clearly labeled `[sample]` fallback when Hermes capture is not yet present) and renders **"Your buyers"** panel in Research + phrase bank in `/today` and Track B `"Why this"` chips.
  - `supabase/migrations/buyer_polls.sql` written as a migration file for review (not applied).

### 5.7 Track G — Weekly Digest as the Habit Loop
- **Requirements:**
  - Inline digest signup prompt at value moments on `/` (after opening a preview or marking an idea done), showing a preview of the real Monday email before asking for an email address, wired to `/api/v1/digest/subscribe` and `/api/v1/digest/confirm`.
  - Frequency (`weekly` / `biweekly`) and topic/competitor controls on `/digest`.

---

## 6. Product Metrics & PostHog Event Mapping

All client events pass through `window.museAnalytics.track(eventName, props)` (`src/api/static/muse-shell.js` / `src/api/ analytics.py`), which no-ops cleanly when PostHog is unset or blocked.

| Funnel Stage / Metric | Definition | PostHog Event Name | Status | Key Properties (Privacy-Safe) |
| :--- | :--- | :--- | :--- | :--- |
| **Activation (Demo Exploration)** | Visitor opens an insight-to-ad preview or tour on `/` | `reco_preview_open`, `preview_open` | `reco_preview_open` shipped (`[live]`); `preview_open` added in Track B | `{ insight_id, placement, source, mode }` |
| **Demo → Signup Conversion** | Visitor creates an account or signs in via Google OAuth | `account_signup`, `account_signin` | Shipped (`[live]`) | `{ method: "google" \| "email" }` |
| **Signed-In Onboarding Funnel** | New account progresses through `/welcome` steps 1–4 | `onboarding_started`, `onboarding_step_completed`, `onboarding_skipped`, `onboarding_completed` | Added in Track H | `{ step, has_socials, competitor_count, used_run }` *(never sends URLs or handles)* |
| **Habit Loop (Digest Signup)** | Seller sees inline digest prompt at a value moment, subscribes, and confirms email | `digest_prompt_shown`, `digest_subscribed`, `digest_confirmed` | Added in Track G | `{ trigger: "preview_open" \| "reco_done", frequency }` |
| **Weekly Active Sellers (WAS)** | Signed-in or returning seller completes at least 1 move or logs 1 outcome in 7 days | `reco_action_triage`, `outcome_logged` | Triage shipped (`[live]`); `outcome_logged` in Track F | `{ status: "done" \| "dismiss", reason, channel }` |
| **Runs per Account & Paid Conversion** | Trial account exhausts `3` free runs and opens/completes Stripe Checkout | `pricing_open`, `checkout_started` | Shipped (`[live]`) | `{ plan: "starter" \| "pro", billing_interval }` |

---

## 7. Pricing, Run Limits & Explicit Non-Goals

### 7.1 Pricing & Limits as Shipped (`src/api/billing.py`, `src/config.py`)
| Plan Tier | Price (`[live]`) | Run Allowance (`[live]`) | What Costs `0` Runs (`[live]`) | What Costs `1` Run (`[live]`) |
| :--- | :--- | :--- | :--- | :--- |
| **Free Demo (Logged Out)** | `$0` | `0` live runs; unlimited saved fixtures | Viewing sample shop (`Art of Sarabjit Singh`), opening all `PreviewSpec` modals, downloading sample PNGs, CSV bid math, weekly digest view. | N/A (live model endpoints blocked in demo mode). |
| **Free Account (Verified Email / Google OAuth)** | `$0` | `3` lifetime trial runs (`TRIAL_RUNS=3`) | `/welcome` Step 1 storefront crawl (`POST /api/v1/ingest-storefront`), Step 2 social handle extraction, Step 4 preferences, cache hits, re-ranking, outcome logging. | `/welcome` Step 3 live competitor discovery/analysis, live `analyze-competitors?live=true`, live `generate-ads`, live `audit-screenshot`. |
| **Starter Plan** | `$9/mo` billed yearly (`$108/yr`) or `$12/mo` billed monthly | `20` live runs / month | All free-account zero-run actions + cached briefs + weekly digest warmup. | Any uncached live Muse Spark 1.3 or Muse Image 1.0 generation. |
| **Pro Plan** | `$29/mo` | `100` live runs / month | All zero-run actions + priority cache warmup. | Any uncached live Muse Spark 1.3 or Muse Image 1.0 generation. |

### 7.2 Explicit Non-Goals
1. **No Auto-Posting to Social Accounts (`[live]`):** Muse never publishes directly to a seller's Instagram, Facebook, TikTok, or Pinterest account. Sellers download the PNG/MP4 and copy the caption to post on their own schedule.
2. **No Automated Ad Buying or Budget Mutation (`[live]`):** Muse never connects to Meta Ads Manager write APIs to spend money or alter live campaign budgets. Bid Advisor outputs human-reviewed recommendations and a downloadable CSV planning pack.
3. **No Unlabeled Fabricated Claims (`[live]`):** Muse never presents illustrative ad hooks as real Meta Ad Library captures, never invents exhibition credentials, and never displays modeled revenue as actual ROI.

---

## 8. Phased Roadmap & Open Questions for Nav

### 8.1 Phased Roadmap (`Now` → `Next` → `Later`)
- **Now (Current Sprint — Branches `prd-research-previews` & `prefs-cache-progress`):**
  1. **Track A:** Ship `docs/product/PRD.md` and the 4 homepage copy accuracy fixes in `src/api/static/index.html`.
  2. **Track H:** Ship `/welcome` 4-step signed-in onboarding (`welcome.html`, `welcome.js`, `welcome.css`), social handle extraction from crawled pages, post-auth redirect for new accounts, `"Sample shop"` switcher label, and honest signed-in empty states on `/`.
  3. **Track B:** Ship `PreviewSpec` & `PreviewEvidence` (`src/models/creative.py`), `data/demo/previews.json`, interactive post preview & copy-ready checklist modal across `/` and `/digest`, compare view, and client canvas PNG export.
  4. **Track D:** Ship `SellerPreferences`, dismiss reason chips (`not_my_style`, `too_advanced`, `no_access`, `already_tried`), difficulty/time tags, and zero-run re-ranking.
  5. **Track F:** Ship `Outcome` model, 30s `"Log result"` flow, `/progress` page, and strict `"Log one result to see ROI"` empty state.
  6. **Track E, C, G:** Ship `research_cache.py` + migration file, `BuyerInsight` + `buyer_voice.json` + migration file, and inline weekly digest habit prompt on `/` + frequency/topic controls on `/digest`.
- **Next (Post-Merge & Hermes Research Integration):**
  1. Merge Hermes captures (`data/research/buyer_voice.json`, `data/research/ad_library_capture.json`, `data/research/placement_specs.json`) to replace `[sample]` buyer/ad fixtures with `[live]` public citations.
  2. Apply reviewed Supabase migrations (`research_cache.sql`, `buyer_polls.sql`) to production Supabase after Nav/Claude sign-off.
  3. Ship P1 shareable 3-question buyer poll link for sellers.
- **Later (P2 Horizon):**
  1. Automated review mining on the seller's own marketplace listings (Pixels, Fine Art America, Saatchi Art).
  2. Search autocomplete phrase tracking across Google, Pinterest, and marketplace search bars.
  3. Closed-loop attribution linking specific `PreviewSpec` variants to logged `Outcome` lift across cohorts.

### 8.2 Open Questions for Nav
1. **Artist Verification of Exhibition & Anniversary Copy:** Can Sarabjit confirm the exact wording and years she prefers for the *Triton Museum*, *Kala Sangam UK*, and *550th Anniversary* references in the default sample shop ads so we can promote them from `[sample — artist to verify]` to `[live]` verified artist bio facts?
2. **Step 3 Onboarding Run Policy for 0-Run Accounts:** When a signed-in user has `0` runs remaining during `/welcome` Step 3, we allow free manual competitor URL entry; should we also allow `1` complimentary onboarding competitor crawl per new verified domain even if trial runs were spent in `/today`?
3. **Supabase Migration Application Timing:** Should `supabase/migrations/research_cache.sql` and `supabase/migrations/buyer_polls.sql` be applied before or after merging `prd-research-previews` and `prefs-cache-progress` into `main`?

---

## 9. Track I: Steerable Research & Directive Injection Guardrails

### 9.1 Purpose & User Need
Sellers need to redirect research in their own words (e.g., *"Look at why SikhiArt dropped prints to $45"*, *"Find gift ideas under $50"* or *"Show me easier moves for solo makers"*) without triggering expensive or risky model calls. Free-text inputs from users or scraped from public competitor websites are untrusted and must never be concatenated into model system instructions.

### 9.2 Data Contract & Schema (`src/models/directive.py`)
Free text (capped at 300 characters `[live]`) is parsed by `parse_research_directive()` into a typed, deterministic Pydantic model `ResearchDirective` `[live]`:
- `focus`: Literal (`pricing`, `products`, `posting`, `gifting`, `seo`, `ads`, `audience`)
- `competitors_add`: list of normalized domain/URLs (at most 6 `[live]`)
- `competitors_remove`: list of normalized domain/URLs
- `price_band`: optional `{ min: float, max: float }` (`0 <= min <= max`)
- `channels`: list of valid channels (`instagram`, `facebook`, `pixels`, `etsy`, `pinterest`, `saatchi`)
- `timeframe_days`: Literal (`7`, `30`, `90`)
- `tone_note`: string (max 80 chars `[live]`)
- `exclude_topics`: list of strings (max 40 chars each `[live]`)

*Implementation Boundary:* Directive parsing is strictly syntax-only pattern extraction. It performs no DNS lookups or network fetches. Any future crawler fetching from candidate URLs must pass them through `src.utils.sitemap.validate_safe_url` at fetch time. Directives confirmed in the UI are currently saved locally on the seller's device (`muse.directive`).

### 9.3 Prompt Injection Safety Rules (`[live]` enforced)
1. **No Instruction Concatenation:** Seller free text and crawled page text are never concatenated into instruction text. Raw input is validated and parsed server-side; only typed schema fields reach the pipeline.
2. **Refusal of Exploits & Sensitive Scrapes:** Requests attempting system prompt overrides (`"ignore previous instructions"`), tool hijacking, credential harvesting, or scraping behind private logins / personal individuals are immediately rejected with an explanatory HTTP 400 response (`[live]`).
3. **Escaped Output & Verified Links:** Any link in output must match crawled competitor URLs or the seller's own registered domain.
4. **Suggestions Without Model Calls:** 4 state-driven suggestion chips ("Why $59.99 entry", "Easier moves", "Gifts under $50", "Weekly post ideas") are generated deterministically (`0` runs `[live]`). Re-ranking from cache is free (`0` runs).

---

## 10. Track J: Seller Brand Voice & Blader/Humanizer Pass

### 10.1 Purpose & Tone Fidelity
AI-generated copy often defaults to generic corporate buzzwords or inflated, dramatic tropes. Track J enforces that all generated captions, headlines, and digest blurbs mirror the seller's actual voice and undergo a deterministic lint-and-suggest pass adhering to the [blader/humanizer](https://github.com/blader/humanizer) guidelines before the seller sees them.

### 10.2 Voice Profile Contract (`VoiceProfile`)
- Built from the seller's verified content: listing descriptions, captions, and about pages captured during the Track H crawl (`[live]`), plus up to 3 "inspired by" URLs.
- Extracts stylistic traits: average sentence length, formality, emoji usage, recurring vocabulary, and words to avoid (`[live]`).
- Plagiarism & Similarity Protection: Inspired-by URLs influence tone only; generated copy is checked against inspiration text to prevent sentence copying (`[live]`).

### 10.3 Deterministic Blader/Humanizer Lint-and-Suggest Rules (`src/utils/humanizer.py` `[live]`)
Copy is evaluated via `lint_humanizer()` with suggestions from `suggest_humanizer_clean()`:
1. **Non-Destructive Review:** Suggestions are presented for seller review rather than silently mutating text. The seller can accept or reject proposed edits.
2. **Protected Context:** Quoted titles, artwork titles (e.g. *Revolutionary Light*), product nouns (e.g. *handwoven tapestry*), and paragraph formatting are protected and never mutated.
3. **Banned AI Vocabulary Flagged:** Recommends alternatives for stock AI filler words: *delve, embark, elevate, testament, beacon, bespoke, meticulously, quintessential, vibrant, realm, navigate, unlock*.
4. **No Rule-of-Three Padding:** Catches and flags synthetic triads ("passion, dedication, and craft").
5. **No Inflated Numeric Claims:** Ad copy cannot invent awards, years of history, or unverified claims.
6. **Short, Plain Sentences:** Flags sentences over 28 words; encourages punchy visual copy under 18 words.

### 10.4 "Sounds Like You?" Feedback Widget
On preview dialogs (`/#loop-create`, `/today`, `/create`), sellers can rate copy with 👍 / 👎 and click one-tap adjusters: **"More casual"**, **"More formal"**, or **"Shorter"**. Feedback is recorded locally on device and logged via `voice_feedback_submitted` PostHog events to tune voice preferences without spending a model run (`[live]`).

---

## 11. Track K: Retention Targets, Weekly Active Sellers & 30-Day Lift

### 11.1 North-Star Metric: Weekly Active Sellers (WAS)
A seller is defined as a **Weekly Active Seller (WAS)** in a 7-day window if and only if they execute at least one meaningful business action:
- `Accept` or mark `Done` on a recommendation
- Download or export a post (`PreviewSpec` canvas PNG)
- Log a verified business outcome on `/progress`
- Confirm a steerable research directive

*Note: Merely opening the homepage or viewing the email digest does NOT count toward WAS.*

### 11.2 Baseline Truth vs. Targets (`[live]` vs. `[estimate]`)
| Metric | Current Baseline (`[live]`) | 90-Day Target (`[estimate]`) | Measurement / Event Source |
| :--- | :--- | :--- | :--- |
| **Activation Rate** | `16.6%` (1 signup / 6 visitors `[live]`) | `>= 40%` onboarded + 1st post exported within 24h | `onboarding_completed` + `preview_export_png` |
| **Habit Retention** | `0%` (no returning cohort yet `[live]`) | `>= 35%` active in 3 of first 4 weeks | WAS cohort tracking |
| **WAS / WAU Ratio** | `N/A` (`[sample]`) | `>= 50%` of weekly visitors perform an action | PostHog weekly active action filter |
| **Monthly ROI Lift** | `0` logged outcomes (`[live]`) | `>= 1` logged result / month showing positive ROAS | `/progress` timeline logs |

*Implementation Note:* On `/progress`, outcomes are partitioned by verified account owner on the device (`muse.outcomes.<user_id>`). Revenue is labeled "Logged on this device", plan cost reflects the Starter monthly baseline ($12/mo), and ROI display requires at least 1 logged result (showing `—` instead of an invented negative return when moves = 0).

### 11.3 14-Day Free Trial Roadmap & 30-Day Lift Measurement
Per Nav's decision (Nov 10, 2026), the free trial is **14 days**, designed to establish the weekly growth habit and provide immediate value without upfront card requirements:
- **Day 0 (Setup):** 4-step onboarding (`/welcome`), workspace creation (`1` run), baseline capture (optional: followers, monthly orders).
- **Days 1–3 (First Action):** Top recommendation previewed and exported; day-1 email prompt if no post exported.
- **Day 7 (Weekly Rhythm):** First Monday digest received with one pre-filled steerable research question; second move completed.
- **Days 8–12 (Optimization):** Research directive steered from cache (`0` runs); first post outcome logged.
- **Day 12 (Two-Week Milestone):** In-app "Your First Two Weeks" summary showing moves completed, posts exported, and competitor changes caught.
- **Day 14 (Trial Expiration):** Paid plan prompt ($9/mo Starter). If not upgraded, workspace remains readable and digest pauses with a one-time notice.
- **Day 30 (Lift Report):** For paid accounts, "Your First 30 Days" report calculates actual lift against the Day-0 baseline. If no baseline or result was logged, Muse states honestly what is missing—no modeled revenue is ever fabricated.
