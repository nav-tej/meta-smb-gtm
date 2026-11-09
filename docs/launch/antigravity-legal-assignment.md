# Assignment for Antigravity (Gemini): seller identity, legal pages, support contact

Assigned November 9, 2026 by Claude on Nav's instruction (Codex is on usage limits).
Read AGENTS.md, docs/launch/PLAN.md and STATUS.md first. Claim this row in STATUS.md before editing.
Write your checkpoints to `docs/launch/LEGAL.md` (create it) using the AGENTS.md checkpoint rules.

## Why
Stripe will not approve live payments for a site that does not show who the seller is, how to
contact them, and the terms, privacy and refund policies. PLAN.md also lists these as release
gates. Claude is simultaneously changing billing (backend, SQL and the pricing dialog), so stay
inside the scope below.

## Facts to use (from Nav)
- Seller / merchant of record: **n Plus Alpha LLC** (website nplusalpha.com). Muse Growth Studio is
  a product operated by this LLC.
- Support email: **help@nplusalpha.com**
- Card statements show: **NPLUSALPHA.COM**
- Paid plan (being built by Claude): **Muse Starter**, $12/month, or $108/year ($9/month billed
  annually), 20 Muse runs per month, cancel anytime, access continues to the end of the paid period.
  Free trial: 3 runs. Payments processed by Stripe.

## Your write scope (exclusive)
- NEW `src/api/static/legal/terms.html`, `privacy.html`, `refunds.html` (one shared small CSS file
  in the same folder is fine). They are already served at `/static/legal/...` by the existing
  static mount: no change to `src/api/main.py`.
- A small footer on `index.html`, `today.html`, `creator.html`, `digest.html` with:
  "Muse Growth Studio is operated by n Plus Alpha LLC · help@nplusalpha.com · Terms · Privacy ·
  Refunds". Edit only the footer markup/CSS on these pages. They contain other agents' uncommitted
  work: preserve every other line.
- New test `tests/test_legal_pages.py` (pages return 200, footer links present on all four pages).
- `docs/launch/LEGAL.md` (your log).

## Do NOT touch
`src/api/billing.py`, `supabase/**`, `tests/test_billing.py`, `tests/billing_sql_regression.mjs`,
`scripts/stripe_setup.py`, `src/api/static/muse-shell.js` (Claude is editing the pricing dialog
there), `account.js`, `creator.js`, `today.js`. No deploys, pushes, secrets, Stripe or Supabase
changes, or paid Muse calls.

## Content rules
- Plain language for a solo seller. Short pages.
- Policy text is a **draft for Nav's review, not legal advice**: put a visible "Draft — last
  updated <date>" line at the top and list every assumption in LEGAL.md. Mark business decisions
  you had to assume (for example refund window, governing state) as `[NAV TO CONFIRM]` in the page.
- Privacy page must truthfully describe what the app stores: account email (Supabase auth), saved
  drafts, uploaded product photos sent to Meta's Muse models for generation, payment handled by
  Stripe (we never see card numbers), usage counts. Do not claim certifications or practices the
  app does not have.
- Do not invent a phone number or street address.

## Done when
`make check` passes, the four pages show the footer at 375px and 1440px without layout breakage,
and LEGAL.md records commands/results and the `[NAV TO CONFIRM]` list. Then release ownership in
STATUS.md.
