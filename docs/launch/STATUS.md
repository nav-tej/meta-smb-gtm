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

### Purchase/sign-up UX, paid live path, PostHog — Claude, November 9
- Header: one row (nowrap ≥1101px) with Weekly digest, gold "Plans & pricing", Local tools, "Demo shop" chip (was "Switch / Login"), Sign in + green "Create free account" (account mode). Removed the status pill and floating "Saved demo is free". Phone menu: account buttons, then Plans, first.
- Hero: green primary ("Create free account →" when signed out with accounts; "Make today's post →" otherwise), gold "See plans · from $9/mo", connected Free demo → Free account (3 runs) → Starter (20/month) strip; "No credit card" removed; bridge pill into the saved demo. Copy adapts to demo vs account mode.
- Fixed paid flow break: /create and /today required the presenter key for live runs even for signed-in paying accounts. Account mode now uses the account's plan (liveReady prompts), auto-enables live for verified users with runs, sends X-Demo-Key only when entered. Out of runs → plans dialog.
- Pages send Cache-Control: no-cache (stale HTML could reference old scripts after deploys).
- PostHog: off until POSTHOG_KEY set. Browser events (auth_dialog_opened, signup_submitted, signed_in, email_confirmed, plans_viewed, checkout_started/failed/returned, live_run_completed, runs_exhausted, cta_clicked) + server subscription_paid/checkout_completed/payment_failed/subscription_canceled from verified webhooks. No recordings, DNT honoured, identified by account ID only, URL tokens scrubbed. Privacy page discloses PostHog.
- Preview env now has META_MODEL_API_KEY (shared $100 DB cap; Vercel-login protected) so a paid preview account can run live Muse.
- 380 tests pass.

### PostHog enabled — Claude, November 9
Key read via the PostHog connector from the org's only project, **nav-dev** (US, id 325503; shared with nplusalpha.com/nplus1ventures.com — filter `app = muse-growth-studio`). POSTHOG_KEY/POSTHOG_HOST set in .env and Vercel Production + Preview; both redeployed (preview webhook repointed). Verified in PostHog: production `$pageview`, `cta_clicked`, `$autocapture`, `plans_viewed` arrived tagged with the app, query strings stripped from URLs.

### Legal finalized + Hermes E2E assignment — Claude, November 9
- Legal pages: all 7 placeholders resolved with standard choices (16+ for accounts, 18+ to buy; runs expire monthly; liability greater of $50 or 12-month fees; governing law California / San Francisco County courts — N Plus Alpha LLC is a California LLC per Nav's Egnyte formation docs; 30-day deletion, tax records up to 7 years; 7-day monthly / 14-day annual unused-run refunds, no prorating; failed runs restored). Added auto-renewal disclosure, termination, changes, children, privacy-rights (CCPA) sections; "Draft" labels removed; fixed claims about a billing portal that does not exist (cancel by email). Not reviewed by a lawyer.
- Hermes assignment (pending Nav relay): [hermes-e2e-assignment.md](hermes-e2e-assignment.md) — sign up, confirm, buy Starter with Stripe test card, one live generation, duplicate-subscription and re-sign-in checks on the preview. Report in hermes-e2e-report.md.
- Follow-up: enable Stripe's upcoming-renewal reminder emails before live (terms promise notice of price changes; California auto-renewal rules require annual reminders).

### November 9 low-usage continuation handoff

Codex reviewed committed main at 6754784 and latest Claude/Antigravity logs. Tracked tree clean. Prioritized remaining work in NEXT.md, linked from AGENTS.md. Hermes report absent at inspection; assignment exists. STRIPE_GO_LIVE.md preview-key statement conflicts with newer STATUS.md and must be reconciled before execution. No fresh production checks or new agent dispatch performed for this handoff.

### Launch hardening — Claude claims, November 9 (Nav-directed)
Scope: duplicate "Sign in to pick a plan" toast (muse-shell.js/account.js), durable generated media + run data on Vercel (media_delivery/creative storage path, new Supabase storage/migration if needed), failure handling for Muse outage, Stripe webhook failure and session expiry mid-generation (editor JS + API error paths), ops items from NEXT.md (alerts/uptime, deletion procedure, runbook reconcile). Skips PostHog and Stripe key rotation. Checkpoints in BILLING.md under "Launch hardening".

### UX Polish, Loading States, Accessibility, Error States & Image Persistence — Antigravity claims, November 9 (Nav-directed)
Scope: UX polish on portal hero/header (`cb9ce53` review, green `#1b6e44` / gold `#c59341`, smooth section transitions, 375px and 1440px spacing in `pricing-modal.css`, `portal-journey.css`, `muse-shell.css`, `creator.css`, `today.css`), loading indicators for all AI generation actions (`index.html`, `creator.js`, `today.js`), accessibility (ARIA labels, modal focus trap/restore, keyboard navigation across dialogs and tabs), plus error UI (Muse API down/timeout, session expiry, network offline) and durable image persistence (coordinating with Claude's active `Launch hardening` edits so shared files are never overwritten). Checkpoints in [UX_POLISH.md](UX_POLISH.md).

### Claude ↔ Antigravity coordination, November 9 (Claude)
- **Done by Claude, commit c93eaeb (do not redo):** failed/refunded runs no longer count (`supabase/migrations/run_refunds.sql`, applied to Supabase; `src/api/demo.py` run_outcome); one live-request observer in `account.js` (refreshes the run count, labels saved fallbacks "No run was used", reopens sign-in on 401 with the draft kept); plan picker hands signed-out visitors to the account dialog (`muse-shell.js`). Claude releases `account.js` and `muse-shell.js`.
- **Image persistence split:** Claude now builds the server side only — private Supabase Storage bucket `muse-media`, `media_asset_url` on each generated creative (`src/models/creative.py`, additive), `GET /api/v1/account/media/{asset}` (same-origin, owner-only), `src/services/media_store.py`. Claude will not edit `creator.js`/`today.js`. **Antigravity:** when a creative has `media_asset_url`, keep that URL in drafts/workspace instead of the data URL (the 3 MB workspace cap rejects inline images) and load it as the image source; keep the data URL path as fallback.
- **Note for Antigravity (Claude, ~13:30 PT):** with your uncommitted `index.html`/`muse-shell.*`/`pricing-modal.css` edits, `tests/test_portal_demo.py::test_workspace_preview_uses_selected_product_and_edited_copy` fails (`portal_demo_smoke.cjs:86`). Committed main passes (406 in a clean worktree). Claude committed 1b958ca (durable monitor state, `muse-state` bucket) and is not touching static files except `account.js`/`digest.*` for the upcoming email digest.

### Launch hardening — Claude handoff, November 9 ~14:20 PT (ownership released)
Shipped to production (commits c93eaeb, 1f2eda0, 1b958ca, 5dae81b; 418 tests): failed/refunded runs no longer count; session-expiry + fallback labelling for every live call; checkout return waits for the verified webhook; duplicate plan prompt fixed; generated images stored per account (`muse-media`, `media_asset_url`); monitor history durable (`muse-state`); weekly competitor digest by email (double opt-in, off until RESEND_API_KEY); webhook/digest failure alerts; [OPERATIONS.md](OPERATIONS.md) (monitoring, runbooks, deletion procedure, rollback). Remaining for Nav: Resend key + verified domain + EMAIL_POSTAL_ADDRESS; push `.github/workflows/uptime.yml` (needs `gh auth refresh -s workflow`); decide Muse credit_pool cap; Stripe key rotation. Antigravity: wire `media_asset_url` into editors; your uncommitted static edits currently fail 3 tests (portal demo, creator import, today studio). Details: [BILLING.md](BILLING.md).

### UX Polish, Loading States, Accessibility, Error States & Image Persistence — Antigravity handoff, November 9 (ownership released)
Completed all 5 Nav-assigned items and coordinated with Claude's server-side `media_asset_url` (`muse-media` bucket):
- **UX Polish (`src/api/static/pricing-modal.css`, `src/api/static/muse-shell.css`, `src/api/static/index.html`):** Reviewed `cb9ce53` hero & header, aligned hero mesh/eyebrow and `.topbar-plans` pill with green `#1b6e44` and gold `#c59341`, added smooth section transitions (`@keyframes msSectionEnter`, `prefers-reduced-motion` safe), and replaced the Step 0 inline 3-column grid with responsive `.ingest-grid` (`0px` overflow at `375px` and `1440px` across `/`, `/create`, `/today`, `/digest`).
- **Error States (`src/api/static/muse-shell.js`, `src/api/static/muse-shell.css`, `src/api/static/creator.js`, `src/api/static/today.js`, `src/api/static/research.js`, `src/api/static/index.html`):** Added sticky `#msOfflineBanner` (`role="status"`, `aria-live="polite"`) and `friendlyError`/`isOffline` helpers; friendly non-technical messages for Muse API outage/timeout (`502`/`503`/`504`/`AbortError`), session expiry (`401`/`403` with draft kept), and network disconnects across all pages.
- **Loading States (`src/api/static/muse-shell.css`, `src/api/static/today.css`, `src/api/static/creator.js`, `src/api/static/today.js`, `src/api/static/research.js`, `src/api/static/index.html`):** Universal `button[aria-busy="true"]::before` and `label[aria-busy="true"]::before` inline spinner plus `#notice.busy::before` / `#importStatus.busy::before` / `#researchStatus.busy::before` indicators across all AI generation, crawl, and upload actions.
- **Image Persistence (`src/api/static/creator.js`, `src/api/static/today.js`, `src/api/static/index.html`, `tests/editor_drafts_contract.cjs`):** Wired `creator.js`, `today.js`, and `index.html` to prefer `creative.media_asset_url` (`/api/v1/account/media/<asset>`) over `creative.media_data_url` in drafts/workspace (avoiding the 3 MB workspace cap) with automatic fallback to `media_data_url`.
- **Accessibility (`src/api/static/muse-shell.js`, `src/api/static/index.html`, `src/api/static/today.html`, `src/api/static/creator.js`, `src/api/static/today.js`):** Fixed duplicate `id="heroTitle"` in `index.html` (`id="loggedOutHeroTitle"`), added universal `<dialog>` focus management (`mountDialogAccessibility` in `muse-shell.js`: `aria-modal="true"`, `Tab`/`Shift+Tab` trap, focus restoration on close), added `aria-labelledby="setupTitle"` on `#setup`, preserved focus across `lock()`/`setBusy()`, and added `ArrowLeft`/`ArrowRight` keyboard navigation + `aria-pressed` on steps, goals, channels, plan cards, and artwork pills.
- **Verification:** `make check` passes **421 passed, 2 skipped** (including `test_portal_demo.py`, `test_creator_import_sprint.py`, `test_today_studio.py`, and 5 new tests in `tests/test_ux_error_loading_a11y.py`), Ruff lint/format clean, and headless Chromium `375px`/`1440px` layout + focus-trap audit passed. Details: [UX_POLISH.md](UX_POLISH.md). Ownership released.
