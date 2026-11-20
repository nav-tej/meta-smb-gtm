# Assignment for Antigravity (Gemini): `/create` and `/first-ad` for any business, with no sample leftovers

Prepared November 18, 2026 by Claude at Nav's request; widened November 19 to cover `/first-ad`.
Status: PROPOSED until Nav relays it. Do this after the preview C coordinator task
(`docs/launch/codex-preview-c-nov18.md`) is recorded. Read `AGENTS.md` (top section and section 12)
on this branch first.

## Why
Nav tested `/create` on production with his own account after setting up nplusalpha.com, a consulting
business. Seen there (production runs older code, so check each one on your base):
1. He uploaded his own image (the n+α logo). The caption under it still read "Ek Onkar · original
   artwork preview. Source: Art of Sarabjit Singh." `upload()` in `creator.js` sets the image but
   never the caption (`#productImageCaption`); `selectCandidateImage()` does
   (`formatImageMetaNote`). The caption keeps whatever an earlier sample load wrote.
2. The page assumes a maker with products: "START WITH WHAT YOU MAKE", "Choose an artwork, decide
   where visitors should go...", the eyebrow "THE WORK COMES FIRST", "Product name" / "Name of the
   product you're promoting", and copy such as "Confirm current price and availability with the
   artist before publishing." A consulting firm promotes a service, an offer or a case study.
3. `/first-ad` has the same assumption (found by Claude on the branch, November 19):
   "Bring visitors to your shop" / "Best when you want people to browse an Etsy, Shopify, or studio
   listing", "Test a direct product offer", "Product or artwork name" with the placeholder "Botanical
   Linocut Print", destinations "Studio website / product page" and "Etsy shop / listing", "Load shop
   images", the audience placeholder "handmade botanical prints and home gifts", and prerequisite
   lines such as "Upload or select a product photo in Step 2". Customer-facing strings in
   `first-ad.html` and `OUTCOME_INFO` in `first-ad.js` also contain em-dashes.

## Base and branch
- Base: the tip of `origin/claude/ux-gap-ad-loop-nov17` when you start (`git fetch origin` first).
  Record the exact SHA in your report.
- New isolated worktree, new branch `gemini/create-any-business-nov18`. Do not use the Mac checkout at
  `/Users/nav/meta-smb-gtm` (detached, dirty, must be preserved; running the gate with its `.venv` is
  fine).

## Step 0: baseline (read-only, before any edit)
`DEMO_MODE=true META_MODEL_API_KEY= DEMO_KEY= make PY=/Users/nav/meta-smb-gtm/.venv/bin check` on your
base. Claude's latest counts are in the last row of the table in `docs/launch/CLAUDE_UX_GAP_NOV16.md`.
Report your own numbers.

## What to change
Exclusive write scope: `creator.js`, `creator.html`, `first-ad.js`, `first-ad.html`, `first-ad.css`
(all under `src/api/static/`) and one new test file.

1. `/create` caption: after an upload, `#productImageCaption` describes the uploaded photo (use
   `formatImageMetaNote(state.imageMeta)`). In a seller's own workspace no path may leave sample
   wording ("Ek Onkar", "Sarabjit", "SikhiArt", "artwork preview") in the caption, `#productFactNote`
   or the notice.
2. `/create` wording in a seller's own workspace (not the sample shop), for products and services
   alike. Suggested:
   - Eyebrow "START WITH WHAT YOU OFFER"; intro "Choose a product, service or offer, decide where
     visitors should go, then make one post. No shop login needed."
   - "THE WORK COMES FIRST" becomes "YOUR PHOTO" (or similar plain wording).
   - "Product name" becomes "What are you promoting?" with placeholder "A product, service or offer".
   - "Confirm ... with the artist" becomes "Confirm the price and details before publishing."
3. `/first-ad` wording in a seller's own workspace, same idea. Suggested: "Bring visitors to your
   website" / "Best when people should read a page, see your work or book a call first"; "Test a
   direct offer"; "What are you promoting?" with a neutral placeholder; destinations "Your website",
   "Etsy shop or listing", "Shopify store" (keep the existing option values, change labels only);
   "Load images from your website"; a neutral audience placeholder; prerequisite lines that say
   "photo" or "image" instead of "product photo". Replace em-dashes in customer-facing strings with
   plain punctuation in both modes (this is a punctuation fix, not a wording change for the sample).
   Keep Meta objective names as they are; do not add a new Meta objective (for example lead forms)
   without a Meta documentation link. If you think one belongs here, propose it in your report.
4. The sample shop keeps today's artist wording exactly (except the em-dash fix). Switch on
   `muse:mode-change` the way `updateChoices()` in `creator.js` already decides `isArtist` / sample
   state; `window.museModes` gives the mode on both pages.
5. Optional: the seller's setup answer is in the workspace document at `onboarding.business_type`
   (`"products"`, `"services"`, `"both"` or null; `GET /api/v1/account/workspace`). You may use it to
   pick the first suggested outcome, but neutral wording must read well without it.
6. Walk `/create` steps 2 to 4 and the whole `/first-ad` guide in a seller's own workspace with a
   services-style item (for example "AI growth audit", no price). Fix static copy that assumes art,
   prints or products. If generated ideas themselves assume a product seller, do not rewrite the idea
   logic: report the exact text and where it comes from.
- New test file `tests/test_create_any_business.py`: the caption after an upload in own workspace,
  the own-workspace wording on both pages at 375px and 1440px, and the sample shop's wording
  unchanged on both pages.
- Report: `docs/launch/ANTIGRAVITY_CREATE_ANY_BUSINESS_NOV18.md`.

## Do NOT touch
Everything outside the scope above, in particular `index.html`, `welcome.js`, `reco-actions.js`,
`seller-memory.js`, `workspace-modes.js`, `today.js`, `digest.js`, `muse-shell.js`, `account.js`,
`src/models/`, `src/services/`, `src/api/*.py`, billing, auth, `supabase/`, `AGENTS.md`, and existing
tests. Claude is working on `/today`, home and the digest at the same time. If an existing test fails
because it pins old wording, report the test and the line; do not edit it.

## Script versions
Bump `creator.js?v=` and `first-ad.js?v=` (and `first-ad.css?v=` if you change it) to `20261119-ag2`
on every page that loads them. Leave every other version on those pages as your base has it. Claude
merges your branch.

## Product rules
- Muse prepares; the seller publishes. Never imply Muse posts, runs ads or spends for them.
- No invented numbers. No em-dashes in customer-facing copy. No horizontal overflow at 375px.

## Boundaries
No paid Muse calls, real emails, charges, deploys, hosted migrations, auth or settings changes. Do not
read `.env` or print credentials. Do not push to `main`, do not force push, do not edit the
coordination branch for this task. Push only `gemini/create-any-business-nov18`.

## Verification and report
- Full offline gate after your change with exact counts, plus the Step 0 line.
- Real browser at 375px and 1440px: own workspace (signed in, mocked account) and sample shop, on
  both pages.
- Do not remove, skip or weaken an existing test; if one fails, report the failure and its cause.
- Report: branch, commit, files changed, exact results, what you checked in a browser, what you did
  not verify, and "Ownership released".
