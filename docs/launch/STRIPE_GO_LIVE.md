# Stripe: test on preview, then go live

Seller: **n Plus Alpha LLC**. Plan on sale: **Muse Starter**, $12/month or $108/year
($9/month), 20 Muse runs per month (annual plans also reset monthly). Growth/Unlimited are hidden.

## Current state (November 9, 2026)
- Stripe **sandbox** "n Plus Alpha LLC sandbox": product + prices `muse_starter_monthly`,
  `muse_starter_annual`; webhook `we_1UZnpQLcBUBSf7XVC77zsu9n` (metadata `muse_env=preview`, 9 events).
- Vercel **Preview** env: Stripe test key, both price IDs, webhook secret, Supabase settings.
  **No Muse key** on Preview, so preview runs cannot spend the Muse balance.
- Preview URLs require a Vercel login. Stripe gets through with the project's automation bypass
  token in the webhook URL (stored in local `.env` as `VERCEL_AUTOMATION_BYPASS_SECRET`; revoke
  in Vercel → Settings → Deployment Protection).
- Supabase `iwatwkiogizfmetiwlqf`: billing migration applied (rollback:
  `supabase/migrations/billing_repair_rollback.sql`).
- Production: unchanged. No Stripe settings, purchase buttons keep the demo checkout.

## After each new preview deploy
```bash
U=https://<new-preview-url>
.venv/bin/python scripts/stripe_setup.py --env preview \
  --webhook-url "$U/api/v1/billing/webhook?x-vercel-protection-bypass=$(grep ^VERCEL_AUTOMATION_BYPASS_SECRET= .env | cut -d= -f2)"
```
Same endpoint, same signing secret; no Vercel env change or redeploy needed.

## Sandbox test (Nav, on the preview URL)
1. Sign up with a real inbox, confirm the email, sign in.
2. Account menu → Plans → Starter Annual or Monthly → Stripe Checkout.
3. Card `4242 4242 4242 4242`, any future date, any CVC, any ZIP.
4. Back in the app, the plan shows Starter, 20 runs. Claude verifies the database rows and the
   Stripe event deliveries.
5. Also try: cancel the subscription in the Stripe sandbox dashboard → plan returns to trial
   after the paid period; card `4000 0000 0000 0341` (attaches, then fails) → no runs granted.

## Go live (about 10 minutes)
1. Stripe live account: business details, bank account, public details (support email
   help@nplusalpha.com, website), statement descriptor NPLUSALPHA.COM. Live payments need
   Terms/Privacy/Refund pages and the seller footer on the site (Antigravity assignment).
2. **Purge sandbox billing rows** (preview and production share one Supabase project):
   ```sql
   truncate muse_private.billing_periods, muse_private.billing_payments,
            muse_private.billing_events, muse_private.billing_subscriptions,
            muse_private.billing_customers;
   update muse_private.entitlements set plan = 'trial', quota = 3, renews_monthly = false,
       stripe_customer_id = null, billing_period_start = null, billing_period_end = null;
   ```
3. Put the **live** secret key in `.env` as `STRIPE_SECRET_KEY` (keep the test key elsewhere),
   then:
   ```bash
   .venv/bin/python scripts/stripe_setup.py --live --env production \
     --webhook-url https://meta-smb-gtm.vercel.app/api/v1/billing/webhook --push-vercel
   ```
   This creates the live product, prices and webhook and sets Production's Stripe variables.
4. Production also needs the Supabase variables (already set) and a redeploy from committed
   `main`. Bump the `muse-shell.js`/`.css` `?v=` query strings in the HTML so browsers load the
   new pricing dialog.
5. One real purchase with your own card, then refund it from the Stripe dashboard.

## Rollback
- Billing off: remove `STRIPE_SECRET_KEY` from the Vercel environment and redeploy (routes return
  "Billing is not configured yet").
- Database: run `supabase/migrations/billing_repair_rollback.sql` (deletes billing records; Stripe
  keeps its own and webhooks can be replayed after re-applying the migration).
