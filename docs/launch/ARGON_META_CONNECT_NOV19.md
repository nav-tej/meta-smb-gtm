# Argon Report: Meta Read-Only Connect (Phase 1a, Offline) & Live API Version Audit

- **Agent:** Argon (Gemini 4 Argon, in Antigravity)
- **Date:** 2026-11-19
- **Base ref:** `origin/claude/ux-gap-ad-loop-nov17` at `9b103ef90169c96ae04ef9c16364c14fdda3ca16`
- **Branch:** `gemini/meta-connect-nov19`
- **Worktree:** `/private/tmp/muse-meta-connect-nov19` (main checkout `/Users/nav/meta-smb-gtm` untouched)

---

## 1. Step 0: Live API Versions Found (With Direct Links)

Directly opened the live vendor version and sunset documentation pages on 2026-11-19 and updated `docs/launch/AD_NETWORKS_SPEC.md`, `src/config.py`, `.env.example`, and `src/clients/ad_networks/meta.py`:

1. **Meta Graph API & Marketing API:**
   - [Marketing API Versioning (`developers.facebook.com/documentation/ads-commerce/marketing-api/overview/versioning`)](https://developers.facebook.com/documentation/ads-commerce/marketing-api/overview/versioning) (accessed 2026-11-19) states: ***"The current version of the Marketing API is v27.0"*** and shows `https://graph.facebook.com/v27.0/me/adaccounts` in its request examples.
   - [Marketing API Changelog (`developers.facebook.com/docs/marketing-api/changelog`)](https://developers.facebook.com/docs/marketing-api/changelog) (accessed 2026-11-19) lists **`v27.0`** (released **November 4, 2026**, expiration TBD) and **`v26.0`** (released **July 29, 2026**, expiration TBD).
   - [Graph API Version Schedule (`developers.facebook.com/docs/graph-api/changelog/versions`)](https://developers.facebook.com/docs/graph-api/changelog/versions) (accessed 2026-11-19) lists **`v26.0`** (released **July 29, 2026**, expiration TBD) and **`v25.0`** (released **February 18, 2026**, Graph API expiration July 29, 2028) at the top of the Graph API table, and its Marketing API table confirms that Marketing API `v21.0` expired **September 9, 2025**, `v22.0` expired **February 19, 2026**, `v23.0` expired **June 9, 2026**, and `v24.0` expired **October 6, 2026**.
   - **Code change:** Replaced the hard-coded version string with `meta_graph_api_version: str = "v27.0"` in `src/config.py` (`META_GRAPH_API_VERSION=v27.0` in `.env.example`), read dynamically by `meta_graph_base_url()` and `meta_oauth_dialog_url()` in `src/clients/ad_networks/meta.py`.

2. **Google Ads API:**
   - [Google Ads API Deprecation and Sunset (`developers.google.com/google-ads/api/docs/sunset-dates`)](https://developers.google.com/google-ads/api/docs/sunset-dates) (accessed 2026-11-19) lists **`v26 (Latest)`** (released **October 14, 2026**, minor releases `v26.1` on October 28, 2026 and `v26.2` on November 11, 2026, sunset **November 2027**), along with currently active versions **`v25`** (released July 22, 2026, sunset August 2027), **`v24`** (released April 22, 2026, sunset May 2027), and **`v23`** (released January 28, 2026, sunset February 2027). Versions `v22` and earlier (including `v18`) are already sunset.

3. **Spec citation & claim audit (`docs/launch/AD_NETWORKS_SPEC.md`):**
   - Kept `(accessed 2026-11-19)` **only** on the 14 official documentation pages and 8 raw GitHub `LICENSE` files directly opened in this task (including `bengoism/agent-ads`, confirmed as **MIT License** at `https://raw.githubusercontent.com/bengoism/agent-ads/main/LICENSE`).
   - Marked all pages not directly opened in this task as `**[Unconfirmed]**`.
   - Removed the unsourced claim that Meta and Google carry >90% of consumer small-business ad spend.

---

## 2. Files Delivered (Within Exclusive Write Scope)

| File | Change |
|---|---|
| `docs/launch/AD_NETWORKS_SPEC.md` | Updated with live API version audit (`v27.0`/`v26.0` for Meta, `v26` for Google Ads), strict citation policy (`accessed 2026-11-19` only on directly opened pages), Nav's approved decisions, Phase 1a architecture, and required production + `https://muse-preview-nav.vercel.app` OAuth redirect URIs. |
| `supabase/migrations/ad_account_connections.sql` | New migration for `muse_private.ad_account_connections` (connections table only; no write audit log in Phase 1a), RLS enabled, revoked from `public, anon, authenticated`, and `service_role`-only RPCs (`muse_ad_connection_upsert`, `muse_ad_connection_list`, `muse_ad_connection_get`, `muse_ad_connection_set_status`, `muse_ad_connection_disconnect`). Written only, never applied. |
| `supabase/migrations/ad_account_connections_rollback.sql` | Companion rollback dropping the 5 RPC functions, RLS policy, and `muse_private.ad_account_connections`. |
| `src/services/ad_connections.py` | New service providing `MultiFernet` token encryption (`encrypt_token`, `decrypt_token`, `rotate_token_ciphertext`) with comma-separated `AD_TOKEN_ENCRYPTION_KEY` and `key_version` tracking; user-bound HMAC-SHA256 OAuth state signing/verification (`sign_meta_oauth_state`, `verify_meta_oauth_state`); and `save_meta_connection`, `list_meta_connections`, `load_meta_connection`, `mark_meta_connection_status`, `disconnect_meta_connection`, `complete_meta_oauth_callback`. |
| `src/api/ad_accounts.py` | New router `/api/v1/ad-accounts/meta/{connect,callback,accounts,insights,disconnect}` gated behind `AD_CONNECT_ENABLED=true` (returns 404 when false) and requiring a signed-in, email-verified seller. Requests `ads_read` only, maps connected insights into `CampaignPerformance`, and marks connections `expired` on Graph code `190`. |
| `src/api/main.py` | Registered `ad_accounts.router` behind `AD_CONNECT_ENABLED=true` and added `"ad_connect_enabled": settings.ad_connect_enabled` to `/api/v1/readiness`. |
| `src/clients/ad_networks/meta.py` | Uses `settings.meta_graph_api_version` (default `"v27.0"`), adds `exchange_meta_oauth_code()` via form-encoded `POST` to `/oauth/access_token` (short-lived → long-lived `fb_exchange_token`), and attaches a redacting log filter on `httpx` so tokens/secrets never appear in logs. |
| `src/config.py` & `.env.example` | Added `meta_graph_api_version: str = "v27.0"`, `meta_app_id: str = ""`, `meta_app_secret: str = ""`, and `ad_token_encryption_key: str = ""`. |
| `requirements.txt` & `pyproject.toml` | Added `cryptography>=43.0`. |
| `src/api/static/index.html` | Added `#metaConnectBar` ("Connect Meta Ads (read-only)" button, `#metaAdAccountSelect` connected-account picker, "Load Connected Insights", and "Disconnect") and its script handlers inside `#tab-bids` only, hidden unless the server reports `ad_connect_enabled: true`. |
| `tests/test_meta_connect_phase1a.py` | New offline `respx` + real headless Chromium (`375px` and `1440px`) test suite (9 tests). |
| `docs/launch/ARGON_META_CONNECT_NOV19.md` | This completion report. |

---

## 3. Verification Results

### Full Offline Check Gate (`DEMO_MODE=true META_MODEL_API_KEY= DEMO_KEY= make PY=/Users/nav/meta-smb-gtm/.venv/bin check`)

| Stage | `ruff check .` | `ruff format --check .` | `pytest` |
|---|---|---|---|
| **Baseline (`9b103ef`)** | All checks passed! | 275 files already formatted | **653 collected: 651 passed, 2 skipped**, 1 warning in 187.09s |
| **After (`gemini/meta-connect-nov19`)** | All checks passed! | 279 files already formatted | **662 collected: 660 passed, 2 skipped** (+9 new tests in `tests/test_meta_connect_phase1a.py`), 1 warning in 193.30s |

### Real Browser Verification (`375px` and `1440px` in `test_tab_bids_browser_375_and_1440_flag_off_and_on`)
- **Flag OFF (`ad_connect_enabled: false`):** Verified in headless Chromium at `375x900` and `1440x900` that `#metaConnectBar` is hidden, zero horizontal overflow occurs, zero page errors occur, and `#tab-bids` (`#csvUploadLabel`, `#runBidsBtn`, `#bidsFirstAdLink`) looks and behaves identically to baseline.
- **Flag ON (route-mocked `ad_connect_enabled: true`):** Verified at `375x900` and `1440x900` that `#metaConnectBar`, `#connectMetaAdsBtn` ("Connect Meta Ads (read-only)"), `#metaAdAccountSelect`, `#loadMetaInsightsBtn`, and `#disconnectMetaAdsBtn` render without horizontal overflow; an expired-token (`401`, `meta_token_expired`) response updates `#connectMetaAdsBtn` to `"Reconnect Meta Ads (read-only)"` and prompts the seller in `#metaConnectStatus`; and clicking `"Disconnect"` removes the account from the picker.

---

## 4. What Nav Must Do Before Anyone Can Connect a Real Account

1. **Create the Meta Developer App (`https://developers.facebook.com/apps`):**
   - Create a Business-type App (*Muse Growth Studio*), link it to your Meta Business Portfolio, and add the **Marketing API** and **Facebook Login for Business** products.
2. **Register OAuth Redirect URIs:**
   - Under **Facebook Login for Business → Settings → Valid OAuth Redirect URIs**, add:
     - `https://meta-smb-gtm.vercel.app/api/v1/ad-accounts/meta/callback` (production)
     - `https://muse-preview-nav.vercel.app/api/v1/ad-accounts/meta/callback` (protected preview)
     - `http://localhost:8000/api/v1/ad-accounts/meta/callback` (optional local testing)
3. **Apply the Database Migration in Supabase:**
   - Execute `supabase/migrations/ad_account_connections.sql` in the Supabase SQL Editor (rollback is `supabase/migrations/ad_account_connections_rollback.sql`).
4. **Set Environment Variables in Vercel:**
   - Generate a Fernet key (`python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`) and set `AD_TOKEN_ENCRYPTION_KEY`.
   - Set `META_APP_ID`, `META_APP_SECRET`, and `META_GRAPH_API_VERSION=v27.0`.
   - Flip `AD_CONNECT_ENABLED=true` on the preview or production deployment when ready to expose the routes and button.
5. **Business Verification & App Review (for external sellers):**
   - Admin/developer accounts with a role on the Meta App (and Sandbox Ad Accounts created under *Marketing API → Tools → Sandbox Ad Account Management*) work immediately with Standard Access to `ads_read`.
   - For external sellers, complete Meta Business Verification in Business Suite Security Center and submit App Review for **Advanced Access** to `ads_read`.

---

## 5. What Could Not Be Verified

1. **Live Meta OAuth handshake and live `/v27.0/me/adaccounts` / `/insights` responses:** Per task boundaries, no live calls were made to Meta (`graph.facebook.com` / `www.facebook.com`) and no Meta Developer App exists yet. All HTTP interactions were verified offline with `respx` against fixtures shaped from Meta's documented payloads.
2. **Live execution of `supabase/migrations/ad_account_connections.sql` against remote Postgres:** Per task boundaries, no migrations were applied to Supabase. The RPC contract was verified offline against an in-memory `service_role` RPC double in `tests/test_meta_connect_phase1a.py`.
3. **Direct inspection of `tiktok/tiktok-business-api-sdk` license file and TikTok developer portal pages:** Opening `https://raw.githubusercontent.com/tiktok/tiktok-business-api-sdk/main/LICENSE` (and `/master/LICENSE`) returned HTTP 404, and TikTok portal docs require a client-rendered portal session; both are marked `**[Unconfirmed]**` in `docs/launch/AD_NETWORKS_SPEC.md`.

---

Ownership released.
