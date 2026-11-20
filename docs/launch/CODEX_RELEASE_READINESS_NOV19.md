# Release readiness — November 19, 2026

Coordinator: Codex. Preparation only; no merge or promotion authorized.

## Candidate and independent evidence

Source: `claude/ux-gap-ad-loop-nov17`, pinned `29904ce2f16df282f13acd739f9f2b7a6d0854a0`. Contains `3afab27` and `bf32ba2` (ancestry checked). `release/nov19` starts at that exact SHA; its only additional change is this report. Main at review: `326cc22d144be1dd30190e4c6a52dfb34b445639`. Later agent work is excluded.

Codex authored neither pass 13 nor the /create merge; the checks below are independent execution, not copied builder results. Local Chromium fixtures do not establish hosted Auth/email behavior.

- Full gate: `DEMO_MODE=true META_MODEL_API_KEY= DEMO_KEY= make PY=/Users/nav/meta-smb-gtm/.venv/bin check` passed on first attempt: **636 passed, 2 skipped, 1 warning in 179.79s**, lint/format clean. Skips require local PGlite; warning is the expected excessive-image rejection test. No flake or rerun. Log `/tmp/muse-preview-d-gate.log`; session 22933 completed.
- Real Chromium: `DEMO_MODE=true META_MODEL_API_KEY= DEMO_KEY= /usr/bin/python3 tests/launch_account_audit.py --output /tmp/muse-preview-d-account` **27 passed, 0 failed**; same environment with `tests/launch_browser_audit.py --output /tmp/muse-preview-d-guest` **20 passed, 0 failed**. Session 31973 completed; evidence directories contain reports/screenshots.
- `node tests/account_ui_contract.cjs`: ACCOUNT UI CONTRACT PASSED.
- `node tests/today_studio_contract.cjs`: DAILY STUDIO CONTRACT PASSED.
- Protected preview D: https://meta-smb-21zg6y020-navtejs-6321s-projects.vercel.app ; [Inspect](https://vercel.com/navtejs-6321s-projects/meta-smb-gtm/BhvS5EjTLR57S85vMAzn7eW7SpEy). Deployment `dpl_BhvS5EjTLR57S85vMAzn7eW7SpEy`, READY, target preview, protection `vercel_authentication`. Deploy from clean 29904ce succeeded (CLI exit 0; no --prod or env overrides). Plain health GET returns 302 to vercel.com/sso-api; authenticated `vercel curl` returns 200 for health, readiness, /, /create, /first-ad, /today, /digest; /creator returns 307. No auth bypass links created. Deployment session 74704 and GET session 43515 completed.
- Alias: Nav confirmed Hermes idle and explicitly approved the move; `https://muse-preview-nav.vercel.app` now points to preview D. Plain health GET returns302 to vercel.com/sso-api; authenticated health returns200. Protection remains active.
- Draft PR: https://github.com/nav-tej/meta-smb-gtm/pull/4 (`release/nov19` → `main`, draft, not merged).

## What sellers get

Based on the source diff from main and `CLAUDE_UX_GAP_NOV16.md`, `CLAUDE_AUTH_HANDOFF_NOV16.md`, `ANTIGRAVITY_CREATE_ANY_BUSINESS_NOV18.md`, `ANTIGRAVITY_AD_LOOP_NOV16.md`, `ANTIGRAVITY_STATE_COPY_NOV18.md`, `GEMINI_DIGEST_PREVIEW.md` and `GEMINI_SHOP_IMAGES.md` in this candidate.

- **Account and sign-up:** real email confirmation replaces automatic confirmation; resend and password recovery paths explain the next step. Browser-bound signup confirmation protects against a password registered by someone else. Confirming on another device asks the owner to choose a password. Private workspace state stays scoped to its account.
- **Setup:** bring a website or use the clearly labeled artist sample; review extracted context and choose Products, Services or Both. Completed setup can be reopened and edited for zero runs. Suggested competitors use the seller's own website, cost one approved run, and arrive unselected; a guest's setup survives the sign-in prompt.
- **Home:** unfinished setup is distinguished from the sample. A Start here card links to the first competitor analysis or today's studio. Ask Muse answers in place with actionable moves, including leads for services businesses. Saved memory, per-draft instructions and competitor context help tailor recommendations. Sample prices and timestamps stay labeled as sample evidence.
- **Today:** own listings are imported when appropriate without replacing an existing draft. Services businesses get service/offer posts and Inquiries as their goal, not artist copy. The artist sample retains its artwork and example posts. Editable copy, photo selection, draft recovery and exports remain available.
- **Create:** own workspaces use offer/photo language; sample workspaces keep the artist example. Website image suggestions supplement local uploads. Upload captions describe the actual local photo; original-photo editing/export and account drafts remain available. No claim that a generated variation is the untouched original.
- **First ad:** a reachable, guided manual preparation flow links from home and editors, preserves workspace context and uses business-appropriate wording. It does not connect an ad account, publish an ad, or spend a budget automatically.
- **Competitor analyses:** analyze the competitor website with the seller's real saved context instead of an Ad Library URL or the sample artist's description. Existing analyses can be viewed free; new analyses require an explicit run. Suggested matches still need seller review.
- **Digest:** personal HTML/text previews use approved memory and saved observations. Cadence/topic/timezone choices are draft preferences, not evidence that scheduled delivery is active. Resend delivery and full scheduling remain separate from the preview experience.

## Hosted requirements and evidence

### Migration: optional for this exact runtime

`git diff --stat origin/main..29904ce -- supabase/` shows only `research_cache.sql` and `research_cache_rollback.sql` (30 added lines). Read-only check for Nav:

```sql
select to_regclass('muse_private.research_cache');
```

A null result means absent. No hosted query or migration was executed by this task. `src/services/research_cache.py` uses JSON files in `data/research/cache`, not this SQL table; `src/api/intel.py` calls that filesystem cache and catches errors into an Ad Library error response. Therefore absence of the SQL table does not cause a missing-table runtime error and migration is optional for this candidate. This is not proof of durable research caching: Vercel's source directory may be unwritable, directory creation is outside the cache write exception handler, and files are not shared across instances. Do not promise reliable persistent cache savings on hosted until separately implemented/verified.

If a later approved release needs the table: verify the existing `muse_private` schema/service-role grants from `supabase/muse_schema.sql` first, then apply `supabase/migrations/research_cache.sql`, then run the read-only check. Do not replay all old migrations blindly. The rollback drops this cache table and its indexes/dependencies with CASCADE; it destroys cache entries, not account workspaces. No migration applied here.

### Environment: names only

Compared `src/config.py` with main and searched added source for direct environment reads. Only new settings: `TRIAL_DURATION_DAYS` (default 14) and `TRIAL_REQUIRES_CARD` (default false). Neither appears in `vercel env ls production`; defaults apply. No new mandatory setting was found.

Production names observed November 19: GOOGLE_CLIENT_SECRET, GOOGLE_CLIENT_ID, EMAIL_TOKEN_SECRET, ACCOUNTS_REQUIRED, STRIPE_WEBHOOK_SECRET, STRIPE_PRICE_STARTER_ANNUAL, STRIPE_PRICE_STARTER_MONTHLY, STRIPE_SECRET_KEY, POSTHOG_HOST, POSTHOG_KEY, SUPABASE_SECRET_KEY, SUPABASE_PUBLISHABLE_KEY, SUPABASE_URL, DEMO_KEY, META_MODEL_API_KEY. Values stayed hidden. Presence is not validation of a credential or provider setup. RESEND_API_KEY and DIGEST_FROM_EMAIL are absent from that list; do not advertise functioning digest email delivery. No environment files were read or downloaded; no settings changed.

### Email confirmation: required before production approval

Hosted custom SMTP, Site URL and redirect allowlist remain UNVERIFIED, not assumed absent. Nav should inspect the existing Supabase project `iwatwkiogizfmetiwlqf`:

- Authentication → Email → SMTP Settings: custom SMTP enabled, host/port/auth configured for the intended mail service, and sender email on a verified domain. Passing evidence is a confirmation and recovery email delivered to an ordinary non-team seller inbox, with working links; configured fields alone are insufficient.
- Authentication → URL Configuration: Site URL `https://meta-smb-gtm.vercel.app`; Redirect URLs permit `https://meta-smb-gtm.vercel.app/account` and any deliberately supported preview `/account` URL. `src/api/accounts.py:callback_query` builds that account return URL. Do not redirect sellers to localhost.
- Authentication → Sign In / Providers → Email: confirm email enabled. Email templates → Confirm signup uses the supported confirmation URL flow; recovery template also returns to the app. No template changes in this task.
- Google Cloud Console → APIs & Services → Credentials → the configured OAuth client: exact authorized redirect URI for production `/api/v1/account/oauth/google/callback`; preview alias callback is reported registered in the assignment, but a successful hosted round trip is still required. Muse's Google flow uses its own configured client; Supabase's Google-provider toggle alone does not prove this path works.

These are inspection/acceptance instructions, not authorization to send email or change settings. Production confirmation delivery is a release blocker until Nav supplies evidence or authorizes the bounded test.

### Existing accounts

`tests/test_email_verification.py` covers accounts without a signup binding (line 756), confirmed Google accounts unchanged (465), and password reset/update preserved (250, 261). `tests/test_account_ui.py` covers Google callback (213) and recovery/update (413). The reviewed auth report documents the same compatibility. Confirmed preexisting accounts retain ordinary sign-in; an account with a pending binding may intentionally need password recovery. Real provider behavior is UNVERIFIED by these mocked tests.

The older report's prose says a password is stored in app_metadata; the reviewed implementation instead updates Auth's password field and stores a nonce hash in binding metadata. Do not interpret the historical prose as current storage behavior. Prior unconfirmed-account inventory is historical; no accounts were deleted or modified. Nav should confirm current unconfirmed-account policy before release if that population has changed.

### Dependencies

Pillow>=11.0 is included in requirements; successful preview build is required evidence that the hosted dependency installation works. The preview build completed successfully and protected route checks passed, establishing installation/runtime evidence for this candidate, not pixel-level hosted acceptance.

## Rollback and production smoke (instructions only)

Read-only `vercel inspect meta-smb-gtm.vercel.app` on November 19 resolves to READY production `meta-smb-ey7g1mcto-navtejs-6321s-projects.vercel.app`, deployment `dpl_8deG8F3rw1CtKSxU3kBA5Bz3idor`, created November 10. Production is unchanged by this task.

If Nav later authorizes rollback: Vercel project → Deployments → select that deployment → Rollback (or the equivalent Vercel rollback command targeting that URL). Recheck public GETs and one Nav sign-in. Deployment rollback does not undo database migrations, environment changes or user data. The optional SQL rollback is separate and needs its own approval; it is unnecessary to restore this runtime.

After an approved promotion, GET-only smoke: `/api/v1/health`, `/api/v1/readiness`, `/`, `/welcome`, `/create`, `/first-ad`, `/today`, `/digest` return 200; `/creator` returns 307 to `/create`. Check sample/own labeling, static assets and mobile layout without generation. Nav signs in once with his existing account, confirms the correct workspace and recovery/setup entry points, and signs out to verify private context disappears. No spend, email send, ad publication or workspace write is part of that smoke.

## Go / no-go

Current decision: NO-GO for production promotion until the following are satisfied.

1. Independent gate, audits, contracts and protected preview checks pass; report every failure/flake without rerunning it away.
2. Hermes tests exact preview D using `docs/launch/hermes-ux-gap-acceptance.md`: all applicable free/non-mutating UI and isolation items 1–31 pass, with particular attention to digest account context (17–18), setup/own-versus-sample behavior (19–27), services posts (28–29) and create/first-ad wording (30–31). Run/crawl steps require their separate approval; unexecuted steps stay UNVERIFIED. Item 32 needs Nav's existing Google account and an approved alias move; hosted OAuth cannot be called passed without the round trip.
3. Research migration proven optional for this exact build (code review above), or separately approved/applied/verified if chosen. Hosted cache durability remains a known limitation.
4. Production confirmation/recovery delivery and correct return URLs confirmed; existing-account sign-in and hosted Google acceptance confirmed. No automatic email sends here.
5. Nav explicitly approves merging the draft PR to main.
6. Nav separately approves promotion. Neither approval has been granted by this preparation task.

Outstanding builder findings intentionally excluded: pass 14's empty /today brief action buttons, draft-button styling and time-budget ranking; other agents' competitor research and ad-network work. This candidate does not silently include later commits.

## Resume checkpoint

All independent local checks and protected preview GETs completed. No source edits, .env reads, settings changes, migration, merge or promotion. Alias move approved by Nav and completed, with protection and authenticated health reverified. Next external step: Hermes acceptance on the exact D URL, then Nav hosted-auth evidence and separate merge/promotion decisions. Ownership released for release preparation; alias move is complete and ownership is released.
