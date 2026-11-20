# UX gap pass — November 16, 2026 (Claude)

Branch `claude/ux-gap-nov16`, based on release candidate `27c1f50`, pushed to origin. Scope: check `UX_GAP_BRIEF.md` (a Nov 15 walkthrough of old production) against the candidate, fix what is still open and cheap, and list the rest. No paid Muse calls, emails, deployments, hosted migrations, auth-setting or billing changes, or pushes to main. Not integrated into the candidate and not deployed.

Commits, in order:

| Commit | What |
|---|---|
| `18768d0` | Pass 1: the first-ad guide is reachable. |
| `52350ec` | Docs: proposed assignment for Antigravity, `docs/launch/antigravity-ad-loop-assignment.md`. |
| `a1ee43e` | Pass 2: the editors use the shop saved in onboarding (first version, armed by a flag on the device). |
| `bafd4ac` | Tests only: the real onboarding wizard walked through to the first `/today` visit. |
| `5e0bdab` | Pass 3: the import follows the seller to any device and covers earlier accounts. Replaces the device flag from pass 2. |
| `d684369` | Pass 4: the dashboard before setup is an explicit demo with a nudge to finish setup. |
| `f956b74` | Pass 5 (Nov 17): the same nudge on `/today` and `/create` when they show the sample shop. Needs pass 4. |
| `8a113f2` | Merge of Antigravity's `gemini/ad-loop-nov16` (`a982987`) on branch `claude/ux-gap-ad-loop-nov17`. |
| `d8f4ba2` | Pass 6 (Nov 17): the nudge on every page that shows the sample (`/first-ad`, `/progress`, `/digest`), run from `workspace-modes.js`; home and the wizard opt out. |
| `b6bbb3a` | Pass 7 (Nov 17): signed-in gaps found by comparing guest, new and set-up sellers: a setup hero in the demo, a "Setup not finished" notice when a page is opened directly in the own workspace, `/today` copy fixes, "Try saved n+α example" renamed. |
| `0e3ddb7` | Pass 8 (Nov 17): the home "Ask Muse what to do next" card (was "Tell Muse what to look into") answers in place with moves to act on; the old "Confirm & Apply" only saved to the browser. Gate 620 passed, 2 skipped; audits 27/27 and 20/20. |
| `879a87f` | Pass 9 (Nov 17): setup step 3 suggests competitors from the seller's own website (1 run, unticked) instead of the saved nplusalpha.com example and invented fallbacks; guests asking for suggestions or analysis get a free-account prompt, and the wizard keeps their progress and added shops after sign-in; added shops on home were analyzed at their Meta Ad Library link (fixed). Gate 622 passed, 2 skipped; audits 27/27 and 20/20. `tests/test_welcome_onboarding.py` now expects "1 run" for suggestions (was "0 runs"). |
| `1d15cb9` | Pass 10 (Nov 18): "Start here" card after setup (analyze a competitor for 1 run, or make today's post free); own-workspace "Analyze seller" now analyzes the competitor, not its Meta Ad Library link; memory panel is one line until Muse remembers something; "up to 5 listings" wording. Gate 624 passed, 2 skipped; audits 27/27 and 20/20. |
| pass 11 | Pass 11 (Nov 18): merged `gemini/state-copy-nov18` (`c9efa56`); `tests/test_steer_answer_e2e.py` asks the own-workspace chip "How do my prices compare?". A live competitor analysis started from home (seller rows, added shops, the "Start here" card) told Muse the seller was "Fine artist selling Sikh & Punjabi heritage art" for every account; it now describes the seller's shop from setup (name, website, product titles, price range, research focus) and keeps the artist's context only in the sample shop. `#competitorSnapshotsNote` is worded by `refreshVisitorCopy` alone (welcome.js no longer captures or overwrites it); a seller's own workspace reads "Analyses you run are saved to your workspace. Viewing one again is free." Gate 626 passed, 2 skipped; audits 27/27 and 20/20; UI contract passed. |
| pass 12 | Pass 12 (Nov 18), from Nav's own test with nplusalpha.com, a consulting business: setup step 1 asks "What do you offer?" (Products, Services, Both), guessed from the scanned pages and saved as `onboarding.business_type`; live analyses tell Muse the business type. A finished setup can be edited: "Edit shop setup" in the account dialog opens `/welcome?edit=1` with the saved answers (step 4 included, which used to reopen with defaults), and "Save changes" sends `edit: true` to `/api/v1/onboarding/build`, which now saves the changes and keeps `completed_at` (it used to ignore any submit after the first). The "Ask Muse" parser has a `leads` focus (leads, clients, inquiries, bookings, proposals, Clutch, Upwork, Toptal, LinkedIn); "How can I get more leads from Clutch or Toptal traffic" used to read as Pricing. Gate 629 passed, 2 skipped; audits 27/27 and 20/20; UI contract passed. |
| pass 13 | Pass 13 (Nov 19): `/today` and the suggested moves follow `onboarding.business_type`. A services workspace with nothing picked shows "<business> · choose a service or offer" instead of "Featured piece · <business>", three starter posts about what the business helps with, a recent project and how working together goes, goal Inquiries, and no product-listing scan of its website; a products workspace gets maker wording without art words. The server's offline content plan and the Muse prompt take `business_type`. The seller-memory ranker has services moves (offer, client result, how you work, answer a question, services page) in place of entry prices, gifts, commissions and "up to 5 listings". `business_type: null` keeps the sample artist's wording and moves. Gate 634 passed, 2 skipped; audits 27/27 and 20/20; UI contract passed. A mutation check (artist wording put back into a services post) fails the new browser test. Found, not fixed: the daily brief's empty card on `/today` shows Accept/Dismiss/Archive/Adjust and says "shop website"; the draft storage buttons are unstyled; a 40-minute move can top a 30-minute weekly budget (the time penalty only applies at 15 minutes or less). |
| merge ag2 | Nov 19: merged Antigravity's `gemini/create-any-business-nov18` (e9d20f4) as `bf32ba2`: `/create` and `/first-ad` wording for any business in a seller's own workspace, the upload caption fix, no em-dashes on `/first-ad`. Resolved the `creator.html` script-tag conflict and moved the `first-ad.js` pin in `tests/test_ad_loop_links.py`. First full gate: 635 passed, 1 failed (`test_seller_memory_e2e`, a 10-second browser wait timed out while the machine was slow; it passed 3 of 3 runs alone); rerun: 636 passed, 2 skipped. Audits 27/27 and 20/20; UI contract passed. Next briefs: `argon-ad-networks-nov19.md` (ad account connections: spec plus a read-only Meta slice) and `antigravity-competitor-research-any-business-nov19.md` (reliable e2e tests, services-aware competitor research, honest competitor ads). Claude keeps `/today`, `muse-shell.js` and `src/services/seller_memory.py`. |
| merge nov19 | Nov 19: merged `gemini/competitor-research-nov19` (27f7eb1, as 4a48cb9: e2e waits on real conditions, `services` and `case_studies` URL buckets, services prompts behind an optional `business_type`, own-workspace ad status per watched shop) and `gemini/ad-networks-nov19` (9b8e76b, as 259645e: `AD_NETWORKS_SPEC.md`, read-only Meta client behind `AD_CONNECT_ENABLED=false`, nothing mounted). Reviewed both diffs: in scope; the Meta client only sends GETs with a bearer header, checks pagination hosts and strips tokens. Claude then reworded the own-workspace ad status for sellers: hosted has no Ad Library token, so every watched shop said "API token not configured" plus a long API note. Now the card says "Not counted yet" and leads with the public Ad Library link. A row gets a status line only when Muse counted ads, and server messages never reach the page. The diagnostics and ads cards no longer say "Deterministic Python", "72 artworks" or "Sample competitor ads" in the own workspace. New browser case for the no-token state. Gate 651 passed, 2 skipped (first run, no flakes); audits 27/27 and 20/20; both UI contracts passed. |
| pass 14 | Pass 14 (Nov 20), the `/today` items left over from pass 13. The daily brief now fits the state. The sample shop keeps the full brief. A seller's own workspace reads "Your shop’s brief is not built yet": `/today` only builds the sample brief, so the old "Your brief fills in once Muse has checked the competitors you track" was not true. Its links jump to the editor (focusing the website field) or open the sample brief. A signed-out visitor gets "See what a daily brief looks like" with the same two links. Empty states no longer show the three empty columns, Re-check, or Accept/Dismiss/Archive/Adjust on a setup prompt. Found while fixing it: the focus card's triage key was fixed at page load, so accepting the sample focus stored it under the loading title (old code: key `a1gf3eot` for "Feature your Empowering Women series", which hashes to `ahtu9ch`). The card now takes triage only with `data-idea`, re-keyed on every new idea. The draft row moved from above the page into the editor under "I posted this", with quiet buttons. Its status replaces "Checking device draft…" once the workspace is known, Save/Load to account hide in the sample shop, and "Recover previous device draft" shows only when there is a backup. On a phone, a post with no photo shows a short dashed prompt instead of an empty 4:5 frame, and crop controls hide until there is a photo. Wording: "Remember this as my website when I find items", "Save website only", and "Up to 30 minutes a week" (was "<= 30 min/wk"). Own workspace at 375px: the editor starts at 2,518px (was 3,233); signed out: 1,945px (was 2,682). New `tests/test_today_brief_states_e2e.py` (375 and 1440, three states); mutation checks: triage put back on every card and the draft status left unsettled each fail it. Gate 664 passed, 2 skipped; guest audit 20/20; UI contracts (drafts, account, today, shell, polish) passed. The account audit failed 4 of 27 cases (`account-create-isolation`, `-conflict`, `-409-race`, `account-editor-merge`) on the base commit too: bisected to the `/create` merge `830f4e8` (`f8b4355` passes 7/7 account cases). That merge ran only the pytest gate, not the audits, so the regression went unnoticed. Cause: its new branch in `applyCreatorMode` calls `refreshPreview()`, which persists the draft, and Save/Load to account refresh the account, which re-runs that branch. So "A different account draft exists" and "No account draft" were replaced at once by "Saved on this device". Fixed by running that re-render with `applyingDraft` set; account audit 27/27. Found, not fixed: the seller's own brief is never requested on `/today` though `daily_brief()` accepts an account; "(no fresh research ran)" in the context bar comes from `seller_memory.py` (Antigravity's scope today); `/today`'s item dialog still offers Pixels, Fine Art America and Saatchi Art in a seller's own workspace, and its Instagram caption adds "Explore the work through the link in my profile" for every business (the `/create` fix in `830f4e8` did not cover `/today`). |
| merge nov20 | Nov 20: merged Antigravity's `gemini/time-budget-nov20` (5b616a7, as `f77e147`): every weekly budget now compares a move's minutes with the seller's; over-budget moves read "Takes about N minutes, more than your M minutes this week" and rank below every move that fits; if none fits, shortest first. Budget-15 scores are unchanged; under 15, moves over the budget are now penalised (a 15-minute move with a 10-minute budget used to get the bonus). Reviewed: in scope, 13 new tests, mutation check fails as it should. Gate on the merge 677 passed, 2 skipped; account audit 27/27; guest audit 20/20. Their report notes two follow-ups for Claude: the home card prefixes the over-budget reason with "Why this fits:", and the digest says "Sized for ~N min/week" without checking the move. Next briefs: `antigravity-today-destinations-nov20.md`; Codex's review range widened to `29904ce..f77e147`. |
| merge argon nov20 | Nov 20: merged Argon's `gemini/meta-connect-followups-nov20` (7ddc4ed, as `7a3681b`): `META_LOGIN_CONFIG_ID` sends `config_id` instead of `scope` when set; every callback error, and a signed-out or unverified seller, now gets a 302 to `/?ad_connect_error=<code>#tab-bids` from a fixed list of 7 codes with the state cookie cleared, never JSON; `#metaConnectBar` and route messages in plain words; spec and Phase 1a report now record the real app. Reviewed: in scope, docs cited, mutation check reported. Claude fixed one bug on top (`2f0903d`): the new plain-wording filter ignores case and also ran on the seller's own ad account names, so "Capital Therapy" or "Rapid Repairs" (they contain "api") showed as "Ad Account". Names are now shown as is (still escaped), and the browser test uses "Rapid Repairs Studio Ads" and fails on the old filter. Report correction: the migration creates `muse_private.ad_account_connections`, not `public.`. Gate 677 passed, 2 skipped; account audit 27/27; guest audit 20/20. Vercel note for Argon's usage investigation: deploys are not the cost (19 in 11 days, all manual CLI, about 20 s each; branch pushes do not build). `vercel.json` rewrites every path to the Python function, so each page load runs it once per CSS, JS and image file, and `/static` responses carry no CDN cache header. |

Passes 3 and 4 are separate commits so the coordinator can take either one. Both touch `workspace-modes.js` and the script version tags, so taking pass 4 alone needs a small manual merge.

## Pass 1: the first-ad guide is reachable

| File | Change |
|---|---|
| `src/api/static/index.html`, `progress.html` | "First ad guide" link in the top nav (inside the hamburger menu on mobile). |
| `src/api/static/today.html` | "Prepare your first ad" line under the delivery note. |
| `src/api/static/creator.html` | "Prepare your first ad" offer on step 4 (Ready to share). |
| `src/api/static/workspace-modes.js` | `syncModeLinks()`: links marked `data-mode-link="/path"` follow the active workspace (sample vs. own). |
| `src/api/main.py` | `/creator` redirects (307) to `/create`, keeping the query string. |
| `tests/test_first_ad_entry_points.py` | 8 tests: entry points on four pages, honest offer copy, mode-link wiring, redirect. |

Why: `/first-ad` (the guided ad preparation flow) existed in the candidate with no inbound link from any page or script. A seller could only reach it by typing the URL, which is why the ad path looked missing.

## Passes 2 and 3: the editors bring in the seller's own listings

The brief's path 1 complaint: onboarding takes the shop URL, then `/today` and `/create` open on a placeholder item ("Featured piece · Shop name") until the seller presses "Find products".

How it works now (pass 3):

| File | Change |
|---|---|
| `src/api/accounts.py` | `GET /api/v1/account/workspace` adds `listing_import: {"first_visit": bool}`, true when the account has a saved shop website. Derived on every read by `listing_import_hint`; nothing is stored and the document and version are untouched. |
| `src/api/static/workspace-modes.js` | `museModes.autoImportPending(ownerId, page, workspace)` is true only with that signal and when this device has not tried yet for this account. `finishAutoImport` records the attempt in `localStorage` (`muse.autoimport.tried.v1:<ownerId>`). `requestAutoImport` is gone. |
| `src/api/static/welcome.js` | The four lines that left a request on the device at the end of onboarding are removed. |
| `src/api/static/today.js` | With the signal and an untouched placeholder draft, `/today` scans the shop without locking the page, starts on the first listing, rebuilds the three-post plan for it and offers its images. The photo is not chosen for the seller. |
| `src/api/static/creator.js` | With the signal, `/create` lists the seller's listings under "Find products" without a click. Nothing in the draft changes until they pick one. |
| `today.js`, `creator.js` | Listings found in one workspace are cleared when the seller switches between their own workspace and the sample. |
| `today.js` | Bug fix from pass 2: "Find products" (and picking a listing) left "Your next three posts" empty, because the plan rebuild ran while the page was locked and returned early. Confirmed on `52350ec`: 3 cards before the import, 0 after. Now 3 after, written for the imported item. An existing plan is kept, so a paid Muse plan is never overwritten. |
| `tests/test_first_visit_import_e2e.py` | 5 tests: the server signal against the real route, the per-device memory, the editor wiring, a real-browser run with eight scenarios, and the real onboarding wizard followed by the first `/today` visit. |
| `tests/test_shop_image_suggestions_e2e.py` | 13 lines added, no assertion changed. See "Existing test touched" below. |

What changed between pass 2 and pass 3, and why:
- Pass 2 armed the import with a flag that onboarding left in the browser. It never fired on a second device, or for accounts that finished setup before the change.
- The signal now comes from the account, so it is the same on every device. "Tried" stays on the device on purpose: drafts are per device, so a new device starts on a placeholder and should get the listing too.
- Storing "tried" in the workspace document was considered and rejected. Every workspace write bumps the document version, and seller memory (loaded on `/today` and `/create`) saves with the version it read and opens a conflict dialog on a mismatch (`src/api/seller_memory.py`, 409 on `expected_version`). An automatic write on the first visit would hand a new seller that dialog on their next memory save.
- The rule is "a saved shop website", not "finished onboarding", so a website saved from an editor counts too.

Guards, each covered by the browser test:
- No signal from the server: neither editor scans. A saved shop website in the document alone is not enough. Browser tests that mock the workspace response omit the field, so they do not start crawling.
- Sample workspace open: nothing is scanned and nothing is recorded as tried.
- The seller already has their own item in the draft on this device: nothing is scanned, and it is recorded as tried.
- The seller switches to the sample shop mid-scan: the late result is discarded, no "Looking…" message is left behind, and the import runs when they return to their own workspace.
- Another account signs in on the same tab mid-scan: the first account's scan is dropped, its result lands nowhere and is recorded for neither account; the second account gets its own listings.
- Once per editor per account per device. A failed scan counts as tried; the seller still has "Find products".
- Browser storage blocked: nothing is scanned unasked, because the attempt could not be remembered.
- The scan is the existing public crawl (`/api/v1/ingest-storefront`). No Muse run is used; the plan is the starter plan.

Limits:
- A device does the import once per editor per account. A seller with three devices gets three scans of their own site on `/today`, one per device, each only while that device's draft is still the placeholder.
- On `/today` the item, description and price hint come from the first listing found. The seller is told to check product facts and can pick another listing under "Change".
- Accounts that finished setup earlier get the import on their next visit only where the device draft is still the untouched placeholder. A device they have already worked on is left alone.

Existing test touched: `tests/test_shop_image_suggestions_e2e.py` serves the real workspace route with two accounts that have saved shop websites, and its fakes return the same listing ("Botanical Linocut") for every shop. With the signal on, the second account's own first-visit import put that listing in its draft, which the test reads as a leak from the first account. I confirmed it was the second account's own import (the draft source read "From cedarkiln.test") and that the test passes when only that account's import is suppressed. The test now runs as a device where the import has already happened (it seeds the "tried" key for both accounts). No assertion was removed or loosened. The cross-account case with distinct listings per account is covered by scenario 8 in `tests/test_first_visit_import_e2e.py`.

## Pass 4: the dashboard before setup is an explicit demo

Nav's decision on the brief's "dashboard before onboarding" item: let a signed-in seller see the dashboard before finishing setup, as an explicit demo that nudges them to complete the wizard, until their own shop and competitors can fill it.

Before: a signed-in seller without completed onboarding who opened `/` was sent to `/welcome` every time. The sample shop was reachable only through the "Explore Sample shop instead" link on the wizard, and its banner offered "Back to my workspace", which led straight back to the wizard.

| File | Change |
|---|---|
| `src/api/static/welcome.js` | `applyHomeModeState`: with setup unfinished, opening `/` switches to the sample workspace instead of redirecting, and reports it with `museModes.setSetupPending(ownerId)`. The workspace switcher's own-shop option reads "Finish setup" and goes to `/welcome`. |
| `src/api/static/workspace-modes.js` | `setSetupPending` / `isSetupPending`. In that state the mode banner reads "Demo data · This dashboard shows a sample shop, Art of Sarabjit Singh, not yours. Finish setup to see your own shop and competitors here." with one action, "Finish setup". It moves directly under the page header (its usual place on the home page is below the hero). |
| Seven HTML pages | `workspace-modes.js` and `welcome.js` at `?v=20261116-uxgap3`; `today.js` and `creator.js` at `uxgap2`. |
| `tests/test_setup_demo_state_e2e.py` | 2 tests, one a real-browser run with five scenarios. |

What did not change:
- Arriving from sign-in still goes to the wizard: the `/account` landing (where email confirmation links arrive), an OAuth return, and a sign-in made on the home page itself.
- Guests see the sample shop exactly as before, banner in its usual place.
- Sellers who finished setup see their own dashboard, and the ordinary sample banner when they look at the sample shop.
- No CSS file changed. `account.css` and `account.js` versions are pinned by `tests/test_signup_followup_e2e.py`.

Limits:
- As shipped in pass 4 the nudge was on the dashboard only; pass 5 extends it to `/today` and `/create`.
- The demo is the sample shop as it is, including the logged-out hero ("Explore the free demo", "No account needed") and the Nov 3 sample data. Only the banner and the workspace switcher are specific to this state.

## Pass 5: the nudge follows the seller into the editors

Before: following a link from the demo dashboard to `/today` or `/create` showed the ordinary sample banner with "Back to my workspace". Those pages read no workspace in sample mode, so they did not know setup was unfinished.

| File | Change |
|---|---|
| `src/api/static/workspace-modes.js` | `museModes.checkSetupPending(ownerId)`: reads the workspace once per account per page load and calls `setSetupPending(ownerId, { editor: true })` when `onboarding.completed_at` is missing. A failed read keeps the ordinary banner. The editor notice reads "Demo data · This page shows a sample shop, Art of Sarabjit Singh, not yours. Finish setup to bring in your own shop and competitors." with "Finish setup" and "Open my workspace". The dashboard notice is unchanged. |
| `today.js`, `creator.js` | One line each in the sample branch: ask only when a signed-in seller (`account_sample`) is viewing the sample. |
| Seven HTML pages | `workspace-modes.js`, `today.js` and `creator.js` at `?v=20261117-uxgap4`. |
| `tests/test_setup_demo_state_e2e.py` | Static checks for the wiring and the two notices; browser scenario 6 (both editors at 375px and 1440px, both buttons, and sellers who finished setup still getting the ordinary banner). |

Why the editors keep "Open my workspace": unlike the dashboard, `/today` and `/create` work before setup (the seller can paste a shop website), so the nudge must not trap them in the sample.

Limits: `/first-ad`, `/progress` and `/digest` still show the ordinary sample banner. The read refreshes the workspace version that `account.js` holds; the editors reload the workspace when the seller switches to their own, so nothing saves against it in sample mode.

## Verification

- `DEMO_MODE=true META_MODEL_API_KEY= DEMO_KEY= make PY=<main checkout>/.venv/bin check` on the final code (`f956b74`): **616 passed, 2 skipped, 1 warning**, ruff lint and format clean (133.15s). The 2 skips are the PGlite SQL tests, which need `BILLING_PGLITE_DIR`. Earlier points: 609 after pass 1, 613 after pass 2, 614 after `bafd4ac`.
- `DEMO_MODE=true META_MODEL_API_KEY= DEMO_KEY= /usr/bin/python3 tests/launch_account_audit.py`: **27 passed, 0 failed**. `tests/launch_browser_audit.py` (guest flows): **20 passed, 0 failed**. `node tests/account_ui_contract.cjs`: passed. All on the final code, real Chromium.
- Pass 3:
  - The import browser tests ran three times in a row without a flake. They abort and record any browser request that leaves the local test server; none did.
  - The real route is tested with a stubbed store: an account that finished setup on Nov 8 with nothing written for this feature gets `first_visit: true`, and the saved document and version come back unchanged.
- Pass 4:
  - The browser test fails when each rule is broken in turn: always redirecting, forgetting that the visitor was signed out, and never reporting setup as pending.
  - Screenshots at 1440px and 375px: the demo notice is the first thing under the header; no horizontal overflow.
  - The dashboard reached by opening `/` was compared with `/?workspace=sample` loaded directly, for the same account: identical visible text, hidden sections, links and API calls, no page or console errors.
- Pass 5:
  - The demo-state tests fail when the `/today` call is removed (static check and browser timeout); they and the import tests passed twice more in a row.
  - Screenshots of `/today` and `/create` at 375px and 1440px: the notice sits directly under the header, both buttons visible, no horizontal overflow, no page errors.
- Earlier passes:
  - Pass 1, headless Chromium at 375px and 1440px on `/`, `/today`, `/progress`, `/create`, with and without `?workspace=sample`: no horizontal overflow; link is `/first-ad` in own mode and `/first-ad?workspace=sample` in sample mode.
  - `/create` step 4 as rendered, sample workspace, 375px and 1440px: the "Prepare your first ad" offer is visible and lands on `/first-ad?workspace=sample` (one-off script, not a suite test).
  - One regression caught and fixed in pass 1: the link first went in the `/today` header, which overflowed 375px by 29px and failed `tests/test_signup_followup_e2e.py::test_375px_add_photo_action_and_real_fixture_first_export`. It moved into the page body.
- Not verified: the hosted preview; a real signed-in account; a real crawl of a real shop from the auto-import (every crawl here was mocked or faked); the workspace read against real Supabase (stubbed here); the `/create` step 4 first-ad offer in a seller's own workspace (link target only).

## Brief items against candidate `27c1f50`

| Brief item | State | Action |
|---|---|---|
| Auto-confirm signup (P0) | Fixed earlier. No `email_confirm=True` remains; verification comes from the Auth server's `email_confirmed_at`. Hosted email delivery is still unverified. | None here |
| Stripe live key exposed (P0) | Unverified. Reconciliation says the keys seen were test keys. | Nav to confirm and rotate if live |
| Ad flow missing (P0) | `/first-ad` exists: outcome, creative, audience, budget, manual Ads Manager handoff marked not published. It was unreachable. | Fixed in pass 1 |
| Personalization bridge (P1) | Onboarding shop URL prefilled `/today` and `/create`, but the seller had to press "Find products". | Fixed in passes 2 and 3 |
| Demo data frozen at Nov 3 (P1) | Left as is on purpose. Moving dates without a recrawl would fake freshness. | Open: a real, approved recrawl |
| `/creator` 404 (P1) | No internal link pointed to it. | Alias added in pass 1 |
| Dashboard before onboarding (P1) | Signed-in sellers without onboarding were sent to `/welcome`. | Fixed in pass 4, as an explicit demo (Nav's decision) |
| Digest cadence (P2) | Weekly, biweekly, monthly and paused exist in digest preview. Scheduled sending is not built; `RESEND_API_KEY` and `DIGEST_FROM_EMAIL` are absent in Vercel. | Open: delivery slice |
| Free runs 3 to 10 (P2) | Held until abuse controls are settled. | None |

## Next steps, in order

1. Coordinator: review this branch's diff against `27c1f50` and decide what joins the candidate. Passes 3 and 4 change behaviour for signed-in sellers and `accounts.py` gains a response field, so they deserve an independent gate run and a hosted check with a real account and a real shop.
2. Antigravity: `docs/launch/antigravity-ad-loop-assignment.md`, a paste-ready message given to Nav on Nov 17. Links from the home performance and bid advice sections to the first-ad guide, and from the end of the guide back to the bid advice upload. No `gemini/ad-loop-nov16` branch existed on origin when checked.
3. Done in pass 6: the nudge shows on every page that shows the sample. Gate on that commit: 618 passed, 2 skipped; account audit 27/27; guest audit 20/20. Pass 7 (`b6bbb3a`) closes the direct-visit case with a "Setup not finished" notice and gives the demo its own hero (Claude's option A; Nav can change the copy in `#setupHero` in `index.html`). Gate on `b6bbb3a`: 618 passed, 2 skipped; account audit 27/27; guest audit 20/20. Still open: `/welcome` is labelled "Signed-in shop setup" for guests; the `/today` plan falls back to "Featured piece · <shop>" titles when no listing was imported.
4. The demo dashboard still shows the logged-out hero to a signed-in seller. A hero written for "you have an account, your shop is not set up yet" would make the demo state clearer. That is a copy and design decision for Nav.

Ownership of this scope is released.
