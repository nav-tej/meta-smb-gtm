# Hermes: hosted acceptance for the UX gap and ad loop work

Prepared November 17, 2026 by Claude at Nav's request. Status: PROPOSED until Nav relays it.
Read-only browser acceptance. No code edits.

## Target
- Preview D only (updated November 19): the protected preview the coordinator deployed from
  `claude/ux-gap-ad-loop-nov17` and recorded in the handoff
  (`git show origin/codex/coordination-nov16:docs/launch/HANDOFF_CURRENT.md`). Codex deployed it from
  `29904ce` (`meta-smb-21zg6y020`) and moved the alias to it. It contains items 1 to 32. If the handoff has no preview D yet, or the SHA there differs from the one in Nav's message,
  stop and report. Previews A (`f83125a`), B (`be453db`) and C (`0f25fff`) are superseded; if you
  already have results from preview C, list them separately and retest on D.
- Use the fixed alias `https://muse-preview-nav.vercel.app` for anything that needs Google sign-in;
  the coordinator moves it to preview D.
- The preview has Vercel Deployment Protection; get access from Nav (a bypass link or Nav's signed-in
  browser). Google sign-in works only on the fixed preview alias, if the coordinator recorded one and
  Nav registered its callback; otherwise sign in with email and password.

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
12. Account A on `/`: the hero reads "Finish setup to see your own shop here." with
    "Finish setup" and "Keep exploring the sample". "No account needed" appears nowhere above the
    sample gallery. The runs count in the hero matches the header.
13. Account A opens `/today`, `/create`, `/first-ad`, `/progress` and `/digest` directly (no
    `workspace=sample`): a "Setup not finished" notice under the header with "Finish
    setup". Account B sees no such notice.
14. `/today`: the example button reads "Try a saved example" (no "n+α"). For a signed-in
    seller with no competitor checks the brief reads "My workspace · no competitor checks yet".
15. Home "Ask Muse what to do next" (needs a preview from `0e3ddb7` or later): in the sample shop,
    "Weekly post ideas" shows "Tell one painting story" and "Feature your Empowering Women series",
    each linking to `/create?workspace=sample&idea=...`; for a signed-in seller in their own
    workspace it shows one move pointing to `/today`. No runs used.
16. Setup step 3 (needs a preview from `879a87f` or later): as a guest, "Suggest similar shops (1 run)"
    opens a free-account prompt; after signing in with account A the wizard is back on step 3 with
    what you entered. Do not press the button signed in unless Nav approves spending 1 run; if he
    does, the suggestions come from account A's shop website and arrive unticked. On home as a
    guest, adding a shop and pressing "Request analysis" both open the free-account prompt.
17. `/digest` signed in (accounts A and B): the page loads your digest settings. It must not say
    "Sign in to load your personal digest preferences." If it does, report the exact text and whether
    a reload fixes it.
18. Account A (no setup, no listings) on `/today`: report the exact text of "Your context" and its
    "Selected move". In a local run it read "Refresh titles & descriptions across 5 listings on your
    shop" for a seller with no listings; report whether the preview shows that.
19. Account B on `/` right after setup: a "Start here" card reads "Your shop is set up. Get your first
    result." with "Analyze <first competitor> · 1 run" (or "View analysis" if one is saved) and "Open
    today's studio". "Hide" keeps it hidden after a reload. Do not press Analyze unless Nav approves
    spending 1 run; if he does, confirm the analysis is of the competitor's own site, not a Meta Ad
    Library page. Account A (setup not finished) and guests do not see the card.
20. The "Your context" panel on `/` for an account Muse remembers nothing about: one line ("Nothing
    saved yet") with "Set your goal" and "What Muse remembers"; "Set your goal" opens the full form.
    After signing out, no shop or competitor name from the signed-out account remains on the page.

21. Add-competitor form on `/` (needs a preview with merge `c9efa56`): as a guest the button reads
    "Add shop" and the note under it says analyzing needs a free account (3 free runs, 1 per analysis);
    the line after the list reads "Saved public snapshots from Nov 3, 2026. Create a free account to
    analyze shops you choose." Account B in its own workspace: "Add and analyze · 1 run" and "Analyses
    you run are saved to your workspace. Viewing one again is free." (no "Nov 3"). Account B on
    `/?workspace=sample`: "Saved public snapshots from Nov 3, 2026. New analyses use 1 run."
22. "Ask Muse what to do next" chips: the sample shop shows "Why $59.99 entry" and "Gifts under $50";
    account B's own workspace shows "How do my prices compare?", "Easier moves", "Gift ideas" and
    "Weekly post ideas", with no dollar amounts. Switching between the two updates the chips.
23. Sample shop watchlist on `/?workspace=sample` (guest and account B): no "Couldn't check" badge and
    no check time later than Nov 3; competitors show "Saved snapshot · Nov 3".
24. Only if Nav approves the item 19 run: in the browser's network panel, the `analyze-competitors`
    request's `seller_context` describes account B's shop (its name or website) and does not say
    "Fine artist selling Sikh & Punjabi heritage art". If you cannot see the request, mark UNVERIFIED.

25. Needs a preview with pass 12. Account B, "Your account": the dialog shows "Edit shop setup", which
    opens `/welcome?edit=1` with a banner "Editing the setup for <shop>." and the saved answers in
    every step, step 4 included. Change one thing (for example the research focus), press "Save
    changes (free · 0 runs)", reload `/welcome?edit=1` and confirm the change stuck. Runs left must
    not change.
26. Setup step 1 shows "What do you offer?" with Products, Services and Both. Only with Nav's
    approval to scan (the scan is a free public crawl, no run): scanning a services website such as
    nplusalpha.com preselects "Services" and says "Muse guessed".
27. Home "Ask Muse what to do next", account B's own workspace: type "How can I get more leads from
    Clutch or Toptal traffic". The answer reads "Focus: Leads" and offers "Compare how a competitor
    wins clients". No runs used.
28. Needs a preview with pass 13 (preview D or later; preview C at `0f25fff` does not have it; mark
    UNVERIFIED there). An account whose setup says "Services", on `/today` with nothing picked: the
    item reads "<business> · choose a service or offer"; the three posts read "What <business>
    helps with", "A recent project, in plain words" and "How working with <business> goes"; the
    goal is "Inquiries". No post, caption or "Image ideas" text mentions artwork, brushwork,
    collectors or a "Featured piece". Muse does not look for product listings on its website.
29. Same account: the "Your context · <business>" bar at the top of `/today` suggests a services
    move (for example "Tighten the services page on your website" or "Say what a first project with
    <business> includes"), not "Refresh titles & descriptions for up to 5 listings", gifts or
    commissions. The sample shop (`/today?workspace=sample`) still shows Ek Onkar and its posts.

30. Needs preview D. Account B's own workspace on `/create`: the first step reads "Start with what you
    offer" and "What are you promoting?" (not "Start with what you make" or "Product name"). Upload
    any photo from your machine: the caption under it changes to "Uploaded photo (...) · Kept on this
    device." and never mentions Ek Onkar, Sarabjit or an "artwork preview". Do not press anything that
    generates. `/create?workspace=sample` still reads "Start with what you make".
31. Needs preview D. Account B's own workspace on `/first-ad`: the outcomes read "Bring visitors to your
    website" and "Test a direct offer"; the item field asks "What are you promoting?"; the image step
    says "photo" or "Image", not "product photo". No em-dash (—) anywhere on the page.
    `/first-ad?workspace=sample` still reads "Bring visitors to your shop" and "Product or artwork name".
32. Google sign-in on `https://muse-preview-nav.vercel.app`, only with a Google account that already has
    a Muse account (Nav's or one he supplies; never create a new account): "Continue with Google"
    reaches Google's account chooser with no `redirect_uri_mismatch`, and after choosing the account you
    land back on the alias signed in. If you have no such account, mark UNVERIFIED.
33. NOT IN PREVIEW D: Codex built D from `29904ce`, before the November 19 merges, so mark this item
    "N/A on D" and do not test it there. It is kept for the next preview. Account B's own workspace on `/`, research area: the
    "Meta Ad Library Signals" card explains that Muse can only count ads that reached the EU and shows
    each watched shop with "Search public Meta Ad Library" and a status such as "Not counted yet". Nothing in
    that card or in the watched shops list mentions a token, an API, a server or "configured". The diagnostics card is titled
    "Your website", not "Storefront Channel Diagnostics (Deterministic Python)", and never mentions
    `artofsarabjitsingh.com` or "72 artworks". `/?workspace=sample` still shows the sample ads and
    diagnostics.

## Report
`docs/launch/HERMES_UX_GAP_NOV19.md` on your own branch: preview URL and SHA, browser and
viewports, PASS / FAIL / UNVERIFIED per numbered item with a screenshot or exact text for each
FAIL, and anything blocked. End with "Ownership released".
