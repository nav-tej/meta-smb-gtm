# Multi-Network Ad Account Connections & Write Safety Specification

**Author:** Argon (Gemini 4 Argon, in Antigravity)
**Date:** 2026-11-19 (Updated Phase 1a: live version audit & Meta read-only connection)
**Branch:** `gemini/meta-connect-nov19` (base `9b103ef` on `origin/claude/ux-gap-ad-loop-nov17`)
**Status:**
- **Approved by Nav (2026-11-19):** (1) Build direct `httpx` adapters in-house (no third-party vendor holds seller tokens); (2) Encrypted token storage in `muse_private.ad_account_connections` per Section 4.3; (3) Phase order **Meta → Google Ads → TikTok** (with X and LinkedIn deferred).
- **Pending Nav approval before Phase 1b:** Section 5 Write Safety Model. Nothing in Phase 0 or Phase 1a writes to an ad account.

> **Citation policy (strict):** `(accessed 2026-11-19)` or `(accessed 2026-11-20)` appears **only** on official pages and repository license files that were directly opened and read in these tasks:
> - `https://developers.facebook.com/documentation/facebook-login/facebook-login-for-business` (accessed 2026-11-20)
> - `https://developers.facebook.com/docs/facebook-login/guides/advanced/manual-flow` (accessed 2026-11-20)
> - `https://developers.facebook.com/docs/facebook-login/guides/access-tokens/get-long-lived` (accessed 2026-11-20)
> - `https://developers.facebook.com/docs/graph-api/changelog/versions` (accessed 2026-11-19)
> - `https://developers.facebook.com/documentation/ads-commerce/marketing-api/overview/versioning` (accessed 2026-11-19)
> - `https://developers.facebook.com/docs/marketing-api/changelog` (accessed 2026-11-19)
> - `https://developers.facebook.com/docs/marketing-api/get-started/authorization` (accessed 2026-11-19)
> - `https://developers.meta.com/blog/updates-to-ads-management-standard-access-feature` (accessed 2026-11-19)
> - `https://developers.facebook.com/docs/marketing-api/overview/rate-limiting` (accessed 2026-11-19)
> - `https://developers.google.com/google-ads/api/docs/sunset-dates` (accessed 2026-11-19)
> - `https://developers.google.com/google-ads/api/docs/access-levels` (accessed 2026-11-19)
> - `https://developers.google.com/google-ads/api/docs/best-practices/test-accounts` (accessed 2026-11-19)
> - `https://developers.google.com/google-ads/api/docs/mutating/overview` (accessed 2026-11-19)
> - `https://learn.microsoft.com/en-us/linkedin/marketing/integrations/marketing-tiers` (accessed 2026-11-19)
> - `https://learn.microsoft.com/en-us/linkedin/marketing/versioning` (accessed 2026-11-19)
> - `https://docs.x.com/x-ads-api/fundamentals/sandbox` (accessed 2026-11-19)
> - `https://docs.x.com/x-ads-api/getting-started/step-by-step-guide` (accessed 2026-11-19)
> - Raw `LICENSE` files on GitHub for `facebook/facebook-python-business-sdk`, `googleads/google-ads-python`, `xdevplatform/twitter-python-ads-sdk`, `linkedin-developers/linkedin-api-python-client`, `RoyAzran/mcp-ads`, `pipeboard-co/meta-ads-mcp`, `byadsco/meta-ads-mcp`, and `bengoism/agent-ads` (accessed 2026-11-19).
>
> Everything else not verified by opening an official page is explicitly marked **[Unconfirmed]**.

---

## 1. Platform Matrix

### 1.1 Summary Comparison Table

| Dimension | Meta (Facebook + Instagram) | Google Ads | TikTok Ads | X (Twitter) Ads | LinkedIn Ads |
|---|---|---|---|---|---|
| **API & Version Policy** | Graph / Marketing API (`https://graph.facebook.com/{version}/`, configured via `META_GRAPH_API_VERSION`, defaulting to `v27.0`). [Marketing API Versioning](https://developers.facebook.com/documentation/ads-commerce/marketing-api/overview/versioning) (accessed 2026-11-19) states *"The current version of the Marketing API is v27.0"* and notes Marketing API versions release roughly every 4 months with at least a 90-day grace period and auto-version upgrade for non-breaking endpoints. [Marketing API Changelog](https://developers.facebook.com/docs/marketing-api/changelog) (accessed 2026-11-19) lists `v27.0` (released November 4, 2026) and `v26.0` (released July 29, 2026). [Graph API Versions](https://developers.facebook.com/docs/graph-api/changelog/versions) (accessed 2026-11-19) lists Graph API `v26.0` (released July 29, 2026) and `v25.0` (released February 18, 2026, Graph expiration July 29, 2028), and shows in its Marketing API table that `v21.0` expired September 9, 2025, `v22.0` expired February 19, 2026, `v23.0` expired June 9, 2026, and `v24.0` expired October 6, 2026. | Google Ads API (`https://googleads.googleapis.com/v26/`). [Google Ads API Deprecation and Sunset](https://developers.google.com/google-ads/api/docs/sunset-dates) (accessed 2026-11-19) lists **`v26 (Latest)`** (released October 14, 2026; minor releases `v26.1` on October 28, 2026 and `v26.2` on November 11, 2026; sunset **November 2027**), alongside active versions `v25` (released July 22, 2026; sunset August 2027), `v24` (released April 22, 2026; sunset May 2027), and `v23` (released January 28, 2026; sunset February 2027). Older versions (`v22` and earlier, including `v18`) are already sunset and fail requests. | TikTok Marketing API (`https://business-api.tiktok.com/open_api/v1.3/`) (**[Unconfirmed]** — TikTok developer portal pages were not opened directly in this task). | X Ads API (`https://ads-api.x.com/12/`). Documented under [X Ads API Step-by-Step Guide](https://docs.x.com/x-ads-api/getting-started/step-by-step-guide) (accessed 2026-11-19); exact version sunset schedule **[Unconfirmed]**. | LinkedIn Marketing API (`https://api.linkedin.com/rest/`). Monthly `LinkedIn-Version: YYYYMM` header; each version supported minimum 1 year ([LinkedIn API Versioning](https://learn.microsoft.com/en-us/linkedin/marketing/versioning), accessed 2026-11-19). |
| **OAuth Flow & Exact Scopes** | OAuth 2.0 authorization code flow (`https://www.facebook.com/{version}/dialog/oauth`). With **Facebook Login for Business**, a Login Configuration ID (`config_id`, set via `META_LOGIN_CONFIG_ID`) replaces `scope` on the login dialog — Meta's manual login flow docs state *"include your configuration ID as an optional parameter (although `scope` can still be included, we recommend that you do not use it): `config_id=<CONFIG_ID>`"* ([Facebook Login for Business](https://developers.facebook.com/documentation/facebook-login/facebook-login-for-business), accessed 2026-11-20). When `META_LOGIN_CONFIG_ID` is unset, Muse falls back to `scope=ads_read`. A **User access token** configuration with `response_type=code` returns an authorization `code` that `exchange_meta_oauth_code()` exchanges at `/v27.0/oauth/access_token` and extends to a ~60-day long-lived User access token via `grant_type=fb_exchange_token` ([Manually Build a Login Flow](https://developers.facebook.com/docs/facebook-login/guides/advanced/manual-flow), [Long-Lived Access Tokens](https://developers.facebook.com/docs/facebook-login/guides/access-tokens/get-long-lived), accessed 2026-11-20; [Meta Marketing API Authorization](https://developers.facebook.com/docs/marketing-api/get-started/authorization), accessed 2026-11-19). | OAuth 2.0 authorization code flow with scope `https://www.googleapis.com/auth/adwords`, plus `developer-token` header and optional `login-customer-id` (MCC) header ([Google Ads API Access Levels](https://developers.google.com/google-ads/api/docs/access-levels), accessed 2026-11-19; exact OAuth screen details **[Unconfirmed]**). | Custom OAuth 2.0 advertiser redirect (`https://business-api.tiktok.com/portal/auth`) exchanging `auth_code` at `/open_api/v1.3/oauth2/access_token/` (**[Unconfirmed]**). | 3-legged OAuth 1.0a user-context signing is documented in [X Ads API Step-by-Step Guide](https://docs.x.com/x-ads-api/getting-started/step-by-step-guide) (accessed 2026-11-19). OAuth 2.0 PKCE support on Ads API endpoints is **[Unconfirmed]**. | OAuth 2.0 3-legged authorization code flow with `r_ads`, `r_ads_reporting`, and `rw_ads` scopes ([LinkedIn Marketing Tiers](https://learn.microsoft.com/en-us/linkedin/marketing/integrations/marketing-tiers), accessed 2026-11-19; token TTLs **[Unconfirmed]**). |
| **Access Tiers & Review Steps** | Standard permission access works for accounts owned/administered by app role members; managing external sellers' ad accounts requires **Advanced Access** via App Review. Separately, rate-limit capacity is governed by the **Marketing API Access Tier** (renamed May 4, 2026 from *Ads Management Standard Access*): starts at **Limited Access**, upgrades to **Full Access** ([Update to Ads Management Standard Access](https://developers.meta.com/blog/updates-to-ads-management-standard-access-feature), accessed 2026-11-19). | Tied to a Google Cloud project (`muse-growth`) and a Manager (MCC) account: **Test Access** (test accounts only) → **Explorer Access** (2,880 operations/day) → **Basic Access** (15,000 operations/day) → **Standard Access** (unlimited operations/day) ([Google Ads API Access Levels](https://developers.google.com/google-ads/api/docs/access-levels), accessed 2026-11-19). | Marketing API developer app registration and platform review at `business-api.tiktok.com` (**[Unconfirmed]**). | Developer app + X Ads API access application form ([X Ads API Step-by-Step Guide](https://docs.x.com/x-ads-api/getting-started/step-by-step-guide), accessed 2026-11-19; 3-business-day review turnaround **[Unconfirmed]**). | **Development Tier** (uncapped reads, max 5 edited ad accounts, 1 test ad account) → **Standard Tier** (unlimited accounts; requires review form and demo video of campaign creation/editing) ([LinkedIn Marketing Tiers](https://learn.microsoft.com/en-us/linkedin/marketing/integrations/marketing-tiers), accessed 2026-11-19). |
| **Business Verification** | Required in Meta Business Suite before App Review for Advanced Access ([Meta Marketing API Authorization](https://developers.facebook.com/docs/marketing-api/get-started/authorization), accessed 2026-11-19). | Required for Basic/Standard developer token upgrade and Google Cloud OAuth verification ([Google Ads API Access Levels](https://developers.google.com/google-ads/api/docs/access-levels), accessed 2026-11-19). | TikTok Business Verification in Developer Portal (**[Unconfirmed]**). | Validated X advertiser account on `ads.x.com` ([X Ads API Step-by-Step Guide](https://docs.x.com/x-ads-api/getting-started/step-by-step-guide), accessed 2026-11-19). | Associated LinkedIn Company Page approved by a Page Super Admin ([LinkedIn Marketing Tiers](https://learn.microsoft.com/en-us/linkedin/marketing/integrations/marketing-tiers), accessed 2026-11-19). |
| **Test / Sandbox Accounts** | Sandbox ad accounts exist in App Dashboard; whether sandbox mode supports creating all ad/creative types is **[Unconfirmed]** (third-party reports note creative limitations). | **Test Manager Account** + child test accounts: full mutate support, zero ad serving or billing, reporting returns zero impressions ([Google Ads Test Accounts](https://developers.google.com/google-ads/api/docs/best-practices/test-accounts), accessed 2026-11-19). | Sandbox environment `sandbox-ads.tiktok.com` (**[Unconfirmed]**). | Sandbox host `ads-api-sandbox.x.com` documented at [X Ads API Sandbox](https://docs.x.com/x-ads-api/fundamentals/sandbox) (accessed 2026-11-19). | **Development Tier** includes creating **1 Test Ad Account** ([LinkedIn Marketing Tiers](https://learn.microsoft.com/en-us/linkedin/marketing/integrations/marketing-tiers), accessed 2026-11-19). |
| **What Can Be Created by API** | Campaigns (`/act_{id}/campaigns`), Ad Sets (`/act_{id}/adsets`), Ads (`/act_{id}/ads`), Ad Creatives (`/act_{id}/adcreatives`), Ad Images/Videos, Audiences ([Marketing API Versioning](https://developers.facebook.com/documentation/ads-commerce/marketing-api/overview/versioning), accessed 2026-11-19). | Campaign Budgets, Campaigns, Ad Groups, Ads, Assets, UserLists via `GoogleAdsService.Mutate` and resource mutate services ([Google Ads Mutate Overview](https://developers.google.com/google-ads/api/docs/mutating/overview), accessed 2026-11-19). | Campaigns, Ad Groups, Ads, Media uploads, Audiences (**[Unconfirmed]**). | Campaigns, Line Items, Promoted Tweets, Media Creatives, Custom Audiences ([X Ads API Step-by-Step Guide](https://docs.x.com/x-ads-api/getting-started/step-by-step-guide), accessed 2026-11-19). | Campaign Groups, Campaigns, Creatives, Media, Audiences ([LinkedIn Marketing Tiers](https://learn.microsoft.com/en-us/linkedin/marketing/integrations/marketing-tiers), accessed 2026-11-19). |
| **Validate-Only / Dry-Run Support** | `execution_options=["validate_only"]` on campaign/adset/ad mutations (**[Unconfirmed]** — individual ad-campaign-group reference page was not opened directly in this task). | **Yes.** `validate_only: true` on `Mutate` requests validates syntax and policy without executing changes ([Google Ads Mutate Overview](https://developers.google.com/google-ads/api/docs/mutating/overview), accessed 2026-11-19). | **[Unconfirmed]** (no documented `validate_only` flag confirmed). | **[Unconfirmed]** (rely on `ads-api-sandbox.x.com` or paused status). | **[Unconfirmed]** (rely on Development Tier test ad account or `DRAFT`/`PAUSED` status). |
| **Rate Limits** | Governed by **Marketing API Access Tier** (Limited vs. Full Access) and rolling ad-account/app usage headers ([Meta Marketing API Rate Limiting](https://developers.facebook.com/docs/marketing-api/overview/rate-limiting), accessed 2026-11-19). | Explorer: **2,880 operations/day**; Basic: **15,000 operations/day**; Standard: **unlimited operations/day** ([Google Ads API Access Levels](https://developers.google.com/google-ads/api/docs/access-levels), accessed 2026-11-19). | Sandbox and production QPS/QPD limits **[Unconfirmed]**. | Per-endpoint rate limit headers (`x-rate-limit-limit`, `x-rate-limit-remaining`, `x-rate-limit-reset`) (**[Unconfirmed]**). | Daily UTC application and member quotas shown in Developer Portal (**[Unconfirmed]**). |
| **Official Client & License** | [`facebook/facebook-python-business-sdk`](https://raw.githubusercontent.com/facebook/facebook-python-business-sdk/main/LICENSE) (accessed 2026-11-19) — **Custom Meta Platform License** (*"for use in connection with the web services and APIs provided by Facebook"*; not an OSI open-source license, incompatible with pure AGPL-3.0 redistribution). | [`googleads/google-ads-python`](https://raw.githubusercontent.com/googleads/google-ads-python/main/LICENSE) (accessed 2026-11-19) — **Apache License 2.0** (requires Python client `>=34.0.0` for `v26` per [Google Ads Sunset Dates](https://developers.google.com/google-ads/api/docs/sunset-dates), accessed 2026-11-19). | `tiktok/tiktok-business-api-sdk` — License file at `/main/LICENSE` and `/master/LICENSE` returned HTTP 404 when opened directly (**[Unconfirmed]**). | [`xdevplatform/twitter-python-ads-sdk`](https://raw.githubusercontent.com/xdevplatform/twitter-python-ads-sdk/master/LICENSE) (accessed 2026-11-19) — **MIT License** (Copyright 2015 Twitter, Inc.; legacy/unmaintained). | [`linkedin-developers/linkedin-api-python-client`](https://raw.githubusercontent.com/linkedin-developers/linkedin-api-python-client/main/LICENSE.md) (accessed 2026-11-19) — **LinkedIn API Development Software License Agreement** (proprietary custom terms, not OSI-approved). |

### 1.2 Why Muse Uses `httpx.AsyncClient` Instead of Vendor Python SDKs
Per `AGENTS.md` section 6 ("Async by default for anything doing I/O. One shared `httpx.AsyncClient` per client module, with explicit timeouts. No `requests`."):
1. **License hygiene (AGPL-3.0):** `facebook-python-business-sdk` and `linkedin-api-python-client` use custom platform-restricted licenses ([Meta LICENSE](https://raw.githubusercontent.com/facebook/facebook-python-business-sdk/main/LICENSE), [LinkedIn LICENSE.md](https://raw.githubusercontent.com/linkedin-developers/linkedin-api-python-client/main/LICENSE.md), accessed 2026-11-19). Calling the versioned REST endpoints directly via `httpx` avoids bundling non-OSI SDK code.
2. **Async & serverless footprint:** `facebook-python-business-sdk` and `twitter-python-ads-sdk` are synchronous. `google-ads-python` pulls in `grpcio` and generated protobufs, whereas Google Ads API `v26` exposes a JSON REST interface (`POST https://googleads.googleapis.com/v26/customers/{customerId}/googleAds:searchStream`) directly callable with `httpx`.
3. **Configurable API version:** `src/config.py` defines `meta_graph_api_version: str = "v27.0"` (`META_GRAPH_API_VERSION=v27.0` in `.env.example`), so version upgrades never require editing client code.

---

## 2. Open-Source & Commercial Unified API Survey

### 2.1 Open-Source Projects Audited

| Repository | License (Verified 2026-11-19) | Networks Covered | Architecture & Reuse Verdict |
|---|---|---|---|
| [`RoyAzran/mcp-ads`](https://raw.githubusercontent.com/RoyAzran/mcp-ads/main/LICENSE) (accessed 2026-11-19) | **MIT License** (`Copyright (c) 2026 MCP Ads contributors`, AGPL-3.0 compatible) | Google Ads, Meta, TikTok, LinkedIn, Microsoft Ads, Snapchat | Enforces a **"created objects start paused"** invariant and uses `cryptography.fernet.Fernet` for encrypted token storage. Our `src/services/ad_connections.py` uses `MultiFernet` key rotation following this pattern. |
| [`pipeboard-co/meta-ads-mcp`](https://raw.githubusercontent.com/pipeboard-co/meta-ads-mcp/main/LICENSE) (accessed 2026-11-19) | **Business Source License 1.1 (BUSL-1.1)** | Meta (Facebook + Instagram) | **Do not copy code.** BUSL-1.1 is incompatible with AGPL-3.0 SaaS distribution. |
| [`byadsco/meta-ads-mcp`](https://raw.githubusercontent.com/byadsco/meta-ads-mcp/main/LICENSE) (accessed 2026-11-19) | **MIT License** (`Copyright (c) 2025 ByAds — Santiago Bastidas`) | Meta (Facebook + Instagram) | TypeScript MCP server; no Python code needed. |
| [`bengoism/agent-ads`](https://raw.githubusercontent.com/bengoism/agent-ads/main/LICENSE) (accessed 2026-11-19) | **MIT License** (`Copyright (c) 2026 bengoism`, AGPL-3.0 compatible) | Meta, Google Ads, TikTok, X, LinkedIn, Pinterest (read-only CLI) | Rust CLI; useful reference for cross-network metric names, no code copied. |

### 2.2 Commercial Unified APIs Considered
- **Unified.to** and **Zernio** (**[Unconfirmed]** — vendor pricing/feature pages not opened directly in this task) provide commercial multi-network ad aggregation, but require a third-party vendor to hold or proxy sellers' OAuth tokens.

### 2.3 Build vs. Vendor Decision (Approved by Nav, 2026-11-19)
**Approved decision:** Build direct `httpx` adapters in-house (phase order **Meta → Google Ads → TikTok**), keeping seller OAuth tokens encrypted inside Muse's own `muse_private.ad_account_connections` table with `MultiFernet` (`AD_TOKEN_ENCRYPTION_KEY`) and zero third-party token intermediaries.

---

## 3. What Nav Has to Do on Each Network (Ordered by Approved Phase Plan)

> **Boundary confirmation:** Argon has **not** created any apps, submitted any forms, accepted any terms, or touched any network, Supabase, or Vercel console.

### Track 1: Meta (Facebook & Instagram) — *App Exists (`1113987174851049`); Remaining Setup Before Turning Flag On*
- **Already completed on November 19:**
  - Meta App **"Muse Growth Studio"** (App ID `1113987174851049`) exists in development mode with use case *"Measure ad performance data with Marketing API"* and **Facebook Login for Business** added.
  - **Valid OAuth Redirect URIs** are registered with Strict Mode on for production (`https://meta-smb-gtm.vercel.app/api/v1/ad-accounts/meta/callback`) and the protected preview (`https://muse-preview-nav.vercel.app/api/v1/ad-accounts/meta/callback`).
  - `META_APP_ID` and `META_APP_SECRET` are already set in Vercel (Production and Preview).
  - No business portfolio is connected (never connect, name, or reference any other business portfolio on Nav's account).
- **Remaining steps for Nav (in order):**
  1. **Create a Facebook Login for Business Configuration (`config_id`):**
     Per [Facebook Login for Business — Get started](https://developers.facebook.com/documentation/facebook-login/facebook-login-for-business) (accessed 2026-11-20):
     - In the Meta App Dashboard for **Muse Growth Studio** (`1113987174851049`), open **Facebook Login for Business > Configurations** in the left menu and click **+ Create configuration** (or **Create from template**).
     - **Name:** Enter a configuration name (e.g., `Muse Read-Only Ads`).
     - **Access token type:** Choose **User access token** (and 60-day expiration if prompted). With a User access token configuration, users log in with their personal Facebook account and no business portfolio is required ([Facebook Login for Business](https://developers.facebook.com/documentation/facebook-login/facebook-login-for-business), accessed 2026-11-20).
     - **Assets to request:** Select **Ad Accounts** only (if an asset step is shown; do not select Pages, Catalogs, or Business Portfolios).
     - **Permissions:** Select **`ads_read` only**, then click **Create** and copy the resulting **Configuration ID**.
  2. **Set `META_LOGIN_CONFIG_ID` and `AD_TOKEN_ENCRYPTION_KEY` in Vercel:**
     - Add `META_LOGIN_CONFIG_ID=<configuration_id>` in Vercel (Preview and Production).
     - Generate a Fernet key (`python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`) and set `AD_TOKEN_ENCRYPTION_KEY` in Vercel (Preview and Production).
  3. **Apply the Phase 1a Supabase Migration:**
     - Run `supabase/migrations/ad_account_connections.sql` in the Supabase SQL Editor (rollback script is at `supabase/migrations/ad_account_connections_rollback.sql`).
  4. **Enable `AD_CONNECT_ENABLED=true` on Preview First:**
     - Set `AD_CONNECT_ENABLED=true` on Preview (`https://muse-preview-nav.vercel.app`) first and test connecting an ad account owned by a user with a role on App `1113987174851049` (works immediately in Development Mode with Standard Access to `ads_read`).
  5. **App Review for External Sellers (Later, Before Opening to Public Sellers):**
     - Complete Business Verification and submit App Review for **Advanced Access** to `ads_read` (and `public_profile`, which Meta's Facebook Login for Business FAQ notes requires Advanced Access before a Facebook Login for Business app goes live for external users; [Facebook Login for Business FAQs](https://developers.facebook.com/documentation/facebook-login/facebook-login-for-business), accessed 2026-11-20).

### Track 2: Google Ads — *Phase 2*
1. **Create a Google Ads Manager (MCC) Account** and link existing Google Cloud project `muse-growth` in **Admin → API Center** to obtain a **Test Access** developer token immediately ([Google Ads API Access Levels](https://developers.google.com/google-ads/api/docs/access-levels), accessed 2026-11-19).
2. **Create a Google Ads Test Manager Account** for zero-spend testing against `v26` ([Google Ads Test Accounts](https://developers.google.com/google-ads/api/docs/best-practices/test-accounts), accessed 2026-11-19).
3. **Apply for Basic Access (15,000 operations/day)** and complete Google Cloud OAuth verification for scope `https://www.googleapis.com/auth/adwords`.

### Track 3: TikTok Marketing API — *Phase 3*
1. Register at `https://business-api.tiktok.com/portal`, complete Business Verification, and submit a Marketing API App with redirect URI `https://meta-smb-gtm.vercel.app/api/v1/ad-accounts/tiktok/callback` and `https://muse-preview-nav.vercel.app/api/v1/ad-accounts/tiktok/callback`.

### Track 4 & Track 5: X Ads & LinkedIn Ads — *Phase 4 (Deferred)*
1. **X Ads:** Create developer app at `developer.x.com` and submit the Ads API access form ([X Ads API Step-by-Step Guide](https://docs.x.com/x-ads-api/getting-started/step-by-step-guide), accessed 2026-11-19).
2. **LinkedIn Ads:** Create developer app linked to company page, request **Development Tier** (1 test ad account, max 5 edited ad accounts), and submit demo video for **Standard Tier** ([LinkedIn Marketing Tiers](https://learn.microsoft.com/en-us/linkedin/marketing/integrations/marketing-tiers), accessed 2026-11-19).

---

## 4. Architecture Implemented in Phase 1a

Following `AGENTS.md` sections 4, 6, and 10, Phase 1a follows the 3-layer separation (**routes → services → clients**) behind `AD_CONNECT_ENABLED=false`:

```
                      ┌─────────────────────────────────────────────┐
                      │         FastAPI (src/api/ad_accounts.py)    │
                      │  /api/v1/ad-accounts/meta/{connect,callback,│
                      │   accounts,insights,disconnect}             │
                      │  (Mounted only when AD_CONNECT_ENABLED=true)│
                      └──────────────────────┬──────────────────────┘
                                             │
            ┌────────────────────────────────▼────────────────────────────────┐
            │                         src/services/                           │
            │  ad_connections.py   (MultiFernet vault, user-bound HMAC state, │
            │                       service_role Supabase RPCs)               │
            │  ad_insights.py      (AdInsightRow -> CampaignPerformance)      │
            └──────┬───────────────────────────────────────────────────┬──────┘
                   │                                                   │
     ┌─────────────▼────────────────┐                   ┌──────────────▼─────────────┐
     │ src/clients/ad_networks/     │                   │ src/clients/supabase.py    │
     │ base.py + meta.py            │                   │ (service_role RPC adapter) │
     │ (Graph API META_GRAPH_API_   │                   └────────────────────────────┘
     │  VERSION, httpx read-only)   │
     └──────────────────────────────┘
```

### 4.1 Read-Only Routes (`src/api/ad_accounts.py`)
Registered in `src/api/main.py` only when `AD_CONNECT_ENABLED=true` (returns HTTP `404` when `AD_CONNECT_ENABLED=false`). Every endpoint requires a signed-in, email-verified Muse seller session (`resolve_account(request, response, require_verified=True)`):
1. `GET /api/v1/ad-accounts/meta/connect` & `POST /api/v1/ad-accounts/meta/connect`:
   - Generates a 10-minute HMAC-SHA256 signed state token (`sign_meta_oauth_state`) bound to `account.user_id` and sets the `HttpOnly`, `SameSite=Lax` cookie `muse_ad_oauth_state`.
   - Builds the Facebook Login for Business dialog URL (`https://www.facebook.com/{meta_graph_api_version}/dialog/oauth`) redirecting to `{base_url}/api/v1/ad-accounts/meta/callback`. When `META_LOGIN_CONFIG_ID` is set, sends `config_id` and omits `scope`; when unset, sends `scope=ads_read`.
2. `GET /api/v1/ad-accounts/meta/callback`:
   - Never renders a raw JSON error page to a seller. A signed-out or unverified seller arriving at `/callback` is redirected (`302`) to `/?ad_connect_error=signin_required#tab-bids` with the state cookie cleared.
   - Verifies that the query `state` matches the `muse_ad_oauth_state` cookie, has a valid HMAC signature, is within the 10-minute expiry window, and belongs to the currently authenticated `account.user_id`. On any error (`error=access_denied`, tampered state, expired state, cross-user state, or upstream error), clears `muse_ad_oauth_state` and redirects (`302`) to `/?ad_connect_error=<code>#tab-bids` using a fixed allowlist of codes (`cancelled`, `expired_state`, `wrong_account`, `invalid_state`, `no_ad_accounts`, `signin_required`, `connect_failed`), never free text.
   - On success, exchanges `code` for a short-lived token and then exchanges that token for a 60-day long-lived User access token (`grant_type=fb_exchange_token`) over `httpx` (`exchange_meta_oauth_code`), fetches the seller's ad accounts (`GET /{version}/me/adaccounts`), encrypts the token with `MultiFernet` (`AD_TOKEN_ENCRYPTION_KEY`), saves each connection via `muse_ad_connection_upsert`, clears `muse_ad_oauth_state`, and redirects to `/?ad_connect=meta&accounts=N#tab-bids`.
3. `GET /api/v1/ad-accounts/meta/accounts`:
   - Calls `muse_ad_connection_list` for `account.user_id` and returns account metadata (`external_account_id`, `account_name`, `currency`, `timezone_name`, `status`, `key_version`, `last_synced_at`). Never returns tokens or ciphertexts.
4. `GET /api/v1/ad-accounts/meta/insights` & `POST /api/v1/ad-accounts/meta/insights`:
   - Loads and decrypts the connection for `(account.user_id, account_id)` via `muse_ad_connection_get` (returns `404` if the account belongs to another seller).
   - Runs `MetaAdsReadClient.fetch_campaign_insights` for the requested date range and maps rows into `CampaignPerformance` via `src/services/ad_insights.py`.
   - If Meta returns error code `190` (`AdNetworkAuthError`), marks the connection `status='expired'` in Supabase and returns HTTP `401` with `{"code": "meta_token_expired", "reconnect_required": true}` so `#tab-bids` prompts the seller to reconnect.
5. `POST /api/v1/ad-accounts/meta/disconnect` & `DELETE /api/v1/ad-accounts/meta/disconnect`:
   - Calls `muse_ad_connection_disconnect` scoped to `(account.user_id, account_id)`, deleting the row and its encrypted token ciphertext (returns `404` if another seller attempts to disconnect an account they do not own).

### 4.2 Token Storage SQL (`supabase/migrations/ad_account_connections.sql`)
- Written in `supabase/migrations/ad_account_connections.sql` with rollback in `supabase/migrations/ad_account_connections_rollback.sql` (connections table and `service_role`-only RPCs `muse_ad_connection_upsert`, `muse_ad_connection_list`, `muse_ad_connection_get`, `muse_ad_connection_set_status`, `muse_ad_connection_disconnect`).
- The write audit log table (`muse_private.ad_account_audit_log`) remains proposed for Phase 1b when write operations are built.

---

## 5. Safety Model for Future Writes (Phase 1b — Requires Nav's Explicit Approval)

No write methods exist in Phase 0 or Phase 1a. Before any code that mutates an ad account is written in Phase 1b, Nav must approve these seven technical guardrails:
1. **Read-Only First (`access_level = 'read_only'`):** Separate opt-in and independent server flag `AD_WRITE_ENABLED=false`.
2. **Mandatory Dry-Run (`validate_only`) Where Supported:** Execute Google Ads `validate_only=True` (and Meta `execution_options=["validate_only"]` once verified against a sandbox account) during preview before any live write.
3. **Preview-and-Confirm Contract:** Server-signed `WritePreviewToken` locking exact `external_account_id`, `daily_budget_cents`, `currency`, `start_date`, `end_date`, and `after_state` SHA-256 digest.
4. **All Created Objects Start `PAUSED`:** Hardcoded `status="PAUSED"` (`operation_status="DISABLE"` on TikTok) at the client adapter layer.
5. **Separate Activation Step:** Seller activates drafts in native Ads Manager in Phase 1b.
6. **Per-Account Daily Spend Cap:** Enforced in Python and SQL (`daily_spend_cap_cents`, default `$50.00/day`).
7. **Immutable Audit Log & Kill Switch:** Append-only `muse_private.ad_account_audit_log` + instant env-var kill switch.

---

## 6. How It Plugs Into Muse

1. **Bid Advisor (`#tab-bids` in `src/api/static/index.html`):**
   - When `/api/v1/readiness` reports `ad_connect_enabled: false` (default), `#metaConnectBar` stays hidden and `#tab-bids` is unchanged.
   - When `ad_connect_enabled: true`, `#tab-bids` displays `#metaConnectBar` with the **"Connect Meta Ads (read-only)"** button, the connected-account `<select id="metaAdAccountSelect">` picker, **"Load Connected Insights"**, and **"Disconnect"**.
   - `/api/v1/ad-accounts/meta/insights` returns a `CampaignPerformance` payload directly compatible with `POST /api/v1/bid-advice` and `bid_advisor.compute_metrics()` without editing `src/services/bid_advisor.py`.
2. **Guided Ad Preparation (`/first-ad`, Phase 1b):** Will offer *"Create as a paused draft in Meta Ads Manager"* once Section 5 is approved.
3. **Ad Creative Studio (`/create`, Phase 1b):** Will offer uploading generated creatives to `/act_{id}/adimages` as draft creatives once Section 5 is approved.

---

## 7. Phased Rollout Plan (Approved Order: Meta → Google Ads → TikTok)

| Phase | Scope | Status | What Nav Needs to Do |
|---|---|---|---|
| **Phase 0** | Multi-network spec + offline `MetaAdsReadClient` (`httpx`) + `ad_insights.py` mapper | Merged (`259645e`) | Completed (Decisions 1, 3, 4 approved 2026-11-19). |
| **Phase 1a** | Meta read-only OAuth (`ads_read`), `MultiFernet` encrypted storage, `/api/v1/ad-accounts/meta/*` routes, `#tab-bids` UI behind `AD_CONNECT_ENABLED=false` | Built offline in `gemini/meta-connect-nov19` | 1. Create Meta App & register redirect URIs (`https://meta-smb-gtm.vercel.app/api/v1/ad-accounts/meta/callback` and `https://muse-preview-nav.vercel.app/api/v1/ad-accounts/meta/callback`).<br>2. Apply `supabase/migrations/ad_account_connections.sql`.<br>3. Set `AD_TOKEN_ENCRYPTION_KEY`, `META_APP_ID`, `META_APP_SECRET`, `META_GRAPH_API_VERSION=v27.0`, and `AD_CONNECT_ENABLED=true`. |
| **Phase 1b** | Meta paused draft creation (`/first-ad`) & creative upload (`/create`) behind `AD_WRITE_ENABLED=false` | Planned | 1. Approve Section 5 Write Safety Model.<br>2. Complete Meta Business Verification + `ads_management` App Review. |
| **Phase 2** | Google Ads (`v26` REST API) read-only insights + `validate_only: true` paused drafts | Planned | 1. Create Google Ads MCC + Test Manager account.<br>2. Link Cloud project `muse-growth` for Developer Token and apply for Basic Access. |
| **Phase 3** | TikTok Ads (`v1.3`) read-only insights + paused drafts | Planned | Register at `business-api.tiktok.com`, complete Business Verification, and submit Marketing API App. |
| **Phase 4** | X Ads & LinkedIn Ads | Deferred | Only start if seller demand justifies review overhead. |
