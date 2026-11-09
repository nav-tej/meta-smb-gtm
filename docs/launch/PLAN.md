# Muse customer launch plan

Updated November 7, 2026, America/Los_Angeles. Target launch November 8, 2026.
Codex owns integration and the release decision. Target is conditional on evidence below.

## Launch promise
A customer can create an account, confirm email, bring a product photo and details, produce and edit a post, save it to their account, resume from another device, and download a usable image and caption. Live AI and paid plans are enabled only after their separate acceptance gates pass.

## Verified baseline
302 offline tests pass. Production serves the repaired desktop/mobile layout. Mobile starter caption recovery and PNG download work. Accounts and Muse provider are unconfigured in production. Editor cloud saving is unwired. Vercel file caches and presenter credits are temporary. See ../creator-polish/CUSTOMER_READINESS.md.

## Ownership and parallel work
| ID | Owner | Write scope | Deliverable |
|---|---|---|---|
| L1 | Codex integration | account.js, accounts services/API, configuration, shared persistence adapter, release docs | Configure existing authorized services, durable workspace contract, owner isolation, concurrency protection, migration/integration, final release |
| L2 | Billing worker | billing.py, new billing migration, test_billing.py, billing-specific tests | Verified payment lifecycle, durable idempotency, subscription ownership and renewal/cancellation handling |
| L3 | Draft worker | creator.js, today.js, creator/today HTML, editor-specific tests | Recoverable device drafts in both editors; explicit account save/load using existing API; preserve editor documents and handle conflicts/account changes |
| L4 | QA worker | new tests/launch_* files, docs/launch/QA.md | Repeatable real-browser customer journey and failure matrix; verify downloads, reload, mobile, signup surfaces; no runtime edits |
| L5 | Codex integration after L1–L4 | generated media storage, run accounting, monitoring, UI release polish | Durable assets, transactional runs/refunds, diagnostics and truthful activation UI |
| L6 | External Claude/Gemini/Hermes if Nav relays | review-only until assigned an exclusive scope | Independent review of integrated results and novice rehearsal; report findings in own launch note |

Started Codex workers are distinct from external Claude/Gemini/Hermes. External delivery is unconfirmed until acknowledged. Worker IDs and status live in STATUS.md. Each worker edits only its scope and reports files, checks, findings and blockers. No worker deploys, pushes, edits secrets or applies remote migrations.

## Implementation order
1. November 7, first wave. Start L2–L4. Codex inventories existing service configuration without exposing values, defines workspace version/merge semantics and preserves current uncommitted fixes.
2. November 7, integration wave. Integrate draft and billing patches, complete durable account storage/assets and quota enforcement. Add monitoring with sanitized request IDs. Test adversarial inputs, duplicate requests, interrupted jobs and recovery.
3. November 8, verification wave. Run isolated account/email/payment sandbox journeys and cross-device recovery. Test real Safari and Chrome on a phone where available. One explicitly approved bounded live AI request verifies delivery and accounting.
4. November 8, release gate. Commit reviewed source after make check. Deploy, repeat public browser smoke checks, record deployment/version, verify rollback procedure and update vault. Invite customers only after all applicable gates pass.

## Acceptance gates
- Fresh signup, confirmation, signin, signout, password reset and session expiry work with configured auth.
- Both editors preserve selected product, destination, copy, selected post and source image on refresh.
- Account A cannot load Account B data. Signout does not silently transfer private drafts. Cloud save conflicts preserve both versions and offer an explicit recovery choice.
- Cross-browser save/load works with separate namespaces for daily and creator drafts; saving one does not erase the other.
- Original photo and generated asset downloads open with expected dimensions and correct content. Durable media survives a new server instance and expired temporary links.
- Duplicate clicks, request retries and payment events cannot double-spend or grant extra entitlements. Failure refunds are idempotent. Durable customer quota is authoritative.
- Checkout success redirect alone grants nothing. Only verified paid events grant access. Pending/failed payment, replay, renewal, cancellation and out-of-order events have regression coverage.
- Service outage and slow network preserve draft and show actionable recovery. No fallback is represented as a personalized generated result.
- Production controls match actual capability. No simulated signup/checkout presented as a real account/payment.
- Keyboard access, dialog focus, readable contrast, touch targets and layouts at 375/390/768/1440px pass. Real-device checks are recorded separately from emulation.
- Error reporting, uptime check, support/contact path, data deletion procedure and privacy terms are present and accurate.
- make check passes; production smoke passes against committed release; rollback target is documented.

## Configuration dependencies and approval boundaries
Use existing project resources where authorized. Inventory first. Missing Supabase auth/database/storage setup, email delivery, Stripe sandbox prices/webhook, Muse credentials and error-alert destination must be reported as concrete blockers. Never invent credentials or put them in notes. Keep DEMO_MODE=true while testing saved workflows. Paid model requests require Nav's existing explicit bounded approval or a new approval. No real customer charges for testing.

## Scope fallback
If payment gates fail, keep purchase actions disabled and consider a free invited beta only after auth, durable saves and core workflow pass. If auth/storage gates fail, remain a clearly labeled demo. Deadline does not override gates.

## Handoff and evidence
Workers write their own status in docs/launch. Record command, result, tested environment, timestamp and remaining uncertainty. Tests against mocks do not establish service configuration. The coordinator integrates first, then independently checks normal browser entry points. Historical hackathon constraints and old file reservations are superseded by this plan for this sprint.
