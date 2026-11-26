# Antigravity brief: a seller's own pages never show the sample shop (Nov 26)

Coordinator: Claude. Nav assigned this on Nov 26. Report:
`docs/launch/ANTIGRAVITY_OWN_PAGES_SAMPLE_AUDIT_NOV26.md`.
Base: `origin/claude/ux-gap-ad-loop-nov17` (the commit that adds this brief, or later).
Branch: `gemini/own-pages-sample-audit-nov26`. Worktree: `/Users/nav/muse-worktrees/own-pages-audit`
(never `/tmp`). Commit and push at every checkpoint. Every push builds a protected preview; never
push to `main` or `production`, never deploy. Read `AGENTS.md` first, especially the top section
and "Own workspace never shows the sample shop".

## Why

Production now runs the Nov 25 release, and Nav is using their own workspace (a services
business). On Nov 25 they hit two places where it showed the sample artist's content:
- the "Ask Muse what to do next" card on the home (fixed in `cdb5b88`);
- the notification bell, which lists "SikhiArt.com: 2 new listings", "Feature your Empowering
  Women series", "Refresh the creative on Golden Temple - Gift Buyers" (Claude is fixing it in
  `muse-shell.js`).

The home has browser tests for this (`tests/test_any_business_home_e2e.py`). The other pages do
not. Find and fix every leak there.

## What to do

1. **Local server only, fake accounts.** Copy the `any_business_server` fixture pattern from
   `tests/test_any_business_home_e2e.py` (fake `resolve_account`/`load_workspace`/`save_workspace`/
   `snapshot`, no crawls, no Muse). Accounts to cover:
   - a services business (goal "More client inquiries", LinkedIn and website);
   - a products seller (goal "More sales", Instagram);
   - a seller with saved competitor checks (`preferences.competitor_checks`) and one saved
     YouTube video (`preferences.content_sources.youtube`);
   - a seller who finished setup and has nothing else.
2. **Pages:** `/today`, `/create`, `/digest`, `/first-ad`, `/progress`, `/welcome?edit=1`, at
   375 and 1440 px, signed in to each own account. Not the home (`/`): Claude owns it.
3. **What counts as a leak.** Any visible text, image, link or count that belongs to the sample
   shop. Start with: Sarabjit, SikhiArt, Sikh, Golden Temple, Ek Onkar, Pixels, Fine Art
   America, Saatchi, Gurinderpreet, Manjot, Gurdish, Empowering Women, Mai Bhago, $59.99,
   "Gift Buyers", "Retargeting - Site Visitors", the sample's ad set names and saved Muse Image
   ads. Also count shop and artwork wording ("your prints", "artwork", "listing") shown to a
   services business as if it were about them.
4. **Fix each leak with the smallest honest change:** render from the seller's own data, mark
   the block `data-sample-only` where that pattern exists, or show an honest empty state ("Not
   set up yet", with a link to the step that fills it). Never invent the seller's data, and never
   change what the sample shop (`?workspace=sample`) shows.
5. **Test:** add `tests/test_own_pages_no_sample_e2e.py`. For every page, own account and
   width:
   - none of the sample strings appear in the page's visible text;
   - no page errors;
   - no sideways scroll at 375 px.

   Plus one check per page that the sample shop still shows its sample content.
6. **Mutation checks:** revert one fix per page you changed, and each must fail a test. Report
   the command and result.

## Do not touch

Claude is working in these:
- `src/api/static/index.html`, `welcome.js`, `muse-shell.js`, `muse-shell.css`;
- `seller-memory.js`, `seller-memory.css`;
- `src/api/intel.py`, `src/api/main.py`;
- `src/services/saved_competitors.py`, `src/services/seller_memory.py`.

If a leak is caused there (the bell is), write it in your report instead.

Version bumps: bump each script you change to `20261126-ag1` on every page that loads it, and
update the pins in `tests/test_create_any_business.py` (`creator.js`) and
`tests/test_ad_loop_links.py` (`first-ad.js`). Put the version list in your report; Claude updates
AGENTS.md's version line at merge. Script tags share a line in `today.html` and `creator.html`, so
expect Claude to resolve a one-line conflict there.

## Gate

- `DEMO_MODE=true META_MODEL_API_KEY= DEMO_KEY= make PY=/Users/nav/meta-smb-gtm/.venv/bin check`.
- Both audits: `/usr/bin/python3 tests/launch_account_audit.py` and `tests/launch_browser_audit.py`.
- All 8 Node contracts.
- Rules: no live calls, no deploys, no `*.vercel.app` targets, no secrets.

## Report

A table: page, what leaked, why, the fix, the commit. Then anything you left alone and why, the
mutation checks, and the gate results.
