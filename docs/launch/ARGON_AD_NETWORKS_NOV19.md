# Argon Report: Ad Network Connections Spec & Read-Only Meta Slice (Nov 19, 2026)

- **Agent:** Argon (Gemini 4 Argon, in Antigravity)
- **Date:** 2026-11-19
- **Base ref:** `origin/claude/ux-gap-ad-loop-nov17` at `01296b6f1234a025212e45de0e28af85ebe7770f`
- **Branch:** `gemini/ad-networks-nov19`
- **Worktree:** `/private/tmp/muse-ad-networks-nov19` (main checkout `/Users/nav/meta-smb-gtm` untouched)

---

## 1. Files Delivered (Within Exclusive Write Scope)

| File | Change |
|---|---|
| `docs/launch/AD_NETWORKS_SPEC.md` | New 7-section multi-network specification with every factual claim linked to an official documentation page and dated `2026-11-19` (or marked unconfirmed), open-source & commercial unified API audit, ordered setup steps for Nav, proposed encrypted Supabase schema + RLS SQL, 7-layer write safety model, Muse integration points, and phased rollout plan. |
| `src/clients/ad_networks/__init__.py` | New package export for `AdNetworkReadAdapter`, boundary models, typed errors, and `MetaAdsReadClient`. |
| `src/clients/ad_networks/base.py` | New adapter protocol (`AdNetworkReadAdapter`), Pydantic v2 models (`AdAccountSummary`, `AdCampaignSummary`, `AdInsightRow`), and typed errors (`AdNetworkError`, `AdNetworkDisabledError`, `AdNetworkAuthError`, `AdNetworkPermissionError`, `AdNetworkRateLimitError`). Read-only; zero write methods. |
| `src/clients/ad_networks/meta.py` | New read-only Meta Marketing API (`v21.0`) `httpx` client (`list_ad_accounts`, `list_campaigns`, `fetch_campaign_insights`, cursor pagination with host validation and token query-param stripping, conversion action deduplication, and typed error classification). Refuses all requests when `AD_CONNECT_ENABLED=false`. |
| `src/services/ad_insights.py` | New service mapping `AdInsightRow` records into `CampaignPerformance` (`src/models/bids.py`) so `bid_advisor.compute_metrics()` and `bid_advisor.advise()` consume connected Meta insights without modifying `src/services/bid_advisor.py`. |
| `src/config.py` | Added `ad_connect_enabled: bool = False` on `Settings`. |
| `.env.example` | Added `AD_CONNECT_ENABLED=false` (default off). |
| `tests/test_ad_networks_meta.py` | New offline `respx` test suite (11 tests): default flag off, disabled flag blocking HTTP calls, happy-path ad accounts and campaigns, paginated insights with conversion deduplication and token query-param stripping, empty account handling, expired token (`code=190`), rate limiting (`code=80004` + `Retry-After`), permission denied (`code=200`), untrusted pagination host rejection, mapping into `CampaignPerformance` + `bid_advisor.compute_metrics()`, and account ID normalization. |
| `docs/launch/ARGON_AD_NETWORKS_NOV19.md` | This completion and handoff report. |

**Scope & boundary verification:**
- No calls to any ad network or live Muse API were made.
- No developer apps, applications, sign-ups, or terms were started or accepted.
- No secrets, Vercel environment variables, or Supabase migrations were touched or applied.
- Out-of-scope files (`src/api/`, `src/services/bid_advisor.py`, `src/clients/ad_library.py`, `src/services/competitor_intel.py`, `src/utils/sitemap.py`, `src/api/static/`, `supabase/`, `AGENTS.md`, and existing tests) are untouched.

---

## 2. Offline Verification Gate Results

Command run before and after changes:
```bash
DEMO_MODE=true META_MODEL_API_KEY= DEMO_KEY= make PY=/Users/nav/meta-smb-gtm/.venv/bin check
```

| Stage | `ruff check .` | `ruff format --check .` | `pytest` |
|---|---|---|---|
| **Baseline (`01296b6`)** | All checks passed! | 263 files already formatted | **638 collected: 636 passed, 2 skipped**, 1 warning in 180.37s |
| **After (`gemini/ad-networks-nov19`)** | All checks passed! | 269 files already formatted | **649 collected: 647 passed, 2 skipped** (+11 new tests in `tests/test_ad_networks_meta.py`), 1 warning in 183.90s |

---

## 3. What Could Not Be Confirmed in Official Docs (Marked Unconfirmed in Spec)

1. **`bengoism/agent-ads` root license file:** Public documentation (`agent-ads.dev`) confirms it is an open-source Rust CLI for 6 ad networks, but the exact SPDX identifier in its root `LICENSE` file could not be verified from official index metadata without cloning the repository. Marked unconfirmed; treated as all-rights-reserved (no code copied).
2. **X Ads API OAuth 2.0 PKCE coverage & sandbox availability for new self-serve apps:** Official X Ads API docs (`docs.x.com/x-ads-api`) document 3-legged OAuth 1.0a and `ads-api-sandbox.x.com`, while third-party integrators report partial OAuth 2.0 `ads.read`/`ads.write` support and intermittent sandbox deprecation for new self-serve accounts. Both are marked unconfirmed in Section 1.1.
3. **Native `validate_only` flag on TikTok, X, and LinkedIn campaign mutation endpoints:** Meta (`execution_options=["validate_only"]`) and Google Ads (`validate_only: true`) officially document dry-run validation flags on mutation endpoints. No equivalent single-request `validate_only` flag could be confirmed in the public TikTok v1.3, X v12, or LinkedIn `/rest/adCampaigns` endpoint references (those three rely on sandbox/test accounts or `DISABLE`/`PAUSED`/`DRAFT` creation states).
4. **TikTok production QPS tier table:** TikTok officially documents sandbox rate limits (`1 QPS`, `30 QPM`, `1,000 QPD`), whereas exact production per-endpoint QPS tiers are shown inside the authenticated TikTok Developer Portal after app creation.

---

## 4. Nav Decisions & Action Checklist

### Decisions Needed from Nav
1. **Build vs. Vendor (Spec Section 2.3):** Confirm the recommendation to build direct `httpx` adapters in-house (keeping seller OAuth tokens encrypted in Muse's own `muse_private` Supabase schema) rather than paying a commercial aggregator (Unified.to or Zernio) to hold seller tokens.
2. **Write Safety Model Sign-Off (Spec Section 5):** Approve or amend the 7 write guardrails before any mutating code is written:
   - Read-only connection by default (`ads_read`); separate `AD_WRITE_ENABLED` flag for writes.
   - Mandatory `validate_only` dry-run where supported (Meta & Google Ads).
   - Server-signed `WritePreviewToken` locking exact daily budget, currency, and dates.
   - All created campaigns, ad sets, and ads hardcoded to start `PAUSED` (`DISABLE` on TikTok).
   - Seller activates campaigns in native Ads Manager in Phase 1b (or separate confirmation step if in-app activation is ever added).
   - Per-account daily spend cap (`daily_spend_cap_cents`, default `$50.00/day`) + global ceiling `AD_MAX_DAILY_BUDGET_USD=100.0`.
   - Append-only `muse_private.ad_account_audit_log` + instant env-var kill switch.
3. **Token Storage & Encryption Secret (Spec Section 4.3):** Approve the proposed `muse_private.ad_account_connections` and `muse_private.ad_account_audit_log` tables using application-layer `MultiFernet` encryption (`AD_TOKEN_ENCRYPTION_KEY`) on top of Supabase RLS + `service_role`-only grants.
4. **Phase Order (Spec Section 7):** Confirm the priority order: **Meta (Phase 1a Read → Phase 1b Paused Drafts) → Google Ads (Phase 2) → TikTok (Phase 3)**, deferring **X Ads and LinkedIn Ads (Phase 4)** until seller demand justifies their review overhead.

### External Actions Only Nav Can Take (When Ready to Start Phase 1a / Phase 2)
1. **Business Verification Documents:** Gather the legal entity formation / IRS EIN document and verify `@nplusalpha.com` domain control in Meta Business Suite.
2. **Meta Developer App (`developers.facebook.com/apps`):**
   - Create a Business-type App (*Muse Growth Studio*), add **Marketing API** and **Facebook Login for Business**, and create a **Sandbox Ad Account** under *Marketing API → Tools → Sandbox Ad Account Management*.
   - Start **Meta Business Verification** in Business Suite Security Center (2–10 business days), then submit **App Review for Advanced Access to `ads_read`** first (Phase 1a), followed by `ads_management` (Phase 1b).
3. **Google Ads MCC & Cloud Project (`muse-growth`):**
   - Create a Google Ads Manager (MCC) account, open *Admin → API Center*, link Google Cloud project `muse-growth` to get a **Test Access** developer token immediately, create a separate Google Ads Test Manager account, and submit the **Basic Access** application form (3–10 business days).
4. **TikTok Developer Portal (`business-api.tiktok.com`):**
   - Register a developer account, complete TikTok Business Verification, and submit a Marketing API App for review (3–5 business days).

---

Ownership released.
