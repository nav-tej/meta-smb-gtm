# Assignment for Antigravity: `/create` destinations and Muse context for any business

Prepared November 19, 2026 by Claude at Nav's request. Status: PROPOSED until Nav relays it. Read
`AGENTS.md` (top section, sections 4 and 12, and the business-type bullets) on this branch first. Your
`/create` wording work (`bf32ba2`) and competitor research (`4a48cb9`) are merged; thank you.

## Base and branch
Tip of `origin/claude/ux-gap-ad-loop-nov17` when you start (`git fetch origin`; record the SHA; it is
`1cfc4a8` or later). New isolated worktree, new branch `gemini/create-destinations-nov19`. Not the Mac
checkout (its `.venv` is fine for the gate).

## What is wrong (found by Claude on November 19, in `src/api/static/creator.js`)
1. Every live generation from `/create` sends Muse the sample artist's rules, in every workspace:
   `productPayload()` (around line 1191) ends its `brand_notes` with "Never assume the same artwork or
   price exists in another shop ... For this artist, Etsy is closed. Do not recommend Etsy ...". A
   consulting business or an Etsy seller gets told Etsy is closed. This is the same kind of leak Claude
   fixed on home in pass 11 (`sellerContextForAnalysis()` in `index.html`).
2. The destination list is the sample artist's: `destinations` (around line 212) is Pixels, Fine Art
   America, Saatchi Art, "Artist website" and "My shop / inquiry page", and `creator.html` hard-codes
   the same `<option>`s. A seller's own workspace should not offer the artist's marketplaces.
3. Sample wording left in the own workspace: "Your product photo will appear here.", "Add a photo to
   create your own product layout.", the `switchDestination()` notice ("Check that this artwork is
   listed there"), and anything else that says artwork, artist or product to a services business.
   Check `postingChecklist()` and the export text too.

## Change
1. `brand_notes` (and anything else sent to Muse from `/create`, including `promotionResearchContext()`)
   carries the sample artist's rules only when `state.workspace === 'sarabjit_singh'` and the item is
   not custom. In a seller's own workspace it describes that seller: business name, what they offer
   (`onboarding.business_type` from the account workspace, as `today.js` reads it), the destination
   they chose, and the generic safety rules (only supplied facts; no invented scarcity, materials,
   reviews, prices or results). Do not invent anything about the seller.
2. Own-workspace destinations: "My website" (`website`), "Booking or contact page", "Etsy shop or
   listing", "Shopify store" and "Other link", or a similar short list you justify. Keep the existing
   keys where they mean the same thing (`website`, `other`) because the `/today` handoff code (around
   line 550) and saved drafts use them; any new key needs a matching label
   everywhere `destinations[...]` is read, and an old saved draft with `pixels`, `fineartamerica` or
   `saatchi` must still load (fall back to `other` with its link kept). The sample shop keeps today's
   list and notes exactly.
3. Neutral wording in the own workspace for the strings in point 3 above; services businesses get
   "service or offer" wording, products and both keep "product" where it fits. No em-dashes in
   customer copy.
4. Bump `creator.js?v=` (and `creator.html` if changed) on every page that loads it, and update the
   pin in `tests/test_create_any_business.py` and the version line in your report (Claude will update
   `AGENTS.md`).

## Exclusive write scope
`src/api/static/creator.js`, `src/api/static/creator.html`, `src/api/static/creator.css` if needed,
`tests/test_create_any_business.py` and new tests. Do not touch `today.js`, `muse-shell.js`,
`index.html`, `seller-memory.js`, `welcome.js`, `first-ad.*`, `src/` Python, billing, auth,
`supabase/` or `AGENTS.md`. Claude is working on `/today` and Argon on ad account connections at the
same time.

## Tests
- A browser test (375px and 1440px) for a services seller and a products seller in their own
  workspace: the destination list has none of Pixels, Fine Art America, Saatchi Art or "Artist
  website"; a captured live `POST` (route-mocked, never sent to Muse) has no "Etsy is closed",
  "artist" or "artwork" in `brand_notes` and does have the seller's business name.
- The sample shop still sends today's artist rules and shows today's list (a regression guard).
- An old saved draft with destination `pixels` loads in the own workspace without an error.
- A mutation check: put the Etsy sentence back for every workspace and confirm the new test fails;
  say so in the report.

## Boundaries
No paid Muse calls (route-mock every generation), no deploys, migrations, emails, auth or settings
changes. Do not read `.env`. Do not push to `main` or force push. Push only
`gemini/create-destinations-nov19`.

## Verification and report
Full offline gate before and after with exact counts
(`DEMO_MODE=true META_MODEL_API_KEY= DEMO_KEY= make PY=/Users/nav/meta-smb-gtm/.venv/bin check`),
and a real browser at 375px and 1440px for the own workspace and the sample shop. Report in
`docs/launch/ANTIGRAVITY_CREATE_DESTINATIONS_NOV19.md`: branch, commit, files, results, the mutation
check, what you did not verify, and "Ownership released".
