# Argon Report — Meta Connect Follow-ups (`config_id`, Callback Error Redirects & Plain Seller Copy, Nov 20, 2026)

- **Branch:** `gemini/meta-connect-followups-nov20`
- **Worktree:** `/private/tmp/muse-meta-connect-followups-nov20`
- **Base commit (`origin/claude/ux-gap-ad-loop-nov17`):** `f35431e1e0f002ac5f6fc468c39750f3219b55a1` (`f35431e`)
- **Implementation commit:** `96ceb03ba6e5bd3ef483990f541aa592e2e650fc` (`96ceb03`)
- **Default runtime posture:** `AD_CONNECT_ENABLED=false` (read-only Meta routes remain unregistered unless explicitly enabled; zero live calls made to `graph.facebook.com` or `www.facebook.com`, zero Meta App Dashboard mutations, zero Vercel env mutations, zero Supabase migrations applied).

---

## 1. Files Changed (Within Exclusive Write Scope)

| File | Summary of Change |
|---|---|
| `src/config.py` | Added `meta_login_config_id: str = ""` (`META_LOGIN_CONFIG_ID`) next to `meta_app_id` / `meta_app_secret`. |
| `.env.example` | Documented that Meta app `"Muse Growth Studio"` (App ID `1113987174851049`) already exists with `META_APP_ID` and `META_APP_SECRET` set in Vercel, and added `META_LOGIN_CONFIG_ID=` with setup notes. |
| `src/services/ad_connections.py` | Updated `build_meta_oauth_authorize_url()` to send `config_id=<META_LOGIN_CONFIG_ID>` and omit `scope` when `meta_login_config_id` is non-empty, while keeping `scope=ads_read` when empty; replaced technical `AdConnectionError` strings with plain seller-facing sentences containing none of `"token"`, `"API"`, `"Marketing API"`, `"ads_read"`, `"server"`, `"configured"`, `"OAuth"`, or `—`. |
| `src/api/ad_accounts.py` | Replaced JSON error responses on `GET /api/v1/ad-accounts/meta/callback` with `302` redirects (`Cache-Control: no-store`) to `/?ad_connect_error=<code>#tab-bids` over a fixed allowlist (`cancelled`, `expired_state`, `wrong_account`, `invalid_state`, `no_ad_accounts`, `signin_required`, `connect_failed`), always clearing `muse_ad_oauth_state` (including when signed-out or unverified); replaced technical route `detail` strings and `detail=str(err)` in `_fetch_connected_insights` with plain seller sentences. |
| `src/api/static/index.html` | Updated only the `#tab-bids` script: maps `/?ad_connect_error=<code>#tab-bids` to plain seller sentences (including `"You cancelled connecting Meta Ads. Nothing was saved."`), strips `ad_connect_error` from the URL via `history.replaceState`, and removes `"token"`, `"API"`, `"ads_read"`, `"server"`, `"configured"`, `"OAuth"`, and `—` from all seller-visible `#metaConnectBar` and `#campaign-table-caption` strings. |
| `docs/launch/AD_NETWORKS_SPEC.md` | Updated Track 1 (`§4.1` and `§6.1`) to record existing Meta app `"Muse Growth Studio"` (App ID `1113987174851049`, development mode, `"Measure ad performance data with Marketing API"`, Facebook Login for Business, production & preview callback URLs registered, Strict Mode on, `META_APP_ID` & `META_APP_SECRET` in Vercel), documented the Facebook Login for Business Configuration (`config_id`) setup and User access token `code` exchange confirmation with official doc citations, and removed `"create the app"`, `"link your business portfolio"`, and the localhost redirect URI. |
| `docs/launch/ARGON_META_CONNECT_NOV19.md` | Updated Section 4 checklist to mark completed app-creation steps as done (`1113987174851049`) and order the remaining steps around `META_LOGIN_CONFIG_ID`. |
| `tests/test_meta_connect_phase1a.py` | Added offline tests for `META_LOGIN_CONFIG_ID` (`config_id` sent and `scope` omitted when set; `scope=ads_read` and no `config_id` when empty), `302` callback error redirects (`cancelled`, `expired_state`, `wrong_account`, `invalid_state`, `no_ad_accounts`, `signin_required`, `connect_failed` + cookie deletion), plain-wording regex checks across all route `detail` responses, and Chromium browser verification at `375px` and `1440px` across all 7 callback error codes and connected/expired/rate-limit/permission/loaded/disconnected states. |
| `docs/launch/ARGON_META_CONNECT_FOLLOWUPS_NOV20.md` | This engineering report. |

---

## 2. Official Meta Documentation Opened & Read (2026-11-20)

All documentation claims were verified by directly reading the live upstream documentation pages on `2026-11-20`:

1. **Facebook Login for Business — Overview & Configurations (`config_id`)**
   - URL: https://developers.facebook.com/documentation/facebook-login/facebook-login-for-business
   - Page status read on `2026-11-20`: Updated Oct 15, 2026.
   - Confirmed details:
     - Apps using the **Facebook Login for Business** product configure an access token type, assets, and permissions under **Facebook Login for Business -> Configurations**, producing a **Configuration ID** (`config_id`).
     - The manual OAuth dialog request passes `&config_id={config-id}` on `https://www.facebook.com/v25.0/dialog/oauth` (with `client_id`, `redirect_uri`, `state`, and `response_type=code`) instead of `scope`.
     - **User access token vs. System user access token:** When a Configuration is created with **Access Token = User access token** (standard `response_type=code`), the dialog redirects back to `redirect_uri` with an authorization `code` parameter (`?code=...&state=...`) that represents a User access token grant. (By contrast, a System user access token configuration requires `response_type=code,token` and generates a system user token via client-side token exchange.)
2. **Manually Build a Login Flow (Code Grant & Exchange)**
   - URL: https://developers.facebook.com/docs/facebook-login/guides/advanced/manual-flow
   - Page status read on `2026-11-20`: Updated Jun 30, 2026.
   - Confirmed details:
     - Redirecting the browser to `https://www.facebook.com/{api-version}/dialog/oauth` with `response_type=code` returns an authorization `code` to `redirect_uri` on approval or `?error=access_denied&error_reason=user_denied...` on cancel.
     - The authorization `code` is exchanged server-side at `GET https://graph.facebook.com/{api-version}/oauth/access_token?client_id={app-id}&redirect_uri={redirect-uri}&client_secret={app-secret}&code={code}` — the exact endpoint called by `exchange_meta_oauth_code()` in `src/clients/ad_networks/meta.py`.
3. **Long-Lived User Access Tokens (`fb_exchange_token`)**
   - URL: https://developers.facebook.com/docs/facebook-login/guides/access-tokens/get-long-lived
   - Page status read on `2026-11-20`: Updated Jun 30, 2026.
   - Confirmed details:
     - A short-lived **User access token** returned from the authorization `code` exchange is extended to a ~60-day long-lived User access token by calling `GET https://graph.facebook.com/{graph-api-version}/oauth/access_token` with `grant_type=fb_exchange_token`, `client_id`, `client_secret`, and `fb_exchange_token={short-lived-user-access-token}` — the exact second hop in `exchange_meta_oauth_code()`.
     - Because Nav's Facebook Login for Business Configuration selects **User access token** (not System user access token), `exchange_meta_oauth_code()` exchanges the returned `code` and extends the resulting User access token without any change to the token exchange contract.

---

## 3. Offline Verification Gate & Mutation Check

### Baseline Gate (Before Changes, at `f35431e`)

Command:
```bash
DEMO_MODE=true META_MODEL_API_KEY= DEMO_KEY= make PY=/Users/nav/meta-smb-gtm/.venv/bin check
```
- `ruff check .`: `All checks passed!`
- `ruff format --check .`: `283 files already formatted`
- `pytest`: `663 passed, 2 skipped, 1 warning in 192.54s` (`665 collected`)

### Mutation Check (Callback Error Redirect vs. JSON Error Regression)

To prove `test_callback_refuses_cancel_tampered_expired_or_other_users_state_with_302_redirect` fails if `meta_oauth_callback` ever regresses to returning a JSON error response:

1. **Mutation applied temporarily in `src/api/ad_accounts.py` (`meta_oauth_callback`):**
   Replaced `return _callback_error_redirect(err.code, probe=probe)` in `except AdConnectionError as err:` with:
   ```python
   return JSONResponse(
       status_code=err.status_code,
       content={"detail": err.detail, "code": err.code},
   )
   ```
2. **Test command executed:**
   ```bash
   DEMO_MODE=true META_MODEL_API_KEY= DEMO_KEY= /Users/nav/meta-smb-gtm/.venv/bin/pytest tests/test_meta_connect_phase1a.py -k test_callback_refuses -v
   ```
3. **Observed failure output:**
   ```text
   FAILED tests/test_meta_connect_phase1a.py::test_callback_refuses_cancel_tampered_expired_or_other_users_state_with_302_redirect
   AssertionError: assert 400 == 302
    +  where 400 = <Response [400 Bad Request]>.status_code
   ```
4. **Restoration confirmed:**
   Restored `return _callback_error_redirect(err.code, probe=probe)` in `src/api/ad_accounts.py` and re-ran the test (`1 passed in 0.23s`).

### Post-Change Gate (After All Changes)

Command:
```bash
DEMO_MODE=true META_MODEL_API_KEY= DEMO_KEY= make PY=/Users/nav/meta-smb-gtm/.venv/bin check
```
- `ruff check .`: `All checks passed!`
- `ruff format --check .`: `283 files already formatted`
- `pytest`: `663 passed, 2 skipped, 1 warning in 210.60s` (`665 collected`, including all `9 passed` in `tests/test_meta_connect_phase1a.py`)

---

## 4. Nav's Remaining Steps (In Exact Order)

What is already done: Meta app **"Muse Growth Studio"** (App ID `1113987174851049`, development mode) exists with use case `"Measure ad performance data with Marketing API"`, **Facebook Login for Business** added, Valid OAuth Redirect URIs registered for `https://meta-smb-gtm.vercel.app/api/v1/ad-accounts/meta/callback` and `https://muse-preview-nav.vercel.app/api/v1/ad-accounts/meta/callback` with Strict Mode on, and `META_APP_ID` / `META_APP_SECRET` set in Vercel.

Only the following steps remain:

1. **Create the Facebook Login for Business Configuration (`config_id`):**
   - In the Meta App Dashboard for **Muse Growth Studio** (`1113987174851049`), open **Facebook Login for Business -> Configurations** in the left sidebar and click **+ Create configuration**.
   - Name: `Muse Read-Only Ads Insights`.
   - Login variation: **General**.
   - Access token: **User access token** (with expiration set to **60 days**; do **not** choose System user access token).
   - Assets: check **Ad Accounts**.
   - Permissions: select **`ads_read` only** (do not add `ads_management` or `business_management`).
   - Click **Create** and copy the numeric **Configuration ID**.
   - *(Do not connect or link any unrelated business portfolio on your account.)*
2. **Set `META_LOGIN_CONFIG_ID` in Vercel:**
   - Add `META_LOGIN_CONFIG_ID=<copied Configuration ID>` to Vercel Environment Variables (Preview and Production).
3. **Generate and set `AD_TOKEN_ENCRYPTION_KEY` in Vercel:**
   - Generate a fresh URL-safe base64 32-byte Fernet key:
     ```bash
     python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
     ```
   - Set `AD_TOKEN_ENCRYPTION_KEY=<generated key>` in Vercel Environment Variables (Preview and Production).
4. **Apply `supabase/migrations/ad_account_connections.sql` to Supabase:**
   - Run `supabase/migrations/ad_account_connections.sql` in the Supabase SQL Editor (after `supabase/migrations/user_accounts.sql`) and verify `public.ad_account_connections` has RLS enabled (`relrowsecurity = true`).
5. **Enable `AD_CONNECT_ENABLED=true` on a preview deployment first:**
   - Set `AD_CONNECT_ENABLED=true` on the preview environment (`https://muse-preview-nav.vercel.app`) first while keeping `AD_CONNECT_ENABLED=false` on production.
   - Sign in as a verified Muse seller on `https://muse-preview-nav.vercel.app/#tab-bids`, click **Connect Meta Ads**, test both **Cancel** (confirming redirect back to `#tab-bids` with `"You cancelled connecting Meta Ads. Nothing was saved."`) and **Continue** with your personal Meta ad account (`act_<id>`) in development mode, load read-only last-30-day insights into `#tab-bids`, and test **Disconnect**.

---

## 5. What Could Not Be Verified Offline

- The live Meta dialog redirect round-trip against `https://www.facebook.com/v25.0/dialog/oauth` using a real `config_id` issued by Meta App `1113987174851049` and a live personal Meta ad account (`act_<id>`) could not be executed offline because live calls to Meta and dashboard configuration creation are prohibited in this task. All URL parameters (`config_id` vs `scope=ads_read`), `302` callback error redirects, cookie clearing, and `#tab-bids` browser rendering at `375px` and `1440px` were verified offline via `respx` and headless Chromium.

Ownership released.
