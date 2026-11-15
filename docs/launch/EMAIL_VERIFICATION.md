# Email verification — Claude checkpoint log

## Resume checkpoint 1 — November 15 2026 ~11:30 PT (start)
- State: scope claimed in STATUS.md; read-only review done; no code edits yet.
- Worktree: `/home/user/muse-email-verify`, branch `claude/email-verification` from `326cc22` (cloud session clone, not Nav's Mac).
- Next: baseline `make check`, then implement.

## Resume checkpoint 2 — November 15 2026 (code edited, tests pending)
- Baseline at `326cc22` in worktree: `make check` → 423 passed, 2 skipped, ruff clean.
- Edited: `src/api/accounts.py` (signup via Supabase `/signup` + confirmation email, new `/resend`, throttle on signup/resend/recover), `src/services/accounts.py` (`throttle_email_send`, `_revoke_unproven_password` in Google callback), `src/api/static/account.js` (resend mode + link, expired-link copy).
- Next: replace `test_signup_auto_confirms_and_signs_in_immediately`, add `tests/test_email_verification.py`, extend `account_ui_contract.cjs`, run `make check`.

## Resume checkpoint 3 — November 15 2026 (tests written)
- Also edited `verify_token`: verification now trusts only Auth's `email_confirmed_at`, not user-writable `user_metadata.email_verified`.
- Tests: new `tests/test_email_verification.py` (25), replaced signup test in `tests/test_account_ui.py`, extended `tests/account_ui_contract.cjs` (resend, confirmation link, expired link).
- `.venv/bin/pytest -q tests/test_email_verification.py tests/test_account_ui.py` → 30 passed. `node tests/account_ui_contract.cjs` → PASSED.
- Same new tests against unmodified `326cc22`: 16 failed (new behavior), 9 passed (preserved behavior) — confirms they discriminate.
- Next: `make check`.

## Handoff — November 15 2026 (ownership released)

### Review findings on the `email_confirm: True` path (`5f4a082`, live since Nov 9)
1. **No proof of address ownership.** `POST /account/signup` created users through the service-key `admin/users` endpoint with `email_confirm: True`, so any typed address became "verified" and got 3 trial runs plus workspace saving.
2. **Bypassed Supabase's own abuse controls.** Admin calls skip Supabase signup rate limits, email-send limits and CAPTCHA. The only limits left on mass account creation were the per-IP live-run limits (10/day, 3/min, rotatable) and the global $100 trial pool. A script could drain that pool and pause live Muse for every real trial user.
3. **Google pre-registration hijack.** An attacker could register `victim@…` with a password. When the real owner later used Google sign-in, the callback signed them into that same account, and the attacker's password still worked, giving read access to the victim's saved workspace and generated media.
4. **Account enumeration.** Signup answered 409 "already exists" for registered addresses.
5. **Self-declared verification.** `verify_token` accepted `user_metadata.email_verified`, which users can write themselves.
6. Root cause of the original sign-in bug was configuration, not code: Supabase `SITE_URL` was `http://localhost:3000`, so confirmation links went nowhere.

### What changed (branch `claude/email-verification`, local commit, not pushed)
- `src/api/accounts.py`: signup calls public Supabase `/signup` with `redirect_to=<app>/account`, returns one identical message for new and existing addresses, sets no session. A provider rejection returns 422 with password guidance. If the hosted project ever auto-confirms (returns a session), signup still works but logs a warning. New `POST /account/resend` (signup confirmation, enumeration-safe). Signup, resend and recover are throttled.
- `src/services/accounts.py`: `throttle_email_send` (per instance: 3 sends per address and 8 per network per 15 min). Google callback replaces the password of an **unconfirmed** existing account before the magic link confirms it, and fails closed if that replacement fails. `verify_token` trusts only `email_confirmed_at`.
- `src/api/static/account.js` + `account.css`: "Resend confirmation email" link in sign-in mode, an email-only resend mode, and expired-link copy that points to resend and reset. The existing hash callback (`#access_token…&type=signup` → `/session` → "Email confirmed") is unchanged and now covered by tests.
- Preserved: sign-in, password reset/update, Google sign-in for confirmed accounts, `/session`, workspace owner binding, live-run gating (`require_verified`).

### Verification (cloud worktree, mocked Supabase/Google, no network)
- `make check`: **448 passed, 2 skipped**, ruff lint/format clean (baseline 423 passed, 2 skipped).
- `tests/test_email_verification.py` (25 tests) against unmodified `326cc22`: 16 fail (new behavior), 9 pass (preserved behavior).
- `node tests/account_ui_contract.cjs`: PASSED (adds resend flow, confirmation-link landing, expired link).
- `tests/launch_account_audit.py` in Chromium: **27/27**. The first run caught a selector clash (`.ma-recover` matched two buttons), fixed with a separate `.ma-resend` class.
- Manual 375px screenshots: sign-in after signup and the resend dialog, 0px horizontal overflow.
- **Not verified:** any real email delivery, the hosted Supabase project, or real Google. None were touched, by instruction.

### Hosted configuration required before deploying (none done here)
1. **Custom SMTP in Supabase Auth.** Per Supabase's docs, the built-in mailer only delivers to project team-member addresses and has a very low hourly cap, so real customers would never receive the link. Use Resend, which is already planned for the digest, with a sender on a verified domain. **This is the release blocker.**
2. **URL configuration.** Set Site URL to `https://meta-smb-gtm.vercel.app`. Add `https://meta-smb-gtm.vercel.app/account` to Redirect URLs, plus a preview pattern if previews need signup. Supabase ignores a `redirect_to` outside the allowlist and falls back to Site URL.
3. **Keep "Confirm email" on** (`mailer_autoconfirm: false`, the state recorded Nov 9).
4. **Keep the default confirmation template**, which uses `{{ .ConfirmationURL }}` and returns tokens in the URL hash. A token-hash/PKCE template needs an `account.js` change first.
5. **Raise Auth email rate limits** once custom SMTP is in place.
6. **Do NOT enable Supabase CAPTCHA yet.** The server does not forward a captcha token, so signup, sign-in, resend and reset would all fail. Turnstile needs a small follow-up change first.
7. **Order:** configure items 1–2, test one real signup on the preview, then deploy this branch. If the code ships before SMTP works, new users get stuck with no email. Rollback is reverting the commit; no data change is involved.

### Migration requirements
- **No schema migration.** No SQL or storage changes.
- **Optional read-only checks before deploy** (Supabase SQL editor, service role):
  - Users who would lose "verified" because they relied only on `user_metadata` (expected 0):
    `select id, email from auth.users where email_confirmed_at is null and raw_user_meta_data->>'email_verified' = 'true';`
  - Candidates confirmed by the old admin path without proof (review by hand; admin-created users have no `confirmation_sent_at`):
    `select id, email, created_at from auth.users where email_confirmed_at is not null and confirmation_sent_at is null and created_at >= '2026-11-09' order by created_at;`
- Existing accounts stay as they are: users confirmed by the old path keep `email_confirmed_at`, stay verified and sign in unchanged. Re-verifying them would be a separate product decision.

### Remaining limits
- The email throttle is per serverless instance (best effort). A durable throttle needs a table and RPC (a migration). Supabase's per-IP limits see every user as the server's IP.
- The trial pool can still be drained by someone with many real inboxes. Per-IP live limits and the $100 cap remain the backstop.

Ownership of the claimed auth scope is released. Codex/coordinator integrates.
