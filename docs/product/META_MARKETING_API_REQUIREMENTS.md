# Meta Marketing API Integration Requirements (Future Live Campaign Writes)

Status: **Documentation only — no live Marketing API campaign writes are implemented in this branch.**

This document specifies the requirements for a future direct Meta Marketing API integration based on current official Meta Developer documentation (`developers.facebook.com/docs/marketing-api`).

## 1. Authorization & Authentication

- **OAuth 2.0 (Never Passwords):** Authenticate sellers exclusively via Meta Facebook Login / Business Login OAuth 2.0. Never ask for, collect, proxy, or store Meta/Facebook/Instagram usernames or passwords.
- **Token Hygiene:** Store OAuth access tokens server-side, encrypted at rest, scoped to the authenticated Muse user (`owner_id`), with explicit disconnect/revocation support.
- **Token Inspection:** Validate active scopes and expiration via the Meta Token Debugger / `debug_token` endpoint before attempting writes.

## 2. Permissions, App Review & Access Tiers

- **Required Scopes:**
  - `ads_read`: Read ad accounts, campaigns, ad sets, ads, and insights.
  - `ads_management`: Create and update campaigns, ad sets, creatives, and ads.
  - `business_management`: Required when reading or managing Ad Accounts, Pages, Pixels, or Instagram accounts owned by a **Meta Business Portfolio (Business Manager)**.
- **Business Verification & App Review:**
  - Moving beyond **Development Mode** requires **Meta Business Verification** and passing **Meta App Review** for **Advanced Access** on `ads_management`, `ads_read`, and `business_management` (including end-to-end screencasts and reviewer test instructions).
  - Meta also gates Marketing API call volume and error-rate health under Marketing API Access Tiers (Development / Limited / Full Access). Apps in Development Mode cannot write to production customer ad accounts (errors such as `270`/`273` or development-mode creative/campaign rejections).

## 3. Account Ownership & Asset Verification

- **Ad Account Binding (`act_<AD_ACCOUNT_ID>`):** Before any write, query `/me/adaccounts` (or business-scoped ad accounts) to confirm the authenticated token has `ADMIN` or `ADVERTISER` permissions on the specific `act_<AD_ACCOUNT_ID>` selected by the seller.
- **Asset Ownership:** Verify the seller's connected Facebook Page / Instagram actor ID and (if using website conversion objectives) Meta Pixel / domain are authorized for that Ad Account. If using a System User token, the System User must be explicitly assigned to the Ad Account in Business Settings (missing assignment causes error `200` / `10`).
- **Tenant Isolation:** Never allow one Muse user to read or write another Muse user's Ad Account ID or OAuth token (`owner_id` binding enforced server-side).

## 4. Paused Creation (`status="PAUSED"`)

- **Default-Safe Creation:** Every object created via the Marketing API must be created in `PAUSED` state so zero budget is spent during setup or partial failure:
  1. Campaign: `POST /<API_VERSION>/act_<AD_ACCOUNT_ID>/campaigns` with `name`, `objective` (e.g. `OUTCOME_TRAFFIC`, `OUTCOME_ENGAGEMENT`, `OUTCOME_LEADS`, `OUTCOME_SALES`), `status="PAUSED"`, and `special_ad_categories` (explicitly declared).
  2. Ad Image / Video upload (`adimages` / `advideos`).
  3. Ad Creative (`adcreatives`) referencing the seller's verified Page/IG actor, copy, CTA, and destination URL.
  4. Ad Set (`adsets`) with `status="PAUSED"`, explicit `daily_budget` or `lifetime_budget` (in account currency minor units), `start_time`/`end_time`, and `targeting`.
  5. Ad (`ads`) linking `adset_id` and `creative_id` with `status="PAUSED"`.

## 5. Explicit Activation

- **Separate Confirmation Gate:** Never activate (`status="ACTIVE"`) automatically at the end of creation.
- **Seller Review & Spend Acknowledgment:** Activation requires a separate, explicit user action displaying the exact `act_<AD_ACCOUNT_ID>`, currency, daily/lifetime budget, start/end dates, destination URL, and `"Meta will bill your Ad Account directly"` notice before sending `POST /<OBJECT_ID>` with `{"status": "ACTIVE"}`.

## 6. Idempotency & Duplicate-Write Prevention

- **Client Idempotency Keys:** Because the Meta Marketing API does not provide a universal `Idempotency-Key` header across single-object creation endpoints, generate a deterministic per-draft/per-step client key (UUID) and embed it in a persisted local/server state machine and/or object tracking/name tag.
- **Check-Before-Retry:** Persist each returned Meta object ID (`campaign_id`, `image_hash`, `creative_id`, `adset_id`, `ad_id`) immediately after creation. On network timeout or 5xx error, query the Ad Account by client tag/name before retrying creation to prevent duplicate campaigns or double budget allocation.

## 7. Error Handling & Recovery

- **Transient Errors (`4`, `17`, `1363047`, `1609010`):** Rate-limit and temporary service-unavailable errors should use bounded exponential backoff with check-before-retry and never silently create duplicate objects.
- **Authorization / Asset Errors (`10`, `200`, `270`, `273`, `OAuthException`):** Surface plain-language remediation (re-authorize OAuth scopes, assign Ad Account/Page in Business Settings, verify payment method in Meta Ads Manager) without wiping the seller's local draft.
- **Manual Fallback:** Keep the manual Ads Manager export/checklist workflow available at all times so a seller is never blocked from launching manually if API permissions or connectivity fail.
