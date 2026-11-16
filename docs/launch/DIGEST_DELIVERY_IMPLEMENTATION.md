# Digest delivery implementation plan — November 14, 2026

Owner: Codex planning. Base:7ed43af; preview remains frozen. This is a plan, not deployed delivery. Gemini owns promotion/editor follow-up separately. Existing Resend/Supabase integrations remain the target; no new service provisioning or remote changes in this task.

## Product boundary
Batch2A preferences are drafts. Activation must be a separate authenticated action with verified destination email and clear cadence/window summary. Pausing draft preferences is not an unsubscribe. Weekly, biweekly and monthly windows use the existing tested schedule calculator; never promise exact local delivery time unsupported by the cron. Keep legacy subscriptions operating without silently attaching private account memory.

## Ordered implementation slices
1. Durable delivery state: additive migration for account-bound subscriptions and scheduled-slot delivery ledger. Unique(subscription_id, scheduled_slot); frozen payload/reference, lease owner/expiry, attempt count and pending/claimed/accepted/failed/uncertain states. Owner-scoped reads; server-only dispatch/claim transitions. Preserve prior migrations and workspace extras. Verify SQL and concurrent claims in disposable local Postgres; mocks alone are insufficient.
2. Activation/preferences: verified session derives account identity; resolve verified recipient server-side. Explicit activate/pause/unsubscribe controls with honest current status independent of draft settings. Require expected-version concurrency checks. Legacy email-only subscription migration must be opt-in or verified mapping; do not infer identity from arbitrary email input.
3. Renderer: reuse digest_preview.py and approved saved account evidence. No crawl/model calls on dispatch or empty cache. Missing/stale/failed observations remain explicit. Email uses authenticated workspace link initially; do not emit localStorage handoff IDs or promise exact cross-device editor restoration. Escape all customer content and validate URL schemes.
4. Dispatcher: atomic due-slot claim, frozen body, bounded retry with stable provider idempotency key. Recheck unsubscribe before sending. Distinguish rejection from unknown acceptance. Provider accepted/database failure must enter reconciliation, not blind resend. Verify current Resend idempotency retention and retry behavior against official docs before implementation. Describe the unavoidable unsubscribe-after-dispatch boundary.
5. Activation rollout: separate reviewed migration, configuration, sender-domain checks and one explicitly authorized test email. Preview can show drafts while delivery remains disabled. No broad cron change until due-window tests and hosting constraints are verified. Production enablement follows independent review, not completion of local mocks.

## Required tests
Fake-clock weekly/biweekly/monthly,31st/leap-year,DST and missed-run catchup; stable slots after retry or preference edit; two concurrent workers claim once; crash before/after provider acceptance; unsubscribe during claim; unauthorized/cross-account access; verified-email mismatch; empty/stale evidence; safe HTML/links; no sample leakage; zero Muse/crawl calls; no real email. Browser activation/pause/error wording must match actual server state. Local SQL result and mock-provider result reported separately.

## Proposed scope for later build
New delivery service and tests, additive migration, src/api/digest_email.py and digest settings UI, config only for explicit feature gating. Preserve existing preview behavior and avoid promotion/editor files. Do not begin remote migrations, email sends or cron activation under this planning document.

## Done and next
Prepared from DIGEST_PLAN_REVIEW.md and existing Batch2A acceptance. No runtime changes/tests required for this documentation-only plan. Next: read current sender/subscription source, verify provider contracts using appropriate service skills, then claim a separate isolated delivery worktree and implement slice1 with local database evidence. Gifting remains queued, not part of either current assignment.
