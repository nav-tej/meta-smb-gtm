# Account Audit Fixtures — Nov 16, 2026

- **Timestamp:** 2026-11-16T13:10:00-08:00
- **Owner:** Gemini (QA-only scope via `.tasks/account-audit-fixtures-nov16.txt`)
- **Base Commit:** `f55f688` (`origin/claude/integration-nov16`)
- **Worktree / Branch:** `/tmp/muse-account-audit` (`gemini/account-audit-fixtures-nov16`)
- **Changed Files:** `tests/launch_account_audit.py`, `docs/launch/ACCOUNT_AUDIT_FIXTURES_NOV16.md` (zero runtime code changes)

## Before Patch (Reproduction)
- **Command:** `DEMO_MODE=true META_MODEL_API_KEY= DEMO_KEY= /usr/bin/python3 tests/launch_account_audit.py --output /tmp/account-audit-before.json`
- **Result:** **20 passed, 7 failed** (`exit code 1`)
- **Blocked Cases:** `account-today-isolation`, `account-today-conflict`, `account-today-409-race`, `account-create-isolation`, `account-create-conflict`, `account-create-409-race`, `account-editor-merge` — all 7 blocked by the audit's fail-closed allowlist on `GET /api/v1/seller-memory` and `POST /api/v1/seller-memory/recommend`.

## Fix Summary
- Added explicit, owner-scoped fixtures in `tests/launch_account_audit.py` (`AccountAudit.route`) matching `src/api/seller_memory.py` contracts:
  - `GET /api/v1/seller-memory`: Returns unauthenticated empty contract when signed out; returns owner-specific `owner_id`, `version`, `business_name` (`"Qa A Studio"` vs `"Qa B Ceramics"`), `memory_entries`, and `voice_profile` when signed in; returns `409` on `X-Muse-Owner` header mismatch.
  - `POST /api/v1/seller-memory/recommend`: Returns owner-specific zero-run recommendation payload (`runs_used: 0`); returns `409` on `X-Muse-Owner` header mismatch.
- Added explicit fixture discrimination assertions in `AccountAudit.isolation()` verifying `qa-b` receives `owner_id == "qa-b"` / `"Qa B Ceramics"` (zero `qa-a` or `"Sarabjit"` leakage) and `409` when `X-Muse-Owner: qa-a` is sent while signed in as `qa-b`.
- All other endpoints, external traffic, and model/network calls remain blocked (`fail closed`).

## After Patch Verification (`DEMO_MODE=true META_MODEL_API_KEY= DEMO_KEY=`)
- **Account Audit (real Chromium, all 27 cases):**
  - Command: `DEMO_MODE=true META_MODEL_API_KEY= DEMO_KEY= /usr/bin/python3 tests/launch_account_audit.py --output /tmp/account-audit-after.json`
  - Result: **27 passed, 0 failed** (`exit code 0`), including all 7 `account-*` isolation, conflict, 409-race, and editor-merge cases.
- **Full Offline Gate:**
  - Command: `DEMO_MODE=true META_MODEL_API_KEY= DEMO_KEY= make PY=/Users/nav/meta-smb-gtm/.venv/bin check`
  - Result: `ruff check .` passed, `ruff format --check .` clean (`240 files already formatted`), `pytest` **`601 passed, 2 skipped, 1 warning in 115.16s (0:01:55)`** (`exit code 0`). The 2 skipped tests require local `@electric-sql/pglite` (`BILLING_PGLITE_DIR`).

## Unverified Hosted Requirements
- Offline browser fixtures establish UI/client isolation behavior only; they do not verify hosted Supabase Auth confirmation/binding semantics, custom SMTP email delivery, Site URL / redirect allowlist, Google OAuth, preexisting unconfirmed accounts, Stripe live webhooks, or live Muse/Meta API calls.

## Ownership Release
- QA-only fixture work is complete, committed on `gemini/account-audit-fixtures-nov16`, and pushed for Codex/coordinator review. Ownership is released.
