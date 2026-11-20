# Assignment for Antigravity: `/today` destinations and wording per workspace

Prepared November 20, 2026 by Claude at Nav's request. Your time-budget change is merged (`f77e147`);
thank you, the budget-15 guard and the mutation check were exactly right. Note for your report: the
change also penalises moves over budget for budgets under 15 (a 15-minute move with a 10-minute
budget used to get the +24 bonus). That is more correct and Claude kept it.

This is the `/today` half of your `/create` work in `830f4e8`. A seller's own workspace on `/today`
still gets the sample artist's shops and art wording.

## Base and branch
Tip of `origin/claude/ux-gap-ad-loop-nov17` when you start (`git fetch origin`; record the SHA; it is
`f77e147` or later). New isolated worktree, new branch `gemini/today-destinations-nov20`.

## What is wrong (found by Claude, `src/api/static/today.js` and `today.html`)
- The item dialog's `#destination` offers Pixels, Fine Art America and Saatchi Art in every workspace;
  `shops` (today.js line 5) has no `booking`, `etsy` or `shopify`.
- `#itemHint` says "Pixels is your preferred shop..." and `draftDestination()` says "other shops may
  carry different work".
- `captionText()` adds "Explore the work through the link in my profile." to every Instagram and
  TikTok caption, for a consultant too.
- `#destinationLink` starts as "Pixels ↗"; the scene prompt default says "Keep attention on the
  artwork" and the note under it says "AI scenes can change artwork details".
- The research form's placeholder is "nplusalpha.com or your shop website" (Nav's own domain).

## Change
1. Same destination model as `/create`: own workspaces offer `website`, `booking`, `etsy`, `shopify`,
   `other` with the labels you used there; the sample shop keeps Pixels, Fine Art America, Saatchi Art,
   "Artist website" and "My shop / inquiry page". Old own-workspace `/today` drafts and recommendation
   handoffs with `pixels`, `fineartamerica` or `saatchi` load as `other` with the link kept.
2. Hints, the destination link, the caption's profile-link line, the scene prompt default and its
   note: the sample keeps today's words; own workspaces get neutral words that fit products, services
   or both (use `ownBusinessType`, as `applyOfferWording()` already does). Plain words, no em-dashes,
   no invented facts.
3. Research placeholder: a neutral example such as "your-website.com".

Lesson from `830f4e8` (Claude fixed it in `371b085`): a re-render on a mode or account change is not
an edit. Wrap it with `applyingDraft = true` (as `today.js` does elsewhere) so it never persists the
draft or overwrites the status a Save or Load to account just wrote.

## Tests
- New `tests/test_today_destinations_e2e.py`, 375 and 1440: own products, own services, sample. Check
  the options, the hints, the caption line on Instagram and Facebook, the scene text, and a legacy
  `pixels` own draft loading as `other` with its link. Keep `tests/test_today_any_business_e2e.py`
  and `tests/test_today_brief_states_e2e.py` passing unchanged.
- A mutation check: put the sample destinations back into the own workspace and confirm your test
  fails; say so in the report.
- Required this time, not only the pytest gate: the account audit (27/27), the guest audit (20/20)
  and the UI contracts, all with exact counts:
  `DEMO_MODE=true META_MODEL_API_KEY= DEMO_KEY= /usr/bin/python3 tests/launch_account_audit.py`,
  `DEMO_MODE=true META_MODEL_API_KEY= DEMO_KEY= /usr/bin/python3 tests/launch_browser_audit.py`,
  `node tests/editor_drafts_contract.cjs`, `node tests/today_studio_contract.cjs`,
  `node tests/account_ui_contract.cjs`.

## Exclusive write scope
`src/api/static/today.js`, `today.html` and `today.css` for the items above only (leave the daily
brief and the draft row from pass 14 as they are), the `today.js` version tag (bump to
`20261120-ag1` on every page that loads it, update AGENTS.md's version line), new tests and your
report. Do not touch `muse-shell.js`, `seller-memory.js`, `src/services/seller_memory.py` or
`src/services/digest_preview.py` (Claude, pass 15), `creator.*`, ad account files and `#tab-bids`
(Argon), billing, auth or `supabase/`.

## Boundaries
No paid Muse calls, deploys, migrations, emails, auth or settings changes. Do not read `.env`. Do not
push to `main` or force push. Push only `gemini/today-destinations-nov20`.

## Verification and report
Full offline gate before and after with exact counts
(`DEMO_MODE=true META_MODEL_API_KEY= DEMO_KEY= make PY=/Users/nav/meta-smb-gtm/.venv/bin check`),
plus the audits and contracts above. Report in `docs/launch/ANTIGRAVITY_TODAY_DESTINATIONS_NOV20.md`:
branch, commit, files, results, the mutation check, what you did not verify, and "Ownership
released".
