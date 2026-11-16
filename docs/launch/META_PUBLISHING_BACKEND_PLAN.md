# Meta account connection and publishing backend — November15

Status: proposed contract, not implemented or enabled. Codex owns this plan; Luna Beauvoir inventories reusable code. Gemini owns first-ad guided UI; Claude owns signup security; Hermes owns read-only guest acceptance. User reports assignments relayed; individual acknowledgment remains separate. No runtime/auth/UI file takeover.

## Product contract
Keep three capabilities separate: prepare/export locally; connect an authorized Meta account; create paused remote objects. Activation is a separate explicitly confirmed operation. A manual Ads Manager handoff never implies automatic transfer. Muse Spark/Image credentials do not authorize Marketing API access. This plan expands the historical read-only bid scope only through separately reviewed publishing routes; bid advice still never applies changes.

## Proposed API boundaries (not existing routes)
- POST /api/v1/meta-connections/start: verified Muse account, CSRF checks; return authorization URL with one-use server-held state bound to user/session, short expiry and allowlisted callback destination.
- GET /api/v1/meta-connections/callback: validate state and session binding before exchange; store tokens server-side encrypted, never in query logs, localStorage, analytics or client responses. Fail closed on expired/denied grants. Exact OAuth configuration and required permissions need official verification before implementation.
- GET /api/v1/meta-connections: minimal connection status, expiry/reconnect reason and capabilities; never return credentials.
- GET /api/v1/meta-connections/{id}/assets: authorized ad accounts/Page identities and eligible Instagram identities. Server checks connection ownership and current asset access; never trust posted account IDs alone.
- DELETE /api/v1/meta-connections/{id}: revoke/delete local authorization and cancel queued operations; disclose that existing ads do not automatically stop. Provider revocation behavior requires verification.
- POST /api/v1/campaign-drafts: validate product, creative, destination, chosen objective, currency, budget type/amount and explicit dates. Save versioned account-owned draft. Approved facts only; no inferred sales tracking status.
- POST /api/v1/campaign-drafts/{id}/validate: read-only readiness and blocking reasons. Do not report approved or publishable unless required checks succeeded.
- POST /api/v1/campaign-drafts/{id}/publish-paused: expected_version + client operation key; server-owned durable operation record. Confirm account/Page/currency/objective and current authorization. Create campaign/adset/creative/ad with PAUSED statuses where supported, verify returned state; never activate as fallback.
- POST /api/v1/campaign-drafts/{id}/activate: separate consent bound to immutable draft hash, exact selected account, budget type/amount/currency/dates and returned remote IDs. Require a fresh confirmation after any change. Show pending review/rejected/paused/delivering states from Meta, not synthetic success.
- GET /api/v1/campaign-operations/{id}: owner-scoped progress, remote IDs, partial failure/reconciliation status and next safe action.

## Spend and failure semantics
Use decimal validation and verified currency units; do not assume all currencies have two decimal places. Distinguish daily budget from lifetime budget; planned spend is not a guaranteed total charge cap. Exact platform budget constraints must be verified. Never label estimated ROAS as observed results. Ads may remain pending review after activation.

Use one durable operation per account-owned draft version and operation kind. Atomic claim/lease plus recorded remote IDs after each step. Duplicate requests return the same operation. A timeout after a write is UNKNOWN, not permission to blindly repeat the create. Reconcile remote state before retry; where lookup cannot prove outcome, stop and show manual recovery. Do not claim Meta universally supports idempotency keys. Do not auto-delete partially created user objects. Recheck ownership/permissions before each remote write and deny queued activation after disconnect.

## Storage plan
Separate connections, account-asset grants, campaign drafts, publish operations and operation steps. Account-scoped access; service-only credential and dispatch paths. Encrypt token values with an external key outside database rows; store key version and support rotation. Audit only IDs, timestamps, sanitized errors and consent details. Never store payment-card data or Meta passwords. Define deletion/revocation handling. Additive migrations must pass real local database ownership/concurrency checks before any hosted application.

## Backend write scope proposed for later implementation
New src/api/meta_connections.py, src/api/campaign_publish.py; src/services/meta_connections.py, src/services/campaign_publish.py; src/clients/meta_marketing.py; src/models/campaign_publish.py; new tests and additive SQL. Config/main router additions require coordination with Claude and integration owner. Reuse existing verify-account and CSRF dependencies without editing Claude auth code. No modifications to Gemini creator files. Shared schema names above are a draft contract for coordination, not authorization to provision.

## Implementation order and acceptance
1. Confirm exact Meta app/account ownership and current developer configuration through authorized metadata, without requesting secrets in chat. Verify official Login for Business, permissions/App Review, supported API version and data deletion requirements. Inventory provider constraints before SDK implementation.
2. Implement connection and asset read-only slice with mocked provider tests: wrong state/session/owner, expired grants, revoked asset access, reconnect and disconnect. Real authorized connection acceptance is a separate gate.
3. Implement draft validation and PAUSED publish with deterministic fake provider + real local SQL tests for parallel clicks, retries, timeout-after-acceptance, partial object creation and revoked token mid-operation. Feature disabled by default.
4. Only after paused acceptance, implement budget-confirmed activation and verify with an explicitly authorized bounded test. No paid execution permitted by this plan alone.
5. Separate production rollout after app permissions and end-to-end account acceptance. No fake Connect/Publish success in demo; use clearly labeled walkthrough states.

## Evidence and limitations
Earlier official references inspected: https://developers.facebook.com/docs/graph-api/reference/adgroup and https://developers.facebook.com/docs/business-management-apis/2tier-bm-solution/pre-app-review-development/ . Current lookup retry failed November15; exact permissions, version, budget constraints, review requirements and token lifecycle remain unverified for implementation. Vercel Marketplace skill loaded; read-only categories discovery failed with network fetch error, so no provider installed and no assertion of a marketplace Meta integration. User explicitly selected Meta. This planning pass makes no remote changes, reads no secrets and spends nothing.

## Luna inventory outcome
Beauvoir completed and released read-only inventory. Existing Ad Library /ads_archive client serves competitor research, not customer campaign access. Muse client serves Model API generation/analysis, not Marketing API authorization. Reuse bid performance models/calculations and creative output models; add a separate customer Marketing API adapter. Existing demo/live gating is not sufficient authorization for ad-account mutations. No source edits or provider calls performed by worker. Worker report linked paths to main checkout despite requested candidate, so line numbers must be rechecked against implementation base before patching.
