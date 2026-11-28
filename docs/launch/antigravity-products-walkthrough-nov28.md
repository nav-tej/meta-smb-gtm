# Antigravity brief: walk the app as a products seller who isn't an artist (Nov 28)

Coordinator: Claude. Report: `docs/launch/ANTIGRAVITY_PRODUCTS_WALKTHROUGH_NOV28.md`.
Base: `origin/claude/ux-gap-ad-loop-nov17` (the commit that adds this brief, or later; your
services walkthrough is merged). Branch: `gemini/products-walkthrough-nov28`. Worktree:
`/Users/nav/muse-worktrees/products-walkthrough` (never `/tmp`). Commit and push at every
checkpoint. Never push to `main` (it deploys production) or `production`, never deploy. Read
AGENTS.md first.

## Why

Your services walkthrough kept the products wording "unchanged". Much of that wording was
written for the sample artist (paintings, prints, room scenes, collectors), and Muse is for any
small online seller. Check that it fits a shop that sells something else.

## The account to walk

A local fixture, built the same way as `tests/test_services_walkthrough_e2e.py`:
- **Business:** "Ember & Wick Candle Co.", `business_type: "products"`, an Etsy shop and its own
  Shopify site.
- **Setup answers:** goal "More sales", channels Instagram and Facebook, 30 minutes a week, tone
  `polished_premium`, plan `trial`.
- **Competitors:** two other candle shops, one with a saved analysis.
- **Activity:** one draft on `/create`, and one logged outcome with revenue.

## The walk, the fix and the report

Same as your services brief (`antigravity-services-walkthrough-nov28.md`), at 375 and 1440 px:
`/today`, `/create`, `/first-ad`, `/digest`, `/progress`, `/account`.
- **Look for:**
  - art words ("artwork", "painting", "print", "room scene", "collector", "gallery", "signature");
  - marketplace or sample assumptions (Pixels, Fine Art America, Saatchi);
  - anything a candle seller wouldn't understand in five seconds.
- **The sample artist keeps every word.** Change what a `products` business sees only. Where the
  sample and a `products` business share one string, make the products version neutral ("item",
  "product", "your shop") and keep the sample's.
- **Fix in your files only**, each fix with a browser test that fails when reverted. Put them in
  one new file: `tests/test_products_walkthrough_e2e.py`.
- **Report:** a findings table (page, width, what happens, why it's wrong, status), plus items
  for Claude's files.
- **Bump changed scripts to `20261128-ag2`** and update their pins.

## Do not touch

- **Claude:**
  - `src/api/static/index.html`, `welcome.*`, `muse-shell.*`, `seller-memory.*`,
    `reco-actions.js`, `workspace-modes.js`, `account.js`;
  - `src/api/intel.py`, `src/api/main.py`, `src/api/onboarding.py`, `src/api/outcomes.py`;
  - `src/services/saved_competitors.py`, `src/services/seller_memory.py`.
- **Codex** (abuse controls):
  - `src/services/accounts.py`, `usage_meter.py`, `scan_guard.py`, `credits.py`;
  - `src/api/accounts.py`, `src/api/demo.py`, `src/api/credits.py`;
  - `supabase/`, `scripts/`, `docs/launch/RELEASE.md`.

## Gate

The full gate, both audits, all 8 Node contracts, and one mutation check per fix category. No
live calls, no Muse runs, no deploys, no `*.vercel.app` targets, no secrets.
