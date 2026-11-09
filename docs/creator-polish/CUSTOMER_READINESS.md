# Customer readiness audit, November 7, 2026

Production is usable as a saved demo and local starter-post tool. It is not ready for paid customer acquisition.

## Verified in production
- Mobile daily-post workflow edits and restores caption after reload.
- Reviewed post downloads a PNG successfully.
- No JavaScript errors during that workflow.
- Account status returns configured=false and live_available=false.
- Readiness reports accounts_configured=false, provider_key_configured=false.
- Prior layout verification covers 375, 390, 768 and 1440px with no horizontal overflow.

## Fixed
- Daily draft now persists selected post, with bounds checking and compatibility for older drafts.
- Added regression coverage for third-post edit recovery and old draft migration.
- Demo profile creation is labeled as a browser-only demo rather than a real signup.

## Launch blockers
- Configure and verify production authentication, email confirmation and recovery.
- Connect editor state to the existing account workspace API. Neither editor currently calls saveWorkspace/loadWorkspace. Establish account isolation and conflict recovery before automatic sync.
- /create currently has no draft persistence.
- Configure Muse provider and verify a bounded authorized live request and failed request refund.
- Stripe checkout completion currently applies a plan without checking payment_status or deduplicating events. Subscription checkout does not attach user metadata to subscription_data, but cancellation handling depends on subscription metadata. Handle renewals, delayed payments, cancellation and out-of-order events before enabling payments.
- Cache, presenter credits and monitor state are per-instance temporary files on Vercel. Durable user entitlements require database-backed enforcement.
- Verify actual signup and checkout against sandbox services before public activation.
- Establish monitoring, durable generated-asset storage and rollback verification.

All 302 offline tests and lint/format gates pass. Provider billing, customer payment, signup email delivery and cross-device recovery have not been exercised against configured services.
