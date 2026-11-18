# Assignment for Antigravity (Gemini): home copy that fits the visitor, and honest sample labels

Prepared November 18, 2026 by Claude at Nav's request. Status: PROPOSED until Nav relays it.
Read `AGENTS.md` (top section and section 12) and `docs/launch/CLAUDE_UX_GAP_NOV16.md` on this
branch first, then `git show origin/codex/coordination-nov16:docs/launch/HANDOFF_CURRENT.md`.

## Why
Home copy written for the sample shop or for a guest shows to every visitor:
1. "Ask Muse what to do next" offers the chips "Why $59.99 entry" and "Gifts under $50" in a
   seller's own workspace. Those are SikhiArt's prices from the sample (`index.html`, `#jrSteerChips`).
2. The add-competitor button reads "Add · 🪙 1 run (live) / 0 in demo", and the note under it says
   "Live crawl uses 1 run. In this saved demo the shop is added to your list and no run is used."
   for everyone (`index.html`, `#addCompetitorForm` and `#addCompetitorCost`, around line 1270).
3. The note after the competitor list says "Public snapshots captured Nov 3, 2026. Only SikhiArt.com
   has a saved Muse Spark brief; new analyses need a live server." (around line 1273). A guest on the
   hosted app needs a free account, not a live server, and "Muse Spark brief" means nothing to them.
4. In the sample shop a watched competitor can show "Couldn't check" and a check time from Nov 16 next
   to "last checked Nov 3" (`muse-shell.js`, the `changeBadges` / "Couldn’t check" code around line
   1290). The sample looks broken.

## Base and branch
- Base: the tip of `origin/claude/ux-gap-ad-loop-nov17` when you start (`git fetch origin` first).
  Record the exact SHA in your report.
- New isolated worktree, new branch `gemini/state-copy-nov18`. Do not use the Mac checkout at
  `/Users/nav/meta-smb-gtm` (detached, dirty, must be preserved).

## Step 0: baseline (read-only, before any edit)
`DEMO_MODE=true META_MODEL_API_KEY= DEMO_KEY= make PY=.venv/bin check` on your base. Claude's result
on `1d15cb9` was 624 passed, 2 skipped, 1 warning. Report your own numbers.

## The four visitor states
Use the helpers already in the `index.html` inline script: `liveSnapshot()` (account snapshot) and
`liveRunsReady()`, and `window.museModes.isSampleMode()`.
- Guest: accounts are configured (`liveSnapshot()?.configured`) and nobody is signed in.
- Signed in, own workspace.
- Signed in, viewing the sample shop.
- Local demo: accounts are not configured (`configured` false). Keep today's demo wording here.

## What to change (exclusive write scope)
1. Chips (`#jrSteerChips` in `index.html`; the "Ask Muse what to do next" block in `reco-actions.js`,
   only to swap the chip set). The sample shop (guest or signed in) keeps the four current chips. A
   seller's own workspace gets four chips with no sample facts, each parsing to a different focus with
   the real parser (`POST /api/v1/directives/parse`, rules in `src/models/directive.py`): pricing,
   products, gifting, posting. For example "How do my prices compare?", "Easier moves", "Gift ideas",
   "Weekly post ideas". Swap the set when the workspace changes (`muse:mode-change`).
2. Add-competitor button and `#addCompetitorCost`, set from the visitor's state (add one function and
   call it wherever `refreshSellerButtons()` runs):
   - Guest: button "Add shop"; note "Analyzing a shop needs a free account. You get 3 free runs, and
     each analysis uses 1."
   - Signed in with runs: button "Add and analyze · 1 run"; note "Muse checks the shop and compares
     it with yours. Uses 1 run."
   - Signed in without runs, or email not confirmed: button "Add shop"; the note says which, and what
     to do (pick a plan, or confirm the email).
   - Local demo: today's wording.
   Do not change what submitting does. Claude's pass 9 already asks guests to sign up on submit
   (`promptForLiveRuns`).
3. The note after the competitor list. Guest: "Saved public snapshots from Nov 3, 2026. Create a free
   account to analyze shops you choose." Signed in: "Saved public snapshots from Nov 3, 2026. New
   analyses use 1 run." Local demo: today's meaning without "Muse Spark brief". If this note shows in
   a seller's own workspace with sample wording, report it; that rendering is in `welcome.js`, which
   is Claude's.
4. Sample freshness (`muse-shell.js`, the competitor monitor rendering only). In the sample shop, do
   not show check-error badges such as "Couldn't check" or check times newer than the snapshot; show
   "Saved snapshot · Nov 3" instead. A seller's own workspace keeps today's behaviour. Do not change
   sample data or its timestamps.
- New test file `tests/test_state_aware_copy.py`. Report `docs/launch/ANTIGRAVITY_STATE_COPY_NOV18.md`.

## Do NOT touch
`seller-memory.js`, `welcome.js`, `workspace-modes.js`, `today.js`, `creator.js`, `first-ad.js`,
`account.js`, `account.css`, `src/api/accounts.py`, `src/services/`, billing, auth, `supabase/`,
`AGENTS.md`, `docs/launch/CLAUDE_UX_GAP_NOV16.md`, and existing tests. In `index.html`, leave
`#setupHero`, `#loggedOutHero`, `#firstMoveCard` (Claude's, in `welcome.js`), the seller-memory panel and
everything outside the scope above alone. The "Local tools" nav item and the `/welcome` header for
guests need Nav's decision: propose in your report, do not change. If you think something outside
your scope must change, write it in the report.

## Script versions
Bump `?v=` only for scripts you change, to `20261118-ag1`, on every page that loads them. Claude
merges your branch and resolves any tag-line conflicts.

## Product rules
- Muse prepares; the seller publishes. Never imply Muse posts or spends for them.
- No invented numbers. "3 free runs" is the trial allowance (`supabase/migrations/billing_repair.sql`).
- No em-dashes in customer-facing copy. No horizontal overflow at 375px.

## Boundaries
No paid Muse calls, real emails, charges, deploys, hosted migrations, auth or settings changes. Do not
read `.env` or print credentials. Do not push to `main`, do not force push, do not edit the
coordination branch. Push only `gemini/state-copy-nov18`.

## Verification and report
- Full offline gate after your change with exact counts, plus the Step 0 line.
- Real browser at 375px and 1440px in all four states for every changed label.
- Do not remove, skip or weaken an existing test; if one fails, report the failure and its cause.
- Report: branch, commit, files changed, exact results, what you checked in a browser, what you did
  not verify, and "Ownership released".
