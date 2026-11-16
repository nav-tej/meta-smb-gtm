# Claude auth handoff — November 16, 2026

Assignment: `.tasks/claude-auth-handoff-nov16.txt` on `origin/codex/coordination-nov16` (read with `git show`; the Mac path is not reachable from this cloud session). Scope: review the existing signup-security work, adversarial offline review of trial eligibility, duplicate signup and retries; fix only owned auth issues. No editor or first-ad files touched. No live Muse calls, emails, hosted Supabase changes, merges or deploys.

## Resume checkpoint 1 — Nov 16 (review done, report written, fix not started; pushed as `d2b3edb`)

### Prior work located (both exist on origin)
| Commit | Branch | What | Changed paths |
|---|---|---|---|
| `6b64a3f` | `origin/claude/email-verification` | Require real email confirmation at signup | `src/api/accounts.py`, `src/services/accounts.py`, `src/api/static/account.js`, `src/api/static/account.css`, `tests/test_email_verification.py`, `tests/test_account_ui.py`, `tests/account_ui_contract.cjs`, `docs/launch/EMAIL_VERIFICATION.md`, `docs/launch/STATUS.md` |
| `b4506d7` | `origin/claude/modest-hamilton-guq82o` (draft PR nav-tej/meta-smb-gtm#2) | First monitor hydrate runs regardless of host uptime | `src/services/durable_state.py`, `tests/test_durable_state.py` |

Both are based on `326cc22` (main) and touch disjoint files. The completion note for `6b64a3f` is `docs/launch/EMAIL_VERIFICATION.md` on that branch. Neither was redone.

### Independent gate (this cloud session, Linux, Python 3.12 venv)
Command, run in a clean checkout of each ref: `DEMO_MODE=true META_MODEL_API_KEY= DEMO_KEY= make PY=.venv/bin check`

| Ref | Result |
|---|---|
| `6b64a3f` | ruff lint + format clean, **448 passed, 2 skipped** |
| `b4506d7` | ruff lint + format clean, **424 passed, 2 skipped** |
| `6b64a3f` merged with `b4506d7` (no conflicts) | **449 passed, 2 skipped** |
| `6b64a3f` + new live-eligibility test (branch `claude/auth-review-nov16`) | ruff clean, **449 passed, 2 skipped** |

Not run here: Node/Chromium account audit (`tests/launch_account_audit.py`), real email delivery, hosted Supabase, real Google. These are fixture/offline results only.

### Verified: unverified accounts cannot get live eligibility
- `verify_token` trusts only Auth's `email_confirmed_at`; user-writable `user_metadata.email_verified` is ignored (existing test).
- Every live or paid path goes through `resolve_account(..., require_verified=True)`: `live_mode` in `src/api/demo.py`, password update and workspace GET/PUT in `src/api/accounts.py`, checkout and portal in `src/api/billing.py`.
- `snapshot()` reads usage only for verified accounts, so `/me` shows `usage: null, live_available: false` for an unconfirmed session.
- The usage RPCs (`muse_usage_status`, `muse_begin_operation`, `muse_finish_operation`) are revoked from `anon`/`authenticated` and granted only to `service_role` (`supabase/migrations/run_refunds.sql:154-159`), so a browser holding an unconfirmed Supabase token cannot call them directly.
- Signup never returns a session for an unconfirmed user, and refuses extra fields such as `user_metadata` (existing tests).
- **New regression test** `test_unconfirmed_session_cannot_start_a_live_run` (`tests/test_email_verification.py`): with `ACCOUNTS_REQUIRED=true`, an unconfirmed session calling `/api/v1/bid-advice?live=true` gets 403 and never reaches `usage_meter.authorize_operation`, and `/me` makes no usage RPC. Previously every live-route test mocked `resolve_account` away. Mutation check: deleting the `email_verified` check in `resolve_account` makes it fail.

### Duplicate signup and retries
- Identical reply for new, existing-unconfirmed and existing-confirmed addresses; no 409. Resend is enumeration-safe.
- Retries are throttled per instance: 3 sends per address and 8 per network per 15 minutes, across signup, resend and reset. Per-instance only (documented limit in `EMAIL_VERIFICATION.md`).

### FINDING (high): email-path pre-registration takeover is still open
`6b64a3f` closed the Google-path hijack but not the same attack through email confirmation.

Upstream Supabase Auth (`supabase/auth` master, `internal/api/signup.go`, the `if user != nil` branch) does **not** change the password when `/signup` is called for an existing unconfirmed address; it only re-sends the confirmation ("do not update the user because we can't be sure of their claimed identity"). Therefore:

1. Attacker signs up `victim@example` with password P_a. Account exists, unconfirmed. Supabase emails the victim a confirmation link.
2. Either the victim signs up later with P_v (gets the identical "check your inbox" reply), uses Resend, or simply clicks the unsolicited link.
3. Clicking confirms the account and signs the victim in. The password is still P_a.
4. The attacker signs in with P_a and has the victim's verified account: trial runs, saved workspace, generated media, billing portal.

Hosted Supabase version was not checked (no hosted access by instruction); the behavior above is from current upstream source.

### Fix options (not implemented; decision needed)
- **A. Rotate on repeat signup (small, partial).** In `/signup`, look up the address (`GET admin/users?filter=<email>`, exact-match in code because the filter is a substring `LIKE`). If it exists unconfirmed, replace its password with the new signup's password before calling `/signup`. Closes step 2's "victim signs up after attacker" case with no extra friction. Does not cover the unsolicited-link click or an attacker re-signing up after the victim.
- **B. Bind confirmation to the signup browser (complete).** At `/signup`, store a random nonce in the user's admin-only `app_metadata` and in an HttpOnly cookie. When `/session` receives a signup-confirmation session, keep the password only if the cookie's nonce matches; otherwise replace the password with a random one and tell the user to set a password through reset. Covers all cases. Cost: a user who confirms on a different device (for example opens the email on their phone) must set a password once.
- **C. Passwordless confirmation.** Collect the password only after the link is clicked. Cleanest model, largest UI change (`account.js`).

Recommendation: B, with A's lookup reused. Only `src/api/accounts.py`, `src/services/accounts.py` and their tests change; `account.js` needs one message for the reset case.

### Decision
Nav chose **option B** and authorized pushing this review branch (no merge, no deploy).

## Checkpoint 2 — Nov 16 (option B implemented and verified)

### What changed (branch `claude/auth-review-nov16`, on top of `6b64a3f`)
- `src/services/accounts.py`:
  - `bind_signup`: after Supabase `/signup`, reads the returned user with the admin API. If it is an unconfirmed account for that exact address, it stores the password just entered and a SHA-256 hash of a random nonce in admin-only `app_metadata.muse_signup_binding`. The raw nonce goes into the HttpOnly, Secure, SameSite=Lax cookie `muse_signup` (path `/api/v1/account`, 2 days). A confirmed address gets Supabase's obfuscated reply with a random id, so the lookup returns 404 and nothing is touched. If the binding cannot be stored, signup fails with 503 (fail closed).
  - `settle_signup_binding`: runs whenever a session is created for a confirmed account with a pending binding. The signup password survives only when the confirmation link lands (`/session`) in the browser holding the latest nonce. Otherwise it is replaced with a random one and the binding cleared. On a landing elsewhere the landing session stays and all other sessions are revoked (`logout?scope=others`). A password sign-in while the binding is still pending means the account was confirmed without a landing (mail scanner, failed landing, or a race), so the password is unproven: it is replaced, every session is revoked (`scope=global`) and sign-in answers 401 asking for a password reset.
  - `_revoke_unproven_password` (Google): also replaces the password and clears the binding for a confirmed account whose binding is still pending.
- `src/api/accounts.py`: `/signup` binds; `/session` settles and adds `password_reset_required: true` when it replaced the password; `/signin` settles first and refuses with 401 when it replaced it.
- `src/api/static/account.js`: a confirmation landing with `password_reset_required` opens the "Update password" form ("Email confirmed. For your security, choose a new password for this account."). The user is already signed in there, so no extra email is needed.
- Tests: `tests/test_email_verification.py` adds a stateful fake of Supabase Auth faithful to upstream `signup.go` (repeat signup keeps the first password; confirmed address gets a random id) and covers: squatter signs up before and after the owner; unsolicited link; owner signed up last keeps their password; confirming on another device; password sign-in before landing refused, including in the squatter's own signup browser; fail closed when the binding cannot be stored or the password cannot be replaced; accounts without a binding unaffected. Four existing tests were updated only for the new call sequence and still check public signup, no `email_confirm`, no session cookie, identical replies. `tests/account_ui_contract.cjs` adds the other-device landing.

### Verification (this cloud session, offline, mocked Supabase)
- `DEMO_MODE=true META_MODEL_API_KEY= DEMO_KEY= make PY=.venv/bin check` → ruff lint clean, 176 files formatted, **458 passed, 2 skipped**.
- Discrimination: with the `src/` changes stashed (tests kept), 10 of the new or updated binding tests fail, and `test_accounts_without_a_binding_are_unaffected` passes, as it should.
- `node tests/account_ui_contract.cjs` → PASSED; with the `account.js` change stashed it fails on the other-device landing.
- **Not run:** `tests/launch_account_audit.py` (Chromium). This container has only Node Playwright, not the Python package, and the environment notes say not to install another Playwright. Run it on the Mac: `/usr/bin/python3 tests/launch_account_audit.py --match account- --output /tmp/muse-auth-audit`.
- **Not verified:** hosted Supabase behavior (version, `app_metadata` merge on admin PUT, `logout?scope=` support), real email, real Google. The fake follows upstream source for these.

### Behavior changes users will notice
- Confirming on a different device or browser than the one used to sign up: signed in, then asked to choose a new password once.
- A mail scanner that opens the link before the owner does: the first password sign-in is refused with a reset prompt.
- Signing up twice with different passwords in the same browser: the latest password works after confirming there.

### Deployment notes (in addition to `EMAIL_VERIFICATION.md`)
- No schema migration. The binding lives in `auth.users.raw_app_meta_data`, which only the service role can write.
- Unconfirmed accounts created before this deploy carry no binding and would keep their signup password on confirmation. Count them before deploy (read-only, service role):
  `select count(*) from auth.users where email_confirmed_at is null;`
  If any exist, either delete them or accept the residual (they are from a period when signup auto-confirmed, so likely none).
- The cookie is `Secure`; previews must be HTTPS (Vercel is).

### Residual risks
- An attacker who controls the victim's mailbox or Google account is out of scope.
- The `muse_signup` cookie holds one address at a time: a browser used to sign up two different addresses keeps the binding only for the latest one; the other confirms as "other device" (password reset once).

### Next step for the coordinator
Review `claude/auth-review-nov16` (based on `6b64a3f`; merges cleanly with `b4506d7`), run the Chromium audit on the Mac, then integrate. Nothing here was merged or deployed.

### Ownership
Released. Auth scope (`src/api/accounts.py`, `src/services/accounts.py`, `src/api/static/account.js`, `tests/test_email_verification.py`, `tests/test_account_ui.py`, `tests/account_ui_contract.cjs`) is free for the coordinator.
