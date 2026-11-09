# Assignment for Hermes: end-to-end customer test on the Muse preview

Assigned November 9, 2026 by Claude on Nav's instruction. Nav authorizes this test: create one test
account on Nav's own app, pay with Stripe's published **test** card, and run **one** live Muse
generation. Read AGENTS.md, docs/launch/PLAN.md and docs/launch/STATUS.md first, then write your
checkpoints and final report to `docs/launch/hermes-e2e-report.md` (create it). Do not edit any
other file.

## Where
Preview (requires a browser already signed in to Nav's Vercel account; it shows a Vercel login otherwise):
**https://meta-smb-59phupulx-navtejs-6321s-projects.vercel.app**

If that URL 404s, ask Nav for the newest preview URL (`docs/launch/STATUS.md` lists it). Never use
the production site (meta-smb-gtm.vercel.app) for this test.

## Test account
- Email: a **plus-address of Nav's inbox**, e.g. `navtejs+muse-e2e-1@gmail.com` (you need access to that
  inbox to click the confirmation link). Use a new suffix if that address was already used.
- Password: generate a random 16+ character password. Do not reuse any real password. Record that you
  generated one, **not the password itself**, in your report.

## Steps (record pass/fail, time, and a screenshot for each)
1. **Landing.** Open the preview. Expect a header with *Plans & pricing*, *Sign in* and a green
   *Create free account*; the hero's main button says *Create free account →*.
2. **Sign up.** Click *Create free account →* in the hero. Enter the test email and password, submit.
   Expect: "Check your email to confirm…".
3. **Confirm.** Open the confirmation email in the inbox and click the link. If it lands on the main
   site (meta-smb-gtm.vercel.app), go back to the preview URL and sign in there. Expect the header
   to show *3 of 3 runs left*.
4. **Plans.** Click *Plans & pricing*. Expect two cards: *Starter · Monthly $12* and
   *Starter · Annual $9/mo billed $108*, both with active *Choose* buttons (not "Coming soon").
5. **Checkout.** Choose **Starter · Monthly**. On the Stripe page confirm it says **TEST MODE**
   (stop and report if it does not). Pay with card `4242 4242 4242 4242`, any future expiry,
   any 3-digit CVC, any ZIP. Use the test account's email if asked.
6. **Back in the app.** After the redirect, wait ~10 seconds and refresh. Expect the header to show
   *20 of 20 runs left* (plan Starter). If it still shows the trial, wait 30 seconds and refresh
   once more, then report.
7. **One live generation (billed, ~cents).** Open `/create`, keep the sample product, go to the image
   step and click *Create my image* exactly **once**. Expect a new image within ~2 minutes and the
   count to drop to *19 of 20*. Do not retry if it fails; screenshot the message and report.
8. **Duplicate-subscription guard.** Open *Plans & pricing* again and click *Starter · Annual*.
   Expect the message "You already have the Starter plan, so no second subscription was started…"
   and **no** Stripe page.
9. **Sign out / sign in.** Sign out, sign back in. Expect *19 of 20 runs left* again.

## Limits
- At most **one** live Muse generation (step 7). No other live/billed actions.
- Only the Stripe test card above. Never enter a real card, real bank, or real personal data.
- Do not change settings in Stripe, Vercel, Supabase or PostHog. Do not deploy or edit code.
- If anything blocks you, stop and report rather than working around it.

## Report (docs/launch/hermes-e2e-report.md)
For each step: PASS/FAIL, timestamp (PT), what you saw, screenshot path. Include the test email
used (not the password), the preview URL, and any error text verbatim. End with "Ready for Claude
verification" so Claude can check Supabase rows, Stripe webhook deliveries and PostHog events.
