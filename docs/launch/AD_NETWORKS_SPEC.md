# Multi-Network Ad Account Connections & Write Safety Specification

**Author:** Argon (Gemini 4 Argon, in Antigravity)
**Date:** 2026-11-19
**Branch:** `gemini/ad-networks-nov19` (base `01296b6` on `origin/claude/ux-gap-ad-loop-nov17`)
**Status:** Design specification + read-only offline Meta slice behind `AD_CONNECT_ENABLED=false`. Write operations require explicit sign-off from Nav on Section 5 before any mutating code is written.

> **Citation policy:** Every factual claim below links to an official vendor or repository URL with `(accessed 2026-11-19)`. Claims reported by third parties or not verifiable on a first-party documentation page are explicitly marked **[Unconfirmed in official docs as of 2026-11-19]**.

---

## 1. Platform Matrix

### 1.1 Summary Comparison Table

| Dimension | Meta (Facebook + Instagram) | Google Ads | TikTok Ads | X (Twitter) Ads | LinkedIn Ads |
|---|---|---|---|---|---|
| **API & Version Policy** | Graph / Marketing API (`https://graph.facebook.com/v21.0/`). Quarterly versions; each version is supported for at least 2 years ([Meta Graph API Changelog](https://developers.facebook.com/docs/graph-api/changelog), accessed 2026-11-19). | Google Ads API (`https://googleads.googleapis.com/v18/`). ~3 major releases/year; each major version is sunset ~1 year after release ([Google Ads API Sunset Dates](https://developers.google.com/google-ads/api/docs/sunset-dates), accessed 2026-11-19). | TikTok Marketing API (`https://business-api.tiktok.com/open_api/v1.3/`). Versioned in path (`v1.3`); legacy `v1.2` deprecated ([TikTok Business API Reference](https://business-api.tiktok.com/portal/docs), accessed 2026-11-19). | X Ads API (`https://ads-api.x.com/12/`). Major version in URL path; legacy versions supported ~12 months after successor launch ([X Ads API Fundamentals](https://docs.x.com/x-ads-api/fundamentals/versioning), accessed 2026-11-19). | LinkedIn Marketing API (`https://api.linkedin.com/rest/`). Monthly `LinkedIn-Version: YYYYMM` header; each version supported minimum 1 year ([LinkedIn API Versioning](https://learn.microsoft.com/en-us/linkedin/marketing/versioning), accessed 2026-11-19). |
| **OAuth Flow & Exact Scopes** | OAuth 2.0 authorization code flow (`https://www.facebook.com/v21.0/dialog/oauth`). Read: `ads_read`. Write: `ads_management`. Business asset discovery: `business_management`. Short-lived user token (1–2h) exchanged for long-lived token (60 days) or System User token ([Meta Marketing API Authorization](https://developers.facebook.com/docs/marketing-api/get-started/authorization), accessed 2026-11-19). | OAuth 2.0 authorization code flow (`access_type=offline`, `prompt=consent`) with single scope `https://www.googleapis.com/auth/adwords`, plus `developer-token` header and optional `login-customer-id` (MCC) header ([Google Ads API OAuth Cloud Console](https://developers.google.com/google-ads/api/docs/oauth/cloud-project), accessed 2026-11-19). | Custom OAuth 2.0 advertiser redirect (`https://business-api.tiktok.com/portal/auth`). Numerical/checkbox permission groups configured on the app (Ad Account Management, Ads Management, Audience Management, Reporting, Creative Management). Returns `access_token` via `/open_api/v1.3/oauth2/access_token/` ([TikTok Marketing API Authentication](https://business-api.tiktok.com/portal/docs?id=1738373164380162), accessed 2026-11-19). | 3-legged OAuth 1.0a (`oauth/request_token` → `oauth/authorize` → `oauth/access_token` with HMAC-SHA1 signing) is the primary documented mechanism ([X Ads API Authentication](https://docs.x.com/x-ads-api/getting-started/step-by-step-guide), accessed 2026-11-19). OAuth 2.0 PKCE with `ads.read`/`ads.write` scopes is **[Unconfirmed in official docs as of 2026-11-19]** across all Ads API endpoints. | OAuth 2.0 3-legged authorization code flow (`https://www.linkedin.com/oauth/v2/authorization`). Read: `r_ads`, `r_ads_reporting`. Write: `rw_ads`. Access token valid 60 days; programmatic refresh token valid 365 days ([LinkedIn Marketing Authentication](https://learn.microsoft.com/en-us/linkedin/shared/authentication/authorization-code-flow), accessed 2026-11-19). |
| **Access Tiers & Review Steps** | **Standard Access** on permissions (`ads_read`, `ads_management`) works immediately for accounts owned/administered by app role members. Managing external sellers' ad accounts requires **Advanced Access** via App Review (screencast + reviewer instructions). Separately, rate-limit quota is governed by the **Marketing API Access Tier** (renamed from *Ads Management Standard Access*): starts at **Limited Access**, upgrades to **Full Access** after >=15 days of activity and <15% error rate ([Updates to Ads Management Standard Access Feature](https://developers.meta.com/blog/updates-to-ads-management-standard-access-feature), accessed 2026-11-19). | Tied to a Google Cloud project (`muse-growth`) and a Google Ads Manager (MCC) account: **Test Access** (automatic, test accounts only) → **Explorer Access** (auto-granted for some accounts, 2,880 ops/day on production) → **Basic Access** (application form + compliance review, 15,000 ops/day) → **Standard Access** (audit + application, unlimited ops/day) ([Google Ads API Access Levels](https://developers.google.com/google-ads/api/docs/access-levels), accessed 2026-11-19). | Register developer account at `business-api.tiktok.com`, create a Marketing API App, and submit for platform review (typically 3–5 business days) specifying required permission groups ([TikTok Developer Onboarding](https://business-api.tiktok.com/portal/docs?id=1735713685554177), accessed 2026-11-19). | Create X Developer project/app at `developer.x.com`, then submit the **X Ads API Access Application** form. Standard approval timeline cited by X is ~3 business days ([X Ads API Step-by-Step Guide](https://docs.x.com/x-ads-api/getting-started/step-by-step-guide), accessed 2026-11-19). | Enable "Advertising API" product on a LinkedIn Developer App: starts in **Development Tier** (uncapped reads, max 5 edited live ad accounts, 1 test ad account). Upgrade to **Standard Tier** (unlimited accounts) requires a review form and a **screen-recorded demo video** showing campaign/creative creation and editing ([LinkedIn Marketing Tiers](https://learn.microsoft.com/en-us/linkedin/marketing/integrations/marketing-tiers), accessed 2026-11-19). |
| **Business Verification** | **Required** in Meta Business Suite before submitting App Review for Advanced Access to `ads_read` / `ads_management` ([Meta Business Verification](https://developers.facebook.com/docs/development/release/business-verification), accessed 2026-11-19). | Google OAuth App Verification (Brand + Sensitive/Restricted scope verification in Google Cloud Console) + Google Ads Advertiser Verification on live ad accounts ([Google Ads API OAuth Verification](https://developers.google.com/google-ads/api/docs/oauth/verification), accessed 2026-11-19). | TikTok Business Verification (company registration document + domain/email verification in TikTok Business Center / Developer Portal) required before app approval ([TikTok Developer Onboarding](https://business-api.tiktok.com/portal/docs?id=1735713685554177), accessed 2026-11-19). | Validated X business/advertiser account (`ads.x.com`) with an active funding instrument or verified organization profile ([X Ads API Getting Started](https://docs.x.com/x-ads-api/getting-started/step-by-step-guide), accessed 2026-11-19). | App must be associated with a verified LinkedIn Company Page; a page Super Admin must approve the association in the Developer Portal ([LinkedIn Marketing Getting Started](https://learn.microsoft.com/en-us/linkedin/marketing/getting-started), accessed 2026-11-19). |
| **Test / Sandbox Accounts** | **Sandbox Ad Accounts** created in App Dashboard (`Marketing API > Tools > Sandbox Ad Account Management`). Isolated from Ads Manager UI; no ads delivered or billed. Note: dynamic creative previews and certain page-backed creative mutations fail in sandbox mode; Meta recommends using a low-budget paused live account or hardcoded creative IDs for full creative tests ([Meta Marketing API Sandbox](https://developers.facebook.com/docs/marketing-api/sandbox), accessed 2026-11-19). | **Test Manager Account** + child **Test Client Accounts** (`developers.google.com/google-ads/api/docs/best-practices/test-accounts`). Supports full mutate tree (`CampaignBudget`, `Campaign`, `AdGroup`, `AdGroupAd`, `Asset`); zero delivery or billing; reporting queries return zero impressions/clicks ([Google Ads Test Accounts](https://developers.google.com/google-ads/api/docs/best-practices/test-accounts), accessed 2026-11-19). | Official **TikTok Sandbox** at `https://sandbox-ads.tiktok.com/open_api/v1.3/`. Supports test advertiser creation in Developer Portal, campaign/adgroup/ad mutations, and mock reporting ([TikTok Sandbox Docs](https://business-api.tiktok.com/portal/docs?id=1738855278046209), accessed 2026-11-19). | Documented sandbox host `https://ads-api-sandbox.x.com` allows creating test accounts without billing ([X Ads API Sandbox](https://docs.x.com/x-ads-api/fundamentals/sandbox), accessed 2026-11-19). Current self-serve reliability for new apps is **[Unconfirmed in official docs as of 2026-11-19]** (third-party developers report intermittent deprecations). | **Development Tier** permits creating **1 Test Ad Account** via `POST /rest/adAccounts` with `test: true` (no billing method required, never serves impressions) ([LinkedIn Test Ad Accounts](https://learn.microsoft.com/en-us/linkedin/marketing/integrations/ads/account-structure/create-and-manage-accounts#create-a-test-ad-account), accessed 2026-11-19). |
| **What Can Be Created by API** | Campaigns (`/act_{id}/campaigns`), Ad Sets (`/act_{id}/adsets`), Ads (`/act_{id}/ads`), Ad Creatives (`/act_{id}/adcreatives`), Ad Images (`/act_{id}/adimages`), Ad Videos (`/act_{id}/advideos`), Custom & Lookalike Audiences (`/act_{id}/customaudiences`). All created objects accept `status="PAUSED"` ([Meta Campaign Reference](https://developers.facebook.com/docs/marketing-api/reference/ad-campaign-group), accessed 2026-11-19). | Campaign Budgets (`CampaignBudgetService`), Campaigns (`CampaignService`, `status=PAUSED`), Ad Groups (`AdGroupService`), Responsive Search/Display/Performance Max Ads (`AdGroupAdService`), Image/Video/Text Assets (`AssetService`), UserLists (`UserListService`) ([Google Ads Mutate Overview](https://developers.google.com/google-ads/api/docs/mutating/overview), accessed 2026-11-19). | Campaigns (`/campaign/create/`), Ad Groups (`/adgroup/create/`), Ads (`/ad/create/`), Image/Video uploads (`/file/image/ad/upload/`, `/file/video/ad/upload/`), Custom Audiences (`/dmp/custom_audience/create/`). Supports `operation_status="DISABLE"` (paused on creation) ([TikTok Campaign Creation](https://business-api.tiktok.com/portal/docs?id=1739318962329602), accessed 2026-11-19). | Campaigns (`/12/accounts/{id}/campaigns`), Line Items (`/12/accounts/{id}/line_items`), Promoted Tweets (`/12/accounts/{id}/promoted_tweets`), Media Creatives & chunked media upload (`upload.x.com`), Custom Audiences (`/12/accounts/{id}/custom_audiences`). Supports `entity_status="PAUSED"` ([X Ads API Campaign Management](https://docs.x.com/x-ads-api/campaign-management/overview), accessed 2026-11-19). | Campaign Groups (`/rest/adAccounts/{id}/adCampaignGroups`), Campaigns (`/rest/adAccounts/{id}/adCampaigns`), Creatives (`/rest/adAccounts/{id}/creatives`), Images/Videos (`/rest/images`, `/rest/videos`), DMP Segments (`/rest/dmpSegments`). Supports `status="PAUSED"` or `"DRAFT"` ([LinkedIn Campaign Management](https://learn.microsoft.com/en-us/linkedin/marketing/integrations/ads/account-structure/create-and-manage-campaigns), accessed 2026-11-19). |
| **Validate-Only / Dry-Run Support** | **Yes.** `execution_options=["validate_only"]` on `POST` calls to `/campaigns`, `/adsets`, `/ads`, and `/adcreatives` validates schema, targeting, and business rules without persisting objects ([Meta Execution Options](https://developers.facebook.com/docs/marketing-api/reference/ad-campaign-group#execution_options), accessed 2026-11-19). | **Yes.** `validate_only: true` on `GoogleAdsService.Mutate` and resource-specific `*Service.Mutate*` endpoints validates syntax, field constraints, and ad policy without committing changes ([Google Ads Validate Only](https://developers.google.com/google-ads/api/docs/mutating/overview#validate_only), accessed 2026-11-19). | **No documented `validate_only` parameter** on `/campaign/create/`, `/adgroup/create/`, or `/ad/create/` (**[Unconfirmed in official docs as of 2026-11-19]**; dry-run validation must use `sandbox-ads.tiktok.com` or create objects with `operation_status="DISABLE"`). | **No documented `validate_only` flag** on campaign/line-item `POST` endpoints (**[Unconfirmed in official docs as of 2026-11-19]**; must validate in `ads-api-sandbox.x.com` or create with `entity_status="PAUSED"`). | **No general `validate_only` query/body flag** on `/rest/adCampaigns` or `/rest/creatives` (**[Unconfirmed in official docs as of 2026-11-19]**; LinkedIn provides `status="DRAFT"` for unbilled draft entities and a test ad account in Development Tier). |
| **Rate Limits** | Dynamic point-based rolling window per ad account (`X-Business-Use-Case-Usage`, `X-Ad-Account-Usage`, `X-FB-Ads-Insights-Throttle`). Error codes `17`, `4`, `613`, `80004` on breach ([Meta Marketing API Rate Limiting](https://developers.facebook.com/docs/marketing-api/overview/rate-limiting), accessed 2026-11-19). | Test/Basic: **15,000 operations/day** (Explorer: 2,880 ops/day; Standard: unlimited). ~1 QPS per Customer ID on heavy reporting/planning services. HTTP `429 RESOURCE_EXHAUSTED` with `Retry-After` ([Google Ads API Quotas](https://developers.google.com/google-ads/api/docs/best-practices/quotas), accessed 2026-11-19). | Sandbox: **1 QPS / 30 QPM / 1,000 QPD** per endpoint ([TikTok Sandbox Docs](https://business-api.tiktok.com/portal/docs?id=1738855278046209), accessed 2026-11-19). Production: sliding-window per app + advertiser (typically 10–20 QPS depending on endpoint; returns HTTP 429 or code `40100`). Exact production tier table behind developer portal login (**[Unconfirmed in official docs as of 2026-11-19]**). | Per-endpoint 15-minute windows returned via `x-rate-limit-limit`, `x-rate-limit-remaining`, `x-rate-limit-reset` headers; HTTP `429` on breach ([X Ads API Rate Limiting](https://docs.x.com/x-ads-api/fundamentals/rate-limiting), accessed 2026-11-19). | Per-application and per-member daily UTC quotas (reset 00:00 UTC); exact numbers displayed only in the LinkedIn Developer Portal Analytics tab after first call; HTTP `429` on breach ([LinkedIn Rate Limits](https://learn.microsoft.com/en-us/linkedin/shared/api-guide/concepts/rate-limits), accessed 2026-11-19). |
| **Official Client & License** | [`facebookbusiness` (`facebook-python-business-sdk`)](https://github.com/facebook/facebook-python-business-sdk) — **Custom Meta Platform License** (royalty-free use/modification/distribution *only* in connection with Meta web services; **incompatible with pure AGPL-3.0 redistribution** if bundled as modified source, and uses synchronous `requests`, accessed 2026-11-19). | [`google-ads` (`google-ads-python`)](https://github.com/googleads/google-ads-python) — **Apache-2.0** (compatible with AGPL-3.0 v3 section 13/patent clauses; heavy gRPC/protobuf dependency tree, accessed 2026-11-19). | [`tiktok-business-api-sdk`](https://github.com/tiktok/tiktok-business-api-sdk) — **MIT License** (AGPL-3.0 compatible; Swagger-generated synchronous `urllib3` client, accessed 2026-11-19). | [`twitter-python-ads-sdk`](https://github.com/xdevplatform/twitter-python-ads-sdk) — **MIT License** (AGPL-3.0 compatible, but **unmaintained/legacy** targeting pre-v12 `ads-api.twitter.com`, accessed 2026-11-19). | [`linkedin-api-python-client`](https://github.com/linkedin-developers/linkedin-api-python-client) — **Custom Proprietary LinkedIn Terms** (`LICENSE.md` restricts usage to LinkedIn Developer Terms; not an OSI-approved license, accessed 2026-11-19). |

### 1.2 Why Muse Uses `httpx.AsyncClient` Instead of Vendor Python SDKs
Per `AGENTS.md` section 6 ("Async by default for anything doing I/O. One shared `httpx.AsyncClient` per client module, with explicit timeouts. No `requests`."):
1. **License hygiene (AGPL-3.0):** `facebook-python-business-sdk` and `linkedin-api-python-client` use custom platform-restricted licenses rather than OSI-approved MIT/Apache-2.0 licenses. Calling the REST endpoints directly via `httpx` avoids bundling non-OSI SDK code.
2. **Async & Vercel bundle weight:** `facebook-python-business-sdk`, `tiktok-business-api-sdk`, and `twitter-python-ads-sdk` are synchronous (`requests`/`urllib3`). `google-ads-python` pulls in `grpcio` and large generated protobuf packages that bloat serverless cold starts on Vercel, whereas Google Ads API v18 exposes a first-class JSON REST interface (`POST https://googleads.googleapis.com/v18/customers/{customerId}/googleAds:searchStream`) directly callable with `httpx`.

---

## 2. Open-Source & Commercial Unified API Survey

### 2.1 Open-Source Projects Audited (2026-11-19)

| Repository | License | Networks Covered | Architecture & Key Patterns | What It Saves Muse / Reuse Verdict |
|---|---|---|---|---|
| [`RoyAzran/mcp-ads`](https://github.com/RoyAzran/mcp-ads) (accessed 2026-11-19) | **MIT License** (AGPL-3.0 compatible with attribution) | Google Ads, Meta, TikTok, LinkedIn, Microsoft Ads, Snapchat (X Ads is hosted-only in their commercial tier) | Python MCP server (~4 stars, ~12 commits). Enforces a **"created objects start paused"** invariant across adapters (`PAUSED` / `DISABLE`), includes a `cryptography.fernet.Fernet` encrypted local token store, and maps disparate network metrics into normalized dicts. | **Best reference pattern.** Because the repo is very young (~12 commits), we should not add it as a runtime dependency, but its MIT-licensed field mappings, per-network pause status constants, and Fernet envelope pattern can be adapted directly with attribution. |
| [`pipeboard-co/meta-ads-mcp`](https://github.com/pipeboard-co/meta-ads-mcp) (accessed 2026-11-19) | **Business Source License 1.1 (BUSL-1.1)** (converts to Apache-2.0 on 2029-01-01) | Meta (Facebook + Instagram) | Python MCP server wrapping Meta Graph API: insights breakdown queries, campaign/adset/ad creation, image upload, and OAuth callback handling. | **Do not copy code.** BUSL-1.1 prohibits commercial/hosted production SaaS competition and is incompatible with Muse's AGPL-3.0 license until 2029. Read only for conceptual validation of Meta Insights query parameters. |
| [`byadsco/meta-ads-mcp`](https://github.com/byadsco/meta-ads-mcp) (accessed 2026-11-19) | **MIT License** (AGPL-3.0 compatible) | Meta (Facebook + Instagram) | Self-hosted Node/TypeScript MCP server for reading Meta ad account hierarchy, insights, and creatives. | Confirms minimal field sets (`campaign_id,campaign_name,adset_id,adset_name,impressions,clicks,spend,actions,action_values,frequency`) needed for daily ad-set diagnostics. Different runtime (TypeScript), so no code reuse needed. |
| [`bengoism/agent-ads`](https://github.com/bengoism/agent-ads) (accessed 2026-11-19) | Root `LICENSE` file **[Unconfirmed in official docs as of 2026-11-19]** via public index snippets (treat as all-rights-reserved until inspected via git clone) | Meta, Google Ads (GAQL), TikTok, X, LinkedIn, Pinterest (6 networks, read-only CLI) | Rust CLI tool that normalizes read-only campaign performance reports across 6 networks into unified terminal tables / JSON for coding agents. | Useful as a conceptual check on cross-network metric normalization (mapping Meta `actions[purchase]`, Google `metrics.conversions`, TikTok `complete_payment`, X `conversion_purchases`, LinkedIn `externalWebsiteConversions`), but no code reuse due to Rust language and unconfirmed license file. |

### 2.2 Commercial Unified APIs Evaluated

| Vendor | Coverage & Capabilities | Pricing & Token Custody Trade-Offs |
|---|---|---|
| [**Unified.to**](https://unified.to/category/ads) (accessed 2026-11-19) | Unified Advertising API + Hosted OAuth vault covering Meta Ads, Google Ads, TikTok Ads, LinkedIn Ads, and X Ads (read & write models for Organizations, Campaigns, Ads, Creatives, and Reports). | **Pros:** Zero time spent waiting on 5 separate network app reviews if using Unified's shared OAuth app credentials during beta; single normalized REST schema. **Cons:** Paid monthly SaaS tier ($150–$500+/mo as active connections scale); third-party vendor sits in the request path and holds or proxies seller OAuth tokens; less granular support for network-specific features like Meta `execution_options=["validate_only"]` or Advantage+ flags. |
| [**Zernio**](https://zernio.com/ads-api) (accessed 2026-11-19) | Unified Ads API designed for AI agents covering Meta, Google, TikTok, LinkedIn, X, Pinterest, Reddit, and Microsoft Ads (campaign launch, post boosting, audience sync, unified analytics). | **Pros:** Purpose-built for agentic workflows ("boost post", "create paused campaign", unified reporting endpoint). **Cons:** Paid per-connection / usage pricing; vendor lock-in on ad creation payloads; sellers must trust an external intermediary with write access to their ad budgets. |

### 2.3 Build vs. Vendor Recommendation

**Recommendation: Build direct `httpx` adapters in-house (starting with Meta and Google Ads), and do not put a commercial unified API vendor in custody of seller ad tokens.**

1. **Trust & security for solo sellers:** Asking an Etsy or Shopify seller to connect an ad account with a live credit card attached is high-friction. Keeping OAuth tokens encrypted inside Muse's own `muse_private` Supabase schema (with zero third-party middleware) is simpler to explain in our privacy policy and required for Meta/Google security reviews.
2. **Meta + Google cover >90% of consumer SMB ad spend:** Solo product and service sellers on Muse almost exclusively run Meta (Instagram/Facebook) and Google Shopping/Search ads, with TikTok a distant third. Building clean `httpx` adapters for Meta (`v21.0`) and Google Ads REST (`v18`) takes ~300 lines of Python each and gives us first-class access to native `validate_only` dry-run flags.
3. **When to reconsider a vendor:** Only if Nav decides X Ads and LinkedIn Ads must launch simultaneously in Phase 1 without waiting for X/LinkedIn developer reviews. Even then, Nav can use direct adapters for Meta/Google and leave X/LinkedIn disabled.

---

## 3. What Nav Has to Do on Each Network (Ordered by Lead Time & ROI)

> **Boundary confirmation:** Argon has **not** created any apps, submitted any forms, accepted any terms, or touched any network or cloud console. Below is the exact checklist for Nav, ordered by when to start based on lead times.

### Step 0: Prerequisite Business Documents (Start Day 1 — needed by Meta, Google, and TikTok)
- Gather official business formation / tax document for the legal entity operating Muse (e.g., IRS EIN confirmation letter CP-575, Articles of Incorporation/Organization, or business utility/bank statement matching the company address) and ensure admin access to `@nplusalpha.com` DNS and email.

### Track 1: Meta (Facebook & Instagram) — *Start Day 1 (Lead time: 0 days for own/test accounts; 1–3 weeks for Business Verification + App Review)*
1. **Create a Meta Developer App:** Log in at [developers.facebook.com/apps](https://developers.facebook.com/apps) (accessed 2026-11-19), click **Create App → Other → Business**, name it *Muse Growth Studio*, and link it to your Meta Business Portfolio (Business Manager).
2. **Add Marketing API & Facebook Login for Business:** In the App Dashboard, add the **Marketing API** and **Facebook Login for Business** products.
3. **Create a Sandbox Ad Account (0-day lead time):** Go to **Marketing API → Tools → Sandbox Ad Account Management** and create a sandbox ad account (`act_...`) + generate a developer token with `ads_read` and `ads_management` to test immediately on your own account.
4. **Configure OAuth Redirect URI:** Under **Facebook Login for Business → Settings**, add `https://meta-smb-gtm.vercel.app/api/v1/ad-accounts/meta/callback` (and `http://localhost:8000/api/v1/ad-accounts/meta/callback` for local testing).
5. **Submit Business Verification (2–10 business days):** In [Meta Business Suite Security Center](https://business.facebook.com/settings/security) (accessed 2026-11-19), upload the legal entity documents and verify `nplusalpha.com` via DNS TXT record or `@nplusalpha.com` email code.
6. **Request Advanced Access via App Review (3–7 business days after Business Verification):**
   - **Phase 1a (Read-only launch):** Submit App Review for **Advanced Access** to `ads_read` only. Record a 60-second screencast showing a seller clicking "Connect Meta Ads", completing Facebook Login, and seeing their real ad-set performance inside Muse Bid Advisor. (`ads_read` review is significantly faster than `ads_management`.)
   - **Phase 1b (Paused draft creation):** Once Phase 1a is live, submit App Review for **Advanced Access** to `ads_management`, showing the seller previewing and creating a **PAUSED** draft campaign from `/first-ad`.

### Track 2: Google Ads — *Start Day 2 (Lead time: 0 days for Test Access; 3–10 business days for Basic Access + Google OAuth Verification)*
1. **Create a Google Ads Manager (MCC) Account:** At [ads.google.com/home/tools/manager-accounts](https://ads.google.com/home/tools/manager-accounts/) (accessed 2026-11-19), create a production Manager Account for Muse.
2. **Request Developer Token & Link Cloud Project (`muse-growth`):** Inside the production MCC, go to **Admin → API Center**, fill out the API Access details, and link existing Google Cloud project `muse-growth`. You receive a **Test Access** developer token immediately ([Google Ads API Obtain Developer Token](https://developers.google.com/google-ads/api/docs/get-started/dev-token), accessed 2026-11-19).
3. **Create a Test Manager Account (0-day lead time):** Create a separate Google Ads Test Manager account at [developers.google.com/google-ads/api/docs/best-practices/test-accounts](https://developers.google.com/google-ads/api/docs/best-practices/test-accounts) (accessed 2026-11-19) and create 1–2 child test ad accounts inside it.
4. **Enable Google Ads API in `muse-growth`:** In Google Cloud Console (`console.cloud.google.com`), enable **Google Ads API** on project `muse-growth` and add redirect URI `https://meta-smb-gtm.vercel.app/api/v1/ad-accounts/google/callback` + scope `https://www.googleapis.com/auth/adwords`.
5. **Apply for Basic Access (3–10 business days):** Submit the **Google Ads API Basic Access Application** form from the MCC API Center (grants 15,000 operations/day on production seller accounts) and complete Google Cloud OAuth Brand + Sensitive Scope verification for `https://www.googleapis.com/auth/adwords`.

### Track 3: TikTok Marketing API — *Start Week 2 (Lead time: 3–7 business days)*
1. **Register Developer Account:** Sign up at [business-api.tiktok.com/portal](https://business-api.tiktok.com/portal) (accessed 2026-11-19) linked to a TikTok Business Center account.
2. **Complete Business Verification (2–4 business days):** Submit business registration details in the TikTok Developer Portal.
3. **Create Marketing API App (3–5 business days for approval):** Create an app requesting **Ad Account Management**, **Reporting**, **Ads Management** (Campaign/AdGroup/Ad), and **Creative Management** permissions, and set redirect URI `https://meta-smb-gtm.vercel.app/api/v1/ad-accounts/tiktok/callback`.
4. **Initialize Sandbox Account (0 days once app exists):** In the Developer Portal, open the **Sandbox** tab (`sandbox-ads.tiktok.com`) to provision a test `advertiser_id` and sandbox access token.

### Track 4: X (Twitter) Ads API — *Start Week 3 if prioritized (Lead time: ~3–5 business days)*
1. **Create X Developer App:** Log in at [developer.x.com](https://developer.x.com) (accessed 2026-11-19) with an X account that has an active advertiser profile on `ads.x.com`.
2. **Enable 3-Legged OAuth 1.0a:** In the App Settings, enable User Authentication (Read and Write) with callback URL `https://meta-smb-gtm.vercel.app/api/v1/ad-accounts/x/callback`.
3. **Submit X Ads API Application (~3 business days):** Fill out the Ads API access form linked in [docs.x.com/x-ads-api/getting-started/step-by-step-guide](https://docs.x.com/x-ads-api/getting-started/step-by-step-guide) (accessed 2026-11-19). **Important:** After approval email arrives, regenerate user tokens so they carry Ads API entitlements.

### Track 5: LinkedIn Advertising API — *Start Week 3 if B2B sellers are in scope (Lead time: 1–2 days for Development Tier; 2–4 weeks for Standard Tier with demo video)*
1. **Create LinkedIn Developer App:** At [developer.linkedin.com](https://www.linkedin.com/developers/) (accessed 2026-11-19), create an app linked to your company's LinkedIn Page and have the Page Super Admin click the verification link.
2. **Request Advertising API (Development Tier, 1–2 business days):** Under the **Products** tab, select **Advertising API** and submit the Development Tier form. Once approved, create 1 test ad account via `POST /rest/adAccounts` (`test: true`) and configure redirect URI `https://meta-smb-gtm.vercel.app/api/v1/ad-accounts/linkedin/callback` with scopes `r_ads`, `r_ads_reporting`, `rw_ads`.
3. **Upgrade to Standard Tier (2–4 weeks):** Record a demo video showing Muse OAuth connection, campaign creation, and reporting, then submit the Standard Tier upgrade application in the Developer Portal ([LinkedIn Marketing Tiers](https://learn.microsoft.com/en-us/linkedin/marketing/integrations/marketing-tiers), accessed 2026-11-19).

---

## 4. Architecture in This Repo's Style

Following `AGENTS.md` sections 4, 6, and 10, all ad network integrations follow the strict 3-layer separation (**routes → services → clients**) with Pydantic v2 boundary models, one shared `httpx.AsyncClient` per client instance, and feature-gating behind `AD_CONNECT_ENABLED` (default `false`).

```
                      ┌─────────────────────────────────────────────┐
                      │              FastAPI (src/api)              │
                      │  /api/v1/ad-accounts  (mounted only when    │
                      │             AD_CONNECT_ENABLED=true)        │
                      └──────────────────────┬──────────────────────┘
                                             │
            ┌────────────────────────────────▼────────────────────────────────┐
            │                         src/services/                           │
            │  ad_insights.py      (Insights rows -> CampaignPerformance)     │
            │  ad_connections.py   (Future: OAuth state, Fernet token Vault)  │
            │  ad_publisher.py     (Future: dry-run, paused-draft writes)     │
            └──────┬─────────────────────────┬─────────────────────────┬──────┘
                   │                         │                         │
     ┌─────────────▼──────────┐ ┌────────────▼───────────┐ ┌───────────▼──────────┐
     │ src/clients/           │ │ src/clients/           │ │ src/clients/         │
     │ ad_networks/base.py    │ │ ad_networks/meta.py    │ │ ad_networks/google.py│
     │ (Protocol + Pydantic   │ │ (Graph API v21.0       │ │ (Future: REST v18,   │
     │  models + typed errs)  │ │  httpx read-only)      │ │  tiktok, x, linkedin)│
     └────────────────────────┘ └────────────────────────┘ └──────────────────────┘
```

### 4.1 Adapter Protocol & Typed Error Hierarchy (`src/clients/ad_networks/base.py`)
Every network client implements `AdNetworkReadAdapter` (read-only protocol implemented in Deliverable 2) and, only after Nav's sign-off on Section 5, a separate `AdNetworkWriteAdapter` protocol:
- **Boundary models:** `AdNetworkId` (`Literal["meta", "google_ads", "tiktok", "x", "linkedin"]`), `AdAccountSummary`, `AdCampaignSummary`, `AdSetInsightRow`.
- **Typed exceptions:**
  - `AdNetworkError(Exception)` — base error carrying `network`, `status_code`, `provider_code`, and safe user message (never logs or echoes tokens).
  - `AdNetworkAuthError(AdNetworkError)` — expired, revoked, or malformed OAuth token (e.g., Meta Graph error code `190`, HTTP `401`). Triggers a UI prompt to reconnect the account.
  - `AdNetworkPermissionError(AdNetworkError)` — missing scope (`ads_read` / `ads_management`) or missing role on the ad account (e.g., Meta error codes `10`, `200`, `294`, HTTP `403`).
  - `AdNetworkRateLimitError(AdNetworkError)` — rate limit or quota breach (e.g., Meta error codes `4`, `17`, `32`, `613`, `80004`, HTTP `429`), carrying optional `retry_after_seconds`.

### 4.2 OAuth Flow Per Network (Design for Phase 1b)
1. **Initiation (`POST /api/v1/ad-accounts/{network}/connect`):** Requires an authenticated Muse account session (`ACCOUNTS_REQUIRED=true` + verified email) and `AD_CONNECT_ENABLED=true`. Generates a cryptographically random 32-byte `state` nonce signed with HMAC-SHA256 (bound to `user_id`, `network`, and a 10-minute expiry timestamp) plus PKCE `code_verifier` where supported, and returns the provider authorization URL.
2. **Callback (`GET /api/v1/ad-accounts/{network}/callback`):** Verifies the signed `state` cookie/token against the logged-in `user_id`, exchanges `code` for access/refresh tokens over `httpx`, fetches the list of accessible ad accounts (`list_ad_accounts`), encrypts the tokens at rest with `AD_TOKEN_ENCRYPTION_KEY`, and redirects back to `/#tab-bids` or `/first-ad`.
3. **Read-first scope principle:** Phase 1 OAuth requests **only** read scopes (`ads_read` on Meta, `r_ads` + `r_ads_reporting` on LinkedIn). Write scopes (`ads_management`, `rw_ads`) are requested via incremental authorization only when the seller explicitly enables draft creation and Nav turns on `AD_WRITE_ENABLED=true`.

### 4.3 Token Storage Encrypted at Rest (Proposed SQL — Not Applied in This Task)
In keeping with `supabase/migrations/digest_subscribers.sql` and `billing_repair.sql`, all sensitive tables live in the private `muse_private` schema with Row-Level Security enabled, all permissions revoked from `public`, `anon`, and `authenticated`, and access restricted strictly to server-side `service_role` calls.

- **Application-layer envelope encryption:** Before any token leaves the Python process for Supabase, `src/services/ad_connections.py` encrypts the raw token string using `cryptography.fernet.MultiFernet` (AES-128-CBC + HMAC-SHA256) keyed by a new secret environment variable `AD_TOKEN_ENCRYPTION_KEY` (supports comma-separated keys for zero-downtime key rotation, with `key_version` recorded per row). Even a full database dump of `muse_private.ad_account_connections` cannot yield usable OAuth tokens without `AD_TOKEN_ENCRYPTION_KEY`.

```sql
-- Proposed migration (DESIGN ONLY — do not apply until Nav approves AD_NETWORKS_SPEC.md):
-- supabase/migrations/ad_account_connections.sql

begin;

create table if not exists muse_private.ad_account_connections (
    id uuid primary key default gen_random_uuid(),
    user_id uuid not null references auth.users(id) on delete cascade,
    network text not null check (network in ('meta', 'google_ads', 'tiktok', 'x', 'linkedin')),
    external_account_id text not null check (length(trim(external_account_id)) between 1 and 128),
    account_name text not null default '',
    currency text not null default 'USD' check (length(currency) = 3),
    timezone_name text not null default 'UTC',
    scopes text[] not null default '{}',
    access_level text not null default 'read_only'
        check (access_level in ('read_only', 'paused_drafts')),
    -- Application-encrypted ciphertext (MultiFernet / AES-128-CBC + HMAC-SHA256).
    -- Never store plaintext tokens.
    access_token_ciphertext text not null,
    refresh_token_ciphertext text,
    key_version smallint not null default 1 check (key_version >= 1),
    token_expires_at timestamptz,
    daily_spend_cap_cents integer not null default 5000 check (daily_spend_cap_cents >= 0),
    status text not null default 'active'
        check (status in ('active', 'expired', 'revoked', 'disconnected')),
    connected_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    last_synced_at timestamptz,
    unique (user_id, network, external_account_id)
);

create index if not exists ad_account_connections_user_idx
    on muse_private.ad_account_connections (user_id, status);

-- Immutable audit log for every write preview, dry-run validation, paused draft creation,
-- or budget update across any ad network (see Section 5.6).
create table if not exists muse_private.ad_account_audit_log (
    id uuid primary key default gen_random_uuid(),
    connection_id uuid not null references muse_private.ad_account_connections(id) on delete cascade,
    user_id uuid not null references auth.users(id) on delete cascade,
    network text not null check (network in ('meta', 'google_ads', 'tiktok', 'x', 'linkedin')),
    external_account_id text not null,
    action_type text not null check (action_type in (
        'validate_only',
        'create_paused_campaign',
        'create_paused_ad_set',
        'create_paused_ad',
        'upload_creative',
        'update_budget',
        'pause_entity',
        'activate_entity'
    )),
    target_entity_id text,
    before_state jsonb,
    after_state jsonb not null,
    daily_budget_cents integer check (daily_budget_cents is null or daily_budget_cents >= 0),
    currency text not null default 'USD',
    seller_confirmation_token_hash text not null check (seller_confirmation_token_hash ~ '^[a-f0-9]{64}$'),
    provider_status text not null check (provider_status in ('validated', 'applied_paused', 'applied_active', 'rejected', 'error')),
    provider_response_summary jsonb,
    created_at timestamptz not null default now()
);

create index if not exists ad_account_audit_log_user_created_idx
    on muse_private.ad_account_audit_log (user_id, created_at desc);

alter table muse_private.ad_account_connections enable row level security;
alter table muse_private.ad_account_audit_log enable row level security;

-- Defense-in-depth RLS: even if a role were ever granted table access, rows are scoped to auth.uid().
create policy ad_account_connections_owner_select
    on muse_private.ad_account_connections
    for select
    using (auth.uid() = user_id);

create policy ad_account_audit_log_owner_select
    on muse_private.ad_account_audit_log
    for select
    using (auth.uid() = user_id);

-- Match repo convention: revoke direct PostgREST access from public/anon/authenticated;
-- only the FastAPI backend (using service_role) may read or decrypt ciphertexts.
revoke all on muse_private.ad_account_connections from public, anon, authenticated;
revoke all on muse_private.ad_account_audit_log from public, anon, authenticated;
grant select, insert, update, delete on muse_private.ad_account_connections to service_role;
grant select, insert on muse_private.ad_account_audit_log to service_role;

commit;
```

---

## 5. Safety Model for Writes (Requires Nav's Explicit Approval)

Because an ad account write can spend real money on a solo seller's credit card, Muse enforces **seven layered technical guardrails**. No write endpoint will be built until Nav signs off on this model:

1. **Read-Only First (`access_level = 'read_only'`):**
   - Connecting an ad account defaults to read-only insights (`ads_read` on Meta). Bid Advisor and `/today` operate purely on read-only performance data.
   - Write capabilities require a separate opt-in ("Enable draft publishing") and an independent server flag `AD_WRITE_ENABLED=false`.
2. **Mandatory Dry-Run (`validate_only`) Before Any Commit:**
   - On networks supporting dry-run validation (Meta `execution_options=["validate_only"]`, Google Ads `validate_only=True`), Muse **must** execute a dry-run call first during the preview step.
   - If the dry-run fails, the seller sees the plain-language explanation before confirming; no live mutation is attempted.
3. **Preview-and-Confirm Contract with Exact Budget, Currency, and Dates:**
   - Every proposed write generates a server-signed `WritePreviewToken` (valid for 5 minutes) locking the exact `external_account_id`, `daily_budget_cents`, `currency`, `start_date`, `end_date`, `target_entity_id`, and `after_state` SHA-256 digest.
   - The seller UI displays a high-contrast confirmation card showing the exact daily budget, currency, schedule dates, and before-vs-after diff. The execution endpoint rejects any request missing a matching, unspent `WritePreviewToken`.
4. **All Created Objects Start `PAUSED` (Hardcoded at the Client Layer):**
   - `create_campaign`, `create_ad_set`, and `create_ad` in the network adapter layer hardcode `status="PAUSED"` (Meta/Google/X/LinkedIn) or `operation_status="DISABLE"` (TikTok) in the outbound payload.
   - Creation methods do not even accept a `status="ACTIVE"` parameter, making it structurally impossible for a prompt injection or UI bug to create a live, spending campaign in a single step.
5. **Activation Is a Separate Confirmation Step (Default: Seller Activates in Native Ads Manager):**
   - In Phase 1b, Muse **never** transitions a campaign from `PAUSED` to `ACTIVE`. After creating a paused draft, Muse gives the seller a direct deep-link to the draft in Meta Ads Manager (`https://adsmanager.facebook.com/adsmanager/manage/campaigns?act={id}`) so the seller can review billing/pixel settings and toggle it on themselves.
   - If Nav approves in-app activation in a later phase, `activate_entity` must be a dedicated endpoint requiring its own separate confirmation modal and a typed confirmation check (e.g., confirming the daily dollar amount).
6. **Hard Per-Account Daily Spend Cap Enforced in Python & SQL:**
   - Each connected account row in `muse_private.ad_account_connections` stores `daily_spend_cap_cents` (default `5000` = `$50.00/day`), alongside a global ceiling `AD_MAX_DAILY_BUDGET_USD=100.0` in `src/config.py`.
   - Any campaign creation or budget increase where the resulting daily budget exceeds `min(connection.daily_spend_cap_cents, settings.ad_max_daily_budget_usd * 100)` is rejected before calling the ad network.
7. **Immutable Audit Log & Instant Kill Switch:**
   - Every dry-run and write operation writes an append-only row to `muse_private.ad_account_audit_log` (Notice: `service_role` has `SELECT, INSERT` only — no `UPDATE` or `DELETE` grant on the audit log table) recording `before_state`, `after_state`, `daily_budget_cents`, and `seller_confirmation_token_hash`.
   - Setting `AD_WRITE_ENABLED=false` (or `AD_CONNECT_ENABLED=false`) on Vercel immediately disables all write routes across every connected account without requiring a redeploy of database state; an in-app "Emergency Pause All Muse Drafts" button lets a seller pause every entity ID recorded in `ad_account_audit_log` in one click.

---

## 6. How It Plugs Into Muse

### 6.1 Flow 3: Bid Advisor (`/bids` and `/#tab-bids`)
- **Today:** Seller exports a CSV from Meta Ads Manager and uploads it to `POST /api/v1/bid-advice/csv`, which calls `load_campaign_csv()` in `src/services/bid_advisor.py` to build a `CampaignPerformance` object (`src/models/bids.py`).
- **With Connected Insights (Deliverable 2 + Phase 1a route):**
  - `MetaAdsReadClient.fetch_ad_set_insights(account_id, start_date=..., end_date=...)` fetches daily ad-set level rows (`level="adset"`, `time_increment=1`) from Meta Graph API `/v21.0/act_{id}/insights`.
  - `src/services/ad_insights.py` (`meta_insights_to_campaign_performance`) converts those rows directly into the existing `CampaignPerformance(account_name=..., currency=..., rows=[AdSetDailyPerformance(...)])` model.
  - `bid_advisor.compute_metrics()` and `bid_advisor.advise()` run **unchanged** on that `CampaignPerformance` object—preserving every deterministic math rule, trend split, and fatigue flag while eliminating the manual CSV export/upload step. CSV upload remains available as a zero-auth fallback.

### 6.2 Guided Ad Preparation (`/first-ad`)
- **Today:** `/first-ad` guides a solo seller through choosing an item, audience, copy, and daily budget, ending with a manual checklist to copy-paste into Meta Ads Manager.
- **With Connected Account (Phase 1b):**
  - At the final step of `/first-ad`, if a Meta ad account is connected, the seller sees **"Create as a paused draft in Meta Ads Manager"** next to the manual checklist.
  - Clicking it runs a `validate_only` check, shows the Section 5.3 preview modal with exact daily budget (`$5`–`$20/day`), start date, and `PAUSED` badge, and upon confirmation creates the Campaign, Ad Set, and Ad Creative in `PAUSED` status, returning a direct deep-link into Meta Ads Manager.

### 6.3 Ad Creative Studio (`/create` and `/today`)
- **Today:** `/create` segments the product photo with SAM 3.1, generates lifestyle ad variants with Muse Image 1.0 / ComfyUI, and lets the seller download WebP/PNG exports + ad copy.
- **With Connected Account (Phase 1b):**
  - The export drawer on `/create` adds **"Send creative to connected ad account (Draft)"**.
  - Selecting a generated variant uploads the image bytes to Meta (`POST /v21.0/act_{id}/adimages` → `image_hash`) and creates an `AdCreative` object pre-populated with the seller's chosen headline, primary text, and shop listing URL, ready to attach to a paused draft in `/first-ad`.

---

## 7. Phased Rollout Plan

| Phase | Scope | Engineering Deliverables | What It Needs from Nav |
|---|---|---|---|
| **Phase 0 (Shipped in this branch)** | Offline specification + read-only Meta Marketing API slice behind `AD_CONNECT_ENABLED=false` | `docs/launch/AD_NETWORKS_SPEC.md`, `src/clients/ad_networks/base.py`, `src/clients/ad_networks/meta.py`, `src/services/ad_insights.py`, `AD_CONNECT_ENABLED=false` in `src/config.py` and `.env.example`, offline `respx` unit test suite (`tests/test_ad_networks_meta.py`). Zero live calls, zero mounted routes. | Review this specification and decide on the 6 open questions in `docs/launch/ARGON_AD_NETWORKS_NOV19.md`. |
| **Phase 1a: Meta Read-Only Connect** | Connect a Meta ad account via OAuth (`ads_read` only) and run Bid Advisor directly on live connected insights without a CSV upload. | Apply `supabase/migrations/ad_account_connections.sql`; add `src/services/ad_connections.py` (Fernet encryption); mount `/api/v1/ad-accounts/meta/*` OAuth & insights sync routes when `AD_CONNECT_ENABLED=true`; add "Connect Meta Ads (Read-only)" button to `/#tab-bids`. | 1. Create Meta Developer App.<br>2. Set `META_APP_ID`, `META_APP_SECRET`, and `AD_TOKEN_ENCRYPTION_KEY` in Vercel env.<br>3. Complete Meta Business Verification + `ads_read` App Review for external sellers (works immediately on Nav's own/sandbox accounts before review finishes). |
| **Phase 1b: Meta Paused Drafts & Creative Upload** | Create `PAUSED` draft campaigns/ad sets/creatives from `/first-ad` and upload `/create` images to `/act_{id}/adimages` behind `AD_WRITE_ENABLED`. | Implement `MetaAdsWriteClient` with mandatory `execution_options=["validate_only"]`, `status="PAUSED"`, `WritePreviewToken`, spend-cap checks, and `ad_account_audit_log` entries. Wire `/first-ad` and `/create` draft export UI. | 1. Sign off on the Section 5 Write Safety Model.<br>2. Submit Meta App Review for Advanced Access to `ads_management` using the Phase 1b preview-and-paused-draft flow in the screencast. |
| **Phase 2: Google Ads (Read + Paused Drafts)** | Connect Google Ads via OAuth (`adwords` scope) using Google Ads REST API v18 (`googleAds:searchStream` + `validateOnly: true` mutates). | `src/clients/ad_networks/google_ads.py` (`httpx` REST client), mapping GAQL `ad_group` daily rows into `CampaignPerformance`, and paused Search/Performance Max draft creation. | 1. Create Google Ads MCC + Test Manager account.<br>2. Link Cloud project `muse-growth` to get a Developer Token (`GOOGLE_ADS_DEVELOPER_TOKEN`).<br>3. Apply for Google Ads Basic Access + Google OAuth scope verification. |
| **Phase 3: TikTok Ads (Read + Paused Drafts)** | Connect TikTok Business accounts (`v1.3`), pull `/report/integrated/get/` into Bid Advisor, and push vertical video/image creatives from `/create` as `operation_status="DISABLE"` drafts. | `src/clients/ad_networks/tiktok.py`, token refresh job (24h access token / 365d refresh token), and sandbox validation against `sandbox-ads.tiktok.com`. | 1. Register at `business-api.tiktok.com`, complete TikTok Business Verification, and submit Marketing API App for review.<br>2. Add `TIKTOK_APP_ID` and `TIKTOK_APP_SECRET`. |
| **Phase 4: X Ads & LinkedIn Ads (On-Demand)** | Read-only insights (and optional paused drafts) for X (`ads-api.x.com/12`) and LinkedIn (`api.linkedin.com/rest/` with `LinkedIn-Version: 202611`). | `src/clients/ad_networks/x_ads.py` (OAuth 1.0a HMAC-SHA1 signer in stdlib `hmac`/`hashlib`) and `src/clients/ad_networks/linkedin.py`. | **Only start if seller demand justifies it** (LinkedIn is B2B-focused; X Ads has lower consumer e-commerce conversion share). Needs X Ads API application form (~3 days) and LinkedIn Advertising API application + Standard Tier demo video (2–4 weeks). |
