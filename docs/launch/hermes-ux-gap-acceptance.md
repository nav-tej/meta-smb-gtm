# Hermes: hosted acceptance for the UX gap and ad loop work

Prepared November 17, 2026 by Claude at Nav's request. Status: PROPOSED until Nav relays it.
Read-only browser acceptance. No code edits.

## Target
- Branch `claude/ux-gap-ad-loop-nov17` at `d8f4ba2` (last runtime change) or a docs-only
  descendant. It combines `claude/ux-gap-nov16` (`c989f4b`) and `gemini/ad-loop-nov16` (`a982987`)
  on top of release candidate `27c1f50`, plus the setup notice on every sample page (`d8f4ba2`).
- Test only a protected preview that the coordinator deployed from that exact SHA and gave you
  with its URL. If you have no such URL, or the preview's SHA differs, stop and report that. Do
  not test production or the older `27c1f50` preview for these items.
- The preview has Vercel Deployment Protection. Earlier runs were blocked at the Vercel login;
  get access from Nav (a bypass link or Nav's signed-in browser) before you start, or report the
  blocker.

## Boundaries
No new signups (they send real email), no password resets, no purchases or test charges, no
settings or auth changes. Do not press anything that runs Muse or uses a credit (for example
"Run bid advice", "Build my plan", paid generation buttons). Do not upload a CSV. Never print
credentials. Viewports: 375px and 1440px for every item.

## Guest checks (no account)
1. `/` shows no mode banner. `/?workspace=sample` shows "Sample shop example".
2. Home, sample workspace: "No ad running yet? Prepare your first ad" in the Improve stage
   (`#improveFirstAdLink`), the Iterate stage (`#iterateFirstAdLink`) and the bid advice tab
   (`#bidsFirstAdLink`). Each lands on `/first-ad?workspace=sample`.
3. `/first-ad?workspace=sample`, last step: the note about exporting results from Meta Ads Manager;
   "home bid advice tab" goes to `/?workspace=sample#tab-bids` and opens that tab.
4. "First ad guide" in the nav of `/` and `/progress`, and "Prepare your first ad" on `/today`
   and on `/create` step 4 (Ready to share), all lead to the guide.
5. `/creator` redirects to `/create` and keeps the query string.
6. No horizontal scrolling on any page above, no page errors in the console.

## Signed-in checks (only with accounts Nav supplies)
Use existing test accounts. Skip and mark UNVERIFIED anything you have no account for.

Account A, setup not finished:
7. Type `/` into the address bar: the page switches to `/?workspace=sample` with a "Demo data"
   banner directly under the header and one button, "Finish setup", which opens `/welcome`.
8. `/today?workspace=sample` and `/create?workspace=sample`: "Demo data · This page shows a sample
   shop…" with "Finish setup" and "Open my workspace". "Open my workspace" opens the seller's own
   editor without `workspace=sample`.
8b. `/first-ad?workspace=sample`, `/progress?workspace=sample` and `/digest?workspace=sample` show the
   same "Demo data" notice with both buttons.
9. Sign out, then sign in from the home page: you land on `/welcome`, not the demo.

Account B, setup finished with a saved shop website:
10. `/` shows the seller's own dashboard, no demo banner. The Create stage offers "Prepare your
    first ad" and it opens `/first-ad` (no `workspace=sample`).
11. Listing import, only if Nav approves crawling that account's shop website: in a fresh browser
    profile, the first `/today` visit brings in the seller's listings without a click, and the
    first `/create` visit lists them under "Find products". A second visit does not scan again.
    The crawl is the free public storefront fetch, not a Muse run. Without approval, mark UNVERIFIED.

## Report
`docs/launch/HERMES_UX_GAP_NOV17.md` on your own branch: preview URL and SHA, browser and
viewports, PASS / FAIL / UNVERIFIED per numbered item with a screenshot or exact text for each
FAIL, and anything blocked. End with "Ownership released".
