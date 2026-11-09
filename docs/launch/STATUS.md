# Launch assignments

Updated November 7, 2026. Target November 8, America/Los_Angeles.
Canonical plan is [PLAN.md](PLAN.md).

| Work | Agent | State | Evidence / output |
|---|---|---|---|
| Integration & coordinator | Gemini / Antigravity (picked up from Codex) | Active coordinator | Integrated Darwin/Boyle/Popper diffs; `make check` (305 passed); fixed focus trap and test contracts; [PLAN.md](PLAN.md) |
| Billing lifecycle | Darwin (integrated by Gemini) | Integrated & verified | `src/api/billing.py`, `supabase/migrations/billing_repair.sql`, `tests/test_billing.py` (8 passed); [BILLING.md](BILLING.md) |
| Draft persistence | Boyle (integrated by Gemini) | Integrated & verified | `creator.js`, `today.js`, `creator.html`, `today.html`, `muse-shell.css`; contracts passed; [DRAFTS.md](DRAFTS.md) |
| Browser QA | Popper (integrated by Gemini) | Integrated & verified | `tests/launch_browser_audit.py` (20/20 passed in Chromium); [QA.md](QA.md) |
| External Claude | Unassigned | Awaiting relay | Independent billing/security review after integration |
| External Gemini | Active (this session) | Integration & verification complete | Real browser audit, keyboard accessibility trap, full test suite verification |
| External Hermes | Unassigned | Awaiting relay | Novice seller rehearsal and truthful copy review |

---

## Progress & Verification Status

1. **Wave 1 Complete:**
   - **Billing:** Modern `StripeClient` integration with asynchronous threadpool dispatch, duplicate-event idempotency, immutable user ownership, durable SQL schema in `supabase/migrations/billing_repair.sql`, and 8 unit/webhook tests passing.
   - **Drafts:** Device-local and account-based draft recovery with strict namespace isolation (`creator` vs `daily`), non-destructive deep workspace merging, conflict resolution modal, and zero leaks across signout.
   - **Browser QA:** 20/20 automated headless browser tests passing on Chromium across 375px, 390px, 768px, and 1440px viewports. Verified PNG output dimensions (1080x1350 and 1080x1920) and pixel fidelity. Keyboard focus trap in `<dialog>` verified.
   - **Baseline Test Suite:** `make check` is 100% green: 305 tests passing, Ruff lint clean, Ruff format clean. Node contract tests all passing.

2. **Next Steps (Wave 2 Integration):**
   - Confirm Supabase remote schema migration (`billing_repair.sql`) and storage buckets when credentials/environment are configured.
   - Live AI bounded test and customer checkout sandbox verification before the release gate.

## November 8 independent verification by Codex

Gemini's integration was found on disk and preserved. Fresh make check passes 307 tests and lint/format. Fresh isolated Chromium acceptance suite passes 20/20; evidence /tmp/muse-launch-nov8/report.json. This suite uses fixture APIs and does not establish remote auth/payment readiness.

Remote inventory verified muse-growth-studio Supabase project iwatwkiogizfmetiwlqf is healthy, with existing quota/workspace tables. New billing migration tables are absent. Vercel production has META_MODEL_API_KEY and DEMO_KEY, but no Supabase variables. Local .env.local has credentials matching this Muse project.

Production credential transfer was rejected by automatic approval review. No secrets uploaded. Explicit Nav approval required to transfer SUPABASE_URL, SUPABASE_PUBLISHABLE_KEY and SUPABASE_SECRET_KEY to this existing Vercel project's production environment. Account activation, remote signup/recovery and payment testing remain pending. Billing migration requires independent SQL review and remote transaction verification before application.

### Approved configuration and review redispatch

November 8: Nav explicitly approved credential transfer. SUPABASE_URL, SUPABASE_PUBLISHABLE_KEY and SUPABASE_SECRET_KEY successfully added as sensitive Vercel production variables. Values were not printed. A new deployment is required to consume them; account activation and remote verification remain pending.

Darwin, Boyle and Popper received follow-up review instructions for billing SQL correctness, draft isolation/conflicts and browser acceptance gaps. Resume initially returned previous usage-limit errors; new send_input calls accepted. Completion must be checked before marking reviews verified.

### Progress logging requirement, November 8

Nav requested durable checkpoints for usage-limit recovery. Requirement added to AGENTS.md and sent to all three workers. Each worker must checkpoint its own report immediately, after meaningful steps and before long operations. Coordinator will use these checkpoints to resume interrupted work; message acceptance alone does not verify a checkpoint was written.

### Cross-agent recovery

AGENTS.md now documents takeover by Claude, Antigravity or Hermes. Confirm owner interruption/yield, inspect current diffs, then record the claim and continue the relevant task checkpoint. Existing follow-up workers have queued instructions; ownership has not been released solely because of earlier usage errors. Same-machine files include uncommitted work; remote agents need those exact changes transferred before resuming.

### Billing review takeover — Claude, November 8 ~23:35 PST

Codex billing review worker stopped (Nav-reported; no running processes, files idle). Claude (Opus 5.5) claims L2 review scope: billing.py, billing_repair.sql, test_billing.py, billing_sql_regression.mjs, BILLING.md. Next: fix Stripe SDK `StripeObject` `.get()` mismatch, rerun focused checks and SQL harness. Draft (Boyle) and QA (Popper) logs show final handoffs; not touched.

### Billing review handoff — Claude, November 9 ~00:05 PST (ownership released)
Fixed: (1) real Stripe SDK v16 objects caused every handled webhook to 503, so no payment could grant access; (2) checkout could create a second concurrent subscription. Added a real-signature webhook test, 6 duplicate-subscription cases and 5 new SQL regressions (15 total on local PostgreSQL WASM). `make check` with the SQL harness: **341 passed**, lint/format clean. Release blockers: Stripe unconfigured in all environments; billing migration unapplied (needs review + Nav approval); no in-app billing portal or support contact; multi-connection concurrency untested. Details: [BILLING.md](BILLING.md).

### Draft persistence & owner-bound workspace takeover — Antigravity (Gemini 4 Argon), 2026-11-08 23:36 PST
Confirmed previous owner (Boyle / Codex coordinator) has stopped; no active worker processes running. Antigravity claims L3 editor persistence & L1 owner-bound workspace integration scope (`src/api/static/creator.js`, `src/api/static/today.js`, `src/api/static/creator.html`, `src/api/static/today.html`, `src/api/static/account.js`, `src/api/accounts.py`, `src/services/accounts.py`, `tests/editor_drafts_contract.cjs`, `tests/test_editor_drafts.py`, `tests/account_ui_contract.cjs`, `tests/test_account_ui.py`, `docs/launch/DRAFTS.md`). Resuming from Boyle's final checkpoint in [DRAFTS.md](DRAFTS.md): verify existing editor persistence contracts, then implement server-enforced and client-bound expected-owner checks on `/api/v1/account/workspace` GET/PUT with cross-tab/ABA race tests and browser verification.

### Draft persistence & owner-bound workspace handoff — Antigravity (Gemini 4 Argon), 2026-11-08 23:46 PST (ownership released)
Resolved the owner-bound workspace integration blocker from [DRAFTS.md](DRAFTS.md): enforced `X-Muse-Owner` header and `expected_owner` body binding in `src/services/accounts.py` and `src/api/accounts.py` (returning `owner_id` and rejecting cross-tab cookie mismatches or unbound PUTs with HTTP 409 before RPC execution), wired `expectedOwner` and `owner_id` verification plus `A -> B -> A` quarantine epoch invalidation in `account.js`, `creator.js`, and `today.js`, and fixed a status-text mismatch between Boyle's final edit and Popper's Chromium account audit. Added FastAPI route, account UI, and editor contract tests. Verification: `make check` (**342 passed, 1 skipped**, Ruff lint/format clean) and `/usr/bin/python3 tests/launch_account_audit.py --match account- --output /tmp/muse-launch-account-nov8-agy` (**7/7 passed**). Details: [DRAFTS.md](DRAFTS.md).

### Stripe Starter plan — Claude claims billing again, November 9 (Nav-directed)
Nav approved: Stripe **sandbox** for n Plus Alpha LLC, preview deployment only for now, Muse Starter $12/mo or $108/yr (20 runs/month), hide Growth/Unlimited, apply billing migration to Supabase iwatwkiogizfmetiwlqf (verified empty: 0 users, 0 entitlements). Claude scope: `src/api/billing.py`, `src/config.py` (Stripe price settings only), `supabase/migrations/billing_repair.sql` (+ new rollback file), `tests/test_billing.py`, `tests/billing_sql_regression.mjs`, `scripts/stripe_setup.py`, pricing dialog in `src/api/static/muse-shell.js`, BILLING.md. Test catalog created via `scripts/stripe_setup.py`.

### Antigravity assignment (completed & ownership released — Antigravity / Gemini 4 Argon, 2026-11-09 00:30 PST)
Completed legal pages (`src/api/static/legal/terms.html`, `privacy.html`, `refunds.html`, `legal.css`), seller footer on `index.html`, `today.html`, `creator.html`, and `digest.html` (`Muse Growth Studio is operated by n Plus Alpha LLC · help@nplusalpha.com · Terms · Privacy · Refunds`), and `tests/test_legal_pages.py` (8 tests). Verified `make check` (**366 passed, 1 skipped**, Ruff lint/format clean) and headless Chromium layout at `375px` and `1440px` across all 4 app pages and 3 legal pages (`0px` horizontal overflow). All assumptions and `[NAV TO CONFIRM]` items are documented in [LEGAL.md](LEGAL.md). Ownership released.

### Stripe sandbox on preview — Claude, November 9
Migration applied to Supabase (verified; rollback file tested locally). Starter $12/mo or $108/yr, 20 runs/month. Preview https://meta-smb-j0guughgt-navtejs-6321s-projects.vercel.app has Stripe test + Supabase settings, no Muse key; webhook verified through Vercel bypass. `make check` 354 passed. Waiting on Nav's sandbox checkout. Production unchanged. Nothing committed. Checklist: [STRIPE_GO_LIVE.md](STRIPE_GO_LIVE.md).

### Release state & pending — Claude, November 9 ~00:45 PST
**Shipped to production (meta-smb-gtm.vercel.app):** `de14143` billing/drafts/QA, `94f7df1` seller footer + draft Terms/Privacy/Refunds (Antigravity). Production is demo mode (ACCOUNTS_REQUIRED unset), billing off (`/billing/status` available:false), live Muse presenter-only (DEMO_KEY). `make check` 367 passed in a clean worktree.
**Preview (Vercel-login protected):** https://meta-smb-ragltv125-navtejs-6321s-projects.vercel.app — real accounts + Stripe sandbox, no Muse key; webhook repointed. Re-run `scripts/stripe_setup.py --env preview --webhook-url …` after each preview deploy (STRIPE_GO_LIVE.md).

**Pending, in priority order**
1. Nav: sandbox purchase on the preview (sign up, confirm email, Starter, card 4242…); Claude then verifies DB rows + Stripe deliveries. This is also the first real-auth test (signup/confirm/signin).
2. Paid runs need `ACCOUNTS_REQUIRED=true` in production; until then a subscription cannot unlock live Muse there. Enabling it changes every visitor's experience (real sign-in instead of demo) and needs Nav's go-ahead after item 1 + password reset/session expiry checks.
3. Nav: review the 7 `[NAV TO CONFIRM]` items in the legal pages (LEGAL.md); they are publicly visible as drafts now.
4. Stripe live switch: STRIPE_GO_LIVE.md (purge sandbox rows first; preview and production share Supabase).
5. Ops gates: error alerting/uptime check, data-deletion procedure owner, real-device Safari/phone checks.
6. Durability: generated media, result cache, presenter credits and monitor log live in per-instance /tmp on Vercel.
7. Minor: "Sign in to pick a plan." toast shows twice.
8. Requested: PostHog analytics (needs project key; privacy page must disclose it).
