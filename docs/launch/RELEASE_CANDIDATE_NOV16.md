# Release Candidate Verification & Preview Deployment — Nov 16, 2026

- **Timestamp:** 2026-11-16T13:18:00-08:00
- **Owner:** Gemini (executing `.tasks/codex-release-candidate-nov16.txt`)
- **Reviewed Exact SHA:** `27c1f50` (`origin/gemini/account-audit-fixtures-nov16`, descending cleanly from integrated `f55f688`)
- **Release Branch:** `release/candidate-nov16`
- **Ancestry & Status:** `git merge-base --is-ancestor f55f688 27c1f50` verified (`ANCESTRY_OK`); working tree clean at deploy.

## Builder & Contract Evidence Reviewed
- Claude integration (`f55f688` / `6536348`): `601 passed, 2 skipped` (`make check`, real Chromium), `node tests/account_ui_contract.cjs` passed.
- Gemini QA account audit (`27c1f50`): `27 passed, 0 failed` (`tests/launch_account_audit.py`, real Chromium, owner-scoped seller-memory GET/POST fixtures + `409` mismatch discrimination).
- Gemini local PGlite DB gate (`056e114` on `origin/gemini/db-gates-nov16`, based on `27c1f50`): `69 passed, 0 skipped` (`tests/test_billing.py` + `tests/test_digest_email.py` with `BILLING_PGLITE_DIR` pointing to local `@electric-sql/pglite`), confirming both formerly skipped SQL regression tests pass against real local Postgres.
- Direct contract check on `27c1f50`: `node tests/account_ui_contract.cjs` -> `ACCOUNT UI CONTRACT PASSED`.

## Hosted Auth & Environment Inspection (Read-Only, Zero Secrets Disclosed)
### Vercel (`navtejs-6321s-projects/meta-smb-gtm`, `vercel env ls`)
- **Configured on Preview & Production:** `SUPABASE_URL`, `SUPABASE_PUBLISHABLE_KEY`, `SUPABASE_SECRET_KEY`, `ACCOUNTS_REQUIRED`, `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `STRIPE_SECRET_KEY`, `STRIPE_PRICE_STARTER_MONTHLY`, `STRIPE_PRICE_STARTER_ANNUAL`, `STRIPE_WEBHOOK_SECRET`, `META_MODEL_API_KEY`, `POSTHOG_KEY`, `POSTHOG_HOST`.
- **Configured on Production only (missing on Preview):** `EMAIL_TOKEN_SECRET`, `DEMO_KEY`.
- **Missing on both Preview & Production:** `RESEND_API_KEY`, `DIGEST_FROM_EMAIL` (if app-level sending is used).

### Supabase Auth (`GET /auth/v1/settings` & `GET /auth/v1/admin/users`, read-only)
- **Configured / Verified:**
  - `external.email = True`
  - `disable_signup = False`
  - `mailer_autoconfirm = False` ("Confirm email" is ON, matching `docs/launch/EMAIL_VERIFICATION.md`)
  - **Preexisting users:** `total_users = 6`, **`unconfirmed_users = 0`**, `confirmed_without_sent_at = 4` (existing confirmed accounts retain `email_confirmed_at`; zero unconfirmed accounts lack signup bindings).
- **Mismatch / Disabled:**
  - `external.google = False` in Supabase Auth settings (even though `GOOGLE_CLIENT_ID`/`GOOGLE_CLIENT_SECRET` exist in Vercel).
- **Unverified via GoTrue public/admin API (requires Supabase Dashboard or Management API):**
  - Custom SMTP (Resend) configuration & sender domain verification (**remains release blocker** before enabling public real signup)
  - `SITE_URL` (`https://meta-smb-gtm.vercel.app`) & `URI_ALLOW_LIST` (`https://meta-smb-gtm.vercel.app/account` + preview pattern)
  - Auth email rate limits & CAPTCHA disabled status

## Protected Preview Deployment
- **Target:** Protected Preview (`vercel deploy --yes`, Deployment Protection ON; no main merge, no production promotion)
- **Preview URL:** `https://meta-smb-iueugs8zd-navtejs-6321s-projects.vercel.app`
- **Inspect URL:** `https://vercel.com/navtejs-6321s-projects/meta-smb-gtm/C1txD64LzM6WhL8Xu6k6P1fVrmxM`
- **Build Status:** `Ready in 20s` (deployed from exact SHA `27c1f50`)
- **Protected Preview GET Checks (via `vercel curl`):**
  - `GET /api/v1/health` -> `HTTP 200` (`{"status":"ok"}`)
  - `GET /api/v1/readiness` -> `HTTP 200` (`{"default_mode":"saved","live_unlock_configured":false,"provider_key_configured":true,"provider_verified":false,"accounts_required":true,"accounts_configured":true,"trial_runs":3}`)
  - `GET /` -> `HTTP 200` (`161183` bytes)
  - `GET /create` -> `HTTP 200` (`18431` bytes)
  - `GET /first-ad` -> `HTTP 200` (`11269` bytes)
  - `GET /today` -> `HTTP 200` (`14319` bytes)
  - `GET /digest` -> `HTTP 200` (`12087` bytes)
- **Rollback References:**
  - Prior Preview: `https://meta-smb-fft3iikv0-navtejs-6321s-projects.vercel.app` (`7ed43af`)
  - Current Production (unchanged): `https://meta-smb-ey7g1mcto-navtejs-6321s-projects.vercel.app` (`https://meta-smb-gtm.vercel.app`)

## Ownership Release
- Release candidate preparation, hosted config inspection, and protected preview deployment are complete. Ownership is released for bounded hosted acceptance / Nav release decision.
