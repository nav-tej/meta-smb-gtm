# Assignment for Antigravity (Gemini): close the ad loop on home and the first-ad guide

Prepared November 16, 2026 by Claude at Nav's request. Status: PROPOSED until Nav relays it and
Antigravity acknowledges. Read `AGENTS.md` (top section and section 12) and
`docs/launch/CLAUDE_UX_GAP_NOV16.md` on this branch first, then the current handoff:
`git show origin/codex/coordination-nov16:docs/launch/HANDOFF_CURRENT.md`.

## Why
`UX_GAP_BRIEF.md` path 4 says campaign numbers appear with no way to act on them. The guided ad
flow exists at `/first-ad` and is now linked from the home nav, `/today`, `/create` step 4 and
`/progress` (commit `18768d0`). Two ends of the loop are still loose:
1. The home page shows performance and bid advice without pointing to the first-ad guide.
2. The first-ad guide ends at the Ads Manager checklist and never tells the seller to bring
   results back for bid advice.

Claude's work on this branch is in `today.js`, `creator.js` and `workspace-modes.js` (bringing
in the seller's saved shop on the first visit after onboarding). Stay inside the scope below so
the two branches merge cleanly.

## Base and branch
- Base: the tip of `origin/claude/ux-gap-nov16` when you start (`git fetch origin` first). It
  contains `18768d0` (first-ad links) and the later commit "Bring in the seller's own listings
  after onboarding". Record the exact SHA you based on in your report.
- That later commit touched two files in your scope, in places you do not need: four lines in
  `welcome.js` right after onboarding completion (`requestAutoImport`), and the `?v=` version on
  the `workspace-modes.js` and `welcome.js` script tags in `index.html`, `first-ad.html` and
  `welcome.html`. Leave those lines as they are. If you change `welcome.js` or another script,
  bump its `?v=` on every page that loads it.
- If you already started from `18768d0`, keep going and merge the branch tip before you report.
- Work in a new isolated worktree on a new branch `gemini/ad-loop-nov16`. Do not use the Mac
  checkout at `/Users/nav/meta-smb-gtm` (detached, dirty, must be preserved).

## Step 0: independent baseline (read-only, before any edit)
1. Run the full offline gate on your base commit and record the exact counts:
   `DEMO_MODE=true META_MODEL_API_KEY= DEMO_KEY= make PY=.venv/bin check`
   Claude's builder results were 609 passed, 2 skipped on `18768d0` and 613 passed, 2 skipped
   on the branch tip, each with 1 warning and lint and format clean. Report yours separately;
   do not copy these numbers.
2. In a real browser against a local demo-mode server, walk `/create` to step 4 (Ready to share)
   at 375px and 1440px and confirm the "Prepare your first ad" offer is visible, does not cause
   horizontal overflow, and lands on `/first-ad` (own workspace) or `/first-ad?workspace=sample`
   (sample). Claude checked only the markup and link target, not the rendered step.

## Step 1: build (exclusive write scope)
- `src/api/static/index.html`: home journey stages `#loop-improve` and `#loop-iterate`, and the
  bid advice tab (`#tab-bids`, around `#csvUploadLabel` / `#runBidsBtn`). Add one clear path to the
  first-ad guide for a seller with no ad running yet, for example "No ad running yet? Prepare your
  first ad". Static anchors use `href="/first-ad" data-mode-link="/first-ad"` so they follow the
  active workspace (see `syncModeLinks()` in `workspace-modes.js`).
- `src/api/static/welcome.js`: only the signed-in home section, part 7 (Create stage and Improve
  stage empty states). Next to "Create your first post", offer the first-ad guide. Links built in
  JS use `window.museModes.ownHref('/first-ad')`.
- `src/api/static/first-ad.html` and `first-ad.js`: only the final handoff step. Add one line
  telling the seller that after the ad has run for a few days they can export results from Meta
  Ads Manager and upload the CSV on the home bid advice tab, with a link to it. Find or add a
  stable anchor for that tab; do not change how the tab works.
- New test file `tests/test_ad_loop_links.py`.
- Your report `docs/launch/ANTIGRAVITY_AD_LOOP_NOV16.md`.

## Do NOT touch
`today.js`, `today.html`, `creator.js`, `creator.html`, `workspace-modes.js`, `progress.html`,
`account.js`, `muse-shell.js`, `tests/test_first_ad_entry_points.py`, `AGENTS.md`,
`docs/launch/CLAUDE_UX_GAP_NOV16.md`, anything under billing, auth or `supabase/`. No new runtime
endpoints. If you believe one of these needs a change, write it in your report instead.

## Product rules
- Muse prepares the ad. The seller publishes it in Meta Ads Manager. Never write "Launch
  campaign", "we publish" or anything that implies Muse spends money or posts for them.
- No invented metrics, ROAS or results. Sample numbers stay labelled as sample.
- No horizontal overflow at 375px. The `/today` header cannot take another link.
- Do not move or refresh sample data timestamps.
- No em-dashes in customer-facing copy.

## Boundaries
No paid Muse calls, real emails, ads, test charges, hosted migrations, auth-setting changes or
deployments. Do not print credentials or read `.env`. Do not push to `main`, do not force push,
do not edit the coordination branch. Push only `gemini/ad-loop-nov16`.

## Verification and report
- Full offline gate after your change, exact counts, plus the Step 0 baseline as a separate line.
- Browser check at 375px and 1440px in both workspaces for every link you add.
- Do not remove, skip or weaken an existing test. If one fails, report the failure and its cause.
- Report: branch, commit, files changed, exact test results, what was checked in a browser, what
  was not verified, and "Ownership released" when done. Return the branch and commit to Nav.
