# Operations runbook (production: meta-smb-gtm.vercel.app)

Updated November 9, 2026 by Claude. Seller: n Plus Alpha LLC, support help@nplusalpha.com.

## What watches production
| Signal | Where | Needs |
|---|---|---|
| Uptime every 15 min (pages, health, accounts, billing, legal) | GitHub Actions `Uptime` (`.github/workflows/uptime.yml`); a failed run emails the repo owner | Workflow pushed (needs a token with `workflow` scope); GitHub pauses schedules after 60 days without repo activity |
| Stripe webhook not recorded | Email to `ALERT_EMAIL` (default help@nplusalpha.com) + Vercel log `BILLING_WEBHOOK_FAILED`; Stripe also emails the account when an endpoint keeps failing | `RESEND_API_KEY` in Vercel Production |
| Weekly digest failed | Email alert + log `DIGEST_SEND_FAILED` | `RESEND_API_KEY` |
| Live runs | Vercel log `LIVE Muse run authorized` (path, user id, operation id) | none |

Alerts are throttled to one email per kind per 15 minutes per server instance.

## Runbooks
**Muse API down or slow.** Customers get a saved result labelled "Live Muse was unavailable, so saved results are shown. No run was used." or an error saying the run was not counted. Runs are finished as `refunded`/`failed` and do not count (`supabase/migrations/run_refunds.sql`). Check Vercel logs for `MetaAPIError`. To pause live generation for everyone:
```sql
update muse_private.credit_pool set enabled = false where id = 'trial';  -- resume: true
```

**Muse spending cap.** Every live call reserves estimated cost in `muse_private.credit_pool` (cap $100, `reserved_micros` never auto-refunds because a timed-out call may still be billed). When reserved reaches the cap, live Muse pauses for **everyone, paying customers included**. Check and raise:
```sql
select cap_micros/1e6 cap_usd, reserved_micros/1e6 reserved_usd from muse_private.credit_pool;
update muse_private.credit_pool set cap_micros = 200000000 where id = 'trial';  -- $200
```
Raise it only after topping up the Meta Model API balance.

**Payment taken but plan not active.** The app grants a plan only from verified Stripe webhooks. Stripe Dashboard → Developers → Webhooks → endpoint `we_1UZyKNPxYcxRFPXnUJ068HQz` → failed deliveries → fix the cause (Vercel logs `BILLING_WEBHOOK_FAILED`, Supabase status) → Resend. Events are idempotent, so resending is safe. The customer's page says activation is slow and to email support; they are never charged twice by a resend.

**Refund.** Stripe Dashboard → Payments → Refund. For a canceled subscription the plan ends at the paid period end via `customer.subscription.deleted`.

**Weekly digest.** Runs Mondays 15:00 UTC (`/api/v1/digest/send`, Vercel Cron) after the monitor at 14:00. Re-running sends nothing new (6-day rule). Manual run: `curl -H "Authorization: Bearer $CRON_SECRET" https://meta-smb-gtm.vercel.app/api/v1/digest/send` (only when `CRON_SECRET` is set; otherwise only Vercel Cron can call it).

## Data deletion request (privacy policy: within 30 days)
1. Confirm the request came from the account's email address.
2. Find the account id (Supabase SQL editor): `select id from auth.users where email = lower('<email>');`
3. Delete stored images (from the repo, with `.env.local` present):
   `.venv/bin/python -c "import asyncio; from src.services.media_store import delete_owner_media; print(asyncio.run(delete_owner_media('<user-id>')))"`
4. Delete run records and the digest subscription:
   ```sql
   delete from muse_private.provider_reservations where operation_id in (select id from muse_private.operations where user_id = '<user-id>');
   delete from muse_private.operations where user_id = '<user-id>';
   select public.muse_digest_forget('<email>');
   ```
5. Supabase Dashboard → Authentication → Users → delete the user. This cascades to the workspace, entitlements and billing rows. Stripe keeps its own payment and tax records.
6. PostHog (project nav-dev): Persons → search the account id → Delete person.
7. Reply to the customer confirming deletion; note the date in your records.

Digest-only requests: `select public.muse_digest_forget('<email>');`

## Rollback
- **App:** Vercel Dashboard → Deployments → previous Production deployment → Promote (or `vercel rollback`). Releases deploy from committed `main` in a clean worktree; the commit SHA is in each STATUS.md/BILLING.md checkpoint.
- **Billing off:** remove `STRIPE_SECRET_KEY` from Vercel Production and redeploy (plans show "Coming soon").
- **Database:** each migration in `supabase/migrations/` has a `*_rollback.sql` or rollback note (`billing_repair`, `run_refunds`, `media_storage`, `durable_state`, `digest_subscribers`).

## Email setup (Resend)
Set in Vercel Production, then redeploy:
- `RESEND_API_KEY`: from Resend, with the sending domain (nplusalpha.com) verified (SPF/DKIM DNS records).
- `EMAIL_FROM` (default `Muse Growth Studio <digest@nplusalpha.com>`), `EMAIL_REPLY_TO` (default help@nplusalpha.com), `ALERT_EMAIL` (default help@nplusalpha.com).
- `EMAIL_TOKEN_SECRET`: random secret that signs confirm/unsubscribe links. Rotating it invalidates outstanding links only.
- `EMAIL_POSTAL_ADDRESS`: the LLC's mailing address, shown in every digest footer (CAN-SPAM requires a physical postal address in commercial email).
- Optional `CRON_SECRET`: when set, scheduled routes accept only `Authorization: Bearer <secret>` (Vercel Cron sends it automatically).
