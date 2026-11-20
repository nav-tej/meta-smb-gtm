# Claude integration — November 16, 2026

Assignment: `.tasks/claude-integrate-nov16.txt` on `origin/codex/coordination-nov16` (`735e1f0`). Codex released integration scope to Claude; Nav relayed it. Cloud session (Linux container), not Nav's Mac.

## Checkpoint 1 — start (no changes yet)
- Branch `claude/integration-nov16` created from `f342db7` (origin/codex/integration-input-nov16), worktree `/tmp/claude-0/integ`.
- Inputs present on origin (`git cat-file -e`): `f342db7`, `6b64a3f`, `d2b3edb`, `d0a6eec`, `00e8536`, `b4506d7`.
- `f342db7` contains main `326cc22`. `00e8536` sits on divergent `b442d5e`; only that one commit is applied.
- Overlap with `f342db7` (changed since `326cc22`): auth commits touch `src/api/accounts.py`, `src/services/accounts.py`, `src/api/static/account.js`, `account.css`, `tests/account_ui_contract.cjs`, `tests/test_account_ui.py`, `docs/launch/STATUS.md`; guest commit touches `src/api/static/creator.js`, `creator.html`. Monitor fix `b4506d7` has no overlap.
- Plan: baseline gate on `f342db7`, cherry-pick `6b64a3f`, `d2b3edb`, `d0a6eec`, `00e8536`, `b4506d7` in that order, resolve, gate, browser checks where available.

## Checkpoint 2 — cherry-picks applied (gate has 3 failures, investigating)
- Independent baseline on `f342db7` (this container, real Chromium via Python Playwright 1.63.0 = preinstalled Node Playwright build, `PLAYWRIGHT_BROWSERS_PATH=/opt/pw-browsers`): **564 passed, 2 skipped** (the 2 need a local PGlite install). Matches the builder report. One earlier run without Playwright showed 1 unidentified failure that did not reproduce in 3 reruns (539 passed, 27 skipped each).
- Applied on `claude/integration-nov16`: `9107b60` (=6b64a3f), `1a7b665` (test adaptation), `160c619` (=d2b3edb), `6950a3b` (=d0a6eec), `4694f3b` (=00e8536), `e311997` (=b4506d7).
- First integrated gate: 3 failed, 598 passed, 2 skipped: `test_account_ui.py::test_recover_and_password_reset_flow`, `test_editor_idea_handoff.py::test_all_5_demo_ideas_in_creator_e2e[1440]`, `test_guest_journey_fixes_e2e.py::test_guest_journey_report_fixes_e2e`.

## Checkpoint 3 — integrated gate green (`6536348`)
Root causes of the 3 failures in the first integrated gate, each fixed in its own commit without weakening an assertion:
1. `test_recover_and_password_reset_flow` (from `b3f11c3`): its Supabase fake did not answer the `GET user` lookup that the landing now makes for a pending signup binding (`d0a6eec`). Fixed in `7a2e55f`: fake returns a normal confirmed user; added assertions that recovery changes no password and revokes no session.
2. `test_guest_journey_report_fixes_e2e` (from `00e8536`): written when `/create` opened on the sample artist; the integrated base (`7fab453`) starts guests in their own workspace ("My studio artwork"). Fixed in `c102dd2`: asserts the own-workspace default, then opens the sample shop and runs every original check. Mutation: with pre-guest `creator.js` the test fails.
3. `test_all_5_demo_ideas_in_creator_e2e` (intermittent): a real race in the test, present on `f342db7` too (1 of 8 runs there, ~4 of 14 after `00e8536`). Applying an idea or restoring a draft unticks the review box (base) and clears the export notice (`00e8536`), asynchronously after DOMContentLoaded; the test ticked and exported immediately after navigation. Fixed in `6536348`: wait for network idle and a resolved workspace mode first. 0 failures in 15 runs; guest test 0 failures in 10 runs.

Gate: `PLAYWRIGHT_BROWSERS_PATH=/opt/pw-browsers DEMO_MODE=true META_MODEL_API_KEY= DEMO_KEY= make PY=.venv/bin check` → ruff clean, 240 files formatted, **601 passed, 2 skipped** (PGlite), 164.9 s. `node tests/account_ui_contract.cjs` → PASSED.

## Final — November 16 (ownership released)

### Result
Branch `claude/integration-nov16` on origin. Base `f342db7`. Commits on top, in order:
| Commit | Source | Note |
|---|---|---|
| `9107b60` | `6b64a3f` | conflicts resolved (below) |
| `1a7b665` | new | duplicate-signup test adapted to enumeration-safe signup |
| `160c619` | `d2b3edb` | clean |
| `6950a3b` | `d0a6eec` | clean |
| `4694f3b` | `00e8536` only | conflicts resolved (below) |
| `e311997` | `b4506d7` | clean |
| `7a2e55f`, `c102dd2`, `6536348` | new | test fixes, see checkpoint 3 |
No branch tip was merged wholesale; nothing from the Mac workspace is included.

### Conflict resolutions
- `src/services/accounts.py`: auth's email throttle and logger kept; `"/welcome"` (from `f342db7`) kept in `SAFE_NEXT_PATHS`.
- `src/api/accounts.py` signup: auth version taken. `f342db7` still created users with the service key and `email_confirm: True` (any typed address became verified) and answered 409 for registered addresses (account enumeration). Kept from `f342db7`: sign-in `next_path` onboarding routing, Google callback `/welcome` routing, server-owned onboarding record on workspace PUT. Sign-in now settles the signup binding first, then routes.
- `src/api/static/account.js`: `f342db7`'s `setMode` (retry count, preserved email, active-tab styling, account sign-out button, error flag) kept; auth's `resend` mode, link and email-only fields added into it. Resend keeps the typed email like the other modes. The client's 409 signup branch is now unreachable (server no longer returns 409) and was left in place.
- `src/api/static/account.css`: `f342db7` stylesheet kept; only auth's `.ma-resend` rule added.
- `tests/account_ui_contract.cjs`: both blocks kept (signup retry feedback; resend and confirmation landing).
- `tests/test_account_ui.py::test_duplicate_signup_returns_409_and_never_signs_in` (from `b3f11c3`) replaced by `test_duplicate_signup_never_signs_in_and_never_reveals_the_account`: same guarantees (no sign-in, no session cookie, identical reply for any password) plus identical to a new address, no password grant.
- `docs/launch/STATUS.md`: both histories kept; auth's two Nov 15 entries appended after `f342db7`'s.
- `src/api/static/creator.js`: `f342db7` handlers kept; guest `clearNotice()` added next to `syncFrameControls()`; guest clipboard fallback applied to `f342db7`'s newer caption text (which includes the CTA line), not the older one.
- `src/api/static/creator.html`: `f342db7` layout kept; guest placeholder added to the product name, worded neutrally ("Name of the product you’re promoting") instead of "e.g. Ek Onkar print", because guests now start in their own workspace and sample names must not appear in a real seller's form. The guest test only requires a placeholder.

### Security review of the signup binding (as integrated)
- Admin password update happens only after an admin GET shows an unconfirmed account whose email matches exactly; a confirmed address gets Supabase's random-id reply and a 404, so it is never touched.
- `app_metadata` holds only a SHA-256 hash of a random nonce; the password goes to Auth's admin password field, never into metadata. Raw nonce only in an HttpOnly, Secure, SameSite=Lax cookie scoped to `/api/v1/account`.
- Mismatch on the confirmation landing: password replaced with a random one, other sessions revoked, user asked to set a new password while signed in by the link. Password sign-in with a pending binding: password replaced, all sessions revoked, 401 with reset prompt.
- No code deletes unconfirmed users (no Auth DELETE anywhere in `src/`).
- Demo/sample content separation, first-ad (manual Ads Manager guidance only), and promotion copy were not changed by this integration.

### Unresolved hosted provider semantics (not verifiable offline)
- Hosted Supabase Auth version: repeat signup keeping the first password, obfuscated random-id reply for confirmed addresses, `app_metadata` merge with `null` deleting a key, and `logout?scope=others|global` were confirmed in upstream `supabase/auth` source only.
- Real confirmation email delivery (custom SMTP), Site URL / redirect allowlist, and real Google sign-in: see `EMAIL_VERIFICATION.md`; still the release blocker.
- Unconfirmed accounts created before deploy carry no binding. Count with a read-only query before deploy; do not delete automatically.

### Tests (this container; independent of builder reports)
- Baseline `f342db7`: **564 passed, 2 skipped**.
- Integrated `6536348`: **601 passed, 2 skipped**, ruff clean, 240 files formatted, real Chromium. Command: `PLAYWRIGHT_BROWSERS_PATH=/opt/pw-browsers DEMO_MODE=true META_MODEL_API_KEY= DEMO_KEY= make PY=.venv/bin check`.
- Named browser journeys, run individually, all PASSED in real Chromium (15 tests, none skipped): workspace modes own/sample isolation (375, 1440), signup follow-up (signed-out privacy reset, mobile forgot password, first export), shop image suggestions with actual PNG exports, first-ad 4-step workflow with draft reload and PNG, promotion guidance handoff, seller memory, guest journey.
- `node tests/account_ui_contract.cjs`: PASSED.
- `tests/launch_account_audit.py` (real Chromium): **20 passed, 7 failed — identical on unmodified `f342db7`**, so not caused by this integration. All 7 are the `account-*` isolation cases, blocked by the audit's own allowlist on `GET /api/v1/seller-memory` and a seller-memory POST (Batch 1 endpoints the audit harness has no fixtures for). Those 7 cases are therefore **unverified** by this audit; own/sample isolation is covered by the passing `test_workspace_modes_e2e.py` and `test_seller_memory_e2e.py`. Fix belongs to the QA harness owner: add seller-memory fixtures in `tests/launch_account_audit.py`.

### Not run / environment notes
- 2 skips need a local `@electric-sql/pglite` install (`BILLING_PGLITE_DIR`).
- Python Playwright 1.63.0 was installed into this worktree's own venv to match the preinstalled browser; no repository dependency files changed.
- No live Muse, email, ads, hosted migration, credentials or auth settings were used or changed. Not merged to main; not deployed.

### Next executable step (coordinator / Nav)
1. Review `claude/integration-nov16` at its head.
2. On the Mac: `DEMO_MODE=true META_MODEL_API_KEY= DEMO_KEY= make PY=<local venv>/bin check`.
3. Add seller-memory fixtures to the account audit, then rerun `python3 tests/launch_account_audit.py`.
4. Configure Supabase SMTP and URLs (`EMAIL_VERIFICATION.md`) before any preview with real signup; then one real signup on a preview.

Ownership of the integration scope is released.
